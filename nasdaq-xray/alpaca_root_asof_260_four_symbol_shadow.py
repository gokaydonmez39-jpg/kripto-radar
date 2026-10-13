#!/usr/bin/env python3
"""Independent exact 2026-10-13 root HISTORY source diagnostic; NO PRIMARY.

Uses official NASDAQ 260 completed session dates and the last 52 completed
weekly closes; does not borrow a stale PRICE epoch, rewrite Sina or certify
market-data use rights. All vendor bars remain in volatile process memory.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from alpaca_free_sip_shadow_guard import request_batch,sufficient_delay,timestamp_date,blob_sha
from alpaca_sip_paginated_transport_shadow import MAX_PAGES
from current_history_source_request import expected_dates

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
SYMBOLS=("AAPL","AMZN","MSFT","NVDA")
SCHEMA="XRAY_ROOT_EXACT_ASOF_260_FOUR_SYMBOL_HISTORY_SHADOW_V1"
SAFE={"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def demand(ok,code):
    if not ok:
        raise ValueError("ROOT_260_SHADOW_"+code)

def source_scope():
    state=json.loads((ROOT/"sina_state.json").read_text())
    demand(state.get("asof_et")==ASOF and state.get("status")=="HISTORY_PARTIAL"
           and state.get("unknown_never_pass") is True
           and state.get("execution")=="NONE" and state.get("real_money")=="NO-GO"
           and state.get("unknown_count")>0,"ROOT_EPOCH")
    rows=state.get("results")
    demand(type(rows) is dict and all(s in rows and
           rows[s].get("status","").startswith("UNKNOWN") for s in SYMBOLS),
           "ROOT_FOUR_UNKNOWN_SCOPE")
    daily,weeks=expected_dates(ASOF)
    demand(len(daily)==260 and daily[-1]==ASOF and
           len(weeks)==52 and weeks[-1]<=ASOF
           and set(weeks).issubset(set(daily)),"EXACT_SESSION_SET")
    return daily,weeks,state

def classify(rows,daily,weeks):
    demand(len(daily)==260 and len(set(daily))==260
           and len(weeks)==52 and set(weeks).issubset(set(daily)),
           "CALENDAR_SCOPE")
    if type(rows) is not list:
        return "UNKNOWN_NON_LIST_PROVIDER_HISTORY"
    observed=set()
    for bar in rows:
        if type(bar) is not dict:
            return "UNKNOWN_MALFORMED_BAR"
        try:
            day=timestamp_date(bar["t"]).isoformat()
            values=[bar[k] for k in ("o","h","l","c")]
            vol=bar["v"]
        except (ValueError,KeyError,TypeError,OverflowError,AttributeError):
            return "UNKNOWN_BAD_DATE_OR_BAR"
        if not(all(type(v) in (int,float) and math.isfinite(v) and v>0
                    for v in values)
               and type(vol) is int and vol>0):
            return "UNKNOWN_BAD_OHLCV"
        o,h,l,c=values
        if not(l<=min(o,c,h) and h>=max(o,l,c)):
            return "UNKNOWN_OHLC_ORDER"
        if day>ASOF or day in observed:
            return "UNKNOWN_FUTURE_OR_DUPLICATE"
        observed.add(day)
    if not set(daily).issubset(observed):
        return "UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE"
    if not set(weeks).issubset(observed):
        return "UNKNOWN_52_WEEK_CLOSES_INCOMPLETE"
    return "OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY"

def report(statuses,state,daily,weeks,source_status):
    counts=dict(sorted(collections.Counter(statuses.values()).items()))
    return {"schema":SCHEMA,"asof_et":ASOF,
      "source_root_git_blob_sha":blob_sha(ROOT/"sina_state.json"),
      "source_root_status":state["status"],
      "source_root_unknown_count":state["unknown_count"],
      "source_root_scope_only":True,
      "symbols":list(SYMBOLS),
      "requested_symbols":len(SYMBOLS),
      "expected_daily_sessions":len(daily),
      "expected_completed_week_closes":len(weeks),
      "calendar_first":daily[0],"calendar_last":daily[-1],
      "source_status":source_status,"symbol_statuses":statuses,
      "counts":counts,"max_alpaca_paginated_calls":MAX_PAGES,
      "source":"ALPACA_PERSONAL_SIP_HISTORICAL_1DAY_RAW",
      "unadjusted_rth_market_volume_verified":False,
      "corporate_action_and_class_continuity_verified":False,
      "automatic_non_display_rights_verified":False,
      "canonical_master_modified":False,"canonical_history_modified":False,
      "primary_dv30_created":False,"primary_history_created":False,
      "primary_mc_created":False,"r92_created":False,
      "vendor_raw_ohlcv_persisted":False,**SAFE}

def selftest():
    daily,weeks,state=source_scope()
    def bar(day):
        midnight=dt.datetime.combine(
            dt.date.fromisoformat(day),dt.time(0,0),
            tzinfo=ZoneInfo("America/New_York"))
        return {"t":midnight.astimezone(dt.timezone.utc).isoformat(),
                "o":10,"h":11,"l":9,"c":10,"v":10000}
    demand(timestamp_date(bar("2026-01-12")["t"]).isoformat()=="2026-01-12"
           and timestamp_date(bar("2026-10-13")["t"]).isoformat()=="2026-10-13",
           "DST_FIXTURE_CORRECTNESS")
    positive=[bar(x) for x in daily]
    demand(classify(positive,daily,weeks)=="OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY","POSITIVE")
    cases=[
        (positive[:-1],"UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE"),
        (positive+[dict(positive[-1])],"UNKNOWN_FUTURE_OR_DUPLICATE"),
        (positive[:-1]+[dict(positive[-1],v=0)],"UNKNOWN_BAD_OHLCV"),
        (positive[:-1]+[dict(positive[-1],h=8)],"UNKNOWN_OHLC_ORDER"),
        (positive[:-1]+[dict(positive[-1],t="2026-10-14T04:00:00Z")],
         "UNKNOWN_FUTURE_OR_DUPLICATE"),
        (None,"UNKNOWN_NON_LIST_PROVIDER_HISTORY")]
    for rows,expected in cases:
        demand(classify(rows,daily,weeks)==expected,"NEGATIVE_"+expected)
    out=report({s:"OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY"
                for s in SYMBOLS},state,daily,weeks,"OFFLINE_FIXTURE")
    demand(out["requested_symbols"]==4 and out["expected_daily_sessions"]==260
           and out["expected_completed_week_closes"]==52
           and out["primary_history_created"] is False
           and out["r92_created"] is False,"NO_ALPHA")
    print("XRAY_ROOT_260_ASOF_SELFTEST=PASS_POSITIVE_6_NEGATIVES_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--one-shot-20261013",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:
        demand(not a.one_shot_20261013 and a.out is None,"SELFTEST_ARGS")
        selftest()
        return
    demand(a.one_shot_20261013 and a.out is not None
           and not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
           "EXPLICIT_SAFE_OUTPUT")
    daily,weeks,state=source_scope()
    demand(sufficient_delay(ASOF,dt.datetime.now(dt.timezone.utc)),
           "HISTORICAL_DELAY_NOT_EXPIRED")
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    demand(key and secret,"PRIVATE_ALPACA_CREDENTIALS_REQUIRED")
    start=(dt.date.fromisoformat(daily[0])-dt.timedelta(days=7)).isoformat()+"T00:00:00-04:00"
    end="2026-10-13T16:30:00-04:00"
    demand(dt.datetime.fromisoformat(end)<dt.datetime.now(dt.timezone.utc),
           "END_IS_FUTURE")
    try:
        bars=request_batch(list(SYMBOLS),start,end,key,secret)
        statuses={s:classify(bars.get(s),daily,weeks) for s in SYMBOLS}
        source_status="SIP_HISTORICAL_RESPONSE_CLASSIFIED"
    except (ValueError,RuntimeError,TimeoutError) as exc:
        code=str(exc)
        if not code.startswith("ALPACA_"):
            code="ALPACA_TRANSPORT_UNCLASSIFIED"
        statuses={s:"UNKNOWN_PROVIDER_"+code for s in SYMBOLS}
        source_status="PROVIDER_BLOCKED"
    out=report(statuses,state,daily,weeks,source_status)
    a.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_ROOT_260_LIVE_SHADOW_COUNTS="+json.dumps(out["counts"],sort_keys=True))
    print("XRAY_ROOT_260_PRIMARY_HISTORY_MC_R92=0")

if __name__=="__main__":
    main()
