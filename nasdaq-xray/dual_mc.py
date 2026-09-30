#!/usr/bin/env python3
"""XRAY dual-source conservative market-cap stage.
Sources: Eastmoney single-symbol company info + Nasdaq.com quote summary.
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
IN=ROOT/"market_candidates.json"
OUT=ROOT/"dual_mc_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.1"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
MAX_NEW=int(os.getenv("XRAY_DUAL_MC_BATCH","40"))
MAX_ATTEMPTS=int(os.getenv("XRAY_DUAL_MC_MAX_ATTEMPTS","4"))
PASS_FLOOR=2_100_000_000
FAIL_CEILING=2_000_000_000
MAX_REL_DIFF=0.10

def get_json(url,params=None,headers=None,timeout=35,retries=3):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    hdr={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"}
    if headers: hdr.update(headers)
    last=None
    for k in range(retries):
        try:
            req=urllib.request.Request(url,headers=hdr)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e
            time.sleep(0.7*(k+1)+random.uniform(0.1,0.4))
    raise last

def load(path):
    if path.exists():
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:pass
    return {}

def atomic(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except Exception:return None

def parse_market_cap_text(x):
    if x is None:return None
    s=str(x).strip()
    if not s or s.lower() in {"n/a","na","--"}:return None
    mult=1.0
    suffix=s[-1:].upper()
    if suffix=="T":mult=1e12;s=s[:-1]
    elif suffix=="B":mult=1e9;s=s[:-1]
    elif suffix=="M":mult=1e6;s=s[:-1]
    cleaned=re.sub(r"[^0-9.\-]","",s)
    v=finite(cleaned)
    return None if v is None else v*mult

def eastmoney_mc(symbol):
    d=get_json("https://push2.eastmoney.com/api/qt/stock/get",{
        "secid":"105."+symbol,"fltt":"2","invt":"2",
        "fields":"f43,f57,f58,f84,f85,f116,f117"
    },{"Referer":"https://quote.eastmoney.com/"})
    data=d.get("data") or {}
    if str(data.get("f57") or "").upper()!=symbol:
        raise RuntimeError("EASTMONEY_IDENTITY_MISMATCH")
    mc=finite(data.get("f116"))
    px=finite(data.get("f43"))
    shares=finite(data.get("f84"))
    if mc is None:raise RuntimeError("EASTMONEY_MC_MISSING")
    return {"market_cap":mc,"price":px,"shares":shares}

def nasdaq_mc(symbol):
    d=get_json(
        "https://api.nasdaq.com/api/quote/"+symbol+"/summary",
        {"assetclass":"stocks"},
        {
            "Origin":"https://www.nasdaq.com",
            "Referer":"https://www.nasdaq.com/",
            "Accept":"application/json, text/plain, */*",
        }
    )
    status=d.get("status") or {}
    if status.get("rCode") not in (200,"200"):
        raise RuntimeError("NASDAQ_STATUS_NOT_200")
    data=d.get("data") or {}
    if str(data.get("symbol") or "").upper()!=symbol:
        raise RuntimeError("NASDAQ_IDENTITY_MISMATCH")
    summary=data.get("summaryData") or {}
    exchange=((summary.get("Exchange") or {}).get("value") or "")
    if not str(exchange).upper().startswith("NASDAQ"):
        raise RuntimeError("NASDAQ_EXCHANGE_MISMATCH")
    value=((summary.get("MarketCap") or {}).get("value"))
    mc=parse_market_cap_text(value)
    if mc is None:raise RuntimeError("NASDAQ_MC_MISSING")
    return {"market_cap":mc,"exchange":exchange}

def classify(symbol):
    try:
        em=eastmoney_mc(symbol)
        nq=nasdaq_mc(symbol)
        a=em["market_cap"];b=nq["market_cap"]
        rel=abs(a-b)/max(a,b)
        detail={"eastmoney":em,"nasdaq":nq,"relative_diff":rel}
        if rel>MAX_REL_DIFF:
            return "UNKNOWN_CONFLICT",detail
        if a>=PASS_FLOOR and b>=PASS_FLOOR:
            return "PASS_FALLBACK_CONSERVATIVE",detail
        if a<FAIL_CEILING and b<FAIL_CEILING:
            return "FAIL_MC",detail
        return "UNKNOWN_BORDERLINE",detail
    except Exception as e:
        return "UNKNOWN_RETRY",type(e).__name__+":"+str(e)[:180]

def counts(results):
    out={}
    for v in results.values():
        st=v.get("status");out[st]=out.get(st,0)+1
    return dict(sorted(out.items()))

def main():
    src=load(IN)
    if src.get("schema")!="XRAY_MARKET_CANDIDATES_V4":
        raise RuntimeError("MARKET_CANDIDATES_V4_REQUIRED")
    asof=src.get("asof_et")
    candidates=src.get("candidates") or {}
    if not asof:raise RuntimeError("ASOF_MISSING")

    state=load(OUT)
    if state.get("schema")!="XRAY_DUAL_MC_V1" or state.get("asof_et")!=asof:
        state={"schema":"XRAY_DUAL_MC_V1","build":BUILD,"task_id":TASK_ID,
               "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
               "asof_et":asof,"results":{},"status":"MC_PARTIAL"}

    results=state.setdefault("results",{})
    new=[s for s in sorted(candidates) if s not in results][:MAX_NEW]
    retry=[s for s,v in sorted(results.items())
           if s in candidates and v.get("status")=="UNKNOWN_RETRY"
           and int(v.get("attempts",0))<MAX_ATTEMPTS][:10]
    work=[];seen=set()
    for s in retry+new:
        if s not in seen:seen.add(s);work.append(s)

    for sym in work:
        st,info=classify(sym)
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if st=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            st="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={"status":st,"info":info,"attempts":attempts,
                      "updated_at_utc":datetime.now(timezone.utc).isoformat()}
        time.sleep(random.uniform(0.08,0.18))

    pending_new=sum(1 for s in candidates if s not in results)
    pending_retry=sum(1 for s,v in results.items()
                      if s in candidates and v.get("status")=="UNKNOWN_RETRY"
                      and int(v.get("attempts",0))<MAX_ATTEMPTS)
    state["build"]=BUILD
    state["candidate_count_seen"]=len(candidates)
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["pending_new"]=pending_new
    state["pending_retry"]=pending_retry
    state["counts"]=counts(results)
    state["status"]="MC_COMPLETE" if pending_new==0 and pending_retry==0 else "MC_PARTIAL"
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    state["state_hash"]=hashlib.sha256(
        json.dumps(state,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    atomic(OUT,state)
    print(json.dumps({"status":state["status"],"candidates":len(candidates),
                      "processed_new":len(new),"processed_retry":len(retry),
                      "pending_new":pending_new,"pending_retry":pending_retry,
                      "counts":state["counts"]},sort_keys=True))

if __name__=="__main__":
    main()
