#!/usr/bin/env python3
"""Independent completed-Nasdaq-session freshness test, not HISTORY/MC authority.

A technically successful stale backfill MUST NOT imply a current research GO.
Use official Nasdaq close + 30m EOD safety buffer; never use the calendar date
alone to infer the latest completed session. No provider keys or market data.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_OFFICIAL_NASDAQ_COMPLETE_SESSION_FRESHNESS_V1"
BUFFER=dt.timedelta(minutes=30)


def last_complete_session(now_utc:dt.datetime)->str:
    if now_utc.tzinfo is None or now_utc.utcoffset()!=dt.timedelta(0):
        raise ValueError("REQUIRES_OFFSET_AWARE_UTC_NOW")
    calendar=mcal.get_calendar("NASDAQ")
    start=(now_utc.date()-dt.timedelta(days=20)).isoformat()
    sessions=calendar.schedule(start_date=start,end_date=now_utc.date().isoformat())
    eligible=[str(day.date()) for day,row in sessions.iterrows()
              if (row["market_close"].to_pydatetime()+BUFFER)<=now_utc]
    if not eligible:raise ValueError("NO_COMPLETED_OFFICIAL_SESSION")
    return eligible[-1]


def audit(price:dict,master:dict,terminal:dict,now_utc:dt.datetime)->dict:
    last=last_complete_session(now_utc)
    pa=price.get("asof_et")
    ma=master.get("asof_et")
    ta=terminal.get("asof_et")
    dates=(pa,ma,ta)
    for k,v in zip(("PRICE","MASTER","TERMINAL"),dates):
        try:
            parsed=dt.date.fromisoformat(v)
            if parsed.isoformat()!=v:raise ValueError
        except (TypeError,ValueError):
            raise ValueError("INVALID_"+k+"_ASOF")
    if (price.get("execution")!="NONE" or master.get("execution")!="NONE"
        or terminal.get("execution")!="NONE"
        or price.get("real_money")!="NO-GO" or master.get("real_money")!="NO-GO"
        or terminal.get("real_money")!="NO-GO"):
        raise ValueError("CANONICAL_SAFETY_DRIFT")
    calendar=mcal.get_calendar("NASDAQ")
    valid={str(x.date()) for x in calendar.valid_days(start_date=(dt.date.fromisoformat(last)-dt.timedelta(days=400)).isoformat(),end_date=last)}
    # A pre-holiday, mid-session or future artifact never qualifies as current.
    valid_sequence=sorted(valid)
    lag={}
    for label,d in (("PRICE",pa),("MASTER",ma),("TERMINAL",ta)):
        if d not in valid:
            lag[label]=None
        else:
            lag[label]=len([x for x in valid_sequence if x>d])
    exact_same_asof=(pa==ma==ta==last)
    return {
       "schema":SCHEMA,"latest_completed_nasdaq_session":last,
       "price_asof":pa,"master_asof":ma,"terminal_asof":ta,
       "session_lag":lag,
       "price_master_same_asof":pa==ma,
       "all_sources_latest_completed_same_asof":exact_same_asof,
       "freshness_ready":exact_same_asof,
       "independent_provider_usage_rights_verified":False,
       "primary_mc_authority":False,"canonical_history_authority":False,
       "AL_or_execution_authorized":False,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }


def selftest():
    price={"asof_et":"2026-10-08","execution":"NONE","real_money":"NO-GO"}
    master=dict(price)
    terminal=dict(price,asof_et="2026-10-07")
    late=dt.datetime(2026,10,9,21,0,tzinfo=dt.timezone.utc)
    before_close=dt.datetime(2026,10,9,19,0,tzinfo=dt.timezone.utc)
    saturday=dt.datetime(2026,10,10,13,0,tzinfo=dt.timezone.utc)
    assert last_complete_session(late)=="2026-10-09"
    assert last_complete_session(before_close)=="2026-10-08"
    assert last_complete_session(saturday)=="2026-10-09"
    o=audit(price,master,terminal,late)
    assert o["session_lag"]=={"PRICE":1,"MASTER":1,"TERMINAL":2}
    assert not o["freshness_ready"]
    assert not o["AL_or_execution_authorized"]
    o2=audit(dict(price,asof_et="2026-10-09"),
             dict(master,asof_et="2026-10-09"),
             dict(terminal,asof_et="2026-10-09"),late)
    assert o2["freshness_ready"]
    assert not o2["primary_mc_authority"]
    try:last_complete_session(dt.datetime(2026,10,9,21,0))
    except ValueError:pass
    else:raise AssertionError("NAIVE_TIME_NOT_BLOCKED")
    print("XRAY_NASDAQ_SESSION_FRESHNESS_SELFTEST=PASS_9OCT_POST_CLOSE_PRE_CLOSE_WEEKEND_STALE_AND_FALSE_GO")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    if not args.out or args.out.resolve().is_relative_to(ROOT.parent.resolve()):
        ap.error("--out must be runner-private")
    def read(name):return json.loads((ROOT/name).read_text())
    d=audit(read("canonical_current_price_dv30.json"),
            read("canonical_current_master_manifest.json"),
            read("canonical_current_terminal.json"),dt.datetime.now(dt.timezone.utc))
    args.out.write_text(json.dumps(d,sort_keys=True)+"\n",encoding="utf-8")
    print("XRAY_CURRENT_SESSION_FRESHNESS="+("PASS" if d["freshness_ready"] else "BLOCKED_STALE_SOURCE_EPOCH"))
    print("XRAY_SESSION_LAGS="+json.dumps(d["session_lag"],sort_keys=True))


if __name__=="__main__":main()
