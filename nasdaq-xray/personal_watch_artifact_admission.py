"""Read-only admission for WATCH's exact source artifact; no trading authority."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ARTIFACT = "xray-personal-six-gate-causal-worklist-no-ohlcv"
GATE = "Fail closed before scheduled SIP vendor IO on Nasdaq holidays"
CALENDAR_STEP = "Enforce ET exchange session on schedule; manual research explicit"
PREFLIGHT_STEP = "Verify latest main SHA and current completed source epoch before provider IO"
SKIPPED_JOBS = frozenset((
    "Replay immutable completed 14-Oct six-gate inputs without vendor API calls",
    "Verify every source symbol's delayed SIP session-day availability",
    "Personal full NASDAQ SIP 260 daily and 52 weekly research",
    "Bind both actual SIP measurements to exact root identity and ASOF",
    "Audit every issuer's first unresolved causal gate across all six links",
    "Personal joint 260-session and daily30 research cohort 30Min RTH bound",
    "Map exact RTH research cohort to current SEC CIK candidates without MC assertion",
))
NY = ZoneInfo("America/New_York")


def need(ok, code):
    if not ok:
        raise ValueError("XRAY_EARLY_WATCH_ARTIFACT_" + code)


def utc(value):
    need(isinstance(value, str), "TIME_MISSING")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(stamp.utcoffset() is not None, "TIME_NAIVE")
    return stamp.astimezone(timezone.utc)


def complete_list(payload, key):
    need(isinstance(payload, dict), "BAD_LIST")
    rows = payload.get(key)
    count = payload.get("total_count")
    need(type(rows) is list and type(count) is int and count == len(rows)
         and all(type(row) is dict for row in rows), "INCOMPLETE_LIST")
    return rows


def admit(run, artifacts_payload, jobs_payload=None, *, permit_compute=None):
    """Call AFTER existing verify_run. Return READY or CLOSED_SESSION_NOOP.

    Unknown/expired/duplicate artifacts and open-session missing output raise.
    Exact verified holiday no-op cannot authorize any private or provider step.
    """
    artifacts = complete_list(artifacts_payload, "artifacts")
    found = [a for a in artifacts if a.get("name") == ARTIFACT]
    if found:
        need(len(found) == 1 and found[0].get("expired") is False
             and type(found[0].get("id")) is int and found[0]["id"] > 0,
             "EXACT_LIVE_ARTIFACT_REQUIRED")
        return "READY"
    need(not artifacts, "MISSING_TARGET_WITH_OTHER_ARTIFACTS")
    need(run.get("event") == "schedule" and run.get("run_attempt") == 1
         and run.get("status") == "completed" and run.get("conclusion") == "success",
         "NOOP_NATURAL_SCHEDULE_REQUIRED")
    jobs = complete_list(jobs_payload, "jobs")
    by_name = {j.get("name"): j for j in jobs}
    need(len(by_name) == len(jobs) and set(by_name) == SKIPPED_JOBS | {GATE},
         "EXACT_HOLIDAY_JOB_SET_REQUIRED")
    need(all(j.get("run_id") == run["id"] and j.get("head_sha") == run["head_sha"]
             and j.get("run_attempt") == 1 and j.get("status") == "completed" for j in jobs),
         "JOB_LINEAGE")
    need(all(by_name[n].get("conclusion") == "skipped" for n in SKIPPED_JOBS),
         "PRIVATE_JOB_NOT_SKIPPED")
    gate = by_name[GATE]
    need(gate.get("conclusion") == "success", "GATE_NOT_SUCCESS")
    steps = gate.get("steps")
    need(type(steps) is list and all(type(s) is dict for s in steps), "GATE_STEPS")
    stepmap = {s.get("name"): s for s in steps}
    need(len(stepmap) == len(steps), "DUPLICATE_STEP")
    c, p = stepmap.get(CALENDAR_STEP, {}), stepmap.get(PREFLIGHT_STEP, {})
    need(c.get("status") == p.get("status") == "completed" and
         c.get("conclusion") == "success" and p.get("conclusion") == "skipped",
         "CALENDAR_NOOP_NOT_PROVEN")
    start, end = utc(c.get("started_at")), utc(c.get("completed_at"))
    need(utc(run.get("run_started_at")) <= utc(gate.get("started_at")) <= start <= end
         <= utc(gate.get("completed_at")) <= utc(run.get("updated_at")), "TIME_LINEAGE")
    need(start.astimezone(NY).date() == end.astimezone(NY).date(), "MIDNIGHT_AMBIGUITY")
    need(callable(permit_compute) and permit_compute(start, "schedule") is False
         and permit_compute(end, "schedule") is False, "CLOSED_SESSION_NOT_PROVEN")
    return "CLOSED_SESSION_NOOP"
