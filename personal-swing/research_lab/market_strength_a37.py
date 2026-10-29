"""XRAY PERSONAL NASDAQ A37: independent, offline-only market breadth & relative strength.

No HTTP, scraping, scraping bypass, API keys, private sheets, trading, production AL,
or push capabilities. An authorized upstream passes completed, PIT-stamped OHLCV.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import hashlib
import math
import re

import exchange_calendars as ec

SCHEMA = "XRAY_A37_SHADOW_V1"
EXPECTED_UNIVERSE = 477
LOOKBACK_SESSIONS = 64  # 63 close-to-close intervals, not '63 calendar days'
ALLOWED_FEEDS = frozenset({"iex", "sip"})
ALLOWED_BASES = frozenset({"raw", "split"})
SYM = re.compile(r"^[A-Z][A-Z0-9.]{0,14}$")
CANONICAL_SCOPE_SHA = "420025dd5b83b59fedd3d9af4332471fee731aedfaacb616ce80ca473bef6745"

class ShadowBlocked(ValueError):
    pass


def require(cond, message):
    if not cond:
        raise ShadowBlocked(message)


def _stamp(stamp):
    require(isinstance(stamp, str), "MISSING_KNOWN_AT")
    try:
        d = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        require(d.tzinfo is not None and d.utcoffset() is not None, "NAIVE_KNOWN_AT")
        return d.astimezone(timezone.utc)
    except ShadowBlocked:
        raise
    except (ValueError, TypeError) as exc:
        raise ShadowBlocked("INVALID_KNOWN_AT") from exc


def _decimal(v, *, positive=True):
    require(isinstance(v, (int, float)) and not isinstance(v, bool), "INVALID_NUMERIC_TYPE")
    x = float(v)
    require(math.isfinite(x) and (x > 0 if positive else x >= 0), "INVALID_NUMERIC_VALUE")
    return x


def official_sessions(asof, window=LOOKBACK_SESSIONS):
    """Require exact official XNAS session set, not a weekday approximation."""
    try:
        final = date.fromisoformat(asof)
        calendar = ec.get_calendar("XNAS")
        require(calendar.is_session(final.isoformat()), "NOT_XNAS_SESSION")
        all_sessions = calendar.sessions_in_range(((final - timedelta(days=800))).isoformat(), asof)
        require(len(all_sessions) >= window, "INSUFFICIENT_XNAS_LOOKBACK")
        return [x.date().isoformat() for x in all_sessions[-window:]]
    except (TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, ShadowBlocked):
            raise
        raise ShadowBlocked("INVALID_XNAS_ASOF") from exc


def _series(rows, *, symbol, dates, closes_by_date, cutoff, feed, basis):
    require(isinstance(rows, list) and len(rows) == len(dates), "MISSING_OR_EXTRA_SESSIONS")
    result = []
    for n, (bar, day) in enumerate(zip(rows, dates)):
        require(isinstance(bar, dict), "INVALID_BAR")
        require(bar.get("session") == day, "GAP_DUPLICATE_OR_WRONG_SESSION")
        require(bar.get("symbol") == symbol, "WRONG_SYMBOL_IDENTITY")
        require(bar.get("feed") == feed and bar.get("basis") == basis, "MIXED_FEED_OR_BASIS")
        known = _stamp(bar.get("known_at_utc"))
        require(known <= cutoff, "LOOKAHEAD_KNOWN_AT")
        # Minimum: completed official bar cannot have been known on its calendar day before RTH close.
        session_close = closes_by_date[day]
        require(known >= session_close, "PREMATURE_FINAL_BAR")
        close = _decimal(bar.get("close"))
        _decimal(bar.get("volume"), positive=False)
        result.append(close)
    return result


def _sma(c, n):
    return sum(c[-n:]) / n


def analyze(*, asof, cutoff_utc, symbols, bars, benchmark, feed="iex", basis="raw",
            expected_scope_sha256=CANONICAL_SCOPE_SHA):
    """All or nothing; 477/477 coverage or ShadowBlocked; no AL decisions.

    Input: maps symbol->64 contiguous completed XNAS bars. Benchmark has 64 bars.
    ASOF cutoff must be after close. Inputs carry provider/adjustment/availability fields.
    """
    require(feed in ALLOWED_FEEDS and basis in ALLOWED_BASES, "UNAUTHORIZED_FEED_OR_BASIS")
    require(isinstance(symbols, list) and len(symbols) == EXPECTED_UNIVERSE, "WRONG_UNIVERSE_SIZE")
    require(all(isinstance(s, str) and SYM.fullmatch(s) for s in symbols), "BAD_TICKER")
    require(len(set(symbols)) == len(symbols), "DUPLICATE_UNIVERSE")
    require(isinstance(expected_scope_sha256, str) and re.fullmatch("[a-f0-9]{64}", expected_scope_sha256), "MISSING_AUTHORITY_SCOPE_SHA")
    computed_scope_sha256 = hashlib.sha256(("\n".join(symbols) + "\n").encode()).hexdigest()
    require(computed_scope_sha256 == expected_scope_sha256, "SCOPE_SHA_MISMATCH")
    require("QQQ" not in symbols, "BENCHMARK_IN_UNIVERSE_AMBIGUITY")
    require(isinstance(bars, dict) and set(bars) == set(symbols), "MISSING_EXTRA_OR_DUPLICATE_SCOPE")
    require(isinstance(benchmark, list), "MISSING_BENCHMARK")
    cutoff = _stamp(cutoff_utc)
    sessions = official_sessions(asof)
    calendar = ec.get_calendar("XNAS")
    closes_by_date = {day: calendar.session_close(day).to_pydatetime().astimezone(timezone.utc) for day in sessions}
    final_close = closes_by_date[asof]
    require(cutoff >= final_close, "ASOF_NOT_COMPLETED")
    benchmark_prices = _series(benchmark, symbol="QQQ", dates=sessions, closes_by_date=closes_by_date, cutoff=cutoff, feed=feed, basis=basis)
    bm_return = benchmark_prices[-1] / benchmark_prices[0] - 1
    require(bm_return > -1, "BAD_BENCHMARK_RETURN")
    above20 = above50 = 0
    result = {}
    for symbol in symbols:
        prices = _series(bars[symbol], symbol=symbol, dates=sessions, closes_by_date=closes_by_date, cutoff=cutoff, feed=feed, basis=basis)
        x20, x50, last = _sma(prices, 20), _sma(prices, 50), prices[-1]
        up20, up50 = last > x20, last > x50
        above20 += int(up20)
        above50 += int(up50)
        equity_return = last / prices[0] - 1
        # Relative-return ratio, NOT a proprietary percentile or guarantee of alpha.
        rs63 = (1 + equity_return) / (1 + bm_return) - 1
        result[symbol] = {"above_sma20": up20, "above_sma50": up50,
                          "relative_return_vs_qqq_63_sessions_pct": round(rs63 * 100, 6)}
    return {"schema": SCHEMA, "asof_et": asof, "cutoff_utc": cutoff.isoformat(),
            "feed": feed, "basis": basis, "benchmark": "QQQ",
            "universe": EXPECTED_UNIVERSE, "covered": EXPECTED_UNIVERSE,
            "scope_sha256": computed_scope_sha256,
            "complete_official_sessions": len(sessions),
            "breadth_above_sma20_count": above20,
            "breadth_above_sma20_pct": round(100 * above20 / EXPECTED_UNIVERSE, 6),
            "breadth_above_sma50_count": above50,
            "breadth_above_sma50_pct": round(100 * above50 / EXPECTED_UNIVERSE, 6),
            "benchmark_return_63_sessions_pct": round(100 * bm_return, 6),
            "per_symbol_research": result, "mode": "OFFLINE_SHADOW_RESEARCH_ONLY",
            "may_generate_al": False, "may_change_stops": False,
            "may_write_sheets": False, "may_emit_alert": False,
            "may_trade": False, "market_strength_site_calls": 0}
