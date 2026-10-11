#!/usr/bin/env python3
"""Fail-closed scheduler readiness guard for research-candidate delivery.

This module is zero-alpha. It never creates candidates and never changes policy.
It only suppresses delivery while the production root/final chain is recovering,
while a recovery kick lacks a successful witness, or while weekday root evidence
is stale under the scheduler failover contract.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"scheduler_failover_contract.json"
ROOT_KICK=ROOT/"scheduler_kick_dataplane.json"
FINAL_KICK=ROOT/"scheduler_kick_final.json"
ROOT_WORKFLOW="nasdaq-xray-daily.yml"
FINAL_WORKFLOW="xray-canonical-current-final.yml"

def _dt(value):
    if not value:
        return None
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("DELIVERY_NAIVE_TIMESTAMP_FORBIDDEN")
    return t.astimezone(timezone.utc)

def _successful_runs(runs):
    return [r for r in runs if r.get("status")=="completed" and r.get("conclusion")=="success"]


def _weekday_root_successes(runs):
    # A green Sunday root is a weekend quota-protection NO-COMPUTE job.
    ny=ZoneInfo("America/New_York")
    return [r for r in _successful_runs(runs)
            if _dt(r.get("created_at")).astimezone(ny).weekday()<5]


def _latest_completed(runs):
    finished=[r for r in runs if r.get("status")=="completed"]
    return max(finished,key=lambda r:_dt(r.get("created_at"))) if finished else None


def _later_red_than_green(runs,successes):
    latest=_latest_completed(runs)
    if latest is None or latest.get("conclusion")=="success":
        return False
    newest_green=max(successes,key=lambda r:_dt(r.get("created_at"))) if successes else None
    return newest_green is None or _dt(latest["created_at"])>_dt(newest_green["created_at"])

ACTIVE={"queued","in_progress","pending","waiting","requested"}
COMPLETED="completed"


def classify_active(now_utc, runs, grace_seconds, recovery_successes=None):
    """Suppress genuinely active runs; expire zombies only with newer SUCCESS.

    An old queued job is not evidence of ongoing recovery forever. However,
    expiry alone cannot authorize signal delivery: require a completed SUCCESS
    created after that orphan, or fail with a distinct unrecovered fault.
    Unknown statuses, impossible clocks and malformed dates remain fail-closed.
    """
    if type(grace_seconds) is not int or grace_seconds <= 0:
        return "ACTIVE_GRACE_INVALID"
    successes=(_successful_runs(runs) if recovery_successes is None
               else recovery_successes)
    for run in runs:
        status=run.get("status")
        if status==COMPLETED:
            continue
        if status not in ACTIVE:
            return "UNKNOWN_ACTIONS_RUN_STATUS"
        try:
            started=_dt(run.get("created_at"))
            if started is None:
                return "ACTION_RUN_TIME_MISSING"
            age=(now_utc-started).total_seconds()
        except (ValueError,TypeError,OverflowError):
            return "ACTION_RUN_TIME_INVALID"
        if age < -60:
            return "ACTION_RUN_FROM_FUTURE"
        if age <= grace_seconds:
            return "ACTIVE"
        # A later completion must have been started after the orphan.
        # A different, older run succeeding cannot cover a newer zombie.
        recovered=False
        for success in successes:
            try:
                succ_started=_dt(success.get("created_at"))
            except (ValueError,TypeError,OverflowError):
                return "SUCCESS_RUN_TIME_INVALID"
            if succ_started is not None and succ_started > started:
                recovered=True
                break
        if not recovered:
            return "ORPHAN_UNRECOVERED"
    return "CLEAR"

def evaluate_readiness(now_utc,contract,root_kick,final_kick,root_runs,final_runs):
    # Exclude foreign branch CI from canonical root/final recovery authority.
    if (not isinstance(root_runs,list) or not isinstance(final_runs,list)
        or any(not isinstance(r,dict) or r.get("head_branch")!="main"
               for r in root_runs+final_runs)):
        return False,"ACTIONS_MAIN_BRANCH_RUN_IDENTITY_UNVERIFIED"
    if now_utc.tzinfo is None:
        now_utc=now_utc.replace(tzinfo=timezone.utc)
    now_utc=now_utc.astimezone(timezone.utc)
    if contract.get("schema")!="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1":
        return False,"CONTRACT_SCHEMA"
    if contract.get("execution")!="NONE" or contract.get("real_money")!="NO-GO":
        return False,"CONTRACT_SAFETY"
    if contract.get("unknown_never_pass") is not True:
        return False,"CONTRACT_UNKNOWN_POLICY"

    root_grace=contract.get("root_active_run_grace_seconds",3300)
    final_grace=contract.get("final_active_run_grace_seconds",3600)
    # Quota-protected weekend root successes are not recovered data work.
    root_success=_weekday_root_successes(root_runs)
    root_active=classify_active(now_utc,root_runs,root_grace,
                                recovery_successes=root_success)
    if root_active!="CLEAR":
        return False,("ROOT_RECOVERY_ACTIVE" if root_active=="ACTIVE"
                      else "ROOT_"+root_active)
    final_active=classify_active(now_utc,final_runs,final_grace)
    if final_active!="CLEAR":
        return False,("FINAL_RECOVERY_ACTIVE" if final_active=="ACTIVE"
                      else "FINAL_"+final_active)

    final_success=_successful_runs(final_runs)
    # A newer red completion outranks an earlier green run: do not release a
    # candidate from a broken current root/final chain.
    if _later_red_than_green(root_runs,root_success):
        return False,"ROOT_LATEST_RUN_FAILED_OR_CANCELLED"
    if _later_red_than_green(final_runs,final_success):
        return False,"FINAL_LATEST_RUN_FAILED_OR_CANCELLED"
    latest_root=max(root_success,key=lambda r:_dt(r.get("created_at"))) if root_success else None

    for label,kick,runs in (("ROOT",root_kick,root_success),("FINAL",final_kick,final_success)):
        kt=_dt(kick.get("requested_at_utc"))
        if kt is None:
            return False,label+"_KICK_TIME_MISSING"
        witnessed=any((_dt(r.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))>=kt for r in runs)
        if not witnessed:
            return False,label+"_KICK_SUCCESS_NOT_OBSERVED"

    ny=now_utc.astimezone(ZoneInfo("America/New_York"))
    if ny.weekday()<5:
        if latest_root is None:
            return False,"ROOT_SUCCESS_MISSING"
        # updated_at can move after a retry/UI update while source compute is
        # still from an earlier invocation; freshness binds created_at.
        rt=_dt(latest_root.get("created_at"))
        if rt is None:
            return False,"ROOT_SUCCESS_TIME_MISSING"
        age=(now_utc-rt).total_seconds()
        stale_after=int(contract.get("stale_after_seconds",4500))
        if age < -60 or age > stale_after:
            return False,"ROOT_SUCCESS_STALE"

    return True,"PASS"

def _fetch_runs(repo,workflow,token):
    url=f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=50&branch=main"
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":f"Bearer {token}",
        "User-Agent":"NASDAQ-SWING-XRAY-delivery-guard",
        "X-GitHub-Api-Version":"2022-11-28",
    })
    with urllib.request.urlopen(req,timeout=20) as resp:
        data=json.load(resp)
    rows=data.get("workflow_runs")
    if not isinstance(rows,list):
        raise RuntimeError("ACTIONS_WORKFLOW_RUNS_NOT_LIST")
    return rows

def main():
    try:
        contract=json.loads(CONTRACT.read_text())
        root_kick=json.loads(ROOT_KICK.read_text())
        final_kick=json.loads(FINAL_KICK.read_text())
        repo=str(os.getenv("GITHUB_REPOSITORY") or "").strip()
        token=str(os.getenv("GITHUB_TOKEN") or "").strip()
        if not repo or not token:
            raise RuntimeError("GITHUB_ACTIONS_AUTH_MISSING")
        root_runs=_fetch_runs(repo,ROOT_WORKFLOW,token)
        final_runs=_fetch_runs(repo,FINAL_WORKFLOW,token)
        ok,reason=evaluate_readiness(datetime.now(timezone.utc),contract,root_kick,final_kick,root_runs,final_runs)
    except Exception as exc:
        ok=False
        reason="GUARD_ERROR_"+type(exc).__name__
    print("XRAY_DELIVERY_SCHEDULER_READY="+("PASS" if ok else "BLOCKED"))
    print("XRAY_DELIVERY_SCHEDULER_REASON="+reason)

if __name__=="__main__":
    main()
