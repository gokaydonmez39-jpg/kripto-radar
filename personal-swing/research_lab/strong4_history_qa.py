#!/usr/bin/env python3
"""Local-only 477-symbol raw-IEX historical shape/identity intake.

DATA RIGHTS, independent PIT/first-known timestamps, issuer historical mapping,
strategy predictions, OOS alpha and production permissions are NEVER certified.
No broker, network, Sheet write, schedule, order or persistent price export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "XRAY_STRONG4_PRIVATE_HISTORY_INPUT_V1"
REPORT = "XRAY_STRONG4_HISTORY_SHAPE_REPORT_V1"
WATCHLIST_GIT_BLOB = "786fa9b3a673ef56e9f0384f721d7fa836e9b9cd"
ASOF_MAX = date(2026, 11, 6)  # this closed-season readback; future epochs require review
TRANSITION = date(2026, 11, 3)
OLD_SYMBOL = "INDV"
SUCCESSOR_SYMBOL = "SUPN"
MIN_HISTORY = 500
NY = ZoneInfo("America/New_York")


def _require(cond: bool, reason: str) -> None:
    if not cond:
        raise ValueError(reason)


def _day(value: object) -> date:
    _require(type(value) is str and len(value) == 10, "BAD_DAY_FORMAT")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("BAD_DAY") from exc
    _require(d.isoformat() == value, "BAD_DAY_FORMAT")
    return d


def immutable_watchlist(raw: bytes) -> list[str]:
    digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
    _require(digest == WATCHLIST_GIT_BLOB, "WATCHLIST_GIT_SHA_CHANGED")
    obj = json.loads(raw)
    symbols = obj.get("liquidity_watch_symbols")
    _require(type(symbols) is list and len(symbols) == 477 and
             len(set(symbols)) == 477 and all(type(s) is str for s in symbols),
             "WATCHLIST_NOT_FIXED_477")
    _require(OLD_SYMBOL in symbols and SUCCESSOR_SYMBOL not in symbols,
             "WATCHLIST_IDENTITY_DRIFT")
    actions = obj.get("point_in_time_symbol_changes")
    _require(type(actions) is list and any(type(a) is dict and
             a.get("old_symbol") == OLD_SYMBOL and a.get("new_symbol") == SUCCESSOR_SYMBOL and
             a.get("effective_asof_et") == TRANSITION.isoformat() for a in actions),
             "KNOWN_NASDAQ_IDENTITY_EVENT_MISSING")
    return symbols


def market_identity(original_watch_symbol: str, session: date) -> tuple[str, str]:
    """Ticker reuse is not issuer continuity. No automatic vendor query/remap."""
    if original_watch_symbol == OLD_SYMBOL:
        if session < TRANSITION:
            return OLD_SYMBOL, "PRE_MERGER_INDVIOR"
        return SUCCESSOR_SYMBOL, "SUCCESSOR_OF_INDVIOR_NOT_LEGACY_SUPN"
    if original_watch_symbol == SUCCESSOR_SYMBOL and session < TRANSITION:
        return SUCCESSOR_SYMBOL, "LEGACY_SUPN_DISTINCT_ISSUER"
    return original_watch_symbol, "NO_KNOWN_ACTION_IN_THIS_GUARD"


def inspect(document: object, watch_symbols: list[str]) -> dict:
    _require(type(document) is dict and document.get("schema") == SCHEMA,
             "SCHEMA_INVALID")
    _require(type(watch_symbols) is list and len(watch_symbols) == 477 and
             len(set(watch_symbols)) == 477 and OLD_SYMBOL in watch_symbols and
             SUCCESSOR_SYMBOL not in watch_symbols, "NOT_FIXED_477")
    asof = _day(document.get("asof_et"))
    _require(asof <= ASOF_MAX, "FUTURE_OR_UNREVIEWED_ASOF")
    for key, expected in (("source", "Alpaca"), ("feed", "iex"),
                          ("timeframe", "1Day"), ("basis", "RAW")):
        _require(document.get(key) == expected, "SOURCE_SCOPE_INVALID_"+key)
    _require(document.get("universe_git_blob") == WATCHLIST_GIT_BLOB,
             "UNIVERSE_SHA_MISMATCH")
    bars_by_symbol = document.get("bars")
    _require(type(bars_by_symbol) is dict and
             set(bars_by_symbol).issubset(watch_symbols),
             "UNDECLARED_PRICE_SYMBOL")

    try:
        import exchange_calendars as xc
        calendar = xc.get_calendar("XNAS")
        _require(calendar.is_session(asof.isoformat()), "ASOF_NOT_EXCHANGE_SESSION")
        start = _day("2024-09-03")
        sessions = [d.strftime("%Y-%m-%d") for d in calendar.sessions_in_range(start, asof)]
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("CALENDAR_ERROR") from exc
    session_set = set(sessions)
    counts = {name: 0 for name in (
        "DATE_SHAPE_500_ONLY", "SHORT_HISTORY_HOLD", "STALE_HISTORY_HOLD",
        "MISSING_HISTORY_HOLD", "GAPPED_HISTORY_HOLD",
        "KNOWN_CORPORATE_ACTION_IDENTITY_HOLD")}
    anomalies=[]
    total_bars=0
    for symbol in watch_symbols:
        observed=bars_by_symbol.get(symbol)
        if observed is None:
            counts["MISSING_HISTORY_HOLD"]+=1
            anomalies.append({"symbol":symbol,"status":"MISSING_HISTORY_HOLD","count":0})
            continue
        _require(type(observed) is list and 0 < len(observed) <= 1500,
                 "INVALID_SYMBOL_BAR_COUNT_"+symbol)
        dates=[]
        for record in observed:
            _require(type(record) is dict and set(record) ==
                     {"timestamp","open","high","low","close","volume"},
                     "BAR_SCHEMA_INVALID_"+symbol)
            try:
                timestamp = datetime.fromisoformat(record["timestamp"])
            except (ValueError, TypeError) as exc:
                raise ValueError("BAR_TIMESTAMP_INVALID_"+symbol) from exc
            _require(timestamp.tzinfo is not None and timestamp.utcoffset() is not None,
                     "NAIVE_BAR_TIMESTAMP_"+symbol)
            et = timestamp.astimezone(NY)
            _require(et.hour == 0 and et.minute == 0 and et.second == 0,
                     "BAR_NOT_DAILY_NY_MIDNIGHT_"+symbol)
            d=et.date().isoformat()
            _require(d in session_set, "NON_XNAS_OR_FUTURE_BAR_"+symbol)
            _require(type(record["volume"]) is int and record["volume"] >= 0,
                     "VOLUME_INVALID_"+symbol)
            price=[]
            for field in ("open","high","low","close"):
                v=record[field]
                _require(type(v) in (int,float) and math.isfinite(v) and v>0,
                         "PRICE_INVALID_"+symbol)
                price.append(float(v))
            op,hi,lo,close=price
            _require(lo<=min(op,close)<=max(op,close)<=hi,
                     "BAR_OHLC_CONTRADICTION_"+symbol)
            dates.append(d)
        _require(all(a<b for a,b in zip(dates,dates[1:])),
                 "DUPLICATE_OR_UNSORTED_BARS_"+symbol)
        first,last=dates[0],dates[-1]
        expected = [s for s in sessions if first<=s<=last]
        missing=len(set(expected)-set(dates))
        total_bars+=len(observed)
        if symbol==OLD_SYMBOL and asof >= TRANSITION:
            # Recognize official November 3 alias but DO NOT join legacy SUPN bars.
            # Correct continuity requires issuer-backed lineage, NOT ticker alone.
            status="KNOWN_CORPORATE_ACTION_IDENTITY_HOLD"
        elif last!=asof.isoformat():
            status="STALE_HISTORY_HOLD"
        elif missing:
            status="GAPPED_HISTORY_HOLD"
        elif len(dates)<MIN_HISTORY:
            status="SHORT_HISTORY_HOLD"
        else:
            status="DATE_SHAPE_500_ONLY"
        counts[status]+=1
        if status!="DATE_SHAPE_500_ONLY":
            anomalies.append({"symbol":symbol,"status":status,"count":len(dates),
                              "first_session":first,"last_session":last,
                              "internal_missing":missing})
    return {
        "schema":REPORT,
        "asof_et":asof.isoformat(),
        "watchlist_size":477,
        "watchlist_blob_sha":WATCHLIST_GIT_BLOB,
        "queried_symbols_with_bars":len(bars_by_symbol),
        "bars_checked":total_bars,
        "counts":counts,
        "exceptions":anomalies,
        "all_477_bars_available":len(bars_by_symbol)==477,
        "status":"DATE_SHAPE_ONLY_PRODUCTION_HOLD",
        "issuer_lineage_independently_verified":False,
        "source_rights_independently_verified":False,
        "source_adjustment_raw_independently_verified":False,
        "model_predictions_verified":False,
        "oos_performance_verified":False,
        "production_authorized":False,
        "live_orders_authorized":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--local-private-bars",required=True)
    parser.add_argument("--watchlist",default=str(Path(__file__).parent.parent/"nasdaq_watchlist_477.json"))
    args=parser.parse_args()
    try:
        path=Path(args.local_private_bars)
        _require(path.is_file() and path.stat().st_size<=80_000_000,"BAR_INPUT_MISSING_OR_TOO_LARGE")
        watch=immutable_watchlist(Path(args.watchlist).read_bytes())
        report=inspect(json.loads(path.read_text(encoding="utf-8")),watch)
        # Metadata only; never print, export or persist proprietary source bars.
        print(json.dumps(report,sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc)[:170],
                          "production_authorized":False},sort_keys=True))
        return 3

if __name__=="__main__":
    raise SystemExit(main())
