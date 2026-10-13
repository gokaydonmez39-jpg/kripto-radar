#!/usr/bin/env python3
"""AAPL frozen exact30 1Min vs 30Min SIP RTH lower-bound feasibility pilot.

No vendor prices/volumes or entire bars are persisted. This is NOT C4.17
PRIMARY DV30: source entitlements, official close, corrections, and auction
lineage remain separate fail-closed requirements.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import urllib.parse
import urllib.request
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo
from alpaca_rth_minute_integrity_shadow import official_window as _official_window

@lru_cache(maxsize=128)
def official_window(day):
    """Memoize the same immutable official session calendar result per date."""
    return _official_window(day)
from alpaca_540_personal_daily_sip_coverage import sha_lines

NY=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
SYMBOL="AAPL"
ASOF="2026-10-12"
SCHEMA="XRAY_SIP_EXACT30_30MIN_RTH_LOWER_BOUND_1MIN_CROSSCHECK_SHADOW_V1"
MAX_CALLS=8
MAX_BYTES=2500000
LIMIT=Decimal("50000000")
SOURCE="https://docs.alpaca.markets/us/docs/market-data-faq"

def need(ok,code):
    if not ok:raise ValueError("XRAY_30M_"+code)

def stamp(row):
    need(type(row) is dict and type(row.get("t")) is str,"BAR_TIMESTAMP")
    t=dt.datetime.fromisoformat(row["t"].replace("Z","+00:00"))
    need(t.tzinfo is not None and t.utcoffset() is not None,"NAIVE_BAR")
    return t.astimezone(UTC)

def data_check(row):
    need(type(row) is dict, "BAR_SHAPE")
    values=[row.get(k) for k in ("o","h","l","c")]
    need(all(type(x) in (int,float) and math.isfinite(x) and x>0
             for x in values),"INVALID_OHLC")
    o,h,l,c=values
    need(h>=max(o,l,c) and l<=min(o,h,c),"OHLC_ORDER")
    v=row.get("v")
    need(type(v) is int and v>0,"VOLUME_INTEGRITY")
    return v

def validate(daily,halfhour,minute,dates):
    need(len(dates)==30 and len(set(dates))==30 and dates[-1]==ASOF,
         "EXACT30_DATES")
    expected_start={}
    expected_end={}
    mins=set()
    thirty=set()
    for day in dates:
        start,end,count=official_window(day)
        need(count==390,"PILOT_EARLY_CLOSE_UNSUPPORTED")
        expected_start[day]=start
        expected_end[day]=end
        for i in range(count):
            mins.add(start+dt.timedelta(minutes=i))
        for i in range(13):
            thirty.add(start+dt.timedelta(minutes=30*i))
    need(len(mins)==11700 and len(thirty)==390,"CALENDAR_CARDINALITY")
    byday={}
    for r in daily:
        t=stamp(r)
        day=t.astimezone(NY).date().isoformat()
        if day in dates:
            need(day not in byday,"DUPLICATE_DAILY")
            data_check(r)
            byday[day]=r
    need(set(byday)==set(dates),"DAILY_EXACT30")
    one={}
    for row in minute:
        when=stamp(row)
        if when in mins:
            need(when not in one,"DUPLICATE_MINUTE")
            one[when]=data_check(row)
    need(set(one)==mins,"NOT_11700_RTH_MINUTES")
    thirty_values={}
    for row in halfhour:
        when=stamp(row)
        if when in thirty:
            need(when not in thirty_values,"DUPLICATE_30MIN")
            thirty_values[when]=data_check(row)
    need(set(thirty_values)==thirty,"NOT_390_RTH_HALF_HOURS")
    lower=[]
    upper=[]
    for day in dates:
        start=expected_start[day]
        minute_sum=0
        thirty_sum=0
        for k in range(13):
            begin=start+dt.timedelta(minutes=30*k)
            part=sum(one[begin+dt.timedelta(minutes=j)] for j in range(30))
            need(part==thirty_values[begin],"MINUTE_TO_30MIN_MISMATCH")
            minute_sum+=part
            thirty_sum+=thirty_values[begin]
        need(minute_sum==thirty_sum,"RTH_AGGREGATE_MISMATCH")
        daily_total=data_check(byday[day])
        need(thirty_sum<=daily_total,"DAILY_LOWERBOUND_VIOLATION")
        close=Decimal(str(byday[day]["c"]))
        need(close.is_finite() and close>0,"CLOSE_NONFINITE")
        lower.append(close*thirty_sum)
        upper.append(close*daily_total)
    lower.sort()
    upper.sort()
    lower_median=(lower[14]+lower[15])/Decimal(2)
    upper_median=(upper[14]+upper[15])/Decimal(2)
    need(lower_median<=upper_median,"MEDIAN_MONOTONICITY")
    return {
        "schema":SCHEMA,"symbol":SYMBOL,"asof_et":ASOF,
        "exact30_complete":True,"official_session_count":30,
        "rth_minute_count_verified":len(one),
        "rth_30min_count_verified":len(thirty_values),
        "minute_to_30min_all_windows_exact":True,
        "daily_sip_volume_upperbounds_rth_30min":True,
        "sip_daily_close_rth_official_settlement_independently_verified":False,
        "full_close_auction_condition_coverage_verified":False,
        "trade_correction_cancel_lineage_verified":False,
        "source_automated_non_display_entitlement_verified":False,
        "shadow_lower_bound_median_ge_50m":lower_median>=LIMIT,
        "shadow_daily_upper_bound_median_lt_50m":upper_median<LIMIT,
        "shadow_rth_dv30_status":(
            "SHADOW_LOWER_BOUND_MEETS_THRESHOLD_NOT_PRIMARY"
            if lower_median>=LIMIT else
            "SHADOW_LOWER_BOUND_BELOW_THRESHOLD_NOT_AN_ALPHA_FAIL"),
        "primary_dv30_pass_created":False,
        "primary_dv30_fail_created":False,
        "primary_mc_created":False,"r92_created":False,
        "raw_ohlcv_stored":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"historical_replay_not_current":True,
        "exact30_session_sha256":sha_lines(dates),
        "evidence_doc":SOURCE,
    }

def selftest():
    import pandas_market_calendars as mcal
    from copy import deepcopy
    days=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date=ASOF)]
    need(len(days)==30,"CALENDAR_FIXTURE")
    daily=[];mins=[];halves=[]
    for day in days:
        start,end,n=official_window(day)
        local=start.astimezone(NY).date()
        opening=dt.datetime.combine(local,dt.time(0,0),NY).astimezone(UTC)
        daily.append({"t":opening.isoformat(),"o":10.,"h":11.,"l":9.,
                      "c":10.,"v":5_000_001})
        for i in range(13):
            begin=start+dt.timedelta(minutes=30*i)
            halves.append({"t":begin.isoformat(),"o":10.,"h":11.,"l":9.,
                           "c":10.,"v":150000})
            for j in range(30):
                mins.append({"t":(begin+dt.timedelta(minutes=j)).isoformat(),
                             "o":10.,"h":11.,"l":9.,"c":10.,"v":5000})
    result=validate(daily,halves,mins,days)
    need(result["exact30_complete"] and
         result["rth_minute_count_verified"]==11700 and
         result["rth_30min_count_verified"]==390 and
         not result["shadow_lower_bound_median_ge_50m"] and
         not result["primary_dv30_pass_created"],"POSITIVE_SHADOW")
    increased=deepcopy(halves)
    large=deepcopy(mins)
    higher=deepcopy(daily)
    for r in increased:r["v"]=450000
    for r in large:r["v"]=15000
    for r in higher:r["v"]=9_000_000
    passed=validate(higher,increased,large,days)
    need(passed["shadow_lower_bound_median_ge_50m"] and
         not passed["primary_dv30_pass_created"],"THRESHOLD_SHADOW_ONLY")
    bad=[
        (lambda d,h,m:m.pop(123),"MISSING_MINUTE"),
        (lambda d,h,m:h.pop(5),"MISSING_HALF_HOUR"),
        (lambda d,h,m:h[0].update(v=149999),"MISMATCH_VOLUME"),
        (lambda d,h,m:d[0].update(v=1),"LOWER_GT_UPPER"),
        (lambda d,h,m:m[0].update(t=m[1]["t"]),"DUPLICATE"),
        (lambda d,h,m:m[0].update(v=True),"BOOL_VOLUME"),
        (lambda d,h,m:d[0].update(c=float("nan")),"NONFINITE"),
    ]
    for change,name in bad:
        aa,bb,cc=(deepcopy(daily),deepcopy(halves),deepcopy(mins))
        change(aa,bb,cc)
        try:validate(aa,bb,cc,days)
        except (ValueError,TypeError,KeyError):pass
        else:raise AssertionError("NEGATIVE_ACCEPTED_"+name)
    print("XRAY_30M_RTH_1MIN_CROSSCHECK_SELFTEST=PASS_7_NEGATIVES_30D_11700_MIN_390_30MIN_NO_PRIMARY")

def fetch(creds):
    key,secret=creds
    calls=[0]
    base="https://data.alpaca.markets/v2/stocks/AAPL/bars"
    def one(timeframe):
        rows=[];token=None;seen=set()
        while True:
            need(calls[0]<MAX_CALLS,"MAX_GLOBAL_REQUESTS")
            calls[0]+=1
            params={"feed":"sip","timeframe":timeframe,
                    "adjustment":"raw","sort":"asc","limit":"10000",
                    "start":"2026-08-31T00:00:00-04:00",
                    "end":"2026-10-12T23:59:59-04:00"}
            if token:params["page_token"]=token
            req=urllib.request.Request(base+"?"+urllib.parse.urlencode(params),
                 headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                          "Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=30) as resp:
                raw=resp.read(MAX_BYTES+1)
            need(len(raw)<=MAX_BYTES,"HTTP_BODY_BUDGET")
            obj=json.loads(raw)
            need(type(obj) is dict and type(obj.get("bars")) is list,
                 "VENDOR_RESPONSE_SCHEMA")
            rows.extend(obj["bars"])
            nxt=obj.get("next_page_token")
            if not nxt:break
            need(type(nxt) is str and nxt not in seen,"PAGE_TOKEN_CYCLE")
            seen.add(nxt);token=nxt
        return rows
    return one("1Day"),one("30Min"),one("1Min"),calls[0]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--one-shot-frozen-20261012",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    need(args.one_shot_frozen_20261012 and args.out is not None,
         "ONE_SHOT_EXPLICIT_REQUIRED")
    need(not args.out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),
         "NO_PUBLIC_REPO_OUTPUT")
    need(os.getenv("XRAY_ALPACA_PERSONAL_BASIC_SHADOW_ENABLED","").lower()=="true",
         "PERSONAL_OPT_IN")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    need(key and secret,"NO_HISTORICAL_SIP_CREDENTIALS")
    import pandas_market_calendars as mcal
    dates=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date=ASOF)]
    need(len(dates)==30,"EXPECTED30_CHANGED")
    daily,half,minutes,calls=fetch((key,secret))
    try:
        result=validate(daily,half,minutes,dates)
        result["status"]="SHADOW_FULL_30D_RTH_BAR_RECONCILIATION_NO_PRIMARY"
    except (ValueError,KeyError,TypeError):
        result={"schema":SCHEMA,"symbol":SYMBOL,"asof_et":ASOF,
                "status":"BLOCKED_30DAY_BAR_INTEGRITY_OR_AGGREGATE_MISMATCH",
                "exact30_complete":False,
                "primary_dv30_pass_created":False,
                "primary_dv30_fail_created":False,
                "primary_mc_created":False,"r92_created":False,
                "raw_ohlcv_stored":False,"historical_replay_not_current":True,
                "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    result["api_calls"]=calls
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_30MIN_RTH_LOWER_BOUND_STATUS="+result["status"])
    if result.get("exact30_complete"):
        print("XRAY_30MIN_RTH_LOWER_BOUND_THRESHOLD_SHADOW="+
              str(result["shadow_lower_bound_median_ge_50m"]))
    print("XRAY_30MIN_RTH_PRIMARY_DV30=0_MC=0_R92=0")

if __name__=="__main__":main()
