#!/usr/bin/env python3
"""A45 limited, append-only GitHub Issue audit ledger for NASDAQ research.

Runs ONLY in a separate workflow_run-only issues:write job after A43 evidence.
Does not edit repository files, run candidate packages, or publish signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

REPO = "gokaydonmez39-jpg/kripto-radar"
API = "https://api.github.com/repos/" + REPO
ISSUE_PREFIX = "[XRAY NASDAQ] A45 evidence-only source ledger "
MARKER = "XRAY-NASDAQ-A45-RECEIPT-V1"
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_RESPONSE = 1024 * 1024


class LedgerError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise LedgerError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_source(assessment: dict, upstream: dict, a42_bytes: bytes) -> dict:
    need(type(assessment) is dict and assessment.get("schema") ==
         "XRAY_NASDAQ_A44_SOURCE_EVIDENCE_V1", "A44_SCHEMA")
    need(assessment.get("scope") == "NASDAQ_RESEARCH_ONLY_NO_CRYPTO" and
         assessment.get("automatic_promotion") is False and
         assessment.get("network_enabled") is True, "A44_SCOPE_OR_OFFLINE_RECEIPT")
    need(assessment.get("candidate_receipt_sha256") == sha(a42_bytes), "A42_SHA_MISMATCH")
    a42 = json.loads(a42_bytes)
    need(a42.get("registry_sha256") == assessment.get("registry_sha256") and
         a42.get("asof") == assessment.get("asof_et"), "REGISTRY_OR_ASOF_DRIFT")
    need(upstream.get("schema") == "XRAY_NASDAQ_A43_EOD_ADMISSION_V1" and
         upstream.get("registry_admission") == "PASS_FOR_READONLY_CANDIDATE_INTAKE" and
         upstream.get("production_promotion") is False and
         upstream.get("asof_et") == assessment.get("asof_et"), "A43_WITNESS_INVALID")
    run_id = upstream.get("run_id")
    need(type(run_id) is int and run_id > 0 and
         isinstance(upstream.get("run_sha"), str) and
         SHA256.fullmatch(upstream["run_sha"]) and
         isinstance(upstream.get("log_sha256"), str) and
         SHA256.fullmatch(upstream["log_sha256"]), "A43_RUN_ID_OR_SHA")
    rows = assessment.get("results")
    need(isinstance(rows, list) and 1 <= len(rows) <= 7, "ROW_COUNT")
    ids = [r.get("registry_id") for r in rows]
    need(len(ids) == len(set(ids)) and all(type(i) is int and 1 <= i <= 284 for i in ids),
         "CANDIDATE_IDS")
    statuses = frozenset({"SOURCE_PROVENANCE_UNKNOWN",
                           "NON_GITHUB_OR_MISSING_URL_MANUAL_PROVENANCE",
                           "HOLD_ARCHIVED_DISABLED_OR_UNVERIFIED",
                           "HOLD_FORK_PARENT_NOT_VERIFIED",
                           "HOLD_LICENSE_REVIEW",
                           "SOURCE_PROBE_UNKNOWN",
                           "PROVENANCE_RECORDED_TEST_REQUIRED"})
    for row in rows:
        need(row.get("status") in statuses and
             row.get("promotion") == "BLOCKED_PENDING_INDEPENDENT_FUNCTIONAL_AND_PIT_TEST" and
             row.get("run_upstream_code") is False and row.get("broker") is False and
             row.get("license_approved") is False, "PREMATURE_PROMOTION_OR_INVALID_ROW")
    date = upstream["asof_et"]
    need(isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date),
         "INVALID_ASOF")
    return {
        "schema": MARKER, "source_run_id": run_id,
        "asof_et": date, "source_run_sha": upstream["run_sha"],
        "source_log_sha256": upstream["log_sha256"],
        "registry_sha256": assessment["registry_sha256"],
        "a42_receipt_sha256": sha(a42_bytes),
        "a44_receipt_sha256": sha(json.dumps(assessment, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")),
        "rows": [{"id": r["registry_id"], "status": r["status"],
                  "upstream_sha": r.get("source_head_sha", "")} for r in rows],
        "action": "RESEARCH_ONLY_DO_NOT_INSTALL_OR_TRADE",
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def github_request(method: str, endpoint: str, body: dict | None = None):
    need(method in ("GET", "POST"), "BAD_GITHUB_METHOD")
    need(isinstance(endpoint, str) and re.fullmatch(
        r"/(?:issues(?:\?state=all&per_page=100&page=\d{1,2}|/\d+/comments"
        r"(?:\?per_page=100&page=\d{1,2})?)?)", endpoint), "BAD_GITHUB_API_PATH")
    token = os.getenv("GH_TOKEN", "")
    need(isinstance(token, str) and len(token) >= 12, "ISSUE_WRITE_TOKEN_MISSING")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "xray-nasdaq-a45-ledger/1.0",
               "Authorization": "Bearer " + token}
    payload = None
    if body is not None:
        need(method == "POST" and isinstance(body, dict), "BAD_BODY")
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        need(len(payload) <= 16384, "OVERSIZE_ISSUE_BODY")
        headers["Content-Type"] = "application/json"
    req = Request(API + endpoint, data=payload, method=method, headers=headers)
    opener = build_opener(NoRedirect, HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=12) as res:
            need(res.status in (200, 201), "GITHUB_ISSUE_STATUS")
            data = res.read(MAX_RESPONSE + 1)
            need(len(data) <= MAX_RESPONSE, "GITHUB_RESPONSE_OVERSIZE")
            return json.loads(data)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise LedgerError("GITHUB_ISSUES_UNAVAILABLE_" + type(exc).__name__) from None


def find_or_create_issue(month: str, api=github_request) -> int:
    need(re.fullmatch(r"\d{4}-\d{2}", month) is not None, "INVALID_MONTH")
    title = ISSUE_PREFIX + month
    for page in range(1, 11):
        items = api("GET", f"/issues?state=all&per_page=100&page={page}")
        need(isinstance(items, list), "ISSUE_LIST_INVALID")
        matching = [r for r in items if r.get("title") == title and not r.get("pull_request")]
        need(len(matching) <= 1, "DUPLICATE_LEDGER_ISSUES")
        if matching:
            need(matching[0].get("state") == "open", "LEDGER_ISSUE_CLOSED")
            return matching[0]["number"]
        if len(items) < 100:
            break
    else:
        raise LedgerError("ISSUE_HISTORY_EXCEEDS_BOUNDED_WINDOW")
    created = api("POST", "/issues",
                  {"title": title, "body":
                   "XRAY NASDAQ only. Append-only research evidence; not a trading "
                   "signal, approval or financial-performance report. No private "
                   "sheets, alerts, tokens or broker data. One cohort receipt "
                   "per completed source EOD run. See nasdaq-candidate-autopilot/README.md."})
    need(type(created) is dict and type(created.get("number")) is int and
         created.get("title") == title, "CREATED_ISSUE_INVALID")
    return created["number"]


def record_receipt(issue: int, evidence: dict, api=github_request) -> str:
    need(type(issue) is int and issue > 0, "INVALID_ISSUE_ID")
    key = f"{MARKER}:{evidence['source_run_id']}"
    compact = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    digest = sha(compact.encode("utf-8"))
    marker = f"<!-- {key}:{digest} -->"
    for page in range(1, 11):
        comments = api("GET", f"/issues/{issue}/comments?per_page=100&page={page}")
        need(isinstance(comments, list), "COMMENT_LIST_INVALID")
        matching = [c.get("body", "") for c in comments
                    if f"<!-- {key}:" in c.get("body", "")]
        need(len(matching) <= 1, "DUPLICATE_SOURCE_RUN_IN_LEDGER")
        if matching:
            need(matching[0].startswith(marker), "EVIDENCE_CONFLICT_FOR_SOURCE_RUN")
            return "IDEMPOTENT_ALREADY_RECORDED"
        if len(comments) < 100:
            break
    else:
        raise LedgerError("COMMENT_HISTORY_EXCEEDS_BOUNDED_WINDOW")
    msg = marker + "\n\n" + "Research-only admission receipt, no auto-promotion.\n\n" + (
        "\x60\x60\x60json\n" + json.dumps(evidence, indent=2, sort_keys=True) +
        "\n\x60\x60\x60")
    outcome = api("POST", f"/issues/{issue}/comments", {"body": msg})
    need(type(outcome) is dict and type(outcome.get("id")) is int, "ISSUE_COMMENT_NOT_CONFIRMED")
    return "RECORDED"


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--a42", required=True)
    cli.add_argument("--a43", required=True)
    cli.add_argument("--a44", required=True)
    args = cli.parse_args()
    raw_a42 = Path(args.a42).read_bytes()
    assessment = json.loads(Path(args.a44).read_text(encoding="utf-8"))
    upstream = json.loads(Path(args.a43).read_text(encoding="utf-8"))
    evidence = validate_source(assessment, upstream, raw_a42)
    issue = find_or_create_issue(upstream["asof_et"][:7])
    status = record_receipt(issue, evidence)
    print("XRAY_A45_LEDGER=" + status + ";ISSUE=" + str(issue) +
          ";SOURCES=" + str(len(evidence["rows"])) + ";AUTOPROMOTE=FALSE")


if __name__ == "__main__":
    main()
