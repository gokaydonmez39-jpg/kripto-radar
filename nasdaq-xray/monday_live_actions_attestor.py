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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo
from root_weekend_quota_guard import permit_compute

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
    "research_watch":"xray-research-watch-radar.yml",
    "strict_g9":"xray-strict-g9-gate.yml",
    "account_reconcile":"xray-account-gate-reconcile.yml",
    "live_truth":"xray-live-truth-attestation.yml",
    "stage_relay":"xray-native-stage-relay-live.yml",
    "manual_research":"xray-manual-decision-research-shadow.yml",
    "final_overlay":"xray-final-gate-overlay-v2.yml",
    "legacy_overlay":"xray-final-gate-overlay.yml",
    "resilience":"xray-resilience-observability.yml",
}
# Additional scheduled SHADOW/diagnostic workflows: observe but do not demand
# activation of paid licensed transports. Disabled is legitimate fail-closed.
SUPPLEMENTAL_SCHEDULED={
    "alpaca_delayed_sip":"xray-alpaca-delayed-sip-research.yml",
    "massive_encrypted_history":"xray-massive-grouped-history-resume.yml",
    "multi_provider_shadow":"xray-multi-provider-research-shadow.yml",
    "sec_mirror_cik":"xray-sec-mirror-cik-shadow.yml",
    "sec_transport_probe":"xray-sec-transport-matrix-probe.yml",
    "twelve_encrypted_history":"xray-twelve-history-resume.yml",
    "zero_cost_stage_verification":"xray-zero-cost-four-stage-verification.yml",
}
SUCCESS="completed"

def stamp(v):
    if not isinstance(v,str):raise ValueError("RUN_TIMESTAMP_INVALID")
    r=dt.datetime.fromisoformat(v.replace("Z","+00:00"))
    if r.tzinfo is None:raise ValueError("RUN_TIMESTAMP_NO_TIMEZONE")
    return r.astimezone(UTC)

def root_compute_event_eligible(run):
    """A green root invocation need not have executed Nasdaq data work."""
    event=run.get("event")
    # An explicit manual dispatch is an operational recovery or diagnostic,
    # not evidence that the unattended weekday data plane actually ran.
    # It may compute the last session on an exchange-closed day, so it must
    # not count as a fresh scheduled-session source heartbeat.
    if event not in ("schedule","push"):
        return False
    return permit_compute(stamp(run["created_at"]),event)


def summarize(now,workflow,runs):
    """Do not promote even a completed success to data, alpha or device PASS."""
    if now.tzinfo is None:raise ValueError("CLOCK_MUST_HAVE_TIMEZONE")
    if not isinstance(runs,list):raise ValueError("RUNS_MALFORMED")
    for r in runs:
        if not isinstance(r,dict) or r.get("head_branch")!="main":
            raise ValueError("RUN_IDENTITY_OR_BRANCH_UNVERIFIED")
        stamp(r.get("created_at"))
    ordered=sorted(runs,key=lambda r:stamp(r["created_at"]),reverse=True)
    latest=ordered[0] if ordered else None
    if latest is None:
        return {"state":"NO_RUN_OBSERVED","observed":False,"run_id":None,
                "last_success_id":None,"last_success_age_seconds":None,
                "latest_root_compute_eligible":False}
    completed=next((r for r in ordered if
                    r.get("status")==SUCCESS and r.get("conclusion")=="success"
                    and (workflow!="root" or root_compute_event_eligible(r))),None)
    age=(now.astimezone(UTC)-stamp(completed["created_at"])).total_seconds() if completed else None
    latest_root_compute_eligible=(workflow=="root" and
                                  root_compute_event_eligible(latest))
    if workflow=="root" and latest.get("conclusion")=="success" and not latest_root_compute_eligible:
        if stamp(latest["created_at"]).astimezone(NY).weekday()>=5:
            state="WEEKEND_GREEN_JOB_QUOTA_SKIP_NOT_DATA_HEARTBEAT"
        else:
            state="NASDAQ_CLOSED_OR_UNVERIFIED_GREEN_NO_DATA_HEARTBEAT"
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
        "latest_root_compute_eligible":latest_root_compute_eligible,
        "last_success_id":completed.get("id") if completed else None,
        "last_success_age_seconds":round(age) if age is not None else None,
    }

def verify_response(rows):
    if not isinstance(rows,dict) or not isinstance(rows.get("workflow_runs"),list):
        raise RuntimeError("GITHUB_WORKFLOW_RUNS_UNAVAILABLE")
    return rows["workflow_runs"]

def workflow_inventory(rows):
    """Require unique actively enabled workflows, not only historical green jobs."""
    if not isinstance(rows,list):
        raise RuntimeError("WORKFLOW_INVENTORY_UNAVAILABLE")
    by_path={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("path"),str):
            raise RuntimeError("WORKFLOW_INVENTORY_ROW_INVALID")
        path=row["path"]
        if path in by_path:
            raise RuntimeError("WORKFLOW_INVENTORY_DUPLICATE_PATH")
        by_path[path]=row
    found={}
    blockers=[]
    for key,basename in WORKFLOWS.items():
        expected_path=".github/workflows/"+basename
        row=by_path.get(expected_path)
        if row is None:
            found[key]={"state":"MISSING","path":expected_path}
            blockers.append(key+":MISSING")
            continue
        state=row.get("state")
        if state!="active":
            blockers.append(key+":"+str(state))
        found[key]={"id":row.get("id"),"state":state,"path":expected_path}
    additional={}
    for key,basename in SUPPLEMENTAL_SCHEDULED.items():
        path=".github/workflows/"+basename
        row=by_path.get(path)
        additional[key]={"path":path,
                         "state":row.get("state") if row else "MISSING",
                         "id":row.get("id") if row else None}
    return {"all_required_active":not blockers,"blockers":blockers,
            "required":found,"supplemental":additional,
            "supplemental_active_count":sum(x["state"]=="active"
                                            for x in additional.values()),
            "total_enumerated":len(rows)}

def fetch_workflow_inventory(token):
    first=github("/actions/workflows?per_page=100&page=1",token)
    total=first.get("total_count")
    rows=first.get("workflows")
    if (type(total) is not int or total<0 or total>1000
        or not isinstance(rows,list)):
        raise RuntimeError("WORKFLOW_INVENTORY_PAGINATION_UNVERIFIED")
    page=2
    while len(rows)<total:
        next_page=github("/actions/workflows?per_page=100&page="+str(page),token)
        chunk=next_page.get("workflows")
        if not isinstance(chunk,list) or not chunk or page>11:
            raise RuntimeError("WORKFLOW_INVENTORY_PAGE_MISSING")
        rows+=chunk
        page+=1
    if len(rows)!=total:
        raise RuntimeError("WORKFLOW_INVENTORY_COUNT_MISMATCH")
    return workflow_inventory(rows)

def selftest():
    date=dt.datetime(2026,10,12,4,5,tzinfo=UTC)
    run=lambda id,date,status="completed",conclusion="success":{
        "id":id,"created_at":date,"head_branch":"main",
        "status":status,"conclusion":conclusion,"head_sha":"a"*40,
        "event":"schedule",
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
    # Weekday exchange holiday green is not a source-data heartbeat.
    next_open=dt.datetime(2026,12,28,16,tzinfo=UTC)
    holiday=run(41,"2026-12-25T16:30:00Z")
    prior=run(42,"2026-12-24T17:00:00Z")
    h=summarize(next_open,"root",[holiday,prior])
    assert h["last_success_id"]==42 and h["run_id"]==41
    assert h["latest_root_compute_eligible"] is False
    assert h["state"]=="NASDAQ_CLOSED_OR_UNVERIFIED_GREEN_NO_DATA_HEARTBEAT"
    half=run(43,"2026-11-27T15:00:00Z")
    assert root_compute_event_eligible(half)
    manual=dict(holiday,event="workflow_dispatch")
    assert root_compute_event_eligible(manual) is False
    assert summarize(next_open,"root",[manual,prior])["last_success_id"]==42
    manual_open=dict(half,event="workflow_dispatch")
    assert root_compute_event_eligible(manual_open) is False
    unknown=dict(holiday,event=None)
    assert root_compute_event_eligible(unknown) is False
    assert summarize(next_open,"root",[unknown])["last_success_id"] is None
    from unittest.mock import patch
    with patch("root_weekend_quota_guard.mcal.get_calendar",
               side_effect=RuntimeError("CALENDAR_OUTAGE")):
        try:summarize(next_open,"root",[prior])
        except RuntimeError as e:assert "NASDAQ_SESSION_CALENDAR_UNAVAILABLE_FAIL_CLOSED" in str(e)
        else:raise AssertionError("CALENDAR_OUTAGE_PROMOTED_ROOT_COMPUTE")
    assert summarize(date,"pre_mc",[sunday])["last_success_id"]==1
    assert summarize(date,"final",[])["state"]=="NO_RUN_OBSERVED"
    for branch in (None,"feature/untrusted","refs/tags/v1"):
        untrusted=run(99,"2026-10-12T04:01:00Z")
        untrusted["head_branch"]=branch
        try:summarize(date,"root",[untrusted])
        except ValueError:pass
        else:raise AssertionError("NON_MAIN_ROOT_SUCCESS_ACCEPTED")
    # No Main/official authority may be inferred from missing branch metadata.
    good_branch=run(98,"2026-10-12T04:01:00Z")
    assert summarize(date,"root",[good_branch])["last_success_id"]==98
    assert summarize(date,"root",[run(4,"2026-10-12T04:02:00Z",
                                     "in_progress",None)])["state"]=="PENDING_OR_RUNNING_NOT_RECOVERY"
    assert summarize(date,"delivery",[run(5,"2026-10-12T04:03:00Z",
                                         "completed","failure")])["state"]=="FAILED_OR_CANCELLED_NOT_SUCCESS"
    for value in ({"workflow_runs":None},{"error":"missing"},[]):
        try:verify_response(value)
        except RuntimeError:pass
        else:raise AssertionError("INVALID_GITHUB_RESPONSE_ACCEPTED")
    good=[{"path":".github/workflows/"+v,"id":i+1,"state":"active"}
          for i,v in enumerate(WORKFLOWS.values())]
    assert workflow_inventory(good)["all_required_active"] is True
    assert len(workflow_inventory(good)["required"])==17
    assert len(workflow_inventory(good)["supplemental"])==7
    with_supplemental=good+[
        {"path":".github/workflows/"+v,"id":50+i,"state":"active"}
        for i,v in enumerate(SUPPLEMENTAL_SCHEDULED.values())]
    assert workflow_inventory(with_supplemental)["supplemental_active_count"]==7
    optional_disabled=[dict(x) for x in with_supplemental]
    optional_disabled[-1]["state"]="disabled_manually"
    assert workflow_inventory(optional_disabled)["all_required_active"] is True
    assert workflow_inventory(optional_disabled)["supplemental_active_count"]==6
    disabled=[dict(row) for row in good]
    disabled[2]["state"]="disabled_manually"
    assert workflow_inventory(disabled)["all_required_active"] is False
    assert workflow_inventory(disabled)["blockers"]==["post_mc:disabled_manually"]
    assert workflow_inventory(good[1:])["blockers"]==["root:MISSING"]
    try:workflow_inventory(good+good[:1])
    except RuntimeError:pass
    else:raise AssertionError("DUPLICATE_WORKFLOW_INVENTORY_ACCEPTED")
    try:workflow_inventory(None)
    except RuntimeError:pass
    else:raise AssertionError("MISSING_WORKFLOW_INVENTORY_ACCEPTED")
    try:summarize(dt.datetime(2026,10,12,4,5),"root",[])
    except ValueError:pass
    else:raise AssertionError("NAIVE_CLOCK_ACCEPTED")
    snapshot_retry_selftest()
    print("XRAY_MONDAY_LIVE_ACTIONS_SELFTEST=PASS_17_WORKFLOWS_MAIN_AND_TWO_OVERLAY_WRITERS_NO_FAKE_RECEIPT")

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

def read_stable_actions_snapshot(token, max_attempts=2):
    """Retry a whole Actions observation, never splice records from different HEADs.

    Each attempt reads one live main preimage, the workflow inventory and all
    execution witnesses, then an independent main postimage. A concurrent
    official-safety/reporting commit invalidates that observation, NOT the
    underlying historical run records. Persistent movement stays fail-closed.
    """
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("INVALID_ACTIONS_SNAPSHOT_ATTEMPTS")
    for attempt in range(max_attempts):
        head_a=github("/git/ref/heads/main",token)["object"]["sha"]
        if not (isinstance(head_a,str) and len(head_a)==40 and
                all(c in "0123456789abcdef" for c in head_a)):
            raise RuntimeError("GITHUB_MAIN_SHA_INVALID")
        inventory=fetch_workflow_inventory(token)
        entries={}
        now=dt.datetime.now(UTC)
        # Read the same exact 17+7 workflow scopes inside one bounded,
        # read-only fanout. A single malformed/failed response aborts this
        # entire attempt; no partial result can create a false green.
        targets=[("required",key,name) for key,name in WORKFLOWS.items()]
        targets += [("supplemental",key,name)
                    for key,name in SUPPLEMENTAL_SCHEDULED.items()]
        def fetch_one(row):
            scope,key,name=row
            runs=verify_response(github(
                "/actions/workflows/"+name+"/runs?per_page=20&branch=main",token))
            return scope,key,summarize(now,key,runs)
        with ThreadPoolExecutor(max_workers=6) as pool:
            observations=list(pool.map(fetch_one,targets))
        supplementary={}
        for scope,key,observed in observations:
            (entries if scope=="required" else supplementary)[key]=observed
        if len(entries)!=len(WORKFLOWS) or len(supplementary)!=len(SUPPLEMENTAL_SCHEDULED):
            raise RuntimeError("GITHUB_ACTIONS_SCOPE_INCOMPLETE")
        head_b=github("/git/ref/heads/main",token)["object"]["sha"]
        if head_a==head_b:
            return now,head_a,inventory,entries,supplementary,attempt+1
    raise RuntimeError("GITHUB_MAIN_CHANGED_DURING_ACTIONS_AUDIT_AFTER_BOUNDED_RETRIES")


def snapshot_retry_selftest():
    from unittest.mock import patch
    workflows=[{"path":".github/workflows/"+n,"id":i+1,"state":"active"}
               for i,n in enumerate(WORKFLOWS.values())]
    workflows += [{"path":".github/workflows/"+n,"id":100+i,"state":"active"}
                  for i,n in enumerate(SUPPLEMENTAL_SCHEDULED.values())]
    def run_case(heads):
        it=iter(heads)
        def fake(url,token):
            if url=="/git/ref/heads/main":
                return {"object":{"sha":next(it)}}
            if url=="/actions/workflows?per_page=100&page=1":
                return {"total_count":len(workflows),"workflows":workflows}
            if url.startswith("/actions/workflows/") and url.endswith(
                    "/runs?per_page=20&branch=main"):
                return {"workflow_runs":[]}
            raise AssertionError("UNEXPECTED_SNAPSHOT_ENDPOINT:"+url)
        with patch(__name__+".github",side_effect=fake):
            return read_stable_actions_snapshot("test",max_attempts=2)
    stable=run_case(["a"*40,"b"*40,"b"*40,"b"*40])
    assert stable[1]=="b"*40 and stable[-1]==2
    assert len(stable[3])==17 and len(stable[4])==7
    assert set(stable[3])==set(WORKFLOWS)
    assert set(stable[4])==set(SUPPLEMENTAL_SCHEDULED)
    try:
        run_case(["a"*40,"b"*40,"c"*40,"d"*40])
    except RuntimeError as e:
        assert str(e)=="GITHUB_MAIN_CHANGED_DURING_ACTIONS_AUDIT_AFTER_BOUNDED_RETRIES"
    else:
        raise AssertionError("MOVING_MAIN_ACCEPTED")
    try:
        read_stable_actions_snapshot("test",max_attempts=0)
    except ValueError:
        pass
    else:
        raise AssertionError("UNBOUNDED_OR_ZERO_RETRY_ACCEPTED")
    print("XRAY_MONDAY_ACTIONS_ATOMIC_SNAPSHOT_RETRY=PASS_POSITIVE_2_NEGATIVE_24_SCOPES_BOUNDED_FANOUT")


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
    now,head_a,inventory,entries,supplementary,attempts=read_stable_actions_snapshot(token)
    result={
        "schema":SCHEMA,"generated_at_utc":now.isoformat(),"main_sha":head_a,
        "main_stable_during_observation":True,
        "atomic_snapshot_attempts":attempts,
        "workflow_inventory":inventory,
        "execution_witnesses":entries,
        "supplemental_scheduled_witnesses":supplementary,
        # Do not call a prior green job current when a newer failure, queued
        # root or new main commit supersedes its execution witness.
        "root_fresh_weekday_job_only":bool(
            entries["root"]["last_success_age_seconds"] is not None
            and -60<=entries["root"]["last_success_age_seconds"]<=4500
            and entries["root"]["status"]=="completed"
            and entries["root"]["conclusion"]=="success"
            and entries["root"]["latest_root_compute_eligible"] is True
            and entries["root"]["run_id"]==entries["root"]["last_success_id"]
            and entries["root"]["head_sha"]==head_a
            and inventory["all_required_active"]
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
    print("XRAY_MONDAY_SUPPLEMENTAL_SCHEDULES=OBSERVED_"+str(len(supplementary)))
    print("XRAY_MONDAY_SUPPLEMENTAL_ACTIVE="+str(inventory["supplemental_active_count"]))
    print("XRAY_MONDAY_ROOT_WEEKDAY_GREEN_AGE_BOUND="+
          str(result["root_fresh_weekday_job_only"]).lower())
    print("XRAY_MONDAY_USER_DELIVERY_RECEIPT=UNVERIFIED")
    print("XRAY_MONDAY_LIVE_ACTIONS_NOT_RESEARCH_GO=TRUE")
    print("XRAY_MONDAY_WORKFLOW_INVENTORY="+
          ("ALL_REQUIRED_ACTIVE" if inventory["all_required_active"]
           else "DISABLED_OR_MISSING:"+",".join(inventory["blockers"])))
    if not inventory["all_required_active"]:
        raise SystemExit("XRAY_MONDAY_CRITICAL_WORKFLOW_DISABLED_OR_MISSING")

if __name__=="__main__":main()
