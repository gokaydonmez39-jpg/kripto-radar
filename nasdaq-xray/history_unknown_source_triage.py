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
# Additive diagnostics retain V1 schema for legacy consumers.
PARSER_EXCEPTION_CODES=frozenset({
    "SyntaxError", "IndexError", "KeyError", "ValueError",
    "JSONDecodeError", "UnicodeDecodeError", "TypeError",
})
NETWORK_EXCEPTION_CODES=frozenset({
    "HTTPError", "TimeoutError", "ConnectionError", "ReadTimeout", "SSLError",
    "RemoteDisconnected", "ConnectionReset",
})
ALLOWED_REASON_CODES={
    "SINA_HISTORY_EMPTY","SINA_HISTORY_TOO_SHORT","SINA_HISTORY_INSUFFICIENT",
    "SINA_NO_ASOF_BAR","SINA_MISSING_SESSIONS","INCOMPLETE_RTH_SESSIONS",
    "SINA_HISTORY_INVALID","SINA_UNVERIFIED_SPLIT","SINA_LOW_QUALITY",
    "RESOLUTION_OVERLAY_INVALID","RESOLUTION_DECISION_UNKNOWN",
    "ASOF_MISSING_REQUIRES_RESOLUTION",
    "SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION",
    "EXACT30_INCOMPLETE_NEVER_PASS",
}
def reason_code(info):
    if isinstance(info,dict):
        raw=str(info.get("reason") or info.get("code") or "")
    elif isinstance(info,str):
        raw=info
    else:raw=""
    if raw in ALLOWED_REASON_CODES:return raw
    if isinstance(info,str) and ":" in raw:
        error_type=raw.split(":",1)[0]
        if error_type in PARSER_EXCEPTION_CODES | NETWORK_EXCEPTION_CODES:
            return "PROVIDER_EXCEPTION_"+error_type
    if isinstance(info,str) and ":" in raw:
        error_type=raw.split(":",1)[0]
        if (re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,55}",error_type)
                and (error_type.endswith(("Error","Exception","Timeout"))
                     or error_type in {"RemoteDisconnected","ConnectionReset"})):
            return "PROVIDER_EXCEPTION_"+error_type
    if not raw:
        return "NO_REASON_GIVEN"
    return "UNCLASSIFIED_PROVIDER_DIAGNOSTIC"

def recovery_class(code):
    """Stable incident grouping; advisory ONLY, never source recovery PASS."""
    if code.startswith("PROVIDER_EXCEPTION_"):
        subtype=code.removeprefix("PROVIDER_EXCEPTION_")
        if subtype in PARSER_EXCEPTION_CODES:
            return "PROVIDER_PARSER_OR_SCHEMA_ERROR"
        if subtype in NETWORK_EXCEPTION_CODES:
            return "PROVIDER_TRANSPORT_OR_QUOTA_UNVERIFIED"
        return "PROVIDER_OTHER_EXCEPTION_NEEDS_INSPECTION"
    if code.startswith("NETWORK_OR_PROVIDER_EXCEPTION"):
        return "PROVIDER_TRANSPORT_OR_QUOTA_UNVERIFIED"
    if code=="EXACT30_INCOMPLETE_NEVER_PASS":
        return "LATEST_30_COMPLETED_SESSIONS_MISSING"
    if code in {"ASOF_MISSING_REQUIRES_RESOLUTION","SINA_NO_ASOF_BAR"}:
        return "SAME_ASOF_SESSION_MISSING"
    if code in {"SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION",
                "SINA_HISTORY_TOO_SHORT","SINA_HISTORY_INSUFFICIENT",
                "SINA_MISSING_SESSIONS","INCOMPLETE_RTH_SESSIONS"}:
        return "HISTORICAL_260_OR_52W_COVERAGE_MISSING"
    if code=="SINA_HISTORY_EMPTY":
        return "SOURCE_NO_HISTORY_RETURNED"
    return "SOURCE_UNVERIFIED_NEEDS_INDEPENDENT_MEASUREMENT"


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
    recovery=Counter(recovery_class(reason_code(row.get("info"))) for row in unknown.values())
    if sum(recovery.values())!=len(unknown):
        raise ValueError("RECOVERY_CLASS_PARTITION_INCOMPLETE")
    # Public ticker IDs and diagnostic categories only; no prices, volume,
    # bar sequences, credentials, provider error bodies, or raw metadata.
    # Source-local incidents must NOT be promoted to verified IPO/52W causes.
    per_symbol={}
    for symbol,row in sorted(unknown.items()):
        rc=reason_code(row.get("info"))
        per_symbol[symbol]={
            "status":str(row.get("status")),
            "provider_reason_code":rc,
            "operational_class":recovery_class(rc),
            "confirmed_ipo":None,
            "daily_260_official_sessions_verified":None,
            "weekly_52_completed_weeks_verified":None,
            "independent_authorized_history_check_required":True,
        }
    if len(per_symbol)!=len(unknown) or set(per_symbol)!=set(unknown):
        raise ValueError("PER_SYMBOL_PARTITION_MISMATCH")
    # Retain the legacy three-per-reason ticker samples.
    samples={}
    for symbol,row in sorted(unknown.items()):
        code=str(row.get("status"))+" | "+reason_code(row.get("info"))
        if len(samples.setdefault(code,[]))<3:
            samples[code].append(symbol)
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
        "advisory_recovery_class_counts":dict(sorted(recovery.items())),
        "public_per_symbol_source_diagnostics":per_symbol,
        "per_symbol_diagnostics_count":len(per_symbol),
        "per_symbol_causes_are_independently_verified":False,
        "recovery_execution_authorized":False,
        "public_sample_tickers_by_reason":dict(sorted(samples.items())),
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
    assert ok["public_sample_tickers_by_reason"]["UNKNOWN_STATIC | SINA_HISTORY_EMPTY"]==["B"]
    assert ok["unknown_reason_counts"]["UNKNOWN_RETRY_EXHAUSTED | NETWORK_OR_PROVIDER_EXCEPTION"]==1
    assert sum(ok["advisory_recovery_class_counts"].values())==2
    assert ok["advisory_recovery_class_counts"]=={
        "PROVIDER_TRANSPORT_OR_QUOTA_UNVERIFIED":1,
        "SOURCE_NO_HISTORY_RETURNED":1}
    assert ok["recovery_execution_authorized"] is False
    assert ok["per_symbol_diagnostics_count"]==2
    assert set(ok["public_per_symbol_source_diagnostics"])=={"B","C"}
    assert all(x["confirmed_ipo"] is None and x["daily_260_official_sessions_verified"] is None
               and x["weekly_52_completed_weeks_verified"] is None and
               x["independent_authorized_history_check_required"] is True
               for x in ok["public_per_symbol_source_diagnostics"].values())
    assert ok["per_symbol_causes_are_independently_verified"] is False
    for reason,expected in [
        ("EXACT30_INCOMPLETE_NEVER_PASS","LATEST_30_COMPLETED_SESSIONS_MISSING"),
        ("ASOF_MISSING_REQUIRES_RESOLUTION","SAME_ASOF_SESSION_MISSING"),
        ("SINA_HISTORY_TOO_SHORT","HISTORICAL_260_OR_52W_COVERAGE_MISSING"),
        ("SINA_HISTORY_EMPTY","SOURCE_NO_HISTORY_RETURNED"),
        ("UNCLASSIFIED_PROVIDER_DIAGNOSTIC","SOURCE_UNVERIFIED_NEEDS_INDEPENDENT_MEASUREMENT")]:
        assert recovery_class(reason)==expected
    assert reason_code({"reason":"ASOF_MISSING_REQUIRES_RESOLUTION"})=="ASOF_MISSING_REQUIRES_RESOLUTION"
    assert reason_code({"reason":"EXACT30_INCOMPLETE_NEVER_PASS"})=="EXACT30_INCOMPLETE_NEVER_PASS"
    assert reason_code("RuntimeError:provider unavailable")=="PROVIDER_EXCEPTION_RuntimeError"
    assert reason_code("SyntaxError:bad json")=="PROVIDER_EXCEPTION_SyntaxError"
    assert reason_code("IndexError:list index out of range")=="PROVIDER_EXCEPTION_IndexError"
    assert reason_code("KeyError:field")=="PROVIDER_EXCEPTION_KeyError"
    assert reason_code("TimeoutError:request")=="PROVIDER_EXCEPTION_TimeoutError"
    assert reason_code("JSONDecodeError:invalid")=="PROVIDER_EXCEPTION_JSONDecodeError"
    assert recovery_class(reason_code("SyntaxError:bad json"))=="PROVIDER_PARSER_OR_SCHEMA_ERROR"
    assert recovery_class(reason_code("IndexError:out of range"))=="PROVIDER_PARSER_OR_SCHEMA_ERROR"
    assert recovery_class(reason_code("TimeoutError:request"))=="PROVIDER_TRANSPORT_OR_QUOTA_UNVERIFIED"
    assert recovery_class(reason_code("RuntimeError:provider"))=="PROVIDER_OTHER_EXCEPTION_NEEDS_INSPECTION"
    assert reason_code("https://private-provider/data?api_key=secret")=="UNCLASSIFIED_PROVIDER_DIAGNOSTIC"
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
    print("XRAY_HISTORY_UNKNOWN_TRIAGE_TICKER_SAMPLES="+json.dumps(data["public_sample_tickers_by_reason"],sort_keys=True))
if __name__=="__main__":
    main()
