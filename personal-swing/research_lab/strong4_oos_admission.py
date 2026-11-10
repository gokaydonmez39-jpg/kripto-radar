#!/usr/bin/env python3
"""Private, offline OOS evidence pre-admission (NEVER production certification).

Checks exact session/decision timing, fixed strategy, embargo and cost analytics.
No provider calls, trading, private Sheet read/write or market data export.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = "XRAY_STRONG4_PRIVATE_OOS_LEDGER_V1"
WATCHLIST_GIT_SHA = "786fa9b3a673ef56e9f0384f721d7fa836e9b9cd"
POLICY = {
    "universe": 477, "feed": "iex", "basis": "RAW", "timeframe": "1Day",
    "stop_atr": 2, "target_atr": 4, "tracking_xnas_sessions": 15,
    "first_fold_train_including_purge": 515, "purge_sessions": 15,
    "test_folds": 3, "sessions_per_fold": 31,
    "final_maturity_tail": 15, "fee_bps": 4.0, "slippage_bps": 5.0,
    "baseline": "PIT_477_EQUAL_WEIGHT_BUY_HOLD",
    "pretested_strategy_variants": 1,
}
SESSIONS_REQUIRED = 623  # 500 usable + 15 purge + 3*31 OOS + 15 maturity
RECEIPTS = {"historical_decision_journal_sha256", "issuer_lineage_sha256", "data_rights_sha256"}
ROW_KEYS = {"session", "decision_asof_et", "decision_at_utc", "feature_first_known_at_utc",
            "decision_receipt_sha256", "strategy_gross_daily_return", "baseline_daily_return",
            "turnover_fraction", "claimed_al_signals"}
ROOT_KEYS = {"schema", "watchlist_git_blob", "policy", "receipts", "rows"}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def day(value: object) -> date:
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            "BAD_DATE_FORMAT")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_DATE") from exc
    require(parsed.isoformat() == value, "NONCANONICAL_DATE")
    return parsed


def utc(value: object) -> datetime:
    require(type(value) is str and len(value) <= 40, "INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def sha(value: object) -> bool:
    return (type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None
            and len(set(value)) > 1)


def finite(value: object, name: str, low: float, high: float) -> float:
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            "INVALID_" + name)
    return float(value)


def max_drawdown(daily_returns: list[float]) -> float:
    equity = peak = 1.0
    minimum = 0.0
    for change in daily_returns:
        equity *= 1.0 + change
        peak = max(peak, equity)
        minimum = min(minimum, equity / peak - 1.0)
    return minimum


def block_bootstrap_lower(excess: list[float]) -> float:
    """Precommitted deterministic 15-day moving blocks; no causal inference."""
    rng = random.Random(20261108)
    means = []
    for _ in range(1000):
        sample = []
        while len(sample) < len(excess):
            i = rng.randrange(len(excess))
            sample.extend(excess[(i + j) % len(excess)] for j in range(15))
        means.append(sum(sample[:len(excess)]) / len(excess))
    return sorted(means)[49]  # one-sided 95% descriptive percentile


def inspect(document: object) -> dict:
    require(type(document) is dict and set(document) == ROOT_KEYS and
            document.get("schema") == SCHEMA, "DOCUMENT_SCHEMA_INVALID")
    require(document["watchlist_git_blob"] == WATCHLIST_GIT_SHA, "WATCHLIST_DRIFT")
    policy = document["policy"]
    require(type(policy) is dict and set(policy) == set(POLICY), "POLICY_SHAPE_DRIFT")
    for key, expected in POLICY.items():
        require(type(policy[key]) is type(expected) and policy[key] == expected,
                "POLICY_DRIFT_" + key)
    receipts = document["receipts"]
    require(type(receipts) is dict and set(receipts) == RECEIPTS,
            "EXTERNAL_RECEIPT_KEYS_MISSING")
    for key in RECEIPTS:
        require(sha(receipts[key]), "INVALID_SELF_DECLARED_RECEIPT_" + key)
    rows = document["rows"]
    require(type(rows) is list and len(rows) == SESSIONS_REQUIRED,
            "REQUIRES_EXACTLY_623_SESSIONS")
    import exchange_calendars as xc
    cal = xc.get_calendar("XNAS")
    first = day(rows[0].get("session") if type(rows[0]) is dict else None)
    last = day(rows[-1].get("session") if type(rows[-1]) is dict else None)
    try:
        expected = [x.strftime("%Y-%m-%d") for x in
                    cal.sessions_in_range(first.isoformat(), last.isoformat())]
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("CALENDAR_NOT_VERIFIABLE") from exc
    require(len(expected) == SESSIONS_REQUIRED, "INCOMPLETE_XNAS_WINDOW")

    gross, baseline, turnover, claimed = [], [], [], []
    daily_receipts = set()
    for idx, row in enumerate(rows):
        require(type(row) is dict and set(row) == ROW_KEYS, "ROW_SCHEMA_INVALID")
        d = day(row["session"])
        require(row["session"] == expected[idx], "NONCONSECUTIVE_XNAS_SESSIONS")
        previous = cal.previous_session(d.isoformat())
        require(row["decision_asof_et"] == previous.strftime("%Y-%m-%d"),
                "LOOKAHEAD_DECISION_DATE")
        at = utc(row["decision_at_utc"])
        first_known = utc(row["feature_first_known_at_utc"])
        require(cal.session_close(previous).to_pydatetime() < at <
                cal.session_open(d.isoformat()).to_pydatetime() and
                first_known <= at, "LOOKAHEAD_OR_LATE_DECISION")
        receipt = row["decision_receipt_sha256"]
        require(sha(receipt), "INVALID_DAILY_RECEIPT")
        require(receipt not in daily_receipts, "REUSED_DECISION_RECEIPT")
        daily_receipts.add(receipt)
        gross.append(finite(row["strategy_gross_daily_return"], "GROSS_RETURN", -1.0, 5.0))
        baseline.append(finite(row["baseline_daily_return"], "BASELINE_RETURN", -1.0, 5.0))
        turnover.append(finite(row["turnover_fraction"], "TURNOVER", 0.0, 2.0))
        signals = row["claimed_al_signals"]
        require(type(signals) is int and 0 <= signals <= 477, "INVALID_CLAIMED_AL_COUNT")
        claimed.append(signals)

    folds, all_excess = [], []
    for fold in range(3):
        start = 515 + 31 * fold
        end = start + 31
        usable_train = start - 15
        require(usable_train >= 500 and end + 15 <= len(rows),
                "PURGE_OR_MATURITY_NOT_SATISFIED")
        net = [gross[i] - turnover[i] * 9.0 / 10000.0 for i in range(start, end)]
        excess = [net[i - start] - baseline[i] for i in range(start, end)]
        all_excess.extend(excess)
        folds.append({
            "fold": fold + 1, "usable_train_sessions": usable_train,
            "purged_sessions": 15, "test_sessions": 31,
            "claimed_al_signals": sum(claimed[start:end]),
            "mean_excess_after_assumed_cost": sum(excess) / len(excess),
            "net_drawdown": max_drawdown(net),
            "nominal_cost_bps_per_unit_turnover": 9.0
        })
    one_sided_lower = block_bootstrap_lower(all_excess)
    all_signals = sum(f["claimed_al_signals"] for f in folds)
    provisional = (all_signals >= 20 and
                   all(f["claimed_al_signals"] >= 5 and
                       f["mean_excess_after_assumed_cost"] > 0 for f in folds) and
                   one_sided_lower > 0)
    return {
        "schema": "XRAY_STRONG4_OOS_PRIVATE_PRE_ADMISSION_REPORT_V1",
        "status": "FORMAT_ACCEPTED_ONLY_EXTERNAL_PROVENANCE_NOT_ATTESTED",
        "asof_et": expected[-1], "observed_xnas_sessions": SESSIONS_REQUIRED,
        "first_fold_usable_training_sessions": 500,
        "out_of_sample_test_sessions": 93, "label_maturity_tail_sessions": 15,
        "folds": folds, "claimed_oos_al_signals": all_signals,
        "no_claimed_signals_hold": all_signals == 0,
        "one_sided_bootstrap_lower_excess_descriptive": one_sided_lower,
        "precommitted_descriptive_criteria_met_not_alpha": provisional,
        "historical_issuer_provenance_independently_verified": False,
        "signed_contemporaneous_decision_records_verified": False,
        "first_known_at_independently_verified": False,
        "data_rights_independently_verified": False,
        "transactions_and_market_impact_verified": False,
        "multiple_testing_bias_excluded": False,
        "real_oos_alpha_verified": False, "production_authorized": False,
        "orders_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-ledger", required=True, type=Path)
    args = parser.parse_args()
    try:
        path = args.private_ledger
        require(path.is_file() and not path.is_symlink() and
                path.stat().st_size <= 2_000_000,
                "PRIVATE_LEDGER_NOT_READABLE_OR_TOO_LARGE")
        result = inspect(json.loads(path.read_text(encoding="utf-8")))
        # Diagnostic only; no input rows, symbols, private prices or receipts emitted.
        print(json.dumps(result, allow_nan=False, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160],
                          "production_authorized": False}, sort_keys=True))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())