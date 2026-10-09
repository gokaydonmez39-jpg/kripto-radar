#!/usr/bin/env python3
"""Strict calendar dispatch for existing Alpaca research-only shadow reader.

Uses the legacy transport but refuses any caller-supplied 30-day sequence
that differs from the official completed NASDAQ session calendar.
Never elevates SHADOW to canonical HISTORY, MC, R92 or execution.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

import alpaca_free_sip_shadow_guard as legacy
from alpaca_official_30_workflow_preflight import validate
from history_transport_cache_guard import official_completed_sessions

_ORIGINAL_EVALUATE = legacy.evaluate_daily
ROOT=Path(__file__).resolve().parent

def evaluate_daily_strict(rows, expected30, asof, now):
    calendar_status=validate(asof,expected30)
    if calendar_status!="EXACT_OFFICIAL_NASDAQ_LAST_30":
        return "UNKNOWN","OFFICIAL_NASDAQ_30_CALENDAR_REQUIRED",0
    return _ORIGINAL_EVALUATE(rows,expected30,asof,now)

def selftest():
    asof="2026-10-08"
    days=sorted(official_completed_sessions(asof))
    good30=days[-30:]
    now=dt.datetime(2026,10,9,14,tzinfo=dt.timezone.utc)
    def sample(date):
        stamped=dt.datetime.combine(dt.date.fromisoformat(date),dt.time(0),legacy.EST)
        return {"t":stamped.astimezone(dt.timezone.utc).isoformat(),
                "o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":1000}
    rows=[sample(d) for d in good30]
    positive=evaluate_daily_strict(rows,good30,asof,now)
    assert positive[0]=="SHADOW_30_BARS_OBSERVED",positive
    fake=[days[-31],*days[-29:]]
    assert len(fake)==30 and fake[-1]==asof and fake!=good30
    rejected=evaluate_daily_strict([sample(d) for d in fake],fake,asof,now)
    assert rejected==("UNKNOWN","OFFICIAL_NASDAQ_30_CALENDAR_REQUIRED",0),rejected
    assert evaluate_daily_strict(rows,list(reversed(good30)),asof,now)[0]=="UNKNOWN"
    assert evaluate_daily_strict(rows,good30[:-1],asof,now)[0]=="UNKNOWN"
    assert evaluate_daily_strict(rows,good30,"2026-10-10",now)[0]=="UNKNOWN"
    assert evaluate_daily_strict(rows[:-1],good30,asof,now)[0]=="UNKNOWN"
    assert positive[0]!="PASS_HISTORY"
    print("XRAY_ALPACA_STRICT_DAILY_SHADOW_V2_SELFTEST=PASS_POSITIVE_5_NEGATIVE_NO_ALPHA")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    # Defense in depth: reject the canonical source scope before invoking
    # historical SIP transport. No vendor raw bars are written to output.
    root,price,syms,days,*_ = legacy.load_scope()
    if validate(price["asof_et"],days)!="EXACT_OFFICIAL_NASDAQ_LAST_30":
        raise SystemExit("XRAY_ALPACA_STRICT_SOURCE_CALENDAR=BLOCKED")
    legacy.evaluate_daily=evaluate_daily_strict
    try:
        result=legacy.run()
    finally:
        legacy.evaluate_daily=_ORIGINAL_EVALUATE
    assert result["primary_mc_authority"] is False
    assert result["c417_price_pass_promoted"] is False
    assert result["candidate_created"] is False
    assert result["vendor_raw_bars_persisted"] is False
    assert result["execution"]=="NONE" and result["real_money"]=="NO-GO"
    if args.output:
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_ALPACA_STRICT_CALENDAR=PASS_SOURCE_DIAGNOSTIC_ONLY")
    print("XRAY_ALPACA_STRICT_SOURCE_STATUS="+result["status"])

if __name__=="__main__":
    main()
