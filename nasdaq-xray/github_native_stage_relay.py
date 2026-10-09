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
from pathlib import Path

from github_native_root_watchdog import github, head_sha, timestamp, UTC

REPO="gokaydonmez39-jpg/kripto-radar"
WORKFLOW="xray-canonical-current-pre-mc.yml"
ACTIVE={"queued","in_progress","pending","waiting","requested"}
ROOT=Path(__file__).resolve().parent

def classify(now, root, master, price, terminal, runs):
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK_FORBIDDEN")
    now=now.astimezone(UTC)
    if not all(isinstance(x,dict) for x in (root,master,price,terminal)):
        raise ValueError("NON_OBJECT_SOURCE")
    asof=str(root.get("asof_et") or "")
    if not asof or not (asof==master.get("asof_et")==price.get("asof_et")):
        return "SOURCE_ASOF_MISMATCH",False
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
    return "EXACT_SOURCE_EPOCH_PRE_MC_RELAY_ELIGIBLE",True

def fingerprint(runs):
    return sorted((r.get("id"),r.get("status"),r.get("conclusion"),
                   r.get("head_sha"),r.get("run_attempt"),r.get("created_at"))
                  for r in runs)

def read_runs(token):
    raw=github("GET","/actions/workflows/"+WORKFLOW+"/runs?per_page=35&branch=main",token)
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
    print("XRAY_STAGE_RELAY_SELFTEST=PASS_EXACT_EPOCH_7_NEGATIVE_NO_PRIMARY_OR_TRADE")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
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
    a=head_sha(token)
    sources=load_sources()
    first_runs=read_runs(token)
    reason,eligible=classify(dt.datetime.now(UTC),*sources,first_runs)
    out={"schema":"XRAY_NATIVE_ROOT_TO_PRE_MC_RELAY_V1",
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "alpha_authority":False,"mc_primary_promoted":False,
         "terminal_updated":False,"device_receipt_proven":False,
         "root_asof_et":sources[0].get("asof_et"),
         "current_terminal_asof":sources[3].get("asof_et"),
         "reason":reason,"action":"NONE","dispatch_accepted":False,
         "main_sha":a}
    if eligible:
        b=head_sha(token)
        next_runs=read_runs(token)
        again_reason,still_ok=classify(dt.datetime.now(UTC),*sources,next_runs)
        if a!=b or fingerprint(first_runs)!=fingerprint(next_runs) or not still_ok:
            out["action"]="SKIP_CONCURRENT_MAIN_OR_PRE_MC_CHANGE"
            out["second_reason"]=again_reason
        else:
            result=github("POST","/actions/workflows/"+WORKFLOW+"/dispatches",
                          token,{"ref":"main"})
            if result.get("http_status")!=204:
                raise RuntimeError("PRE_MC_DISPATCH_NO_204")
            out["action"]="PRE_MC_DISPATCH_ACCEPTED_NOT_PROVEN"
            out["dispatch_accepted"]=True
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("XRAY_STAGE_RELAY="+out["action"]+
          " reason="+reason+
          " current_terminal="+str(out["current_terminal_asof"]))
if __name__=="__main__":
    main()
