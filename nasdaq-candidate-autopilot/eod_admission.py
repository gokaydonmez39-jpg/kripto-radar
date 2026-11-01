#!/usr/bin/env python3
"""A43: independently gate candidate intake on actual successful 477 EOD receipts.

Read-only GitHub Actions log admission, not a trading decision or claim of device ACK.
Only the default-branch, scheduled personal EOD run is eligible.
No Sheets credentials, Alpaca keys, orders, repo writes or auto-promotion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from zoneinfo import ZoneInfo

EXPECTED_NAME = "XRAY Personal 477 EOD Daily Health (Research Only)"
EXPECTED_REPO = "gokaydonmez39-jpg/kripto-radar"
EXPECTED_HANDOFF = "XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE"
UTC_STAMP = re.compile(r"\b20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z\s+(.*)$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_LOG_BYTES = 5 * 1024 * 1024


class Blocked(ValueError):
    pass


def need(cond: bool, code: str) -> None:
    if not cond:
        raise Blocked(code)


def record_lines(log: str) -> list[str]:
    """Trust only timestamped *output* lines, not GitHub bash's echoed script."""
    out = []
    for line in log.splitlines():
        m = UTC_STAMP.search(line)
        if not m:
            continue
        content = m.group(1).strip()
        if content.startswith("\x1b") or content.startswith("echo ") or content.startswith("print("):
            continue
        if content.startswith("***") and content.endswith("***"):
            content = content[3:-3].strip()
        out.append(content)
    return out


def json_receipts(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        if not line.startswith('"') or '": ' not in line:
            continue
        try:
            data = json.loads("{" + line + "}")
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def validate_event(event: dict, log: str) -> dict:
    need(isinstance(event, dict), "EVENT_NOT_OBJECT")
    need(event.get("repository") == EXPECTED_REPO, "REPOSITORY_SCOPE")
    need(event.get("workflow_name") == EXPECTED_NAME, "WORKFLOW_IDENTITY")
    need(event.get("head_branch") == "main", "NON_MAIN_PRODUCER")
    need(event.get("event") == "schedule", "NON_SCHEDULE_PRODUCER")
    need(event.get("status") == "completed" and event.get("conclusion") == "success",
         "UPSTREAM_NOT_SUCCESS")
    need(type(event.get("run_id")) is int and event["run_id"] > 0, "BAD_RUN_ID")
    head_sha = event.get("head_sha")
    need(isinstance(head_sha, str) and SHA256.fullmatch(head_sha), "BAD_HEAD_SHA")
    created = event.get("created_at")
    need(isinstance(created, str), "RUN_DATE_MISSING")
    try:
        stamp = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        need(stamp.tzinfo is not None, "RUN_DATE_NAIVE")
        ny_date = stamp.astimezone(ZoneInfo("America/New_York")).date()
    except (ValueError, OverflowError):
        raise Blocked("RUN_DATE_INVALID") from None
    need(isinstance(log, str) and 0 < len(log.encode("utf-8")) <= MAX_LOG_BYTES,
         "NO_OR_OVERSIZE_SOURCE_LOG")
    lines = record_lines(log)
    need(any(line == EXPECTED_HANDOFF for line in lines), "MISSING_477_SHA_HANDOFF")
    receipts = json_receipts(lines)
    scans = [r for r in receipts if
             r.get("universe") == 477 and r.get("processed") == 477 and
             r.get("valid") == 477 and r.get("remaining") == 0 and
             r.get("invalid_or_missing") == 0 and
             r.get("final_ready") is True and
             r.get("no_execution") is True and
             type(r.get("new_entries")) is int and r["new_entries"] >= 0 and
             isinstance(r.get("analysis_fingerprint_sha256"), str) and
             SHA256.fullmatch(r["analysis_fingerprint_sha256"]) and
             isinstance(r.get("scope_sha256"), str) and
             SHA256.fullmatch(r["scope_sha256"])]
    need(len(scans) == 1, "MISSING_OR_AMBIGUOUS_477_SCAN_RECEIPT")
    asof = scans[0].get("asof_et")
    need(isinstance(asof, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof),
         "INVALID_ASOF_ET")
    try:
        session = dt.date.fromisoformat(asof)
    except ValueError:
        raise Blocked("INVALID_ASOF_ET") from None
    need(ny_date == session and session.weekday() < 5, "RUN_SESSION_DAY_MISMATCH")
    statuses = ("PRIVATE_SHEET_READBACK_PASS", "LIFECYCLE_READBACK_PASS",
                "PANEL_READBACK_PASS")
    for status in statuses:
        matches = [r for r in receipts if r.get("status") == status]
        need(len(matches) == 1 and matches[0].get("asof_et") == asof,
             "MISSING_OR_STALE_" + status)
        need(matches[0].get("device_ack") is False, "INVALID_DEVICE_ACK_CLAIM")
    need(any(line == "PRIVATE_SHEETS_PREFLIGHT=READ_PASS_WRITE_NOT_VERIFIED"
             for line in lines), "PRIVATE_SHEET_PREFLIGHT_NOT_PROVEN")
    return {
        "schema": "XRAY_NASDAQ_A43_EOD_ADMISSION_V1",
        "source": "PERSONAL_477_IEX_EOD_SCHEDULE",
        "run_id": event["run_id"],
        "run_sha": head_sha,
        "asof_et": asof,
        "registry_admission": "PASS_FOR_READONLY_CANDIDATE_INTAKE",
        "scan_477": True,
        "sheet_readback": True,
        "lifecycle_readback": True,
        "panel_readback": True,
        "log_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(),
        "real_orders": False,
        "device_ack": "UNKNOWN",
        "production_promotion": False,
    }


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", required=True)
    args = cli.parse_args()
    run_raw = os.environ.get("SOURCE_RUN_ID", "")
    need(re.fullmatch(r"[1-9]\d*", run_raw) is not None, "SOURCE_RUN_ID_INVALID")
    event = {
        "run_id": int(run_raw),
        "repository": os.environ.get("SOURCE_RUN_REPOSITORY"),
        "workflow_name": os.environ.get("SOURCE_RUN_NAME"),
        "head_branch": os.environ.get("SOURCE_RUN_BRANCH"),
        "head_sha": os.environ.get("SOURCE_RUN_SHA"),
        "event": os.environ.get("SOURCE_RUN_EVENT"),
        "status": os.environ.get("SOURCE_RUN_STATUS"),
        "conclusion": os.environ.get("SOURCE_RUN_CONCLUSION"),
        "created_at": os.environ.get("SOURCE_RUN_CREATED_AT"),
    }
    # Fail before any network subprocess on all untrusted metadata.
    metadata = dict(event)
    need(metadata.get("repository") == EXPECTED_REPO and
         metadata.get("workflow_name") == EXPECTED_NAME and
         metadata.get("head_branch") == "main" and
         metadata.get("event") == "schedule" and
         metadata.get("conclusion") == "success" and
         metadata.get("status") == "completed", "UNTRUSTED_UPSTREAM_METADATA")
    need(bool(os.environ.get("GH_TOKEN")), "NO_READONLY_GITHUB_TOKEN")
    try:
        proc = subprocess.run(
            ["gh", "run", "view", run_raw, "--repo", EXPECTED_REPO, "--log"],
            check=True, text=True, capture_output=True, timeout=75,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise Blocked("GITHUB_LOG_UNAVAILABLE") from None
    proof = validate_event(event, proc.stdout)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(proof, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("XRAY_A43_EOD_ADMISSION=PASS;ASOF_ET=%s;AUTO_PROMOTE=FALSE" % proof["asof_et"])


if __name__ == "__main__":
    main()
