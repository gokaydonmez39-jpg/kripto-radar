#!/usr/bin/env python3
"""Exact NASDAQ rolling-30 session incident drop-out horizon; no market calls.

This forecasts the first official session whose most recent 30-session RTH
measurement window excludes a named incomplete historical source day. It is
NOT a source repair, C4.17 price proof, MC proof, licensed data entitlement,
candidate, trading approval, notification or a promised FINAL deadline.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import pandas_market_calendars as mcal
from zoneinfo import ZoneInfo
from source_epoch_freshness_guard import last_complete_session
from alpaca_personal_price_current_exact30 import dates30

SCHEMA="XRAY_PERSONAL_RTH30_UNREPAIRED_GAP_EXIT_HORIZON_V1"
NY=ZoneInfo("America/New_York")
def need(v,why):
    if not v:raise ValueError("XRAY_RTH30_RECOVERY_HORIZON_"+why)

def predict(gap_day:str,asof:str):
    gap=dt.date.fromisoformat(gap_day)
    epoch=dt.date.fromisoformat(asof)
    need(gap.isoformat()==gap_day and epoch.isoformat()==asof
         and gap<=epoch and 0<=(epoch-gap).days<=366,
         "GAP_AND_ASOF_FORMAT_ORDER")
    cal=mcal.get_calendar("NASDAQ")
    events=[str(x.date()) for x in cal.valid_days(
        start_date=(gap-dt.timedelta(days=100)).isoformat(),
        end_date=(gap+dt.timedelta(days=160)).isoformat())]
    need(gap_day in events and asof in events and events==sorted(set(events)),
         "EXACT_OFFICIAL_NASDAQ_DATES")
    current=dates30(asof)
    need(current==events[events.index(asof)-29:events.index(asof)+1],
         "SAME_PRODUCTION_30_SESSION_RULE")
    after=events[events.index(gap_day)+1:]
    need(len(after)>=30, "NO_CLEAN_WINDOW_INSIDE_DATE_HORIZON")
    first_clean=after[29]
    prev=after[28]
    need(gap_day in dates30(prev)
         and gap_day not in dates30(first_clean)
         and dates30(first_clean)[0]==after[0],
         "FIRST_CLEAN_DAY_MINIMALITY")
    schedule=cal.schedule(start_date=first_clean,end_date=first_clean)
    need(len(schedule)==1,"CLEAN_DATE_HAS_ONE_SESSION")
    op=schedule.iloc[0]["market_open"].tz_convert(NY)
    close=schedule.iloc[0]["market_close"].tz_convert(NY)
    minutes=int((close-op).total_seconds()/60)
    need(minutes in (390,210) and minutes%30==0,
         "OFFICIAL_FULL_OR_EARLY_SESSION")
    remaining=sum(x<=asof for x in after[:30])
    # If the gap is no longer in the last 30 days, it was already exited.
    gap_still_window=gap_day in current
    return {
        "schema":SCHEMA,"incident_missing_session":gap_day,
        "asof_last_completed_session":asof,
        "gap_still_in_current_30_session_window":gap_still_window,
        "first_clean_30_session_window_day_without_backfill":first_clean,
        "preceding_29_new_session_day":prev,
        "new_official_sessions_since_incident":sum(
            gap_day<x<=asof for x in events),
        "required_new_official_sessions_after_incident":30,
        "clean_window_achieved_on_asof":asof>=first_clean,
        "first_clean_day_rth_minutes":minutes,
        "first_clean_day_expected_30min_slots":minutes//30,
        "next_session_day_after_incident":after[0],
        "nasdaq_calendar_holiday_adjustment":True,
        "calendar_staleness_caveat":"EXCHANGE_AD_HOC_HALTS_OR_CALENDAR_REVISIONS_REQUIRE_RECHECK",
        "date_is_only_no_backfill_window_drop_out_not_final_deadline":True,
        "independent_c417_price_dv30_attested":False,
        "official_missing_bar_backfill_completed":False,
        "all_30_sessions_clean_data_attested":False,
        "market_cap_2b_attested":False,
        "issuer_and_corporate_events_attested":False,
        "data_feed_rights_attested":False,
        "device_notification_receipt_attested":False,
        "registered_R92_count":0,
        "execution":"NONE","real_money":"NO-GO",
    }

def selftest():
    x=predict("2026-10-15","2026-10-15")
    need(x["first_clean_30_session_window_day_without_backfill"]=="2026-11-27" and
         x["preceding_29_new_session_day"]=="2026-11-25" and
         x["new_official_sessions_since_incident"]==0 and
         x["first_clean_day_expected_30min_slots"]==7 and
         x["first_clean_day_rth_minutes"]==210 and
         x["gap_still_in_current_30_session_window"] is True,
         "THANKSGIVING_EARLY_CLOSE_EXACT30")
    prior=predict("2026-10-15","2026-11-25")
    need(prior["gap_still_in_current_30_session_window"] is True
         and prior["clean_window_achieved_on_asof"] is False
         and prior["new_official_sessions_since_incident"]==29,
         "29_FRESH_SESSIONS_STILL_NOT_SUFFICIENT")
    after=predict("2026-10-15","2026-11-27")
    need(after["gap_still_in_current_30_session_window"] is False
         and after["clean_window_achieved_on_asof"] is True and
         after["new_official_sessions_since_incident"]==30,
         "30_FRESH_SESSIONS_EXCLUDE_GAP")
    import copy
    for d in (x,prior,after):
        need(all(d[k] is False for k in (
            "independent_c417_price_dv30_attested",
            "official_missing_bar_backfill_completed",
            "all_30_sessions_clean_data_attested",
            "market_cap_2b_attested",
            "issuer_and_corporate_events_attested",
            "data_feed_rights_attested",
            "device_notification_receipt_attested")),
            "CALENDAR_NEVER_DATA_PASS")
        need(d["registered_R92_count"]==0 and
             d["execution"]=="NONE" and d["real_money"]=="NO-GO" and
             d["date_is_only_no_backfill_window_drop_out_not_final_deadline"] is True,
             "NO_SCHEDULED_FALSE_FINAL")
    for gap,asof in (
        ("2026-10-15","2026-10-14"),
        ("2026-10-17","2026-10-19"),
        ("2026-10-15","2026-10-18"),
        ("2026-01-01","2026-10-16"),
    ):
        try:predict(gap,asof)
        except ValueError:pass
        else:raise AssertionError("INVALID_OFFICIAL_SOURCE_DATE_ACCEPTED")
    print("XRAY_RTH30_RECOVERY_HORIZON_SELFTEST=PASS_2026_NASDAQ_30_SESSIONS_27NOV_EARLY_CLOSE_NO_FALSE_GO")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--gap-session",default="2026-10-15")
    p.add_argument("--asof")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    asof=a.asof or last_complete_session(dt.datetime.now(dt.timezone.utc))
    r=predict(a.gap_session,asof)
    if a.out is not None:
        # An ephemeral Actions artifact only; never mutate canonical source.
        a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_RTH30_UNREPAIRED_GAP_HORIZON="+json.dumps({
        "gap":r["incident_missing_session"],"asof":r["asof_last_completed_session"],
        "first_gap_free_window_asof":r["first_clean_30_session_window_day_without_backfill"],
        "new_sessions":r["new_official_sessions_since_incident"],
        "early_close_30min_slots":r["first_clean_day_expected_30min_slots"],
        "actual_price_pass":False,"MC":False,"FINAL":False,"R92":0,
    },sort_keys=True))
if __name__=="__main__":main()
