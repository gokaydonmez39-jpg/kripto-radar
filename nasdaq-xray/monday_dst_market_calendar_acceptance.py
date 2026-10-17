#!/usr/bin/env python3
"""Independent Nasdaq Monday, DST, holiday and early-close acceptance checks.

READ-ONLY: no vendor quotes/bars, paid keys, writes, notifications or orders.
Official session calendar controls all decisions, never UTC weekday alone.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from root_weekend_quota_guard import permit_compute
from source_epoch_freshness_guard import last_complete_session
from preopen_live_release_gate import official_window

UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
TR=ZoneInfo("Europe/Istanbul")
CAL=mcal.get_calendar("NASDAQ")


def utc(y,m,d,h,minute=0):
    return dt.datetime(y,m,d,h,minute,tzinfo=UTC)


def market(date):
    schedule=CAL.schedule(start_date=date,end_date=date)
    if schedule.empty:
        return None
    assert len(schedule)==1 and schedule.index[0].date().isoformat()==date
    row=schedule.iloc[0]
    return tuple(row[name].to_pydatetime().astimezone(UTC)
                 for name in ("market_open","market_close"))


def ensure_day(date, open_utc, close_utc, open_tr, close_tr):
    window=market(date)
    assert window is not None,("WRONG_CLOSED_SESSION",date)
    op,cl=window
    assert (op.strftime("%H:%M"),cl.strftime("%H:%M"))==(open_utc,close_utc),(
        "UTC_OPEN_CLOSE_WRONG",date,op,cl)
    assert (op.astimezone(TR).strftime("%Y-%m-%d %H:%M"),
            cl.astimezone(TR).strftime("%Y-%m-%d %H:%M"))==(
        date+" "+open_tr, (cl.astimezone(TR).date().isoformat())+" "+close_tr),(
        "TURKEY_LOCAL_SESSION_WRONG",date,op,cl)
    assert op.astimezone(NY).strftime("%H:%M")=="09:30"
    assert cl.astimezone(NY).strftime("%H:%M") in {"16:00","13:00"}
    # A close is NOT a data-ready decision. Last completed session only
    # advances after the required 30-minute end-of-session safe buffer.
    assert last_complete_session(cl-dt.timedelta(minutes=1))!=date,(
        "PREMATURE_ASOF_BEFORE_CLOSE",date)
    assert last_complete_session(cl+dt.timedelta(minutes=29))!=date,(
        "PREMATURE_ASOF_BEFORE_BUFFER",date)
    assert last_complete_session(cl+dt.timedelta(minutes=30))==date,(
        "MISSING_ASOF_AFTER_OFFICIAL_BUFFER",date)
    return op,cl


def selftest():
    # Monday 19 October is not a Nasdaq holiday. The following Saturday/
    # Sunday are closed. No UTC-day-based early Monday kickoff.
    monday=ensure_day("2026-10-19","13:30","20:00","16:30","23:00")
    assert market("2026-10-17") is None and market("2026-10-18") is None
    assert last_complete_session(utc(2026,10,19,19,59))=="2026-10-16"
    assert last_complete_session(utc(2026,10,19,20,29))=="2026-10-16"
    assert last_complete_session(utc(2026,10,19,20,30))=="2026-10-19"
    assert not permit_compute(utc(2026,10,19,3),"schedule") # Sunday 23 EDT
    assert permit_compute(utc(2026,10,19,13),"schedule")
    assert official_window(utc(2026,10,19,12,15))["preopen"] is True
    assert official_window(utc(2026,10,19,13,30))["preopen"] is False

    # DST change 1 November 2026. Turkey remains UTC+03 throughout.
    friday=ensure_day("2026-10-30","13:30","20:00","16:30","23:00")
    assert market("2026-11-01") is None
    winter=ensure_day("2026-11-02","14:30","21:00","17:30","00:00")
    assert friday[0].astimezone(NY).utcoffset()==dt.timedelta(hours=-4)
    assert winter[0].astimezone(NY).utcoffset()==dt.timedelta(hours=-5)
    assert friday[0].astimezone(TR).utcoffset()==dt.timedelta(hours=3)
    assert winter[0].astimezone(TR).utcoffset()==dt.timedelta(hours=3)
    assert last_complete_session(utc(2026,11,2,21,29))=="2026-10-30"
    assert last_complete_session(utc(2026,11,2,21,30))=="2026-11-02"
    assert official_window(utc(2026,11,2,13,15))["preopen"] is True

    # Thanksgiving closed; following Friday is an EARLY CLOSE: 13:00 EST.
    assert market("2026-11-26") is None
    assert not permit_compute(utc(2026,11,26,15),"schedule")
    half=ensure_day("2026-11-27","14:30","18:00","17:30","21:00")
    assert last_complete_session(utc(2026,11,27,18,29))=="2026-11-25"
    assert last_complete_session(utc(2026,11,27,18,30))=="2026-11-27"
    assert permit_compute(utc(2026,11,27,15),"schedule")
    assert half[1].astimezone(NY).strftime("%H:%M")=="13:00"

    # Christmas Eve also closes early. Christmas Day closed.
    ensure_day("2026-12-24","14:30","18:00","17:30","21:00")
    assert market("2026-12-25") is None
    assert not permit_compute(utc(2026,12,25,16),"schedule")
    assert market("2027-01-01") is None

    # Spring DST reset March 14, 2027. Next open shifts one hour earlier
    # in Istanbul, with New York remaining fixed at 09:30.
    ensure_day("2027-03-12","14:30","21:00","17:30","00:00")
    assert market("2027-03-14") is None
    ensure_day("2027-03-15","13:30","20:00","16:30","23:00")
    assert not permit_compute(utc(2027,3,14,16),"schedule")
    assert permit_compute(utc(2027,3,15,16),"schedule")

    # Sunday, holiday and naive clock cannot pass pre-open readiness.
    assert official_window(utc(2026,11,26,13,15))["preopen"] is False
    assert official_window(utc(2026,10,18,12,15))["preopen"] is False
    try:
        official_window(dt.datetime(2026,10,19,12,15))
    except ValueError:
        pass
    else:
        raise AssertionError("NAIVE_CLOCK_FALSE_PREOPEN")
    print("XRAY_NASDAQ_MONDAY_19OCT_DST_EARLY_CLOSE_CALENDAR=PASS_2026_2027")
    print("XRAY_CALENDAR_UNVERIFIED_AL_OR_ORDER=NONE")


if __name__=="__main__":
    selftest()
