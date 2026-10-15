#!/usr/bin/env python3
"""GitHub-native root -> pre-MC dispatch independent of workflow_run chain depth.

Does not materialize MC, prices, candidates, or notify investors. Triggering
an audit is NOT evidence that the downstream pipeline produced a terminal.
Repo GITHUB_TOKEN is used only for action dispatch, with main/SHA double-read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

from github_native_root_watchdog import github, head_sha, timestamp, UTC

REPO="gokaydonmez39-jpg/kripto-radar"
WORKFLOWS={"pre-mc":"xray-canonical-current-pre-mc.yml",
           "post-mc":"xray-canonical-current-post-mc.yml"}
ACTIVE={"queued","in_progress","pending","waiting","requested"}
ROOT=Path(__file__).resolve().parent

def classify(now, root, master, price, terminal, runs, target="pre-mc"):
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK_FORBIDDEN")
    now=now.astimezone(UTC)
    if target not in WORKFLOWS:
        raise ValueError("UNAUTHORIZED_RELAY_TARGET")
    if not all(isinstance(x,dict) for x in (root,master,price,terminal)):
        raise ValueError("NON_OBJECT_SOURCE")
    asof=str(root.get("asof_et") or "")
    canonical_asof=str(master.get("asof_et") or "")
    if not canonical_asof or canonical_asof!=price.get("asof_et"):
        return "CANONICAL_MASTER_PRICE_EPOCH_MISMATCH",False
    try:
        root_date=dt.date.fromisoformat(asof)
        canonical_date=dt.date.fromisoformat(canonical_asof)
        if root_date.isoformat()!=asof or canonical_date.isoformat()!=canonical_asof:
            return "INVALID_SOURCE_EPOCH",False
    except (TypeError,ValueError):
        return "INVALID_SOURCE_EPOCH",False
    # An epoch from the future in exchange-local time cannot wake any stage.
    if root_date>now.astimezone(ZoneInfo("America/New_York")).date():
        return "ROOT_SOURCE_EPOCH_IN_FUTURE",False
    if canonical_date>root_date:
        return "ROOT_BEHIND_CANONICAL_EPOCH",False
    stale_canonical=canonical_date<root_date
    # The root->Pre-MC relay repairs canonical source drift. Demanding that
    # MASTER/PRICE already match the new root is a dependency cycle. Post-MC
    # must still require exact current source epochs; this NEVER promotes a
    # stale PRICE or HISTORY result or authorizes terminal/AL.
    if stale_canonical and target!="pre-mc":
        return "STALE_CANONICAL_EPOCH_POST_MC_FORBIDDEN",False
    if root.get("execution")!="NONE" or root.get("real_money")!="NO-GO":
        return "ROOT_POLICY_SAFETY_INVALID",False
    if master.get("unknown_never_pass") is not True or price.get("unknown_never_pass") is not True:
        return "SOURCE_UNKNOWN_POLICY_MISMATCH",False
    # Do not trigger blindly on a partially built price/master partition.
    p=price.get("pass_symbols") or []
    if (not isinstance(p,list) or len(p)!=int(price.get("pass_count",-1))
        or len(p)!=len(set(p))
        or not set(p).issubset(set(master.get("pass_symbols") or []))):
        return "CANONICAL_PASS_PARTITION_UNTRUSTED",False
    if target=="post-mc":
        # The full-scope Post-MC handoff explicitly requires zero PRICE
        # UNKNOWN. Dispatching while any remain creates a known-failing
        # workflow rather than resolving data. Pre-MC remains available to
        # rebuild its source; confirmed FAIL-only residuals may still enter
        # Post-MC after all UNKNOWN are resolved.
        unknown=price.get("unknown_symbols")
        blocked=price.get("blocked_symbols")
        if (not isinstance(unknown,list) or not isinstance(blocked,list)
            or type(price.get("unknown_count")) is not int
            or type(price.get("blocked_count")) is not int
            or price["unknown_count"]!=len(unknown)
            or price["blocked_count"]!=len(blocked)
            or any(type(s) is not str or not s for s in unknown+blocked)
            or len(unknown)!=len(set(unknown))
            or len(blocked)!=len(set(blocked))
            or unknown!=sorted(unknown) or blocked!=sorted(blocked)
            or bool(set(unknown)&(set(blocked)|set(p)))
            or bool(set(blocked)&set(p))):
            return "POST_MC_PRICE_PARTITION_UNTRUSTED",False
        if unknown:
            return "POST_MC_PRICE_UNKNOWN_NO_DISPATCH",False
    if terminal.get("asof_et")==asof and terminal.get("full_end_to_end_research_pass") is True:
        # Current terminal is already final; do not churn the factory.
        return "CURRENT_FULL_TERMINAL_ALREADY_PRESENT",False
    if not isinstance(runs,list):
        raise ValueError("RUNS_NOT_LIST")
    for run in runs:
        if run.get("status") not in ACTIVE:
            continue
        age=(now-timestamp(run.get("created_at"))).total_seconds()
        if -60<=age<=3600:
            return "PRE_MC_ACTIVE_SUPPRESS",False
    return ("STALE_CANONICAL_EPOCH_PRE_MC_REFRESH_ELIGIBLE" if stale_canonical
            else "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE"),True

def fingerprint(runs):
    return sorted((r.get("id"),r.get("status"),r.get("conclusion"),
                   r.get("head_sha"),r.get("run_attempt"),r.get("created_at"))
                  for r in runs)

def read_runs(token,workflow):
    if workflow not in WORKFLOWS.values():
        raise ValueError("UNAUTHORIZED_STAGE_WORKFLOW")
    raw=github("GET","/actions/workflows/"+workflow+"/runs?per_page=35&branch=main",token)
    runs=raw.get("workflow_runs")
    if not isinstance(runs,list):
        raise RuntimeError("PRE_MC_GITHUB_RUNS_UNAVAILABLE")
    return runs

def load_sources():
    return tuple(json.loads((ROOT/name).read_text(encoding="utf-8")) for name in (
        "orchestrator_state.json",
        "canonical_current_master_manifest.json",
        "canonical_current_price_dv30.json",
        "canonical_current_terminal.json"
    ))

def exact_checked_out_main(local_sha,first_remote_sha,second_remote_sha):
    """Do not dispatch a newer main using stale committed source snapshots."""
    return (all(isinstance(v,str) and len(v)==40 for v in
                (local_sha,first_remote_sha,second_remote_sha))
            and local_sha==first_remote_sha==second_remote_sha)

def selftest():
    now=dt.datetime(2026,10,9,9,tzinfo=UTC)
    r={"asof_et":"2026-10-08","status":"PARTIAL_HISTORY",
       "execution":"NONE","real_money":"NO-GO"}
    m={"asof_et":"2026-10-08","unknown_never_pass":True,
       "pass_symbols":["A","B"]}
    p={"asof_et":"2026-10-08","unknown_never_pass":True,
       "pass_symbols":["A"],"pass_count":1}
    t={"asof_et":"2026-10-07","full_end_to_end_research_pass":False}
    assert classify(now,r,m,p,t,[])==(
        "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE",True)
    # Actual Oct 15: 548 canonical PRICE UNKNOWN and zero certified PRICE
    # survivors. Post-MC's full-scope resolver cannot run, so wake only
    # Pre-MC; never dispatch a predictably failing downstream release job.
    waiting_price=dict(p,unknown_symbols=["B"],unknown_count=1,
                       blocked_symbols=[],blocked_count=0)
    assert classify(now,r,m,waiting_price,t,[],target="post-mc")==(
        "POST_MC_PRICE_UNKNOWN_NO_DISPATCH",False)
    assert classify(now,r,m,waiting_price,t,[],target="pre-mc")==(
        "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE",True)
    # A complete PRICE pass and an exact FAIL-only residual remain eligible.
    fully_resolved=dict(p,unknown_symbols=[],unknown_count=0,
                        blocked_symbols=[],blocked_count=0)
    assert classify(now,r,m,fully_resolved,t,[],target="post-mc")==(
        "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE",True)
    fail_residual=dict(fully_resolved,blocked_symbols=["B"],blocked_count=1)
    assert classify(now,r,m,fail_residual,t,[],target="post-mc")==(
        "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE",True)
    duplicated=dict(waiting_price,unknown_symbols=["B","B"],unknown_count=2)
    assert classify(now,r,m,duplicated,t,[],target="post-mc")==(
        "POST_MC_PRICE_PARTITION_UNTRUSTED",False)
    overlapping=dict(waiting_price,unknown_symbols=["A"],unknown_count=1)
    assert classify(now,r,m,overlapping,t,[],target="post-mc")==(
        "POST_MC_PRICE_PARTITION_UNTRUSTED",False)
    malformed_price=dict(waiting_price,unknown_count=0)
    assert classify(now,r,m,malformed_price,t,[],target="post-mc")==(
        "POST_MC_PRICE_PARTITION_UNTRUSTED",False)

    # Regression from 15 Oct 2026 live root: root moved to Oct 15 while
    # canonical MASTER and PRICE remained on Oct 14. Pre-MC must be allowed
    # to REBUILD them; this must never count as downstream source proof.
    rollover_now=dt.datetime(2026,10,16,0,30,tzinfo=UTC)
    rollover_root=dict(r,asof_et="2026-10-15")
    old_master=dict(m,asof_et="2026-10-14")
    old_price=dict(p,asof_et="2026-10-14")
    assert classify(rollover_now,rollover_root,old_master,old_price,t,[])==(
        "STALE_CANONICAL_EPOCH_PRE_MC_REFRESH_ELIGIBLE",True), (
        "ROOT_NEWER_THAN_CANONICAL_MUST_WAKE_PRE_MC_NOT_FREEZE")

    assert classify(rollover_now,rollover_root,old_master,old_price,t,[],
                    target="post-mc")==(
        "STALE_CANONICAL_EPOCH_POST_MC_FORBIDDEN",False)
    mismatch_price=dict(old_price,asof_et="2026-10-13")
    assert classify(rollover_now,rollover_root,old_master,mismatch_price,t,[])[1] is False
    forward_master=dict(old_master,asof_et="2026-10-16")
    forward_price=dict(old_price,asof_et="2026-10-16")
    assert classify(rollover_now,rollover_root,forward_master,forward_price,t,[])==(
        "ROOT_BEHIND_CANONICAL_EPOCH",False)
    invented_root=dict(rollover_root,asof_et="2026-10-16")
    assert classify(rollover_now,invented_root,old_master,old_price,t,[])==(
        "ROOT_SOURCE_EPOCH_IN_FUTURE",False)
    broken_root=dict(rollover_root,asof_et="invalid")
    assert classify(rollover_now,broken_root,old_master,old_price,t,[])==(
        "INVALID_SOURCE_EPOCH",False)
    try:classify(rollover_now,rollover_root,old_master,old_price,t,[],target="unknown")
    except ValueError as exc:assert "UNAUTHORIZED_RELAY_TARGET" in str(exc)
    else:raise AssertionError("UNAUTHORIZED_STAGE_TARGET_ACCEPTED")
    assert classify(rollover_now,rollover_root,old_master,old_price,t,
                    [{"status":"in_progress","created_at":"2026-10-16T00:20:00Z"}])==(
        "PRE_MC_ACTIVE_SUPPRESS",False)
    def one(run_status,created):
        return [{"status":run_status,"created_at":created,"id":1}]
    assert classify(now,r,m,p,t,one("in_progress","2026-10-09T08:45:00Z"))==(
        "PRE_MC_ACTIVE_SUPPRESS",False)
    assert classify(now,r,m,p,t,one("queued","2026-10-09T07:00:00Z"))[1] is True
    from copy import deepcopy
    t2=dict(t,asof_et="2026-10-08",full_end_to_end_research_pass=True)
    assert classify(now,r,m,p,t2,[])[1] is False
    for obj,name in ((r,"asof_et"),(r,"execution"),(m,"unknown_never_pass"),
                     (p,"asof_et"),(p,"pass_count")):
        rs,ms,ps=deepcopy(r),deepcopy(m),deepcopy(p)
        which=rs if obj is r else ms if obj is m else ps
        which[name]="TAMPER" if name!="pass_count" else 22
        assert classify(now,rs,ms,ps,t,[])[1] is False
    assert set(WORKFLOWS)=={"pre-mc","post-mc"}
    assert len(set(WORKFLOWS.values()))==2
    sha="a"*40
    assert exact_checked_out_main(sha,sha,sha)
    for trio in ((sha,"b"*40,sha),(sha,sha,"b"*40),
                 ("b"*40,sha,sha),("",sha,sha),
                 (sha,sha,None),("not-a-sha",sha,sha)):
        assert not exact_checked_out_main(*trio)
    print("XRAY_STAGE_RELAY_SELFTEST=PASS_ROLLOVER_PREMC_POSITIVE_POSTMC_NEGATIVE_SHA_BOUND_NO_PRIMARY_OR_TRADE")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--target",choices=sorted(WORKFLOWS),default="pre-mc")
    parser.add_argument("--out",type=Path,default=Path("/tmp/xray_stage_relay.json"))
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    if os.environ.get("GITHUB_REPOSITORY")!=REPO or os.environ.get("GITHUB_REF")!="refs/heads/main":
        raise RuntimeError("REPO_BRANCH_MISMATCH")
    token=os.environ.get("GITHUB_TOKEN","")
    if not token:
        raise RuntimeError("GITHUB_ACTIONS_DISPATCH_TOKEN_MISSING")
    target=WORKFLOWS[args.target]
    a=head_sha(token)
    local_sha=subprocess.check_output(
        ["git","rev-parse","HEAD"],text=True).strip()
    sources=load_sources()
    first_runs=read_runs(token,target)
    reason,eligible=classify(dt.datetime.now(UTC),*sources,first_runs,target=args.target)
    out={"schema":"XRAY_NATIVE_ROOT_TO_PRE_MC_RELAY_V1",
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "alpha_authority":False,"mc_primary_promoted":False,
         "terminal_updated":False,"device_receipt_proven":False,
         "root_asof_et":sources[0].get("asof_et"),
         "current_terminal_asof":sources[3].get("asof_et"),
         "reason":reason,"target_workflow":target,
         "action":"NONE","dispatch_accepted":False,
         "main_sha":a,"local_checkout_sha":local_sha}
    if eligible:
        b=head_sha(token)
        next_runs=read_runs(token,target)
        again_reason,still_ok=classify(dt.datetime.now(UTC),*sources,next_runs,target=args.target)
        # Both remote snapshots and the actual runner checkout must agree.
        # This is critical when another writer updated main since checkout.
        checkout_exact=exact_checked_out_main(local_sha,a,b)
        out["checkout_main_sha_exact"]=checkout_exact
        if (not checkout_exact or
            fingerprint(first_runs)!=fingerprint(next_runs) or not still_ok):
            out["action"]="SKIP_CONCURRENT_MAIN_OR_PRE_MC_CHANGE"
            out["second_reason"]=again_reason
        else:
            result=github("POST","/actions/workflows/"+target+"/dispatches",
                          token,{"ref":"main"})
            if result.get("http_status")!=204:
                raise RuntimeError("PRE_MC_DISPATCH_NO_204")
            out["action"]=args.target.upper().replace("-","_")+"_DISPATCH_ACCEPTED_NOT_PROVEN"
            out["dispatch_accepted"]=True
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("XRAY_STAGE_RELAY="+out["action"]+
          " reason="+reason+
          " current_terminal="+str(out["current_terminal_asof"]))
if __name__=="__main__":
    main()
