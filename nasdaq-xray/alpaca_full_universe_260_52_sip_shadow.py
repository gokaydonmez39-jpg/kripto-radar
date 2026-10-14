#!/usr/bin/env python3
"""Personal completed-session full-NASDAQ 260 daily / 52 week SIP census.

Source is exact current SINA identity queue; raw vendor OHLCV ephemeral only.
This proves neither issuer continuity, official RTH DV30, MC, G9 nor R92.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import time

from alpaca_full_universe_asof_sip_availability import (
    scope, historical_request_window, sha)
from alpaca_full_scope_260_shadow import classify
from alpaca_free_sip_shadow_guard import request_batch
from alpaca_sip_paginated_transport_shadow import SYMBOL_RE
from current_history_source_request import expected_dates

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1"
BATCH = 32
MAX_SYMBOLS = 6500


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_FULL_NASDAQ_SIP_260_" + reason)


def audit(asof, symbols, daily, weekly, fetch, pacing=0):
    need(len(symbols) > 0 and len(symbols) <= MAX_SYMBOLS
         and symbols == sorted(set(symbols)), "IDENTITY_SCOPE")
    need(len(daily) == 260 and daily[-1] == asof and
         len(weekly) == 52 and weekly == sorted(set(weekly)),
         "260_52_OFFICIAL_SESSION_DATES")
    labels = {}
    calls = 0
    transport = None
    for i in range(0, len(symbols), BATCH):
        group = symbols[i:i+BATCH]
        if transport is not None:
            for name in group:
                labels[name] = transport
            continue
        valid = [sym for sym in group if SYMBOL_RE.fullmatch(sym)]
        for sym in group:
            if sym not in valid:
                labels[sym] = "UNKNOWN_SYMBOL_MALFORMED_FOR_PROVIDER"
        if not valid:
            continue
        try:
            received = fetch(valid, daily, asof)
            need(type(received) is dict and set(received).issubset(set(valid)),
                 "UNEXPECTED_PROVIDER_SYMBOL_OR_FORMAT")
            calls += 1
            for sym in valid:
                status, observed = classify(received.get(sym, []),
                                            daily, weekly, asof)
                need(type(status) is str and
                     type(observed) is int and 0 <= observed <= 260,
                     "HISTORY_CLASSIFIER_INVALID")
                labels[sym] = status
        except (RuntimeError, ValueError, TimeoutError, OSError) as e:
            v = str(e)
            # Preserve known HTTP and pagination classes, never raw responses.
            transport = (v if v.startswith(("ALPACA_HTTP_", "ALPACA_PAGE_"))
                         else "UNKNOWN_PROVIDER_TRANSPORT_OR_INTEGRITY")
            for sym in valid:
                labels[sym] = transport
        if pacing:
            time.sleep(pacing)
    need(set(labels) == set(symbols), "ALL_IDENTITY_PARTITION_REQUIRED")
    counts = dict(sorted(collections.Counter(labels.values()).items()))
    return labels, counts, calls, transport


def report(asof, names, daily, weekly, fetch, pacing=0):
    labels, counts, calls, transport = audit(
        asof, names, daily, weekly, fetch, pacing)
    ready = counts.get("SHADOW_260_DAILY_52_WEEK_OBSERVED", 0)
    need(sum(counts.values()) == len(names) and
         ready <= len(names), "COUNTS")
    return {
        "schema": SCHEMA, "asof_et": asof,
        "source_full_identity_queue_sha256": sha(names),
        "scope_count": len(names), "classified_count": len(labels),
        "session_count": 260, "weekly_close_count": 52,
        "source": "ALPACA_HISTORICAL_SIP_RAW_ADJUSTMENT",
        "full_history_260_52_observed_count": ready,
        "full_history_missing_or_unknown_count": len(names)-ready,
        "classification_counts": counts,
        "symbol_classifications": dict(sorted(labels.items())),
        "api_batch_calls": calls, "transport_stop_class": transport,
        "status": ("SHADOW_FULL_IDENTITY_MEASURED_NO_AUTHORITY"
                   if transport is None else
                   "SHADOW_PARTIAL_SOURCE_FAILURE_NO_AUTHORITY"),
        "source_rights_not_inferred": True,
        "same_issuer_first_trade_not_independently_proven": True,
        "official_rth_volume_not_attested": True,
        "adjusted_history_not_primary_attested": True,
        "canonical_price_history_mc_untouched": True,
        "registered_R92_count": 0, "no_vendor_ohlcv_persisted": True,
        "execution": "NONE", "real_money": "NO-GO",
    }


def selftest():
    asof = "2026-10-14"
    daily, weekly = expected_dates(asof)
    need(len(daily) == 260 and len(weekly) == 52, "EXPECTED_DATES")
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    def bar(day):
        stamp = dt.datetime.combine(dt.date.fromisoformat(day),
                                    dt.time(), ny)
        return {"t": stamp.astimezone(dt.timezone.utc).isoformat(),
                "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}
    good = [bar(day) for day in daily]
    def fake(group, expected, date):
        need(date == asof and expected == daily, "FAKE_BOUND")
        return {sym: (good if sym == "AAA" else good[:-1])
                for sym in group}
    result = report(asof, ["AAA", "BBB"], daily, weekly, fake)
    need(result["full_history_260_52_observed_count"] == 1 and
         result["classification_counts"]["MISSING_EXACT_COMPLETED_SESSIONS"] == 1
         and result["registered_R92_count"] == 0, "POSITIVE_AND_MISSING")
    def limited(group, expected, date):
        raise RuntimeError("ALPACA_HTTP_429")
    z = report(asof, ["AAA", "BBB"], daily, weekly, limited)
    need(z["classification_counts"] == {"ALPACA_HTTP_429": 2}
         and z["api_batch_calls"] == 0 and z["transport_stop_class"] ==
         "ALPACA_HTTP_429", "RATE_LIMIT_HARD_STOP")
    def foreign(group, expected, date):
        return {"OUTSIDE": good}
    w = report(asof, ["AAA", "BBB"], daily, weekly, foreign)
    need(w["full_history_260_52_observed_count"] == 0 and
         w["transport_stop_class"] ==
         "UNKNOWN_PROVIDER_TRANSPORT_OR_INTEGRITY", "FOREIGN_FAIL_CLOSED")
    try:
        audit(asof, ["AAA", "AAA"], daily, weekly, fake)
    except ValueError as exc:
        need("IDENTITY_SCOPE" in str(exc), "DUPLICATE_REASON")
    else:
        raise AssertionError("DUPLICATE_ACCEPTED")
    # Request window never asks Basic account for future/current 15min data.
    start, end = historical_request_window(
        asof, dt.datetime(2026, 10, 14, 22, tzinfo=dt.timezone.utc))
    need(start.endswith("-04:00") and
         end == "2026-10-14T20:05:00+00:00",
         "OFFICIAL_CLOSE_NO_FUTURE")
    print("XRAY_FULL_NASDAQ_260_52_SIP_SELFTEST=PASS_260_52_FAIL_CLOSED_RATE_LIMIT_NO_ALPHA")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    need(args.out is not None and
         not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "FORBID_VENDOR_OR_REPORT_COMMIT")
    root = json.loads((ROOT/"orchestrator_state.json").read_text())
    state = json.loads((ROOT/"sina_state.json").read_text())
    now = dt.datetime.now(dt.timezone.utc)
    asof, names = scope(state, root, now)
    daily, weeks = expected_dates(asof)
    _, end = historical_request_window(asof, now)
    start = (dt.datetime.combine(dt.date.fromisoformat(daily[0]),
                                 dt.time(), dt.timezone.utc)
             ).isoformat(timespec="seconds")
    key = os.environ["XRAY_ALPACA_DATA_KEY_ID"]
    secret = os.environ["XRAY_ALPACA_DATA_SECRET_KEY"]
    def fetch(batch, dates, day):
        return request_batch(batch, start, end, key, secret,
                             adjustment="raw", asof=day)
    result = report(asof, names, daily, weeks, fetch, pacing=0.2)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")
    print("XRAY_FULL_NASDAQ_260_52_SIP_CENSUS="+json.dumps({
        "asof_et":asof, "scope":result["scope_count"],
        "observed":result["full_history_260_52_observed_count"],
        "not_proven":result["full_history_missing_or_unknown_count"],
        "counts":result["classification_counts"],
        "source_stop":result["transport_stop_class"],
        "api_calls":result["api_batch_calls"]},sort_keys=True))


if __name__ == "__main__":
    main()
