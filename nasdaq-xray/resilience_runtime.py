#!/usr/bin/env python3
from __future__ import annotations
import json, os, threading, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LEDGER=ROOT/"provider_health_ledger.json"
CACHE=ROOT/".resilience_cache"
_LOCK=threading.Lock()
_INFLIGHT={}
_MEM={}

def now(): return datetime.now(timezone.utc).isoformat()

def load_ledger():
    try: return json.loads(LEDGER.read_text())
    except Exception: return {"schema":"XRAY_PROVIDER_HEALTH_LEDGER_V1","providers":{}}

def save_ledger(x):
    tmp=LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
    tmp.replace(LEDGER)

def _provider_state(provider):
    l=load_ledger(); p=l.setdefault("providers",{}).setdefault(provider,{})
    return l,p

def fetch_json(provider,url,headers=None,timeout=20,cache_ttl=0,circuit_failures=3,cooldown=120):
    key=provider+"|"+url
    now_s=time.time()
    with _LOCK:
        hit=_MEM.get(key)
        if hit and hit[0]>now_s: return hit[1]
    l,p=_provider_state(provider)
    open_until=float(p.get("open_until_epoch") or 0)
    if open_until>now_s:
        raise RuntimeError(f"CIRCUIT_OPEN:{provider}:{int(open_until-now_s)}s")
    evt=None
    with _LOCK:
        evt=_INFLIGHT.get(key)
        if evt is None:
            evt=threading.Event(); _INFLIGHT[key]=evt; owner=True
        else: owner=False
    if not owner:
        evt.wait(timeout+5)
        with _LOCK:
            hit=_MEM.get(key)
        if hit and hit[0]>time.time(): return hit[1]
        raise RuntimeError(f"SINGLE_FLIGHT_OWNER_FAILED:{provider}")
    try:
        req=urllib.request.Request(url,headers=headers or {"Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=timeout) as r:
            data=json.loads(r.read().decode("utf-8"))
        l,p=_provider_state(provider)
        p.update({"status":"HEALTHY","consecutive_failures":0,"last_success_at_utc":now(),"last_error":None,"open_until_epoch":0})
        l["updated_at_utc"]=now(); save_ledger(l)
        with _LOCK: _MEM[key]=(time.time()+max(1,cache_ttl),data)
        return data
    except Exception as e:
        l,p=_provider_state(provider)
        n=int(p.get("consecutive_failures") or 0)+1
        p.update({"status":"DEGRADED","consecutive_failures":n,"last_failure_at_utc":now(),"last_error":f"{type(e).__name__}:{str(e)[:240]}"})
        if n>=circuit_failures: p["open_until_epoch"]=time.time()+cooldown; p["status"]="CIRCUIT_OPEN"
        l["updated_at_utc"]=now(); save_ledger(l)
        raise
    finally:
        with _LOCK:
            _INFLIGHT.pop(key,None); evt.set()
