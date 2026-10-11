#!/usr/bin/env python3
"""Real immutable 9-Oct resolver proof vs 514-MC scope boundary regression.

This is a read-only source verifier. It cannot manufacture cap measurements,
R92 signals, entitlements, phone receipts or order execution.
"""
from __future__ import annotations
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT))
from build_mc_provenance_rebind import settlement_witness_relation, hash_lines

FULL=ROOT/"canonical_resolver_bridge_20261009_c417_dv30_v2.json"
RESIDUAL=ROOT/"canonical_resolver_bridge_20261009_c417_dv30_v1.json"

def require(condition,reason):
    if not condition:
        raise RuntimeError("XRAY_SCOPE_REGRESSION:"+reason)

def git_sha(path):
    return subprocess.check_output(
        ["git","hash-object",str(path)],cwd=REPO,text=True).strip()

def check():
    full=json.loads(FULL.read_text())
    partial=json.loads(RESIDUAL.read_text())
    # v2 is the recorded immutable complete queue; no mutable current-master
    # dependency, so this regression stays valid after the next ASOF.
    master={
        "pass_symbols":full["symbols"],
        "queue_total":full["queue_total"],
        "queue_hash":full["queue_hash"],
    }
    for name,row,path in (("full",full,FULL),("partial",partial,RESIDUAL)):
        require(row.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1",name+"_schema")
        require(row.get("status")=="COMMITTED",name+"_status")
        require(row.get("asof_et")=="2026-10-09",name+"_asof")
        require(row.get("compiled_policy_version")=="C4.17",name+"_policy")
        require(row.get("execution")=="NONE" and row.get("real_money")=="NO-GO",name+"_trade_guard")
        require(row.get("unknown_never_pass") is True,name+"_unknown_guard")
        require(row["symbol_count"]==len(row["symbols"]),name+"_symbol_count")
        require(row["symbol_hash"]==hash_lines(row["symbols"]),name+"_symbol_hash")
        require(len(row["symbols"])==len(set(row["symbols"])),name+"_uniqueness")
        require(len(git_sha(path))==40,name+"_git_blob")
        require(row["queue_hash"]==master["queue_hash"],name+"_queue_hash")
        require(row["queue_total"]==master["queue_total"],name+"_queue_total")
    require(len(full["symbols"])==3184,"expected_full_scope_3184")
    require(len(partial["symbols"])==553,"expected_residual_scope_553")
    require(set(partial["symbols"]).issubset(full["symbols"]),"residual_subset_of_full")
    require(full["settlement_witness_blob_sha"]==git_sha(RESIDUAL),"v2_binds_v1_exact_git_blob")
    require(full["bridge_role"]=="FULL_SCOPE_MC_HANDOFF_PROVENANCE","full_role")
    require(partial["bridge_role"]=="CURRENT_RESIDUAL_REQUEST_AUTHORITY","residual_role")
    require(set(full["settlement_symbols"])=={"AAPL","MSFT","NVDA"},"three_settlement_probes")
    require(set(partial["settlement_symbols"])=={"AAPL","MSFT","NVDA"},"residual_three_settlement_probes")

    require(settlement_witness_relation(full,master)=="EXACT_QUEUE",
            "full_3184_valid_exact_handoff")
    require(settlement_witness_relation(partial,master)=="EXACT_QUEUE_RESIDUAL_SETTLEMENT_ONLY",
            "residual_553_must_never_masquerade_as_3184")

    bad=[]
    def reject(label,row):
        require(settlement_witness_relation(row,master) is None,"accepted_mutant_"+label)
        bad.append(label)
    x=copy.deepcopy(full);x["symbols"]=x["symbols"][:-1];reject("truncated_full_set",x)
    x=copy.deepcopy(full);x["symbol_count"]-=1;reject("wrong_symbol_count",x)
    x=copy.deepcopy(full);x["symbol_hash"]="0"*64;reject("fake_hash",x)
    x=copy.deepcopy(full);x["symbols"][0]=x["symbols"][1];reject("duplicate_member",x)
    x=copy.deepcopy(full);x["symbols"][0]="A!GHOST";x["symbols"].sort()
    x["symbol_hash"]=hash_lines(x["symbols"]);reject("same_count_wrong_member",x)
    x=copy.deepcopy(full);x["queue_total"]+=1;reject("queue_count_spoof",x)
    x=copy.deepcopy(full);x["queue_hash"]="tampered";reject("queue_hash_spoof",x)
    x=copy.deepcopy(full);x["settlement_symbols"]=["AAPL","BAD"];reject("settlement_not_in_scope",x)
    x=copy.deepcopy(full);x["settlement_symbols"]=["AAPL","AAPL"];reject("duplicate_settlement",x)
    x=copy.deepcopy(full);x["bridge_role"]="SOURCE_UNKNOWN";reject("unapproved_role",x)
    x=copy.deepcopy(partial);x["symbols"].append("A!GHOST");x["symbols"].sort()
    x["symbol_count"]=len(x["symbols"]);x["symbol_hash"]=hash_lines(x["symbols"])
    reject("residual_foreign_member",x)
    x=copy.deepcopy(partial);x["settlement_symbols"]=["A!GHOST"];reject("residual_unseen_settlement",x)
    x=copy.deepcopy(partial);x.pop("symbols");reject("residual_missing_set",x)
    # Regression that was actually accepted pre-fix: fake queue total/hash
    # plus 553-source-symbol residual metadata claimed complete.
    x=copy.deepcopy(partial);x["bridge_role"]="FULL_SCOPE_MC_HANDOFF_PROVENANCE"
    reject("residual_disguised_as_full_handoff",x)

    return {
        "schema":"XRAY_MC_RESOLVER_SCOPE_REGRESSION_V1",
        "asof_et":"2026-10-09",
        "real_full_symbol_count":len(full["symbols"]),
        "real_partial_symbol_count":len(partial["symbols"]),
        "queue_label_count":full["queue_total"],
        "partial_hash_equals_full_queue_hash":partial["queue_hash"]==full["queue_hash"],
        "partial_is_full_mc_handoff":False,
        "partial_is_settlement_only":True,
        "full_is_exact_mc_handoff":True,
        "negative_cases":len(bad),
        "real_original_github_sha":{"full":git_sha(FULL),"partial":git_sha(RESIDUAL)},
        "mc_primary_measurements_created":0,
        "r92_created":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "go":False,
    }

def main():
    j=check()
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--out")
    opts=p.parse_args()
    if opts.out:
        Path(opts.out).write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    print("XRAY_REAL_RESOLVER_V1_553_NOT_FULL_V2_3184_EXACT=PASS")
    print("XRAY_MC_RESOLVER_SCOPE_NEGATIVES="+str(j["negative_cases"]))
    print("XRAY_MC_PRIMARY_CREATED=0_REAL_MONEY=NO_GO")

if __name__=="__main__": main()
