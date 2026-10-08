#!/usr/bin/env python3
"""Pre-open independent source proof: PASS cannot be manufactured from coverage counts.

Read-only. Uses committed exact-ASOF lineage and fail-closed E2E audit.
No market prices, ticker observations, credentials, alerts or vendor records are emitted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import Counter
import e2e_production_readiness as audit

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PREOPEN_SOURCE_AUDIT_V1"

def load(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

def inspect(master,price,req,terminal,readiness,master_sha,price_sha):
    identity_pass=master.get("pass_symbols") or []
    identity_unknown=master.get("unknown_symbols") or []
    price_pass=price.get("pass_symbols") or []
    blocked=price.get("blocked_symbols") or []
    unknown=price.get("unknown_symbols") or []
    price_details=req.get("price_unknown_detail") or {}
    reasons=Counter()
    rescue=Counter()
    for sym in blocked:
        d=(price_details.get(sym) or {}).get("price_result") or {}
        info=d.get("info") or {}
        attempt=d.get("block_recovery_attempt") or {}
        provider=attempt.get("provider_result") or {}
        reasons[str(info.get("reason") or "BLOCK_REASON_NOT_DOCUMENTED")]+=1
        rescue[str(provider.get("reason") or "RECOVERY_NOT_DOCUMENTED")]+=1
    invariants={
        "master_set_partition_exact":(
            len(identity_pass)==int(master.get("pass_count",-1))
            and len(identity_unknown)==int(master.get("unknown_count",-1))
            and len(set(identity_pass))==len(identity_pass)
            and len(set(identity_unknown))==len(identity_unknown)
            and not (set(identity_pass)&set(identity_unknown))),
        "price_pass_scope_exact":(
            set(price_pass).issubset(set(identity_pass))
            and len(set(price_pass))==len(price_pass)==int(price.get("pass_count",-1))
            and not(set(price_pass)&set(blocked))
            and not(set(price_pass)&set(unknown))
            and not(set(blocked)&set(unknown))
            and len(set(blocked))==len(blocked)==int(price.get("blocked_count",-1))
            and len(set(unknown))==len(unknown)==int(price.get("unknown_count",-1))
            and set(price.get("results") or {})==set(identity_pass)
            and len(price.get("results") or {})==len(identity_pass)
            and (set(price_pass)|set(blocked)|set(unknown)).issubset(set(identity_pass))),
        "resolver_master_git_sha_exact":req.get("source_master_blob_sha")==master_sha,
        "resolver_price_git_sha_exact":req.get("source_price_blob_sha")==price_sha
            and req.get("source_price_pass_hash")==price.get("pass_hash")
            and int(req.get("source_price_pass_count",-1))==len(price_pass),
        "same_asof_epoch":(
            bool(master.get("asof_et"))
            and master.get("asof_et")==price.get("asof_et")==req.get("asof_et")),
        "resolver_blocked_partition_exact":(
            set(req.get("price_blocked_symbols") or [])==set(blocked)
            and int(req.get("price_blocked_count",-1))==len(blocked)
            and set(price_details)==set(blocked)|set(unknown)),
        "safety_contract_exact":all(
            d.get("execution")=="NONE"
            and d.get("real_money")=="NO-GO"
            and d.get("unknown_never_pass") is True
            for d in (master,price,req,terminal)),
    }
    verified=all(invariants.values())
    mc_ok=(readiness.get("current_mc_authority_count")==1
           and "CURRENT_MC_AUTHORITY_MISSING" not in (readiness.get("blockers") or []))
    terminal_ok=(readiness.get("full_e2e_research_attested") is True
                 and terminal.get("asof_et")==master.get("asof_et"))
    # Global discovery and candidate-local readiness are *separate*.
    # Incomplete global identity must not become candidate-local PASS.
    global_complete=(verified and not identity_unknown and not blocked and not unknown)
    candidate_local_proven=(verified and mc_ok and terminal_ok)
    # Never use 514 PRICE-PASS to infer 514 MC-PASS or any AL candidate.
    return {
        "schema":SCHEMA,"asof_et":master.get("asof_et"),
        "policy":"C4.17","control":"C4.27",
        "mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "invariants":invariants,"source_integrity_pass":verified,
        "identity_pass_count":len(identity_pass),
        "identity_unknown_count":len(identity_unknown),
        "price_pass_count":len(price_pass),
        "price_blocked_count":len(blocked),
        "price_unknown_count":len(unknown),
        "price_block_reason_counts":dict(sorted(reasons.items())),
        "price_recovery_reason_counts":dict(sorted(rescue.items())),
        "full_universe_discovery_complete":global_complete,
        "current_primary_mc_proof_complete":mc_ok,
        "current_terminal_proof_complete":terminal_ok,
        "candidate_local_source_preconditions_proven":candidate_local_proven,
        "verified_live_manual_buy_candidates":0 if not candidate_local_proven else None,
        "verified_live_manual_buy_candidates_meaning":(
            "ZERO_ATTESTED_NOT_ZERO_POSSIBLE" if not candidate_local_proven
            else "NOT_ASSESSED_BY_SOURCE_AUDIT"),
        "actual_device_notification_receipt_proven":False,
        "shadow_massive_not_primary":True,
        "non_display_license_proven_by_this_audit":False,
        "bigdata_free_credit_availability_proven_by_this_audit":False,
        "research_go":False,
        "blockers":sorted(set(readiness.get("blockers") or []) |
             ({"SOURCE_PARTITION_OR_SHA_INVALID"} if not verified else set()) |
             ({"SOURCE_PRIMARY_MC_NOT_ATTESTED"} if not mc_ok else set()) |
             ({"SOURCE_CURRENT_TERMINAL_NOT_ATTESTED"} if not terminal_ok else set())),
        "disclaimer":"A workflow success means classification ran, not actionable AL, broker activity, or device delivery."
    }

def selftest():
    def d(**k):
        return dict(execution="NONE",real_money="NO-GO",unknown_never_pass=True,**k)
    m=d(asof_et="2026-10-08",pass_symbols=["A","B"],unknown_symbols=["S"],
        pass_count=2,unknown_count=1)
    p=d(asof_et="2026-10-08",pass_symbols=["A"],blocked_symbols=["B"],
        unknown_symbols=[],pass_count=1,blocked_count=1,unknown_count=0,
        pass_hash="HP",results={"A":{"status":"PASS_PRICE_DV30"},"B":{"status":"BLOCK_CURRENT_RUN"}})
    q=d(asof_et="2026-10-08",source_master_blob_sha="M",source_price_blob_sha="P",
        source_price_pass_hash="HP",source_price_pass_count=1,
        price_blocked_symbols=["B"],price_blocked_count=1,
        price_unknown_detail={"B":{"price_result":{
            "info":{"reason":"ASOF_MISSING"},
            "block_recovery_attempt":{"provider_result":{"reason":"NO_FALLBACK"}}}}})
    t=d(asof_et="2026-10-07")
    r={"current_mc_authority_count":0,"full_e2e_research_attested":False,
       "blockers":["CURRENT_MC_AUTHORITY_MISSING"]}
    base=inspect(m,p,q,t,r,"M","P")
    assert base["source_integrity_pass"]
    assert not base["full_universe_discovery_complete"]
    assert not base["candidate_local_source_preconditions_proven"]
    assert base["verified_live_manual_buy_candidates"]==0
    assert base["price_block_reason_counts"]=={"ASOF_MISSING":1}
    assert "SOURCE_PRIMARY_MC_NOT_ATTESTED" in base["blockers"]
    for a,b,ms,ps in (
        (m,{**p,"pass_symbols":["A","B"],"pass_count":2},"M","P"),
        (m,p,"DIFFERENT","P"),
        (m,p,"M","DIFFERENT"),
        (m,{**p,"blocked_count":0},"M","P"),
        (m,{**p,"results":{"A":{"status":"PASS_PRICE_DV30"}}},"M","P"),
        ({**m,"unknown_symbols":["A"]},p,"M","P"),
        (m,p,"M","P"),
    ):
        out=inspect(a,b,q,t,r,ms,ps)
        if a is m and b is p and ms=="M" and ps=="P":
            assert out==base
        else:
            assert not out["source_integrity_pass"] or not out["candidate_local_source_preconditions_proven"]
    # Globally unresolved identity does not make an independent fully-bound
    # candidate source surface invalid; still not a real AL signal.
    strong=dict(r,current_mc_authority_count=1,full_e2e_research_attested=True,blockers=[])
    result=inspect(m,p,q,{**t,"asof_et":"2026-10-08"},strong,"M","P")
    assert result["candidate_local_source_preconditions_proven"]
    assert not result["full_universe_discovery_complete"]
    assert result["verified_live_manual_buy_candidates"] is None
    assert result["research_go"] is False
    print("XRAY_PREOPEN_SOURCE_AUDIT_SELFTEST=PASS_POSITIVE_NEGATIVE_SHA_PARTITION_NO_FALSE_ALPHA")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--output")
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    master=load("canonical_current_master_manifest.json")
    price=load("canonical_current_price_dv30.json")
    req=load("canonical_current_resolver_request.json")
    terminal=load("canonical_current_terminal.json")
    data=inspect(master,price,req,terminal,audit.snapshot(),
                 audit.sha("canonical_current_master_manifest.json"),
                 audit.sha("canonical_current_price_dv30.json"))
    if args.output:
        Path(args.output).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_PREOPEN_SOURCE_INTEGRITY="+("PASS" if data["source_integrity_pass"] else "BLOCKED"))
    print("XRAY_PREOPEN_CANDIDATE_SOURCE="+("PROVEN_PRECONDITIONS_ONLY" if data["candidate_local_source_preconditions_proven"] else "BLOCKED"))
    print("XRAY_PREOPEN_FULL_UNIVERSE="+("COMPLETE" if data["full_universe_discovery_complete"] else "INCOMPLETE"))
    print("XRAY_PREOPEN_BLOCKERS="+json.dumps(data["blockers"],sort_keys=True))

if __name__=="__main__":
    main()
