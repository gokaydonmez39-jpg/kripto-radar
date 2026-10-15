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
    "PRICE_UNKNOWN_CURRENT",
    "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
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

def exact_epoch_mc_names(asof: str, names: list[str]) -> list[str]:
    """List exact epoch/version MC bridge *filenames*, never grant MC authority."""
    if type(asof) is not str or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",asof):
        return []
    pat=(r"canonical_mc_bridge_"+re.escape(asof.replace("-",""))+
         r"_c417_dv30_v[1-9][0-9]*\.json")
    return [n for n in names if type(n) is str and re.fullmatch(pat,n)]


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
    current=exact_epoch_mc_names(p["asof_et"],mc_names)
    require(len(current)==len(set(current)),"DUPLICATE_MC_FILE")
    unknown_in_price=sorted(set(us)&set(ps))
    blocked=set(e.get("blockers") or [])
    require(len(blocked)==len(e.get("blockers") or []),"DUPLICATE_E2E_BLOCKER")
    require(blocked.issubset(BLOCKS),"UNEXPECTED_BLOCKERS_MUST_TRIAGE:"+str(sorted(blocked-BLOCKS)))
    price_unknown=p.get("unknown_symbols")
    require(type(price_unknown) is list and clean(price_unknown) and
            len(price_unknown)==p.get("unknown_count") and
            set(price_unknown).isdisjoint(ps),"PRICE_UNKNOWN_PARTITION_INTEGRITY")
    if price_unknown:
        require("PRICE_UNKNOWN_CURRENT" in blocked,"PRICE_UNKNOWN_MUST_BLOCK_RELEASE")
    require(e.get("current_mc_authority_count")==0 if "CURRENT_MC_AUTHORITY_MISSING" in blocked else True,"MC_AUTHORITY_CLAIM")
    if not current:
        require("CURRENT_MC_AUTHORITY_MISSING" in blocked,"MISSING_MC_NOT_FLAGGED")
    delivery=e.get("delivery_observability")
    require(isinstance(delivery,dict)
            and delivery.get("phase")=="POST_DELIVERY_INDEPENDENT_ACK"
            and delivery.get("status")=="UNVERIFIED_NO_INDEPENDENT_DEVICE_ACK"
            and delivery.get("device_receipt_attested") is False
            and delivery.get("research_release_prerequisite") is False
            and delivery.get("notification_sent_by_this_audit") is False
            and e.get("actual_device_delivery_receipt_attested") is False,
            "POST_DELIVERY_FAKE_ACK_OR_CIRCULAR_RELEASE")
    require(e.get("alpha_authority") is False,"RELEASE_CANNOT_BE_ALPHA_AUTHORITY")
    # Future verified research-ready witnesses must prove every local gate.
    if e.get("ready_for_current_research_signal") is True:
        require(e.get("candidate_local_source_chain_attested") is True
                and e.get("current_mc_authority_count")==1
                and e.get("candidate_preparation_witness_only") is True
                and e.get("official_nasdaq_session_freshness_attested") is True,
                "UNPROVEN_RESEARCH_READY_PROMOTION")
        critical={
            "SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION",
            "CURRENT_MC_AUTHORITY_MISSING",
            "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",
            "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
            "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
            "PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY",
            "PRICE_UNKNOWN_CURRENT",
        }
        require(not (blocked & critical), "READY_WITH_UNRESOLVED_LOCAL_GATE")
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
        "P0_EXACT30_AUTHENTICATED_PRICE_DV30":bool("PRICE_UNKNOWN_CURRENT" in blocked),
        "P0_SETTLEMENT_SOURCE_BINDING":bool("SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT" in blocked),
        "P0_IDENTITY_GLOBAL_COVERAGE":bool("IDENTITY_PARTITION_INCOMPLETE" in blocked),
        "P0_STRICT_G9_ENTITLEMENT":g9_block,
        "P0_DEVICE_RECEIPT_EVIDENCE":not delivery["device_receipt_attested"],
    }
    # Operational dependency order: evidence-only, never a shortcut to AL.
    # A partial global identity set does not contaminate an exact disjoint
    # PRICE survivor cohort; it still blocks universe-wide completeness.
    local_scope_eligible=(len(unknown_in_price)==0 and
                          p.get("asof_et")==e.get("latest_completed_nasdaq_session"))
    mc_authorized=(e.get("current_mc_authority_count")==1 and
                   "CURRENT_MC_AUTHORITY_MISSING" not in blocked)
    terminal_exact=mc_authorized and t.get("asof_et")==p.get("asof_et") and (
        "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE" not in blocked
        and "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN" not in blocked)
    manual_research_preparation=(terminal_exact and e.get(
        "ready_for_current_research_signal") is True)
    ordered_recovery_steps=[
        {
            "order":1,"id":"C417_CURRENT_PRICE_SCOPE",
            "status":"PRICE_UNKNOWN_SOURCE_REQUIRES_EXACT30" if price_unknown
                     else "SOURCE_SCOPE_EXACT_BUT_GLOBAL_IDENTITY_OPEN" if local_scope_eligible and len(us)>0
                     else "SOURCE_SCOPE_EXACT" if local_scope_eligible else "SOURCE_SCOPE_NOT_CURRENT",
            "acceptance":"Current compiled C4.17, exact master and 30-session DV30 PRICE blob/hash/set; no unknown identity intersects PRICE PASS.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":2,"id":"LICENSED_CURRENT_PRIMARY_MC",
            "status":"REQUIRES_REAL_MEASUREMENT_ENTITLEMENT" if not mc_authorized else "MC_AUTHORITY_PRESENT_RECHECK_EXACT_BINDINGS",
            "acceptance":"Same ASOF, issuer/listing identity, license, PIT/report date, current PRICE exact 514-symbol pass set/hash/blob and PRIMARY MC USD >=2bn; no WATCH-to-PRIMARY promotion.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":3,"id":"HISTORY_260_DAILY_52_WEEKLY",
            "status":"WAITING_EXACT_PRIMARY_MC" if not mc_authorized else "NEEDS_FRESH_EXACT_SOURCE_HISTORY_PROOF",
            "acceptance":"260 actual completed official exchange sessions, 52 completed weeks per eligible stock; verified raw-source lineage, actions/split/ticker continuity, no synthetic backfill.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":4,"id":"CORPORATE_ACTIONS_LEGAL_ISSUER_EVENTS",
            "status":"WAITING_HISTORICAL_SOURCE_CHAIN" if not terminal_exact else "RECHECK_CURRENT_ISSUER_PRIMARY_EVIDENCE",
            "acceptance":"Exact candidate-local CA/legal/issuer event PIT, 8-session event horizon, official Nasdaq halt and sticky suspension veto; UNKNOWN never CLEAN.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":5,"id":"STAGE1_WEEKLY_REGIME_DEEP_FINAL_R1_RR",
            "status":"WAITING_ELIGIBLE_SAME_ASOF_CHAIN" if not terminal_exact else "NEEDS_INDEPENDENT_SETUP_EVIDENCE",
            "acceptance":"Same ASOF SHA-bound Stage1, 52-weekly, regime, deep geometry, risks <= policy maxima, family-specific RR, no chase; WATCH never AL.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":6,"id":"TERMINAL_R92_CANDIDATE_LOCAL",
            "status":"PREPARATION_ATTESTED_NOT_DELIVERY" if manual_research_preparation
                     else "BLOCKED_CURRENT_TERMINAL_AND_R92_PROOF",
            "acceptance":"Exact CURRENT terminal candidate_local_research_pass, nonempty registered R92, unique delivery key, official safety, no in-flight scheduler recovery; G9/account not required for manual research.",
            "research_candidate_required":True,"universe_full_e2e_required":True
        },{
            "order":7,"id":"CANONICAL_USER_DELIVERY_AND_RECEIPT",
            "status":"DEVICE_RECEIPT_NOT_ATTESTED",
            "acceptance":"Canonical sole user-facing authority; independent real candidate notification and actual device receipt proof, never infer push from GitHub workflow or task setting.",
            "research_candidate_required":False,"universe_full_e2e_required":False
        },{
            "order":8,"id":"UNIVERSE_WIDE_IDENTITY_COMPLETENESS",
            "status":"GLOBAL_IDENTITY_UNKNOWN_"+str(len(us)) if us else "GLOBAL_IDENTITY_PROVEN",
            "acceptance":"Every remaining official Nasdaq security identity resolved or explicitly excluded; no universe-wide NO_CONFIRMED_SETUP with unknown identity.",
            "research_candidate_required":False,"universe_full_e2e_required":True
        },{
            "order":9,"id":"STRICT_G9_AND_READ_ONLY_ACCOUNT_TRUE_FULL_GO",
            "status":"G9_BLOCKED_ACCOUNT_UNATTESTED" if g9_block else "G9_ACCOUNT_STILL_REQUIRE_SAME_RUN_PROOF",
            "acceptance":"Independent strict zero-dollar consolidated National NBBO A+B+C+D and same-run sanctioned read-only cash/positions plus global FULL_E2E; not prerequisites for manual R92.",
            "research_candidate_required":False,"universe_full_e2e_required":False
        }
    ]
    require([x["order"] for x in ordered_recovery_steps]==list(range(1,10)),
            "RECOVERY_ORDER_INTEGRITY")
    require(all(x["id"] and x["acceptance"] for x in ordered_recovery_steps),
            "RECOVERY_ACCEPTANCE_NOT_EMPTY")
    require(not mc_authorized or manual_research_preparation or
            ordered_recovery_steps[5]["status"]=="BLOCKED_CURRENT_TERMINAL_AND_R92_PROOF",
            "MC_NOT_AL_PROOF")

    derivative={
        "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN":"NEEDS_SAME_ASOF_MEASURED_MC",
        "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE":"NEEDS_MC_HISTORY_LEGAL_STAGE1_EVENTS_FINAL",
        "SOURCE_EPOCH_NOT_LATEST_COMPLETED_SESSION":"RESULT_OF_STALE_TERMINAL_ASOF",
        "PRICE_PASS_NON_G9_SOURCE_NOT_RELEASE_AUTHORITY":"G9_ENTITLEMENT_IS_NOT_HISTORICAL_PRICE_AUTHORITY",
        "PRICE_UNKNOWN_CURRENT":"NO_UNVERIFIED_DV30_PASS_PROMOTION",
        "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT":"REQUIRE_EXACT_CURRENT_SETTLEMENT_PRICE_SOURCE_BINDING",
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
        "ordered_recovery_steps":ordered_recovery_steps,
        "manual_research_g9_account_required":False,
        "manual_candidate_claim_released":False,
        "full_go_g9_account_requires_separate_validation":True,
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
       "unknown_symbols":[],"unknown_count":0,
       "unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"}
    t={"asof_et":"2026-10-07","unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO"}
    blobs={"master":"a"*40,"price":"b"*40,"terminal":"c"*40}
    e={"schema":"XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1",
       "source_blob_shas":dict(blobs),"asof_et":"2026-10-09","terminal_asof_et":"2026-10-07",
       "price_pass_count":1,"master_unknown_count":1,"current_mc_authority_count":0,
       "blockers":sorted(BLOCKS-{"PRICE_UNKNOWN_CURRENT","SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT"}),"source_session_lags":{"TERMINAL":2},
       "actual_device_delivery_receipt_attested":False,"ready_for_current_research_signal":False,"alpha_authority":False,
       "delivery_observability":{
           "phase":"POST_DELIVERY_INDEPENDENT_ACK",
           "status":"UNVERIFIED_NO_INDEPENDENT_DEVICE_ACK",
           "device_receipt_attested":False,
           "research_release_prerequisite":False,
           "notification_sent_by_this_audit":False},
       "historical_manual_non_g9_source_contract_ready":True,
       "historical_manual_research_candidate_prep_only":False,
       "historical_manual_research_no_g9_pass_claim":True,
       "historical_manual_research_no_notification_claim":True}
    return m,p,t,e,blobs,[],{"status":"BLOCKED_STRICT_PERMANENT_ZERO"}

def selftest():
    # Previously r"\\.json" accidentally required a literal backslash,
    # so even a REAL valid bridge name could never match. This positive
    # test must fail on that prior regex, while 8 lookalikes remain rejected.
    mcname="canonical_mc_bridge_20261009_c417_dv30_v1.json"
    accepted=exact_epoch_mc_names("2026-10-09",[mcname])
    require(accepted==[mcname],"MC_VALID_EPOCH_NAME_FALSE_NEGATIVE")
    invalid=[
        "canonical_mc_bridge_20261008_c417_dv30_v1.json",
        "canonical_mc_bridge_20261009_c417_dv20_v1.json",
        "canonical_mc_bridge_20261009_c417_dv30_v0.json",
        "canonical_mc_bridge_20261009_c417_dv30_v1Xjson",
        "canonical_mc_bridge_20261009_c417_dv30_v1.json.backup",
        "nasdaq-xray/canonical_mc_bridge_20261009_c417_dv30_v1.json",
        "canonical_mc_bridge_20261009_c417_dv30_v1\\json",
        "canonical_mc_bridge_20261009_c417_dv30_v-1.json",
    ]
    require(exact_epoch_mc_names("2026-10-09",invalid)==[],
            "MC_OTHER_EPOCH_OR_MALFORMED_ACCEPTED")
    print("XRAY_EXACT_MC_FILENAME=PASS_ONE_VALID_EIGHT_NEGATIVES")
    x=fixtures()
    good=evaluate(*x)
    require(good["master_identity_unknown_intersection_price_pass_count"]==0,"BASE_DISJOINT")
    require(good["canonical_mc_current_revision_count"]==0,"BASE_NO_MC")
    require(len(good["root_cause_classes"])==6 and
            good["root_cause_classes"]["P0_EXACT30_AUTHENTICATED_PRICE_DV30"] is False and
            good["root_cause_classes"]["P0_SETTLEMENT_SOURCE_BINDING"] is False,
            "SIX_ROOT_CLASSES_WITH_TWO_EXPLICIT_SOURCE_GATES")
    require(len(good["ordered_recovery_steps"])==9 and
            good["ordered_recovery_steps"][1]["status"]=="REQUIRES_REAL_MEASUREMENT_ENTITLEMENT" and
            good["ordered_recovery_steps"][7]["status"]=="GLOBAL_IDENTITY_UNKNOWN_1" and
            good["manual_research_g9_account_required"] is False and
            good["manual_candidate_claim_released"] is False, "ORDERED_RECOVERY_NEGATIVE_DEFAULT")
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
        (3,"delivery_observability",{"device_receipt_attested":True}),
        (3,"delivery_observability",{"phase":"POST_DELIVERY_INDEPENDENT_ACK",
            "status":"UNVERIFIED_NO_INDEPENDENT_DEVICE_ACK",
            "device_receipt_attested":False,
            "research_release_prerequisite":True,
            "notification_sent_by_this_audit":False}),
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
    require(good["root_cause_classes"]["P0_DEVICE_RECEIPT_EVIDENCE"] is True,
            "INDEPENDENT_DELIVERY_UNKNOWN_NOT_LOST")
    require("NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN" not in good["e2e_blockers_exact"],
            "DEVICE_ACK_NOT_A_SOURCE_BLOCKER")
    # POSITIVE future-research-only witness: allow a source-ready candidate
    # without claiming its notification arrived on a real phone. The fixture
    # is isolated and never grants alpha, G9 or real market source authority.
    future=list(copy.deepcopy(x))
    future[2]["asof_et"]="2026-10-09"
    future[3]["terminal_asof_et"]="2026-10-09"
    future[3]["current_mc_authority_count"]=1
    future[3]["candidate_local_source_chain_attested"]=True
    future[3]["candidate_preparation_witness_only"]=True
    future[3]["official_nasdaq_session_freshness_attested"]=True
    future[3]["latest_completed_nasdaq_session"]="2026-10-09"
    future[3]["ready_for_current_research_signal"]=True
    future[3]["blockers"]=["IDENTITY_PARTITION_INCOMPLETE"]
    future[5]=["canonical_mc_bridge_20261009_c417_dv30_v1.json"]
    positive=evaluate(*future)
    require(positive["root_cause_classes"]["P0_DEVICE_RECEIPT_EVIDENCE"] is True
            and positive["manual_candidate_claim_released"] is False
            and positive["go"] is False,
            "FUTURE_READY_WITHOUT_FAKE_DEVICE_OR_ALPHA")
    tamper=copy.deepcopy(future)
    tamper[3]["blockers"].append("CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE")
    try:
        evaluate(*tamper)
    except ValueError: pass
    else: raise RuntimeError("FUTURE_READY_WITH_STALE_TERMINAL_ACCEPTED")
    print("XRAY_FUTURE_RESEARCH_READY=PASS_POSITIVE_AND_STALE_SOURCE_NEGATIVE_NO_DEVICE_ACK")
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
    print("XRAY_CAUSAL_DAG_ORDERED_RECOVERY="+json.dumps([{ "order":x["order"],"id":x["id"],"status":x["status"] } for x in result["ordered_recovery_steps"]],sort_keys=True))
    print("XRAY_CAUSAL_DAG_GO=false_RECEIPT=false")

if __name__=="__main__":
    main()
