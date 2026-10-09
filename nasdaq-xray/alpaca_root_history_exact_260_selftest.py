#!/usr/bin/env python3
"""Adversarial root HISTORY shadow dates-only test. No real provider data."""
from __future__ import annotations
import datetime as dt
import alpaca_root_unknown_rescue_shadow as rescue
import alpaca_free_sip_shadow_guard as sip
import alpaca_strict_daily_shadow_v2 as strict
from history_transport_cache_guard import official_completed_sessions

ASOF = "2026-10-08"
NOW = dt.datetime(2026,10,9,14,tzinfo=dt.timezone.utc)

def rows(dates):
    result = []
    for day in dates:
        stamp=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0),sip.EST).astimezone(dt.timezone.utc).isoformat()
        result.append({"t":stamp, "o":10., "h":11., "l":9., "c":10.5, "v":1000})
    return result

def main():
    official=sorted(official_completed_sessions(ASOF))
    assert len(official)>=261 and official[-1]==ASOF
    expected30=official[-30:]
    good=rows(official[-260:])
    hole=rows([official[-261],*official[-260:-100],*official[-99:]])
    assert len(good)==len(hole)==260
    passed=rescue.study(["UNIT"],ASOF,expected30,{"UNIT":good},NOW)
    assert passed == {"SHADOW_LATEST_260_OFFICIAL_DATES_52_ISO_WEEKS_NOT_PRIMARY":1},passed
    blocked=rescue.study(["UNIT"],ASOF,expected30,{"UNIT":hole},NOW)
    assert blocked == {"UNKNOWN_LATEST_260_OFFICIAL_SESSIONS_INCOMPLETE":1},blocked
    wrong30=[official[-31],*official[-29:]]
    assert len(wrong30)==30 and wrong30[-1]==ASOF
    # Legacy direct API still lacks the official-date hard gate; the
    # production workflow must call only the guarded v2 dispatcher.
    status,reason,_=strict.evaluate_daily_strict(rows(wrong30),wrong30,ASOF,NOW)
    assert status=="UNKNOWN" and reason=="OFFICIAL_NASDAQ_30_CALENDAR_REQUIRED",(
        "STRICT_GUARDED_SHADOW_ACCEPTED_FABRICATED_CALENDAR",status,reason)
    status,reason,_=strict.evaluate_daily_strict(rows(expected30),expected30,ASOF,NOW)
    assert status=="SHADOW_30_BARS_OBSERVED",("GUARDED_POSITIVE_FAIL",status,reason)
    print("XRAY_ALPACA_SHADOW_EXACT260_AND_STRICT30_DISPATCH_REGRESSION=PASS")

if __name__=="__main__":
    main()
