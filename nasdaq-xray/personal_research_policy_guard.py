#!/usr/bin/env python3
"""Fail-closed personal-research technical-source policy validator.

This module does not alter canonical C4.17 market-data semantics, issue a
broker order, or create an R92 candidate. Personal use is not evidence of
unrestricted network automation or exchange-feed entitlements.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PERSONAL=ROOT/"personal_research_technical_policy_v1.json"
COMPILED=ROOT/"chatgpt_compiled_policy_v3.json"

def require(value,reason):
    if not value:
        raise ValueError("XRAY_PERSONAL_POLICY_"+reason)

def check(personal,compiled):
    p=json.loads(compiled["payload_json"])
    gates=p["hard_gates"]
    require(personal.get("schema")=="XRAY_PERSONAL_RESEARCH_TECHNICAL_AUTHORITY_V1","SCHEMA")
    require(personal.get("parent_compiled_policy")=="C4.17" and
            personal.get("activation")=="RESEARCH_OUTPUT_ONLY_NOT_PRODUCTION_SWITCH","ISOLATION")
    require(personal.get("research_use")=="PERSONAL_NONCOMMERCIAL_NO_RESALE","USE")
    require(personal.get("no_waiver_of_upstream_contract_or_feed_terms") is True and
            personal.get("persist_raw_vendor_ohlcv") is False,"TERMS_AND_RAW")
    require(all(personal.get(k) is False for k in
            ("can_update_compiled_C417_alpha","can_override_canonical_unknown",
             "can_create_r92","can_set_true_full_go")),"NO_PROMOTION")
    require(personal.get("execution")=="NONE" and personal.get("real_money")=="NO-GO"
            and personal.get("unknown_never_pass") is True,"NO_EXECUTION")
    require(p["execution"]=="NONE" and p["real_money"]=="NO-GO","COMPILED_SAFETY")
    require(personal.get("price_min_usd")==5 and gates["price"]==">=5","PRICE_THRESHOLD")
    require(personal.get("dv30_usd_min")==50000000 and
            "50000000" in gates["dv30"] and
            "exactly30" in gates["dv30"],"DV30_THRESHOLD")
    require(personal.get("mc_usd_min")==2000000000 and
            gates["market_cap"]==">=2000000000 USD","MC_THRESHOLD")
    require(personal.get("history_days_min")==260 and
            gates["daily_history"]==">=260 completed","DAILY_HISTORY")
    require(personal.get("history_completed_weeks_min")==52 and
            gates["weekly_history"]==">=52 completed","WEEKLY_HISTORY")
    require(personal.get("exact_sessions_for_dv30")==30,"EXACT_SESSIONS")
    require(personal.get("non_display_enterprise_grant_required_for_local_personal_technical_label") is False
            and "Only within actually granted" in personal.get("source_usage_limit",""),
            "LICENSE_RESEARCH_SEPARATION")
    return {"schema":"XRAY_PERSONAL_POLICY_VALIDATION_V1",
            "policy_hash_sha256":hashlib.sha256(PERSONAL.read_bytes()).hexdigest(),
            "compiled_policy_sha256":hashlib.sha256(COMPILED.read_bytes()).hexdigest(),
            "technical_research_policy_valid":True,
            "canonical_c417_changed":False,"canonical_r92_enabled":False,
            "enterprise_rights_waived":False,"execution":"NONE","real_money":"NO-GO"}

def selftest(personal,compiled):
    good=check(personal,compiled)
    require(good["technical_research_policy_valid"] is True,"POSITIVE")
    cases=[
      ("PRICE",lambda d:d.update(price_min_usd=4.99)),
      ("DV30",lambda d:d.update(dv30_usd_min=49000000)),
      ("MC",lambda d:d.update(mc_usd_min=1999999999)),
      ("DAILY",lambda d:d.update(history_days_min=259)),
      ("WEEKLY",lambda d:d.update(history_completed_weeks_min=51)),
      ("R92",lambda d:d.update(can_create_r92=True)),
      ("CANONICAL",lambda d:d.update(can_update_compiled_C417_alpha=True)),
      ("UNKNOWN",lambda d:d.update(unknown_never_pass=False)),
      ("AUTOTRADE",lambda d:d.update(execution="AUTO")),
      ("TERMS",lambda d:d.update(no_waiver_of_upstream_contract_or_feed_terms=False)),
      ("RAW",lambda d:d.update(persist_raw_vendor_ohlcv=True)),
      ("PERSONAL_SCOPE",lambda d:d.update(research_use="COMMERCIAL_RESALE"))]
    for label,change in cases:
        invalid=copy.deepcopy(personal)
        change(invalid)
        try:check(invalid,compiled)
        except ValueError:continue
        raise AssertionError("FALSE_PASS_"+label)
    print("XRAY_PERSONAL_POLICY_SELFTEST=PASS_12_NEGATIVE_RESEARCH_ONLY")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--out",type=Path)
    args=a.parse_args()
    personal=json.loads(PERSONAL.read_text())
    compiled=json.loads(COMPILED.read_text())
    if args.selftest:
        require(args.out is None,"SELFTEST_WRITE")
        selftest(personal,compiled)
        return
    require(args.out is not None and not
            args.out.resolve().is_relative_to(ROOT.parent.resolve()),"OUTPUT_LOCATION")
    args.out.write_text(json.dumps(check(personal,compiled),sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_POLICY=PASS_NO_CANONICAL_OR_R92_PROMOTION")

if __name__=="__main__":
    main()
