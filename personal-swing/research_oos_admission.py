"""Offline cohort admission for the pre-registered Personal 477 event test.

Supplied proof flags and session labels are not independent source attestations.
This function checks structure, not trading performance or statistical power.
"""
from bisect import bisect_right
from datetime import date


MIN_FOLDS = 3
MIN_PER_ARM = 30
HORIZON = 15


def _day(value):
    if not isinstance(value, str):
        raise ValueError("OOS_INVALID_SESSION")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("OOS_INVALID_SESSION")
    return parsed


def assess_oos_readiness(rows, *, official_sessions, folds):
    """Count unique, mature episodes with known coverage in fixed OOS folds.

    Require the full original follow-up window even for an earlier touch.
    An unresolved label spanning the fold edge is not counted in either fold.
    No study result or alpha claim is emitted even when the structure passes.
    """
    if not isinstance(official_sessions, list) or not official_sessions:
        raise ValueError("OOS_INVALID_SESSIONS")
    days = [_day(s) for s in official_sessions]
    if any(a >= b for a, b in zip(days, days[1:])):
        raise ValueError("OOS_INVALID_SESSIONS")
    idx = {s: i for i, s in enumerate(official_sessions)}
    if not isinstance(folds, list) or not MIN_FOLDS <= len(folds) <= len(days):
        raise ValueError("OOS_INVALID_FOLDS")
    windows = []
    for fold in folds:
        try:
            start, end = idx[fold["start"]], idx[fold["end"]]
        except (KeyError, TypeError) as exc:
            raise ValueError("OOS_INVALID_FOLDS") from exc
        if end - start < HORIZON or (windows and start <= windows[-1][1]):
            raise ValueError("OOS_INVALID_FOLDS")
        windows.append((start, end))
    starts = [a for a, _ in windows]
    counts = [{"start": official_sessions[a], "end": official_sessions[b],
               "event": 0, "no_event": 0} for a, b in windows]
    excluded = dict(outside_folds=0, unproved_coverage=0,
                    invalid_outcome_window=0, overlapping_outcome=0)
    if not isinstance(rows, list):
        raise ValueError("OOS_INVALID_EPISODES")
    seen = set()
    for row in rows:
        if type(row) is not dict:
            raise ValueError("OOS_INVALID_EPISODES")
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            raise ValueError("OOS_INVALID_EPISODE_KEY")
        if key in seen:
            raise ValueError("OOS_DUPLICATE_EPISODE")
        seen.add(key)
        signal = row.get("signal_session")
        if not isinstance(signal, str) or signal not in idx:
            raise ValueError("OOS_UNVERIFIED_SIGNAL_SESSION")
        signal_idx = idx[signal]
        k = bisect_right(starts, signal_idx) - 1
        if k < 0 or signal_idx > windows[k][1]:
            excluded["outside_folds"] += 1
            continue
        event = row.get("event_present")
        if row.get("pit_coverage_proven") is not True or type(event) is not bool:
            excluded["unproved_coverage"] += 1
            continue
        end = row.get("last_verified_session")
        end_idx = idx.get(end) if isinstance(end, str) else None
        if end_idx != signal_idx + HORIZON or type(row.get("stop_contact")) is not bool:
            excluded["invalid_outcome_window"] += 1
            continue
        if end_idx > windows[k][1]:
            excluded["overlapping_outcome"] += 1
            continue
        counts[k]["event" if event else "no_event"] += 1
    eligible = sum(c["event"] + c["no_event"] for c in counts)
    ready = all(min(c["event"], c["no_event"]) >= MIN_PER_ARM for c in counts)
    return {
        "status": "STRUCTURAL_READY_FOR_RESEARCH" if ready else "HOLD_INSUFFICIENT_OOS_COHORT",
        "input_unique_episodes": len(seen), "eligible_episodes": eligible,
        "necessary_unique_floor": len(windows) * 2 * MIN_PER_ARM,
        "folds": counts, "excluded": excluded, "official_sessions_attested": False,
        "live_source_attested": False, "performance_improvement_proven": False,
        "production_eligible": False,
    }
