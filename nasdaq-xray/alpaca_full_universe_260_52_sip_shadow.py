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
from alpaca_free_sip_shadow_guard import timestamp_date
import math
from alpaca_free_sip_shadow_guard import request_batch
from alpaca_sip_paginated_transport_shadow import SYMBOL_RE
from current_history_source_request import expected_dates
from official_first_trade_260_history_guard import fence as official_first_trade_fence

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1"
BATCH = 32
MAX_SYMBOLS = 6500


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_FULL_NASDAQ_SIP_260_" + reason)


def cause_of_nonpass(rows, label, official_days):
    """Partition negative history cases by exact defect; never upgrade to PASS.

    Returns only labels; vendor values and timestamps stay ephemeral in memory.
    """
    if label == "SHADOW_260_DAILY_52_WEEK_OBSERVED":
        return "260_52_OBSERVED_RESEARCH_ONLY"
    if label == "NO_BAR":
        return "NO_SOURCE_BAR"
    if label == "INVALID_OHLCV_OR_ZERO_VOLUME":
        flags = set()
        for row in rows:
            if not isinstance(row, dict):
                return "BAD_BAR_OBJECT"
            try:
                o, h, l, c, v = (row[k] for k in ("o", "h", "l", "c", "v"))
                if any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) for x in (o, h, l, c, v)):
                    return "MALFORMED_OR_NONFINITE_BAR"
                if v <= 0:
                    flags.add("ZERO_OR_NEGATIVE_RECORDED_VOLUME")
                if min(o, h, l, c) <= 0:
                    flags.add("NONPOSITIVE_RECORDED_PRICE")
                if h < max(o, l, c) or l > min(o, c):
                    flags.add("OHLC_GEOMETRY_CONFLICT")
            except (KeyError, ValueError, TypeError):
                return "MALFORMED_BAR_FIELDS"
        return "+".join(sorted(flags)) if flags else "INVALID_CAUSE_NOT_REPRODUCED"
    if label == "MISSING_EXACT_COMPLETED_SESSIONS":
        observed = set()
        for row in rows:
            try:
                observed.add(timestamp_date(row["t"]).isoformat())
            except (KeyError, TypeError, ValueError, OverflowError):
                return "MISSING_WITH_BAD_TIMESTAMPS"
        lacking = set(official_days) - observed
        n = len(lacking)
        if n == 0:
            return "MISSING_REASON_NOT_REPRODUCED"
        if official_days[-1] in lacking:
            return "MISSING_CURRENT_ASOF_AND_" + (
                "1_TO_5_DAYS" if n <= 5 else
                "6_TO_30_DAYS" if n <= 30 else "OVER_30_DAYS")
        # A leading-only gap is consistent with a newly listed issuer,
        # BUT is not proof of an IPO or first trade. It needs official
        # issuer evidence; an interior hole calls for source integrity work.
        if set(official_days[:n]) == lacking:
            return "MISSING_LEADING_ONLY_IPO_OR_MAPPING_UNPROVEN_" + (
                "1_TO_5" if n <= 5 else
                "6_TO_30" if n <= 30 else "OVER_30")
        return ("MISSING_INTERIOR_OR_MIXED_1_TO_5_DAYS" if n <= 5 else
                "MISSING_INTERIOR_OR_MIXED_6_TO_30_DAYS" if n <= 30 else
                "MISSING_INTERIOR_OR_MIXED_OVER_30_DAYS")
    return label


def audit(asof, symbols, daily, weekly, fetch, pacing=0,
          cause_labels=None):
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
                if cause_labels is not None:
                    cause_labels[name] = transport
            continue
        valid = [sym for sym in group if SYMBOL_RE.fullmatch(sym)]
        for sym in group:
            if sym not in valid:
                labels[sym] = "UNKNOWN_SYMBOL_MALFORMED_FOR_PROVIDER"
                if cause_labels is not None:
                    cause_labels[sym] = "UNKNOWN_SYMBOL_MALFORMED_FOR_PROVIDER"
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
                # Alpaca historical asof symbol mapping can return bars
                # belonging to a predecessor ticker occupant. A hard official
                # first-trade fence is FAIL-only and supersedes vendor count.
                issuer = official_first_trade_fence(sym, asof)
                if issuer and issuer["own_listed_history_short"]:
                    status = "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE"
                labels[sym] = status
                if cause_labels is not None:
                    cause_labels[sym] = (
                        "OFFICIAL_SAME_ISSUER_FIRST_TRADE_LT260_VETO"
                        if status == "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE"
                        else cause_of_nonpass(
                            received.get(sym, []), status, daily))
        except (RuntimeError, ValueError, TimeoutError, OSError) as e:
            v = str(e)
            # Preserve known HTTP and pagination classes, never raw responses.
            transport = (v if v.startswith(("ALPACA_HTTP_", "ALPACA_PAGE_"))
                         else "UNKNOWN_PROVIDER_TRANSPORT_OR_INTEGRITY")
            for sym in valid:
                labels[sym] = transport
                if cause_labels is not None:
                    cause_labels[sym] = transport
        if pacing:
            time.sleep(pacing)
    need(set(labels) == set(symbols), "ALL_IDENTITY_PARTITION_REQUIRED")
    counts = dict(sorted(collections.Counter(labels.values()).items()))
    return labels, counts, calls, transport


def report(asof, names, daily, weekly, fetch, pacing=0):
    causes = {}
    labels, counts, calls, transport = audit(
        asof, names, daily, weekly, fetch, pacing, cause_labels=causes)
    need(set(causes) == set(labels), "ALL_CAUSES_PARTITION")
    cause_counts = dict(sorted(collections.Counter(causes.values()).items()))
    need(sum(cause_counts.values()) == len(names), "CAUSE_COUNTS")
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
        "official_first_trade_fail_only_veto_count": counts.get(
            "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE", 0),
        "classification_counts": counts,
        "history_nonpass_cause_counts": cause_counts,
        "symbol_nonpass_cause_classes": dict(sorted(causes.items())),
        "cause_labels_are_diagnostics_not_ticker_age_or_verified_history": True,
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
    need(result["history_nonpass_cause_counts"] == {
        "260_52_OBSERVED_RESEARCH_ONLY": 1,
        "MISSING_CURRENT_ASOF_AND_1_TO_5_DAYS": 1},
        "MISSING_SINGLE_CURRENT_DATE_CAUSE")
    need(result["full_history_260_52_observed_count"] == 1 and
         result["classification_counts"]["MISSING_EXACT_COMPLETED_SESSIONS"] == 1
         and result["registered_R92_count"] == 0, "POSITIVE_AND_MISSING")
    zero_volume = [dict(good[0], v=0)] + good[1:]
    need(cause_of_nonpass(zero_volume,
         classify(zero_volume, daily, weekly, asof)[0], daily) ==
         "ZERO_OR_NEGATIVE_RECORDED_VOLUME",
         "ZERO_RECORDED_VOLUME_NOT_OTHER_DEFECT")
    bad_geom = [dict(good[0], h=8)] + good[1:]
    need(cause_of_nonpass(bad_geom,
         classify(bad_geom, daily, weekly, asof)[0], daily) ==
         "OHLC_GEOMETRY_CONFLICT",
         "OHLC_GEOMETRY_NOT_VOLUME")
    before_asof = good[1:]
    need(cause_of_nonpass(before_asof,
         classify(before_asof, daily, weekly, asof)[0], daily) ==
         "MISSING_LEADING_ONLY_IPO_OR_MAPPING_UNPROVEN_1_TO_5",
         "LEADING_GAP_DOES_NOT_PROVE_IPO")
    interior = good[:120] + good[121:]
    need(cause_of_nonpass(interior,
         classify(interior, daily, weekly, asof)[0], daily) ==
         "MISSING_INTERIOR_OR_MIXED_1_TO_5_DAYS",
         "INTERIOR_HOLE_NEEDS_INDEPENDENT_RETRY")
    # Even vendor-supplied 260 rows may belong to an unrelated prior issuer.
    # BSP's official 2026-07-01 first-trade proof vetoes that false history.
    def false_predecessor(group, expected, date):
        return {sym: good for sym in group}
    issuer_test = report(asof, ["BSP"], daily, weekly, false_predecessor)
    need(issuer_test["full_history_260_52_observed_count"] == 0 and
         issuer_test["official_first_trade_fail_only_veto_count"] == 1 and
         issuer_test["symbol_nonpass_cause_classes"]["BSP"] ==
           "OFFICIAL_SAME_ISSUER_FIRST_TRADE_LT260_VETO",
         "TICKER_REUSE_NOT_ISSUER_HISTORY_PASS")
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
    print("XRAY_FULL_NASDAQ_260_52_SIP_SELFTEST=PASS_260_52_ISSUER_FIRST_TRADE_FAIL_ONLY_CAUSAL_DISAGGREGATION_NO_ALPHA")


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
        "official_first_trade_fail_veto":
            result["official_first_trade_fail_only_veto_count"],
        "counts":result["classification_counts"],
        "cause_counts":result["history_nonpass_cause_counts"],
        "source_stop":result["transport_stop_class"],
        "api_calls":result["api_batch_calls"]},sort_keys=True))


if __name__ == "__main__":
    main()
