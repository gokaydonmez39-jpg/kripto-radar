#!/usr/bin/env python3
"""Read-only C4.17 / manual-research end-to-end production readiness witness.

Outputs *blocked states*, never prices, tickers, trade instructions or signals.
A green CI job running this script is NOT a production-ready claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"

def read(name):
    p=ROOT/name
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError,OSError): return {}

def sha(name):
    try:
        b=(ROOT/name).read_bytes()
        return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
    except OSError:
        return None

def mc_exact(mc,price,price_sha):
    """Do NOT accept WATCH, missing provenance or incomplete symbol partitions."""
    symbols=set(price.get("pass_symbols") or [])
    statuses={
       "MC_PASS_PRIMARY":set(mc.get("primary_pass_symbols") or []),
       "MC_FAIL_PRIMARY":set(mc.get("primary_fail_symbols") or []),
       "MC_PASS_FALLBACK_WATCH":set(mc.get("fallback_watch_symbols") or []),
       "MC_FAIL_FALLBACK_TWO_SOURCE":set(mc.get("fallback_fail_symbols") or mc.get("fallback_two_source_fail_symbols") or []),
       "MC_UNKNOWN":set(mc.get("unknown_symbols") or [])}
    if not (mc.get("asof_et")==price.get("asof_et")
            and mc.get("input_blob_sha")==price_sha
            and mc.get("input_pass_hash")==price.get("pass_hash")
            and mc.get("policy_hash")==POLICY
            and mc.get("execution")=="NONE" and mc.get("real_money")=="NO-GO"
            and mc.get("unknown_never_pass") is True
            and set(mc.get("input_pass_symbols") or [])==symbols
            and len(mc.get("input_pass_symbols") or [])==len(symbols)
            and set(mc.get("results") or {})==symbols):
        return False
    seen=set()
    for group, group_symbols in statuses.items():
        if seen & group_symbols:return False
        seen |= group_symbols
        if any((mc["results"][s] or {}).get("status") != group for s in group_symbols):
            return False
    counts=mc.get("counts") or {}
    if any(int(counts.get(k,-1))!=len(v) for k,v in statuses.items()):
        return False
    return seen==symbols

def terminal_chain_exact(terminal, asof, source_shas, mc_name, mc_sha):
    """Full terminal is current ONLY with every upstream Git blob bound."""
    ev=terminal.get("evidence") or {}
    checks=terminal.get("checks") or {}
    names=("master","price","history","events","final")
    if not (
        terminal.get("asof_et")==asof
        and terminal.get("compiled_policy_hash")==POLICY
        and terminal.get("full_end_to_end_research_pass") is True
        and checks.get("exact_blob_provenance_chain") is True
        and checks.get("semantic_provenance_chain_exact") is True
        and isinstance(mc_name,str)
        and mc_name.startswith("canonical_mc_bridge_")
        and (ev.get("mc") or {}).get("path")=="nasdaq-xray/"+mc_name
        and (ev.get("mc") or {}).get("blob_sha")==mc_sha
        and all((ev.get(k) or {}).get("blob_sha")==source_shas.get(k)
                and source_shas.get(k) is not None for k in names)
    ):
        return False
    return True

def scope_readiness(blockers,chain_exact):
    """Distinguish global universe completion from exact candidate-local lineage.

    This function never vets a particular setup or acknowledges an iPhone
    notification; neither can be inferred from symbol counts or workflow PASS.
    """
    local_hard={
        "POLICY_SAFETY_NOT_ALL_ATTESTED",
        "PRICE_PARTITION_NOT_EXACT_CURRENT",
        "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
        "CURRENT_MC_AUTHORITY_MISSING",
        "CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",
        "TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
    }
    global_only={"IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS"}
    blocks=set(blockers)
    local=bool(chain_exact) and blocks.isdisjoint(local_hard)
    return {
        "candidate_local_source_chain_attested":local,
        "full_universe_source_coverage_attested":local and blocks.isdisjoint(global_only),
        "candidate_local_al_setup_attested":False,
        "actual_device_delivery_receipt_attested":False,
    }

TASK_ID="6a825366222081918997094d76e6ae46"
REQUIRED_REGISTERED_FIELDS=(
    "delivery_key","symbol","setup","asof_et","entry_low","entry_high",
    "chase_limit","stop","r1","rr_basic","rr_severe","dv30",
    "regime","event_status","mc_class","mc_source","liquidity","pass_reason",
    "g9_status","account_status","registered_at_utc","execution","real_money"
)
REQUIRED_LOCAL_CHECKS=(
    "candidate_local_research_pass","alpha_semantic_conformance_exact",
    "alpha_source_binding_exact","lifecycle_frozen_semantics_exact",
    "candidate_legal_guard_exact_binding","all_finalists_detailed_legal_review_exact",
    "mc_exact_price_pass_set","semantic_provenance_chain_exact"
)

def registered_research_candidate_exact(terminal,pointer,asof,terminal_sha):
    """A positive *preparation* witness; actual delivery requires delivery_prepare.

    No user notification/phone receipt/trading action is inferred from this.
    All candidate fields, exact pointer and terminal registration must agree.
    """
    if not (terminal.get("asof_et")==asof
            and terminal.get("candidate_local_research_pass") is True
            and (terminal.get("candidate_delivery_safety") or {}).get("status")=="PASS"
            and all((terminal.get("checks") or {}).get(x) is True for x in REQUIRED_LOCAL_CHECKS)
            and pointer.get("schema")=="XRAY_GITHUB_DURABLE_STATE_V3"
            and pointer.get("authority")=="GITHUB_CURRENT_POINTER"
            and pointer.get("execution")=="NONE" and pointer.get("real_money")=="NO-GO"):
        return False
    state=pointer.get("state_json")
    if isinstance(state,str):
        try: state=json.loads(state)
        except (ValueError,TypeError):return False
    if not isinstance(state,dict):
        return False
    if not (state.get("task_id")==TASK_ID
            and state.get("asof_et")==asof
            and (state.get("deep_final_evidence") or {}).get("terminal_path")
                =="nasdaq-xray/canonical_current_terminal.json"
            and (state.get("deep_final_evidence") or {}).get("terminal_blob_sha")==terminal_sha):
        return False
    keys=state.get("delivery_keys") or []
    rows=state.get("r92") or []
    terminal_keys=terminal.get("r92_candidates") or []
    pre_keys=(terminal.get("sets") or {}).get("pre_g9_tech_pass") or []
    if not (isinstance(keys,list) and isinstance(rows,list)
            and isinstance(terminal_keys,list) and isinstance(pre_keys,list)
            and 1<=len(rows)<=3 and len(set(keys))==len(keys)
            and set(terminal_keys)==set(pre_keys)
            and bool(terminal_keys)):
        return False
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("schema")!="XRAY_RESEARCH_CANDIDATE_R92_V1":
            return False
        if any(row.get(k) is None for k in REQUIRED_REGISTERED_FIELDS):
            return False
        nums=("entry_low","entry_high","chase_limit","stop",
              "r1","rr_basic","rr_severe","dv30")
        if any(isinstance(row.get(n),bool) or not isinstance(row.get(n),(int,float))
               or not math.isfinite(row[n]) for n in nums):
            return False
        if not (0 < row["stop"] < row["entry_low"] <= row["entry_high"]
                <= row["chase_limit"] < row["r1"]
                and row["dv30"]>=50_000_000
                and row["rr_basic"]>=2.0 and row["rr_severe"]>=1.5):
            return False
        key=str(row.get("symbol") or "").upper()+"|"+str(row.get("setup") or "").upper()
        dkey=row.get("delivery_key")
        if (key not in terminal_keys or dkey not in keys or dkey in seen
            or row.get("asof_et")!=asof
            or row.get("mc_class")!="MC_PASS_PRIMARY"
            or row.get("execution")!="NONE" or row.get("real_money")!="NO-GO"):
            return False
        seen.add(dkey)
    return True

def snapshot():
    master=read("canonical_current_master_manifest.json")
    price=read("canonical_current_price_dv30.json")
    req=read("canonical_current_resolver_request.json")
    terminal=read("canonical_current_terminal.json")
    ledger=read("delivery_ledger.json")
    blocks=[]
    def fail(code,ok):
        if not ok:blocks.append(code)
    asof=master.get("asof_et")
    safety=(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                and x.get("unknown_never_pass") is True for x in (master,price,req,terminal)))
    fail("POLICY_SAFETY_NOT_ALL_ATTESTED",safety)
    master_set=set(master.get("pass_symbols") or [])
    fail("IDENTITY_PARTITION_INCOMPLETE",master.get("unknown_count")==0
         and int(master.get("queue_total") or -1)==len(master_set))
    price_set=set(price.get("pass_symbols") or [])
    fail("PRICE_PARTITION_NOT_EXACT_CURRENT",bool(asof)
         and price.get("asof_et")==asof
         and price.get("source_master_queue_hash")==master.get("queue_hash")
         and price.get("source_master_count")==master.get("queue_total")
         and len(price.get("results") or {})==len(master_set)
         and set(price.get("results") or {})==master_set
         and set(price.get("blocked_symbols") or []).isdisjoint(price_set)
         and int(price.get("pass_count") or -1)==len(price_set))
    fail("PRICE_BLOCKED_30_SESSION_BARS",price.get("unknown_count")==0
         and price.get("blocked_count")==0)
    price_sha=sha("canonical_current_price_dv30.json")
    fail("SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",req.get("asof_et")==asof
         and req.get("source_master_blob_sha")==sha("canonical_current_master_manifest.json")
         and req.get("source_price_blob_sha")==price_sha
         and req.get("settlement_already_proven") is True
         and req.get("settlement_bridge_blob_sha")==sha(
             Path(str(req.get("settlement_bridge_path") or "")).name))
    mc_files=list(ROOT.glob("canonical_mc_bridge_*_c417_dv30_v*.json"))
    mc_authorities=[p for p in mc_files if p.name.startswith("canonical_mc_bridge_"+str(asof or "").replace("-","")+"_"+ "c417_dv30_v")]
    mcs=[]
    for p in mc_authorities:
        try:j=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        if mc_exact(j,price,price_sha):mcs.append(p.name)
    fail("CURRENT_MC_AUTHORITY_MISSING",len(mcs)==1)
    exact_terminal=(terminal.get("asof_et")==asof
        and terminal.get("full_end_to_end_research_pass") is True
        and terminal.get("compiled_policy_hash")==POLICY)
    fail("CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",exact_terminal)
    source_shas={key:sha(name) for key,name in {
        "master":"canonical_current_master_manifest.json",
        "price":"canonical_current_price_dv30.json",
        "history":"canonical_current_history.json",
        "events":"canonical_current_event_state.json",
        "final":"canonical_current_final_tech.json"}.items()}
    current_chain=(len(mcs)==1 and terminal_chain_exact(
        terminal,asof,source_shas,mcs[0],sha(mcs[0])))
    fail("TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",current_chain)
    pointer=read("chatgpt_canonical_state_v2.json")
    prepared=bool(current_chain and registered_research_candidate_exact(
        terminal,pointer,asof,sha("canonical_current_terminal.json")))
    # Delivery is independent: a zero-signal scenario may be a legitimate
    # completed run, but a device receipt must never be inferred from a ledger.
    fail("NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN",False)
    scopes=scope_readiness(blocks,current_chain)
    return {
        "schema":"XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1",
        "asof_et":asof,"research_mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
        "blockers":sorted(set(blocks)),
        "ready_for_current_research_signal":prepared,
        "candidate_preparation_witness_only":prepared,
        "actual_device_delivery_receipt_attested":False,
        "full_e2e_research_attested":current_chain
            and not any(k in blocks for k in (
                "PRICE_PARTITION_NOT_EXACT_CURRENT","POLICY_SAFETY_NOT_ALL_ATTESTED",
                "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
                "IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS")),
        "current_mc_authority_count":len(mcs),
        **scopes,
        "price_pass_count":price.get("pass_count"),"price_blocked_count":price.get("blocked_count"),
        "master_unknown_count":master.get("unknown_count"),
        "terminal_asof_et":terminal.get("asof_et"),
        "ledger_entry_count":len(ledger.get("deliveries") or {}),
        "source_blob_shas":{
            "master":sha("canonical_current_master_manifest.json"),
            "price":price_sha,
            "resolver_request":sha("canonical_current_resolver_request.json"),
            "terminal":sha("canonical_current_terminal.json")},
        "no_trading_or_device_receipt_claim":True,
        "explanation":"An Actions SUCCESS for this audit only means the fail-closed blocker classification completed."
    }

def selftest():
    price={"asof_et":"2026-10-08","pass_symbols":["A","B"],"pass_hash":"X"}
    mc={"asof_et":"2026-10-08","input_blob_sha":"P","input_pass_hash":"X",
       "input_pass_symbols":["A","B"],"policy_hash":POLICY,"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "primary_pass_symbols":["A"],"primary_fail_symbols":[],
       "fallback_watch_symbols":["B"],"fallback_fail_symbols":[],"unknown_symbols":[],
       "counts":{"MC_PASS_PRIMARY":1,"MC_FAIL_PRIMARY":0,"MC_PASS_FALLBACK_WATCH":1,
                "MC_FAIL_FALLBACK_TWO_SOURCE":0,"MC_UNKNOWN":0},
       "results":{"A":{"status":"MC_PASS_PRIMARY"},"B":{"status":"MC_PASS_FALLBACK_WATCH"}}}
    assert mc_exact(mc,price,"P")
    from copy import deepcopy
    for change in (
       lambda x:x.update(input_blob_sha="OTHER"),
       lambda x:x.update(asof_et="2026-10-07"),
       lambda x:x["results"]["B"].update(status="MC_PASS_PRIMARY"),
       lambda x:x["unknown_symbols"].append("B"),
       lambda x:x["counts"].update(MC_PASS_PRIMARY=2),
       lambda x:x.update(input_pass_symbols=["A"]),
       lambda x:x.update(policy_hash="INVALID")):
        bad=deepcopy(mc);change(bad)
        assert not mc_exact(bad,price,"P"),bad
    base_shas={k:k+"_SHA" for k in ("master","price","history","events","final")}
    t={"asof_et":"2026-10-08","compiled_policy_hash":POLICY,
       "full_end_to_end_research_pass":True,
       "checks":{"exact_blob_provenance_chain":True,
                 "semantic_provenance_chain_exact":True},
       "evidence":{**{k:{"blob_sha":v} for k,v in base_shas.items()},
                   "mc":{"path":"nasdaq-xray/canonical_mc_bridge_20261008_c417_dv30_v1.json",
                         "blob_sha":"MC_SHA"}}}
    good="canonical_mc_bridge_20261008_c417_dv30_v1.json"
    assert terminal_chain_exact(t,"2026-10-08",base_shas,good,"MC_SHA")
    for changed in (
        lambda x:x["evidence"]["mc"].update(blob_sha="BAD"),
        lambda x:x["evidence"]["events"].update(blob_sha="STALE"),
        lambda x:x["checks"].update(exact_blob_provenance_chain=False),
        lambda x:x.update(full_end_to_end_research_pass=False),
        lambda x:x.update(asof_et="2026-10-07")):
        bad=deepcopy(t);changed(bad)
        assert not terminal_chain_exact(bad,"2026-10-08",base_shas,good,"MC_SHA")
    global_only=("IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS")
    x=scope_readiness(global_only,True)
    assert x["candidate_local_source_chain_attested"] is True
    assert x["full_universe_source_coverage_attested"] is False
    assert x["candidate_local_al_setup_attested"] is False
    assert x["actual_device_delivery_receipt_attested"] is False
    assert scope_readiness([],True)["full_universe_source_coverage_attested"] is True
    assert scope_readiness([],False)["candidate_local_source_chain_attested"] is False
    for blocker in ("CURRENT_MC_AUTHORITY_MISSING","TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",
                    "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
                    "POLICY_SAFETY_NOT_ALL_ATTESTED"):
        assert scope_readiness([blocker],True)["candidate_local_source_chain_attested"] is False
    # A negative-only readiness implementation is not a working state
    # machine. Prove real future exact candidate registration is reachable,
    # while tampered provenance, mismatched MC, or absent registration fail.
    from copy import deepcopy
    reg_t=deepcopy(t)
    reg_t["candidate_local_research_pass"]=True
    reg_t["candidate_delivery_safety"]={"status":"PASS"}
    reg_t["checks"].update({key:True for key in REQUIRED_LOCAL_CHECKS})
    reg_t["r92_candidates"]=["AAA|B"]
    reg_t["sets"]={"pre_g9_tech_pass":["AAA|B"]}
    reg_row={key:"present" for key in REQUIRED_REGISTERED_FIELDS}
    reg_row.update({
        "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
        "delivery_key":"exact-key", "symbol":"AAA","setup":"B",
        "asof_et":"2026-10-08","mc_class":"MC_PASS_PRIMARY",
        "execution":"NONE","real_money":"NO-GO",
        "entry_low":20.0,"entry_high":21.0,"chase_limit":22.0,
        "stop":18.0,"r1":27.0,"rr_basic":2.5,"rr_severe":1.7,
        "dv30":100_000_000.0})
    ptr={"schema":"XRAY_GITHUB_DURABLE_STATE_V3",
         "authority":"GITHUB_CURRENT_POINTER","execution":"NONE",
         "real_money":"NO-GO",
         "state_json":{
           "task_id":TASK_ID,"asof_et":"2026-10-08",
           "deep_final_evidence":{
             "terminal_path":"nasdaq-xray/canonical_current_terminal.json",
             "terminal_blob_sha":"TERMINAL-SHA"},
           "delivery_keys":["exact-key"],"r92":[reg_row]}}
    assert registered_research_candidate_exact(reg_t,ptr,"2026-10-08","TERMINAL-SHA")
    for edit in (
        lambda t,p:p["state_json"]["deep_final_evidence"].update(terminal_blob_sha="DRIFT"),
        lambda t,p:p["state_json"]["delivery_keys"].clear(),
        lambda t,p:p["state_json"]["r92"][0].update(mc_class="MC_PASS_FALLBACK_WATCH"),
        lambda t,p:p["state_json"]["r92"][0].update(execution="ORDER"),
        lambda t,p:p["state_json"]["r92"][0].update(asof_et="2026-10-07"),
        lambda t,p:p.update(authority="NOT_CANONICAL"),
        lambda t,p:t["candidate_delivery_safety"].update(status="UNKNOWN"),
        lambda t,p:t["checks"].update(candidate_legal_guard_exact_binding=False),
        lambda t,p:t["sets"].update(pre_g9_tech_pass=[]),
        lambda t,p:p["state_json"]["r92"].clear(),
        lambda t,p:p["state_json"]["r92"][0].update(rr_basic=1.9),
        lambda t,p:p["state_json"]["r92"][0].update(rr_severe=1.4),
        lambda t,p:p["state_json"]["r92"][0].update(dv30=49_999_999),
        lambda t,p:p["state_json"]["r92"][0].update(entry_low=float("nan")),
        lambda t,p:p["state_json"]["r92"][0].update(stop=21),
    ):
        tbad,pbad=deepcopy(reg_t),deepcopy(ptr)
        edit(tbad,pbad)
        assert not registered_research_candidate_exact(tbad,pbad,"2026-10-08","TERMINAL-SHA")
    print("XRAY_E2E_REGISTERED_RESEARCH_PREP_SELFTEST=PASS_POSITIVE_15_NEGATIVES_NO_DEVICE_CLAIM")
    print("XRAY_E2E_SCOPE_BOUNDARY_SELFTEST=PASS_INDEPENDENT_GLOBAL_AND_LOCAL_NO_AL")
    print("XRAY_E2E_READINESS_MC_SELFTEST=PASS_POSITIVE_7_NEGATIVES")
    print("XRAY_E2E_TERMINAL_SHA_BINDING_SELFTEST=PASS_POSITIVE_5_NEGATIVES")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output")
    args=p.parse_args()
    if args.selftest:
        selftest()
    else:
        result=snapshot()
        if args.output:
            Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print("XRAY_E2E_READINESS="+("ATTESTED_TECH_CHAIN_ONLY" if result["full_e2e_research_attested"] else "BLOCKED"))
        print("XRAY_E2E_BLOCKERS="+json.dumps(result["blockers"]))
        print("XRAY_E2E_SNAPSHOT="+json.dumps(result,sort_keys=True))
