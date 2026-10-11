#!/usr/bin/env python3
"""Fail-closed GitHub Actions supply-chain guard for fifteen critical XRAY workflows.

Only exact vendor-owned commit refs independently verified against official
GitHub release tags are accepted. This verifies pinned dependency identity,
not marketplace trust, licensing, market data, or production readiness.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
ARTIFACT = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
EXPECTED = {
    ".github/workflows/nasdaq-xray-daily.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/nasdaq-xray-delivery.yml": (CHECKOUT, PYTHON),
    ".github/workflows/xray-e2e-production-readiness.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-preopen-source-audit.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-c418-multi-source-contract.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-c418-sec-alpaca-intersection-shadow.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-canonical-current-pre-mc.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-canonical-current-post-mc.yml": (CHECKOUT, PYTHON, ARTIFACT, ARTIFACT),
    ".github/workflows/xray-canonical-current-final.yml": (CHECKOUT, PYTHON),
    ".github/workflows/xray-final-gate-overlay-v2.yml": (CHECKOUT, PYTHON),
    ".github/workflows/xray-strict-g9-gate.yml": (CHECKOUT, PYTHON),
    ".github/workflows/xray-account-gate-reconcile.yml": (CHECKOUT, PYTHON),
    ".github/workflows/xray-live-truth-attestation.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-manual-decision-research-shadow.yml": (CHECKOUT, PYTHON, ARTIFACT),
    ".github/workflows/xray-sec-free-mc-transport-proof.yml": (CHECKOUT, PYTHON, ARTIFACT),
}
LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(?:\s*(?:#.*)?)?$")


def references(source: str) -> list[str]:
    if not isinstance(source, str):
        raise ValueError("WORKFLOW_TEXT_REQUIRED")
    found = []
    for line in source.splitlines():
        if re.match(r"^\s*(?:-\s*)?uses\s*:", line):
            match = LINE.fullmatch(line)
            if not match:
                raise ValueError("INVALID_ACTION_REFERENCE_SHAPE")
            found.append(match.group(1))
    return found


def verify(path: str, contents: str) -> int:
    if path not in EXPECTED:
        raise ValueError("UNREGISTERED_WORKFLOW")
    observed = references(contents)
    expected = EXPECTED[path]
    if not observed or observed != list(expected):
        raise ValueError("UNPINNED_UNEXPECTED_OR_REORDERED_ACTION_REFERENCE")
    if any(not re.fullmatch(r"actions/[a-z-]+@[a-f0-9]{40}", ref)
           for ref in observed):
        raise ValueError("ACTION_NOT_IMMUTABLE")
    if path == ".github/workflows/xray-sec-free-mc-transport-proof.yml":
        if re.search(r"(?m)^s*ref:s*(?:main|master)s*$", contents):
            raise ValueError("SEC_CHECKOUT_MOVING_MAIN_DISALLOWED")
        if ("git rev-parse HEAD" not in contents or "$GITHUB_SHA" not in contents
                or "XRAY_SEC_TRANSPORT_CHECKOUT_EXACT=PASS" not in contents):
            raise ValueError("SEC_CHECKOUT_INVOCATION_SHA_FENCE_MISSING")
    return len(observed)


def selftest() -> None:
    example = ".github/workflows/nasdaq-xray-daily.yml"
    source = ("steps:\n  - uses: " + CHECKOUT + " # v4.4.0\n"
              "  - uses: " + PYTHON + " # v5.6.0\n"
              "  - uses: " + ARTIFACT + " # v4.6.2\n")
    assert verify(example, source) == 3
    assert references("steps:\n  - name: hello\n") == []
    negatives = [
        source.replace(CHECKOUT, "actions/checkout@v4"),
        source.replace(CHECKOUT, "actions/checkout@" + "f" * 40),
        source.replace(PYTHON, "attacker/setup-python@" + "a" * 40),
        source.replace(ARTIFACT, "actions/upload-artifact@v4"),
        source.replace("  - uses: " + ARTIFACT + " # v4.6.2\n", ""),
        source + "  - uses: actions/cache@v4\n",
        source.replace(" # v4.4.0", " trailing_unexpected"),
    ]
    for modified in negatives:
        try:
            verify(example, modified)
        except ValueError:
            continue
        raise AssertionError("ACTION_DEPENDENCY_NEGATIVE_BYPASS")
    sec=".github/workflows/xray-sec-free-mc-transport-proof.yml"
    fenced=(source+"  - name: source check\n    run: |\n"
            "      test \"$(git rev-parse HEAD)\" = \"$GITHUB_SHA\"\n"
            "      echo XRAY_SEC_TRANSPORT_CHECKOUT_EXACT=PASS\n")
    assert verify(sec,fenced)==3
    for modified in (fenced+"  ref: main\n",
                     fenced.replace("XRAY_SEC_TRANSPORT_CHECKOUT_EXACT=PASS",
                                    "SOURCE_FENCE_MISSING")):
        try:
            verify(sec,modified)
        except ValueError:
            continue
        raise AssertionError("SEC_EXACT_INVOCATION_NEGATIVE_BYPASS")
    print("XRAY_IMMUTABLE_ACTION_GUARD_SELFTEST=PASS_9_NEGATIVES")


def live() -> dict:
    audited = {}
    for path in sorted(EXPECTED):
        file = REPO / path
        if not file.is_file():
            raise ValueError("CRITICAL_WORKFLOW_MISSING:" + path)
        audited[path] = verify(path, file.read_text(encoding="utf-8"))
    if sum(audited.values()) != 41:
        raise ValueError("CRITICAL_ACTION_REFERENCE_COVERAGE_CHANGED")
    return audited


if __name__ == "__main__":
    selftest()
    d = live()
    print("XRAY_IMMUTABLE_ACTION_GUARD=PASS_15_WORKFLOWS_41_EXACT_OFFICIAL_SHAS")
