#!/usr/bin/env python3
"""A36 bounded historical trade+quote collector (manual, DATA ONLY, no broker).

No cron, no private Sheet, no notifications, no orders, no raw data persisted.
Single-symbol read-only Alpaca REST. Only aggregate metrics printed.
This is a pilot; response-page completion cannot certify tape coverage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flow_shadow_a36 import (
    FlowBlocked, SCHEMA_TICK, SYMBOL, ALLOWED_FEEDS, need, utc_stamp,
    evaluate_ticks,
)

HOST = "https://data.alpaca.markets"
MAX_SYMBOLS = 5
MAX_SECONDS = 60
PAGE_LIMIT = 1000
MAX_PAGES = 30
MAX_RECORDS = 30000


def get_page(url, headers, *, request_json=None):
    """Only data.alpaca.markets GET; never accept arbitrary URL hosts."""
    need(type(url) is str and url.startswith(HOST+"/v2/stocks/"),
         "NOT_ALLOWED_DATA_ONLY_HOST")
    if request_json is not None:
        return request_json(url, headers)
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=20) as response:
            need(response.status == 200, "PROVIDER_NON_200")
            return json.load(response)
    except Exception:
        raise FlowBlocked("PROVIDER_DATA_READ_FAILED") from None


def fetch_pages(symbol, kind, feed, start, end, headers, *, request_json=None):
    """API reports next_page_token; enforce every page, limit and dedup."""
    need(kind in ("trades", "quotes") and
         type(symbol) is str and bool(SYMBOL.fullmatch(symbol)) and
         feed in ALLOWED_FEEDS, "INVALID_REQUEST_SCOPE")
    # The user cannot inject endpoint paths, feeds, broker URLs or arbitrary hosts.
    endpoint = HOST + "/v2/stocks/" + symbol + "/" + kind
    seen_tokens = set()
    pages = 0
    rows = []
    token = None
    while pages < MAX_PAGES:
        query = {"start": start, "end": end, "limit": PAGE_LIMIT,
                 "sort": "asc", "feed": feed.lower()}
        if token:
            query["page_token"] = token
        payload = get_page(endpoint + "?" + urlencode(query), headers,
                           request_json=request_json)
        need(type(payload) is dict and type(payload.get(kind)) is list,
             "BAD_PROVIDER_PAGE")
        batch = payload[kind]
        need(len(batch) <= PAGE_LIMIT and all(type(x) is dict for x in batch),
             "INVALID_OR_OVERSIZED_PAGE")
        rows.extend(batch)
        pages += 1
        need(len(rows) <= MAX_RECORDS, "PILOT_RECORD_CAP_EXCEEDED")
        nxt = payload.get("next_page_token")
        if nxt in (None, ""):
            return rows, pages
        need(type(nxt) is str and nxt not in seen_tokens,
             "BAD_OR_REPEATED_PAGE_TOKEN")
        seen_tokens.add(nxt)
        token = nxt
    raise FlowBlocked("PILOT_UNFINISHED_PAGINATION_FAIL_CLOSED")


def normalized_trades(rows):
    results = []
    for r in rows:
        need(all(k in r for k in ("t", "x", "p", "s", "i", "c")),
             "MISSING_RAW_TRADE_FIELD")
        results.append({
            "timestamp": r["t"], "exchange": r["x"], "price": r["p"],
            "size": r["s"], "id": r["i"], "conditions": r["c"],
        })
    return results


def normalized_quotes(rows):
    results = []
    for r in rows:
        need(all(k in r for k in ("t", "bp", "ap")),
             "MISSING_RAW_QUOTE_FIELD")
        results.append({"timestamp": r["t"], "bid_price": r["bp"],
                        "ask_price": r["ap"]})
    return results


def pilot(*, symbols, feed, start_utc, end_utc, key, secret,
          now_utc=None, request_json=None):
    need(type(symbols) is list and 1 <= len(symbols) <= MAX_SYMBOLS and
         len(set(symbols)) == len(symbols) and
         all(type(s) is str and SYMBOL.fullmatch(s) for s in symbols),
         "PILOT_SCOPE_NOT_ONE_TO_FIVE_SYMBOLS")
    need(feed in ALLOWED_FEEDS, "PILOT_FEED_NOT_EXACT")
    need(type(key) is str and bool(key) and type(secret) is str and bool(secret),
         "MISSING_DATA_ONLY_CREDENTIALS")
    start, end = utc_stamp(start_utc), utc_stamp(end_utc)
    now = now_utc or datetime.now(timezone.utc)
    need(now.tzinfo is not None and now.utcoffset() == timedelta(0),
         "INVALID_NOW_UTC")
    need(start < end and (end-start).total_seconds() <= MAX_SECONDS,
         "PILOT_WINDOW_EXCEEDS_60_SECONDS")
    need(end + timedelta(minutes=20) <= now,
         "PILOT_HISTORICAL_EMBARGO_NOT_MET")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
               "Accept": "application/json",
               "User-Agent": "xray-nasdaq-a36-readonly-pilot"}
    counts = {"qualified_trade_count": 0, "unknown_trade_count": 0,
              "inferred_buy_trade_count": 0, "inferred_sell_trade_count": 0,
              "trade_pages": 0, "quote_pages": 0}
    unknown_reasons = {}
    for symbol in symbols:
        trades, tpages = fetch_pages(symbol, "trades", feed, start_utc,
                                     end_utc, headers, request_json=request_json)
        quotes, qpages = fetch_pages(symbol, "quotes", feed, start_utc,
                                     end_utc, headers, request_json=request_json)
        document = {"schema": SCHEMA_TICK, "provider": "ALPACA",
                    "feed": feed, "symbol": symbol, "basis": "RAW",
                    "window_start_utc": start_utc, "window_end_utc": end_utc,
                    "cutoff_utc": now.isoformat(),
                    "trades": normalized_trades(trades),
                    "quotes": normalized_quotes(quotes)}
        result = evaluate_ticks(document)
        counts["qualified_trade_count"] += result["classified_count"]
        counts["unknown_trade_count"] += result["unclassified_count"]
        counts["inferred_buy_trade_count"] += result["inferred_buy_trades"]
        counts["inferred_sell_trade_count"] += result["inferred_sell_trades"]
        counts["trade_pages"] += tpages
        counts["quote_pages"] += qpages
        for reason, quantity in result["unknown_reasons"].items():
            unknown_reasons[reason] = unknown_reasons.get(reason, 0) + quantity
    return {
        "schema": "XRAY_NASDAQ_A36_BOUNDED_READONLY_PILOT_V1",
        "requested_feed": feed, "symbol_count": len(symbols),
        "window_duration_seconds": (end-start).total_seconds(),
        "source_response_pagination_chain_completed": True,
        "full_market_venue_and_correction_coverage_attested": False,
        "provider_entitlement_and_license_independently_verified": False,
        "institutional_identity_verified": False,
        "pilot_outcome": "SAMPLE_ONLY_NOT_AN_AL_OR_WHALE_EVENT",
        "aggregate_counts": counts, "aggregate_unknown_reasons": unknown_reasons,
        "raw_trade_or_quote_data_retained": False, "may_change_al": False,
        "may_write_sheets": False, "may_emit_alert": False, "orders": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="manual one-minute Alpaca DATA-only pilot")
    p.add_argument("--symbols", required=True, help="1..5 exact NASDAQ symbols comma separated")
    p.add_argument("--feed", required=True, choices=["IEX", "SIP"])
    p.add_argument("--start-utc", required=True, help="UTC ISO-8601 timestamp")
    p.add_argument("--end-utc", required=True, help="UTC ISO-8601 timestamp")
    a = p.parse_args(argv)
    try:
        result = pilot(
            symbols=a.symbols.split(","), feed=a.feed,
            start_utc=a.start_utc, end_utc=a.end_utc,
            key=os.getenv("XRAY_ALPACA_DATA_KEY_ID", ""),
            secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY", ""),
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print("XRAY_A36_PILOT=BLOCKED_NO_PRIVATE_DATA_PUBLISHED_NO_AL_OR_ORDERS")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
