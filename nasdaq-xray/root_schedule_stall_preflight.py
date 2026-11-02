#!/usr/bin/env python3
"""Read-only productivity gate for existing hourly Nasdaq root schedule.

The native watchdog is not the sole producer: nasdaq-xray-daily.yml itself has
an hourly schedule. Apply the same four-hour source-aware circuit to BOTH
without changing either Cron. Manual workflow_dispatch and code push retain
their pre-existing authority. No alpha, market data, private data or writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

from github_native_root_watchdog import (
    REPO, get_runs, head_sha, root_productivity_gate, timestamp)
from root_weekend_quota_guard import permit_compute

UTC=dt.timezone.utc

def decision(*, event: str, now: dt.datetime, runs: list, live_main: str,
             local_head: str, token: str, productivity):
    if event not in ("schedule","push","workflow_dispatch"):
        return {"allow":False,"reason":"UNKNOWN_EVENT_FAIL_CLOSED"}
    if event!="schedule":
        return {"allow":True,"reason":"EXPLICIT_OR_CODE_PUSH_DISTINCT_FROM_SCHEDULE"}
    if not token or len(token)<4:
        return {"allow":False,"reason":"SCHEDULE_TOKEN_UNAVAILABLE"}
    if live_main!=local_head:
        return {"allow":False,"reason":"SCHEDULE_CHECKOUT_MAIN_SHA_MOVED"}
    if not isinstance(runs,list) or any(not isinstance(x,dict) for x in runs):
        return {"allow":False,"reason":"SCHEDULE_ROOT_RUNS_UNVERIFIED"}
    completed=[]
    for r in runs:
        if r.get("name")!="NASDAQ SWING XRAY Autonomous Data Plane" or r.get("head_branch") not in ("main",None):
            return {"allow":False,"reason":"WRONG_ROOT_IDENTITY"}
        if r.get("status")!="completed":
            continue
        try:
            run_time=timestamp(r["created_at"])
            if not permit_compute(run_time,"schedule"):
                continue # ignore green weekend/holiday control-only no-compute
        except Exception:
            return {"allow":False,"reason":"ROOT_COMPLETION_CALENDAR_UNAVAILABLE"}
        completed.append(r)
    if not completed:
        return {"allow":True,"reason":"NO_PRIOR_COMPUTE_ROOT"}
    latest=max(completed,key=lambda x:timestamp(x["created_at"]))
    if latest.get("conclusion")!="success":
        return {"allow":True,"reason":"LATEST_ROOT_FAILED_RECOVERY_ALLOWED"}
    first={"dispatch_allowed":True, "latest_root_id":latest.get("id"),
           "last_success_id":latest.get("id"),
           "decision":"SCHEDULE_SOURCE_PRODUCTIVITY_PROBE"}
    try:
        result=productivity(token,now,first,[latest],live_main)
    except Exception as exc:
        return {"allow":False,"reason":"SOURCE_PROBE_FAILED_"+type(exc).__name__}
    if not isinstance(result,dict) or type(result.get("suppress")) is not bool:
        return {"allow":False,"reason":"SOURCE_PROBE_MALFORMED"}
    return {"allow":not result["suppress"],
            "reason":result.get("reason","SOURCE_PROBE_NO_REASON")}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--emit",action="store_true")
    args=ap.parse_args()
    if not args.emit:
        ap.error("require --emit; offline selftests are in test_root_schedule_stall_preflight.py")
    event=os.environ.get("GITHUB_EVENT_NAME","")
    token=os.environ.get("GITHUB_TOKEN","")
    now=dt.datetime.now(UTC)
    # No GitHub call or token required for explicit/manual continuation.
    if event!="schedule":
        result=decision(event=event,now=now,runs=[],live_main="",
                        local_head="",token="",productivity=lambda *a:None)
    else:
        try:
            from github_native_root_watchdog import head_sha as live_head, get_runs as live_runs
            remote=live_head(token)
            local=subprocess.check_output(["git","rev-parse","HEAD"],
                                           text=True).strip()
            rows=live_runs(token)
            result=decision(event=event,now=now,runs=rows,
                            live_main=remote,local_head=local,token=token,
                            productivity=root_productivity_gate)
        except Exception as exc:
            result={"allow":False,"reason":"SCHEDULE_PREFLIGHT_UNVERIFIED_"+type(exc).__name__}
    if not isinstance(result,dict) or type(result.get("allow")) is not bool:
        raise RuntimeError("ROOT_PRODUCTIVITY_RESULT_INVALID")
    dest=os.environ.get("GITHUB_OUTPUT")
    if not dest:
        raise RuntimeError("GITHUB_OUTPUT_REQUIRED")
    with open(dest,"a",encoding="utf-8") as f:
        f.write("allow_compute="+("true" if result["allow"] else "false")+"\n")
        f.write("reason="+str(result.get("reason","UNDEFINED")).replace("\n","_")+"\n")
    print("XRAY_ROOT_SCHEDULE_PRODUCTIVITY="+
          ("ALLOW_" if result["allow"] else "HOLD_")+str(result.get("reason")))
    print("XRAY_ROOT_SCHEDULE_NO_ALPHA_NO_PROVIDER_UPGRADE_NO_BROKER")
    if not result["allow"]:
        summary=os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary,"a",encoding="utf-8") as f:
                f.write("### XRAY Nasdaq root productivity — safe HOLD\n"
                        "No market data, source promotion, AL or dispatch.\n"
                        "Reason: "+str(result.get("reason"))+"\n")


if __name__=="__main__":
    main()
