#!/usr/bin/env python3
"""Fail-closed, read-only provenance gate for a *future* 477 EOD recovery.

This module does not dispatch workflows, place orders, mutate Sheets, or
authorize ChatGPT notifications. A verified fallback parent and an eligible
child are necessary but not sufficient: an independent one-writer epoch lock
and private EOD readback must also exist. The currently deployed scheduler
does NOT issue such a child or lock. No historical replay is authorized.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

SCHEMA = "XRAY_477_RECOVERY_CHAIN_READ_ONLY_V1"
REPO = "gokaydonmez39-jpg/kripto-radar"
PARENT_PATH = ".github/workflows/xray-personal-477-schedule-fallback.yml"
CHILD_PATH = ".github/workflows/xray-personal-477-eod.yml"
JOBS = frozenset(("offline-guard", "private-sheets-auth-preflight",
                  "daily-private-scan", "private-episode-followups",
                  "guardian-acceptance", "daily-private-score-acceptance"))
MAX_DISPATCH_AGE = timedelta(hours=10)


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo is not None else None


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _sha(value, size):
    return isinstance(value, str) and bool(re.fullmatch("[0-9a-f]{" + str(size) + "}", value))


def _id(value):
    return type(value) is int and value > 0


def _blocked(reason):
    return {"schema": SCHEMA, "state": "HOLD", "stage": reason,
            "parent_child_proven": False, "ab_release_authorized": False,
            "orders": False, "sheet_writes": 0, "device_ack": "UNKNOWN"}


def attest(parent, parent_receipt, child, child_receipt, jobs, scan,
           epoch_lock, *, expected_asof, official_cutoff, observed_at):
    """Verify normalized primary evidence. No I/O and no side effects.

    official_cutoff must equal the locally resolved XNAS close+45m for the
    exact expected session. A caller-supplied timestamp alone is never proof.
    """
    if not _day(expected_asof):
        return _blocked("ASOF_INVALID")
    cutoff, now = _utc(official_cutoff), _utc(observed_at)
    if cutoff is None or now is None or cutoff > now:
        return _blocked("XNAS_CUTOFF_OR_CLOCK_UNVERIFIED")
    # The caller's cutoff is a claim, not independent calendar evidence.
    # Verify the exact XNAS session close (including holidays and early close)
    # before accepting ANY parent/child or private readback witness.
    try:
        import exchange_calendars as ec
        cal = ec.get_calendar("XNAS")
        if not cal.is_session(expected_asof):
            return _blocked("XNAS_OFFICIAL_CUTOFF_UNVERIFIED")
        actual_cutoff = (cal.session_close(expected_asof).to_pydatetime()
                         .astimezone(timezone.utc) + timedelta(minutes=45))
        if cutoff != actual_cutoff:
            return _blocked("XNAS_OFFICIAL_CUTOFF_UNVERIFIED")
    except Exception:
        return _blocked("XNAS_OFFICIAL_CUTOFF_UNVERIFIED")
    if not isinstance(parent, dict) or not isinstance(child, dict):
        return _blocked("RUN_DOCUMENT_MISSING")
    parent_id, child_id = parent.get("id"), child.get("id")
    if not _id(parent_id) or not _id(child_id) or parent_id == child_id:
        return _blocked("PARENT_CHILD_ID_INVALID")
    for item, path, event in ((parent, PARENT_PATH, "schedule"),
                              (child, CHILD_PATH, "workflow_dispatch")):
        if (item.get("repository", {}).get("full_name") != REPO or
                item.get("path") != path or item.get("event") != event or
                item.get("head_branch") != "main" or
                item.get("run_attempt") != 1 or
                item.get("status") != "completed" or
                item.get("conclusion") != "success" or
                not _sha(item.get("head_sha"), 40)):
            return _blocked("RUN_ORIGIN_NOT_VERIFIED")
    p_created, p_end = _utc(parent.get("created_at")), _utc(parent.get("updated_at"))
    c_created, c_end = _utc(child.get("created_at")), _utc(child.get("updated_at"))
    if (None in (p_created, p_end, c_created, c_end) or
            not cutoff <= p_created <= cutoff + MAX_DISPATCH_AGE or
            not p_created <= c_created <= c_end <= now or not p_created <= p_end <= now):
        return _blocked("RUN_WINDOW_OR_ORDER_INVALID")
    if not isinstance(parent_receipt, dict) or (
        parent_receipt.get("schema") != "XRAY_477_FALLBACK_PARENT_RECEIPT_V1" or
        parent_receipt.get("parent_run_id") != parent_id or
        parent_receipt.get("parent_source_event") != "schedule" or
        parent_receipt.get("parent_workflow") != PARENT_PATH or
        parent_receipt.get("parent_head_sha") != parent.get("head_sha") or
        parent_receipt.get("parent_ref") != "refs/heads/main" or
        parent_receipt.get("requested_asof_et") != expected_asof or
        parent_receipt.get("dispatch_request_accepted") is not True or
        parent_receipt.get("eod_completion_proven") is not False or
        parent_receipt.get("ab_release_authorized") is not False or
        parent_receipt.get("writes") != 0 or parent_receipt.get("orders") != 0
    ):
        return _blocked("PARENT_DISPATCH_WITNESS_MISSING")
    if not isinstance(child_receipt, dict) or (
        child_receipt.get("schema") != "XRAY_477_RECOVERY_CHILD_RECEIPT_V1" or
        child_receipt.get("parent_run_id") != parent_id or
        child_receipt.get("child_run_id") != child_id or
        child_receipt.get("asof_et") != expected_asof or
        child_receipt.get("source_event") != "workflow_dispatch" or
        child_receipt.get("source_sha") != child.get("head_sha") or
        child_receipt.get("source_readback_verified") is not True or
        child_receipt.get("orders") is not False
    ):
        return _blocked("CHILD_PARENT_BINDING_MISSING")
    # Bind each job to the same immutable child run, commit and real run
    # time interval. A green job name without provenance is NOT a receipt.
    child_run_url = "https://api.github.com/repos/" + REPO + "/actions/runs/" + str(child_id)

    def job_verified(j):
        if not isinstance(j, dict):
            return False
        begun = _utc(j.get("started_at"))
        finished = _utc(j.get("completed_at"))
        return (isinstance(j.get("name"), str) and
                _id(j.get("id")) and j.get("run_id") == child_id and
                j.get("run_attempt") == 1 and
                j.get("run_url") == child_run_url and
                j.get("head_sha") == child.get("head_sha") and
                j.get("head_branch") == "main" and
                j.get("status") == "completed" and
                j.get("conclusion") == "success" and
                begun is not None and finished is not None and
                c_created <= begun <= finished <= c_end)

    if (not isinstance(jobs, list) or len(jobs) != len(JOBS) or
            any(not job_verified(j) for j in jobs) or
            {j["name"] for j in jobs} != JOBS or
            len({j["id"] for j in jobs}) != len(JOBS)):
        return _blocked("EXACT_SIX_JOB_RECEIPT_MISSING")
    by_name = {j["name"]: j for j in jobs}
    dependencies = (
        ("offline-guard", "private-sheets-auth-preflight"),
        ("offline-guard", "daily-private-scan"),
        ("daily-private-scan", "private-episode-followups"),
        ("private-episode-followups", "guardian-acceptance"),
        ("private-sheets-auth-preflight", "guardian-acceptance"),
        ("guardian-acceptance", "daily-private-score-acceptance"),
    )
    if any(_utc(by_name[first]["completed_at"]) >
           _utc(by_name[second]["started_at"]) for first, second in dependencies):
        return _blocked("EOD_JOB_DAG_UNVERIFIED")
    if (not isinstance(scan, dict) or scan.get("asof_et") != expected_asof or
            scan.get("source_event") != "workflow_dispatch" or
            scan.get("run_id") != child_id or
            scan.get("requested") != 477 or scan.get("processed") != 477 or
            scan.get("valid") != 477 or scan.get("missing") != 0 or
            scan.get("final_ready") is not True or
            scan.get("independent_get_verified") is not True or
            not _sha(scan.get("scope_sha"), 64) or
            not _sha(scan.get("policy_sha"), 64)):
        return _blocked("PRIVATE_477_READBACK_MISSING")
    if (not isinstance(epoch_lock, dict) or
            epoch_lock.get("asof_et") != expected_asof or
            epoch_lock.get("owner_run_id") != child_id or
            epoch_lock.get("unique_reservation") is not True or
            epoch_lock.get("independent_get_verified") is not True or
            epoch_lock.get("competing_writer_observed") is not False):
        return _blocked("ATOMIC_EPOCH_LOCK_NOT_VERIFIED")
    # This source proof cannot claim that a ChatGPT card or iOS push arrived.
    # Promoting an AB release requires a distinct versioned policy and test.
    return {"schema": SCHEMA, "state": "RECOVERY_CHAIN_PROVEN_READ_ONLY",
            "stage": "SOURCE_AND_EPOCH_WITNESS", "parent_child_proven": True,
            "asof_et": expected_asof, "parent_id": parent_id,
            "child_id": child_id, "ab_release_authorized": False,
            "orders": False, "sheet_writes": 0, "device_ack": "UNKNOWN"}
