#!/usr/bin/env python3
"""Prevent false manual-shadow failures after reporting-only GitHub writes.

HEAD must be source-equivalent to current origin/main. The ONLY admitted
difference is the non-authoritative V2 final-gate reporting overlay. Every
other path (including unknown future paths) fails closed. No candidate,
notification, data-source rights, market order, or policy authority is added.
"""
from __future__ import annotations

import argparse
import subprocess

REPORTING_ONLY = "nasdaq-xray/canonical_current_final_gate_overlay.json"
SCHEMA = "XRAY_MANUAL_SHADOW_SOURCE_EQUIVALENCE_V1"


def classify(head: str, main: str, changed_paths: list[str]) -> str:
    if (not isinstance(head, str) or not isinstance(main, str)
            or len(head) != 40 or len(main) != 40
            or any(c not in "0123456789abcdef" for c in head + main)
            or not isinstance(changed_paths, list)
            or any(not isinstance(p, str) or not p
                   or p != p.strip() for p in changed_paths)
            or len(changed_paths) != len(set(changed_paths))):
        raise ValueError("SOURCE_EQUIVALENCE_INPUT_INVALID")
    if head == main:
        if changed_paths:
            raise ValueError("HEAD_EQUAL_BUT_TREE_CHANGED")
        return "CURRENT_EXACT"
    if changed_paths == [REPORTING_ONLY]:
        return "REPORTING_OVERLAY_ONLY_SOURCE_EQUIVALENT_NO_ALPHA_AUTHORITY"
    raise ValueError("SOURCE_SENSITIVE_MAIN_ADVANCED_FAIL_CLOSED")


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], encoding="utf-8", stderr=subprocess.DEVNULL,
        timeout=30).strip()


def live() -> None:
    head = _git("rev-parse", "HEAD")
    _git("fetch", "--no-tags", "--quiet", "origin", "main")
    main = _git("rev-parse", "FETCH_HEAD")
    changed = [] if head == main else _git(
        "diff", "--name-only", "--no-ext-diff", head, main, "--").splitlines()
    try:
        status = classify(head, main, changed)
    except ValueError as e:
        raise SystemExit("XRAY_MANUAL_SOURCE_EPOCH=BLOCKED:" + str(e)) from e
    # Second, independent remote ref read closes the fetch->report race.
    remote = _git("ls-remote", "--heads", "origin", "refs/heads/main")
    ref = remote.split()[0] if remote.split() else None
    if ref != main:
        raise SystemExit("XRAY_MANUAL_SOURCE_EPOCH=BLOCKED_REMOTE_MAIN_MOVED")
    print("XRAY_MANUAL_SOURCE_EPOCH=" + status)
    print("XRAY_MANUAL_ADVISORY_DIFF_ONLY="
          + str(status != "CURRENT_EXACT").lower())
    print("XRAY_MANUAL_ALPHA_AUTHORITY=false")
    print("XRAY_MANUAL_EXECUTION=NONE REAL_MONEY=NO-GO")


def selftest() -> None:
    a, b = "a" * 40, "b" * 40
    valid = [
        (a, a, [], "CURRENT_EXACT"),
        (a, b, [REPORTING_ONLY],
         "REPORTING_OVERLAY_ONLY_SOURCE_EQUIVALENT_NO_ALPHA_AUTHORITY"),
    ]
    for x, y, changed, want in valid:
        if classify(x, y, changed) != want:
            raise AssertionError("VALID_SOURCE_EQUIVALENCE_REJECTED")
    invalid = [
        (a, b, []),
        (a, b, ["nasdaq-xray/canonical_current_terminal.json"]),
        (a, b, ["nasdaq-xray/canonical_current_price_dv30.json"]),
        (a, b, ["nasdaq-xray/canonical_current_history.json"]),
        (a, b, ["nasdaq-xray/chatgpt_compiled_policy_v3.json"]),
        (a, b, ["nasdaq-xray/canonical_official_source_guard.json"]),
        (a, b, ["nasdaq-xray/scheduler_kick_final.json"]),
        (a, b, ["nasdaq-xray/canonical_mc_bridge_20261009_c417_dv30_v1.json"]),
        (a, b, [REPORTING_ONLY, "nasdaq-xray/delivery_ledger.json"]),
        (a, b, ["nasdaq-xray/unexpected_new_path.json"]),
        (a, b, [REPORTING_ONLY, REPORTING_ONLY]),
        (a, a, [REPORTING_ONLY]),
        ("bad", b, []),
        (a, "bad", []),
    ]
    for x, y, changed in invalid:
        try:
            classify(x, y, changed)
        except ValueError:
            continue
        raise AssertionError("UNSAFE_SOURCE_MAIN_DIFF_ACCEPTED:" + str(changed))
    print("XRAY_MANUAL_SHADOW_SOURCE_EQUIVALENCE_SELFTEST="
          "PASS_2_POSITIVE_14_NEGATIVE_NO_ALPHA")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--live", action="store_true")
    opts = parser.parse_args()
    if opts.selftest:
        selftest()
    elif opts.live:
        live()
    else:
        parser.error("Specify --selftest or --live")
