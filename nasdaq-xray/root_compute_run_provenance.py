#!/usr/bin/env python3
"""Attest REAL root compute attempts, excluding green no-compute control runs.

A successful GitHub Actions run is NOT a successful vendor/data-plane compute.
Only the named 'Run autonomous XRAY data plane' step with conclusion 'success'
counts as a quota-consuming root attempt. No writes, price data or keys.
"""
from __future__ import annotations

import datetime as dt
import re

ROOT_NAME = "NASDAQ SWING XRAY Autonomous Data Plane"
REAL_COMPUTE_STEP = "Run autonomous XRAY data plane"
MAX_WINDOW = dt.timedelta(hours=4)
MAX_LOOKUPS = 20
RUN_ID = re.compile(r"^[1-9][0-9]{0,18}$")


def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("COMPUTE_RUN_TIME_MISSING")
    v = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if v.tzinfo is None:
        raise ValueError("COMPUTE_RUN_TIME_NAIVE")
    return v.astimezone(dt.timezone.utc)


def step_proof(jobs: object) -> str:
    """SUCCESS / FAILURE / SKIPPED / UNVERIFIED. Exactly one marker required."""
    if type(jobs) is not dict or type(jobs.get("jobs")) is not list:
        return "UNVERIFIED"
    rows = jobs["jobs"]
    if not rows or len(rows) > 100:
        return "UNVERIFIED"
    found = []
    for job in rows:
        if type(job) is not dict or type(job.get("steps")) is not list:
            return "UNVERIFIED"
        for step in job["steps"]:
            if type(step) is not dict:
                return "UNVERIFIED"
            if step.get("name") == REAL_COMPUTE_STEP:
                found.append(step.get("conclusion"))
    if len(found) != 1:
        return "UNVERIFIED"
    return {
        "success": "SUCCESS",
        "failure": "FAILURE",
        "skipped": "SKIPPED"
    }.get(found[0], "UNVERIFIED")


def last_real_compute(*, now: dt.datetime, runs: list, get_jobs) -> dict:
    """Find most recent ACTUAL compute, not last green workflow.

    Every candidate needs a positive GitHub step witness. Missing/paginated
    evidence is not suppressed; it becomes UNVERIFIED and allows the existing
    independent recovery safety checks to decide.
    """
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        return {"status": "UNVERIFIED", "reason": "COMPUTE_CLOCK_UNKNOWN"}
    if type(runs) is not list:
        return {"status": "UNVERIFIED", "reason": "COMPUTE_RUN_LIST_UNKNOWN"}
    try:
        sorted_runs = sorted(runs, key=lambda r: parse_utc(r["created_at"]),
                             reverse=True)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return {"status": "UNVERIFIED", "reason": "COMPUTE_RUN_TIMESTAMP_INVALID"}
    examined = 0
    for row in sorted_runs:
        if type(row) is not dict or row.get("name") != ROOT_NAME or row.get("head_branch") not in ("main", None):
            return {"status": "UNVERIFIED", "reason": "COMPUTE_IDENTITY_UNVERIFIED"}
        age = now.astimezone(dt.timezone.utc) - parse_utc(row["created_at"])
        if age < dt.timedelta(minutes=-1):
            return {"status": "UNVERIFIED", "reason": "COMPUTE_FUTURE_RUN"}
        if age >= MAX_WINDOW:
            return {"status": "NO_RECENT_COMPUTE", "reason": "FOUR_HOUR_WINDOW_EXPIRED",
                    "examined": examined}
        if row.get("status") != "completed":
            # The enclosing watchdog already suppresses active roots. A stale
            # unfinished execution is no successful source-progress witness.
            continue
        rid = row.get("id")
        if type(rid) is not int or not RUN_ID.fullmatch(str(rid)):
            return {"status": "UNVERIFIED", "reason": "COMPUTE_RUN_ID_INVALID"}
        if examined >= MAX_LOOKUPS:
            return {"status": "UNVERIFIED", "reason": "COMPUTE_JOB_LOOKUP_LIMIT"}
        examined += 1
        try:
            jobs = get_jobs(rid)
        except Exception:
            return {"status": "UNVERIFIED", "reason": "COMPUTE_JOB_READ_FAILED"}
        proof = step_proof(jobs)
        if proof == "SKIPPED":
            continue
        if proof == "UNVERIFIED":
            return {"status": "UNVERIFIED", "reason": "COMPUTE_STEP_UNVERIFIED"}
        if proof == "FAILURE" or row.get("conclusion") != "success":
            return {"status": "FAILED_COMPUTE", "reason": "LATEST_TRUE_COMPUTE_FAILED",
                    "run_id": rid}
        return {"status": "SUCCESS_COMPUTE",
                "reason": "EXACT_GITHUB_COMPUTE_STEP_SUCCESS",
                "run": row, "run_id": rid, "age_seconds": int(age.total_seconds())}
    return {"status": "NO_RECENT_COMPUTE",
            "reason": "NO_TRUE_COMPUTE_IN_RECENT_ROOT_RUNS",
            "examined": examined}


def selftest():
    UTC = dt.timezone.utc
    now = dt.datetime(2026,11,2,18,0,tzinfo=UTC)
    def run(i, minute, result="success", step="success"):
        return {"id":i,"name":ROOT_NAME,"head_branch":"main",
                "created_at":f"2026-11-02T{minute}Z",
                "status":"completed","conclusion":result,"compute":step}
    jobs = lambda i, rows: {"jobs":[{"steps":[
        {"name":REAL_COMPUTE_STEP,
         "conclusion":next(x["compute"] for x in rows if x["id"]==i)}]}]}
    # A new green control-only run must NOT reset a four-hour source quota.
    original=run(1,"16:30:00",step="success")
    control=run(2,"17:30:00",step="skipped")
    rows=[control,original]
    got=last_real_compute(now=now,runs=rows,get_jobs=lambda i:jobs(i,rows))
    if got["status"]!="SUCCESS_COMPUTE" or got["run_id"]!=1:
        raise AssertionError("GREEN_CONTROL_RESET_ROOT_CIRCUIT")
    stale=run(3,"13:30:00",step="success")
    controls=[run(4,"17:30:00",step="skipped"),run(5,"16:30:00",step="skipped")]
    refs=controls+[stale]
    got=last_real_compute(now=now,runs=refs,get_jobs=lambda i:jobs(i,refs))
    if got["status"]!="NO_RECENT_COMPUTE":
        raise AssertionError("FOUR_HOUR_TIMER_RESET_BY_CONTROL_RUN")
    fail=run(6,"17:40:00",result="failure",step="failure")
    refs=[fail,original]
    got=last_real_compute(now=now,runs=refs,get_jobs=lambda i:jobs(i,refs))
    if got["status"]!="FAILED_COMPUTE":
        raise AssertionError("FAILED_COMPUTE_HIDDEN_BY_OLDER_GREEN")
    for fake in ({"jobs":[]},{"jobs":[{"steps":[]}]},{"jobs":None},
                 {"jobs":[{"steps":[{"name":REAL_COMPUTE_STEP,"conclusion":"success"},
                                    {"name":REAL_COMPUTE_STEP,"conclusion":"success"}]}]}):
        if step_proof(fake)!="UNVERIFIED":
            raise AssertionError("UNKNOWN_OR_DUPLICATE_STEP_PROOF_ACCEPTED")
    print("XRAY_ROOT_REAL_COMPUTE_WITNESS=PASS_LAST_TRUE_STEP_4H_GREEN_NOOP_NOT_REFRESH_FAILURE_NEGATIVES")


if __name__ == "__main__":
    selftest()
