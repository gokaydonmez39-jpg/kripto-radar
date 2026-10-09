#!/usr/bin/env python3
"""Audit-only merge of exact 514-symbol SEC baseline and bounded transient retry.

No SEC API calls, no paid providers, no price or share values published.
Reconciliation changes only the shadow classification of the five originally
verified transient failures, never existing UNKNOWN/MISSING/HTTP404 records.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from sec_full_transient_retry import validate_origin,TRANSIENT
from sec_free_mc_multisymbol_pit_audit import ROOT,git_blob_sha

SCHEMA="XRAY_SEC_PIT_SHADOW_RECONCILIATION_V1"

def verify_and_reconcile(origin,recovery,mb,pb):
    m=json.loads(mb); p=json.loads(pb)
    syms=p.get("pass_symbols") or []
    if m.get("asof_et")!="2026-10-08" or p.get("asof_et")!=m["asof_et"]:
        raise ValueError("CURRENT_ASOF_FENCE_FAIL")
    if not set(syms).issubset(set(m.get("pass_symbols") or [])):
        raise ValueError("PRICE_SYMBOL_NOT_CURRENT_MASTER_PASS")
    master_sha=git_blob_sha(mb); price_sha=git_blob_sha(pb)
    allowed=validate_origin(origin,master_sha,price_sha,syms)
    if recovery.get("schema")!="XRAY_SEC_TRANSIENT_RECOVERY_SHADOW_V1":
        raise ValueError("RECOVERY_SCHEMA_BAD")
    if (recovery.get("origin_master_blob_sha")!=master_sha or
            recovery.get("origin_price_blob_sha")!=price_sha or
            recovery.get("origin_asof_et")!="2026-10-08"):
        raise ValueError("RECOVERY_SOURCE_BINDING_DRIFT")
    if (recovery.get("origin_source_scope_count")!=len(syms) or
            int(recovery.get("eligible_retry_count",-1))!=len(allowed) or
            recovery.get("eligible_retry_symbols")!=allowed):
        raise ValueError("RECOVERY_SCOPE_NOT_EXACT")
    if (recovery.get("execution")!="NONE" or recovery.get("real_money")!="NO-GO"
        or recovery.get("production_authority") is not False
        or recovery.get("c417_primary_mc_count")!=0
        or recovery.get("raw_share_counts_stored") is not False):
        raise ValueError("RECOVERY_SAFETY_INVALID")
    if recovery.get("status")!="BOUNDED_TRANSIENT_RETRY_COMPLETED":
        raise ValueError("RECOVERY_NOT_COMPLETED")
    states=recovery.get("outcomes") or {}
    if set(states)!=set(allowed):
        raise ValueError("RECOVERY_OUTCOMES_NOT_EXACT")
    if int(recovery.get("attempted",-1))>2*len(allowed):
        raise ValueError("RECOVERY_ATTEMPT_LIMIT_VIOLATION")
    merged=dict(origin["statuses"])
    new=0
    for sym,outcome in sorted(states.items()):
        if (origin["reason_codes"].get(sym)!=TRANSIENT
             or origin["statuses"].get(sym)!="UNKNOWN_SEC_TRANSPORT"):
            raise ValueError("NONTRANSIENT_RECLASSIFICATION_REJECTED")
        if outcome=="SHADOW_SHARES_VINTAGE_ONLY":
            merged[sym]=outcome
            new+=1
        elif not (outcome=="UNKNOWN" or
                 (isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))):
            raise ValueError("UNAUTHORIZED_RETRY_CLASSIFICATION")
    return {"schema":SCHEMA,"asof_et":"2026-10-08",
            "master_git_blob_sha":master_sha,"price_git_blob_sha":price_sha,
            "source_scope_count":len(syms),
            "baseline_shadow_count":sum(v=="SHADOW_SHARES_VINTAGE_ONLY" for v in origin["statuses"].values()),
            "recovered_additional_shadow_count":new,
            "consolidated_status_counts":dict(sorted(collections.Counter(merged.values()).items())),
            "unresolved_scope_count":sum(v!="SHADOW_SHARES_VINTAGE_ONLY" for v in merged.values()),
            "symbol_statuses":dict(sorted(merged.items())),
            "recovered_symbols":[x for x in allowed if merged[x]=="SHADOW_SHARES_VINTAGE_ONLY"],
            "origin_source_sha256":hashlib.sha256(json.dumps(origin,sort_keys=True).encode()).hexdigest(),
            "recovery_source_sha256":hashlib.sha256(json.dumps(recovery,sort_keys=True).encode()).hexdigest(),
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "c417_primary_mc_count":0,"production_alpha_authority":False,
            "candidate_count_attested":0,"same_asof_market_price_binding":False,
            "corporate_action_share_class_binding":False,
            "device_notification_delivered":False,"live_unattended_provider_license_attested":False}

def selftest():
    sample=["A","B","C"]
    mb=json.dumps({"asof_et":"2026-10-08","pass_symbols":sample}).encode()
    pb=json.dumps({"asof_et":"2026-10-08","pass_symbols":sample}).encode()
    ms,ps=git_blob_sha(mb),git_blob_sha(pb)
    origin={"schema":"XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1",
            "asof_et":"2026-10-08","master_git_blob_sha":ms,
            "price_git_blob_sha":ps,"execution":"NONE","real_money":"NO-GO",
            "production_alpha_authority":False,"c417_primary_mc_count":0,
            "batch_limit":3,"batch_offset":0,"sample_count":3,
            "statuses":{"A":"UNKNOWN_SEC_TRANSPORT","B":"UNKNOWN_SEC_TRANSPORT",
                        "C":"SHADOW_SHARES_VINTAGE_ONLY"},
            "reason_codes":{"A":TRANSIENT,"B":"SEC_HTTP_404",
                            "C":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED"},
            "sample_scope_sha256":hashlib.sha256("A\nB\nC\n".encode()).hexdigest()}
    rec={"schema":"XRAY_SEC_TRANSIENT_RECOVERY_SHADOW_V1",
         "origin_master_blob_sha":ms,"origin_price_blob_sha":ps,
         "origin_asof_et":"2026-10-08","origin_source_scope_count":3,
         "eligible_retry_count":1,"eligible_retry_symbols":["A"],
         "outcomes":{"A":"SHADOW_SHARES_VINTAGE_ONLY"},"attempted":1,
         "execution":"NONE","real_money":"NO-GO","production_authority":False,
         "c417_primary_mc_count":0,"raw_share_counts_stored":False,
         "status":"BOUNDED_TRANSIENT_RETRY_COMPLETED"}
    from copy import deepcopy
    result=verify_and_reconcile(origin,rec,mb,pb)
    assert result["baseline_shadow_count"]==1 and result["recovered_additional_shadow_count"]==1
    assert result["symbol_statuses"]["B"]=="UNKNOWN_SEC_TRANSPORT"
    for key,val in (("eligible_retry_symbols",["B"]),("origin_price_blob_sha","0"*40),
                    ("status","IN_PROGRESS"),("c417_primary_mc_count",1),
                    ("outcomes",{"B":"SHADOW_SHARES_VINTAGE_ONLY"})):
        bad=deepcopy(rec);bad[key]=val
        try:verify_and_reconcile(origin,bad,mb,pb)
        except ValueError:pass
        else:raise AssertionError("INVALID_RECOVERY_ADMITTED_"+key)
    print("XRAY_SEC_SHADOW_RECONCILE_SELFTEST=PASS_BOUND_EXACT_NO_PERMANENT_PROMOTION")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--origin",type=Path)
    p.add_argument("--recovery",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if not(a.origin and a.recovery and a.output):
        p.error("--origin --recovery --output required")
    root=ROOT
    report=verify_and_reconcile(json.loads(a.origin.read_text()),
        json.loads(a.recovery.read_text()),
        (root/"canonical_current_master_manifest.json").read_bytes(),
        (root/"canonical_current_price_dv30.json").read_bytes())
    if report["source_scope_count"]!=514:
        raise ValueError("FULL_514_SCOPE_NOT_PROVEN")
    a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_RECONCILED_COUNT="+str(report["baseline_shadow_count"]+
                                             report["recovered_additional_shadow_count"]))
    print("XRAY_SEC_RECONCILED_STATUS_COUNTS="+json.dumps(report["consolidated_status_counts"],sort_keys=True))
    print("XRAY_SEC_RECONCILED_PRIMARY=0_SHADOW_RESEARCH_ONLY")

if __name__=="__main__":
    main()
