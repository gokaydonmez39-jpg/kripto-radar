#!/usr/bin/env python3
"""SHA-bound same-ASOF canonical state and personal research delta audit.

This is a read-only structural decision: a missing or different epoch can
never manufacture an R92 candidate or overwrite existing canonical files.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NAMES={
 "MASTER":"canonical_current_master_manifest.json",
 "PRICE":"canonical_current_price_dv30.json",
 "HISTORY":"canonical_current_history.json",
 "LEGAL":"canonical_current_legal.json",
 "EVENT":"canonical_current_event_state.json",
 "FINAL":"canonical_current_final_tech.json",
 "TERMINAL":"canonical_current_terminal.json"
}
POLICY="chatgpt_compiled_policy_v3.json"
HEALTH="research/health_runtime_reenable_20261014_v1.json"

def demand(v,s):
    if not v:raise ValueError("XRAY_SAME_ASOF_"+s)

def git_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def read_sources():
    inputs={}
    for role,filename in NAMES.items():
        raw=(ROOT/filename).read_bytes()
        item=json.loads(raw)
        demand(isinstance(item,dict) and isinstance(item.get("asof_et"),str),
               "ASOF_ABSENT_"+role)
        demand(item.get("execution")=="NONE" and item.get("real_money")=="NO-GO",
               "SOURCE_SAFETY_"+role)
        inputs[role]={"asof_et":item["asof_et"],
                      "git_blob_sha":git_sha(raw),
                      "path":"nasdaq-xray/"+filename,
                      "unknown_count":item.get("unknown_count"),
                      "status":item.get("status"),
                      "candidate_local_research_pass":item.get(
                          "candidate_local_research_pass"),
                      "r92_count":len(item.get("r92_candidates") or [])}
    return inputs

def inspect(inputs,health,policy):
    demand(set(inputs)==set(NAMES),"ROLE_COMPLETENESS")
    demand(policy.get("schema")=="XRAY_PERSONAL_RESEARCH_TECHNICAL_AUTHORITY_V1"
           and policy.get("activation")==
           "RESEARCH_OUTPUT_ONLY_NOT_PRODUCTION_SWITCH"
           and policy.get("can_create_r92") is False,"PERSONAL_POLICY_BOUND")
    demand(health.get("schema")=="XRAY_HEALTH_RUNTIME_REENABLE_20261014_V1"
           and health.get("enabled_after_update") is True,"HEALTH_CONTROL_WITNESS")
    asofs={k:v["asof_et"] for k,v in inputs.items()}
    master=inputs["MASTER"]["asof_et"]
    blockers=[]
    for k,v in inputs.items():
        demand(isinstance(v["git_blob_sha"],str)
               and len(v["git_blob_sha"])==40,"BLOB_TYPE_"+k)
        if v["asof_et"]!=master:
            blockers.append("CROSS_ASOF_"+k)
    if inputs["MASTER"]["unknown_count"]!=0:
        blockers.append("MASTER_UNKNOWN_NONZERO")
    if inputs["PRICE"]["unknown_count"]!=0:
        blockers.append("PRICE_UNKNOWN_NONZERO")
    if inputs["PRICE"].get("status") not in ("READY","COMPLETE","PASS"):
        blockers.append("PRICE_SCOPE_NOT_RELEASED")
    if inputs["TERMINAL"]["candidate_local_research_pass"] is not True:
        blockers.append("TERMINAL_LOCAL_CANDIDATE_PROOF_MISSING")
    if inputs["TERMINAL"]["r92_count"]==0:
        blockers.append("NO_REAL_R92_REGISTRATION")
    if health.get("real_holiday_suppression_runtime_witness") is not True:
        blockers.append("HEALTH_REAL_HOLIDAY_RUNTIME_NOT_PROVEN")
    blockers=sorted(set(blockers))
    return {"schema":"XRAY_PERSONAL_SAME_ASOF_CHAIN_AUDIT_V1",
            "master_asof_et":master,"asof_by_layer":asofs,
            "canonical_source_git_blob_shas":{
                 key:val["git_blob_sha"] for key,val in inputs.items()},
            "exact_same_asof":len(set(asofs.values()))==1,
            "master_unknown_count":inputs["MASTER"]["unknown_count"],
            "price_unknown_count":inputs["PRICE"]["unknown_count"],
            "blockers":blockers,
            "r92_provable":len(blockers)==0,
            "r92_created":False,
            "root_source_health_enabled_control_verified":
                health["enabled_after_update"] is True,
            "actual_holiday_runtime_verified":
                health.get("real_holiday_suppression_runtime_witness") is True,
            "production_pointer_written":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest(inputs,health,policy):
    live=inspect(inputs,health,policy)
    demand(live["r92_created"] is False
           and live["production_pointer_written"] is False,"SAFETY")
    tests=[
      ("EPOCH",lambda d:d["HISTORY"].update(asof_et="2026-01-01")),
      ("MASTER",lambda d:d["MASTER"].update(unknown_count=10)),
      ("PRICE",lambda d:d["PRICE"].update(unknown_count=540)),
      ("TERMINAL",lambda d:d["TERMINAL"].update(r92_count=0)),
      ("LOCAL",lambda d:d["TERMINAL"].update(candidate_local_research_pass=False))]
    for label,mutate in tests:
        bad=copy.deepcopy(inputs)
        mutate(bad)
        result=inspect(bad,health,policy)
        demand(result["r92_provable"] is False,"FALSE_R92_"+label)
    invalid=copy.deepcopy(policy)
    invalid["can_create_r92"]=True
    try:inspect(inputs,health,invalid)
    except ValueError:pass
    else:raise AssertionError("UNAUTHORIZED_PERSONAL_ALPHA")
    print("XRAY_SAME_ASOF_SELFTEST=PASS_6_NEGATIVES_R92_FAIL_CLOSED")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    inputs=read_sources()
    health=json.loads((ROOT/HEALTH).read_text())
    policy=json.loads((ROOT/"personal_research_technical_policy_v1.json").read_text())
    if args.selftest:
        demand(args.out is None,"SELFTEST_OUT")
        selftest(inputs,health,policy)
        return
    demand(args.out is not None
           and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
           "NO_CANONICAL_DATA_WRITE")
    result=inspect(inputs,health,policy)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_SAME_ASOF="+str(result["exact_same_asof"]))
    print("XRAY_R92_PROVABLE="+str(result["r92_provable"]))
    print("XRAY_SAME_ASOF_BLOCKERS="+json.dumps(result["blockers"],sort_keys=True))

if __name__=="__main__":
    main()
