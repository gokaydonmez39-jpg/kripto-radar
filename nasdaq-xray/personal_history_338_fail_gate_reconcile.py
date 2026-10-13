#!/usr/bin/env python3
"""Immutable Oct-13 provider invalid-bar -> technical 260/52 HISTORY gate failures.

Reads verified Actions metadata for the SAME cohort and SAME ASOF. Neither a
nonpositive vendor daily bar nor a missing vendor day proves exchange-level
zero trades, IPO vintage, or a PRIMARY/canonical market-data measurement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ASOF = "2026-10-13"
ROOT_SHA = "dd6d3e6574dc318017d46f412b69e2a5f1331df5"
FULL_SHA256 = "1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e"
FULL_RUN = 38481474945
RECHECK_RUN = 38483601348
BAD = "UNKNOWN_BAD_OHLCV"
MISSING = "UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE"
REPRODUCED = "REPRODUCED_ZERO_OR_NEGATIVE_DAILY_VOLUME"


def must(v, why):
    if not v:
        raise ValueError("XRAY_338_HISTORY_FAIL_GATE_" + why)


def classify_reproduced(value):
    # Fail the 260 positive-source-bar coverage requirement, never claim that
    # the exchange recorded no trades. A revised source must be reassessed.
    if value == REPRODUCED:
        return "FAIL_HISTORY_VERIFIED_SOURCE_NONPOSITIVE_DAILY_VOLUME"
    return "UNKNOWN_RECHECK_OR_SOURCE_REVISED_NOT_FAIL"


def reconcile(full, recheck, full_bytes_hash):
    must(full_bytes_hash == FULL_SHA256, "FROZEN_3185_SHA256")
    must(full.get("schema") == "XRAY_FULL_ROOT_260_52_PERSONAL_SIP_COHORT_V1"
         and full.get("asof_et") == ASOF
         and full.get("source_root_git_blob_sha") == ROOT_SHA
         and full.get("full_scope_reached") is True
         and full.get("total_scope") == 3185
         and full.get("official_daily_session_count") == 260
         and full.get("official_weekly_close_count") == 52
         and full.get("execution") == "NONE"
         and full.get("real_money") == "NO-GO", "ROOT_PROVENANCE")
    base = full.get("symbol_statuses")
    must(type(base) is dict and len(base) == 3185, "ROOT_SYMBOL_COUNT")
    bad_set = {s for s, v in base.items() if v == BAD}
    missing_set = {s for s, v in base.items() if v == MISSING}
    positive_set = set(base) - bad_set - missing_set
    must(len(bad_set) == 338 and len(missing_set) == 168
         and len(positive_set) == 2679 and
         sum(full["counts"].values()) == 3185
         and full["counts"].get(BAD) == 338
         and full["counts"].get(MISSING) == 168,
         "FROZEN_HISTORY_PARTITION")
    must(recheck.get("schema") == "XRAY_BAD338_20261013_SIP_OHLCV_DIAGNOSTIC_V1"
         and recheck.get("asof_et") == ASOF
         and recheck.get("source_artifact_run_id") == FULL_RUN
         and recheck.get("source_artifact_sha256") == FULL_SHA256
         and recheck.get("source_root_git_blob_sha") == ROOT_SHA
         and recheck.get("target_count") == 338
         and recheck.get("scope_fully_classified") is True
         and recheck.get("actual_api_calls") <= 45
         and recheck.get("no_raw_ohlcv_exported") is True
         and recheck.get("primary_history_created") is False
         and recheck.get("r92_created") is False
         and recheck.get("execution") == "NONE"
         and recheck.get("real_money") == "NO-GO",
         "RECHECK_RUN_PROVENANCE")
    statuses = recheck.get("symbol_statuses")
    must(type(statuses) is dict and set(statuses) == bad_set,
         "EXACT_338_SET_EQUALITY")
    classes = {s: classify_reproduced(statuses[s]) for s in sorted(bad_set)}
    hard_fail = {s for s, result in classes.items()
                 if result == "FAIL_HISTORY_VERIFIED_SOURCE_NONPOSITIVE_DAILY_VOLUME"}
    must(len(hard_fail) == 338
         and recheck.get("counts") == {REPRODUCED: 338},
         "NO_EXTRAPOLATION_OR_REVISED_BAR")
    return {
        "schema": "XRAY_20261013_HISTORY_RAW_BAR_FAIL_GATE_V1",
        "asof_et": ASOF,
        "source_root_git_blob_sha": ROOT_SHA,
        "frozen_3185_source_run_id": FULL_RUN,
        "frozen_3185_source_json_sha256": FULL_SHA256,
        "targeted_338_recheck_run_id": RECHECK_RUN,
        "scope": 3185,
        "positive_raw_260_52_shadow_not_primary": 2679,
        "technical_screen_fail_260_valid_daily_bar": 338,
        "technical_screen_fail_reason": "FAIL_HISTORY_VERIFIED_SOURCE_NONPOSITIVE_DAILY_VOLUME",
        "technical_screen_fail_symbols": sorted(hard_fail),
        "unresolved_missing_official_dates": 168,
        "unresolved_missing_symbols": sorted(missing_set),
        "source_recheck_set_exact": True,
        "exchange_zero_trades_for_all_338_proven": False,
        "all_168_late_listings_proven": False,
        "personal_technical_history_primary_promoted": 0,
        "canonical_history_fail_written": False,
        "canonical_history_primary_written": False,
        "cross_asof_price_history_released": False,
        "same_asof_c417_release_proven": False,
        "r92_created": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
    }


def selftest():
    must(classify_reproduced(REPRODUCED).startswith("FAIL_"), "ZERO_RECHECK_FAIL")
    for value in ("SOURCE_REVISED_SINCE_BASELINE_NO_PRIMARY",
                  "UNKNOWN_PROVIDER_ACCESS",
                  "REPRODUCED_INCONSISTENT_OHLC_ORDER",
                  "REPRODUCED_NOW_MISSING_REQUIRED_SESSIONS"):
        must(classify_reproduced(value).startswith("UNKNOWN_"),
             "UNSUPPORTED_FAILURE_REASON")
    # More than a selftest count: a forged immutable source SHA is always vetoed.
    try:
        reconcile({}, {}, "0" * 64)
    except ValueError as e:
        must("FROZEN_3185_SHA256" in str(e), "SOURCE_SHA_VETO")
    else:
        raise AssertionError("XRAY_338_MISSING_SOURCE_SHA_VETO")
    print("XRAY_HISTORY_338_SELFTEST=PASS_NO_EXCHANGE_ZERO_TRADE_INFERENCE")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", type=Path)
    p.add_argument("--recheck", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.selftest:
        must(not (a.root or a.recheck or a.out), "SELFTEST_ISOLATED")
        selftest()
        return
    must(a.root and a.recheck and a.out, "MISSING_ARGUMENT")
    base = Path(__file__).resolve().parent.parent
    must(not a.out.resolve().is_relative_to(base), "NO_REPOSITORY_MUTATION")
    raw = a.root.read_bytes()
    result = reconcile(json.loads(raw), json.loads(a.recheck.read_bytes()),
                       hashlib.sha256(raw).hexdigest())
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_HISTORY_20261013_RAW_BAR_FAIL=338")
    print("XRAY_HISTORY_20261013_DATA_UNRESOLVED=168")
    print("XRAY_PRIMARY_PROMOTED=0_R92=0_TRUE_FULL_GO=NO_GO")


if __name__ == "__main__":
    main()
