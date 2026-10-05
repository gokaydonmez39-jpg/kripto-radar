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
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)

def _successful_runs(runs):
    return [r for r in runs if r.get("status")=="completed" and r.get("conclusion")=="success"]

def _active_runs(runs):
    # GitHub may report queued, pending, waiting, requested or in_progress.
    return [r for r in runs if r.get("status")!="completed"]

def evaluate_readiness(now_utc,contract,root_kick,final_kick,root_runs,final_runs):
    if now_utc.tzinfo is None:
        now_utc=now_utc.replace(tzinfo=timezone.utc)
    now_utc=now_utc.astimezone(timezone.utc)
    if contract.get("schema")!="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1":
        return False,"CONTRACT_SCHEMA"
    if contract.get("execution")!="NONE" or contract.get("real_money")!="NO-GO":
        return False,"CONTRACT_SAFETY"
    if contract.get("unknown_never_pass") is not True:
        return False,"CONTRACT_UNKNOWN_POLICY"

    if _active_runs(root_runs):
        return False,"ROOT_RECOVERY_ACTIVE"
    if _active_runs(final_runs):
        return False,"FINAL_RECOVERY_ACTIVE"

    root_success=_successful_runs(root_runs)
    final_success=_successful_runs(final_runs)
    latest_root=max(root_success,key=lambda r:_dt(r.get("updated_at") or r.get("created_at"))) if root_success else None

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
        rt=_dt(latest_root.get("updated_at") or latest_root.get("created_at"))
        if rt is None:
            return False,"ROOT_SUCCESS_TIME_MISSING"
        age=(now_utc-rt).total_seconds()
        stale_after=int(contract.get("stale_after_seconds",4500))
        if age < -60 or age > stale_after:
            return False,"ROOT_SUCCESS_STALE"

    return True,"PASS"

def _fetch_runs(repo,workflow,token):
    url=f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=50"
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":f"Bearer {token}",
        "User-Agent":"NASDAQ-SWING-XRAY-delivery-guard",
        "X-GitHub-Api-Version":"2022-11-28",
    })
    with urllib.request.urlopen(req,timeout=20) as resp:
        data=json.load(resp)
    return data.get("workflow_runs") or []

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
