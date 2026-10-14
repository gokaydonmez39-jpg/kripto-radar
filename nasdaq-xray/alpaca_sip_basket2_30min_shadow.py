#!/usr/bin/env python3
"""Four NEW symbols, same frozen Nasdaq-30-session SHADOW measurement, no PRIMARY.
Reuses pinned and already-green original 4-symbol methodology; does not rewrite it.
Historical research only. Does not store bars, issue trades, or create R92.
"""
from __future__ import annotations
import copy
import hashlib
import json
import sys
from pathlib import Path

import alpaca_sip_4symbol_30min_rth_shadow as engine

COHORT=("AMZN","GOOGL","META","TSLA")
OLD=("AAPL","NVDA","MSFT","AAON")
ENGINE_GIT_BLOB="527936d2eb06c9d92c90364e9391974e0c3085eb"
SCHEMA="XRAY_EXACT30_FROZEN_SIP_BASKET2_4SYM_SHADOW_V1"

def need(condition, code):
    if not condition:
        raise ValueError("XRAY_BASKET2_"+code)

def frozen_cohort_matches(price):
    if not isinstance(price,dict):
        return False
    unknown=price.get("unknown_symbols")
    return bool(
        price.get("asof_et")==engine.ASOF
        and type(unknown) is list and len(unknown)==540
        and len(set(unknown))==540
        and set(COHORT).issubset(unknown)
    )

def activate(*, require_frozen_sources=True):
    need(engine.git_blob(Path(engine.__file__))==ENGINE_GIT_BLOB,
         "BASE_ENGINE_SOURCE_CHANGED")
    need(len(COHORT)==len(set(COHORT))==4 and set(COHORT).isdisjoint(OLD),
         "BASKET_COLLISION")
    if require_frozen_sources:
        # Only the one-shot vendor probe needs immutable 12-Oct source proof.
        # Offline regression fixtures must never depend on today's PRICE epoch.
        price_path=engine.ROOT/"canonical_current_price_dv30.json"
        price=json.loads(price_path.read_text())
        need(frozen_cohort_matches(price) and
             engine.git_blob(price_path)==engine.PRICE_SHA,
             "COHORT_NOT_FROZEN_PRICE_UNKNOWN")
    engine.SYMBOLS=COHORT
    engine.SCHEMA=SCHEMA

def selftest():
    activate(require_frozen_sources=False)
    # A synthetic fixture exercises admission logic; never used for market data.
    fake=sorted([f"__TEST_{i:04d}" for i in range(536)]+list(COHORT))
    good={"asof_et":engine.ASOF,"unknown_symbols":fake}
    need(frozen_cohort_matches(good),"FROZEN_COHORT_POSITIVE_FIXTURE")
    shifted=copy.deepcopy(good)
    shifted["asof_et"]="2026-10-13"
    need(not frozen_cohort_matches(shifted),"ASOF_DRIFT_ADMITTED")
    truncated=copy.deepcopy(good)
    truncated["unknown_symbols"].pop()
    need(not frozen_cohort_matches(truncated),"TRUNCATED_COHORT_ADMITTED")
    missing=copy.deepcopy(good)
    missing["unknown_symbols"].remove("TSLA")
    missing["unknown_symbols"].append("__OTHER_SYMBOL")
    need(not frozen_cohort_matches(missing),"FOREIGN_COHORT_ADMITTED")
    duplicate=copy.deepcopy(good)
    duplicate["unknown_symbols"][0]=duplicate["unknown_symbols"][1]
    need(not frozen_cohort_matches(duplicate),"DUPLICATE_COHORT_ADMITTED")
    dates=list(engine.official_frozen_exact30())
    daily={sym:[] for sym in COHORT}
    halfhour={sym:[] for sym in COHORT}
    for symbol in COHORT:
        for day in dates:
            start,_,n=engine.session(day)
            need(n==390,"NONFULL_SESSION")
            localmidnight=start.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
            localmidnight=localmidnight.replace(hour=0,minute=0,second=0,microsecond=0)
            daily[symbol].append({"t":localmidnight.isoformat(),"o":10,
                                  "h":11,"l":9,"c":10,"v":9000000})
            for index in range(13):
                at=start+__import__("datetime").timedelta(minutes=30*index)
                halfhour[symbol].append({"t":at.isoformat(),"o":10,
                                         "h":11,"l":9,"c":10,"v":450000})
    result=engine.measure(daily,halfhour,dates)
    need(result["schema"]==SCHEMA and result["symbols_requested"]==4
         and result["counts"]["LOWER_BOUND_GE_50M_SHADOW"]==4
         and set(result["shadow_symbol_statuses"])==set(COHORT),
         "POSITIVE_FIXTURE")
    need(all(result[k] is False for k in (
        "primary_price_pass_created","primary_dv30_pass_created",
        "primary_mc_created","r92_created","automated_non_display_rights_verified")),
         "AUTHORITY_LEAK")
    broken=copy.deepcopy(halfhour)
    broken["TSLA"].pop()
    test=engine.measure(daily,broken,dates)
    need(test["shadow_symbol_statuses"]["TSLA"]==
         "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW" and
         test["counts"]["LOWER_BOUND_GE_50M_SHADOW"]==3,
         "MISSING_BAR_WAS_PROMOTED")
    duplicate=dates.copy()
    duplicate[4]=duplicate[3]
    try:
        engine.measure(daily,halfhour,duplicate)
    except ValueError:
        pass
    else:
        raise AssertionError("DUPLICATE_SESSION_ACCEPTED")
    pages=engine.collect_pages_exact(
        lambda token: {"bars":{"AMZN":[{"t":"a"}],"TSLA":[{"t":"b"}]},
                       "next_page_token":None})
    need(len(pages["AMZN"])==1 and len(pages["TSLA"])==1,
         "PAGINATION_SCOPE")
    print("XRAY_BASKET2_SELFTEST=PASS_EXACT30_BAR_MISSING_NO_PRIMARY_PAGING")

def main():
    if "--selftest" in sys.argv:
        need(sys.argv[1:]==["--selftest"],"BAD_SELFTEST_ARGS")
        selftest()
        return
    activate(require_frozen_sources=True)
    need(sys.argv[1:3]==["--one-shot-frozen-20261012","--out"]
         and len(sys.argv)==4,"EXPLICIT_ONE_SHOT_REQUIRED")
    engine.main()
    out=Path(sys.argv[3])
    report=json.loads(out.read_text())
    need(report["schema"]==SCHEMA and
         set(report["shadow_symbol_statuses"])==set(COHORT) and
         report["symbols_requested"]==4 and
         report["symbols_completed"]==4 and
         2<=report["api_calls"]<=engine.MAX_CALLS and
         all(report[k] is False for k in (
           "primary_price_pass_created","primary_dv30_pass_created",
           "primary_dv30_fail_created","primary_mc_created","r92_created",
           "raw_ohlcv_persisted","automated_non_display_rights_verified")),
         "OUTPUT_INTEGRITY")
    report["cohort"]="BASKET2_FOUR_NEW_SYMBOLS"
    report["candidate_symbols_1min_crosscheck_verified"]=False
    report["current_asof_primary_scope_verified"]=False
    report["reused_first_basket_data"]=False
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_BASKET2_SHADOW=NO_PRIMARY_MC_R92")

if __name__=="__main__":
    main()
