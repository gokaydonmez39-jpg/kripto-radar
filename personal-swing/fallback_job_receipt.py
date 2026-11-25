#!/usr/bin/env python3
"""Independent GitHub-only six-job receipt for existing NASDAQ 477 fallback.

This validates the natural producer's complete GitHub job DAG, not its private
Google Sheet rows, a ChatGPT chat_ref, or iPhone delivery. Pure gate plus
read-only GitHub REST GETs, never a dispatch, broker call or Sheet access.
"""
import argparse
import json
import os
import re
import sys
from datetime import date,datetime,timedelta,timezone
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

import schedule_failover

REPO="gokaydonmez39-jpg/kripto-radar"
PATH=".github/workflows/xray-personal-477-eod.yml"
NAMES=(
    "offline-guard",
    "private-sheets-auth-preflight",
    "daily-private-scan",
    "private-episode-followups",
    "guardian-acceptance",
    "daily-private-score-acceptance",
)
REQUIRED_STEPS={
    "offline-guard": (
        "Static tests before any data API access",
        "Personal scheduler and official research-shadow fail-closed contracts",
        "Require real natural EOD GitHub-run receipt (GET only, no tag claim)",
    ),
    "private-sheets-auth-preflight": (
        "Verify service-account access and private worksheet headers without writes",),
    "daily-private-scan": (
        "Run no-broker personal EOD scan (ephemeral private data)",
        "Verify exact private 477-scoped handoff without publishing signals",
        "Private Google Sheets writer (authorized service account only)",
        "Reserve verified new AL events PENDING in private outbox (NO PUSH)",
    ),
    "private-episode-followups": (
        "Track each open private episode from exact completed XNAS daily IEX bars",
        "Reconcile PANEL from verified private scan and immutable candidate ledger",
        "Private EOD swing ranking V1 (advisory; never blocks AL or Guardian)",
    ),
    "guardian-acceptance": (
        "Independent Guardian gates and bounded PANEL-only self-repair",),
    "daily-private-score-acceptance": (
        "Gate raw score outcome after Guardian (fail closed)",),
}
SHA40=re.compile(r"[0-9a-f]{40}")
RUN_ID=re.compile(r"[1-9][0-9]*")
ASOF_RE=re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}")
EOD_RUN_BASE="https://api.github.com/repos/"+REPO+"/actions/runs/"
WORKFLOW_RUN_BASE=("https://api.github.com/repos/"+REPO+
                   "/actions/workflows/xray-personal-477-eod.yml")
PUBLIC_ERRORS=frozenset((
    "PRIMARY_RUN_ORIGIN_NOT_VERIFIED",
    "PRIMARY_JOB_RECEIPT_MISSING",
    "PRIMARY_JOB_STEP_RECEIPT_MISSING",
    "PRIMARY_JOB_DAG_UNVERIFIED",
    "PRIMARY_RUN_LIST_DETAIL_DRIFT",
    "PRIMARY_EOD_TIME_WINDOW_UNVERIFIED",
    "PRIMARY_EOD_EPOCH_AMBIGUOUS",
    "PRIMARY_API_COLLECTION_UNTRUSTED",
    "PRIMARY_EOD_GITHUB_READ_UNAVAILABLE",
    "PRIMARY_AUDIT_TRIGGER_UNAUTHORIZED",
    "PRIMARY_AUDIT_ASOF_INVALID",
))


class ReceiptHold(ValueError):
    pass


def need(ok,why):
    if not ok:
        raise ReceiptHold(why)


def utc(value):
    if not isinstance(value,str):
        return None
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def valid_day(asof):
    if not isinstance(asof,str) or not ASOF_RE.fullmatch(asof):
        return False
    try:
        return date.fromisoformat(asof).isoformat()==asof
    except ValueError:
        return False


def validate(run,jobs,asof,observed_at):
    """No market data, private Sheets, dispatch, delivery or mutation."""
    need(valid_day(asof),"PRIMARY_AUDIT_ASOF_INVALID")
    need(isinstance(observed_at,datetime) and
         observed_at.tzinfo is not None and
         observed_at.utcoffset() is not None,"PRIMARY_EOD_TIME_WINDOW_UNVERIFIED")
    now=observed_at.astimezone(timezone.utc)
    need(isinstance(run,dict) and
         type(run.get("id")) is int and run["id"]>0 and
         run.get("repository",{}).get("full_name")==REPO and
         run.get("path")==PATH and
         run.get("event")=="schedule" and
         run.get("head_branch")=="main" and
         type(run.get("run_attempt")) is int and run["run_attempt"]==1 and
         run.get("status")=="completed" and
         run.get("conclusion")=="success" and
         isinstance(run.get("head_sha"),str) and
         SHA40.fullmatch(run["head_sha"]) is not None,
         "PRIMARY_RUN_ORIGIN_NOT_VERIFIED")
    # XNAS calendar—not wall-clock subtraction—includes early closes/holidays.
    try:
        import exchange_calendars as ec
        cal=ec.get_calendar("XNAS")
        need(cal.is_session(asof),"PRIMARY_EOD_TIME_WINDOW_UNVERIFIED")
        cutoff=(cal.session_close(asof).to_pydatetime().astimezone(timezone.utc)
                +timedelta(minutes=45))
    except ReceiptHold:
        raise
    except Exception:
        raise ReceiptHold("PRIMARY_EOD_TIME_WINDOW_UNVERIFIED") from None
    created,updated=utc(run.get("created_at")),utc(run.get("updated_at"))
    need(created is not None and updated is not None and
         cutoff <= created <= cutoff+timedelta(hours=10) and
         created <= updated <= now,
         "PRIMARY_EOD_TIME_WINDOW_UNVERIFIED")
    need(isinstance(jobs,dict) and
         isinstance(jobs.get("total_count"),int) and
         jobs["total_count"]==len(NAMES) and
         isinstance(jobs.get("jobs"),list) and
         len(jobs["jobs"])==len(NAMES),
         "PRIMARY_JOB_RECEIPT_MISSING")
    entries=jobs["jobs"]
    need(all(isinstance(j,dict) and
             type(j.get("id")) is int and j["id"]>0 and
             type(j.get("run_id")) is int and j["run_id"]==run["id"] and
             j.get("status")=="completed" and
             j.get("conclusion")=="success" for j in entries) and
         len({j["id"] for j in entries})==len(NAMES) and
         {j.get("name") for j in entries}==set(NAMES),
         "PRIMARY_JOB_RECEIPT_MISSING")
    # A green job name or a relabelled job from another attempt/commit is
    # NOT the canonical natural run's receipt. Bind every job to the exact
    # GitHub REST run URL, attempt, protected branch and immutable SHA.
    # The public GitHub jobs endpoint exposes these fields.
    job_times={}
    expected_url=EOD_RUN_BASE+str(run["id"])
    for job in entries:
        begun,ended=utc(job.get("started_at")),utc(job.get("completed_at"))
        need(type(job.get("run_attempt")) is int and
             job["run_attempt"]==1 and
             job.get("run_url")==expected_url and
             job.get("head_sha")==run["head_sha"] and
             job.get("head_branch")=="main" and
             begun is not None and ended is not None and
             created<=begun<=ended<=updated,
             "PRIMARY_JOB_RECEIPT_MISSING")
        job_times[job["name"]]=(begun,ended)
    # Assert the real EOD needs-DAG at the timestamps recorded by GitHub.
    # The authorization preflight and vendor scan may run concurrently;
    # Guardian must wait for BOTH, and score must wait for Guardian.
    edges=(
        ("offline-guard","private-sheets-auth-preflight"),
        ("offline-guard","daily-private-scan"),
        ("daily-private-scan","private-episode-followups"),
        ("private-episode-followups","guardian-acceptance"),
        ("private-sheets-auth-preflight","guardian-acceptance"),
        ("guardian-acceptance","daily-private-score-acceptance"),
    )
    need(all(job_times[parent][1]<=job_times[child][0]
             for parent,child in edges),"PRIMARY_JOB_DAG_UNVERIFIED")
    for job in entries:
        names=REQUIRED_STEPS.get(job["name"],())
        steps=job.get("steps")
        need(isinstance(steps,list),"PRIMARY_JOB_STEP_RECEIPT_MISSING")
        prev_number=0
        prev_end=None
        job_begin,job_end=job_times[job["name"]]
        for expected in names:
            found=[x for x in steps if isinstance(x,dict) and
                   x.get("name")==expected]
            need(len(found)==1 and
                 found[0].get("status")=="completed" and
                 found[0].get("conclusion")=="success",
                 "PRIMARY_JOB_STEP_RECEIPT_MISSING")
            step=found[0]
            begun,ended=utc(step.get("started_at")),utc(step.get("completed_at"))
            number=step.get("number")
            need(type(number) is int and number>prev_number and
                 begun is not None and ended is not None and
                 job_begin<=begun<=ended<=job_end and
                 (prev_end is None or prev_end<=begun),
                 "PRIMARY_JOB_STEP_RECEIPT_MISSING")
            prev_number,prev_end=number,ended
    return {
        "status":"PRIMARY_EOD_SIX_JOB_PROVEN_GH_ONLY",
        "asof_et":asof,"run_id":run["id"],
        "source_event":"schedule",
        "private_sheet_verified":False,
        "ab_release_authorized":False,
        "device_ack":"UNKNOWN",
        "orders":False,
    }


def github_get(url,token):
    need(isinstance(token,str) and bool(token),
         "PRIMARY_EOD_GITHUB_READ_UNAVAILABLE")
    need(url.startswith("https://api.github.com/repos/"+REPO+"/actions/"),
         "PRIMARY_EOD_GITHUB_READ_UNAVAILABLE")
    request=Request(url,method="GET",headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"xray-personal477-readonly-source-audit",
    })
    with urlopen(request,timeout=25) as response:
        need(response.status==200,"PRIMARY_EOD_GITHUB_READ_UNAVAILABLE")
        return json.load(response)


def _same_run_identity(listed, detail):
    """Immutable source fields must agree across independently read endpoints.

    A matching numeric run ID alone cannot bind the unique selected producer
    to a substituted commit or timestamp. Do not request jobs on disagreement.
    The mutable updated_at field is independently checked by validate().
    """
    if not isinstance(listed, dict) or not isinstance(detail, dict):
        return False
    for key in ("id", "run_attempt"):
        if type(listed.get(key)) is not int or type(detail.get(key)) is not int:
            return False
    fields = ("id", "run_attempt", "head_sha", "head_branch", "event",
              "path", "status", "conclusion")
    if any(listed.get(key) != detail.get(key) for key in fields):
        return False
    for row in (listed, detail):
        repo = row.get("repository")
        if not isinstance(repo, dict) or repo.get("full_name") != REPO:
            return False
    created = utc(listed.get("created_at"))
    return created is not None and created == utc(detail.get("created_at"))


def audit(asof,*,now=None,get=None):
    """Independently re-fetch natural run and its exact six jobs; no POST."""
    now=now if now is not None else datetime.now(timezone.utc)
    need(valid_day(asof),"PRIMARY_AUDIT_ASOF_INVALID")
    need(isinstance(now,datetime) and now.tzinfo is not None and
         now.utcoffset() is not None,"PRIMARY_EOD_TIME_WINDOW_UNVERIFIED")
    need(callable(get),"PRIMARY_EOD_GITHUB_READ_UNAVAILABLE")
    runs=get(schedule_failover.windowed_runs_url(WORKFLOW_RUN_BASE,now))
    need(isinstance(runs,dict) and
         type(runs.get("total_count")) is int and
         isinstance(runs.get("workflow_runs"),list) and
         runs["total_count"]==len(runs["workflow_runs"]) and
         len(runs["workflow_runs"])<100,
         "PRIMARY_API_COLLECTION_UNTRUSTED")
    verdict,official_asof=schedule_failover.decision(now,runs["workflow_runs"])
    need(verdict=="NOOP_CURRENT_EPOCH_RUN_EXISTS" and official_asof==asof,
         "PRIMARY_EOD_EPOCH_AMBIGUOUS")
    # EXACTLY ONE natural producer, across ALL statuses, is necessary.
    # A second queued/running/failed run may have made partial private
    # writes, so a green first producer cannot prove a unique source.
    # Never promote a successful-only subset into canonical acceptance.
    natural=[x for x in runs["workflow_runs"] if isinstance(x,dict)
             and x.get("event")=="schedule" and
             x.get("head_branch")=="main"]
    need(len(natural)==1 and
         natural[0].get("status")=="completed" and
         natural[0].get("conclusion")=="success" and
         type(natural[0].get("id")) is int and natural[0]["id"]>0,
         "PRIMARY_EOD_EPOCH_AMBIGUOUS")
    rid=natural[0]["id"]
    original=get(EOD_RUN_BASE+str(rid))
    need(_same_run_identity(natural[0], original),
         "PRIMARY_RUN_LIST_DETAIL_DRIFT")
    jobs=get(EOD_RUN_BASE+str(rid)+"/jobs?per_page=100")
    return validate(original,jobs,asof,now)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--asof",required=True)
    args=parser.parse_args(argv)
    try:
        need(os.environ.get("GITHUB_EVENT_NAME")=="schedule" and
             os.environ.get("GITHUB_REF")=="refs/heads/main" and
             os.environ.get("GITHUB_RUN_ATTEMPT")=="1" and
             os.environ.get("GITHUB_REPOSITORY")==REPO,
             "PRIMARY_AUDIT_TRIGGER_UNAUTHORIZED")
        token=os.environ.get("GITHUB_TOKEN","")
        result=audit(args.asof,get=lambda url:github_get(url,token))
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as exc:
        # Do not expose response bodies/headers/tokens/URLs/private rows.
        reason=(str(exc) if isinstance(exc,ReceiptHold)
                and str(exc) in PUBLIC_ERRORS else
                "PRIMARY_EOD_GITHUB_READ_UNAVAILABLE")
        print(json.dumps({"status":"PRIMARY_EOD_SOURCE_AUDIT_HOLD",
                          "reason_code":reason,"private_sheet_verified":False,
                          "ab_release_authorized":False,"device_ack":"UNKNOWN",
                          "orders":False},sort_keys=True))
        return 3


if __name__=="__main__":
    sys.exit(main())
