#!/usr/bin/env python3
"""XRAY NASDAQ A36. OFFLINE, read-only, isolated price/volume and trade/quote lab.

NO provider HTTP, broker, order, Google Sheets, push, AL/IZLE/ELE decision
changes or claims about the identity of an institution/"whale".
Never publish supplied per-symbol snapshots from a public Actions job.
The point-in-time integrity, vendor licensing and full tick capture are
NOT established by this synthetic/offline research contract.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re

SCHEMA_EOD = "XRAY_NASDAQ_A36_EOD_RESEARCH_INPUT_V1"
SCHEMA_TICK = "XRAY_NASDAQ_A36_TICK_RESEARCH_INPUT_V1"
SCHEMA_REPORT = "XRAY_NASDAQ_A36_RESEARCH_OUTPUT_V1"
SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,15}\Z")
ALLOWED_FEEDS = frozenset(("IEX", "SIP"))
DENIAL = {
    "may_change_production_al": False,
    "may_change_stops_or_targets": False,
    "may_write_sheet": False,
    "may_send_notification": False,
    "may_place_order": False,
    "whale_identity_verified": False,
    "whole_market_buy_sell_proven": False,
}


class FlowBlocked(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise FlowBlocked(reason)


def finite(value, *, positive=True):
    need(type(value) in (int, float) and math.isfinite(value) and
         (value > 0 if positive else value >= 0), "INVALID_NUMERIC")
    return float(value)


def utc_stamp(value):
    need(isinstance(value, str), "BAD_TIMESTAMP")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FlowBlocked("BAD_TIMESTAMP") from None
    need(d.tzinfo is not None and d.utcoffset() == timedelta(0), "UTC_REQUIRED")
    return d.astimezone(timezone.utc)


def common(doc, schema):
    need(type(doc) is dict and doc.get("schema") == schema, "BAD_SCHEMA")
    symbol = doc.get("symbol")
    need(type(symbol) is str and bool(SYMBOL.fullmatch(symbol)), "BAD_SYMBOL")
    need(doc.get("provider") == "ALPACA" and doc.get("feed") in ALLOWED_FEEDS,
         "PROVIDER_OR_FEED_UNTRUSTED")
    need(doc.get("basis") == "RAW", "NOT_RAW_PRICE_BASIS")
    return symbol


def evaluate_eod(doc):
    """Descriptive daily IEX/SIP price-volume proxy, NOT signed order flow.

    52 contiguous, actual XNAS sessions, exact EOD date and post-close cutoff.
    Does not attest original timestamp-of-knowledge or corporate actions.
    """
    common(doc, SCHEMA_EOD)
    import exchange_calendars as ec
    cal = ec.get_calendar("XNAS")
    asof = doc.get("asof_et")
    need(type(asof) is str and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof)),
         "BAD_ASOF")
    try:
        is_session = cal.is_session(asof)
    except (ValueError, TypeError, OverflowError):
        raise FlowBlocked("INVALID_CALENDAR_DATE") from None
    need(is_session, "NOT_XNAS_SESSION")
    try:
        expected = [str(s.date()) for s in
                    cal.sessions_window(cal.date_to_session(asof), -52)]
    except (ValueError, TypeError, OverflowError):
        raise FlowBlocked("INVALID_CALENDAR_DATE") from None
    cutoff = utc_stamp(doc.get("cutoff_utc"))
    need(cutoff >= cal.session_close(asof).to_pydatetime()
         + timedelta(minutes=45), "EOD_NOT_YET_FINAL")
    bars = doc.get("bars")
    need(type(bars) is list and len(bars) == 52, "EXACT_52_BARS_REQUIRED")
    need([b.get("session") if type(b) is dict else None for b in bars]
         == expected, "NONCONTIGUOUS_52_XNAS_SESSIONS")
    valid = []
    for b in bars:
        o, h, l, c, v = (finite(b.get(k)) for k in
                         ("open", "high", "low", "close", "volume"))
        need(l <= o <= h and l <= c <= h, "BAD_OHLC_GEOMETRY")
        valid.append((o, h, l, c, v))
    prior = valid[-21:-1]
    last = valid[-1]
    volume_mean = sum(x[4] for x in prior) / 20.0
    rvol = last[4] / volume_mean
    price_change = (last[3] / prior[-1][3]) - 1.0
    spread = last[1] - last[2]
    close_location = ((2 * last[3] - last[1] - last[2]) / spread
                      if spread else None)
    # This is descriptive candle geometry, NOT real buyer/seller initiative.
    if close_location is None:
        tag = "ZERO_RANGE_UNKNOWN"
    elif rvol >= 1.30 and price_change > 0 and close_location >= 0.50:
        tag = "EOD_UP_VOLUME_PROXY"
    elif rvol >= 1.30 and price_change < 0 and close_location <= -0.50:
        tag = "EOD_DOWN_VOLUME_PROXY"
    else:
        tag = "EOD_MIXED_OR_UNINFORMATIVE"
    return {
        "schema": SCHEMA_REPORT,
        "layer": "DAILY_PRICE_VOLUME_PROXY",
        "asof_et": asof,
        "source_feed": doc["feed"],
        "sessions": 52,
        "rvol20": round(rvol, 6),
        "price_return_pct": round(price_change * 100, 6),
        "close_location": (round(close_location, 6)
                           if close_location is not None else None),
        "volume_percentile_prior20": round(
            100 * sum(x[4] <= last[4] for x in prior) / 20, 1),
        "dollar_turnover_close_proxy": round(last[3] * last[4], 2),
        "research_tag": tag,
        "signed_order_flow": "UNAVAILABLE_FROM_OHLCV",
        "corporate_action_source_verified": False,
        "point_in_time_originality_verified": False,
        "data_license_independently_verified": False,
        "research_thresholds_validated": False,
        **DENIAL,
    }


def evaluate_ticks(doc, *, max_age_ms=1000, max_spread_pct=1.0):
    """Sample-only quote-mid inferred aggressor. Never call it whale buying.

    Quote MUST precede trade. Odd-lot/non-standard conditions remain UNKNOWN.
    The thresholds are declared pilot assumptions, not optimized.
    No paging provenance is accepted from caller: sample is always incomplete.
    """
    common(doc, SCHEMA_TICK)
    need(type(max_age_ms) is int and 1 <= max_age_ms <= 1000,
         "BAD_AGE_POLICY")
    need(type(max_spread_pct) in (int, float)
         and math.isfinite(max_spread_pct) and 0 < max_spread_pct <= 1,
         "BAD_SPREAD_POLICY")
    start, end = utc_stamp(doc.get("window_start_utc")), utc_stamp(doc.get("window_end_utc"))
    cutoff = utc_stamp(doc.get("cutoff_utc"))
    need(start < end <= cutoff and (end-start) <= timedelta(minutes=5),
         "INVALID_OR_FUTURE_SAMPLE_WINDOW")
    trades, quotes = doc.get("trades"), doc.get("quotes")
    need(type(trades) is list and type(quotes) is list,
         "TRADE_QUOTE_LIST_REQUIRED")
    # Hard stop on excessive offline input and unknown / unverified data shape.
    need(len(trades) <= 100000 and len(quotes) <= 100000,
         "SAMPLE_LIMIT_EXCEEDED")
    qtimes = []
    qdata = []
    for quote in quotes:
        need(type(quote) is dict, "BAD_QUOTE")
        tm = utc_stamp(quote.get("timestamp"))
        need(start <= tm <= end, "QUOTE_OUT_OF_WINDOW")
        if qtimes:
            need(tm >= qtimes[-1], "UNSORTED_QUOTES")
        qtimes.append(tm)
        qdata.append(quote)
    ttimes = []
    seen = set()
    counts = {"INFERRED_BUY": 0, "INFERRED_SELL": 0, "UNKNOWN": 0}
    reasons = {"NONSTANDARD_CONDITION": 0, "NO_PRIOR_QUOTE": 0,
               "STALE_QUOTE": 0, "WIDE_OR_INVALID_SPREAD": 0,
               "TRADE_AT_MID": 0}
    buy_size = sell_size = unknown_size = 0.0
    for trade in trades:
        need(type(trade) is dict, "BAD_TRADE")
        tm = utc_stamp(trade.get("timestamp"))
        need(start <= tm <= end, "TRADE_OUT_OF_WINDOW")
        if ttimes:
            need(tm >= ttimes[-1], "UNSORTED_TRADES")
        ttimes.append(tm)
        exchange, ident = trade.get("exchange"), trade.get("id")
        need(type(exchange) is str and bool(exchange) and
             type(ident) in (int, str) and str(ident) != "",
             "TRADE_ID_MISSING")
        key = (exchange, str(ident))
        need(key not in seen, "DUPLICATE_TRADE_ID")
        seen.add(key)
        price = finite(trade.get("price"))
        size = finite(trade.get("size"))
        conditions = trade.get("conditions")
        need(type(conditions) is list and
             all(type(c) is str for c in conditions), "BAD_TRADE_CONDITIONS")
        why = None
        if conditions != ["@"]:
            why = "NONSTANDARD_CONDITION"
        else:
            ix = bisect_right(qtimes, tm) - 1
            if ix < 0:
                why = "NO_PRIOR_QUOTE"
            else:
                q = qdata[ix]
                age_ms = (tm - qtimes[ix]).total_seconds() * 1000
                if age_ms > max_age_ms:
                    why = "STALE_QUOTE"
                else:
                    bid = q.get("bid_price")
                    ask = q.get("ask_price")
                    # Do not throw for a malformed single quote: discard the
                    # inferential classification and record evidence loss.
                    if (type(bid) not in (int,float) or
                        type(ask) not in (int,float) or
                        not math.isfinite(bid) or not math.isfinite(ask) or
                        bid <= 0 or ask <= bid or
                        200 * (ask-bid) / (ask+bid) > max_spread_pct):
                        why = "WIDE_OR_INVALID_SPREAD"
                    else:
                        middle = (bid+ask)/2
                        if price > middle:
                            counts["INFERRED_BUY"] += 1
                            buy_size += size
                        elif price < middle:
                            counts["INFERRED_SELL"] += 1
                            sell_size += size
                        else:
                            why = "TRADE_AT_MID"
        if why is not None:
            counts["UNKNOWN"] += 1
            reasons[why] += 1
            unknown_size += size
    all_count = len(trades)
    known = counts["INFERRED_BUY"] + counts["INFERRED_SELL"]
    return {
        "schema": SCHEMA_REPORT,
        "layer": "SAMPLE_QUOTE_MID_INFERENCE",
        "source_feed": doc["feed"],
        "sample_window_seconds": round((end-start).total_seconds(), 3),
        "trade_count_sampled": all_count,
        "quote_count_sampled": len(quotes),
        "classified_count": known,
        "unclassified_count": counts["UNKNOWN"],
        "classified_ratio": round(known/all_count, 6) if all_count else 0,
        "inferred_buy_trades": counts["INFERRED_BUY"],
        "inferred_sell_trades": counts["INFERRED_SELL"],
        "unknown_reasons": reasons,
        "inferred_buy_shares": round(buy_size, 6),
        "inferred_sell_shares": round(sell_size, 6),
        "unknown_shares": round(unknown_size, 6),
        "sample_pagination_and_venue_completeness": "NOT_ATTESTED",
        "aggressor_classification": "INFERRED_NOT_GROUND_TRUTH",
        "whale_activity": "UNKNOWN_NOT_IDENTIFIABLE",
        "quote_age_policy_ms": max_age_ms,
        "max_spread_policy_pct": float(max_spread_pct),
        "policy_sensitivity_tested": False,
        **DENIAL,
    }


def evaluate_cohort(doc):
    """477 exact, immutable-watchlist-scoped offline aggregation, no signal leak.

    This verifies submitted snapshots against a caller-supplied scope SHA; it
    does not authenticate that the caller actually used the owner's watchlist
    or collected all raw provider pages from Alpaca.
    """
    import hashlib
    need(type(doc) is dict and doc.get("schema") ==
         "XRAY_NASDAQ_A36_COHORT_RESEARCH_INPUT_V1", "BAD_COHORT_SCHEMA")
    watchlist = doc.get("watchlist")
    need(type(watchlist) is list and len(watchlist) == 477 and
         len(set(watchlist)) == 477 and
         all(type(x) is str and SYMBOL.fullmatch(x) for x in watchlist),
         "COHORT_WATCHLIST_NOT_EXACT_477")
    digest = hashlib.sha256(("\n".join(watchlist)+"\n").encode()).hexdigest()
    sha = doc.get("expected_scope_sha256")
    need(type(sha) is str and bool(re.fullmatch(r"[0-9a-f]{64}", sha))
         and sha == digest, "COHORT_SCOPE_SHA_CONFLICT")
    series = doc.get("snapshots")
    need(type(series) is list and len(series) == 477, "COHORT_COVERAGE_INCOMPLETE")
    keys = [x.get("symbol") if type(x) is dict else None for x in series]
    need(len(set(keys)) == 477 and set(keys) == set(watchlist),
         "COHORT_MISSING_DUPLICATE_OR_EXTRA_SYMBOL")
    asofs = {x.get("asof_et") for x in series}
    need(len(asofs) == 1, "COHORT_ASOF_MIXED")
    tags = {}
    for item in series:
        need(item.get("feed") == "IEX", "COHORT_PRODUCTION_SOURCE_NOT_IEX")
        sample = evaluate_eod(item)
        tag = sample["research_tag"]
        tags[tag] = tags.get(tag, 0) + 1
    return {
        "schema": SCHEMA_REPORT,
        "layer": "FULL_SCOPE_EOD_PROXY_OFFLINE_ONLY",
        "asof_et": series[0]["asof_et"],
        "scope_sha256": digest,
        "supplied_symbols_validated": 477,
        "supplied_sessions_validated": 52,
        "research_tags": tags,
        "live_provider_collection_proven": False,
        "real_trade_quote_side_proven": False,
        "research_status": "OFFLINE_COHORT_VALIDATION_NOT_PRODUCTION",
        **DENIAL,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="A36 local-only research; no network")
    parser.add_argument("--mode", choices=("eod", "ticks", "cohort"), required=True)
    parser.add_argument("--input", required=True,
                        help="Private local snapshot JSON. NEVER commit it.")
    args = parser.parse_args(argv)
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = (evaluate_eod(data) if args.mode == "eod" else
                  evaluate_ticks(data) if args.mode == "ticks" else
                  evaluate_cohort(data))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        # Source text, symbol, private rows and credentials NEVER logged.
        print("XRAY_A36_RESEARCH=BLOCKED_NO_AL_NO_WRITES_NO_ALERTS")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
