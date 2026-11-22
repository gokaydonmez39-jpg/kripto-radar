#!/usr/bin/env python3
"""Redacted, read-only GitHub Step Summary for a failed NASDAQ477 fallback.

This program never dispatches, reads private Sheets, creates an epoch lease,
queries market data, sends notifications or changes exit status of the failed
source job. Unknown/untrusted provider content is never echoed to public logs.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re

SCHEMA = "XRAY_NASDAQ477_FALLBACK_INCIDENT_V1"
MAX_INPUT_BYTES = 8192
CATEGORIES = {
    "BLOCKED_DISPATCH_NOT_CONFIRMED": "MISSING_PRIMARY_RECOVERY_POLICY_LOCKED",
    "BLOCKED_NATURAL_FALLBACK_EXPIRED": "NATURAL_WINDOW_EXPIRED",
    "BLOCKED_CURRENT_EPOCH_NATURAL_EOD_NOT_SUCCESS": "PRIMARY_FAILED",
    "BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE": "PRIMARY_INCOMPLETE",
    "BLOCKED_CURRENT_EPOCH_DUPLICATE_NATURAL_RUN": "DUPLICATE_NATURAL_SOURCE",
    "BLOCKED_UNTRUSTED_RUN_PAGINATION": "GITHUB_RUN_COLLECTION_UNVERIFIED",
    "BLOCKED_RECHECK_UNTRUSTED_RUN_PAGINATION": "GITHUB_RUN_COLLECTION_UNVERIFIED",
    "BLOCKED_INVALID_GITHUB_RUN_RESPONSE": "GITHUB_RUN_COLLECTION_UNVERIFIED",
    "BLOCKED_RECHECK_INVALID_GITHUB_RUN_RESPONSE": "GITHUB_RUN_COLLECTION_UNVERIFIED",
    "BLOCKED_RECHECK_UNCERTAIN_RUN_STATE": "GITHUB_RUN_COLLECTION_UNVERIFIED",
    "BLOCKED_GITHUB_API_UNCERTAIN": "GITHUB_READ_UNCERTAIN",
}


def safe_asof(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
        return "UNKNOWN"
    try:
        return raw if date.fromisoformat(raw).isoformat() == raw else "UNKNOWN"
    except ValueError:
        return "UNKNOWN"


def classify(raw):
    """Never turn a malformed/partial output into a verified missing EOD."""
    unknown = {"category": "UNVERIFIED_FAILURE", "asof": "UNKNOWN"}
    if not isinstance(raw, bytes) or len(raw) > MAX_INPUT_BYTES:
        return unknown
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
        if len(lines) != 1:
            return unknown
        event = json.loads(lines[0])
        if not isinstance(event, dict) or event.get("execution") != "NONE":
            return unknown
        status = event.get("status")
        category = CATEGORIES.get(status)
        if category is None:
            return unknown
        if status == "BLOCKED_GITHUB_API_UNCERTAIN":
            return {"category": category, "asof": "UNKNOWN"}
        if event.get("dispatch_requested") is not False:
            return unknown
        asof = safe_asof(event.get("asof_et"))
        if status == "BLOCKED_DISPATCH_NOT_CONFIRMED":
            if event.get("reason_code") != "NATURAL_FALLBACK_POLICY_LOCKED" or asof == "UNKNOWN":
                return unknown
        return {"category": category, "asof": asof}
    except (UnicodeError, ValueError, TypeError):
        return unknown


def render(receipt):
    """Fixed vocabulary only. Nothing from GitHub JSON is interpolated raw."""
    if (not isinstance(receipt, dict) or
            receipt.get("category") not in {*CATEGORIES.values(), "UNVERIFIED_FAILURE"} or
            (receipt.get("asof") != "UNKNOWN" and
             safe_asof(receipt.get("asof")) == "UNKNOWN")):
        receipt = {"category": "UNVERIFIED_FAILURE", "asof": "UNKNOWN"}
    return (
        "### XRAY NASDAQ 477 — scheduled fallback failure\n"
        f"- Receipt schema: \x60{SCHEMA}\x60\n"
        f"- Category: \x60{receipt['category']}\x60\n"
        f"- ASOF_ET: \x60{receipt['asof']}\x60\n"
        "- Source job: \x60FAILURE\x60 (original nonzero outcome preserved)\n"
        "- Fallback effects: \x60NO_WORKFLOW_DISPATCH\x60, \x60NO_SHEET_POST\x60, \x60NO_TAG_CLAIM\x60, \x60NO_ORDER\x60\n"
        "- Canonical EOD completion: \x60UNVERIFIED\x60; ChatGPT delivery: \x60UNKNOWN\x60; iPhone: \x60UNKNOWN\x60\n"
        "- Recovery: \x60HOLD\x60; no replay/backfill and no automatic policy bypass.\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    try:
        path = Path(args.result)
        raw = path.read_bytes() if path.is_file() and path.stat().st_size <= MAX_INPUT_BYTES else b""
    except OSError:
        raw = b""
    summary = render(classify(raw))
    try:
        with open(args.summary, "a", encoding="utf-8") as out:
            out.write(summary)
    except OSError:
        print("XRAY_NASDAQ477_FALLBACK_SUMMARY_WRITE_UNAVAILABLE")
        return 1
    print("XRAY_NASDAQ477_FALLBACK_INCIDENT_REDACTED_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
