#!/usr/bin/env python3
"""4-symbol frozen exact30 consolidated SIP 30Min regular-session LOWER bound.

Research-only. Alpaca's 30Min bars aggregate minute bars. 09:30..15:59:59
RTH minute-volume omits the 16:00 closing auction; it can prove a sufficient
non-auction dollar-volume LOWER bound, never a C4.17 PRIMARY PASS.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from alpaca_540_personal_daily_sip_coverage import ROOT,REPO,UTC,sha_lines
from alpaca_sip_30min_rth_lower_bound_pilot import stamp,data_check
from alpaca_rth_minute_integrity_shadow import official_window
from alpaca_sip_exact30_backup_probe import personal_shadow_access

SYMBOLS=("AAPL","NVDA","MSFT","AAON")
ASOF="2026-10-12"
SCHEMA="XRAY_SIP_EXACT30_4_SYMBOL_30MIN_RTH_LOWER_BOUND_SHADOW_V1"
LIMIT=Decimal("50000000")
MAX_CALLS=24
MAX_BYTES=2500000
MASTER_SHA="fb64a44b79ced9dcda390f5661b796ee13a60f63"
PRICE_SHA="787e1222fe140ae141b51e98bbbaaa9034ead377"

def need(ok,code):
    if not ok:raise ValueError("XRAY_4_30M_"+code)

@lru_cache(maxsize=64)
def session(day):
    return official_window(day)

def classify_one(daily,halfhour,dates):
    expected={}
    for day in dates:
        start,end,n=session(day)
        need(n==390,"EARLY_CLOSE_UNSUPPORTED_IN_FROZEN_SCOPE")
        expected.update({start+dt.timedelta(minutes=i*30):day for i in range(13)})
    daybars={}
    for r in daily:
        moment=stamp(r)
        from alpaca_sip_30min_rth_lower_bound_pilot import NY
        day=moment.astimezone(NY).date().isoformat()
        if day in dates:
            need(day not in daybars,"DUPLICATE_DAILY")
            data_check(r)
            daybars[day]=r
    need(set(daybars)==set(dates),"EXACT30_DAILY_MISSING")
    half={}
    for r in halfhour:
        at=stamp(r)
        if at in expected:
            need(at not in half,"DUPLICATE_30MIN")
            half[at]=data_check(r)
    need(set(half)==set(expected),"EXACT390_30MIN_MISSING")
    lower=[]
    upper=[]
    for day in dates:
        start,end,n=session(day)
        rth=sum(half[start+dt.timedelta(minutes=30*i)] for i in range(13))
        daily_volume=data_check(daybars[day])
        need(rth<=daily_volume,"DAILY_NOT_AN_UPPER_BOUND")
        close=Decimal(str(daybars[day]["c"]))
        need(close.is_finite() and close>0,"CLOSE_INVALID")
        lower.append(close*rth)
        upper.append(close*daily_volume)
    lower.sort();upper.sort()
    lo=(lower[14]+lower[15])/Decimal(2)
    hi=(upper[14]+upper[15])/Decimal(2)
    need(lo<=hi,"MEDIAN_BOUNDS_INVERTED")
    if lo>=LIMIT:return "LOWER_BOUND_GE_50M_SHADOW"
    if hi<LIMIT:return "UPPER_BOUND_LT_50M_SHADOW"
    return "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW"

@lru_cache(maxsize=1)
def official_frozen_exact30():
    """Independent official calendar fence for the frozen 2026-10-12 research cohort."""
    import pandas_market_calendars as mcal
    dates=tuple(x.date().isoformat() for x in
        mcal.get_calendar("NASDAQ").valid_days(
            start_date="2026-08-31",end_date=ASOF))
    need(len(dates)==30 and dates[-1]==ASOF,
         "OFFICIAL_CALENDAR_FROZEN_SCOPE_CHANGED")
    return dates

def measure(daily,halfhour,dates):
    need(type(daily) is dict and type(halfhour) is dict,
         "BAD_BATCH_PAYLOAD")
    need(type(dates) is list and len(dates)==30 and
         all(type(day) is str for day in dates) and
         tuple(dates)==official_frozen_exact30(),
         "NOT_EXACT30_OFFICIAL_CALENDAR")
    need(set(daily).issubset(set(SYMBOLS)) and
         set(halfhour).issubset(set(SYMBOLS)),"FOREIGN_SYMBOL")
    statuses={}
    for symbol in SYMBOLS:
        try:
            statuses[symbol]=classify_one(
                daily.get(symbol,[]),halfhour.get(symbol,[]),dates)
        except (ValueError,KeyError,TypeError,OverflowError):
            statuses[symbol]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    need(len(statuses)==len(SYMBOLS),"SCOPE_TRUNCATION")
    bucket={state:sum(x==state for x in statuses.values()) for state in
      ("LOWER_BOUND_GE_50M_SHADOW","UPPER_BOUND_LT_50M_SHADOW",
       "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
       "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW")}
    need(sum(bucket.values())==len(SYMBOLS),"BUCKET_TOTAL")
    proof=sorted(s for s in SYMBOLS if
                 statuses[s]=="LOWER_BOUND_GE_50M_SHADOW")
    return {"schema":SCHEMA,"asof_et":ASOF,"symbols_requested":4,
            "symbols_completed":4,"counts":bucket,
            "lowerbound_ge_50m_symbol_sha256":sha_lines(proof),
            "source_master_blob_sha":MASTER_SHA,
            "source_price_blob_sha":PRICE_SHA,
            "shadow_symbol_statuses":statuses,
            "provider":"ALPACA_PERSONAL_HISTORICAL_SIP",
            "rth_from_30min_without_auction":True,
            "source_minute_aggregation_pilot_aapl_exact30_passed":True,
            "vendor_dataset_independence_verified":False,
            "automated_non_display_rights_verified":False,
            "official_price_settlement_verified":False,
            "correction_cancellation_lineage_verified":False,
            "primary_price_pass_created":False,
            "primary_dv30_pass_created":False,
            "primary_dv30_fail_created":False,
            "primary_mc_created":False,"r92_created":False,
            "raw_ohlcv_persisted":False,
            "historical_replay_not_current":True,
            "unknown_never_pass":True,"execution":"NONE",
            "real_money":"NO-GO",
            "exact30_session_sha256":sha_lines(dates)}

def selftest():
    import pandas_market_calendars as mcal
    from copy import deepcopy
    dates=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
         start_date="2026-08-31",end_date=ASOF)]
    need(len(dates)==30,"SELFTEST_DATE_COUNT")
    daily={};half={}
    for sym in SYMBOLS:
        daily[sym]=[];half[sym]=[]
        for day in dates:
            start,end,n=session(day)
            midnight=start.astimezone(dt.timezone(dt.timedelta(hours=-4)))
            midnight=midnight.replace(hour=0,minute=0,second=0,microsecond=0)
            daily[sym].append({"t":midnight.isoformat(),
                               "o":10.,"h":11.,"l":9.,"c":10.,
                               "v":9000000})
            for i in range(13):
                half[sym].append({"t":(start+dt.timedelta(minutes=30*i)).isoformat(),
                                  "o":10.,"h":11.,"l":9.,"c":10.,
                                  "v":450000})
    def reject_bad_calendar(candidate,reason):
        try:
            measure(daily,half,candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("BAD_EXACT30_CALENDAR_ACCEPTED_"+reason)
    duplicate=dates.copy()
    duplicate[4]=duplicate[3]
    reject_bad_calendar(duplicate,"DUPLICATE_DATE")
    reordered=dates.copy()
    reordered[3],reordered[4]=reordered[4],reordered[3]
    reject_bad_calendar(reordered,"REORDERED_DATES")
    reject_bad_calendar(["2026-08-28"]+dates[1:],
                        "MISSING_RECENT_OFFICIAL_SESSION")
    reject_bad_calendar(dates[:-1],"TRUNCATED")
    reject_bad_calendar(tuple(dates),"WRONG_CONTAINER")
    print("XRAY_4SYM_OFFICIAL_EXACT30_NEGATIVE=PASS_DUPLICATE_ORDER_MISSING_TRUNCATION")
    good=measure(daily,half,dates)
    need(good["counts"]["LOWER_BOUND_GE_50M_SHADOW"]==4 and
         good["primary_dv30_pass_created"] is False,"POSITIVE_SHADOW_ONLY")
    high=deepcopy(daily);small=deepcopy(half)
    for row in high["AAON"]:row["v"]=4000000
    for row in small["AAON"]:row["v"]=100000
    low=measure(high,small,dates)
    need(low["shadow_symbol_statuses"]["AAON"]==
         "LOWER_BOUND_GE_50M_SHADOW" or
         low["shadow_symbol_statuses"]["AAON"]==
         "UPPER_BOUND_LT_50M_SHADOW","LOWER_OR_UPPER")
    need(low["shadow_symbol_statuses"]["AAON"]==
         "UPPER_BOUND_LT_50M_SHADOW","PROVEN_FAIL_ONLY")
    bad=deepcopy(half)
    bad["MSFT"].pop()
    state=measure(daily,bad,dates)
    need(state["shadow_symbol_statuses"]["MSFT"]==
         "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW" and
         state["counts"]["LOWER_BOUND_GE_50M_SHADOW"]==3,
         "MISSING_BAR_DOES_NOT_POISON_OTHERS")
    injected=deepcopy(half)
    injected["AAPL"][0]["v"]=False
    state=measure(daily,injected,dates)
    need(state["shadow_symbol_statuses"]["AAPL"]==
         "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW","BOOL_REJECT")
    altered=deepcopy(half)
    altered["NVDA"][0]["v"]=1000000000
    state=measure(daily,altered,dates)
    need(state["shadow_symbol_statuses"]["NVDA"]==
         "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW","MONOTONE_VIOLATION")
    samples=[
        {"bars":{"AAPL":[{"t":"a"}]},"next_page_token":"step2"},
        {"bars":{"NVDA":[{"t":"b"}],"AAPL":[{"t":"c"}]},
         "next_page_token":None}]
    pager_calls=[]
    def mock_page(token):
        pager_calls.append(token)
        return samples[0] if token is None else samples[1]
    pages=collect_pages_exact(mock_page)
    need(pager_calls==[None,"step2"] and len(pages["AAPL"])==2
         and len(pages["NVDA"])==1,"PAGINATION_MERGE")
    def deny(getpage,label):
        try:collect_pages_exact(getpage,max_pages=2)
        except ValueError:pass
        else:raise AssertionError("PAGINATION_NEGATIVE_ACCEPTED_"+label)
    deny(lambda t:{"bars":{},"next_page_token":"repeat"},"CYCLE")
    seq=[0]
    def endless(token):
        seq[0]+=1
        return {"bars":{},"next_page_token":str(seq[0])}
    deny(endless,"MAX_PAGE_BUDGET")
    deny(lambda token:{"bars":{"UNLISTED":[]},"next_page_token":None},
         "FOREIGN_SYMBOL")
    # Global hard budget is intentionally greater than the original 8 pages.
    # Providers may paginate by symbol, even with a nominal limit=10000.
    need(MAX_CALLS==24,"BOUND_TO_24")
    print("XRAY_4SYM_30M_PAGINATION_SELFTEST=PASS_MERGE_CYCLE_LIMIT_FOREIGN_NO_HTTP")
    print("XRAY_4SYM_30M_EXACT30_SELFTEST=PASS_MIXED_UNKNOWN_BOUND_NO_PRIMARY")

def git_blob(path):
    import subprocess
    return subprocess.check_output(["git","hash-object",str(path)],
                                   text=True).strip()

def collect_pages_exact(getpage,max_pages=8):
    """Merge exact case-sensitive provider pages. Never silently truncate scope."""
    need(type(max_pages) is int and 1<=max_pages<=MAX_CALLS,"PAGE_CAP_INVALID")
    merged={}
    token=None
    used_tokens=set()
    for _ in range(max_pages):
        data=getpage(token)
        need(type(data) is dict and type(data.get("bars")) is dict,
             "PAGE_SCHEMA")
        for symbol,rows in data["bars"].items():
            need(symbol in SYMBOLS and type(rows) is list,
                 "PAGE_FOREIGN_SYMBOL_OR_BAD_ROWS")
            merged.setdefault(symbol,[]).extend(rows)
        nxt=data.get("next_page_token")
        if not nxt:
            return merged
        need(type(nxt) is str and nxt not in used_tokens,
             "PAGE_TOKEN_CYCLE_OR_MALFORMED")
        used_tokens.add(nxt)
        token=nxt
    raise ValueError("XRAY_4_30M_PAGINATION_LIMIT_INCOMPLETE")

def fetch(keys):
    creds,secret=keys
    base="https://data.alpaca.markets/v2/stocks/bars"
    calls=[0]
    def one(timeframe):
        def request_page(token):
            need(calls[0]<MAX_CALLS,"GLOBAL_CALL_BUDGET_EXHAUSTED")
            calls[0]+=1
            params={"symbols":",".join(SYMBOLS),"timeframe":timeframe,
                    "feed":"sip","adjustment":"raw","sort":"asc",
                    "limit":"10000","start":"2026-08-31T00:00:00-04:00",
                    "end":"2026-10-12T23:59:59-04:00"}
            if token:params["page_token"]=token
            request=urllib.request.Request(base+"?"+urllib.parse.urlencode(params),
                headers={"APCA-API-KEY-ID":creds,
                         "APCA-API-SECRET-KEY":secret,"Accept":"application/json"})
            with urllib.request.urlopen(request,timeout=30) as handle:
                raw=handle.read(MAX_BYTES+1)
            need(len(raw)<=MAX_BYTES,"BODY_TOO_LARGE")
            return json.loads(raw)
        return collect_pages_exact(request_page,max_pages=MAX_CALLS)
    daily=one("1Day")
    half=one("30Min")
    return daily,half,calls[0]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--one-shot-frozen-20261012",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:selftest();return
    need(args.one_shot_frozen_20261012 and args.out is not None,
         "ONE_SHOT_REQUIRED")
    need(not args.out.resolve().is_relative_to(REPO.resolve()),
         "NO_PUBLIC_RAW_ARTIFACT")
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    need(git_blob(ROOT/"canonical_current_master_manifest.json")==MASTER_SHA
         and git_blob(ROOT/"canonical_current_price_dv30.json")==PRICE_SHA,
         "SOURCE_SHA_DRIFT")
    need(master.get("asof_et")==price.get("asof_et")==ASOF,
         "SOURCE_ASOF_DRIFT")
    scope=price.get("unknown_symbols")
    need(type(scope) is list and len(scope)==540 and
         all(sym in scope for sym in SYMBOLS),"CURRENT_UNKNOWN540_SCOPE")
    need(personal_shadow_access(os.environ),"PERSONAL_RESEARCH_ONLY")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    need(key and secret,"NO_SIP_KEYS")
    import pandas_market_calendars as mcal
    dates=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date=ASOF)]
    need(len(dates)==30,"CALENDAR_DATE_MISMATCH")
    a,b,calls=fetch((key,secret))
    report=measure(a,b,dates)
    report["api_calls"]=calls
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_4SYM_30M_BUCKETS="+json.dumps(report["counts"],sort_keys=True))
    print("XRAY_4SYM_30M_PRIMARY=0_MC=0_R92=0")

if __name__=="__main__":main()
