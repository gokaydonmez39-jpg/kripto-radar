#!/usr/bin/env python3
"""C4.18 candidate policy integrity and activation safety gate.

Does not query/persist market data, alter the active policy, or issue an AL.
Operator approval to investigate a successor is NOT provider license.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY=ROOT/"source_successor_c418_proposal.json"
SCHEMA="XRAY_SOURCE_SUCCESSOR_POLICY_PROPOSAL_V1"
CANARY="C4.18-SOURCE-SUCCESSOR-PROPOSAL"
REQUIRED_SOURCE_NAMES={"Bigdata","Massive","SEC_EDGAR","NASDAQ","Alpaca","Yahoo_AKShare_Eastmoney"}
REQUIRED={ 
    "PROVIDER_SIGNED_NONDISPLAY_LICENSE_FOR_UNATTENDED_GITHUB_RUNNER",
    "LICENSE_HAS_PRICE_DERIVATION_INTERNAL_STORAGE_RETENTION_AND_OUTPUT_SCOPE",
    "SEC_CIK_TICKER_EXCHANGE_SHARE_CLASS_PIT_CONTINUITY_PROOF",
    "SHARES_OUTSTANDING_CLASS_CORPORATE_ACTIONS_SAME_EPOCH_RECONCILIATION",
    "INDEPENDENT_SECOND_PROVIDER_SAME_ASOF_MC_CROSSCHECK_WITH_LICENSE",
    "HISTORY_260_LAST_OFFICIAL_EXCHANGE_SESSIONS_AND_52_COMPLETED_WEEKS",
    "ALL_CANONICAL_SOURCE_BLOB_SHA_ASOF_SCOPE_HASH_EXACT",
    "NEW_C418_POLICY_HASH_OPERATOR_REVIEW_AND_ROLLBACK_PLAN",
    "UNALTERED_RISK_RR_EARNINGS_LEGAL_AND_DELIVERY_GATES",
    "PRODUCTION_GITHUB_ACTIONS_POSITIVE_AND_NEGATIVE_EVIDENCE"
}
THRESHOLDS={
    "min_market_cap_usd":2000000000,"min_price_usd":5,
    "min_dv30_usd":50000000,"min_daily_complete_sessions":260,
    "min_weekly_completed":52,"min_rr_basic":2,"min_rr_severe":1.5
}
UNATTESTED_FLAGS=(
 "automated_runner_entitlement_verified","non_display_scope_verified",
 "corporate_actions_interval_complete_verified",
 "independent_same_asof_crosscheck_verified",
 "source_exhaustive_universe_scope_verified"
)

def inspect(p):
    errors=[]
    def require(ok,reason):
        if not ok: errors.append(reason)
    if not isinstance(p,dict):
        return {"status":"REJECTED_INVALID_POLICY","errors":["NOT_AN_OBJECT"],
                "production_active":False,"can_register_R92":False}
    require(p.get("schema")==SCHEMA,"SCHEMA_INVALID")
    require(p.get("candidate_version")==CANARY,"CANDIDATE_VERSION_INVALID")
    require(p.get("predecessor")=="C4.17" and p.get("control")=="C4.27","PREDECESSOR_INVALID")
    require(p.get("effective_production_policy")=="C4.17","C417_ACTIVE_POLICY_DRIFT")
    require(p.get("activation_status")=="PROPOSED_NOT_ACTIVATED","ACTIVATION_UNAUTHORIZED")
    require(p.get("explicit_source_promotion_authorized") is False,"PRIMARY_PROMOTION_FORBIDDEN")
    require(p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
            and p.get("mode")=="RESEARCH_ONLY_MANUAL_DECISION","EXECUTION_SAFETY_INVALID")
    require(p.get("unknown_never_pass") is True and
            p.get("alpha_thresholds_unchanged") is True,"UNKNOWN_OR_ALPHA_DRIFT")
    require(p.get("numeric_thresholds")==THRESHOLDS,"FROZEN_THRESHOLDS_DRIFT")
    s=p.get("sources")
    names=[row.get("name") for row in s if isinstance(row,dict)] if isinstance(s,list) else []
    require(len(names)==len(REQUIRED_SOURCE_NAMES) and set(names)==REQUIRED_SOURCE_NAMES,
            "SOURCE_UNIVERSE_OR_DUPLICATE_INVALID")
    require(set(p.get("approval_required_for_activation") or [])==REQUIRED
            and len(p.get("approval_required_for_activation") or [])==len(REQUIRED),
            "ACTIVATION_EVIDENCE_CLAUSES_DRIFT")
    for name in UNATTESTED_FLAGS:
        require(p.get(name) is False,"UNVERIFIED_SOURCE_ASSUMED_TRUE:"+name)
    require(p.get("rights_grant_document_sha256") is None
            and p.get("secondary_provider_rights_sha256") is None,
            "UNVERIFIED_LICENSE_CLAIM_INSERTED")
    require(p.get("can_register_R92") is False and
            p.get("can_create_PRIMARY") is False,"CANONICAL_PROMOTION_FORBIDDEN")
    require(p.get("new_customer_payment_authorized") is False,"PAYMENT_CHANGE_FORBIDDEN")
    require(p.get("rollback")=="KEEP_C4.17_ACTIVE_AND_DISABLE_C4.18_ON_ANY_SOURCE_DRIFT_LICENSE_UNKNOWN_OR_TEST_FAIL",
            "ROLLBACK_REMOVED")
    require(p.get("source_role_separation",{}).get("none_default")
            =="UNKNOWN_SOURCE_NOT_LICENSED_OR_NOT_ATTESTED","UNKNOWN_DEFAULT_MISSING")
    return {
        "schema":"XRAY_C418_SOURCE_POLICY_PREFLIGHT_V1",
        "status":"PROPOSED_FAIL_CLOSED" if not errors else "REJECTED_INVALID_POLICY",
        "errors":sorted(set(errors)),
        "production_active":False,
        "policy_can_activate":False,
        "can_create_PRIMARY":False,
        "can_register_R92":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
        "licensed_market_data_exported":False,
        "policy_sha256":hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    }

def selftest(p):
    good=inspect(p)
    assert good["status"]=="PROPOSED_FAIL_CLOSED",good
    assert good["errors"]==[] and not good["policy_can_activate"]
    assert all(good[k] is False for k in ("production_active","can_create_PRIMARY","can_register_R92","licensed_market_data_exported"))
    badcases=[
      ("activation_status","ACTIVE"),("effective_production_policy","C4.18"),
      ("explicit_source_promotion_authorized",True),
      ("execution","REAL"),("real_money","GO"),
      ("unknown_never_pass",False),("alpha_thresholds_unchanged",False),
      ("can_create_PRIMARY",True),("can_register_R92",True),
      ("new_customer_payment_authorized",True),
      ("automated_runner_entitlement_verified",True),
      ("rights_grant_document_sha256","f"*64),
      ("approval_required_for_activation",[]),
      ("sources",[]),("rollback","DISABLED")
    ]
    for key,value in badcases:
        z=copy.deepcopy(p);z[key]=value
        result=inspect(z)
        assert result["status"]=="REJECTED_INVALID_POLICY",(key,result)
        assert result["production_active"] is False
        assert result["can_register_R92"] is False
    z=copy.deepcopy(p);z["numeric_thresholds"]["min_rr_basic"]=1
    assert inspect(z)["status"]=="REJECTED_INVALID_POLICY"
    z=copy.deepcopy(p);z["numeric_thresholds"]["min_market_cap_usd"]=100000000
    assert inspect(z)["status"]=="REJECTED_INVALID_POLICY"
    assert inspect({})["status"]=="REJECTED_INVALID_POLICY"
    assert inspect(None)["status"]=="REJECTED_INVALID_POLICY"
    print("XRAY_C418_PREFLIGHT_SELFTEST=PASS_POSITIVE_19_NEGATIVE_ZERO_PRODUCTION_AUTHORITY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    if args.selftest:selftest(p)
    result=inspect(p)
    if args.out:
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    if result["status"]!="PROPOSED_FAIL_CLOSED":
        print("XRAY_C418_POLICY_PREFLIGHT=INVALID_FAIL_CLOSED errors="+",".join(result["errors"]))
        raise SystemExit(2)
    print("XRAY_C418_POLICY_PREFLIGHT=VALID_PROPOSAL_NOT_ACTIVE")
    print("XRAY_C418_CAN_CREATE_PRIMARY=false")
    print("XRAY_C418_CAN_REGISTER_R92=false")

if __name__=="__main__":
    main()
