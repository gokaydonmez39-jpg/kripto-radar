#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import post_mc_history_legal_reuse_guard as g


def fixtures():
    price = {
        "task_id": g.TASK,
        "asof_et": "2026-10-06",
        "pass_symbols": ["A", "B", "GRAL"],
        "pass_hash": "current-pass-hash",
    }
    prior = {
        "schema": "XRAY_MC_EPOCH_RESULT_V1",
        "status": "COMMITTED",
        "task_id": g.TASK,
        "asof_et": "2026-10-06",
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "policy_hash": g.POLICY_HASH,
        "policy_version": g.POLICY_VERSION,
        "primary_pass_symbols": [],
        "fallback_watch_symbols": ["A", "B"],
        "state_caps": {"A": "WATCH", "B": "WATCH"},
    }
    current = copy.deepcopy(prior)
    current.update({
        "input_pass_symbols": ["A", "B", "GRAL"],
        "input_count": 3,
        "input_pass_hash": "current-pass-hash",
        "unknown_symbols": ["GRAL"],
        "results": {
            "A": {"status": "MC_PASS_FALLBACK_WATCH"},
            "B": {"status": "MC_PASS_FALLBACK_WATCH"},
            "GRAL": {"status": "MC_UNKNOWN"},
        },
    })
    history = {
        "task_id": g.TASK,
        "asof_et": "2026-10-06",
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "input_count": 2,
        "unknown_count": 0,
        "results": {"A": {"status": "PASS_HISTORY"}, "B": {"status": "PASS_HISTORY"}},
        "pass_symbols": ["A", "B"],
        "pass_hash": "history-pass-hash",
        "source_mc_policy_hash": g.POLICY_HASH,
        "source_mc_policy_version": g.POLICY_VERSION,
        "state_caps": {"A": "WATCH", "B": "WATCH"},
        "r92_ineligible": ["A", "B"],
    }
    legal = {
        "task_id": g.TASK,
        "asof_et": "2026-10-06",
        "execution": "NONE",
        "real_money": "NO-GO",
        "counts": {"UNKNOWN_LEGAL": 0},
        "results": {"A": {"status": "PASS_LEGAL"}, "B": {"status": "PASS_LEGAL"}},
        "pass_symbols": ["A", "B"],
        "blocked_symbols": [],
        "source_history_pass_hash": "history-pass-hash",
    }
    return price, current, prior, history, legal


def assert_reason(mutator, expected):
    price, current, prior, history, legal = fixtures()
    mutator(price, current, prior, history, legal)
    ok, reason = g.evaluate_documents(price, current, prior, history, legal)
    assert ok is False and reason == expected, (ok, reason, expected)


def test_noneligible_scope_growth_reuses_history_legal():
    price, current, prior, history, legal = fixtures()
    ok, reason = g.evaluate_documents(price, current, prior, history, legal)
    assert ok is True, (ok, reason)
    assert reason == "EXACT_SAME_ASOF_HISTORY_LEGAL_SEMANTIC_REUSE"


def test_watch_change_forces_rebuild():
    def mutate(price, current, prior, history, legal):
        current["fallback_watch_symbols"] = ["A"]
    assert_reason(mutate, "HISTORY_ELIGIBLE_MC_PARTITION_CHANGED")


def test_history_unknown_forces_rebuild():
    def mutate(price, current, prior, history, legal):
        history["unknown_count"] = 1
    assert_reason(mutate, "HISTORY_UNKNOWN_OR_SAFETY_INVALID")


def test_legal_unknown_forces_rebuild():
    def mutate(price, current, prior, history, legal):
        legal["counts"]["UNKNOWN_LEGAL"] = 1
    assert_reason(mutate, "LEGAL_UNKNOWN")


def test_state_cap_drift_forces_rebuild():
    def mutate(price, current, prior, history, legal):
        history["state_caps"]["B"] = "NORMAL"
    assert_reason(mutate, "HISTORY_STATE_CAP_MISMATCH")


def test_current_price_scope_mismatch_forces_rebuild():
    def mutate(price, current, prior, history, legal):
        current["input_pass_symbols"] = ["A", "B"]
    assert_reason(mutate, "CURRENT_MC_PRICE_SCOPE_MISMATCH")


def test_filesystem_blob_binding():
    price, current, prior, history, legal = fixtures()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nx = root / "nasdaq-xray"
        nx.mkdir()
        pp = nx / "canonical_current_price_dv30.json"
        cp = nx / "current_mc.json"
        op = nx / "old_mc.json"
        hp = nx / "canonical_current_history.json"
        lp = nx / "canonical_current_legal.json"

        pp.write_text(json.dumps(price, sort_keys=True) + "\n")
        op.write_text(json.dumps(prior, sort_keys=True) + "\n")
        history["source_mc_artifact"] = "nasdaq-xray/old_mc.json"
        history["source_mc_blob_sha"] = g.blob_sha(op)
        hp.write_text(json.dumps(history, sort_keys=True) + "\n")
        legal["source_history_blob_sha"] = g.blob_sha(hp)
        lp.write_text(json.dumps(legal, sort_keys=True) + "\n")
        current["input_blob_sha"] = g.blob_sha(pp)
        cp.write_text(json.dumps(current, sort_keys=True) + "\n")

        ok, reason = g.evaluate_paths(root, pp, cp, hp, lp)
        assert ok is True, (ok, reason)

        prior["fallback_watch_symbols"] = ["A"]
        op.write_text(json.dumps(prior, sort_keys=True) + "\n")
        ok, reason = g.evaluate_paths(root, pp, cp, hp, lp)
        assert ok is False and reason == "HISTORY_SOURCE_MC_BLOB_MISMATCH", (ok, reason)


if __name__ == "__main__":
    test_noneligible_scope_growth_reuses_history_legal()
    test_watch_change_forces_rebuild()
    test_history_unknown_forces_rebuild()
    test_legal_unknown_forces_rebuild()
    test_state_cap_drift_forces_rebuild()
    test_current_price_scope_mismatch_forces_rebuild()
    test_filesystem_blob_binding()
    print("POST_MC_HISTORY_LEGAL_REUSE_GUARD_SELFTEST=PASS")
