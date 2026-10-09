#!/usr/bin/env python3
"""Fail-closed GitHub-native watchdog; only safe action: dispatch existing root.
No alpha, account, entitlement, MC, terminal or immutable witness writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.request
from zoneinfo import ZoneInfo

REPO = "gokaydonmez39-jpg/kripto-radar"
WORKFLOW = "nasdaq-xray-daily.yml"
NAME = "NASDAQ SWING XRAY Autonomous Data Plane"
API = "https://api.github.com/repos/" + REPO
ACTIVE = {"queued", "in_progress", "pending", "waiting", "requested"}
UTC = dt.timezone.utc

def timestamp(value):
    value = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("XRAY_UNZONED_RUN_TIMESTAMP")
    return value.astimezone(UTC)

def classify(now, runs):
    now = now.astimezone(UTC)
    if now.astimezone(ZoneInfo("America/New_York")).weekday() >= 5:
        return {"decision":"WEEKEND_OBSERVE_ONLY","dispatch_allowed":False}
    if not isinstance(runs, list) or any(not isinstance(r,dict) for r in runs):
        raise ValueError("XRAY_ROOT_RUNS_INVALID")
    for r in runs:
        if r.get("name") != NAME or r.get("head_branch") not in ("main",None):
            raise ValueError("XRAY_WRONG_ROOT_WORKFLOW_IDENTITY")
        timestamp(r.get("created_at"))
    runs = sorted(runs,key=lambda r:timestamp(r["created_at"]),reverse=True)
    latest = runs[0] if runs else None
    success = next((r for r in runs if r.get("status")=="completed" and
                    r.get("conclusion")=="success"),None)
    # The scheduler contract bounds active-run suppression to 3300s.
    # An orphaned/pending Actions run must not suppress restart forever.
    active = [r for r in runs if r.get("status") in ACTIVE
              and -60 <= (now-timestamp(r["created_at"])).total_seconds() <= 3300]
    expired_active = [r for r in runs if r.get("status") in ACTIVE
                      and (now-timestamp(r["created_at"])).total_seconds() > 3300]
    success_age = (now-timestamp(success["created_at"])).total_seconds() if success else None
    last_age = (now-timestamp(latest["created_at"])).total_seconds() if latest else None
    if success_age is not None and -60 <= success_age <= 4500:
        decision = "FRESH_ROOT_SUCCESS"
    elif active:
        decision = "ACTIVE_ROOT_SUPPRESS"
    elif last_age is not None and last_age < 1800:
        decision = "RECENT_ROOT_COOLDOWN"
    else:
        decision = "STALE_ROOT_ELIGIBLE"
    return {
        "decision":decision,"dispatch_allowed":decision=="STALE_ROOT_ELIGIBLE",
        "latest_root_id":latest.get("id") if latest else None,
        "last_success_id":success.get("id") if success else None,
        "last_success_age_seconds":round(success_age) if success_age is not None else None,
        "active_root_ids":[x.get("id") for x in active],
        "expired_active_root_ids":[x.get("id") for x in expired_active],
    }

def signature(runs):
    return sorted((x.get("id"),x.get("status"),x.get("conclusion"),
                   x.get("created_at"),x.get("head_sha"),x.get("run_attempt"))
                  for x in runs)

def two_read_authorized(a,b,head_a,head_b,now):
    if not head_a or head_a != head_b:
        return False,"LIVE_MAIN_CHANGED"
    if signature(a)!=signature(b):
        return False,"ROOT_RUN_CHANGED"
    if not classify(now,b)["dispatch_allowed"]:
        return False,"ROOT_NO_LONGER_ELIGIBLE"
    return True,"TWO_LIVE_READS_AGREE"

def github(method, path, token, payload=None):
    if not token or not path.startswith("/"):
        raise RuntimeError("GITHUB_TOKEN_OR_PATH_UNAVAILABLE")
    body=json.dumps(payload).encode() if payload is not None else None
    request=urllib.request.Request(API+path,data=body,method=method,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "Content-Type":"application/json",
        "User-Agent":"XRAY-Native-Root-Watchdog",
    })
    with urllib.request.urlopen(request,timeout=15) as response:
        if method=="POST":
            if response.status!=204:
                raise RuntimeError("GITHUB_DISPATCH_NOT_204")
            return {"http_status":204}
        if response.status!=200:
            raise RuntimeError("GITHUB_READ_NOT_200")
        return json.loads(response.read(2000000))

def get_runs(token):
    data=github("GET","/actions/workflows/"+WORKFLOW+
                "/runs?per_page=60&branch=main",token)
    runs=data.get("workflow_runs")
    if not isinstance(runs,list):
        raise RuntimeError("GITHUB_WORKFLOW_RUNS_MISSING")
    return runs

def head_sha(token):
    return str(github("GET","/branches/main",token).get("commit",{}).get("sha") or "")

def selftest():
    now=dt.datetime(2026,10,8,11,tzinfo=UTC)
    def r(num,date,status,conclusion=None):
        return {"id":num,"name":NAME,"head_branch":"main",
                "created_at":date,"status":status,"conclusion":conclusion,
                "head_sha":"a"*40,"run_attempt":1}
    fresh=[r(1,"2026-10-08T10:30:00Z","completed","success")]
    stale=[r(2,"2026-10-08T08:30:00Z","completed","success")]
    active=[r(3,"2026-10-08T10:45:00Z","in_progress")]+stale
    cooldown=[r(4,"2026-10-08T10:40:00Z","completed","failure")]+stale
    assert classify(now,fresh)["decision"]=="FRESH_ROOT_SUCCESS"
    assert classify(now,stale)["dispatch_allowed"] is True
    assert classify(now,active)["decision"]=="ACTIVE_ROOT_SUPPRESS"
    # A stale orphaned queued/in_progress run is not an infinite kill-switch.
    zombie=[r(8,"2026-10-08T08:00:00Z","in_progress")]+stale
    assert classify(now,zombie)["decision"]=="STALE_ROOT_ELIGIBLE"
    assert classify(now,zombie)["expired_active_root_ids"]==[8]
    assert classify(now,cooldown)["decision"]=="RECENT_ROOT_COOLDOWN"
    assert classify(dt.datetime(2026,10,10,11,tzinfo=UTC),stale)["decision"]=="WEEKEND_OBSERVE_ONLY"
    assert two_read_authorized(stale,stale,"a"*40,"a"*40,now)[0] is True
    assert two_read_authorized(stale,fresh,"a"*40,"a"*40,now)[0] is False
    assert two_read_authorized(stale,stale,"a"*40,"b"*40,now)[0] is False
    assert classify(now,[])["dispatch_allowed"] is True
    try:
        classify(now,[r(5,"BAD_DATE","completed")])
        raise AssertionError("MALFORMED_DATE_ACCEPTED")
    except ValueError:
        pass
    print("XRAY_GITHUB_NATIVE_ROOT_WATCHDOG_SELFTEST=PASS ZERO_ALPHA")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",default="/tmp/xray_native_watchdog.json")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if (os.environ.get("GITHUB_REPOSITORY")!=REPO or
        os.environ.get("GITHUB_REF")!="refs/heads/main"):
        raise RuntimeError("REPO_BRANCH_AUTHORITY_MISMATCH")
    token=os.environ.get("GITHUB_TOKEN","")
    now=dt.datetime.now(UTC)
    before=get_runs(token)
    before_head=head_sha(token)
    first=classify(now,before)
    output={
        "schema":"XRAY_GITHUB_NATIVE_ROOT_FAILOVER_V1",
        "generated_at_utc":now.isoformat(),
        "execution":"NONE","real_money":"NO-GO","policy":"C4.17",
        "unknown_never_pass":True,"alpha_authority":False,
        "mc_primary_promoted":False,"g9_promoted":False,"account_promoted":False,
        "r92_created":False,"terminal_pass_claimed":False,"recovery_proven":False,
        "first_snapshot":first,"action":"NONE","second_snapshot":None,
    }
    try:
        if first["dispatch_allowed"]:
            after=get_runs(token)
            after_head=head_sha(token)
            accepted,reason=two_read_authorized(
                before,after,before_head,after_head,dt.datetime.now(UTC))
            output["second_snapshot"]=reason
            if accepted:
                response=github("POST","/actions/workflows/"+WORKFLOW+
                                "/dispatches",token,{"ref":"main"})
                output["action"]="ROOT_DISPATCH_ACCEPTED_NOT_RECOVERY"
                output["dispatch_http_status"]=response["http_status"]
            else:
                output["action"]="NO_ACTION_LIVE_SNAPSHOT_CHANGED"
    finally:
        target=pathlib.Path(args.out)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("XRAY_NATIVE_ROOT_WATCHDOG="+output["action"]+
          " decision="+first["decision"]+" recovery_proven=false")

if __name__=="__main__":
    main()
