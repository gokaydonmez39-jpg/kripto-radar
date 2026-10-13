#!/usr/bin/env python3
"""Recheck only 338 historical SIP records rejected for malformed OHLCV.

Requires exact SHA-256 pinned 3185-symbol CI artifact #38481474945 and
immutable same-ASOF root. Raw prices/volumes stay in memory, never persisted.
Any apparent provider correction is RESEARCH_REVISION, never PRIMARY or R92.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import time
from pathlib import Path

import alpaca_root_asof_260_four_symbol_shadow as original
from alpaca_root260_full_cohort_personal import request_one

ROOT=Path(__file__).resolve().parent
EXPECTED_SHA="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e"
SOURCE_RUN=38481474945
SOURCE_ROOT="dd6d3e6574dc318017d46f412b69e2a5f1331df5"
ASOF="2026-10-13"
BAD="UNKNOWN_BAD_OHLCV"
BATCH=8
MAX_CALLS=45

def require(ok,reason):
    if not ok:raise ValueError("XRAY_BAD338_"+reason)

def source_scope(blob):
    require(hashlib.sha256(blob).hexdigest()==EXPECTED_SHA,"ARTIFACT_HASH")
    doc=json.loads(blob)
    require(doc.get("schema")=="XRAY_FULL_ROOT_260_52_PERSONAL_SIP_COHORT_V1"
            and doc.get("asof_et")==ASOF and doc.get("full_scope_reached") is True
            and doc.get("total_scope")==3185
            and doc.get("source_root_git_blob_sha")==SOURCE_ROOT
            and doc.get("prior_ci_run")==38477817138
            and doc.get("r92_created") is False
            and doc.get("c417_primary_history_created") is False
            and doc.get("vendor_raw_ohlcv_persisted") is False,
            "FROZEN_SCOPE_OR_AUTHORITY")
    statuses=doc["symbol_statuses"]
    require(type(statuses) is dict and len(statuses)==3185 and
            doc.get("counts",{}).get(BAD)==338,
            "SOURCE_PARTITION")
    target=sorted(s for s,why in statuses.items() if why==BAD)
    require(len(target)==338 and len(set(target))==338,"TARGET_COUNT")
    return target

def reason(rows,required,weekly):
    if type(rows) is not list:return "MALFORMED_PROVIDER_ROWS"
    dates=set()
    for bar in rows:
        if type(bar) is not dict:return "ROW_NOT_OBJECT"
        try:day=original.timestamp_date(bar["t"]).isoformat()
        except (ValueError,TypeError,KeyError,OverflowError):
            return "INVALID_DAILY_TIMESTAMP"
        if day in dates or day>ASOF:return "FUTURE_OR_DUPLICATE_BAR"
        dates.add(day)
        try:
            values=[bar[k] for k in ("o","h","l","c")]
            v=bar["v"]
        except KeyError:return "MISSING_PRICE_OR_VOLUME_FIELD"
        if type(v) is not int:return "NONINTEGER_OR_BOOLEAN_VOLUME"
        if v<=0:return "ZERO_OR_NEGATIVE_DAILY_VOLUME"
        if not all(type(x) in (float,int) and math.isfinite(x) and x>0
                   for x in values):
            return "MALFORMED_NONFINITE_OR_ZERO_PRICE"
        o,h,l,c=values
        if l>min(o,c,h) or h<max(o,l,c):
            return "INCONSISTENT_OHLC_ORDER"
    if not set(required).issubset(dates):
        return "NOW_MISSING_REQUIRED_SESSIONS"
    if not set(weekly).issubset(dates):
        return "NOW_MISSING_WEEK_CLOSING_DATES"
    return "SOURCE_NO_LONGER_REPRODUCES_PRIOR_FAILURE"

def selftest():
    # Unit fixtures intentionally contain synthetic values and have NO market authority.
    d=["2026-10-12","2026-10-13"]
    w=["2026-10-13"]
    good=[{"t":"2026-10-12T04:00:00Z","o":10,
           "h":11,"l":9,"c":10,"v":100}]
    require(reason(good,d,w)=="NOW_MISSING_REQUIRED_SESSIONS","MISSING_DATE")
    require(reason([dict(good[0],v=0)],d,w)==
            "ZERO_OR_NEGATIVE_DAILY_VOLUME","ZERO_VOL")
    require(reason([dict(good[0],v=1.4)],d,w)==
            "NONINTEGER_OR_BOOLEAN_VOLUME","FLOAT_VOL")
    require(reason([dict(good[0],h=8)],d,w)==
            "INCONSISTENT_OHLC_ORDER","OHLC_ORDER")
    require(reason([dict(good[0],t="bad")],d,w)==
            "INVALID_DAILY_TIMESTAMP","BAD_TIMESTAMP")
    require(reason(None,d,w)=="MALFORMED_PROVIDER_ROWS","BAD_ROWS")
    print("XRAY_BAD338_SELFTEST=PASS_6_ADVERSARIAL_NOT_PRIMARY")

def run(input_bytes,output):
    target=source_scope(input_bytes)
    dates,weeks,root=original.source_scope()
    require(original.blob_sha(ROOT/"sina_state.json")==SOURCE_ROOT
            and root["unknown_count"]==3185
            and dates[-1]==ASOF and len(dates)==260 and len(weeks)==52,
            "CURRENT_ROOT_CALENDAR_DRIFT")
    result={
      "schema":"XRAY_BAD338_20261013_SIP_OHLCV_DIAGNOSTIC_V1",
      "asof_et":ASOF,"source_artifact_run_id":SOURCE_RUN,
      "source_artifact_sha256":EXPECTED_SHA,
      "source_root_git_blob_sha":SOURCE_ROOT,
      "source_status":BAD,"target_count":len(target),
      "symbol_statuses":{s:"UNKNOWN_NOT_YET_RECHECKED" for s in target},
      "counts":{},"actual_api_calls":0,"call_budget":MAX_CALLS,
      "source_problem":None,"remaining_count":len(target),
      "scope_fully_classified":False,
      "no_raw_ohlcv_exported":True,"canonical_root_modified":False,
      "canonical_history_modified":False,"primary_history_created":False,
      "r92_created":False,"execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True}
    def save():
        result["counts"]=dict(sorted(collections.Counter(
            result["symbol_statuses"].values()).items()))
        result["remaining_count"]=result["counts"].get(
            "UNKNOWN_NOT_YET_RECHECKED",0)
        result["scope_fully_classified"]=result["remaining_count"]==0
        output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    save()
    key=(os.environ.get("XRAY_ALPACA_DATA_KEY_ID") or
         os.environ.get("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.environ.get("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    require(bool(key and secret),"MISSING_PRIVATE_KEYS")
    require((len(target)+BATCH-1)//BATCH<=MAX_CALLS,"API_BUDGET")
    for i in range(0,len(target),BATCH):
        batch=target[i:i+BATCH]
        result["actual_api_calls"]+=1
        try:
            payload=request_one(batch,dates[0],key,secret)
            for sym in batch:
                classification=original.classify(payload.get(sym,[]),dates,weeks)
                if classification=="UNKNOWN_BAD_OHLCV":
                    classification="REPRODUCED_"+reason(payload.get(sym),dates,weeks)
                elif classification=="OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY":
                    classification="SOURCE_REVISED_SINCE_BASELINE_NO_PRIMARY"
                else:
                    classification="NEW_"+classification
                result["symbol_statuses"][sym]=classification
        except (RuntimeError,ValueError) as exc:
            message=str(exc)
            if "HTTP_403" in message or "HTTP_429" in message:
                result["source_problem"]="RATE_OR_AUTH_STOP"
                for sym in batch:result["symbol_statuses"][sym]="UNKNOWN_PROVIDER_ACCESS"
                save()
                break
            result["source_problem"]="BATCH_TRANSPORT_ERROR"
            for sym in batch:result["symbol_statuses"][sym]="UNKNOWN_PROVIDER_RETRY_FAILED"
        save()
        if i+BATCH<len(target):time.sleep(0.65)
    save()
    print("XRAY_BAD338_CAUSE_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_BAD338_SOURCE_CALLS="+str(result["actual_api_calls"]))
    print("XRAY_BAD338_NO_CANONICAL_PASS=TRUE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--frozen-artifact",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        require(args.frozen_artifact is None and args.out is None,"TEST_ARGS")
        selftest()
        return
    require(args.frozen_artifact is not None and args.out is not None
            and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
            "SAFE_OUTPUT_REQUIRED")
    run(args.frozen_artifact.read_bytes(),args.out)

if __name__=="__main__":
    main()
