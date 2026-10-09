#!/usr/bin/env python3
"""Fail-closed entrypoint for Alpaca root-UNKNOWN research source.

Every row is evaluated under the independent exact official NASDAQ last-30
session requirement. This wrapper has no PRIMARY, AL or trading authority.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

import alpaca_root_unknown_rescue_shadow as legacy
import alpaca_strict_daily_shadow_v2 as strict
from alpaca_official_30_workflow_preflight import validate
from history_transport_cache_guard import official_completed_sessions

ROOT=Path(__file__).resolve().parent

def selftest():
    asof="2026-10-08"
    all_dates=sorted(official_completed_sessions(asof))
    canonical=all_dates[-30:]
    fake=[all_dates[-31],*canonical[1:]]
    now=dt.datetime(2026,10,9,14,tzinfo=dt.timezone.utc)
    def mk(day):
        t=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0),strict.legacy.EST)
        return {"t":t.astimezone(dt.timezone.utc).isoformat(),
                "o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":1000}
    original=legacy.sip.evaluate_daily
    legacy.sip.evaluate_daily=strict.evaluate_daily_strict
    try:
        neg=legacy.study(["UNIT"],asof,fake,{"UNIT":[mk(x) for x in fake]},now)
        assert neg=={"UNKNOWN_OFFICIAL_NASDAQ_30_CALENDAR_REQUIRED":1},neg
        positive=legacy.study(["UNIT"],asof,canonical,{"UNIT":[mk(x) for x in canonical]},now)
        assert positive=={"UNKNOWN_LT260_OR_52_WEEKS":1},positive
    finally:
        legacy.sip.evaluate_daily=original
    print("XRAY_ALPACA_ROOT_STRICT_DISPATCH_V2=PASS_FAKE_CALENDAR_BLOCKED_REAL_CALENDAR_SHORT_UNKNOWN")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--offset",type=int,default=0)
    ap.add_argument("--limit",type=int,default=12)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    root_state=json.loads((ROOT/"sina_state.json").read_text(encoding="utf-8"))
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text(encoding="utf-8"))
    if (root_state.get("asof_et")!=price.get("asof_et")
            or validate(price.get("asof_et"),price.get("expected30"))!="EXACT_OFFICIAL_NASDAQ_LAST_30"):
        raise SystemExit("XRAY_ALPACA_ROOT_STRICT_CALENDAR=BLOCKED")
    original=legacy.sip.evaluate_daily
    legacy.sip.evaluate_daily=strict.evaluate_daily_strict
    try:
        result=legacy.run(args.offset,args.limit)
    finally:
        legacy.sip.evaluate_daily=original
    assert result["primary_mc_authority"] is False
    assert result["canonical_history_modified"] is False
    assert result["candidate_created"] is False
    assert result["vendor_raw_bars_persisted"] is False
    assert result["execution"]=="NONE" and result["real_money"]=="NO-GO"
    if args.output:
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_ALPACA_ROOT_STRICT_DISPATCH_STATUS="+result["status"])

if __name__=="__main__":
    main()
