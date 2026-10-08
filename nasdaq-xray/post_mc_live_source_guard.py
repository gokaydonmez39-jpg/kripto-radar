#!/usr/bin/env python3
"""Fail closed before expensive Post-MC Stage1 if its source identity changed.

This is a read-only same-run source consistency fence, NOT a PASS authority.
It does not rewrite canonical artifacts, loosen alpha, create R92, or trade.
A late concurrent change is still caught by the existing commit-stage CAS.
"""
from __future__ import annotations

import argparse
import json
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


def active_mc_from_rows(rows: dict[str, tuple[str, dict]], asof: str) -> str:
    """Validate one exact-ASOF immutable supersession chain; no version guessing."""
    expected = re.compile(
        r"nasdaq-xray/canonical_mc_bridge_" + re.escape(asof.replace("-", ""))
        + r"_c417_dv30_v\d+\.json\Z"
    )
    if not rows or any(not expected.fullmatch(path) for path in rows):
        raise ValueError("MC_ACTIVE_EXACT_ASOF_SCOPE_INVALID")
    superseded = set()
    for path, (sha, doc) in rows.items():
        if (not re.fullmatch(r"[0-9a-f]{40}", str(sha))
                or not isinstance(doc, dict)
                or doc.get("asof_et") != asof
                or doc.get("status") != "COMMITTED"
                or doc.get("unknown_never_pass") is not True
                or doc.get("execution") != "NONE"
                or doc.get("real_money") != "NO-GO"):
            raise ValueError("MC_AUTHORITY_ROW_INVALID:" + path)
        parent = doc.get("supersedes_mc_bridge_path")
        parent_sha = doc.get("supersedes_mc_bridge_blob_sha")
        if bool(parent) != bool(parent_sha):
            raise ValueError("MC_AUTHORITY_SUPERSESSION_PAIR_INVALID:" + path)
        if parent:
            if parent not in rows or rows[parent][0] != parent_sha or parent == path:
                raise ValueError("MC_AUTHORITY_SUPERSESSION_BLOB_MISMATCH:" + path)
            superseded.add(parent)
    active = sorted(set(rows) - superseded)
    if len(active) != 1:
        raise ValueError("MC_ACTIVE_AUTHORITY_AMBIGUOUS:" + str(len(active)))
    cursor = active[0]
    visited = set()
    while cursor:
        if cursor in visited:
            raise ValueError("MC_SUPERSESSION_CYCLE")
        visited.add(cursor)
        cursor = rows[cursor][1].get("supersedes_mc_bridge_path")
    if visited != set(rows):
        raise ValueError("MC_SUPERSESSION_DISCONNECTED")
    return active[0]


def fetch_main() -> None:
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", "main"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=35,
    )


def live_mc_active_path(asof: str) -> str:
    stamp = asof.replace("-", "")
    if not re.fullmatch(r"\d{8}", stamp):
        raise ValueError("MC_ASOF_INVALID")
    prefix = "nasdaq-xray/canonical_mc_bridge_" + stamp + "_c417_dv30_v"
    raw = git_output("ls-tree", "-r", "--name-only", "FETCH_HEAD", "--", "nasdaq-xray", timeout=25)
    paths = [p for p in raw.splitlines() if p.startswith(prefix) and MC_PATTERN.fullmatch(p)]
    if not paths or len(paths) > 150:
        raise ValueError("MC_AUTHORITY_CHAIN_COUNT_OUT_OF_RANGE")
    rows = {}
    for p in paths:
        sha = git_output("rev-parse", "FETCH_HEAD:" + p)
        row = json.loads(git_output("show", "FETCH_HEAD:" + p, timeout=30))
        rows[p] = (sha, row)
    return active_mc_from_rows(rows, asof)


def verify_live() -> None:
    mc = str(os.getenv("XRAY_MC_AUTHORITY_PATH") or "")
    if not MC_PATTERN.fullmatch(mc):
        raise ValueError("MC_SOURCE_PATH_NOT_EXACT_CANONICAL_BRIDGE")
    paths = CORE + (mc,)
    # FETCH_HEAD intentionally corresponds to this exact fetch (not a cached
    # remote branch or date). Any fetch failure blocks evaluation.
    fetch_main()
    asof = mc.split("canonical_mc_bridge_", 1)[1][:8]
    active = live_mc_active_path(asof[:4] + "-" + asof[4:6] + "-" + asof[6:])
    if mc != active:
        raise RuntimeError("MC_BRIDGE_SUPERSEDED_LIVE expected=" + active + " selected=" + mc)
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
    # A formerly active immutable MC file remains byte-identical after a
    # successor exists, so SHA equality alone MUST NOT imply active authority.
    p0 = "nasdaq-xray/canonical_mc_bridge_20261007_c417_dv30_v1.json"
    p1 = "nasdaq-xray/canonical_mc_bridge_20261007_c417_dv30_v2.json"
    p2 = "nasdaq-xray/canonical_mc_bridge_20261007_c417_dv30_v3.json"
    def rec(parent=None, parent_sha=None):
        return {
            "asof_et": "2026-10-07", "status": "COMMITTED",
            "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
            "supersedes_mc_bridge_path": parent,
            "supersedes_mc_bridge_blob_sha": parent_sha,
        }
    chain = {p0: (sha0, rec()), p1: (sha1, rec(p0, sha0))}
    assert active_mc_from_rows(chain, "2026-10-07") == p1
    assert p0 != active_mc_from_rows(chain, "2026-10-07")
    chain[p2] = ("c" * 40, rec(p1, sha1))
    assert active_mc_from_rows(chain, "2026-10-07") == p2
    bad = dict(chain)
    bad[p2] = ("c" * 40, rec(p1, "f" * 40))
    for negative in (bad, {p0: chain[p0], p2: chain[p2]},
                     {p0: chain[p0], p1: (sha1, rec())}):
        try:
            active_mc_from_rows(negative, "2026-10-07")
        except ValueError:
            pass
        else:
            raise AssertionError("BAD_MC_CHAIN_ACCEPTED")
    print("XRAY_POSTMC_LIVE_SOURCE_GUARD_SELFTEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--discover-active", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    else:
        try:
            if args.discover_active:
                fetch_main()
                print(live_mc_active_path(os.getenv("XRAY_ASOF_ET", "2026-10-07")))
            else:
                verify_live()
        except (ValueError, FileNotFoundError, subprocess.SubprocessError,
                TimeoutError, RuntimeError) as exc:
            print("::error::XRAY_POSTMC_LIVE_SOURCE_GUARD=BLOCKED "
                  + type(exc).__name__ + ":" + str(exc)[:240], file=sys.stderr)
            raise SystemExit(3) from None


if __name__ == "__main__":
    main()
