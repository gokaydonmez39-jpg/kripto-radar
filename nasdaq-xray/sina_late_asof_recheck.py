#!/usr/bin/env python3
"""Bounded delayed ASOF recheck policy for Sina research accelerator ONLY.
No bars synthesized. Does not authorize 260/52 HISTORY, MC, R92 or production.
"""
from __future__ import annotations
import datetime as dt
import hashlib
from zoneinfo import ZoneInfo

MAX_RECHECK_ROUNDS=2
MAX_PER_RUN=250
MIN_AFTER_RTH_CLOSE=dt.timedelta(minutes=90)
MIN_SINCE_LAST_OBSERVATION=dt.timedelta(minutes=60)
REASONS=frozenset({"ASOF_MISSING_REQUIRES_RESOLUTION",
                   "EXACT30_INCOMPLETE_NEVER_PASS"})
NY=ZoneInfo("America/New_York")


def _stamp(s):
    if not isinstance(s,str):return None
    try:
        z=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    except (ValueError,OverflowError):return None
    return z.astimezone(dt.timezone.utc) if z.tzinfo is not None else None


def choose(state,official_close_utc,now=None,limit=MAX_PER_RUN):
    """Return ONLY symbols eligible for re-observation; never PASS/price.
    official_close_utc MUST be from a verified Nasdaq session schedule.
    """
    now=now if now is not None else dt.datetime.now(dt.timezone.utc)
    if not isinstance(state,dict) or not isinstance(now,dt.datetime):
        raise ValueError("STATE_OR_CLOCK_INVALID")
    if now.tzinfo is None or official_close_utc is None or official_close_utc.tzinfo is None:
        raise ValueError("NAIVE_CLOCK_OR_NO_OFFICIAL_CLOSE")
    now=now.astimezone(dt.timezone.utc)
    close=official_close_utc.astimezone(dt.timezone.utc)
    local=close.astimezone(NY)
    asof=state.get("asof_et")
    if (not isinstance(asof,str) or local.date().isoformat()!=asof or
        (local.hour,local.minute,local.second) not in {(13,0,0),(16,0,0)}):
        raise ValueError("OFFICIAL_EXCHANGE_CLOSE_ASOF_MISMATCH")
    if (state.get("execution")!="NONE" or state.get("real_money")!="NO-GO"
        or state.get("unknown_never_pass") is not True):
        raise ValueError("CONTROL_SAFETY_INVALID")
    queue=state.get("queue")
    rows=state.get("results")
    expected=state.get("expected30")
    if (not isinstance(queue,list) or not queue
        or len(queue)!=len(set(queue))
        or state.get("queue_total")!=len(queue)
        or state.get("cursor")!=len(queue)
        or state.get("queue_hash")!=hashlib.sha256("\n".join(queue).encode()).hexdigest()
        or not isinstance(rows,dict) or set(rows)!=set(queue)
        or not isinstance(expected,list) or len(expected)!=30
        or expected[-1]!=asof or len(set(expected))!=30):
        raise ValueError("EXACT_QUEUE_30_SESSION_SCOPE_INVALID")
    if state.get("status")!="HISTORY_PARTIAL":
        return []
    if now<close+MIN_AFTER_RTH_CLOSE:
        return []
    if type(limit) is not int or not (1<=limit<=MAX_PER_RUN):
        raise ValueError("RECHECK_RATE_LIMIT_INVALID")
    eligible=[]
    for sym in sorted(rows):
        rec=rows[sym]
        if not isinstance(rec,dict) or rec.get("status")!="UNKNOWN_STATIC":
            continue
        info=rec.get("info")
        if not isinstance(info,dict) or info.get("reason") not in REASONS:
            continue
        attempts=rec.get("late_asof_recheck_round",0)
        if type(attempts) is not int or attempts<0 or attempts>=MAX_RECHECK_ROUNDS:
            continue
        last=_stamp(rec.get("updated_at_utc"))
        if last is None or not (close<=last<=now) or now-last<MIN_SINCE_LAST_OBSERVATION:
            continue
        eligible.append(sym)
    return eligible[:limit]
