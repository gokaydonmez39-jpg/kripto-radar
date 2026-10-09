#!/usr/bin/env python3
"""Independent zero-cost corporate split event date guard, not production history proof.

Massive /stocks/v1/splits is advertised on Stocks Basic Free with 2-year
availability; API can return future announced splits. Never use execution
events after ASOF in historical research. The guard validates an in-memory
fixture only, emits counts and reason codes, never raw vendor price/split rows.
No API keys, networking, PRICE/HISTORY/MC authority or AL.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import date, timedelta

SCHEMA="XRAY_MASSIVE_BASIC_SPLIT_ASOF_SHADOW_V1"
ALLOWED={"forward_split","reverse_split","stock_dividend"}


def classify(rows:object, asof:str, ticker:str)->dict:
    today=date.fromisoformat(asof)
    if today.isoformat()!=asof or not ticker or not ticker.isalnum():
        raise ValueError("SPLIT_ASOF_OR_TICKER_INVALID")
    if not isinstance(rows,list):
        raise ValueError("SPLIT_PROVIDER_SCHEMA_INVALID")
    cutoff=today-timedelta(days=731)
    counts={
        "at_or_before_asof_valid":0,
        "future_execution_excluded":0,
        "outside_basic_two_year_window":0,
        "wrong_ticker":0,
        "duplicate":0,
        "invalid_schema_or_ratio":0,
    }
    seen=set()
    for r in rows:
        if not isinstance(r,dict):
            counts["invalid_schema_or_ratio"]+=1;continue
        d=r.get("execution_date")
        try:day=date.fromisoformat(str(d))
        except (TypeError,ValueError):
            counts["invalid_schema_or_ratio"]+=1;continue
        if day>today:
            counts["future_execution_excluded"]+=1;continue
        if day<cutoff:
            counts["outside_basic_two_year_window"]+=1;continue
        if r.get("ticker")!=ticker:
            counts["wrong_ticker"]+=1;continue
        k=(ticker,d,str(r.get("id") or ""))
        if k in seen:
            counts["duplicate"]+=1;continue
        seen.add(k)
        x=r.get("split_from")
        y=r.get("split_to")
        if (r.get("adjustment_type") not in ALLOWED
                or isinstance(x,bool) or isinstance(y,bool)):
            counts["invalid_schema_or_ratio"]+=1;continue
        try:a,b=float(x),float(y)
        except (TypeError,ValueError,OverflowError):
            counts["invalid_schema_or_ratio"]+=1;continue
        if not (math.isfinite(a) and math.isfinite(b) and a>0 and b>0):
            counts["invalid_schema_or_ratio"]+=1;continue
        kind=r["adjustment_type"]
        if kind=="forward_split" and b<=a:
            counts["invalid_schema_or_ratio"]+=1;continue
        if kind=="reverse_split" and b>=a:
            counts["invalid_schema_or_ratio"]+=1;continue
        counts["at_or_before_asof_valid"]+=1
    assert sum(counts.values())==len(rows)
    return {
        "schema":SCHEMA,"asof_et":asof,"symbol":ticker,
        "status":"ASOF_DATE_FILTERED_SPLIT_OBSERVATIONS_ONLY",
        "source_role":"CORPORATE_ACTION_CROSSCHECK_NOT_HISTORY_OR_PRIMARY_MC",
        "total_rows_observed":len(rows),
        "counts":counts,
        "provider_time_of_first_publication_verified":False,
        "provider_licensing_for_GitHub_and_storage_verified":False,
        "full_all_split_events_covered":False,
        "history_adjustment_factors_independently_attested":False,
        "market_data_vendor_raw_rows_exported":False,
        "source_authority":False,"can_register_R92":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }


def selftest()->None:
    asof="2026-10-09"
    base={"ticker":"TEST","id":"1","execution_date":"2026-10-08",
          "split_from":1.0,"split_to":2.0,"adjustment_type":"forward_split"}
    good=classify([base],asof,"TEST")
    assert good["counts"]["at_or_before_asof_valid"]==1
    assert good["source_authority"] is False and good["can_register_R92"] is False
    from copy import deepcopy
    cases=[
        ({"execution_date":"2026-11-05"},"future_execution_excluded"),
        ({"execution_date":"2024-01-01"},"outside_basic_two_year_window"),
        ({"ticker":"WRONG"},"wrong_ticker"),
        ({"split_from":0},"invalid_schema_or_ratio"),
        ({"split_to":float("nan")},"invalid_schema_or_ratio"),
        ({"adjustment_type":"reverse_split"},"invalid_schema_or_ratio"),
        ({"execution_date":"garbled"},"invalid_schema_or_ratio"),
    ]
    for diff,cat in cases:
        bad=deepcopy(base);bad.update(diff)
        assert classify([bad],asof,"TEST")["counts"][cat]==1,cat
    assert classify([base,base],asof,"TEST")["counts"]["duplicate"]==1
    reverse=deepcopy(base);reverse.update(id="2",adjustment_type="reverse_split",split_from=10,split_to=1)
    assert classify([reverse],asof,"TEST")["counts"]["at_or_before_asof_valid"]==1
    assert classify([],asof,"TEST")["counts"]["at_or_before_asof_valid"]==0
    for unsafe in ({"execution_date":"2027-01-01"},{"execution_date":"2026-12-31"}):
        row=deepcopy(base);row.update(unsafe)
        assert classify([row],asof,"TEST")["counts"]["at_or_before_asof_valid"]==0
    print("XRAY_MASSIVE_FREE_SPLITS_ASOF_SELFTEST=PASS_POSITIVE_FUTURE_OLD_BAD_RATIO_DUPLICATE_UNKNOWN_NONAUTHORITY")


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:selftest()
    else:ap.error("No live fetch or vendor data output permitted; --selftest only")
