#!/usr/bin/env python3
"""Independent fail-closed calendar authority for legacy Alpaca shadow workflow.

If main Alpaca code is invoked from another path this gate does NOT protect it;
attach this preflight to each workflow before making an HTTP request.
Never produces or promotes a market signal.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from history_transport_cache_guard import official_completed_sessions

ROOT=Path(__file__).resolve().parent

def validate(asof,claimed):
    if not isinstance(asof,str) or not isinstance(claimed,list):
        return "CALENDAR_INPUT_INVALID"
    try:
        day=dt.date.fromisoformat(asof)
        assert day.isoformat()==asof
        expected=sorted(official_completed_sessions(asof))[-30:]
    except (ValueError,TypeError,AssertionError,KeyError):
        return "OFFICIAL_CALENDAR_UNVERIFIED"
    if len(expected)!=30 or len(set(expected))!=30 or expected[-1]!=asof:
        return "ASOF_NOT_COMPLETED_NASDAQ_SESSION"
    if claimed!=expected:
        return "CLAIMED_30_NOT_OFFICIAL_COMPLETE_SESSIONS"
    return "EXACT_OFFICIAL_NASDAQ_LAST_30"

def selftest():
    asof="2026-10-08"
    dates=sorted(official_completed_sessions(asof))[-31:]
    assert len(dates)==31
    assert validate(asof,dates[-30:])=="EXACT_OFFICIAL_NASDAQ_LAST_30"
    assert validate(asof,[dates[0],*dates[-29:]])=="CLAIMED_30_NOT_OFFICIAL_COMPLETE_SESSIONS"
    assert validate(asof,list(reversed(dates[-30:])))=="CLAIMED_30_NOT_OFFICIAL_COMPLETE_SESSIONS"
    assert validate(asof,dates[-30:-1])=="CLAIMED_30_NOT_OFFICIAL_COMPLETE_SESSIONS"
    assert validate("2026-10-10",dates[-30:])=="ASOF_NOT_COMPLETED_NASDAQ_SESSION"
    assert validate("not-date",dates[-30:])=="OFFICIAL_CALENDAR_UNVERIFIED"
    assert validate(asof,[])=="CLAIMED_30_NOT_OFFICIAL_COMPLETE_SESSIONS"
    print("XRAY_ALPACA_OFFICIAL_30_WORKFLOW_PREFLIGHT_SELFTEST=PASS_POSITIVE_6_NEGATIVE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text(encoding="utf-8"))
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text(encoding="utf-8"))
    asof=price.get("asof_et")
    status=validate(asof,price.get("expected30"))
    if asof!=master.get("asof_et") or price.get("unknown_never_pass") is not True:
        status="SOURCE_ASOF_OR_UNKNOWN_SAFETY_INVALID"
    print("XRAY_ALPACA_OFFICIAL_30_WORKFLOW_PREFLIGHT="+status)
    if status!="EXACT_OFFICIAL_NASDAQ_LAST_30":
        raise SystemExit(2)

if __name__=="__main__":
    main()
