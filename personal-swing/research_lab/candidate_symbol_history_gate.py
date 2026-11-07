#!/usr/bin/env python3
"""XRAY NASDAQ historical research eligibility: date shape, NOT PIT/alpha.

Current 477 operational membership never shrinks because of short listing history.
No network, price feed, brokerage, Sheet write, alert or order.
"""
from __future__ import annotations
from datetime import date
import re

SYMBOL_RE = re.compile(r"[A-Z][A-Z0-9.]{0,14}")
MIN_RESEARCH_SESSIONS = 500


def _date(raw: object) -> date:
    if type(raw) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
        raise ValueError("BAD_SESSION_FORMAT")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("BAD_SESSION_DATE") from exc
    if parsed.isoformat() != raw:
        raise ValueError("NONCANONICAL_DATE")
    return parsed


def assess(universe: list[str], asof_et: str, observations: dict) -> dict:
    if type(universe) is not list or len(universe) != 477:
        raise ValueError("REQUIRES_FIXED_477_UNIVERSE")
    if any(type(s) is not str or SYMBOL_RE.fullmatch(s) is None for s in universe):
        raise ValueError("INVALID_UNIVERSE_SYMBOL")
    if len(set(universe)) != 477:
        raise ValueError("DUPLICATE_UNIVERSE_SYMBOL")
    asof = _date(asof_et)
    if type(observations) is not dict or not set(observations).issubset(set(universe)):
        raise ValueError("UNKNOWN_HISTORY_SYMBOL")
    import exchange_calendars as xc
    calendar = xc.get_calendar("XNAS")
    if not calendar.is_session(asof.isoformat()):
        raise ValueError("NON_XNAS_ASOF")

    output = []
    for symbol in universe:
        if symbol not in observations:
            output.append({"symbol": symbol, "status": "UNKNOWN_HISTORY",
                           "observed_sessions": 0, "first_session": None,
                           "last_session": None})
            continue
        row = observations[symbol]
        if type(row) is not dict or set(row) != {"sessions", "feed", "basis"}:
            raise ValueError("INVALID_HISTORY_RECORD")
        if row["feed"] != "iex" or row["basis"] != "RAW":
            raise ValueError("UNAUTHORIZED_TAPE_OR_ADJUSTMENT")
        dates = row["sessions"]
        if type(dates) is not list or not (1 <= len(dates) <= 4000):
            raise ValueError("INVALID_SESSION_LIST")
        parsed = [_date(v) for v in dates]
        if any(a >= b for a,b in zip(parsed, parsed[1:])):
            raise ValueError("DUPLICATE_OR_NONMONOTONIC_SESSIONS")
        if parsed[-1] > asof:
            raise ValueError("FUTURE_SESSION")
        expected = {s.strftime("%Y-%m-%d") for s in
                    calendar.sessions_in_range(parsed[0].isoformat(),
                                               parsed[-1].isoformat())}
        if not set(dates).issubset(expected):
            raise ValueError("NON_XNAS_SESSION_IN_HISTORY")
        missing = len(expected.difference(dates))
        if parsed[-1] < asof:
            status = "STALE_HISTORY_HOLD"
        elif missing:
            status = "GAPPED_HISTORY_HOLD"
        elif len(dates) < MIN_RESEARCH_SESSIONS:
            status = "INSUFFICIENT_HISTORY"
        else:
            status = "DATE_SHAPE_500_PASS_ONLY"
        output.append({
            "symbol": symbol, "status": status,
            "observed_sessions": len(dates), "first_session": dates[0],
            "last_session": dates[-1], "missing_calendar_sessions": missing
        })
    categories = (
        "UNKNOWN_HISTORY", "STALE_HISTORY_HOLD", "GAPPED_HISTORY_HOLD",
        "INSUFFICIENT_HISTORY", "DATE_SHAPE_500_PASS_ONLY"
    )
    return {
        "schema": "XRAY_NASDAQ_HISTORY_ELIGIBILITY_V1",
        "asof_et": asof_et, "universe_covered": 477,
        "counts": {key: sum(r["status"] == key for r in output)
                   for key in categories},
        "records": output,
        "status": "CALENDAR_DATE_SHAPE_ONLY_NOT_PIT_OR_OOS",
        "can_use_for_production": False,
        "source_rights_verified": False,
        "first_known_at_verified": False,
        "historical_membership_verified": False,
        "corporate_actions_verified": False,
        "real_pit_verified": False,
        "oos_alpha_verified": False
    }
