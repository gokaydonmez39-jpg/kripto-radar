#!/usr/bin/env python3
"""Read-only GitHub Actions execution witness for the XRAY preopen control plane.

Unlike YAML/cron checks, this records actual runs. Green CI != a current
C4.17 PRIMARY MC, terminal, candidate, device receipt, or production release.
Requires only the Actions read permission; never dispatches or writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

REPO="gokaydonmez39-jpg/kripto-radar"
UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
SCHEMA="XRAY_MONDAY_LIVE_ACTIONS_EXECUTION_WITNESS_V1"
WORKFLOWS={
    "root":"nasdaq-xray-daily.yml",
    "pre_mc":"xray-canonical-current-pre-mc.yml",
    "post_mc":"xray-canonical-current-post-mc.yml",
    "final":"xray-canonical-current-final.yml",
    "preopen":"xray-preopen-source-audit.yml",
    "watchdog":"xray-github-native-root-watchdog.yml",
    "delivery":"nasdaq-xray-delivery.yml",
    "e2e":"xray-e2e-production-readiness.yml",
}
SUCCESS="completed"

def stamp(v):
    if not isinstance(v,str):raise ValueError("RUN_TIMESTAMP_INVALID")
    r=dt.datetime.fromisoformat(v.replace("Z","+00:00"))
    if r.tzinfo is None:raise ValueError("RUN_TIMESTAMP_NO_TIMEZONE")
    return r.astimezone(UTC)

def summarize(now,workflow,runs):
    """Do not promote even a completed success to data, alpha or device PASS."""
    if now.tzinfo is None:raise ValueError("CLOCK_MUST_HAVE_TIMEZONE")
    if not isinstance(runs,list):raise ValueError("RUNS_MALFORMED")
    for r in runs:
        if not isinstance(r,dict) or r.get("head_branch") not in ("main",None):
            raise ValueError("RUN_IDENTITY_OR_BRANCH_UNVERIFIED")
        stamp(r.get("created_at"))
    ordered=sorted(runs,key=lambda r:stamp(r["created_at"]),reverse=True)
    latest=ordered[0] if ordered else None
    if latest is None:
        return {"state":"NO_RUN_OBSERVED","observed":False,"run_id":None,
                "last_success_id":None,"last_success_age_seconds":None}
    completed=next((r for r in ordered if
                    r.get("status")==SUCCESS and r.get("conclusion")=="success"
                    and (workflow!="root" or
                         stamp(r["created_at"]).astimezone(NY).weekday()<5)),None)
    age=(now.astimezone(UTC)-stamp(completed["created_at"])).total_seconds() if completed else None
    if workflow=="root" and latest.get("conclusion")=="success" and (
        stamp(latest["created_at"]).astimezone(NY).weekday()>=5):
        state="WEEKEND_GREEN_JOB_QUOTA_SKIP_NOT_DATA_HEARTBEAT"
    elif latest.get("status")!=SUCCESS:
        state="PENDING_OR_RUNNING_NOT_RECOVERY"
    elif latest.get("conclusion")!="success":
        state="FAILED_OR_CANCELLED_NOT_SUCCESS"
    else:
        state="JOB_SUCCESS_ONLY_NO_DATA_OR_DEVICE_AUTHORITY"
    return {
        "state":state,"observed":True,
        "run_id":latest.get("id"),
        "status":latest.get("status"),"conclusion":latest.get("conclusion"),
        "created_at_utc":latest.get("created_at"),
        "head_sha":latest.get("head_sha"),
        "last_success_id":completed.get("id") if completed else None,
        "last_success_age_seconds":round(age) if age is not None else None,
    }

def verify_response(rows):
    if not isinstance(rows,dict) or not isinstance(rows.get("workflow_runs"),list):
        raise RuntimeError("GITHUB_WORKFLOW_RUNS_UNAVAILABLE")
    return rows["workflow_runs"]

def selftest():
    date=dt.datetime(2026,10,12,4,5,tzinfo=UTC)
    run=lambda id,date,status="completed",conclusion="success":{
        "id":id,"created_at":date,"head_branch":"main",
        "status":status,"conclusion":conclusion,"head_sha":"a"*40,
    }
    sunday=run(1,"2026-10-12T03:59:00Z")
    friday=run(2,"2026-10-09T20:35:00Z")
    m=summarize(date,"root",[sunday,friday])
    assert m["state"]=="WEEKEND_GREEN_JOB_QUOTA_SKIP_NOT_DATA_HEARTBEAT"
    assert m["last_success_id"]==2 and m["last_success_age_seconds"]>4500
    monday=run(3,"2026-10-12T04:01:00Z")
    m=summarize(date,"root",[sunday,monday])
    assert m["last_success_id"]==3 and m["last_success_age_seconds"]==240
    assert m["state"]=="JOB_SUCCESS_ONLY_NO_DATA_OR_DEVICE_AUTHORITY"
    assert summarize(date,"pre_mc",[sunday])["last_success_id"]==1
    assert summarize(date,"final",[])["state"]=="NO_RUN_OBSERVED"
    assert summarize(date,"root",[run(4,"2026-10-12T04:02:00Z",
                                     "in_progress",None)])["state"]=="PENDING_OR_RUNNING_NOT_RECOVERY"
    assert summarize(date,"delivery",[run(5,"2026-10-12T04:03:00Z",
                                         "completed","failure")])["state"]=="FAILED_OR_CANCELLED_NOT_SUCCESS"
    for value in ({"workflow_runs":None},{"error":"missing"},[]):
        try:verify_response(value)
        except RuntimeError:pass
        else:raise AssertionError("INVALID_GITHUB_RESPONSE_ACCEPTED")
    try:summarize(dt.datetime(2026,10,12,4,5),"root",[])
    except ValueError:pass
    else:raise AssertionError("NAIVE_CLOCK_ACCEPTED")
    print("XRAY_MONDAY_LIVE_ACTIONS_SELFTEST=PASS_WEEKEND_ROOT_SUNDAY_GREEN_NOT_MONDAY_HEARTBEAT_NO_FAKE_RECEIPT")

def github(path,token):
    if not token or not path.startswith("/"):raise RuntimeError("GITHUB_AUTH_UNAVAILABLE")
    url="https://api.github.com/repos/"+REPO+path
    request=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"XRAY-Monday-Live-Actions-Attestor",
    })
    with urllib.request.urlopen(request,timeout=18) as result:
        if result.status!=200:raise RuntimeError("GITHUB_ACTIONS_HTTP_NON_200")
        return json.loads(result.read(3000000))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if not a.out:p.error("--out required")
    if os.environ.get("GITHUB_REPOSITORY")!=REPO:
        raise RuntimeError("GITHUB_REPOSITORY_MISMATCH")
    token=os.environ.get("GITHUB_TOKEN","")
    head_a=github("/git/ref/heads/main",token)["object"]["sha"]
    now=dt.datetime.now(UTC)
    entries={}
    for key,name in WORKFLOWS.items():
        runs=verify_response(github(
            "/actions/workflows/"+name+"/runs?per_page=20&branch=main",token))
        entries[key]=summarize(now,key,runs)
    head_b=github("/git/ref/heads/main",token)["object"]["sha"]
    main_exact=bool(head_a and head_a==head_b)
    if not main_exact:raise RuntimeError("GITHUB_MAIN_CHANGED_DURING_ACTIONS_AUDIT")
    result={
        "schema":SCHEMA,"generated_at_utc":now.isoformat(),"main_sha":head_a,
        "main_stable_during_observation":True,
        "execution_witnesses":entries,
        "root_fresh_weekday_job_only":bool(
            entries["root"]["last_success_age_seconds"] is not None
            and -60<=entries["root"]["last_success_age_seconds"]<=4500
        ),
        "scheduler_ready_for_alpha_attested":False,
        "full_end_to_end_research_attested":False,
        "registered_r92_attested":False,
        "real_user_device_receipt_attested":False,
        "alpha_authority":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_MONDAY_LIVE_ACTIONS=OBSERVED_"+str(len(entries)))
    print("XRAY_MONDAY_ROOT_WEEKDAY_GREEN_AGE_BOUND="+
          str(result["root_fresh_weekday_job_only"]).lower())
    print("XRAY_MONDAY_USER_DELIVERY_RECEIPT=UNVERIFIED")
    print("XRAY_MONDAY_LIVE_ACTIONS_NOT_RESEARCH_GO=TRUE")

if __name__=="__main__":main()
