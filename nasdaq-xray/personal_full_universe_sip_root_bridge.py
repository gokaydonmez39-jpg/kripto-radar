#!/usr/bin/env python3
"""Bind personal SIP research observations to exact current root identity.

The result is a SOURCE AVAILABILITY bridge, NEVER C4.17 PRICE, HISTORY,
MC, technical GO, AL, R92, or trading authority. No vendor OHLCV is exported.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

from alpaca_full_universe_asof_sip_availability import sha
from source_epoch_freshness_guard import last_complete_session

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_SIP_ROOT_SOURCE_BRIDGE_V1"
DAY = "XRAY_ALPACA_PERSONAL_UNIVERSE_ASOF_SIP_COVERAGE_V1"
HISTORY = "XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1"
PRESENT = "OBSERVED_SIP_DAILY_ASOF_SHADOW"
LONG = "SHADOW_260_DAILY_52_WEEK_OBSERVED"


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_PERSONAL_SIP_ROOT_BRIDGE_" + reason)


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode()
                        + b"\0" + raw).hexdigest()


def check_partition(doc, symbols, field, counts_field, expected_schema):
    need(type(doc) is dict and doc.get("schema") == expected_schema, "SCHEMA")
    labels = doc.get(field)
    counts = doc.get(counts_field)
    need(type(labels) is dict and set(labels) == set(symbols) and
         all(type(x) is str and len(x) > 0 for x in labels.values()),
         "EXACT_SYMBOL_LABEL_PARTITION")
    need(type(counts) is dict and
         all(type(x) is str and type(n) is int and n >= 0
             for x, n in counts.items()) and
         counts == dict(sorted(collections.Counter(labels.values()).items())),
         "COUNTS_NOT_PROVED_BY_SYMBOLS")
    return labels


def build(root, sina, daily, history, now, root_sha, sina_sha):
    need(type(root) is dict and type(sina) is dict and
         type(now) is dt.datetime and now.tzinfo is not None, "INPUTS")
    asof = last_complete_session(now)
    need(all(x.get("asof_et") == asof for x in
             (root, sina, daily, history)), "LATEST_SAME_SESSION_NOT_BOUND")
    need(root.get("execution") == sina.get("execution") ==
         daily.get("execution") == history.get("execution") == "NONE" and
         root.get("real_money") == sina.get("real_money") ==
         daily.get("real_money") == history.get("real_money") == "NO-GO",
         "EXECUTION_SAFETY")
    need(sina.get("unknown_never_pass") is True and
         daily.get("no_vendor_ohlcv_persisted") is True and
         history.get("no_vendor_ohlcv_persisted") is True and
         daily.get("no_canonical_promotion") is True and
         history.get("canonical_price_history_mc_untouched") is True and
         daily.get("registered_R92_count") == history.get("registered_R92_count")
         == 0, "NO_VENDOR_OR_ALPHA_PROMOTION")
    q = sina.get("queue")
    need(type(q) is list and len(q) > 0 and q == sorted(set(q))
         and all(type(x) is str and x for x in q), "SOURCE_QUEUE")
    fingerprint = sha(q)
    need(root.get("queue_hash") == sina.get("queue_hash") ==
         fingerprint and root.get("queue_total") ==
         sina.get("queue_total") == len(q), "SOURCE_IDENTITY_QUEUE_HASH")
    need(daily.get("source_sina_queue_sha256") ==
         history.get("source_full_identity_queue_sha256") ==
         fingerprint and
         daily.get("source_sina_queue_count") ==
         daily.get("measured_scope_count") == history.get("scope_count") ==
         history.get("classified_count") == len(q),
         "PROVIDER_SCOPE_NOT_EXACT")
    day = check_partition(daily, q, "symbol_classifications",
                          "classification_counts", DAY)
    hist = check_partition(history, q, "symbol_classifications",
                           "classification_counts", HISTORY)
    causes = check_partition(history, q, "symbol_nonpass_cause_classes",
                             "history_nonpass_cause_counts", HISTORY)
    need(history.get("cause_labels_are_diagnostics_not_ticker_age_or_verified_history")
         is True and history.get("source_rights_not_inferred") is True and
         history.get("same_issuer_first_trade_not_independently_proven")
         is True and history.get("official_rth_volume_not_attested") is True,
         "NO_SOURCE_AUTHORITY_INFERENCE")
    present = sum(x == PRESENT for x in day.values())
    long = sum(x == LONG for x in hist.values())
    need(present == daily["classification_counts"].get(PRESENT, 0)
         and long == history.get("full_history_260_52_observed_count")
         and long + history.get("full_history_missing_or_unknown_count") ==
         len(q) and history.get("official_first_trade_fail_only_veto_count") ==
         history["classification_counts"].get(
             "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE", 0),
         "HISTORY_METRICS_DRIFT")
    inconsistent = sorted(sym for sym in q
                          if hist[sym] == LONG and day[sym] != PRESENT)
    need(not inconsistent, "PROVIDER_DAILY_VS_260_CONTRADICTION")
    need(all(type(v) is str for v in causes.values()), "CAUSE_CODE")
    return {
        "schema": SCHEMA,
        "asof_et": asof,
        "root_git_blob_sha": root_sha,
        "sina_git_blob_sha": sina_sha,
        "exact_identity_queue_sha256": fingerprint,
        "identity_scope_count": len(q),
        "daily_asof_bar_observed": present,
        "daily_asof_unproven": len(q)-present,
        "260_daily_52_week_observed": long,
        "260_daily_52_week_unproven": len(q)-long,
        "official_first_trade_fail_only_veto_count":
            history["official_first_trade_fail_only_veto_count"],
        "nonpass_cause_counts": history["history_nonpass_cause_counts"],
        "same_asof_same_universe_join": True,
        "research_observations_not_canonical_pass": True,
        "no_issuer_identity_mapping_proof": True,
        "no_official_rth_exact_volume": True,
        "no_c417_dv30_or_mc_pass": True,
        "no_technical_or_event_clear": True,
        "no_vetted_r92_or_delivery": True,
        "no_vendor_ohlcv_persisted": True,
        "execution": "NONE",
        "real_money": "NO-GO",
        "status": "INDEPENDENT_SIP_CURRENT_ROOT_SOURCE_PROOF_NOT_C417_AL",
    }


def selftest():
    asof = "2026-10-14"
    now = dt.datetime(2026, 10, 14, 22, 0, tzinfo=dt.timezone.utc)
    syms = ["AAPL", "BSP"]
    fp = sha(syms)
    base = {"asof_et": asof, "execution": "NONE", "real_money": "NO-GO"}
    root = dict(base, queue_total=2, queue_hash=fp)
    sina = dict(root, queue=syms, unknown_never_pass=True)
    day = dict(base, schema=DAY, no_vendor_ohlcv_persisted=True,
               no_canonical_promotion=True, registered_R92_count=0,
               source_sina_queue_sha256=fp,
               source_sina_queue_count=2, measured_scope_count=2,
               symbol_classifications={
                   "AAPL": PRESENT, "BSP": "UNKNOWN_DAILY_MISSING_OR_INTEGRITY"},
               classification_counts={
                   PRESENT: 1, "UNKNOWN_DAILY_MISSING_OR_INTEGRITY": 1})
    hist = dict(base, schema=HISTORY, no_vendor_ohlcv_persisted=True,
                canonical_price_history_mc_untouched=True,
                registered_R92_count=0,
                source_full_identity_queue_sha256=fp,
                scope_count=2, classified_count=2,
                source_rights_not_inferred=True,
                same_issuer_first_trade_not_independently_proven=True,
                official_rth_volume_not_attested=True,
                cause_labels_are_diagnostics_not_ticker_age_or_verified_history=True,
                official_first_trade_fail_only_veto_count=1,
                full_history_260_52_observed_count=1,
                full_history_missing_or_unknown_count=1,
                symbol_classifications={
                    "AAPL": LONG,
                    "BSP": "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE"},
                classification_counts={
                    LONG: 1, "FAIL_OWN_ISSUER_LT260_OFFICIAL_FIRST_TRADE": 1},
                symbol_nonpass_cause_classes={
                    "AAPL": "260_52_OBSERVED_RESEARCH_ONLY",
                    "BSP": "OFFICIAL_SAME_ISSUER_FIRST_TRADE_LT260_VETO"},
                history_nonpass_cause_counts={
                    "260_52_OBSERVED_RESEARCH_ONLY": 1,
                    "OFFICIAL_SAME_ISSUER_FIRST_TRADE_LT260_VETO": 1})
    import copy
    valid = build(root, sina, day, hist, now, "a"*40, "b"*40)
    need(valid["daily_asof_bar_observed"] == 1
         and valid["260_daily_52_week_observed"] == 1
         and valid["no_c417_dv30_or_mc_pass"], "POSITIVE_NO_AUTHORITY")
    trials = [
        (lambda r,s,d,h: d.update(asof_et="2026-10-13"), "LATEST_SAME_SESSION"),
        (lambda r,s,d,h: s.update(queue=["BSP", "AAPL"]), "SOURCE_QUEUE"),
        (lambda r,s,d,h: r.update(queue_hash="z"*64), "SOURCE_IDENTITY_QUEUE"),
        (lambda r,s,d,h: d["symbol_classifications"].update(AAPL="UNKNOWN"),
         "COUNTS_NOT_PROVED"),
        (lambda r,s,d,h: (
            d["symbol_classifications"].update(
                AAPL="UNKNOWN_DAILY_MISSING_OR_INTEGRITY"),
            d["classification_counts"].clear(),
            d["classification_counts"].update(
                {"UNKNOWN_DAILY_MISSING_OR_INTEGRITY": 2})),
         "PROVIDER_DAILY_VS_260_CONTRADICTION"),
        (lambda r,s,d,h: h.update(registered_R92_count=1),
         "NO_VENDOR_OR_ALPHA"),
        (lambda r,s,d,h: h["symbol_classifications"].update(BSP=LONG),
         "COUNTS_NOT_PROVED"),
        (lambda r,s,d,h: h.update(source_full_identity_queue_sha256="x"*64),
         "PROVIDER_SCOPE_NOT_EXACT"),
        (lambda r,s,d,h: h.update(official_rth_volume_not_attested=False),
         "NO_SOURCE_AUTHORITY"),
    ]
    for change, reason in trials:
        r, s, d, h = (copy.deepcopy(x) for x in (root, sina, day, hist))
        change(r, s, d, h)
        try:
            build(r, s, d, h, now, "a"*40, "b"*40)
        except ValueError as exc:
            need(reason in str(exc), "NEGATIVE_REASON_" + reason)
        else:
            raise AssertionError("UNSAFE_RESEARCH_BRIDGE_ACCEPTED_" + reason)
    print("XRAY_PERSONAL_SIP_ROOT_BRIDGE_SELFTEST=PASS_9_NEGATIVES_EXACT_QUEUE_EPOCH_NO_ALPHA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--daily", type=Path)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    need(all(x is not None and x.is_file() for x in
             (args.daily, args.history)) and args.out is not None,
         "EXACT_INPUTS")
    need(not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "NO_REPO_WRITES")
    root_bytes = (ROOT/"orchestrator_state.json").read_bytes()
    sina_bytes = (ROOT/"sina_state.json").read_bytes()
    result = build(json.loads(root_bytes), json.loads(sina_bytes),
                   json.loads(args.daily.read_text()),
                   json.loads(args.history.read_text()),
                   dt.datetime.now(dt.timezone.utc),
                   blob(root_bytes), blob(sina_bytes))
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("XRAY_PERSONAL_SIP_ROOT_BRIDGE="+json.dumps({
        "status": result["status"], "asof_et": result["asof_et"],
        "identity": result["identity_scope_count"],
        "daily_observed": result["daily_asof_bar_observed"],
        "260_52_observed": result["260_daily_52_week_observed"],
        "remaining": result["260_daily_52_week_unproven"]},sort_keys=True))


if __name__ == "__main__":
    main()
