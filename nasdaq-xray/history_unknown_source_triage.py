#!/usr/bin/env python3
"""Read-only root HISTORY unknown classification. No market data emitted.

A complete cursor does not imply complete 260-session coverage. Results are
reported as operational counts only; raw provider bars stay out of GitHub.
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_HISTORY_UNKNOWN_SOURCE_TRIAGE_V1"
ALLOWED_REASON_CODES={
    "SINA_HISTORY_EMPTY","SINA_HISTORY_TOO_SHORT","SINA_HISTORY_INSUFFICIENT",
    "SINA_NO_ASOF_BAR","SINA_MISSING_SESSIONS","INCOMPLETE_RTH_SESSIONS",
    "SINA_HISTORY_INVALID","SINA_UNVERIFIED_SPLIT","SINA_LOW_QUALITY",
    "RESOLUTION_OVERLAY_INVALID","RESOLUTION_DECISION_UNKNOWN",
}
def reason_code(info):
    if isinstance(info,dict):
        raw=str(info.get("reason") or info.get("code") or "")
    elif isinstance(info,str):
        raw=info
    else:raw=""
    if raw in ALLOWED_REASON_CODES:return raw
    if re.match(r"^(?:HTTPError|TimeoutError|ConnectionError|ReadTimeout|JSONDecodeError|ValueError|KeyError|SSLError):",raw):
        return "NETWORK_OR_PROVIDER_EXCEPTION"
    if not raw:
        return "NO_REASON_GIVEN"
    return "UNCLASSIFIED_PROVIDER_DIAGNOSTIC"

def audit(state):
    if not isinstance(state,dict):
        raise ValueError("STATE_MUST_BE_OBJECT")
    if state.get("execution")!="NONE" or state.get("real_money")!="NO-GO":
        raise ValueError("STATE_SAFETY_INVALID")
    queue=state.get("queue") or []
    results=state.get("results") or {}
    if not isinstance(results,dict) or not isinstance(queue,list):
        raise ValueError("HISTORY_QUEUE_RESULTS_INVALID")
    if len(queue)!=len(set(queue)) or len(queue)!=int(state.get("queue_total",-1)):
        raise ValueError("QUEUE_PARTITION_INTEGRITY_FAIL")
    cursor=int(state.get("cursor",-1))
    if cursor<0 or cursor>len(queue):
        raise ValueError("INVALID_HISTORY_CURSOR")
    if not set(results).issubset(set(queue)):
        raise ValueError("RESULT_OUTSIDE_AUTHORIZED_QUEUE")
    counts=Counter((r.get("status") or "UNKNOWN_NO_STATUS") for r in results.values())
    official=state.get("counts") or {}
    for st,n in counts.items():
        if int(official.get(st,-1))!=n:
            raise ValueError("STATUS_COUNTS_DO_NOT_MATCH_RESULTS")
    if sum(int(v) for v in official.values())!=len(results):
        raise ValueError("STATE_COUNT_SUM_MISMATCH")
    unknown={sym:row for sym,row in results.items() if str(row.get("status") or "").startswith("UNKNOWN")}
    if len(unknown)!=int(state.get("unknown_count",-1)):
        raise ValueError("UNKNOWN_COUNT_MISMATCH")
    reasons=Counter((str(row.get("status"))+" | "+reason_code(row.get("info"))) for row in unknown.values())
    retry_count=int(state.get("pending_retry",0) or 0)
    if retry_count<0:
        raise ValueError("NEGATIVE_RETRY_COUNT")
    # The record status is historical only. Neither 497 other price-pass
    # symbols nor 514 canonical price-pass symbols are validated here.
    return {
        "schema":SCHEMA,"asof_et":state.get("asof_et"),
        "status":"FAIL_CLOSED_SOURCE_UNKNOWN",
        "execution":"NONE","real_money":"NO-GO",
        "authority":"ROOT_HISTORY_DIAGNOSTIC_ONLY",
        "alpha_authority":False,"candidate_created":False,
        "total_scope":len(queue),"cursor":cursor,"classifications":len(results),
        "unknown_count":len(unknown),"pending_retry":retry_count,
        "status_counts":dict(sorted(counts.items())),
        "unknown_reason_counts":dict(sorted(reasons.items())),
        "public_market_bars_persisted":False,
        "fully_verified_260_session_candidate_count":None,
    }

def selftest():
    base={
       "execution":"NONE","real_money":"NO-GO","asof_et":"2026-10-08",
       "queue":["A","B","C"],"queue_total":3,"cursor":3,
       "results":{"A":{"status":"PASS"},"B":{"status":"UNKNOWN_STATIC",
                  "info":{"reason":"SINA_HISTORY_EMPTY"}},
                  "C":{"status":"UNKNOWN_RETRY_EXHAUSTED",
                  "info":"TimeoutError:request"}},
       "counts":{"PASS":1,"UNKNOWN_STATIC":1,"UNKNOWN_RETRY_EXHAUSTED":1},
       "unknown_count":2,"pending_retry":0}
    ok=audit(base)
    assert ok["unknown_count"]==2
    assert ok["unknown_reason_counts"]["UNKNOWN_STATIC | SINA_HISTORY_EMPTY"]==1
    assert ok["unknown_reason_counts"]["UNKNOWN_RETRY_EXHAUSTED | NETWORK_OR_PROVIDER_EXCEPTION"]==1
    from copy import deepcopy
    for outer,key,val in (
        ("top","queue_total",2),("top","cursor",4),
        ("top","unknown_count",1),("top","execution","ORDER"),
        ("top","real_money","GO"),("top","queue",["A","A","C"]),
        ("top","pending_retry",-1)):
        test=deepcopy(base);test[key]=val
        try:audit(test)
        except ValueError:pass
        else:raise AssertionError("TRIAGE_INVALID_STATE_ACCEPTED_"+key)
    bad=deepcopy(base);bad["counts"]["PASS"]=9
    try:audit(bad)
    except ValueError:pass
    else:raise AssertionError("TRIAGE_BAD_COUNT_ACCEPTED")
    print("XRAY_HISTORY_UNKNOWN_TRIAGE_SELFTEST=PASS_COUNTS_PARTITIONS_REASON_CLASSES_8_NEGATIVE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    state=json.loads((ROOT/"sina_state.json").read_text(encoding="utf-8"))
    data=audit(state)
    if args.output: args.output.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("XRAY_HISTORY_UNKNOWN_TRIAGE_STATUS="+data["status"])
    print("XRAY_HISTORY_UNKNOWN_TRIAGE_COUNTS="+json.dumps(data["status_counts"],sort_keys=True))
    print("XRAY_HISTORY_UNKNOWN_TRIAGE_REASONS="+json.dumps(data["unknown_reason_counts"],sort_keys=True))
if __name__=="__main__":
    main()
