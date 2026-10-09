#!/usr/bin/env python3
"""Guard LIVE Nasdaq directory from rewriting a prior completed-session identity.

On Oct 9, Nasdaq's current directory footer reads Oct 9, even while the
latest *completed* price ASOF remains Oct 8. Exact-ASOF replay cannot use
the next day's current directory. Preserve frozen master/PRICE and defer
identity rediscovery until an authentic 8 Oct PIT witness is available.
UNKNOWN is never promoted to PASS.
"""
from __future__ import annotations
import argparse
import datetime as dt
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")

def defer_live_identity_replay(now_utc, asof, active_completed_epoch, price_integrity_ok, requested):
    if now_utc.tzinfo is None:
        raise ValueError("NAIVE_CLOCK_FORBIDDEN")
    day=dt.date.fromisoformat(str(asof))
    ny_today=now_utc.astimezone(NY).date()
    if day>ny_today:
        raise ValueError("FUTURE_ASOF_IDENTITY_REPLAY_FORBIDDEN")
    return bool(requested and active_completed_epoch and price_integrity_ok
                and day<ny_today)

def selftest():
    ny_dt=lambda y,m,d,h:dt.datetime(y,m,d,h,tzinfo=NY)
    # Current next-day Nasdaq directory may not re-identify Oct 8's PIT.
    assert defer_live_identity_replay(ny_dt(2026,10,9,4),"2026-10-08",True,True,True)
    # Same-day completed session is eligible for live directory only if the
    # directory itself passes the independent exact-footer check.
    assert not defer_live_identity_replay(ny_dt(2026,10,8,18),"2026-10-08",True,True,True)
    for active,price_ok,requested in ((False,True,True),(True,False,True),(True,True,False)):
        assert not defer_live_identity_replay(ny_dt(2026,10,9,4),"2026-10-08",
                                             active,price_ok,requested)
    assert defer_live_identity_replay(ny_dt(2026,10,12,11),"2026-10-09",True,True,True)
    for date in ("2026-10-10","2026-10-25"):
        try:defer_live_identity_replay(ny_dt(2026,10,9,4),date,True,True,True)
        except ValueError:pass
        else:raise AssertionError("FUTURE_IDENTITY_ALLOWED")
    try:defer_live_identity_replay(dt.datetime(2026,10,9,4),"2026-10-08",True,True,True)
    except ValueError:pass
    else:raise AssertionError("NAIVE_CLOCK_ALLOWED")
    print("XRAY_PRE_MC_NEXT_DAY_IDENTITY_GUARD_SELFTEST=PASS_FROZEN_PIT_7_NEGATIVE")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    opts=p.parse_args()
    if opts.selftest:selftest()
