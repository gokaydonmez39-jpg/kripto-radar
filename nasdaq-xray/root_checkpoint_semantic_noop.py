#!/usr/bin/env python3
"""Prevent timestamp-only root checkpoint commits and redundant downstream relays.

This is a commit/relay optimization ONLY, not a market-data or alpha gate.
The root workflow still executes official session, quota and source guards.
Never classify source data, signals or accounts as PASS here.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path

from sina_state_hash_guard import seal, verify

FILES = (
    "sina_state.json",
    "sina_candidates.json",
    "mc_zero_key_state.json",
    "production_core_state.json",
    "stage1_shadow.json",
    "regime_breadth_shadow.json",
    "deep_pre_r1_shadow.json",
    "orchestrator_state.json",
)
RUN_FLAGS = (
    "processed_new_this_run",
    "processed_retry_this_run",
    "processed_transport_rescue_this_run",
    "processed_late_asof_recheck_this_run",
    "processed_late_asof_canary_this_run",
)

def payload_equal(previous, current, name):
    if type(previous) is not dict or type(current) is not dict:
        return False
    left = copy.deepcopy(previous)
    right = copy.deepcopy(current)
    for obj in (left, right):
        obj.pop("updated_at_utc", None)
        if name == "sina_state.json":
            obj.pop("state_hash", None)  # Recomputed from timestamp.
    return left == right

def no_progress(previous, current, candidate):
    """Exact previous/current state, no source work, no possible silent release."""
    if any(type(x) is not dict for x in (previous, current, candidate)):
        return False
    if not payload_equal(previous, current, "sina_state.json"):
        return False
    if any(verify(s) != "PASS_DETERMINISTIC_BLOB_INTERNAL" for s in (previous, current)):
        return False
    if any(s.get("execution") != "NONE" or s.get("real_money") != "NO-GO"
           or s.get("unknown_never_pass") is not True for s in (previous, current)):
        return False
    if any(s.get("status") != "HISTORY_PARTIAL" for s in (previous, current)):
        return False
    if any(s.get("cursor") != s.get("queue_total") or
           type(s.get("queue_total")) is not int or s["queue_total"] <= 0
           for s in (previous, current)):
        return False
    for name in ("pending_retry", "pending_late_asof_recheck", *RUN_FLAGS):
        if any(type(s.get(name)) is not int or s[name] != 0
               for s in (previous, current)):
            return False
    if (candidate.get("asof_et") != current.get("asof_et") or
        candidate.get("execution") != "NONE" or
        candidate.get("real_money") != "NO-GO" or
        candidate.get("market_cap_authority") !=
            "UNRESOLVED_UNTIL_CANONICAL_MC_POLICY"):
        return False
    results = current.get("results")
    if type(results) is not dict or set(results) != set(current.get("queue") or []):
        return False
    if candidate.get("candidate_count") != sum(
         1 for row in results.values() if type(row) is dict and row.get("status") == "PASS"):
        return False
    if set(candidate.get("candidates") or {}) != {
        sym for sym, row in results.items()
        if type(row) is dict and row.get("status") == "PASS"
    }:
        return False
    return True

def get_json(data):
    try:
        obj = json.loads(data)
        return obj if type(obj) is dict else None
    except (ValueError, TypeError):
        return None

def read_head(repo, path):
    result = subprocess.run(
        ["git", "show", "HEAD:nasdaq-xray/" + path],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    return get_json(result.stdout) if result.returncode == 0 else None

def eligible(repo):
    """Fail open toward a normal commit, NEVER toward dropping real changes."""
    root = Path(repo) / "nasdaq-xray"
    before, after = {}, {}
    for name in FILES:
        original = read_head(repo, name)
        try:
            latest = get_json((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return False
        if original is None or latest is None:
            return False
        before[name], after[name] = original, latest
        if not payload_equal(original, latest, name):
            return False
    if not no_progress(
        before["sina_state.json"],
        after["sina_state.json"],
        after["sina_candidates.json"],
    ):
        return False
    prev_orch, now_orch = before["orchestrator_state.json"], after["orchestrator_state.json"]
    if any(
        x.get("status") != "PARTIAL_HISTORY" or
        x.get("history_retryable") is not False or
        x.get("execution") != "NONE" or x.get("real_money") != "NO-GO"
        for x in (prev_orch, now_orch)
    ):
        return False
    if now_orch.get("asof_et") != after["sina_state.json"].get("asof_et"):
        return False
    if now_orch.get("queue_hash") != after["sina_state.json"].get("queue_hash"):
        return False
    return True

def selftest():
    previous = {
        "schema": "XRAY_NASDAQ_SCREENER_SINA_V2",
        "status": "HISTORY_PARTIAL", "asof_et": "2026-10-12",
        "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
        "cursor": 2, "queue_total": 2, "queue": ["AAPL", "BETA"],
        "results": {"AAPL": {"status": "PASS"}, "BETA": {"status": "UNKNOWN_STATIC"}},
        "pending_retry": 0, "pending_late_asof_recheck": 0,
        "updated_at_utc": "2026-10-13T01:00:00Z",
    }
    for flag in RUN_FLAGS:
        previous[flag] = 0
    seal(previous)
    current = copy.deepcopy(previous)
    current["updated_at_utc"] = "2026-10-13T02:00:00Z"
    seal(current)
    cand = {"asof_et": "2026-10-12", "candidate_count": 1,
            "candidates": {"AAPL": {}}, "execution": "NONE",
            "real_money": "NO-GO",
            "market_cap_authority": "UNRESOLVED_UNTIL_CANONICAL_MC_POLICY"}
    if not no_progress(previous, current, cand):
        raise AssertionError("ZERO_PROGRESS_SHOULD_DEDUP")
    tests = (
        lambda x: x.update(asof_et="2026-10-13"),
        lambda x: x.update(pending_retry=1),
        lambda x: x.update(pending_late_asof_recheck=1),
        lambda x: x.update(cursor=1),
        lambda x: x.update(unknown_never_pass=False),
        lambda x: x["results"]["BETA"].update(status="PASS"),
        lambda x: x.update(processed_new_this_run=1),
    )
    for mutate in tests:
        changed = copy.deepcopy(current)
        mutate(changed)
        seal(changed)
        if no_progress(previous, changed, cand):
            raise AssertionError("MATERIAL_CHANGE_SUPPRESSED")
    broken = copy.deepcopy(current)
    broken["state_hash"] = "0" * 64
    if no_progress(previous, broken, cand):
        raise AssertionError("CORRUPTED_HASH_SUPPRESSED")
    badcand = copy.deepcopy(cand)
    badcand["candidate_count"] = 2
    if no_progress(previous, current, badcand):
        raise AssertionError("CANDIDATE_DRIFT_SUPPRESSED")
    if payload_equal({"results": {"AAPL": {"status": "PASS"}}},
                     {"results": {"AAPL": {"status": "UNKNOWN_STATIC"}}},
                     "sina_state.json"):
        raise AssertionError("CHANGED_CLASSIFICATION_SUPPRESSED")
    print("XRAY_ROOT_TIMESTAMP_ONLY_NOOP_SELFTEST=PASS_1_POSITIVE_10_NEGATIVES_NO_VENDOR_CALLS")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.check:
        print("XRAY_ROOT_TIMESTAMP_ONLY_NOOP=" + ("true" if eligible(Path(__file__).resolve().parent.parent) else "false"))
    else:
        ap.error("Use --selftest or --check")

if __name__ == "__main__":
    main()
