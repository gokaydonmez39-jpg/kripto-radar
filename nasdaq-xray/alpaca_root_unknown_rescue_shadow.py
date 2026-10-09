#!/usr/bin/env python3
"""Zero-cost, source-specific HISTORY rescue measurement for the root UNKNOWN set.

Consumes a frozen root Sina result partition and a same-ASOF canonical
30-session calendar, with Alpaca historical SIP input via private Actions
credentials. Produces aggregates only. NEVER writes prices or modifies root,
MC, alpha thresholds, canonical sources, candidates, or notification gates.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

import alpaca_free_sip_shadow_guard as sip

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_ROOT_UNKNOWN_SIP_RESCUE_SHADOW_V1"
PRIORITY={
  "UNKNOWN_RETRY_EXHAUSTED":0,
  "UNKNOWN_RETRY":1,
  "UNKNOWN_STATIC":2,
}

def pick_unknown(state,offset=0,limit=12):
    if not (type(offset) is int and type(limit) is int
            and offset>=0 and 1<=limit<=32):
        raise ValueError("INVALID_BOUNDED_RESCUE_SLICE")
    queue=state.get("queue") or []
    rows=state.get("results") or {}
    if (not isinstance(queue,list) or not isinstance(rows,dict)
            or len(queue)!=len(set(queue))
            or len(queue)!=state.get("queue_total")
            or not set(rows).issubset(set(queue))):
        raise ValueError("ROOT_QUEUE_PARTITION_INVALID")
    unknown={sym:row for sym,row in rows.items()
             if str(row.get("status") or "").startswith("UNKNOWN")}
    if len(unknown)!=state.get("unknown_count"):
        raise ValueError("ROOT_UNKNOWN_COUNT_INVALID")
    for sym in unknown:
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,12}",sym):
            raise ValueError("SYMBOL_FORMAT_UNTRUSTED")
    ordered=sorted(unknown,key=lambda sym:(
        PRIORITY.get(unknown[sym].get("status"),9),sym))
    if offset>=len(ordered):
        raise ValueError("OFFSET_OUTSIDE_UNRESOLVED_SCOPE")
    return ordered[offset:offset+limit],len(ordered)

def study(symbols,asof,expected30,bar_map,now):
    counts=Counter()
    for sym in symbols:
        rows=bar_map.get(sym) or []
        state,why,n=sip.evaluate_daily(rows,expected30,asof,now)
        if state!="SHADOW_30_BARS_OBSERVED":
            counts["UNKNOWN_"+why]+=1
            continue
        # 260 distinct traded days and 52 ISO weeks are *diagnostics*,
        # not evidence of Nasdaq calendar exactness or split neutrality.
        try:
            obs=[sip.timestamp_date(row["t"]) for row in rows]
            uniq=set(obs)
            positive={sip.timestamp_date(row["t"]) for row in rows if row["v"]>0}
            weeks={(d.isocalendar().year,d.isocalendar().week) for d in positive}
        except (KeyError,TypeError,ValueError):
            counts["UNKNOWN_BAD_HISTORY_SCHEMA"]+=1
            continue
        if len(uniq)!=len(obs):
            counts["UNKNOWN_DUPLICATE_HISTORY_SESSION"]+=1
        elif len(positive)>=260 and len(weeks)>=52:
            counts["SHADOW_260_BARS_52_WEEKS_OBSERVED_NOT_PRIMARY"]+=1
        else:
            counts["UNKNOWN_LT260_OR_52_WEEKS"]+=1
    return dict(sorted(counts.items()))

def selftest():
    s={"queue":["A","B","C","D"],"queue_total":4,"unknown_count":3,
       "results":{
         "A":{"status":"PASS"},
         "B":{"status":"UNKNOWN_STATIC","info":{"reason":"EXACT30_INCOMPLETE_NEVER_PASS"}},
         "C":{"status":"UNKNOWN_RETRY_EXHAUSTED"},
         "D":{"status":"UNKNOWN_RETRY_EXHAUSTED"},
       }}
    assert pick_unknown(s,0,3)==(["C","D","B"],3)
    assert pick_unknown(s,1,2)==(["D","B"],3)
    for off,lim in ((-1,1),(0,0),(0,33),(10,2)):
        try:pick_unknown(s,off,lim)
        except ValueError:pass
        else:raise AssertionError("BAD_SCOPE_ACCEPTED")
    from copy import deepcopy
    bad=deepcopy(s);bad["unknown_count"]=2
    try:pick_unknown(bad)
    except ValueError:pass
    else:raise AssertionError("INVALID_UNKNOWN_COUNT_ACCEPTED")
    assert study(["C"],"2026-10-08",[],{},dt.datetime(2026,10,9,14,tzinfo=sip.UTC))=={
        "UNKNOWN_OFFICIAL_30_SESSION_LIST_UNVERIFIED":1}
    print("XRAY_ROOT_UNKNOWN_SIP_RESCUE_SELFTEST=PASS_RANKED_SCOPE_5_NEGATIVE_NO_AUTHORITY")

def run(offset=0,limit=12,now=None):
    if now is None:now=dt.datetime.now(sip.UTC)
    rootp=ROOT/"sina_state.json"
    pp=ROOT/"canonical_current_price_dv30.json"
    state=json.loads(rootp.read_text(encoding="utf-8"))
    price=json.loads(pp.read_text(encoding="utf-8"))
    syms,total=pick_unknown(state,offset,limit)
    asof=state.get("asof_et")
    if (asof!=price.get("asof_et")
            or price.get("unknown_never_pass") is not True
            or state.get("execution")!="NONE" or state.get("real_money")!="NO-GO"):
        raise ValueError("ASOF_OR_SAFETY_MISMATCH")
    dates=price.get("expected30") or []
    if len(dates)!=30 or dates[-1]!=asof or len(set(dates))!=30:
        raise ValueError("CANONICAL_CALENDAR_30_INVALID")
    output={
      "schema":SCHEMA,"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
      "mode":"RESEARCH_ONLY_MANUAL_DECISION","unknown_never_pass":True,
      "root_git_blob_sha":sip.blob_sha(rootp),"price_git_blob_sha":sip.blob_sha(pp),
      "total_root_unknown":total,"sample_offset":offset,"sample_count":len(syms),
      "sample_ticker_hash_sha256":hashlib.sha256("\n".join(syms).encode()).hexdigest(),
      "status":"BLOCKED","reason_counts":{},
      "primary_mc_authority":False,"canonical_history_modified":False,
      "candidate_created":False,"vendor_raw_bars_persisted":False}
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","")
    if not key or not secret:
        output["reason_counts"]={"PRIVATE_ALPACA_CREDENTIALS_REQUIRED":len(syms)}
        return output
    if not sip.sufficient_delay(asof,now):
        output["reason_counts"]={"HISTORICAL_DELAY_WINDOW_NOT_EXPIRED":len(syms)}
        return output
    start=dt.datetime.combine(sip.parse_date(asof)-dt.timedelta(days=440),
                              dt.time(0,0),sip.EST).astimezone(sip.UTC).isoformat()
    end=dt.datetime.combine(sip.parse_date(asof)+dt.timedelta(days=1),
                            dt.time(0,0),sip.EST).astimezone(sip.UTC).isoformat()
    try:rows=sip.request_batch(syms,start,end,key,secret)
    except (RuntimeError,ValueError) as exc:
        code=str(exc)
        if not code.startswith("ALPACA_"):code="ALPACA_UNVERIFIED_ERROR"
        output["reason_counts"]={code:len(syms)}
        return output
    output["reason_counts"]=study(syms,asof,dates,rows,now)
    output["status"]="SHADOW_HISTORICAL_SOURCE_DIAGNOSTIC_COMPLETE"
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=12)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    out=run(args.offset,args.limit)
    if args.output:args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_ALPACA_ROOT_RESCUE="+out["status"])
    print("XRAY_ALPACA_ROOT_RESCUE_COUNTS="+json.dumps(out["reason_counts"],sort_keys=True))
    print("XRAY_ALPACA_ROOT_RESCUE_PRIMARY=NEVER_WITHOUT_NEW_POLICY")
if __name__=="__main__":
    main()
