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
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

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
    dispatch = ("NO_WORKFLOW_DISPATCH"
                if receipt["category"] == "MISSING_PRIMARY_RECOVERY_POLICY_LOCKED"
                else "DISPATCH_STATE_UNVERIFIED")
    return (
        "### XRAY NASDAQ 477 — scheduled fallback failure\n"
        f"- Receipt schema: \x60{SCHEMA}\x60\n"
        f"- Category: \x60{receipt['category']}\x60\n"
        f"- ASOF_ET: \x60{receipt['asof']}\x60\n"
        "- Source job: \x60FAILURE\x60 (original nonzero outcome preserved)\n"
        f"- Fallback dispatch: \x60{dispatch}\x60; this parent job never directly posts to private Sheets or creates tags/orders.\n"
        "- Canonical EOD completion: \x60UNVERIFIED\x60; ChatGPT delivery: \x60UNKNOWN\x60; iPhone: \x60UNKNOWN\x60\n"
        "- Recovery: \x60HOLD\x60; no replay/backfill and no automatic policy bypass.\n"
    )



# Exact public REST resource identities. The fallback's existing scheduled
# runner has actions:read; this new diagnostic has no mutation permission.
REPO_META_PATH = "/repos/gokaydonmez39-jpg/kripto-radar"
WORKFLOW_META_PATH = REPO_META_PATH + "/actions/workflows/xray-personal-477-eod.yml"
EXPECTED_EOD_PATH = ".github/workflows/xray-personal-477-eod.yml"
PROBE_CATEGORIES = frozenset((
    "SOURCE_EVENT_NOT_ESTABLISHED",
    "SOURCE_RUNNER_UNVERIFIED",
    "GITHUB_METADATA_UNVERIFIED",
    "DEFAULT_BRANCH_NOT_MAIN",
    "WORKFLOW_DISABLED_OBSERVED",
    "WORKFLOW_ACTIVE_CAUSE_UNRESOLVED",
))
DISABLED_WORKFLOW_STATES = frozenset((
    "disabled_manually", "disabled_inactivity", "disabled_fork",
))


def github_readonly_metadata(path, token):
    """Only two GET paths; never dispatch, create a tag or access private data.

    A failed/large HTTP response is classified by the caller without logging
    provider bodies, URLs, tokens or untrusted error messages.
    """
    if path not in (REPO_META_PATH, WORKFLOW_META_PATH):
        raise ValueError("UNAPPROVED_GITHUB_METADATA_PATH")
    if not isinstance(token, str) or not token:
        raise ValueError("NO_GITHUB_METADATA_CREDENTIAL")
    req = Request(
        "https://api.github.com" + path,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "xray-nasdaq477-source-liveness-readonly",
        },
    )
    with urlopen(req, timeout=12) as response:
        raw = response.read(16385)
    if len(raw) > 16384:
        raise ValueError("GITHUB_METADATA_TOO_LARGE")
    return json.loads(raw.decode("utf-8", errors="strict"))


def probe_source_metadata(raw, environment, fetch):
    """Metadata snapshot for an ALREADY OBSERVED, policy-locked missing EOD.

    Only the existing scheduled fallback's exact runner may perform two
    read-only metadata queries. Active != guaranteed schedule delivery and a
    newly disabled state does not prove it was disabled on a historic ASOF.
    """
    prior = classify(raw)
    if prior.get("category") != "MISSING_PRIMARY_RECOVERY_POLICY_LOCKED":
        return {"category": "SOURCE_EVENT_NOT_ESTABLISHED", "asof": "UNKNOWN"}
    asof = prior["asof"]
    if (type(environment) is not dict or not callable(fetch) or
            environment.get("GITHUB_EVENT_NAME") != "schedule" or
            environment.get("GITHUB_REPOSITORY") != "gokaydonmez39-jpg/kripto-radar" or
            environment.get("GITHUB_REF") != "refs/heads/main" or
            environment.get("GITHUB_RUN_ATTEMPT") != "1" or
            type(environment.get("GITHUB_TOKEN")) is not str or
            not environment["GITHUB_TOKEN"]):
        return {"category": "SOURCE_RUNNER_UNVERIFIED", "asof": asof}
    unknown = {"category": "GITHUB_METADATA_UNVERIFIED", "asof": asof}
    try:
        repo = fetch(REPO_META_PATH)
        if (type(repo) is not dict or
                repo.get("full_name") != "gokaydonmez39-jpg/kripto-radar" or
                type(repo.get("default_branch")) is not str):
            return unknown
        if repo["default_branch"] != "main":
            return {"category": "DEFAULT_BRANCH_NOT_MAIN", "asof": asof}
        wf = fetch(WORKFLOW_META_PATH)
        if (type(wf) is not dict or wf.get("path") != EXPECTED_EOD_PATH or
                type(wf.get("state")) is not str):
            return unknown
        state = wf["state"]
        if state == "active":
            category = "WORKFLOW_ACTIVE_CAUSE_UNRESOLVED"
        elif state in DISABLED_WORKFLOW_STATES:
            category = "WORKFLOW_DISABLED_OBSERVED"
        else:
            return unknown
        return {"category": category, "asof": asof}
    except Exception:
        # Provider may include bearer secrets or user-provided content.
        # Never leak exceptions, HTTP responses, actor identity or raw JSON.
        return unknown


def render_source_probe(proof):
    """Fixed vocabulary; no untrusted provider body interpolated to logs."""
    if (type(proof) is not dict or
            proof.get("category") not in PROBE_CATEGORIES or
            safe_asof(proof.get("asof")) != proof.get("asof")):
        proof = {"category": "GITHUB_METADATA_UNVERIFIED", "asof": "UNKNOWN"}
    return (
        "### XRAY NASDAQ 477 — source workflow liveness (GET only)\\n"
        f"- Category: \\x60{proof['category']}\\x60\\n"
        f"- Missing-EOD observation ASOF: \\x60{proof['asof']}\\x60\\n"
        "- Provenance: current GitHub metadata snapshot only; does NOT establish "
        "the cause or state of a past GitHub scheduler event.\\n"
        "- Workflow actor health: \\x60UNKNOWN\\x60; "
        "natural EOD completion: \\x60UNVERIFIED\\x60.\\n"
        "- Recovery: \\x60HOLD\\x60; \\x60NO_DISPATCH\\x60; "
        "\\x60NO_SHEETS_WRITE\\x60; \\x60NO_AL_OR_DEVICE_ACK\\x60.\\n"
    )

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--probe-source", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = Path(args.result)
        raw = path.read_bytes() if path.is_file() and path.stat().st_size <= MAX_INPUT_BYTES else b""
    except OSError:
        raw = b""
    if args.probe_source:
        runtime = dict(os.environ)
        proof = probe_source_metadata(
            raw, runtime, lambda path: github_readonly_metadata(
                path, runtime.get("GITHUB_TOKEN", "")))
        summary = render_source_probe(proof)
    else:
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
