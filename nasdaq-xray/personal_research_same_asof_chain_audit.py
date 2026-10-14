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
TARGET_ASOF="2026-10-13"

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
        counts=item.get("counts") or {}
        evidence=item.get("evidence") or {}
        mc=evidence.get("mc") or {}
        inputs[role]={"asof_et":item["asof_et"],
                      "git_blob_sha":git_sha(raw),
                      "path":"nasdaq-xray/"+filename,
                      "unknown_count":item.get("unknown_count"),
                      "status":item.get("status"),
                      "pass_count":item.get("pass_count"),
                      "terminal_mc_primary_pass":counts.get("mc_primary_pass"),
                      "terminal_pre_g9_tech_pass":counts.get("pre_g9_tech_pass"),
                      "final_pre_g9_tech_pass":item.get("pre_g9_tech_pass_count"),
                      "terminal_mc_input_price_sha":mc.get("current_price_blob_sha"),
                      "terminal_mc_blob_sha":mc.get("blob_sha"),
                      "history_source_mc_blob_sha":item.get("source_mc_blob_sha"),
                      "terminal_evidence_blobs":{k.upper():(v or {}).get("blob_sha")
                        for k,v in evidence.items() if k.upper() in NAMES},
                      "candidate_local_research_pass":item.get(
                          "candidate_local_research_pass"),
                      "r92_count":len(item.get("r92_candidates") or [])}
    return inputs

def inspect(inputs,health,policy):
    demand(set(inputs)==set(NAMES),"ROLE_COMPLETENESS")
    demand(policy.get("schema")=="XRAY_PERSONAL_RESEARCH_TECHNICAL_AUTHORITY_V1"
           and policy.get("activation")==
           "RESEARCH_OUTPUT_ONLY_NOT_PRODUCTION_SWITCH"
           and policy.get("can_create_r92") is True
           and policy.get("r92_registration_mode")=="INDEPENDENT_C417_RELEASE_APPROVAL_REQUIRED"
           and policy.get("can_update_compiled_C417_alpha") is False
           and policy.get("r92_creation_requires_all_candidate_local_and_compiled_gates") is True,
           "PERSONAL_POLICY_C417_INDEPENDENT_BOUND")
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
    for role,epoch in asofs.items():
        if epoch!=TARGET_ASOF:
            blockers.append("TARGET_20261013_MISSING_"+role)
    if inputs["MASTER"]["unknown_count"]!=0:
        blockers.append("MASTER_UNKNOWN_NONZERO")
    if inputs["PRICE"]["unknown_count"]!=0:
        blockers.append("PRICE_UNKNOWN_NONZERO")
    if not isinstance(inputs["PRICE"].get("pass_count"),int) or inputs["PRICE"]["pass_count"]<=0:
        blockers.append("NO_C417_PRIMARY_PRICE_PASS")
    if not isinstance(inputs["HISTORY"].get("pass_count"),int) or inputs["HISTORY"]["pass_count"]<=0:
        blockers.append("NO_CURRENT_PRIMARY_HISTORY_PASS")
    if inputs["TERMINAL"].get("terminal_mc_primary_pass") is None or inputs["TERMINAL"]["terminal_mc_primary_pass"]<=0:
        blockers.append("NO_PIT_RECONCILED_PRIMARY_MC_PASS")
    if not isinstance(inputs["FINAL"].get("final_pre_g9_tech_pass"),int) or inputs["FINAL"]["final_pre_g9_tech_pass"]<=0:
        blockers.append("NO_R1_RR_TECH_CONFIRMED_FINAL")
    if not isinstance(inputs["TERMINAL"].get("terminal_pre_g9_tech_pass"),int) or inputs["TERMINAL"]["terminal_pre_g9_tech_pass"]<=0:
        blockers.append("NO_TERMINAL_PRE_G9_TECH_PASS")
    if inputs["TERMINAL"].get("terminal_mc_input_price_sha")!=inputs["PRICE"]["git_blob_sha"]:
        blockers.append("MC_NOT_BOUND_TO_CURRENT_PRICE_BLOB")
    if inputs["TERMINAL"].get("terminal_mc_blob_sha")!=inputs["HISTORY"].get("history_source_mc_blob_sha"):
        blockers.append("HISTORY_MC_BLOB_NOT_BOUND")
    for role in ("MASTER","PRICE","HISTORY","LEGAL","FINAL"):
        if inputs["TERMINAL"]["terminal_evidence_blobs"].get(role)!=inputs[role]["git_blob_sha"]:
            blockers.append("TERMINAL_STALE_"+role+"_BLOB")
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
            "master_asof_et":master,"target_asof_et":TARGET_ASOF,"asof_by_layer":asofs,
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
    demand(len(inputs["TERMINAL"]["terminal_evidence_blobs"])>=5,
           "TERMINAL_EXACT_SOURCE_FIELDS")
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
    invalid["r92_registration_mode"]="UNCONDITIONAL"
    try:inspect(inputs,health,invalid)
    except ValueError:pass
    else:raise AssertionError("UNAUTHORIZED_PERSONAL_ALPHA")
    # Adversarial: retag every stale source to 2026-10-13. Dates and
    # matching labels alone cannot create audited PRICE/MC/FINAL or R92.
    retag=copy.deepcopy(inputs)
    for value in retag.values():
        value["asof_et"]=TARGET_ASOF
    result=inspect(retag,health,policy)
    demand(result["exact_same_asof"] is True and
           "NO_C417_PRIMARY_PRICE_PASS" in result["blockers"] and
           "NO_PIT_RECONCILED_PRIMARY_MC_PASS" in result["blockers"] and
           "NO_R1_RR_TECH_CONFIRMED_FINAL" in result["blockers"] and
           result["r92_provable"] is False,
           "RETARGETED_ASOF_MUST_NOT_IMPLY_PRIMARY")
    print("XRAY_SAME_ASOF_SELFTEST=PASS_7_ADVERSARIAL_R92_FAIL_CLOSED")

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
