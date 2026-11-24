#!/usr/bin/env python3
"""Collect the existing NASDAQ B source proofs as one allowlisted record."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import re
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



# Optional A witness. No event keys, symbols, account fields, or raw logs enter the note.
A_SCHEMA = "XRAY_477_A_SOURCE_ENVELOPE_V1"
A_SCOPE = "3d1d226e2ef511570b2abd57e59c74d2c2156e6eed9baf4a08b8d3df82223060"
A_ALGO = "0c137ecbdaf0eb68dbab3a642cfd501e4af61641b52367607fe616713af32523"
A_ALGO_NEXT = "cac4dd7b729e23cd4f6e4c181f569ef286858c1473217e46358202f595f7723c"


def a_source_algo(asof: str) -> str:
    return A_ALGO_NEXT if asof >= "2026-11-23" else A_ALGO


# Recover delimiters only for the exact known, non-secret NEON child.
# No scalar unmasking, general substitution or synthesized evidence.
_A_NEON_MASK = re.compile(
    r'"neon_shadow"\s*:\s*\*\*\*("[^*\r\n]+?)\*\*\*(?=\s*,\s*"new_entries"\s*:)'
)
_A_NEON_CHILD = re.compile(
    r'"asof"\s*:\s*"(\d{4}-\d\d-\d\d)"\s*,\s*'
    r'"notification_sent"\s*:\s*false\s*,\s*"orders_sent"\s*:\s*0\s*,\s*'
    r'"scored"\s*:\s*477\s*,\s*"status"\s*:\s*"NEON_SHADOW_477_READY_PRIVATE_NO_DELIVERY"'
)


def a_receipt_object(text: str):
    child_asof = None
    if text.startswith('***"') and text.endswith("***"):
        text = "{" + text[3:-3] + "}"
        if "***" in text:
            found = list(_A_NEON_MASK.finditer(text))
            if len(found) != 1 or text.count("***") != 2:
                return None
            match = found[0]
            child = _A_NEON_CHILD.fullmatch(match.group(1))
            if child is None:
                return None
            child_asof = child.group(1)
            text = text[:match.start()] + '"neon_shadow": {' + match.group(1) + "}" + text[match.end():]
    if "***" in text or not text.startswith("{") or not text.endswith("}"):
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict) or (child_asof is not None and obj.get("asof_et") != child_asof):
        return None
    return obj


def a_log_rows(log: str, job: dict) -> list[tuple[str, dict]]:
    started, ended = utc(job["started_at"]), utc(job["completed_at"])
    found = []
    for raw in log.splitlines():
        stamp, sep, text = raw.partition(" ")
        if not sep or not STAMP.fullmatch(stamp) or not started <= utc(stamp) < ended + dt.timedelta(seconds=1):
            continue
        obj = a_receipt_object(text.strip())
        if obj is not None:
            found.append((stamp, obj))
    return found


def a_supplement(jobs: dict, logs: dict[str, str], asof: str, source_proof: list) -> dict:
    rows = [a_log_rows(logs[name], jobs[name]) for name in NAMES[:3]]
    scan, follow, guard = rows
    new = json.loads(source_proof[0]["lines"][1][1])["candidates"]

    def match(pool, predicate, label):
        return one([(t, o) for t, o in pool if predicate(o)], "A_SOURCE_" + label)

    def today(o):
        return o.get("asof_et") == asof

    s, _ = match(scan, lambda o: today(o) and o.get("no_execution") is True
                 and o.get("final_ready") is True
                 and all(type(o.get(k)) is int and o[k] == 477 for k in ("universe", "processed", "valid"))
                 and all(type(o.get(k)) is int and o[k] == 0 for k in ("invalid_or_missing", "remaining"))
                 and type(o.get("new_entries")) is int and o["new_entries"] == new
                 and o.get("scope_sha256") == A_SCOPE and o.get("analysis_fingerprint_sha256") == a_source_algo(asof),
                 "SCAN")
    o, outbox = match(scan, lambda x: today(x) and x.get("status") == "AL_OUTBOX_PENDING_READBACK_PASS"
                      and type(x.get("technical_al")) is int and x["technical_al"] == new
                      and type(x.get("messages_sent")) is int and x["messages_sent"] == 0
                      and x.get("device_ack") is False and count(x.get("new_pending"), 477)
                      and count(x.get("new_suppressed"), 477)
                      and x["new_pending"] + x["new_suppressed"] <= new, "OUTBOX")
    p, _ = match(follow, lambda x: today(x) and x.get("status") == "PANEL_READBACK_PASS"
                 and x.get("device_ack") is False, "PANEL")
    l, facts = match(follow, lambda x: today(x) and x.get("status") == "LIFECYCLE_READBACK_PASS"
                     and x.get("notification_delivery") == "NOT_ATTEMPTED_BY_GITHUB"
                     and x.get("device_ack") is False and count(x.get("terminal_updates")), "LIFECYCLE")
    g, _ = match(guard, lambda x: x.get("last_verified_scan_asof") == asof
                 and x.get("schema") == "XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1"
                 and x.get("status") == "READ_ONLY_EVIDENCE_AUDIT" and x.get("execution") == "NONE"
                 and type(x.get("messages_sent")) is int and x["messages_sent"] == 0
                 and type(x.get("sheet_writes")) is int and x["sheet_writes"] == 0, "GUARD")
    if g != source_proof[2]["lines"][0][0]:
        raise EvidenceError("A_AND_B_GUARD_WITNESS_DRIFT")
    return {"schema": A_SCHEMA, "scan": s, "outbox": [o, outbox["new_pending"], outbox["new_suppressed"]],
            "panel": p, "life": [l, facts["terminal_updates"]], "guard": g}


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
    try:
        extra = a_supplement(jobs, logs, asof, out)
        next_obj = {**obj, "a": extra}
        if len(json.dumps(next_obj, separators=(",", ":"))) <= 2500:
            return next_obj
    except EvidenceError:
        # A may still use its established exact job-log path. Missing A evidence
        # cannot block or weaken the pre-existing B note.
        pass
    return obj


def collect() -> dict:
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
    return envelope(jobs, logs, run, sha, asof, dt.datetime.now(dt.timezone.utc))
