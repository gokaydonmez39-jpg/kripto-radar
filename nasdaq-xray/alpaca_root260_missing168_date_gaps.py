#!/usr/bin/env python3
"""Only 168 previously incomplete 260-session SIP symbols: date-gap diagnostics.

Metadata-only historical personal research. Official calendar is exact;
do not infer IPO dates, synthesize bars, create canonical HISTORY, or issue R92.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path

import alpaca_root_asof_260_four_symbol_shadow as prior
from alpaca_root260_full_cohort_personal import request_one

ROOT=Path(__file__).resolve().parent
SOURCE_SHA="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e"
ROOT_SHA="dd6d3e6574dc318017d46f412b69e2a5f1331df5"
ASOF="2026-10-13"
SOURCE_RUN=38481474945
INCOMPLETE="UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE"
BATCH=12
CALL_BUDGET=14

def check(ok,code):
    if not ok:raise ValueError("XRAY_MISSING168_"+code)

def frozen_target(data):
    check(hashlib.sha256(data).hexdigest()==SOURCE_SHA,"SOURCE_ARTIFACT_SHA")
    d=json.loads(data)
    check(d.get("schema")=="XRAY_FULL_ROOT_260_52_PERSONAL_SIP_COHORT_V1"
          and d.get("asof_et")==ASOF and d.get("full_scope_reached") is True
          and d.get("total_scope")==3185
          and d.get("source_root_git_blob_sha")==ROOT_SHA
          and d.get("counts",{}).get(INCOMPLETE)==168
          and d.get("r92_created") is False
          and d.get("c417_primary_history_created") is False,
          "SOURCE_SCOPE_OR_AUTHORITY")
    statuses=d.get("symbol_statuses")
    check(type(statuses) is dict and len(statuses)==3185,
          "FULL_SOURCE_MEMBERSHIP")
    targets=sorted(s for s,v in statuses.items() if v==INCOMPLETE)
    check(len(targets)==168 and len(set(targets))==168,
          "EXACT_168")
    return targets

def evaluate(symbol_rows,calendar,weeks):
    check(len(calendar)==260 and calendar[-1]==ASOF
          and len(weeks)==52 and set(weeks).issubset(calendar),
          "OFFICIAL_DATES")
    if type(symbol_rows) is not list:
        return "UNKNOWN_BAD_PROVIDER_SHAPE",0,0,0,0
    seen=set()
    for r in symbol_rows:
        if type(r) is not dict or type(r.get("t")) is not str:
            return "UNKNOWN_BAD_TIMESTAMP",0,0,0,0
        try:
            day=prior.timestamp_date(r["t"]).isoformat()
        except (ValueError,TypeError,OverflowError,AttributeError):
            return "UNKNOWN_BAD_TIMESTAMP",0,0,0,0
        if day in seen or day>ASOF:
            return "UNKNOWN_DUPLICATE_OR_FUTURE",0,0,0,0
        seen.add(day)
    missing=[day for day in calendar if day not in seen]
    if not missing:
        return "SOURCE_CHANGED_FULL_DATE_SET_REVERIFY_OHLCV",0,0,0,0
    initial=0
    for day in calendar:
        if day in seen:break
        initial+=1
    trailing=0
    for day in reversed(calendar):
        if day in seen:break
        trailing+=1
    # All 260 missing: prefix and suffix are the same dates, don't double count.
    if initial==len(calendar):
        return "NO_USABLE_OFFICIAL_SESSION_IN_260",len(calendar),len(calendar),0,0
    interior=len(missing)-initial-trailing
    check(interior>=0 and initial+interior+trailing==len(missing),"MISSING_PARTITION")
    if interior:
        klass="OFFICIAL_SESSION_GAP_IN_RETAINED_PERIOD"
    elif trailing:
        klass="CURRENT_OR_RECENT_SESSION_MISSING"
    else:
        klass="MISSING_EARLY_HISTORY_OR_LATE_LISTING_UNPROVEN"
    return klass,len(missing),initial,interior,trailing

def selftest():
    sample=["2026-10-08","2026-10-09","2026-10-12","2026-10-13"]
    def make(day):
        from zoneinfo import ZoneInfo
        ts=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0,0),
             tzinfo=ZoneInfo("America/New_York")).astimezone(dt.timezone.utc)
        return {"t":ts.isoformat()}
    f=lambda ds:evaluate([make(x) for x in ds],sample,sample[1:])
    check(f(sample)==("SOURCE_CHANGED_FULL_DATE_SET_REVERIFY_OHLCV",0,0,0,0),"FULL")
    check(f(sample[1:])==("MISSING_EARLY_HISTORY_OR_LATE_LISTING_UNPROVEN",1,1,0,0),"PREFIX")
    check(f(sample[:-1])==("CURRENT_OR_RECENT_SESSION_MISSING",1,0,0,1),"TRAILING")
    check(f([sample[0],sample[-1]])==("OFFICIAL_SESSION_GAP_IN_RETAINED_PERIOD",2,0,2,0),"INTERIOR")
    check(f([])==("NO_USABLE_OFFICIAL_SESSION_IN_260",4,4,0,0),"NONE")
    check(evaluate(None,sample,sample[1:])[0]=="UNKNOWN_BAD_PROVIDER_SHAPE","SHAPE")
    check(evaluate([make(sample[0])]*2,sample,sample[1:])[0]=="UNKNOWN_DUPLICATE_OR_FUTURE","DUPLICATE")
    print("XRAY_MISSING168_SELFTEST=PASS_7_FIXTURES_SESSION_SPLITS_NO_PRIMARY")

def run(raw,out):
    targets=frozen_target(raw)
    dates,weeks,state=prior.source_scope()
    check(prior.blob_sha(ROOT/"sina_state.json")==ROOT_SHA
          and state["unknown_count"]==3185,"ROOT_BLOB_OR_SET_DRIFT")
    check((len(targets)+BATCH-1)//BATCH<=CALL_BUDGET,"CALL_CAP")
    report={
      "schema":"XRAY_ROOT260_MISSING168_SOURCE_DATE_GAPS_V1",
      "asof_et":ASOF,"source_run":SOURCE_RUN,
      "source_report_sha256":SOURCE_SHA,"source_root_git_blob_sha":ROOT_SHA,
      "target_count":168,"official_daily_sessions":260,
      "official_completed_week_closes":52,
      "requested_research_symbols":targets,
      "statuses":{s:"UNKNOWN_NOT_YET_ATTEMPTED" for s in targets},
      "observed_date_metadata":{},
      "counts":{},"actual_api_calls":0,"max_api_calls":CALL_BUDGET,
      "remaining_count":168,"scope_classified":False,
      "provider_problem":None,
      "canonical_history_modified":False,
      "primary_history_created":False,"primary_price_created":False,
      "primary_market_cap_created":False,"r92_created":False,
      "vendor_raw_ohlcv_persisted":False,
      "same_asof_all_layers_proven":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        report["counts"]=dict(sorted(collections.Counter(report["statuses"].values()).items()))
        report["remaining_count"]=report["counts"].get("UNKNOWN_NOT_YET_ATTEMPTED",0)
        report["scope_classified"]=report["remaining_count"]==0
        out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    check(key and secret,"READ_ONLY_SOURCE_CREDENTIALS_REQUIRED")
    for k in range(0,len(targets),BATCH):
        batch=targets[k:k+BATCH]
        report["actual_api_calls"]+=1
        try:
            bars=request_one(batch,dates[0],key,secret)
            for sym in batch:
                status,total,initial,interior,trailing=evaluate(bars.get(sym),dates,weeks)
                report["statuses"][sym]=status
                report["observed_date_metadata"][sym]={
                    "missing_official_sessions":total,
                    "initial_missing":initial,
                    "interior_missing":interior,
                    "trailing_missing":trailing}
        except (RuntimeError,ValueError) as e:
            msg=str(e)
            # Stop on 403/429; no hammering or credential cycling.
            if "HTTP_403" in msg or "HTTP_429" in msg:
                report["provider_problem"]="PROVIDER_AUTH_OR_FAIR_ACCESS"
                for sym in batch:report["statuses"][sym]="UNKNOWN_SOURCE_ACCESS_STOP"
                save()
                break
            report["provider_problem"]="PROVIDER_BATCH_UNRESOLVED"
            for sym in batch:report["statuses"][sym]="UNKNOWN_SOURCE_TRANSPORT"
        save()
        if k+BATCH<len(targets):time.sleep(0.65)
    save()
    print("XRAY_MISSING168_REASON_COUNTS="+json.dumps(report["counts"],sort_keys=True))
    print("XRAY_MISSING168_CALLS="+str(report["actual_api_calls"]))
    print("XRAY_MISSING168_CANONICAL_MUTATIONS=0")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--frozen-artifact",type=Path)
    parser.add_argument("--out",type=Path)
    a=parser.parse_args()
    if a.selftest:
        check(a.frozen_artifact is None and a.out is None,"SELFTEST_ARGS")
        selftest()
        return
    check(a.frozen_artifact is not None and a.out is not None
          and not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
          "OUTPUT_MUST_BE_EPHEMERAL")
    run(a.frozen_artifact.read_bytes(),a.out)

if __name__=="__main__":
    main()
