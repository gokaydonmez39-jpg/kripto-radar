#!/usr/bin/env python3
"""Sidecar-only research validation; official-session inputs must be attested upstream.

Never edits the real journal, redefines stop/target, emits push or trades.
"""
from datetime import date
import math


def _date(x):
    if not isinstance(x, str):
        raise ValueError("SESSION_DATE_REQUIRED")
    d = date.fromisoformat(x)
    if d.isoformat() != x:
        raise ValueError("NONCANONICAL_SESSION_DATE")
    return d


def _price(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("INVALID_OHLC_PRICE")
    x = float(x)
    if not math.isfinite(x) or x <= 0:
        raise ValueError("INVALID_OHLC_PRICE")
    return x


def research_lifecycle(candidate, *, verified_next_sessions, bars):
    """Review up to 15 *supplied verified* official next trading sessions.

    If a bar is missing, STOP at UNKNOWN rather than silently skipping a day.
    A hypothetical touch is NOT broker execution and daily bars cannot order
    intraday stop/target touches. Terminal status never realizes cash P&L.
    """
    if not isinstance(verified_next_sessions, list):
        raise ValueError("OFFICIAL_SESSIONS_REQUIRED")
    if not isinstance(bars, dict):
        raise ValueError("BAR_MAP_REQUIRED")
    if len(verified_next_sessions) > 15 or len(verified_next_sessions) != len(set(verified_next_sessions)):
        raise ValueError("SESSION_SCOPE_INVALID")
    dates = [_date(x) for x in verified_next_sessions]
    if dates != sorted(dates):
        raise ValueError("NONMONOTONIC_OFFICIAL_SESSIONS")
    entry = _date(candidate["asof_et"])
    if dates and dates[0] <= entry:
        raise ValueError("LOOKAHEAD_OR_ENTRY_AS_SESSION")
    start = _price(candidate["reference_close"])
    stop = _price(candidate["stop"])
    target = _price(candidate["target_2r"])
    if not stop < start < target:
        raise ValueError("INVALID_ORIGINAL_RISK_LEVELS")
    for n, session in enumerate(verified_next_sessions, 1):
        if session not in bars:
            return {"status": "STATUS_UNKNOWN_MISSING_SESSION", "sessions": n - 1,
                    "missing_session": session, "production_eligible": False,
                    "fills_confirmed": False}
        bar = bars[session]
        o, h, l, c = [_price(bar[field]) for field in ("open", "high", "low", "close")]
        if h < max(o, l, c) or l > min(o, h, c):
            raise ValueError("INVALID_OHLC_GEOMETRY")
        stop_hit, target_hit = l <= stop, h >= target
        if stop_hit or target_hit:
            if stop_hit and target_hit:
                status = "BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS"
            elif stop_hit:
                status = "GAP_BELOW_STOP" if o < stop else "STOP_TOUCHED"
            else:
                status = "TARGET_TOUCHED"
            return {"status": status, "sessions": n, "asof_et": session,
                    "original_stop": stop, "original_target": target,
                    "gap_below_stop": o < stop, "production_eligible": False,
                    "fills_confirmed": False}
        if n == 15:
            return {"status": "TIME_EXIT_AT_CLOSE", "sessions": n,
                    "asof_et": session, "reference_close": c,
                    "production_eligible": False, "fills_confirmed": False}
    return {"status": "OPEN_RESEARCH_ONLY", "sessions": len(dates),
            "production_eligible": False, "fills_confirmed": False}


def purged_walkforward(records, *, official_sessions, test_start, embargo_sessions=2,
                       min_test_size=30):
    """No train/test label leakage; never returns an unproven 'improved alpha' claim.

    Requires outcomes computed upstream with correct corporate-action, survivorship,
    price-provider and execution-cost semantics. This only validates split chronology.
    """
    if not isinstance(official_sessions, list) or not official_sessions:
        raise ValueError("OFFICIAL_SESSIONS_REQUIRED")
    if len(set(official_sessions)) != len(official_sessions):
        raise ValueError("DUPLICATE_OFFICIAL_SESSION")
    if [_date(x) for x in official_sessions] != sorted(_date(x) for x in official_sessions):
        raise ValueError("NONMONOTONIC_OFFICIAL_SESSIONS")
    if isinstance(embargo_sessions, bool) or not isinstance(embargo_sessions, int) or embargo_sessions < 0:
        raise ValueError("INVALID_EMBARGO")
    day_to_i = {s: i for i, s in enumerate(official_sessions)}
    if test_start not in day_to_i:
        raise ValueError("INVALID_TEST_START")
    boundary = day_to_i[test_start]
    cutoff_train = boundary - embargo_sessions
    train, holdout = [], []
    seen = set()
    for r in records:
        identity = r.get("id")
        if not identity or identity in seen:
            raise ValueError("DUPLICATE_OR_MISSING_CANDIDATE_KEY")
        seen.add(identity)
        open_day, close_day = r["signal_session"], r["outcome_session"]
        if open_day not in day_to_i or close_day not in day_to_i:
            raise ValueError("UNVERIFIED_RECORD_SESSION")
        a, b = day_to_i[open_day], day_to_i[close_day]
        if a > b or b - a > 15:
            raise ValueError("LOOKAHEAD_OR_LIFECYCLE_BOUND_VIOLATION")
        if a >= boundary:
            holdout.append(identity)
        elif b < cutoff_train:
            train.append(identity)
        # Otherwise purge overlapping labels. No re-use of test evidence for fit.
    return {
        "schema": "XRAY_PURGED_WALKFORWARD_PARTITION_V1",
        "train_ids": sorted(train),
        "test_ids": sorted(holdout),
        "purged_count": len(records) - len(train) - len(holdout),
        "minimum_holdout_count": min_test_size,
        "statistical_conclusion": "INSUFFICIENT_OOS_EVIDENCE"
        if len(holdout) < min_test_size else "REQUIRES_FEES_BENCHMARK_AND_STATS",
        "performance_improvement_proven": False,
        "changes_to_live_alpha": False,
    }
