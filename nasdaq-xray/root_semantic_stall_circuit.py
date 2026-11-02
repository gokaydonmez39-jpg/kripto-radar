#!/usr/bin/env python3
"""Pure watchdog quota circuit breaker; NO source promotion or root dispatch.

The 15-minute watchdog must not repeatedly start a successful, semantically
stalled root on the same completed XNAS session merely because its 75-minute
GitHub Actions heartbeat has expired.

A new completed session, any changed non-overlay tracked source, a failed root,
retryable history, expired bounded cooldown, or unknown evidence always releases
the circuit. Manual data-plane dispatch is outside this guard.
"""
from __future__ import annotations

import datetime as dt
import re

MAX_STALL_COOLDOWN = dt.timedelta(hours=4)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
IGNORED_REPORT_ONLY_FILES = frozenset({
    "nasdaq-xray/canonical_current_final_gate_overlay.json",
})

def evaluate(*, now: dt.datetime, last_complete_asof: str | None,
             state: dict, last_success: dict, current_main_sha: str,
             comparison: dict) -> dict:
    """Return conservative, deterministic suppression with diagnostic reason.

    Unknown/missing provenance must NEVER suppress recovery. The independent
    official session calculator is supplied by the watchdog caller.
    """
    allow = lambda reason: {"suppress": False, "reason": reason}
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        return allow("UNVERIFIED_CLOCK")
    if not isinstance(state, dict) or not isinstance(last_success, dict):
        return allow("UNVERIFIED_STATE_OR_RUN")
    if not isinstance(comparison, dict):
        return allow("UNVERIFIED_SOURCE_COMPARISON")
    if not (isinstance(last_complete_asof, str) and
            re.fullmatch(r"20\d\d-\d\d-\d\d", last_complete_asof)):
        return allow("OFFICIAL_COMPLETED_XNAS_UNKNOWN")
    if not (isinstance(current_main_sha, str) and HEX40.fullmatch(current_main_sha)):
        return allow("MAIN_SHA_UNKNOWN")
    old_sha = last_success.get("head_sha")
    if not (isinstance(old_sha, str) and HEX40.fullmatch(old_sha)):
        return allow("LAST_ROOT_SHA_UNKNOWN")
    if comparison.get("status") not in ("ahead", "identical") or comparison.get("behind_by") != 0:
        return allow("NO_LINEAR_GIT_PROVENANCE")
    base = comparison.get("base_commit")
    last = comparison.get("head_commit")
    if type(base) is not dict or base.get("sha") != old_sha:
        return allow("WRONG_COMPARE_BASE_SHA")
    if type(last) is not dict or last.get("sha") != current_main_sha:
        return allow("WRONG_COMPARE_HEAD_SHA")
    files = comparison.get("files")
    if not isinstance(files, list) or len(files) > 299:
        return allow("CHANGED_FILE_PROVENANCE_INCOMPLETE")
    if not all(isinstance(f, dict) and isinstance(f.get("filename"), str) for f in files):
        return allow("INVALID_CHANGED_FILE_LIST")
    if any(f["filename"] not in IGNORED_REPORT_ONLY_FILES for f in files):
        return allow("NEW_TRACKED_SOURCE_OR_CODE_EVIDENCE")
    if state.get("execution") != "NONE" or state.get("real_money") != "NO-GO":
        return allow("ORCHESTRATOR_SAFETY_UNVERIFIED")
    if state.get("asof_et") != last_complete_asof:
        return allow("NEW_XNAS_ASOF_OR_OUTDATED_ORCHESTRATOR")
    if state.get("status") != "PARTIAL_HISTORY" or state.get("history_retryable") is not False:
        return allow("POTENTIAL_ACTIONABLE_SOURCE_WORK")
    if state.get("history_retry_reason") != "NO_RETRYABLE_HISTORY_WORK_REMAINS":
        return allow("HISTORY_RETRY_CLASS_UNVERIFIED")
    if type(state.get("unknown_count")) is not int or state["unknown_count"] <= 0:
        return allow("UNEXPECTED_ORCHESTRATOR_UNKNOWN_PARTITION")
    if last_success.get("conclusion") != "success" or last_success.get("status") != "completed":
        return allow("LAST_ROOT_NOT_SUCCESSFUL")
    created = last_success.get("created_at")
    if not isinstance(created, str):
        return allow("LAST_ROOT_TIMESTAMP_MISSING")
    try:
        run_time = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        if run_time.tzinfo is None:
            raise ValueError("NAIVE_LAST_ROOT_TIME")
        age = now.astimezone(dt.timezone.utc) - run_time.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return allow("INVALID_LAST_ROOT_TIMESTAMP")
    if age < dt.timedelta(0) or age >= MAX_STALL_COOLDOWN:
        return allow("BOUNDED_RECHECK_DUE")
    return {"suppress": True, "reason": "SAME_ASOF_NO_RETRYABLE_HISTORY_NO_NEW_SOURCE",
            "last_success_age_seconds": int(age.total_seconds()),
            "max_suppression_seconds": int(MAX_STALL_COOLDOWN.total_seconds())}


def selftest() -> None:
    now = dt.datetime(2026, 11, 2, 18, 0, tzinfo=dt.timezone.utc)
    old = "a" * 40
    current = "b" * 40
    state = {"schema": "XRAY_ORCHESTRATOR_STATE_V1",
             "execution": "NONE", "real_money": "NO-GO",
             "asof_et": "2026-10-30", "status": "PARTIAL_HISTORY",
             "history_retryable": False,
             "history_retry_reason": "NO_RETRYABLE_HISTORY_WORK_REMAINS",
             "unknown_count": 215}
    run = {"head_sha": old, "status": "completed", "conclusion": "success",
           "created_at": "2026-11-02T16:30:00Z"}
    comparison = {"status": "ahead", "behind_by": 0,
                  "base_commit": {"sha": old}, "head_commit": {"sha": current},
                  "files": [{"filename": "nasdaq-xray/canonical_current_final_gate_overlay.json"}]}
    arguments = {"now": now, "last_complete_asof": "2026-10-30",
                 "state": state, "last_success": run,
                 "current_main_sha": current, "comparison": comparison}
    import copy
    assert evaluate(**arguments)["suppress"] is True
    samples = [
        ("NEW_SESSION", lambda x: x.update(last_complete_asof="2026-11-02")),
        ("NEW_SOURCE", lambda x: x["comparison"]["files"].append(
            {"filename": "nasdaq-xray/canonical_official_source_guard.json"})),
        ("NEW_CODE", lambda x: x["comparison"]["files"].append(
            {"filename": ".github/workflows/nasdaq-xray-daily.yml"})),
        ("HISTORY_RETRYABLE", lambda x: x["state"].update(history_retryable=True)),
        ("ROOT_FAILED", lambda x: x["last_success"].update(conclusion="failure")),
        ("BAD_CLOCK", lambda x: x.update(now=now.replace(tzinfo=None))),
        ("RECENT_FUTURE", lambda x: x["last_success"].update(
            created_at="2026-11-02T18:05:00Z")),
        ("OLD_RUN", lambda x: x["last_success"].update(
            created_at="2026-11-02T13:00:00Z")),
        ("NO_COMPARE", lambda x: x.update(comparison=None)),
        ("DIVERGED", lambda x: x["comparison"].update(status="diverged")),
        ("NO_BASE_MATCH", lambda x: x["comparison"]["base_commit"].update(sha="e"*40)),
        ("NO_HEAD_MATCH", lambda x: x["comparison"]["head_commit"].update(sha="e"*40)),
        ("NONZERO_BEHIND", lambda x: x["comparison"].update(behind_by=1)),
        ("BAD_MAIN", lambda x: x.update(current_main_sha="invalid")),
        ("MISSING_UNKNOWN", lambda x: x["state"].pop("unknown_count")),
        ("NO_RIGHTS_EVIDENCE", lambda x: x["state"].update(real_money="UNKNOWN")),
        ("BAD_SOURCE_STATUS", lambda x: x["state"].update(status="UNKNOWN")),
        ("UNKNOWN_ROOT_DATE", lambda x: x["last_success"].update(created_at="invalid")),
        ("MISSING_SOURCE_COMPARISON_FILES", lambda x: x["comparison"].pop("files")),
        ("TOO_MANY_FILES", lambda x: x["comparison"].update(
            files=[{"filename": "nasdaq-xray/canonical_current_final_gate_overlay.json"}]*300)),
        ("NEW_PRICE_BLOB", lambda x: x["comparison"]["files"].append(
            {"filename": "nasdaq-xray/canonical_current_price_dv30.json"})),
        ("NEW_G9_PROVIDER", lambda x: x["comparison"]["files"].append(
            {"filename": "nasdaq-xray/g9_entitlement_authority.json"})),
        ("BAD_RETRY_REASON", lambda x: x["state"].update(history_retry_reason="UNKNOWN")),
        ("INCOMPLETE_RUN", lambda x: x["last_success"].update(status="in_progress")),
        ("INVALID_ASOF", lambda x: x.update(last_complete_asof="UNKNOWN")),
    ]
    for label, mutation in samples:
        test = copy.deepcopy(arguments)
        mutation(test)
        result = evaluate(**test)
        if result["suppress"]:
            raise AssertionError("FALSE_STALL_SUPPRESSION_" + label)
    assert evaluate(**dict(arguments, comparison=dict(comparison,
        status="identical", files=[])))["suppress"] is True
    print("XRAY_WATCHDOG_STALLED_SOURCE_CIRCUIT=PASS_POSITIVE_2_NEGATIVE_25_BOUNDED_4H")


if __name__ == "__main__":
    selftest()
