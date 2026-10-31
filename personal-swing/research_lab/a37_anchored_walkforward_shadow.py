"""XRAY NASDAQ A37: deterministic, anchored walk-forward structural admission.

Offline research only, over declared source metadata; NOT Qlib execution,
real source attestation, alpha validation or executable-trade simulation.
No API, broker, Sheets, secrets, notification, LLM, install or scheduler.
Uses existing qlib_pit_readiness_shadow negative gates unchanged.
"""
from __future__ import annotations

import hashlib
import json

from qlib_pit_readiness_shadow import (
    HORIZON, MIN_HISTORY, check_fixture, purged_chronological_split,
    synthetic_rows, train_only_scaler, _utc,
)

SCHEMA = "XRAY_NASDAQ_A37_ANCHORED_WALKFORWARD_SHADOW_V1"
MAX_ROWS = 100_000
MAX_FOLDS = 24


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("A37_" + code)


def admission(rows: list[dict], *, train_min: int = 500,
              test_size: int = 40, min_folds: int = 3,
              horizon: int = HORIZON) -> dict:
    """Assert an exact, non-overlapping expanding walk-forward split.

    A fold may train on previously tested rows ONLY after their labels mature;
    rows whose label_end_index reaches the next test boundary are purged.
    The only output authority is synthetic/structural; never live approval.
    """
    require(type(rows) is list and MIN_HISTORY <= len(rows) <= MAX_ROWS,
            "ROW_COUNT_OR_TYPE")
    require(type(train_min) is int and train_min >= MIN_HISTORY and
            type(test_size) is int and 31 <= test_size <= 250 and
            type(min_folds) is int and 3 <= min_folds <= MAX_FOLDS and
            type(horizon) is int and horizon == HORIZON,
            "PARAMETER_CONTRACT")
    require(len(rows) >= train_min + test_size * min_folds,
            "INSUFFICIENT_FOLD_HISTORY")
    require((len(rows) - train_min) % test_size == 0,
            "INCOMPLETE_UNEVALUATED_TAIL")
    folds_count = (len(rows) - train_min) // test_size
    require(min_folds <= folds_count <= MAX_FOLDS, "FOLD_BUDGET")
    check_fixture(rows, minimum=MIN_HISTORY)
    issuers = {r["issuer_id"] for r in rows}
    require(len(issuers) == 1, "CROSS_ISSUER_SERIES_MIXING")
    for r in rows:
        # Ensures the declared decision snapshot is not silently dated
        # after the feature's own session. This is NOT external PIT proof.
        cutoff = _utc(r["decision_cutoff_utc"])
        require(cutoff.date().isoformat() == r["session"],
                "DECISION_CUTOFF_SESSION_DRIFT")
        require(_utc(r["first_known_at_utc"]) <= cutoff,
                "FEATURE_NOT_YET_AVAILABLE")

    out = []
    covered = set()
    for ordinal in range(folds_count):
        train_end = train_min + ordinal * test_size
        test_end = train_end + test_size
        # Critical: slice to this fold's horizon BEFORE building scaler.
        # No observations from later folds can enter the current fit.
        prefix = rows[:test_end]
        train, test = purged_chronological_split(
            prefix, train_end=train_end, label_horizon=horizon)
        require(test == tuple(range(train_end, test_end)),
                "TEST_WINDOW_BOUNDARY_DRIFT")
        require(not set(test) & covered, "REUSED_HOLDOUT_OBSERVATION")
        covered.update(test)
        require(len(train) >= 100 and
                all(prefix[i]["label_end_index"] < train_end for i in train),
                "TRAINING_LABEL_OVERLAP")
        scale = train_only_scaler(prefix, train, test)
        require(len(scale["test_transformed"]) == test_size,
                "SCALER_TEST_COVERAGE")
        # Fingerprint training-only statistics for sensitivity tests; never
        # publish underlying feature values or symbols in workflow logs.
        stats = (float(scale["train_mean"]).hex(),
                 float(scale["train_std"]).hex())
        out.append({"fold": ordinal + 1,
                    "train_cutoff_index": train_end,
                    "purged_training_rows": train_end - len(train),
                    "usable_training_rows": len(train),
                    "test_start_index": test[0],
                    "test_end_index_exclusive": test_end,
                    "test_rows": len(test),
                    "training_scaler_sha256": hashlib.sha256(
                        json.dumps(stats).encode("ascii")).hexdigest(),
                    "synthetic_or_caller_claim_only": True})
    require(covered == set(range(train_min, len(rows))),
            "INCOMPLETE_HOLDOUT_COVERAGE")
    return {"schema": SCHEMA,
            "decision": "STRUCTURAL_PASS_REAL_DATA_UNVERIFIED_NO_GO",
            "source_rows": len(rows), "train_start_rows": train_min,
            "test_size": test_size, "folds": out,
            "holdout_coverage_count": len(covered),
            "required_label_horizon": HORIZON,
            "official_xnas_calendar_verified": False,
            "real_provider_provenance_verified": False,
            "qlib_runtime_executed": False,
            "benchmark_returns_measured": False,
            "out_of_sample_alpha_proven": False,
            "may_generate_al": False, "may_change_risk_levels": False,
            "may_write_sheets": False, "may_notify": False,
            "may_execute_order": False}


def strictly_synthetic_fixture(n: int = 620) -> list[dict]:
    rows = synthetic_rows(n)
    for r in rows:
        r["first_known_at_utc"] = r["session"] + "T20:00:00Z"
        r["decision_cutoff_utc"] = r["session"] + "T23:00:00Z"
    return rows


def main() -> None:
    result = admission(strictly_synthetic_fixture())
    print(json.dumps({"state": result["decision"],
                      "fold_count": len(result["folds"]),
                      "holdout_rows": result["holdout_coverage_count"],
                      "purged_training_rows": [x["purged_training_rows"]
                                               for x in result["folds"]],
                      "synthetic_only": True, "real_alpha_proven": False,
                      "orders": False, "sheets": False}, sort_keys=True))


if __name__ == "__main__":
    main()
