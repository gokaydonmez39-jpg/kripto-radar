#!/usr/bin/env python3
"""Fail closed before expensive Post-MC Stage1 if its source identity changed.

This is a read-only same-run source consistency fence, NOT a PASS authority.
It does not rewrite canonical artifacts, loosen alpha, create R92, or trade.
A late concurrent change is still caught by the existing commit-stage CAS.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = (
    "nasdaq-xray/canonical_current_full_state.json",
    "nasdaq-xray/canonical_current_master_manifest.json",
    "nasdaq-xray/canonical_current_price_dv30.json",
)
MC_PATTERN = re.compile(
    r"nasdaq-xray/canonical_mc_bridge_\d{8}_c417_dv30_v\d+\.json\Z"
)


def source_diff(current: dict[str, str], live: dict[str, str], paths: tuple[str, ...]) -> list[str]:
    if len(paths) != len(set(paths)) or not paths:
        raise ValueError("INVALID_SOURCE_SCOPE")
    return [
        name for name in paths
        if not current.get(name)
        or not live.get(name)
        or not re.fullmatch(r"[0-9a-f]{40}", str(current[name]))
        or not re.fullmatch(r"[0-9a-f]{40}", str(live[name]))
        or current[name] != live[name]
    ]


def git_output(*args: str, timeout: int = 25) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPO_ROOT, text=True,
        stderr=subprocess.PIPE, timeout=timeout
    ).strip()


def verify_live() -> None:
    mc = str(os.getenv("XRAY_MC_AUTHORITY_PATH") or "")
    if not MC_PATTERN.fullmatch(mc):
        raise ValueError("MC_SOURCE_PATH_NOT_EXACT_CANONICAL_BRIDGE")
    paths = CORE + (mc,)
    # FETCH_HEAD intentionally corresponds to this exact fetch (not a cached
    # remote branch or date). Any fetch failure blocks evaluation.
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", "main"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=35,
    )
    actual = {}
    live = {}
    for p in paths:
        fp = REPO_ROOT / p
        if not fp.is_file():
            raise FileNotFoundError("CURRENT_SOURCE_MISSING:" + p)
        actual[p] = git_output("hash-object", "--", p)
        live[p] = git_output("rev-parse", "FETCH_HEAD:" + p)
    stale = source_diff(actual, live, paths)
    if stale:
        for p in stale:
            print("::error::XRAY_POSTMC_STALE_INPUT_FAIL_CLOSED path=" + p)
        raise RuntimeError("STALE_PREMC_INPUT_REQUEUE_LATEST_WORKFLOW")
    print("XRAY_POSTMC_LIVE_SOURCE_GUARD=PASS source_count=" + str(len(paths)))
    print("G9=NOT_ATTESTED ACCOUNT=NOT_ATTESTED AL=NOT_CREATED")


def selftest() -> None:
    sha0 = "a" * 40
    sha1 = "b" * 40
    paths = CORE + ("nasdaq-xray/canonical_mc_bridge_20261007_c417_dv30_v13.json",)
    valid = {k: sha0 for k in paths}
    assert source_diff(valid, dict(valid), paths) == []
    for p in paths:
        changed = dict(valid, **{p: sha1})
        assert source_diff(valid, changed, paths) == [p]
        absent = dict(valid)
        absent.pop(p)
        assert source_diff(valid, absent, paths) == [p]
    bad = dict(valid)
    bad[paths[0]] = "invalid"
    assert source_diff(valid, bad, paths) == [paths[0]]
    try:
        source_diff(valid, valid, paths + (paths[0],))
    except ValueError:
        pass
    else:
        raise AssertionError("DUPLICATE_SOURCE_SCOPE_ACCEPTED")
    assert MC_PATTERN.fullmatch(paths[-1])
    for candidate in (
        "../canonical_mc_bridge_20261007_c417_dv30_v13.json",
        "nasdaq-xray/canonical_current_mc.json",
        "nasdaq-xray/canonical_mc_bridge_20261007_c417_dv30_v13.json/../../x",
    ):
        assert not MC_PATTERN.fullmatch(candidate)
    print("XRAY_POSTMC_LIVE_SOURCE_GUARD_SELFTEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    else:
        try:
            verify_live()
        except (ValueError, FileNotFoundError, subprocess.SubprocessError,
                TimeoutError, RuntimeError) as exc:
            print("::error::XRAY_POSTMC_LIVE_SOURCE_GUARD=BLOCKED "
                  + type(exc).__name__ + ":" + str(exc)[:240], file=sys.stderr)
            raise SystemExit(3) from None


if __name__ == "__main__":
    main()
