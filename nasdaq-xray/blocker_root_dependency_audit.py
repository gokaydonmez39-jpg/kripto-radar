#!/usr/bin/env python3
"""Reproduce current X-RAY seven blockers as root causes vs consequences.

Reads immutable checked-out Git blobs, never changes MC, signal, WATCH, GO,
notifications, trading, credentials, market data or source entitlements.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
BLOCKS={
    "CURRENT_MC_AUTHORITY_MISSING",
    "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",
    "IDENTITY_PARTITION_INCOMPLETE",
    "SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION",
    "PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY",
    "NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN",
    "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
}
BLOBS={
    "master":"canonical_current_master_manifest.json",
    "price":"canonical_current_price_dv30.json",
    "terminal":"canonical_current_terminal.json",
}
def require(ok, label):
    if not ok:
        raise ValueError("XRAY_ROOT_CAUSE_AUDIT:"+label)

def git_sha(name):
    return subprocess.check_output(["git","hash-object",str(ROOT/name)],cwd=REPO,text=True).strip()

def sha_symbols(items):
    return hashlib.sha256("\n".join(items).encode()).hexdigest()

def clean(symbols):
    return (type(symbols) is list
        and all(type(x) is str and re.fullmatch("[A-Z0-9.\\-]+",x) for x in symbols)
        and symbols==sorted(set(symbols)))

def evaluate(m,p,t,e,blobs,mc_names,strict_g9):
    require(e.get("schema")=="XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1","E2E_SCHEMA")
    require(set(e.get("source_blob_shas") or {})>=set(BLOBS),"E2E_BLOB_SCOPE")
    for key in BLOBS:
        require(e["source_blob_shas"][key]==blobs.get(key),"E2E_SOURCE_SHA_"+key)
    require(all((a.get("execution"),a.get("real_money"))==("NONE","NO-GO") for a in (m,p,t)),"TRADE_GUARD")
    require(m.get("unknown_never_pass") is True and p.get("unknown_never_pass") is True and t.get("unknown_never_pass") is True,"UNKNOWN_GUARD")
    require(p.get("asof_et")==m.get("asof_et")==e.get("asof_et"),"CURRENT_MASTER_PRICE_ASOF")
    require(t.get("asof_et")==e.get("terminal_asof_et"),"TERMINAL_ASOF")
    ps,ms,us=p.get("pass_symbols"),m.get("pass_symbols"),m.get("unknown_symbols")
    require(all(clean(x) for x in (ps,ms,us)),"IDENTITY_SETS_INVALID")
    require(len(ps)==p.get("pass_count")==e.get("price_pass_count"),"PRICE_PASS_COUNT")
    require(len(ms)==m.get("pass_count"),"MASTER_PASS_COUNT")
    require(len(us)==m.get("unknown_count")==e.get("master_unknown_count"),"MASTER_UNKNOWN_COUNT")
    require(set(ms).isdisjoint(us),"MASTER_UNKNOWN_IN_PASS")
    require(set(ps).issubset(ms),"PRICE_NOT_SUBSET_MASTER")
    require(p.get("pass_hash")==sha_symbols(ps),"PRICE_HASH")
    require(m.get("queue_hash")==sha_symbols(ms),"MASTER_QUEUE_HASH")
    require(p.get("source_master_queue_hash")==m.get("queue_hash"),"PRICE_MASTER_BINDING")
    require(isinstance(mc_names,list),"MC_FILES_INPUT")
    current_name_prefix="canonical_mc_bridge_"+str(p["asof_et"]).replace("-","")+"_c417_dv30_v"
    current=[n for n in mc_names if n.startswith(current_name_prefix) and re.fullmatch(r"v[1-9][0-9]*\\.json",n[len(current_name_prefix)-1:])]
    # Explicit simpler full basename regex prevents unrelated policy/epoch matches.
    current=[n for n in mc_names if re.fullmatch(
        r"canonical_mc_bridge_"+p["asof_et"].replace("-","")+r"_c417_dv30_v[1-9][0-9]*\\.json",n)]
    require(len(current)==len(set(current)),"DUPLICATE_MC_FILE")
    unknown_in_price=sorted(set(us)&set(ps))
    blocked=set(e.get("blockers") or [])
    require(len(blocked)==len(e.get("blockers") or []),"DUPLICATE_E2E_BLOCKER")
    require(blocked.issubset(BLOCKS),"UNEXPECTED_BLOCKERS_MUST_TRIAGE:"+str(sorted(blocked-BLOCKS)))
    require(e.get("current_mc_authority_count")==0 if "CURRENT_MC_AUTHORITY_MISSING" in blocked else True,"MC_AUTHORITY_CLAIM")
    if not current:
        require("CURRENT_MC_AUTHORITY_MISSING" in blocked,"MISSING_MC_NOT_FLAGGED")
    require(e.get("actual_device_delivery_receipt_attested") is False,"FAKE_DEVICE_RECEIPT")
    require(e.get("alpha_authority") is False and e.get("ready_for_current_research_signal") is False,"RELEASE_PROMOTION")
    manual_compatible=e.get("historical_manual_non_g9_source_contract_ready")
    manual_prep=e.get("historical_manual_research_candidate_prep_only")
    require(type(manual_compatible) is bool and type(manual_prep) is bool,
            "MANUAL_HISTORICAL_CONTRACT_ATTESTATIONS_REQUIRED")
    require(e.get("historical_manual_research_no_g9_pass_claim") is True,
            "HISTORICAL_NOT_STRICT_G9_LABEL_MISSING")
    require(e.get("historical_manual_research_no_notification_claim") is True,
            "HISTORICAL_NOT_DELIVERY_LABEL_MISSING")
    if manual_prep:
        require(manual_compatible and e.get("current_mc_authority_count")==1,
                "FAKE_MANUAL_PREP_WITHOUT_PRIMARY_MC")
    g9_block=(strict_g9.get("status")=="BLOCKED_STRICT_PERMANENT_ZERO")
    root={
        "P0_CURRENT_MEASURED_PRIMARY_MC":bool("CURRENT_MC_AUTHORITY_MISSING" in blocked),
        "P0_IDENTITY_GLOBAL_COVERAGE":bool("IDENTITY_PARTITION_INCOMPLETE" in blocked),
        "P0_STRICT_G9_ENTITLEMENT":g9_block,
        "P0_DEVICE_RECEIPT_EVIDENCE":bool("NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN" in blocked),
    }
    derivative={
        "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN":"NEEDS_SAME_ASOF_MEASURED_MC",
        "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE":"NEEDS_MC_HISTORY_LEGAL_STAGE1_EVENTS_FINAL",
        "SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION":"RESULT_OF_STALE_TERMINAL_ASOF",
        "PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY":"G9_ENTITLEMENT_IS_NOT_HISTORICAL_PRICE_AUTHORITY",
    }
    return {
        "schema":"XRAY_C417_BLOCKER_CAUSAL_DAG_V1",
        "asof_et":p["asof_et"],"master_asof_et":m["asof_et"],"terminal_asof_et":t["asof_et"],
        "source_blob_shas":{x:blobs[x] for x in BLOBS},
        "price_pass_count":len(ps),"master_pass_count":len(ms),
        "master_identity_unknown_count":len(us),
        "master_identity_unknown_intersection_price_pass_count":len(unknown_in_price),
        "master_identity_unknown_intersection_price_pass":unknown_in_price,
        "global_identity_unknown_cannot_be_inferred_pass":True,
        "candidate_local_identity_disjoint_does_not_prove_mc_or_al":True,
        "canonical_mc_current_revision_count":len(current),
        "canonical_current_mc_primary_count_attested":e["current_mc_authority_count"],
        "root_cause_classes":root,
        "downstream_blocker_dependencies":{k:v for k,v in derivative.items() if k in blocked},
        "e2e_blockers_exact":sorted(blocked),
        "strict_g9_status":strict_g9.get("status"),
        "historical_manual_non_g9_source_contract_ready":manual_compatible,
        "historical_manual_research_candidate_prep_only":manual_prep,
        "historical_manual_no_live_g9_or_order_claim":True,
        "e2e_latest_completed_nasdaq_session":e.get("latest_completed_nasdaq_session"),
        "terminal_session_lag":(e.get("source_session_lags") or {}).get("TERMINAL"),
        "needs_authorized_primary_mc_measurement":root["P0_CURRENT_MEASURED_PRIMARY_MC"],
        "possible_research_only_without_g9_is_not_full_go":True,
        "registered_r92_attested":False,
        "real_device_notification_receipt_attested":False,
        "go":False,"alpha_authority":False,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }

def fixtures():
    m={"asof_et":"2026-10-09","pass_symbols":["AAA","BBB"],"pass_count":2,
       "unknown_symbols":["SPAC"],"unknown_count":1,
       "queue_hash":sha_symbols(["AAA","BBB"]),"unknown_never_pass":True,
       "execution":"NONE","real_money":"NO-GO"}
    p={"asof_et":"2026-10-09","pass_symbols":["AAA"],"pass_count":1,
       "pass_hash":sha_symbols(["AAA"]),"source_master_queue_hash":m["queue_hash"],
       "unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"}
    t={"asof_et":"2026-10-07","unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"}
    blobs={"master":"a"*40,"price":"b"*40,"terminal":"c"*40}
    e={"schema":"XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1",
       "source_blob_shas":dict(blobs),"asof_et":"2026-10-09","terminal_asof_et":"2026-10-07",
       "price_pass_count":1,"master_unknown_count":1,"current_mc_authority_count":0,
       "blockers":sorted(BLOCKS),"source_session_lags":{"TERMINAL":2},
       "actual_device_delivery_receipt_attested":False,"ready_for_current_research_signal":False,"alpha_authority":False,
       "historical_manual_non_g9_source_contract_ready":True,
       "historical_manual_research_candidate_prep_only":False,
       "historical_manual_research_no_g9_pass_claim":True,
       "historical_manual_research_no_notification_claim":True}
    return m,p,t,e,blobs,[],{"status":"BLOCKED_STRICT_PERMANENT_ZERO"}

def selftest():
    x=fixtures()
    good=evaluate(*x)
    require(good["master_identity_unknown_intersection_price_pass_count"]==0,"BASE_DISJOINT")
    require(good["canonical_mc_current_revision_count"]==0,"BASE_NO_MC")
    require(len(good["root_cause_classes"])==4,"FOUR_ROOT_CLASSES")
    n=0
    for idx,key,bad in [
        (0,"pass_symbols",["AAA","SPAC"]),
        (0,"unknown_symbols",["AAA"]),
        (0,"unknown_count",3),
        (0,"queue_hash","f"*64),
        (1,"source_master_queue_hash","f"*64),
        (1,"pass_hash","f"*64),
        (1,"asof_et","2026-10-07"),
        (1,"pass_count",3),
        (2,"execution","TRADE"),
        (2,"unknown_never_pass",False),
        (3,"source_blob_shas",{"master":"x"*40,"price":"b"*40,"terminal":"c"*40}),
        (3,"actual_device_delivery_receipt_attested",True),
        (3,"ready_for_current_research_signal",True),
        (3,"current_mc_authority_count",1),
        (3,"historical_manual_research_candidate_prep_only",True),
        (3,"historical_manual_research_no_g9_pass_claim",False),
        (3,"historical_manual_research_no_notification_claim",False),
    ]:
        items=copy.deepcopy(x)
        items[idx][key]=bad
        try:
            evaluate(*items)
        except ValueError:
            n+=1
        else:
            raise RuntimeError("XRAY_NEGATIVE_MUTANT_ACCEPTED:"+str((idx,key)))
    # A 12th unknown SPAC in the master outside PRICE must not alter PRICE scope.
    xx=copy.deepcopy(x)
    xx[0]["unknown_symbols"]=["S1","S2"]
    xx[0]["unknown_count"]=xx[3]["master_unknown_count"]=2
    out=evaluate(*xx)
    require(out["master_identity_unknown_intersection_price_pass_count"]==0,"UNKNOWN_DISJOINT")
    # Current successful research evaluation is NOT under test, and cannot
    # be claimed from absent MC with a fake terminal.
    print("XRAY_CAUSAL_DAG_SELFTEST=PASS_"+str(n)+"_MUTANTS_NO_MC_PROMOTION")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--e2e-witness")
    parser.add_argument("--out")
    opt=parser.parse_args()
    if opt.selftest:
        selftest();return
    require(bool(opt.e2e_witness) and bool(opt.out),"WITNESS_AND_OUTPUT_REQUIRED")
    data={k:json.loads((ROOT/v).read_text()) for k,v in BLOBS.items()}
    e=json.loads(Path(opt.e2e_witness).read_text())
    g9=json.loads((ROOT/"g9_entitlement_authority.json").read_text())
    b={k:git_sha(v) for k,v in BLOBS.items()}
    mc=[x.name for x in ROOT.glob("canonical_mc_bridge_*.json")]
    result=evaluate(data["master"],data["price"],data["terminal"],e,b,mc,g9)
    Path(opt.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_CAUSAL_DAG_ROOT_CLASSES="+str(result["root_cause_classes"]))
    print("XRAY_CAUSAL_DAG_UNKNOWN_INTERSECT_PRICE="+str(result["master_identity_unknown_intersection_price_pass_count"]))
    print("XRAY_CAUSAL_DAG_CURRENT_PRIMARY_MC="+str(result["canonical_current_mc_primary_count_attested"]))
    print("XRAY_CAUSAL_DAG_GO=false_RECEIPT=false")

if __name__=="__main__":
    main()
