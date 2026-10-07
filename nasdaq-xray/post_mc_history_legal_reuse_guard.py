#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

TASK = "6a825366222081918997094d76e6ae46"
POLICY_HASH = "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION = "C4.17"


def blob_sha(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def eligible(mc: dict) -> set[str]:
    return set(mc.get("primary_pass_symbols") or []) | set(mc.get("fallback_watch_symbols") or [])


def _legal_unknown_count(legal: dict) -> int:
    counts = legal.get("counts") or {}
    return int(counts.get("UNKNOWN_LEGAL", legal.get("unknown_count", 0)) or 0)


def evaluate_documents(price: dict, current_mc: dict, prior_mc: dict, history: dict, legal: dict) -> tuple[bool, str]:
    try:
        if price.get("task_id") != TASK or current_mc.get("task_id") != TASK or prior_mc.get("task_id") != TASK:
            return False, "TASK_MISMATCH"
        if current_mc.get("schema") != "XRAY_MC_EPOCH_RESULT_V1" or current_mc.get("status") != "COMMITTED":
            return False, "CURRENT_MC_INVALID"
        if prior_mc.get("schema") != "XRAY_MC_EPOCH_RESULT_V1" or prior_mc.get("status") != "COMMITTED":
            return False, "PRIOR_MC_INVALID"
        if current_mc.get("execution") != "NONE" or current_mc.get("real_money") != "NO-GO" or current_mc.get("unknown_never_pass") is not True:
            return False, "CURRENT_MC_SAFETY_INVALID"
        if prior_mc.get("execution") != "NONE" or prior_mc.get("real_money") != "NO-GO" or prior_mc.get("unknown_never_pass") is not True:
            return False, "PRIOR_MC_SAFETY_INVALID"
        asof = price.get("asof_et")
        if not asof or current_mc.get("asof_et") != asof or prior_mc.get("asof_et") != asof or history.get("asof_et") != asof or legal.get("asof_et") != asof:
            return False, "ASOF_MISMATCH"
        if current_mc.get("policy_hash") != POLICY_HASH or prior_mc.get("policy_hash") != POLICY_HASH:
            return False, "POLICY_HASH_MISMATCH"
        if current_mc.get("policy_version") != POLICY_VERSION or prior_mc.get("policy_version") != POLICY_VERSION:
            return False, "POLICY_VERSION_MISMATCH"

        price_pass = sorted(set(price.get("pass_symbols") or []))
        if list(current_mc.get("input_pass_symbols") or []) != price_pass:
            return False, "CURRENT_MC_PRICE_SCOPE_MISMATCH"
        if int(current_mc.get("input_count", -1)) != len(price_pass):
            return False, "CURRENT_MC_INPUT_COUNT_MISMATCH"
        if current_mc.get("input_pass_hash") != price.get("pass_hash"):
            return False, "CURRENT_MC_PASS_HASH_MISMATCH"

        cur_primary = set(current_mc.get("primary_pass_symbols") or [])
        old_primary = set(prior_mc.get("primary_pass_symbols") or [])
        cur_watch = set(current_mc.get("fallback_watch_symbols") or [])
        old_watch = set(prior_mc.get("fallback_watch_symbols") or [])
        if cur_primary != old_primary or cur_watch != old_watch:
            return False, "HISTORY_ELIGIBLE_MC_PARTITION_CHANGED"
        cur_eligible = cur_primary | cur_watch
        if cur_eligible != eligible(prior_mc):
            return False, "HISTORY_ELIGIBLE_SCOPE_CHANGED"

        hresults = set((history.get("results") or {}).keys())
        hpass = set(history.get("pass_symbols") or [])
        if history.get("unknown_never_pass") is not True or int(history.get("unknown_count", -1)) != 0:
            return False, "HISTORY_UNKNOWN_OR_SAFETY_INVALID"
        if int(history.get("input_count", -1)) != len(cur_eligible) or hresults != cur_eligible:
            return False, "HISTORY_SCOPE_MISMATCH"
        if history.get("source_mc_policy_hash") != POLICY_HASH or history.get("source_mc_policy_version") != POLICY_VERSION:
            return False, "HISTORY_POLICY_MISMATCH"
        hcaps = history.get("state_caps") or {}
        expected_caps = {s: ("WATCH" if s in cur_watch else (current_mc.get("state_caps") or {}).get(s, "NORMAL")) for s in cur_eligible}
        if {s: hcaps.get(s) for s in cur_eligible} != expected_caps:
            return False, "HISTORY_STATE_CAP_MISMATCH"
        if not cur_watch.issubset(set(history.get("r92_ineligible") or [])):
            return False, "HISTORY_R92_WATCH_MISMATCH"

        lresults = set((legal.get("results") or {}).keys())
        lpass = set(legal.get("pass_symbols") or [])
        lblock = set(legal.get("blocked_symbols") or [])
        if _legal_unknown_count(legal) != 0:
            return False, "LEGAL_UNKNOWN"
        if lresults != hpass:
            return False, "LEGAL_SCOPE_MISMATCH"
        if (lpass | lblock) != hpass or (lpass & lblock):
            return False, "LEGAL_PARTITION_INVALID"
        if legal.get("source_history_pass_hash") != history.get("pass_hash"):
            return False, "LEGAL_HISTORY_PASS_HASH_MISMATCH"
        return True, "EXACT_SAME_ASOF_HISTORY_LEGAL_SEMANTIC_REUSE"
    except Exception as exc:
        return False, "REUSE_CHECK_ERROR_" + type(exc).__name__


def evaluate_paths(repo_root: Path, price_path: Path, current_mc_path: Path, history_path: Path, legal_path: Path) -> tuple[bool, str]:
    price = load(price_path)
    current_mc = load(current_mc_path)
    history = load(history_path)
    legal = load(legal_path)

    prior_rel = str(history.get("source_mc_artifact") or "")
    prior_sha = str(history.get("source_mc_blob_sha") or "")
    if not prior_rel or not prior_sha:
        return False, "HISTORY_SOURCE_MC_BINDING_MISSING"
    prior_path = (repo_root / prior_rel).resolve()
    try:
        prior_path.relative_to(repo_root.resolve())
    except Exception:
        return False, "HISTORY_SOURCE_MC_PATH_OUTSIDE_REPO"
    if not prior_path.exists() or blob_sha(prior_path) != prior_sha:
        return False, "HISTORY_SOURCE_MC_BLOB_MISMATCH"
    if legal.get("source_history_blob_sha") != blob_sha(history_path):
        return False, "LEGAL_HISTORY_BLOB_MISMATCH"

    if current_mc.get("input_blob_sha") != blob_sha(price_path):
        return False, "CURRENT_MC_PRICE_BLOB_MISMATCH"

    return evaluate_documents(price, current_mc, load(prior_path), history, legal)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--price", required=True)
    ap.add_argument("--mc", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--legal", required=True)
    args = ap.parse_args()

    ok, reason = evaluate_paths(
        Path(args.repo_root),
        Path(args.price),
        Path(args.mc),
        Path(args.history),
        Path(args.legal),
    )
    print("reuse=" + ("true" if ok else "false"))
    print("reason=" + reason)


if __name__ == "__main__":
    main()
