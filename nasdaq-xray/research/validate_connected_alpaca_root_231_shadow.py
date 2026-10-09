#!/usr/bin/env python3
"""Validate counts-only interactive Alpaca research against immutable root scope.

Does NOT repeat proprietary API calls; attests scope/partition/accounting only.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"research/alpaca_connected_root_231_operational_shadow_20261009_v1.json"
STATE=ROOT/"sina_state.json"
EXPECTED={"measured_symbols":231,"at_least_260_daily_rows_and_asof":90,
          "under_260_with_asof":136,"no_asof":5,"api_error_symbols":0}
CLASSES={"PROVIDER_PARSER_OR_SCHEMA_ERROR":28,
         "SAME_ASOF_SESSION_MISSING":53,
         "HISTORY_COVERAGE_AND_EXACT30_PARTITION":150}
FORBIDDEN={"o","h","l","c","v","price","close","open","high","low",
           "volume","vwap","ohlcv","market_cap_usd","market_cap",
           "shares_outstanding","bid","ask"}

def check(report,state):
    if not isinstance(report,dict) or not isinstance(state,dict):
        raise ValueError("INVALID_OBJECT")
    if report.get("schema")!="XRAY_ALPACA_CONNECTED_ROOT_231_OPERATIONAL_SHADOW_V1":
        raise ValueError("INVALID_SCHEMA")
    if report.get("authority")!="CONNECTED_INTERACTIVE_SHADOW_NOT_GITHUB_RUNNER_OR_C417_PRIMARY":
        raise ValueError("ALPHA_AUTHORITY_INVALID")
    if state.get("asof_et")!=report.get("asof_et") or state.get("asof_et")!="2026-10-08":
        raise ValueError("ROOT_ASOF_MISMATCH")
    if state.get("execution")!="NONE" or state.get("real_money")!="NO-GO":
        raise ValueError("ROOT_SAFETY_INVALID")
    results=state.get("results")
    if not isinstance(results,dict):
        raise ValueError("ROOT_RESULTS_MISSING")
    unknown=sorted(s for s,row in results.items()
                   if isinstance(row,dict) and str(row.get("status") or "").startswith("UNKNOWN"))
    if len(unknown)!=231 or state.get("unknown_count")!=231:
        raise ValueError("ROOT_UNKNOWN_SCOPE_DRIFT")
    digest=hashlib.sha256("\n".join(unknown).encode()).hexdigest()
    if digest!=report.get("history_unknown_symbols_sha256"):
        raise ValueError("EXACT_ROOT_UNKNOWN_SYMBOL_SET_MISMATCH")
    slices=report.get("aggregation_slices")
    if not isinstance(slices,list) or len(slices)!=8:
        raise ValueError("SLICE_PARTITION_INVALID")
    categories={}
    total={k:0 for k in EXPECTED}
    valid_offsets=[]
    for row in slices:
        if not isinstance(row,dict):
            raise ValueError("SLICE_SCHEMA_INVALID")
        reason=row.get("original_reason")
        n=row.get("sample_count")
        if reason not in CLASSES or type(n) is not int or n<=0:
            raise ValueError("SOURCE_CLASS_INVALID")
        categories[reason]=categories.get(reason,0)+n
        total["measured_symbols"]+=n
        for k in ("at_least_260_daily_rows_and_asof","under_260_with_asof","no_asof"):
            v=row.get(k)
            if type(v) is not int or v<0:
                raise ValueError("OBSERVATION_COUNTS_INVALID")
            total[k]+=v
        if sum(row.get(k) for k in ("at_least_260_daily_rows_and_asof","under_260_with_asof","no_asof"))!=n:
            raise ValueError("ROW_PARTITION_SUM_INVALID")
        if reason=="HISTORY_COVERAGE_AND_EXACT30_PARTITION":
            valid_offsets.append(row.get("offset"))
            if n!=25:
                raise ValueError("HISTORY_SLICE_SIZE_INVALID")
    if categories!=CLASSES or sorted(valid_offsets)!=[0,25,50,75,100,125]:
        raise ValueError("ROOT_CLASS_SCOPE_INVALID")
    if total!=EXPECTED or report.get("totals")!=EXPECTED:
        raise ValueError("AGGREGATE_RECONCILIATION_INVALID")
    flags=("completed_calendar_260_proven","weekly_52_completed_proven",
           "corporate_actions_and_split_basis_proven","ticker_lineage_PIT_proven",
           "provider_runner_non_display_rights_proven",
           "source_exact_market_data_accession_persisted",
           "market_data_in_public_artifact","price_volume_ohlcv_in_public_artifact",
           "symbol_level_vendor_derived_rows_in_public_artifact",
           "live_root_history_changed")
    if any(report.get(name) is not False for name in flags):
        raise ValueError("PRODUCTION_EVIDENCE_FABRICATED")
    if report.get("canonical_history_pass_created")!=0 or report.get("c417_primary_pass_created")!=0 or report.get("r92_created")!=0:
        raise ValueError("FALSE_ALPHA_PROMOTION")
    if report.get("execution")!="NONE" or report.get("real_money")!="NO-GO" or report.get("unknown_never_pass") is not True:
        raise ValueError("REPORT_EXECUTION_INVALID")
    def check_keys(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k.lower() in FORBIDDEN:
                    raise ValueError("MARKET_DATA_FIELD_IN_PUBLIC_AGGREGATE")
                check_keys(v)
        elif isinstance(x,list):
            for y in x: check_keys(y)
    check_keys(report)
    return {"status":"INTEGRITY_SCOPE_AND_AGGREGATE_PASS_SHADOW_ONLY",
            "symbols":len(unknown),"at_least_260_bar_observed":90,
            "canonical_history_pass_created":False,
            "production_mc_pass_created":False,"phone_receipt":False}

def test(report,state):
    good=check(report,state)
    assert good["symbols"]==231
    bad=[]
    for k,v in (("canonical_history_pass_created",1),
                ("completed_calendar_260_proven",True),
                ("provider_runner_non_display_rights_proven",True),
                ("unknown_never_pass",False)):
        x=copy.deepcopy(report);x[k]=v;bad.append(x)
    x=copy.deepcopy(report);x["totals"]["measured_symbols"]=230;bad.append(x)
    x=copy.deepcopy(report);x["aggregation_slices"][0]["no_asof"]+=1;bad.append(x)
    x=copy.deepcopy(report);x["aggregation_slices"][0]["close"]=50.0;bad.append(x)
    x=copy.deepcopy(report);x["history_unknown_symbols_sha256"]="0"*64;bad.append(x)
    x=copy.deepcopy(report);x["aggregation_slices"][2]["offset"]=25;bad.append(x)
    for n,x in enumerate(bad):
        try:check(x,state)
        except ValueError:pass
        else:raise AssertionError("INVALID_RESEARCH_ARTIFACT_ACCEPTED:"+str(n))
    print("XRAY_CONNECTED_ALPACA_231_INTEGRITY_SELFTEST=PASS_REAL_ROOT_9_NEGATIVES_NO_ALPHA")

if __name__=="__main__":
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    state=json.loads(STATE.read_text(encoding="utf-8"))
    test(report,state)
    print("XRAY_ROOT_231_RESEARCH_SCOPE="+json.dumps(check(report,state),sort_keys=True))
