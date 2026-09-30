#!/usr/bin/env python3
"""XRAY official SEC conservative market-cap stage V2.
Input: PRICE/DV20/HISTORY candidates.
Official facts: SEC companyfacts, no paid key.
Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
IN=ROOT/"market_candidates.json"
OUT=ROOT/"sec_mc_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.2"
UA="NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar"
MAX_NEW=int(os.getenv("XRAY_SEC_MC_BATCH","35"))
MAX_ATTEMPTS=int(os.getenv("XRAY_SEC_MC_MAX_ATTEMPTS","3"))
PASS_FLOOR=2_100_000_000
FAIL_CEILING=2_000_000_000
MAX_FACT_AGE_DAYS=130
ALLOWED_FORMS={"10-K","10-Q","10-K/A","10-Q/A"}

def get_json(url,timeout=35,retries=3):
    last=None
    for k in range(retries):
        try:
            req=urllib.request.Request(url,headers={
                "User-Agent":UA,
                "Accept":"application/json",
                "Accept-Encoding":"identity",
            })
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e
            time.sleep(0.8*(k+1)+random.uniform(0.1,0.4))
    raise last

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except Exception:
        return None

def load(path):
    if path.exists():
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:pass
    return {}

def atomic(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def input_hash(candidates,asof):
    rows=[asof]+[f"{s}|{(v or {}).get('cik')}|{(v or {}).get('price')}" for s,v in sorted(candidates.items())]
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def latest_shares(facts,asof):
    concept=(((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding"))
    if not concept:
        return None,"SHARES_CONCEPT_MISSING"
    vals=((concept.get("units") or {}).get("shares") or [])
    eligible=[]
    for x in vals:
        end=str(x.get("end") or "")
        filed=str(x.get("filed") or "")
        form=str(x.get("form") or "")
        val=finite(x.get("val"))
        if val is None or not end or not filed:
            continue
        if end>asof or filed>asof:
            continue
        if form not in ALLOWED_FORMS:
            continue
        try:
            age=(date.fromisoformat(asof)-date.fromisoformat(end)).days
        except Exception:
            continue
        if age<0 or age>MAX_FACT_AGE_DAYS:
            continue
        eligible.append((filed,end,val,form,age,x.get("accn")))
    if not eligible:
        return None,"NO_FRESH_US_10K10Q_SHARES_FACT"
    eligible.sort(key=lambda z:(z[0],z[1]))
    filed,end,val,form,age,accn=eligible[-1]
    return {
        "shares":val,"end":end,"filed":filed,"form":form,
        "age_days":age,"accn":accn
    },None

def classify_symbol(sym,info,asof):
    if bool((info or {}).get("multi_ticker_cik")):
        return "UNKNOWN_STATIC","MULTI_TICKER_CIK"
    px=finite((info or {}).get("price"))
    cik=(info or {}).get("cik")
    if px is None:
        return "UNKNOWN_STATIC","PRICE_MISSING"
    try:cik=int(cik)
    except Exception:return "UNKNOWN_STATIC","CIK_MISSING"
    try:
        facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        sh,err=latest_shares(facts,asof)
        if err:
            return "UNKNOWN_STATIC",err
        mc=px*sh["shares"]
        rec={
            "price":px,"cik":cik,"shares":sh["shares"],"shares_end":sh["end"],
            "filed":sh["filed"],"form":sh["form"],"shares_age_days":sh["age_days"],
            "accn":sh["accn"],"market_cap_est":mc,
            "method":"ASOF_CLOSE_X_FRESH_SEC_ENTITY_SHARES",
        }
        if mc>=PASS_FLOOR:
            return "PASS_SEC_CONSERVATIVE",rec
        if mc<FAIL_CEILING:
            return "FAIL_MC",rec
        return "UNKNOWN_STATIC",{"reason":"MC_BORDERLINE_2_0_TO_2_1B","detail":rec}
    except Exception as e:
        return "UNKNOWN_RETRY",f"{type(e).__name__}:{str(e)[:160]}"

def counts(results):
    out={}
    for v in results.values():
        st=v.get("status")
        out[st]=out.get(st,0)+1
    return out

def main():
    src=load(IN)
    if src.get("schema")!="XRAY_MARKET_CANDIDATES_V2":
        raise RuntimeError("MARKET_CANDIDATES_V2_REQUIRED")
    asof=src.get("asof_et")
    candidates=src.get("candidates") or {}
    if not asof:
        raise RuntimeError("ASOF_MISSING")

    state=load(OUT)
    # Keep existing same-ASOF results even as new candidates are appended.
    if state.get("schema")!="XRAY_SEC_MC_V2" or state.get("asof_et")!=asof:
        state={
            "schema":"XRAY_SEC_MC_V2","build":BUILD,"task_id":TASK_ID,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "asof_et":asof,"results":{},"status":"MC_PARTIAL"
        }

    results=state.setdefault("results",{})
    new=[s for s in sorted(candidates) if s not in results][:MAX_NEW]
    retry=[
        s for s,v in sorted(results.items())
        if v.get("status")=="UNKNOWN_RETRY"
        and int(v.get("attempts",0))<MAX_ATTEMPTS
        and s in candidates
    ][:10]
    work=[]
    seen=set()
    for s in retry+new:
        if s not in seen:
            seen.add(s);work.append(s)

    for sym in work:
        st,info=classify_symbol(sym,candidates[sym],asof)
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if st=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            st="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={
            "status":st,"info":info,"attempts":attempts,
            "updated_at_utc":datetime.now(timezone.utc).isoformat()
        }
        time.sleep(0.13)

    state["build"]=BUILD
    state["candidate_count_seen"]=len(candidates)
    state["input_hash"]=input_hash(candidates,asof)
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["counts"]=counts(results)
    pending_new=sum(1 for s in candidates if s not in results)
    pending_retry=sum(
        1 for s,v in results.items()
        if s in candidates and v.get("status")=="UNKNOWN_RETRY"
        and int(v.get("attempts",0))<MAX_ATTEMPTS
    )
    state["pending_new"]=pending_new
    state["pending_retry"]=pending_retry
    state["status"]="MC_COMPLETE" if pending_new==0 and pending_retry==0 else "MC_PARTIAL"
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    state["state_hash"]=hashlib.sha256(
        json.dumps(state,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    atomic(OUT,state)
    print(json.dumps({
        "status":state["status"],"candidates":len(candidates),
        "processed_new":len(new),"processed_retry":len(retry),
        "pending_new":pending_new,"pending_retry":pending_retry,
        "counts":state["counts"]
    },sort_keys=True))

if __name__=="__main__":
    main()
