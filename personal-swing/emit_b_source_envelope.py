#!/usr/bin/env python3
"""Emit the existing NASDAQ B source proofs in one small, redacted score-job log record."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "gokaydonmez39-jpg/kripto-radar"
API = f"https://api.github.com/repos/{REPO}"
SCHEMA = "XRAY_477_B_SOURCE_ENVELOPE_V1"
CARRIER = "daily-private-score-acceptance"
NAMES = ("daily-private-scan", "private-episode-followups", "guardian-acceptance", CARRIER)
ALL_JOBS = set(NAMES) | {"offline-guard", "private-sheets-auth-preflight"}
SCAN_MARK = "XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE"
SCORE_MARK = "XRAY_DAILY_SWING_SCORE=PRIVATE_READBACK_PASS_ASOF_{}_NOT_CHATGPT_DELIVERY"
SCAN_FIELDS = ("status", "asof_et", "candidates")
FOLLOW_FIELDS = ("status", "asof_et", "execution", "active_episodes", "scoreable")
GUARD_FIELDS = ("schema", "status", "execution", "sheet_writes", "last_verified_scan_asof",
                "last_asof_score", "score_count", "score_hold_count", "scored_active_episodes")
MAX_BODY = 4 * 1024 * 1024
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")


class EvidenceError(ValueError):
    pass


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = urllib.parse.urlsplit(newurl)
        if new.scheme != "https" or new.username or new.password or not new.hostname:
            raise EvidenceError("INSECURE_GITHUB_REDIRECT")
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result:
            result.remove_header("Authorization")
        return result


def utc(value: str) -> dt.datetime:
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise EvidenceError("TIMESTAMP_INVALID")
    return dt.datetime.fromisoformat(value[:-1] + "+00:00")


def one(items: list, error: str):
    if len(items) != 1:
        raise EvidenceError(error)
    return items[0]


def github_get(path: str, token: str) -> str:
    if not (path.startswith("/actions/runs/") or path.startswith("/actions/jobs/")):
        raise EvidenceError("GITHUB_PATH_INVALID")
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "xray-477-source-envelope",
    })
    req.add_unredirected_header("Authorization", f"Bearer {token}")
    with urllib.request.build_opener(SafeRedirect()).open(req, timeout=10) as response:
        data = response.read(MAX_BODY + 1)
    if len(data) > MAX_BODY:
        raise EvidenceError("GITHUB_RESPONSE_TOO_LARGE")
    return data.decode("utf-8")


def checked_jobs(body: dict, run_id: int, sha: str) -> dict:
    jobs = body.get("jobs")
    if body.get("total_count") != len(ALL_JOBS) or not isinstance(jobs, list) or len(jobs) != len(ALL_JOBS):
        raise EvidenceError("EOD_JOB_SET_INCOMPLETE")
    out = {}
    for name in ALL_JOBS:
        job = one([j for j in jobs if j.get("name") == name], "EOD_JOB_IDENTITY")
        if (type(job.get("id")) is not int or job["id"] <= 0 or job.get("run_id") != run_id
                or job.get("run_url") != f"{API}/actions/runs/{run_id}"
                or job.get("run_attempt") != 1 or job.get("head_sha") != sha
                or job.get("head_branch") != "main"):
            raise EvidenceError("EOD_JOB_BINDING")
        started = utc(job.get("started_at"))
        if name == CARRIER:
            if job.get("status") != "in_progress" or job.get("completed_at") is not None:
                raise EvidenceError("CARRIER_NOT_ACTIVE")
        elif (job.get("status") != "completed" or job.get("conclusion") != "success"
                or utc(job.get("completed_at")) < started):
            raise EvidenceError("UPSTREAM_JOB_NOT_SUCCESSFUL")
        out[name] = job
    if len({job["id"] for job in out.values()}) != len(ALL_JOBS):
        raise EvidenceError("EOD_JOB_DUPLICATION")
    return out


def count(value, maximum=1_000_000) -> bool:
    return type(value) is int and 0 <= value <= maximum


def uri_free_fields(obj: dict, keys: tuple[str, ...]) -> dict:
    return {key: obj[key] for key in keys}


def receipts(log: str, job: dict, asof: str, index: int) -> list[list[str]]:
    started, ended = utc(job["started_at"]), utc(job["completed_at"])
    exact, typed = [], []
    for raw in log.splitlines():
        stamp, sep, data = raw.partition(" ")
        if not sep or not STAMP.fullmatch(stamp) or not started <= utc(stamp) < ended + dt.timedelta(seconds=1):
            continue
        data = data.strip()
        if index == 0 and data == SCAN_MARK:
            exact.append([stamp, data])
        if data.startswith('***"') and data.endswith("***"):
            data = "{" + data[3:-3] + "}"
        if not data.startswith("{") or not data.endswith("}"):
            continue
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        status = obj.get("status")
        fields = None
        if index == 0 and status == "PRIVATE_SHEET_READBACK_PASS" and obj.get("asof_et") == asof:
            if count(obj.get("candidates"), 477):
                fields = SCAN_FIELDS
        if index == 1 and status in ("SWING_SCORE_PRIVATE_READBACK_PASS", "SWING_SCORE_IDEMPOTENT_READBACK_PASS"):
            if (obj.get("asof_et") == asof and obj.get("execution") == "NONE"
                    and count(obj.get("active_episodes")) and count(obj.get("scoreable"))
                    and obj["scoreable"] <= obj["active_episodes"]):
                fields = FOLLOW_FIELDS
        if index == 2 and status == "READ_ONLY_EVIDENCE_AUDIT":
            if (obj.get("schema") == "XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1"
                    and obj.get("execution") == "NONE" and type(obj.get("sheet_writes")) is int
                    and obj["sheet_writes"] == 0 and obj.get("last_verified_scan_asof") == asof
                    and obj.get("last_asof_score") == "SUMMARY_PRESENT"
                    and all(count(obj.get(k)) for k in GUARD_FIELDS[-3:])
                    and obj["score_count"] <= obj["scored_active_episodes"]
                    and obj["score_hold_count"] <= obj["scored_active_episodes"]):
                fields = GUARD_FIELDS
        if fields:
            allowed = uri_free_fields(obj, fields)
            typed.append([stamp, json.dumps(allowed, separators=(",", ":"), ensure_ascii=True)])
    line = one(typed, f"SOURCE_RECEIPT_{index}_UNAVAILABLE")
    return [one(exact, "SCAN_HANDOFF_UNAVAILABLE"), line] if index == 0 else [line]


def envelope(jobs: dict, logs: dict[str, str], run_id: int, sha: str, asof: str,
             now: dt.datetime) -> dict:
    if dt.date.fromisoformat(asof).isoformat() != asof:
        raise EvidenceError("SOURCE_ASOF_INVALID")
    if now < utc(jobs[CARRIER]["started_at"]):
        raise EvidenceError("CARRIER_TIMESTAMP_INVALID")
    out = [{"jobId": jobs[name]["id"], "jobName": name,
            "lines": receipts(logs[name], jobs[name], asof, index)}
           for index, name in enumerate(NAMES[:3])]
    follow = json.loads(out[1]["lines"][0][1])
    guardian = json.loads(out[2]["lines"][0][1])
    if (follow["active_episodes"], follow["scoreable"]) != (guardian["scored_active_episodes"], guardian["score_count"]):
        raise EvidenceError("B_CROSS_RECEIPT_COUNTS")
    out.append({"jobId": jobs[CARRIER]["id"], "jobName": CARRIER,
                "lines": [[now.isoformat(timespec="milliseconds").replace("+00:00", "Z"), SCORE_MARK.format(asof)]]})
    obj = {"schema": SCHEMA, "asof": asof, "run": run_id, "head": sha, "proof": out}
    if len(json.dumps(obj, separators=(",", ":"))) > 2500:
        raise EvidenceError("B_ENVELOPE_UNEXPECTED_SIZE")
    return obj


def main() -> None:
    if (os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get("GITHUB_EVENT_NAME") != "schedule"
            or os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or os.environ.get("GITHUB_WORKFLOW_REF", "").split("@", 1)[0]
            != REPO + "/.github/workflows/xray-personal-477-eod.yml"):
        raise EvidenceError("NATURAL_EOD_ONLY")
    run, sha = int(os.environ["GITHUB_RUN_ID"]), os.environ["GITHUB_SHA"]
    asof, token = os.environ["XRAY_SCORE_ASOF"], os.environ["GH_TOKEN"]
    if run < 1 or not re.fullmatch(r"[a-f0-9]{40}", sha) or not token:
        raise EvidenceError("RUN_IDENTITY_INVALID")
    jobs = checked_jobs(json.loads(github_get(f"/actions/runs/{run}/attempts/1/jobs?per_page=100", token)), run, sha)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as worker:
        submitted = {name: worker.submit(github_get, f"/actions/jobs/{jobs[name]['id']}/logs", token)
                     for name in NAMES[:3]}
        logs = {name: result.result() for name, result in submitted.items()}
    obj = envelope(jobs, logs, run, sha, asof, dt.datetime.now(dt.timezone.utc))
    print(SCHEMA + " " + json.dumps(obj, separators=(",", ":"), ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except EvidenceError as error:
        print("XRAY_477_B_SOURCE_ENVELOPE_HOLD=" + str(error), file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError, OSError, OverflowError, TimeoutError, urllib.error.HTTPError):
        print("XRAY_477_B_SOURCE_ENVELOPE_HOLD=SOURCE_READ_OR_SCHEMA_UNVERIFIED", file=sys.stderr)
        sys.exit(1)
