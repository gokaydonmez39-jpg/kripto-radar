#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, threading, time, urllib.error, urllib.request
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

def classify_exception(exc):
    """Return machine-readable retry semantics for provider failures.

    Retryable failures are transport/upstream conditions that may recover
    without operator/config changes. Definitive auth/permission/not-found and
    other client errors must not poison the transient circuit breaker.
    """
    if isinstance(exc, urllib.error.HTTPError):
        status=int(getattr(exc,"code",0) or 0)
        if status in {408,425,429} or 500 <= status <= 599:
            return {"retryable":True,"code":"HTTP_TRANSIENT","http_status":status}
        return {"retryable":False,"code":"HTTP_DEFINITIVE","http_status":status}
    if isinstance(exc, json.JSONDecodeError):
        return {"retryable":True,"code":"UPSTREAM_INVALID_JSON","http_status":None}
    if isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError, OSError)):
        return {"retryable":True,"code":"TRANSPORT_TRANSIENT","http_status":None}
    return {"retryable":False,"code":"INTERNAL_OR_DEFINITIVE","http_status":None}

def _record_success(provider):
    l,p=_provider_state(provider)
    p.update({
        "status":"HEALTHY","consecutive_failures":0,"last_success_at_utc":now(),
        "last_error":None,"last_error_code":None,"last_error_retryable":None,
        "last_http_status":None,"open_until_epoch":0
    })
    l["updated_at_utc"]=now(); save_ledger(l)

def _record_failure(provider,exc,circuit_failures,cooldown):
    cls=classify_exception(exc)
    l,p=_provider_state(provider)
    err=f"{type(exc).__name__}:{str(exc)[:240]}"
    if cls["retryable"]:
        n=int(p.get("consecutive_failures") or 0)+1
        p.update({
            "status":"DEGRADED","consecutive_failures":n,
            "last_failure_at_utc":now(),"last_error":err,
            "last_error_code":cls["code"],"last_error_retryable":True,
            "last_http_status":cls["http_status"]
        })
        if n>=circuit_failures:
            p["open_until_epoch"]=time.time()+cooldown
            p["status"]="CIRCUIT_OPEN"
    else:
        # Definitive failures (e.g. 401/403/404) need a config/permission/source
        # change, not repeated hammering. They do not count toward the transient
        # circuit and also clear a circuit that may have been poisoned by older
        # versions that misclassified definitive 4xx responses.
        p.update({
            "status":"NONRETRYABLE_ERROR","consecutive_failures":0,
            "last_failure_at_utc":now(),"last_error":err,
            "last_error_code":cls["code"],"last_error_retryable":False,
            "last_http_status":cls["http_status"],"open_until_epoch":0
        })
    l["updated_at_utc"]=now(); save_ledger(l)
    return cls

def _check_circuit(provider,now_s):
    l,p=_provider_state(provider)
    open_until=float(p.get("open_until_epoch") or 0)
    if open_until>now_s:
        raise RuntimeError(f"CIRCUIT_OPEN:{provider}:{int(open_until-now_s)}s")

def _retry_sleep(provider,url,attempt_index,base_delay,jitter):
    """Deterministic bounded jitter so retries do not synchronize in herds."""
    d=max(0.0,float(base_delay))
    j=max(0.0,min(float(jitter),0.5))
    if d<=0 or j<=0:
        if d>0: time.sleep(d)
        return
    h=hashlib.sha256(f"{provider}|{url}|{attempt_index}".encode()).digest()
    u=int.from_bytes(h[:8],"big")/(2**64-1)
    factor=1.0 + j*(2*u-1)
    time.sleep(max(0.0,d*factor))

def _attempt_budget(timeout,retry_delays):
    ds=[max(0.0,float(x)) for x in (retry_delays or ())]
    return (len(ds)+1)*float(timeout)+sum(ds)+5.0

def fetch_json(provider,url,headers=None,timeout=20,cache_ttl=0,circuit_failures=3,cooldown=120,retry_delays=(1.0,4.0),retry_jitter=0.20):
    key=provider+"|"+url
    now_s=time.time()
    with _LOCK:
        hit=_MEM.get(key)
        if hit and hit[0]>now_s: return hit[1]
    _check_circuit(provider,now_s)
    evt=None
    with _LOCK:
        evt=_INFLIGHT.get(key)
        if evt is None:
            evt=threading.Event(); _INFLIGHT[key]=evt; owner=True
        else: owner=False
    if not owner:
        evt.wait(_attempt_budget(timeout,retry_delays))
        with _LOCK:
            hit=_MEM.get(key)
        if hit and hit[0]>time.time(): return hit[1]
        raise RuntimeError(f"SINGLE_FLIGHT_OWNER_FAILED:{provider}")
    try:
        delays=tuple(retry_delays or ())
        last=None
        for attempt in range(len(delays)+1):
            try:
                req=urllib.request.Request(url,headers=headers or {"Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=timeout) as r:
                    data=json.loads(r.read().decode("utf-8"))
                _record_success(provider)
                with _LOCK: _MEM[key]=(time.time()+max(1,cache_ttl),data)
                return data
            except Exception as e:
                last=e
                cls=classify_exception(e)
                if (not cls["retryable"]) or attempt>=len(delays):
                    _record_failure(provider,e,circuit_failures,cooldown)
                    raise
                _retry_sleep(provider,url,attempt+1,delays[attempt],retry_jitter)
        raise last if last is not None else RuntimeError(f"RETRY_EXHAUSTED:{provider}")
    finally:
        with _LOCK:
            _INFLIGHT.pop(key,None); evt.set()

def fetch_text(provider,url,headers=None,timeout=20,cache_ttl=0,circuit_failures=3,cooldown=120,retry_delays=(1.0,4.0),retry_jitter=0.20):
    key=provider+"|TEXT|"+url
    now_s=time.time()
    with _LOCK:
        hit=_MEM.get(key)
        if hit and hit[0]>now_s: return hit[1]
    _check_circuit(provider,now_s)
    evt=None
    with _LOCK:
        evt=_INFLIGHT.get(key)
        if evt is None:
            evt=threading.Event(); _INFLIGHT[key]=evt; owner=True
        else: owner=False
    if not owner:
        evt.wait(_attempt_budget(timeout,retry_delays))
        with _LOCK:
            hit=_MEM.get(key)
        if hit and hit[0]>time.time(): return hit[1]
        raise RuntimeError(f"SINGLE_FLIGHT_OWNER_FAILED:{provider}")
    try:
        delays=tuple(retry_delays or ())
        last=None
        for attempt in range(len(delays)+1):
            try:
                req=urllib.request.Request(url,headers=headers or {})
                with urllib.request.urlopen(req,timeout=timeout) as r:
                    data=r.read().decode("utf-8")
                _record_success(provider)
                with _LOCK: _MEM[key]=(time.time()+max(1,cache_ttl),data)
                return data
            except Exception as e:
                last=e
                cls=classify_exception(e)
                if (not cls["retryable"]) or attempt>=len(delays):
                    _record_failure(provider,e,circuit_failures,cooldown)
                    raise
                _retry_sleep(provider,url,attempt+1,delays[attempt],retry_jitter)
        raise last if last is not None else RuntimeError(f"RETRY_EXHAUSTED:{provider}")
    finally:
        with _LOCK:
            _INFLIGHT.pop(key,None); evt.set()
