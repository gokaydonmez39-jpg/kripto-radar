#!/usr/bin/env python3
"""Personal NASDAQ EOD research session validation V2, read-only and no AL.

The V1 research engine remains immutable: prior evidence pins its exact Git SHA.
V2 adds a *real* XNAS session/weekly-close + latest-completed-epoch gate, which
cannot disappear under python -O. C4.17 and R92 production authority unchanged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Mapping

import pandas_market_calendars as mcal
import personal_research_primary_engine_v1 as old
from source_epoch_freshness_guard import last_complete_session

SAFE = dict(old.SAFETY)
SOURCE = "PERSONAL_OFFICIAL_XNAS_EOD_LOCAL_TECHNICAL_ONLY_NOT_C417_RELEASE"


def _iso_date(text):
    if type(text) is not str:
        raise ValueError("DATE_TYPE")
    parsed = dt.date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError("DATE_NOT_CANONICAL")
    return parsed


def official_sessions(asof, n, now_utc):
    """Last n *actual* XNAS sessions, only for the latest completed RTH epoch."""
    if type(n) is not int or n not in (30, 260):
        raise ValueError("WRONG_OFFICIAL_WINDOW")
    day = _iso_date(asof)
    if (not isinstance(now_utc, dt.datetime) or now_utc.tzinfo is None
            or now_utc.utcoffset() != dt.timedelta(0)):
        raise ValueError("NOW_MUST_BE_UTC_AWARE")
    if last_complete_session(now_utc) != asof:
        raise ValueError("STALE_OR_PREMATURE_XNAS_EPOCH")
    cal = mcal.get_calendar("NASDAQ")
    lookback = (day - dt.timedelta(days=560)).isoformat()
    sessions = [t.date().isoformat() for t in cal.valid_days(
        start_date=lookback, end_date=asof)]
    if len(sessions) < n or sessions[-1] != asof:
        raise ValueError("NOT_N_XNAS_COMPLETED_SESSIONS")
    return sessions[-n:]


def completed_weekly_closes(asof, now_utc):
    """Exactly 52 completed XNAS week-end sessions (no unfinished week)."""
    _ = official_sessions(asof, 260, now_utc)
    d = _iso_date(asof)
    cal = mcal.get_calendar("NASDAQ")
    # Include the following week to recognize an unfinished current week.
    all_days = [t.date() for t in cal.valid_days(
        start_date=(d - dt.timedelta(days=560)).isoformat(),
        end_date=(d + dt.timedelta(days=8)).isoformat())]
    week_ends = {}
    for x in all_days:
        week_ends[x.isocalendar()[:2]] = x
    closes = sorted(x.isoformat() for x in week_ends.values() if x <= d)
    if len(closes) < 52:
        raise ValueError("NOT_52_OFFICIAL_WEEKS")
    return closes[-52:]


def price_dv30(asof, purported30, daily, close_proofs, rth_proofs,
               correction_proof, identity_proof, *, now_utc):
    try:
        expected = official_sessions(asof, 30, now_utc)
    except (TypeError, ValueError, KeyError, OverflowError):
        return {"status": "UNKNOWN_XNAS_SESSION_OR_EPOCH"}
    if type(purported30) is not list or purported30 != expected:
        return {"status": "UNKNOWN_EXACT30_XNAS_CALENDAR_MISMATCH"}
    result = old.assess_price_dv30(asof, expected, daily, close_proofs,
                                    rth_proofs, correction_proof, identity_proof)
    # A positive technical measurement is NOT a canonical PRICE pass or R92.
    if result.get("status") == "TECHNICAL_PRIMARY_PERSONAL_PRICE_DV30_NOT_RELEASE":
        result = dict(result)
        result["source_class"] = SOURCE
        result["canonical_promotion"] = False
        result["r92_authority"] = False
    return result


def history260_52(asof, purported260, daily, purported_weekly52,
                  identity_pit_verified=False, corporate_actions_verified=False,
                  *, now_utc):
    try:
        expected = official_sessions(asof, 260, now_utc)
        weekly = completed_weekly_closes(asof, now_utc)
    except (TypeError, ValueError, KeyError, OverflowError):
        return "UNKNOWN_XNAS_SESSION_OR_EPOCH"
    if type(purported260) is not list or purported260 != expected:
        return "UNKNOWN_EXACT260_XNAS_CALENDAR_MISMATCH"
    if type(purported_weekly52) is not list or purported_weekly52 != weekly:
        return "UNKNOWN_EXACT52_COMPLETED_WEEK_MISMATCH"
    return old.assess_history(asof, expected, daily, weekly,
                              identity_pit_verified, corporate_actions_verified)


def selftest():
    def must(ok, code):
        if not ok:
            raise RuntimeError("XRAY_PERSONAL_OFFICIAL_V2_" + code)
    asof = "2026-10-16"
    during_monday = dt.datetime(2026, 10, 19, 16, 0, tzinfo=dt.timezone.utc)
    monday_settled = dt.datetime(2026, 10, 19, 20, 30, tzinfo=dt.timezone.utc)
    d30 = official_sessions(asof, 30, during_monday)
    d260 = official_sessions(asof, 260, during_monday)
    w52 = completed_weekly_closes(asof, during_monday)
    must(len(d30) == 30 and d30 == d260[-30:], "VALID_DAILY_WINDOWS")
    must(len(d260) == 260 and d260[0] == "2025-10-06", "XNAS_260")
    must(len(w52) == 52 and w52[-1] == asof
         and set(w52).issubset(set(d260)), "VALID_FINISHED_WEEK_ENDS")
    bar = {"o":100,"h":101,"l":99,"c":100,"v":500000,"rth_v":500000}
    bars = {d:dict(bar) for d in d260}
    proven = {d:True for d in d30}
    def price(dates, now=during_monday, data=bars):
        return price_dv30(asof, dates, data, proven, proven, True, True,
                          now_utc=now)
    yes = price(d30)
    must(yes["status"] == "TECHNICAL_PRIMARY_PERSONAL_PRICE_DV30_NOT_RELEASE"
         and yes["dv30_usd"] == 50000000
         and yes["canonical_promotion"] is False
         and yes["r92_authority"] is False, "EXACT30_RESEARCH_BOUNDARY_NOT_AL")
    calendar_days = [(dt.date(2026,9,17) + dt.timedelta(days=i)).isoformat()
                     for i in range(30)]
    fake = {d:dict(bar) for d in calendar_days}
    false_weekend = price_dv30(asof, calendar_days, fake,
        {d:True for d in calendar_days}, {d:True for d in calendar_days},
        True,True,now_utc=during_monday)
    must(false_weekend["status"] == "UNKNOWN_EXACT30_XNAS_CALENDAR_MISMATCH",
         "CALENDAR_DAY_FALSE_30")
    must(price(d30[:-1])["status"] == "UNKNOWN_EXACT30_XNAS_CALENDAR_MISMATCH",
         "29_SESSIONS")
    must(price(d30[::-1])["status"] == "UNKNOWN_EXACT30_XNAS_CALENDAR_MISMATCH",
         "OUT_OF_ORDER")
    must(price(d30, now=monday_settled)["status"] ==
         "UNKNOWN_XNAS_SESSION_OR_EPOCH", "STALE_AFTER_MONDAY_CLOSE")
    must(price(d30, now=dt.datetime(2026,10,19,16))["status"] ==
         "UNKNOWN_XNAS_SESSION_OR_EPOCH", "NAIVE_CLOCK")
    bad = dict(bars)
    bad.pop(d30[11])
    must(price(d30,data=bad)["status"] ==
         "UNKNOWN_DV30_BAD_OR_MISSING_SESSION", "MISSING_REAL_SESSION")
    must(price_dv30(asof, d30, bars, {}, proven, True, True,
                    now_utc=during_monday)["status"] ==
         "UNKNOWN_RTH_SETTLEMENT_OR_VOLUME", "NO_TRUE_VOLUME_PROOF")
    must(history260_52(asof,d260,bars,w52,True,True,
                       now_utc=during_monday) ==
         "TECHNICAL_PRIMARY_PERSONAL_HISTORY_NOT_RELEASE", "EXACT_HISTORY")
    must(history260_52(asof,d260,bars,d260[::5],True,True,
                       now_utc=during_monday) ==
         "UNKNOWN_EXACT52_COMPLETED_WEEK_MISMATCH", "FALSE_WEEKLY_52")
    must(history260_52(asof,d260[:-1],bars,w52,True,True,
                       now_utc=during_monday) ==
         "UNKNOWN_EXACT260_XNAS_CALENDAR_MISMATCH", "259_SESSIONS")
    must(history260_52(asof,d260,bars,w52,True,True,
                       now_utc=monday_settled) ==
         "UNKNOWN_XNAS_SESSION_OR_EPOCH", "STALE_HISTORY")
    must(SAFE["execution"] == "NONE" and SAFE["real_money"] == "NO-GO"
         and SAFE["unknown_never_pass"] is True
         and not SAFE["r92_created"] and not SAFE["canonical_primary_created"],
         "NO_RELEASE_OR_EXECUTION")
    print(json.dumps({"schema":"XRAY_PERSONAL_XNAS_CALENDAR_GUARD_V2",
          "result":"PASS_12_ADVERSARIAL_GATES",
          "asof_et":asof,"exact30":len(d30),"exact260":len(d260),
          "completed_weekly52":len(w52),"optimized_python_safe":True,
          "canonical_primary_created":False,"r92_created":False,
          "execution":"NONE","real_money":"NO-GO"},sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest: selftest()
    else: parser.error("Offline selftest only. No vendor I/O and no production promotion.")
