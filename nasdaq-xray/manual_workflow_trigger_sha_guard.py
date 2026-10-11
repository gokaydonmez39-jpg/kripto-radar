#!/usr/bin/env python3
"""Verify that a manual research workflow cannot replay an unrelated Final run.

GitHub workflow_run sets GITHUB_SHA to default branch HEAD, not the source
Final workflow's head_sha. Only exact same-repo/same-commit Final triggers
may enter downstream manual research. Scheduled/manual triggers are clearly
classified as fresh research-only, not as Final-authoritative receipts.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SCHEMA="XRAY_MANUAL_WORKFLOW_TRIGGER_SHA_GUARD_V1"
SHA=re.compile(r"^[0-9a-f]{40}$")
MAIN="refs/heads/main"

def verify(event_name:str,payload:dict,repository:str,checked_out_sha:str)->dict:
    if (event_name not in {"workflow_run","push","schedule","workflow_dispatch"}
            or not isinstance(repository,str) or "/" not in repository
            or not isinstance(checked_out_sha,str) or not SHA.fullmatch(checked_out_sha)
            or not isinstance(payload,dict)
            or (payload.get("repository") or {}).get("full_name")!=repository):
        raise ValueError("MANUAL_EVENT_REPOSITORY_OR_SHA_INVALID")
    result={"schema":SCHEMA,"event_name":event_name,
            "checkout_sha":checked_out_sha,
            "execution":"NONE","real_money":"NO-GO",
            "source_authority":False,"can_register_R92":False,
            "notification_delivered":False,"unknown_never_pass":True}
    if event_name=="workflow_run":
        x=payload.get("workflow_run")
        if (not isinstance(x,dict)
            or payload.get("action")!="completed"
            or x.get("status")!="completed" or x.get("conclusion")!="success"
            or x.get("name")!="XRAY Canonical Current Final Factory"
            or x.get("head_branch")!="main"
            or (x.get("head_repository") or {}).get("full_name")!=repository
            or type(x.get("id")) is not int or x["id"]<=0
            or not isinstance(x.get("head_sha"),str)
            or not SHA.fullmatch(x["head_sha"])):
            raise ValueError("MANUAL_UPSTREAM_FINAL_PROVENANCE_INVALID")
        if x["head_sha"]!=checked_out_sha:
            raise ValueError("MANUAL_UPSTREAM_FINAL_HEAD_MISMATCH_FAIL_CLOSED")
        result["status"]="SAME_COMMIT_FINAL_TRIGGER_RESEARCH_ONLY"
        result["upstream_final_run_id"]=x["id"]
    elif event_name=="push":
        if payload.get("ref")!=MAIN or payload.get("after")!=checked_out_sha:
            raise ValueError("MANUAL_PUSH_CHECKOUT_EPOCH_MISMATCH")
        result["status"]="SAME_COMMIT_PUSH_RESEARCH_ONLY"
    else:
        result["status"]="CURRENT_MAIN_RESEARCH_ONLY_NO_FINAL_INVOCATION_ATTESTED"
    return result

def selftest()->None:
    repo="researcher/xray"
    head="a"*40
    raw={"repository":{"full_name":repo},
         "action":"completed",
         "workflow_run":{"id":123,"name":"XRAY Canonical Current Final Factory",
           "head_sha":head,"head_branch":"main","status":"completed",
           "conclusion":"success","head_repository":{"full_name":repo}}}
    from copy import deepcopy
    assert verify("workflow_run",raw,repo,head)["upstream_final_run_id"]==123
    assert verify("push",{"repository":{"full_name":repo},
           "ref":MAIN,"after":head},repo,head)["can_register_R92"] is False
    assert verify("schedule",{"repository":{"full_name":repo}},repo,head)[
           "status"]=="CURRENT_MAIN_RESEARCH_ONLY_NO_FINAL_INVOCATION_ATTESTED"
    tests=[]
    def mod(fn):
        p=deepcopy(raw);fn(p);tests.append(p)
    mod(lambda p:p["workflow_run"].update(head_sha="b"*40))
    mod(lambda p:p["workflow_run"].update(conclusion="failure"))
    mod(lambda p:p["workflow_run"].update(head_branch="develop"))
    mod(lambda p:p["workflow_run"].update(head_repository={"full_name":"attacker/fork"}))
    mod(lambda p:p["workflow_run"].update(name="Other Workflow"))
    mod(lambda p:p["workflow_run"].update(id=0))
    mod(lambda p:p.update(action="requested"))
    mod(lambda p:p.update(repository={"full_name":"attacker/fork"}))
    for payload in tests:
        try:verify("workflow_run",payload,repo,head)
        except ValueError:continue
        raise AssertionError("MANUAL_CROSS_EPOCH_NEGATIVE_BYPASS")
    for event,body in [
        ("push",{"repository":{"full_name":repo},"ref":MAIN,"after":"c"*40}),
        ("push",{"repository":{"full_name":repo},"ref":"refs/heads/dev","after":head})]:
        try:verify(event,body,repo,head)
        except ValueError:continue
        raise AssertionError("MANUAL_PUSH_EPOCH_NEGATIVE_BYPASS")
    print("XRAY_MANUAL_INVOCATION_SELFTEST=PASS_3_POSITIVE_10_NEGATIVE_NO_R92")

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    event_name=os.getenv("GITHUB_EVENT_NAME","")
    event_path=os.getenv("GITHUB_EVENT_PATH","")
    repo=os.getenv("GITHUB_REPOSITORY","")
    if not event_path or not Path(event_path).is_file():
        raise SystemExit("MANUAL_EVENT_PATH_MISSING_FAIL_CLOSED")
    data=json.loads(Path(event_path).read_text(encoding="utf-8"))
    head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    try:out=verify(event_name,data,repo,head)
    except ValueError as e:
        print("XRAY_MANUAL_INVOCATION_STATUS=BLOCKED:"+str(e))
        raise SystemExit(2) from e
    if args.out:
        args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_MANUAL_INVOCATION_STATUS="+out["status"])

if __name__=="__main__":main()
