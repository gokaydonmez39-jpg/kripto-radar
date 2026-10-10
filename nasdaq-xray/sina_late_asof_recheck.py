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
MAX_CANARY_PROBES_PER_EPOCH=8
MAX_CANARY_HORIZON=dt.timedelta(hours=16)
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


def _source_ready(rows,close):
    # A real, timely, as-of Sina measurement can attest publication readiness
    # even when the alpha price/DV30 hard gate correctly FAILS. Neither status
    # grants HISTORY/MC/R92 authority. Overlays cannot be source canaries.
    for v in rows.values():
        if not isinstance(v,dict) or v.get("resolution_overlay") is True:
            continue
        if type(v.get("attempts")) is not int or v["attempts"]<1:
            continue
        if (_stamp(v.get("updated_at_utc")) or close-dt.timedelta(days=1))<close:
            continue
        info=v.get("info")
        if not isinstance(info,dict):continue
        status=v.get("status")
        proof=info.get("proof")
        if ((status in ("PASS","FAIL_DV30") and proof=="EXACT30_MEDIAN")
            or (status=="FAIL_PRICE" and proof=="ASOF_CLOSE")):
            return True
    return False


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
    # Only real source-observed dates open bounded delayed EOD rechecks.
    source_ready=_source_ready(rows,close)
    if not source_ready:
        return []
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

def choose_canary_probe(state,official_close_utc,now=None):
    """At most ONE real-source canary request/hour, eight per ASOF epoch total.
    Caller MUST invoke choose() first, which rejects invalid scope/safety.
    No canary observation is invented or promoted to PRIMARY.
    """
    now=now if now is not None else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CANARY_CLOCK")
    now=now.astimezone(dt.timezone.utc)
    close=official_close_utc.astimezone(dt.timezone.utc)
    if (state.get("status")!="HISTORY_PARTIAL"
        or now<close+MIN_AFTER_RTH_CLOSE
        or now>close+MAX_CANARY_HORIZON):
        return []
    rows=state["results"]
    probes=0
    last_probe=None
    for rec in rows.values():
        if not isinstance(rec,dict):return []
        n=rec.get("late_asof_canary_probe_round",0)
        if type(n) is not int or not 0<=n<=MAX_CANARY_PROBES_PER_EPOCH:
            return []
        probes+=n
        if n:
            when=_stamp(rec.get("updated_at_utc"))
            if when is None or when<close or when>now:return []
            last_probe=max(last_probe,when) if last_probe else when
    if probes>=MAX_CANARY_PROBES_PER_EPOCH:return []
    if last_probe and now-last_probe<MIN_SINCE_LAST_OBSERVATION:
        return []
    if _source_ready(rows,close):
        return []
    for sym in ("AAPL","NVDA","MSFT"):
        v=rows.get(sym)
        if (isinstance(v,dict) and v.get("status")=="UNKNOWN_STATIC"
            and isinstance(v.get("info"),dict)
            and v["info"].get("reason")=="ASOF_MISSING_REQUIRES_RESOLUTION"):
            t=_stamp(v.get("updated_at_utc"))
            if t and close<=t<=now and now-t>=MIN_SINCE_LAST_OBSERVATION:
                return [sym]
    return []
