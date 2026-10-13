#!/usr/bin/env python3
"""Frozen 2026-10-12 SIP daily-volume UPPER-BOUND research, fail-only.

A daily SIP bar's eligible volume can contain extended-hours/odd-lot trades
that are not eligible in the exact RTH minute-window volume. Under the Alpaca
documented per-condition volume update rules, the daily aggregate is an
upper bound for the subset of RTH minute-bar eligible trade volume.
No daily-bar observation may create C4.17 PRIMARY PASS/FAIL, R92, or orders.
Only redacted counts and exact hash commitments may leave the runner.

Official source: https://docs.alpaca.markets/us/docs/market-data-faq
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import urllib.error
from decimal import Decimal
from pathlib import Path

from alpaca_540_personal_daily_sip_coverage import (
    ROOT, REPO, UTC, CHUNK, MAX_CALLS, classify, exact_source,
    fetch_live, sha_lines, collect_pages,
)
from alpaca_sip_exact30_backup_probe import personal_shadow_access

ASOF = "2026-10-12"
SOURCE_MASTER_SHA = "fb64a44b79ced9dcda390f5661b796ee13a60f63"
SOURCE_PRICE_SHA = "787e1222fe140ae141b51e98bbbaaa9034ead377"
LIMIT = Decimal("50000000")
SCHEMA = "XRAY_PERSONAL_SIP_EXACT30_DAILY_UPPER_BOUND_FAIL_ONLY_SHADOW_V1"
VALID = "DAILY_SIP_30_VALID_NOT_RTH"
FAIL = "BELOW_50M_DAILY_UPPER_BOUND_SHADOW"
UNRESOLVED = "AT_OR_ABOVE_50M_RTH_UNVERIFIED_SHADOW"

def need(ok, code):
    if not ok:
        raise ValueError("XRAY_SIP_UPPER_" + code)

def git_blob(path):
    return subprocess.check_output(["git", "hash-object", str(path)],
                                   text=True).strip()

def frozen_source(master, price, *, master_sha, price_sha):
    need(master_sha == SOURCE_MASTER_SHA, "MASTER_BLOB_DRIFT")
    need(price_sha == SOURCE_PRICE_SHA, "PRICE_BLOB_DRIFT")
    # A HISTORICAL REPLAY clock, never passed off as the live runtime clock.
    frozen = dt.datetime(2026, 10, 12, 23, 0, tzinfo=UTC)
    scope, days = exact_source(master, price, frozen)
    need(master.get("asof_et") == price.get("asof_et") == ASOF,
         "ASOF_CHANGED")
    need(len(scope) == 540 and len(days) == 30 and days[-1] == ASOF,
         "FROZEN_SCOPE_INVALID")
    return scope, days

def upper_bound(rows, dates):
    """30-session median of CLOSE * DAILY SIP VOLUME, never RTH PASS."""
    need(classify(rows, dates) == VALID, "EXACT30_NOT_INTACT")
    by_date = {}
    for r in rows:
        stamp = dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
        from alpaca_540_personal_daily_sip_coverage import NY
        day = stamp.astimezone(NY).date().isoformat()
        close = Decimal(str(r["c"]))
        vol = r["v"]
        need(close.is_finite() and close > 0 and type(vol) is int
             and vol > 0 and day not in by_date, "BAD_INPUT")
        by_date[day] = close * vol
    need(len(by_date) == 30 and set(by_date) == set(dates),
         "MISSING_SESSION")
    values = sorted(by_date[day] for day in dates)
    median = (values[14] + values[15]) / Decimal(2)
    return FAIL if median < LIMIT else UNRESOLVED

def measure(scope, dates, fetch):
    calls = [0]
    attempted = 0
    valid = 0
    bucket = {FAIL: 0, UNRESOLVED: 0}
    fails = []
    malformed = []
    failure_reason = None
    for idx in range(0, len(scope), CHUNK):
        symbols = scope[idx:idx+CHUNK]
        def getpage(token):
            if calls[0] >= MAX_CALLS:
                raise RuntimeError("GLOBAL_CALL_LIMIT")
            calls[0] += 1
            return fetch(symbols, dates, token)
        try:
            bars = collect_pages(symbols, getpage, max_pages=3)
        except (RuntimeError, ValueError, TimeoutError,
                OSError, urllib.error.HTTPError, urllib.error.URLError):
            failure_reason = "TRANSPORT_OR_PAGINATION_INCOMPLETE"
            break
        for sym in symbols:
            rows = bars.get(sym)
            if classify(rows, dates) != VALID:
                malformed.append(sym)
                continue
            valid += 1
            state = upper_bound(rows, dates)
            bucket[state] += 1
            if state == FAIL:
                fails.append(sym)
        attempted += len(symbols)
    need(sum(bucket.values()) == valid, "CLASSIFICATION_COUNT_MISMATCH")
    need(valid + len(malformed) == attempted, "SCOPE_ACCOUNTING")
    return {
        "requested": len(scope), "attempted": attempted,
        "remaining": len(scope)-attempted, "api_calls": calls[0],
        "daily_sip_30_valid": valid, "incomplete_or_integrity": len(malformed),
        "daily_upper_bound_shadow": bucket,
        "daily_upper_bound_fail_only_symbols_sha256": sha_lines(sorted(fails)),
        "unresolved_daily_bar_symbols_sha256": sha_lines(sorted(malformed)),
        "exact30_session_sha256": sha_lines(dates),
        "exact540_symbol_set_sha256": sha_lines(sorted(scope)),
        "coverage_complete": attempted == len(scope),
        "failure_reason": failure_reason,
        "primary_price_count_created": 0,
        "primary_dv30_fail_count_created": 0,
        "primary_dv30_pass_count_created": 0,
        "primary_mc_count_created": 0,
        "r92_created": False,
        "daily_sip_volume_is_rth": False,
        "daily_upper_bound_is_primary_authority": False,
        "volume_lineage_independently_attested": False,
        "personal_noncommercial_research_only": True,
        "raw_prices_or_volumes_persisted": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
    }

def selftest():
    from alpaca_540_personal_daily_sip_coverage import NY
    import pandas_market_calendars as mcal
    from copy import deepcopy
    days=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31", end_date=ASOF)]
    need(len(days)==30, "FIXTURE_DATES")
    def build():
        ans=[]
        for date in days:
            instant=dt.datetime.combine(dt.date.fromisoformat(date),
                                         dt.time.min, NY).astimezone(UTC)
            ans.append({"t":instant.isoformat().replace("+00:00","Z"),
                        "o":10., "h":11., "l":9., "c":10., "v":5_000_000})
        return ans
    eq=build()
    need(upper_bound(eq,days)==UNRESOLVED, "EQ_NOT_A_FAIL")
    low=deepcopy(eq)
    for row in low:row["v"]=4_999_999
    need(upper_bound(low,days)==FAIL, "BELOW_BOUND_MUST_FAIL_ONLY")
    high=deepcopy(eq)
    for row in high:row["v"]=5_000_001
    need(upper_bound(high,days)==UNRESOLVED, "HIGH_NEVER_PASS")
    even=deepcopy(eq)
    for row in even[:15]:row["v"]=4_900_000
    for row in even[15:]:row["v"]=5_100_000
    need(upper_bound(even,days)==UNRESOLVED, "EVEN_MEDIAN_EQ")
    evenlow=deepcopy(eq)
    for row in evenlow[:16]:row["v"]=4_900_000
    for row in evenlow[16:]:row["v"]=5_100_000
    need(upper_bound(evenlow,days)==FAIL,"EVEN_MEDIAN_LOW")
    negative=[
        lambda q: q.pop(),
        lambda q: q[0].update(v=4.9),
        lambda q: q[0].update(v=True),
        lambda q: q[0].update(v=-1),
        lambda q: q[0].update(c=float("nan")),
        lambda q: q[0].update(t=q[1]["t"]),
    ]
    for mutation in negative:
        row=deepcopy(eq);mutation(row)
        try:upper_bound(row,days)
        except (ValueError,TypeError,KeyError):pass
        else:raise AssertionError("BAD_INPUT_ACCEPTED")
    calls=[]
    def fake(symbols,dates,token):
        calls.append((symbols,token))
        return {"bars":{symbol:deepcopy(low if symbol=="AAPL" else high)
                        for symbol in symbols},"next_page_token":None}
    result=measure(["AAPL","NVDA"],days,fake)
    need(result["daily_upper_bound_shadow"]=={FAIL:1,UNRESOLVED:1}
         and result["api_calls"]==1 and result["attempted"]==2
         and result["primary_dv30_pass_count_created"]==0
         and result["primary_dv30_fail_count_created"]==0,
         "MIXED_FAIL_ONLY_MOCK")
    broken=measure(["AAPL"],days,lambda a,b,c:{
        "bars":{},"next_page_token":"never_ending"})
    need(not broken["coverage_complete"] and broken["api_calls"]<=MAX_CALLS,
         "PAGINATION_FAIL_CLOSED")
    print("XRAY_SIP_DV30_UPPERBOUND_SELFTEST=PASS_6_BAD_5_BOUNDARY_2_TRANSPORT_NO_HTTP")

def run(out_path):
    need(not out_path.resolve().is_relative_to(REPO.resolve()),
         "PUBLIC_REPO_OUTPUT_FORBIDDEN")
    master_path=ROOT/"canonical_current_master_manifest.json"
    price_path=ROOT/"canonical_current_price_dv30.json"
    master=json.loads(master_path.read_text())
    price=json.loads(price_path.read_text())
    scope,days=frozen_source(master,price,master_sha=git_blob(master_path),
                             price_sha=git_blob(price_path))
    need(personal_shadow_access(os.environ), "PERSONAL_OPT_IN_REQUIRED")
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    need(bool(key and secret),"CREDENTIALS_REQUIRED")
    result=measure(scope,days,fetch_live((key,secret)))
    result.update({"schema":SCHEMA,"asof_et":ASOF,
                   "research_frozen_historical_not_current":True,
                   "source_master_blob_sha":SOURCE_MASTER_SHA,
                   "source_price_blob_sha":SOURCE_PRICE_SHA})
    out_path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_SIP_DV30_UPPERBOUND_STATE="+
          ("SHADOW_MEASURED" if result["coverage_complete"]
           else "BLOCKED_SCOPE_PARTIAL"))
    print("XRAY_SIP_DV30_UPPERBOUND_BUCKETS="+
          json.dumps(result["daily_upper_bound_shadow"],sort_keys=True))
    print("XRAY_SIP_DV30_PRIMARY_FAIL=0_PASS=0_MC=0_R92=0")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--frozen-research-20261012",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.frozen_research_20261012 or args.out is None:
        p.error("Historical frozen research mode and --out are required")
    run(args.out)

if __name__=="__main__":
    main()
