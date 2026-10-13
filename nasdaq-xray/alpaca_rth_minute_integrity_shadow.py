#!/usr/bin/env python3
"""Fail-closed exact Nasdaq RTH minute-volume integrity validator.

Alpaca 1Day volume includes non-RTH trading. Daily bars may NOT serve as
C4.17 RTH DV30 evidence. Continuous regular-session minute sums alone do
not prove allocation of the closing auction / trade conditions, either.
Offline mock regressions only; no HTTP, credentials or canonical writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
SCHEMA="XRAY_ALPACA_EXACT_RTH_MINUTE_INTEGRITY_SHADOW_V1"

def need(ok, reason):
    if not ok:
        raise ValueError("RTH_MINUTE_"+reason)

def official_window(asof):
    need(isinstance(asof,str), "INVALID_ASOF")
    d=dt.date.fromisoformat(asof)
    need(d.isoformat()==asof, "NONCANONICAL_DATE")
    s=mcal.get_calendar("NASDAQ").schedule(start_date=asof,end_date=asof)
    need(len(s)==1, "NOT_AN_OFFICIAL_NASDAQ_SESSION")
    start=s.iloc[0]["market_open"].to_pydatetime().astimezone(UTC)
    close=s.iloc[0]["market_close"].to_pydatetime().astimezone(UTC)
    need(start<close and start.second==close.second==0, "NONMINUTE_SCHEDULE")
    expected=int((close-start).total_seconds()//60)
    need(expected in (210,390), "UNEXPECTED_SESSION_LENGTH")
    return start,close,expected

def inspect_minutes(asof, rows):
    start,close,expected=official_window(asof)
    need(isinstance(rows,list), "ROWS_NOT_LIST")
    need(len(rows)==expected, "NOT_EVERY_RTH_MINUTE_RECORDED")
    total=0
    for i,row in enumerate(rows):
        need(type(row) is dict, "ROW_NOT_OBJECT")
        raw=row.get("t")
        need(isinstance(raw,str), "TIMESTAMP_MISSING")
        try:
            t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        except ValueError as exc:
            raise ValueError("RTH_MINUTE_INVALID_TIMESTAMP") from exc
        need(t.tzinfo is not None and t.utcoffset() is not None, "NAIVE_TIMESTAMP")
        need(t.astimezone(UTC)==start+dt.timedelta(minutes=i), "GAP_DUPLICATE_OUT_OF_SESSION")
        v=row.get("v")
        need(type(v) is int and v>0, "VOLUME_NOT_POSITIVE_INTEGER")
        total+=v
        need(total<10**16, "VOLUME_SUM_UNBOUNDED")
    # Not C4.17 DV30 authority: 16:00 ET closing-auction classification and
    # conditions/adjustments are separately required even when count==390.
    return {"schema":SCHEMA,"asof_et":asof,"regular_session_minutes_observed":expected,
            "regular_session_minute_volume_sum_research_only":total,
            "continuous_minute_window_exact":True,
            "close_auction_allocation_verified":False,
            "trade_condition_rth_only_proven":False,
            "canonical_dv30_eligible":False,"primary_price_authority":False,
            "alpha_authority":False,"execution":"NONE","real_money":"NO-GO"}

def selftest():
    def mock(asof):
        start,close,count=official_window(asof)
        return [{"t":(start+dt.timedelta(minutes=i)).isoformat().replace("+00:00","Z"),
                 "v":1000} for i in range(count)]
    full=inspect_minutes("2026-10-12",mock("2026-10-12"))
    assert full["regular_session_minutes_observed"]==390
    assert full["regular_session_minute_volume_sum_research_only"]==390000
    short=inspect_minutes("2026-11-27",mock("2026-11-27"))
    assert short["regular_session_minutes_observed"]==210
    assert short["regular_session_minute_volume_sum_research_only"]==210000
    assert all(full[k] is False for k in ("close_auction_allocation_verified",
            "trade_condition_rth_only_proven","canonical_dv30_eligible",
            "primary_price_authority","alpha_authority"))
    import copy
    for mutation in (
        lambda x:x.pop(),
        lambda x:x[0].update(v=1000.5),
        lambda x:x[0].update(v=True),
        lambda x:x[0].update(v=0),
        lambda x:x[0].update(t=x[1]["t"]),
        lambda x:x[0].update(t="2026-10-12T20:00:00Z"),
        lambda x:x[0].update(t="2026-10-12T13:29:00Z"),
        lambda x:x[0].update(t="2026-10-12T13:30:01Z"),
        lambda x:x.reverse(),
    ):
        bad=copy.deepcopy(mock("2026-10-12"))
        mutation(bad)
        try:inspect_minutes("2026-10-12",bad)
        except ValueError:pass
        else:raise AssertionError("INVALID_OR_NONRTH_MINUTE_ACCEPTED")
    for day in ("2026-07-03","2026-10-11","not-a-date"):
        try:official_window(day)
        except ValueError:pass
        else:raise AssertionError("NONTRADING_DATE_ACCEPTED")
    # A 16:00 bar may include the auction and afterhours; never automatically
    # attach it to the 390 contiguous 09:30-15:59 minute windows.
    assert (dt.datetime.fromisoformat("2026-10-12T20:00:00Z".replace("Z","+00:00"))
            >=official_window("2026-10-12")[1])
    print("XRAY_RTH_MINUTE_INTEGRITY=PASS_390_FULL_210_EARLY_CLOSE_12_NEGATIVE_NO_DV30_AUTHORITY")

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true",required=True)
    _=a.parse_args()
    selftest()
