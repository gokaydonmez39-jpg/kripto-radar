#!/usr/bin/env python3
"""Recompute C4.17 shadow SEC/HISTORY/MC intersection from real SEC Actions artifact.
NO licensed vendor raw prices/caps; connected-app observations are UNATTESTED.
No production changes, AL registration, C4.18 approval or device notification.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(__file__).resolve().parent
PRICE=ROOT/"canonical_current_price_dv30.json"
V2=BASE/"20261010_sec514_history514_joint_shadow_checkpoint_v2.json"
V46=BASE/"continuation_checkpoint_20261010_price514_three_source_shadow_triage_v46.json"
OFFICIAL_SEC_STATUS="SHADOW_SHARES_VINTAGE_ONLY"
ASOF="2026-10-09"
EXPECTED_SCOPE=514
EXPECTED_ARTIFACT_ID=11664626544
EXPECTED_JOIN_SHA256="043394d78aaf1fd6a0515fa136627b3bd5eb1f8b401ede63a0ea0052ad913ff0"

def git_blob(b:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()

def verify(sec,price,v2,v46,price_sha):
    errors=[]
    def check(value,reason):
        if not value: errors.append(reason)
    syms=price.get("pass_symbols")
    syms=syms if isinstance(syms,list) else []
    check(price.get("asof_et")==ASOF and len(syms)==EXPECTED_SCOPE
          and len(set(syms))==EXPECTED_SCOPE
          and price.get("pass_count")==EXPECTED_SCOPE,"PRICE_SCOPE_OR_ASOF_DRIFT")
    check(v46.get("source_price_git_blob_sha")==price_sha
          and v2.get("canonical_price",{}).get("blob_sha")==price_sha,
          "PRICE_SOURCE_SHA_DRIFT")
    official=v2.get("official_SEC_execution") or {}
    check(official.get("workflow_run_id")==38037486395
          and official.get("artifact_id")==EXPECTED_ARTIFACT_ID
          and official.get("conclusion")=="SUCCESS"
          and official.get("scope_count")==EXPECTED_SCOPE,
          "SEC_ARTIFACT_IDENTITY_INVALID")
    check(sec.get("asof_et")==ASOF
          and sec.get("price_git_blob_sha")==price_sha
          and sec.get("sample_count")==EXPECTED_SCOPE
          and sec.get("execution")=="NONE"
          and sec.get("real_money")=="NO-GO"
          and sec.get("c417_primary_mc_count")==0
          and sec.get("production_alpha_authority") is False
          and sec.get("market_cap_calculated") is False,
          "SEC_ARTIFACT_SOURCE_OR_AUTHORITY_INVALID")
    statuses=sec.get("statuses")
    statuses=statuses if isinstance(statuses,dict) else {}
    check(set(statuses)==set(syms),"SEC_514_SYMBOL_SET_MISMATCH")
    categories=set(statuses.values())
    check(categories<= {OFFICIAL_SEC_STATUS,"UNKNOWN","UNKNOWN_SEC_TRANSPORT"},
          "SEC_STATUS_ILLEGAL")
    hist=v46.get("history_alpaca_connected") or {}
    market=v46.get("mc_longbridge_connected") or {}
    missing=hist.get("incomplete_symbols") or []
    below=market.get("below_floor_symbols") or []
    check(isinstance(missing,list) and len(missing)==17
          and len(set(missing))==17 and set(missing)<=set(syms),
          "HISTORY_17_SET_INVALID")
    check(isinstance(below,list) and len(below)==16
          and len(set(below))==16 and set(below)<=set(syms),
          "MC_16_SET_INVALID")
    check(hist.get("exact_session_and_week_date_coverage")==497
          and hist.get("exchange_sessions_exact")==260
          and hist.get("weekly_last_closes_exact")==52
          and hist.get("git_runner_secret_present") is False
          and market.get("above_or_equal_existing_usd_2b_mc_floor")==498
          and market.get("asof_et_value_witness_present") is False
          and market.get("non_display_automation_license_proven") is False,
          "INTERACTIVE_SOURCE_LIMITS_NOT_EXPLICIT")
    sec_yes={sym for sym,s in statuses.items() if s==OFFICIAL_SEC_STATUS}
    hp=set(syms)-set(missing)
    mp=set(syms)-set(below)
    hp_mc=hp & mp
    sec_hp=sec_yes & hp
    triple=sec_hp & mp
    sha=hashlib.sha256(("\n".join(sorted(triple))+"\n").encode()).hexdigest()
    check(len(sec_yes)==346 and len(hp_mc)==482 and len(sec_hp)==341
          and len(triple)==330,"JOINT_COUNTS_NOT_MATCHING_SOURCE")
    check(sha==EXPECTED_JOIN_SHA256,"TRIPLE_SHA256_INVALID")
    check(v2.get("crosscheck",{}).get("sec_shares_vintage_AND_history_complete_count")==len(sec_hp)
          and v2.get("crosscheck",{}).get("production_mc_primary_count")==0,
          "PRIOR_RECORD_OR_PRIMARY_CONFLICT")
    check(v46.get("can_create_primary_mc") is False
          and v46.get("can_register_r92") is False
          and v46.get("release_status")=="RESEARCH_DIAGNOSTIC_ONLY_NO_GO",
          "UNAUTHORIZED_C4_17_PROMOTION")
    report={"schema":"XRAY_20261010_THREE_SOURCE_JOIN_SHADOW_V3",
            "asof_et":ASOF,"source_PRICE_blob_sha":price_sha,
            "sec_artifact_id":EXPECTED_ARTIFACT_ID,
            "price_pass_count":len(syms),"sec_share_vintage_count":len(sec_yes),
            "history_data_complete_shadow":len(hp),
            "connected_mc_above_2b_shadow":len(mp),
            "history_and_mc_shadow_overlap":len(hp_mc),
            "sec_history_shadow_overlap":len(sec_hp),
            "three_way_shadow_overlap":len(triple),
            "three_way_shadow_sha256":sha,
            "SEC_live_artifact_replay_executed":True,
            "connected_HISTORY_or_MC_raw_replay_executed":False,
            "market_cap_asof_licensed_primary_proven":False,
            "production_mc_primary_pass":False,
            "canonical_history_written":False,
            "candidate_r92_created":False,
            "actual_notification_delivered":False,
            "execution":"NONE","real_money":"NO-GO",
            "status":"SHADOW_COUNTS_VALIDATED_NOT_C4_17_PRIMARY" if not errors else "BLOCKED",
            "errors":sorted(set(errors))}
    return report

def selftest():
    price=json.loads(PRICE.read_text())
    v2=json.loads(V2.read_text())
    v46=json.loads(V46.read_text())
    official=v2["official_SEC_execution"]
    assert official["artifact_id"]==EXPECTED_ARTIFACT_ID
    assert price["asof_et"]==ASOF
    assert v46["source_price_git_blob_sha"]==git_blob(PRICE.read_bytes())
    # Only negative tests with fabricated data; live pass needs REAL SEC artifact.
    mock={"asof_et":ASOF,"price_git_blob_sha":git_blob(PRICE.read_bytes()),
          "sample_count":514,"execution":"NONE","real_money":"NO-GO",
          "c417_primary_mc_count":0,"market_cap_calculated":False,
          "production_alpha_authority":False,
          "statuses":{s:"UNKNOWN" for s in price["pass_symbols"]}}
    for tamper in ("base","false_mc","missing_symbol","after_asof"):
        c=copy.deepcopy(mock)
        if tamper=="false_mc": c["c417_primary_mc_count"]=1
        if tamper=="missing_symbol": c["statuses"].pop(price["pass_symbols"][0])
        if tamper=="after_asof": c["asof_et"]="2026-10-08"
        result=verify(c,price,v2,v46,git_blob(PRICE.read_bytes()))
        assert result["status"]=="BLOCKED" and result["production_mc_primary_pass"] is False, tamper
    print("XRAY_THREE_SOURCE_JOIN_SELFTEST=PASS_FOUR_NEGATIVE_NO_FAKE_SEC_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sec-artifact-json",type=Path)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.sec_artifact_json is None:
        raise SystemExit("FAIL_CLOSED_REAL_SEC_ARTIFACT_REQUIRED")
    sec=json.loads(args.sec_artifact_json.read_bytes())
    b=PRICE.read_bytes()
    result=verify(sec,json.loads(b),json.loads(V2.read_bytes()),
                  json.loads(V46.read_bytes()),git_blob(b))
    if args.out:
        args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_THREE_SOURCE_JOIN_SHADOW_STATUS="+result["status"])
    print("XRAY_THREE_SOURCE_JOIN_SHADOW_COUNT="+str(result["three_way_shadow_overlap"]))
    print("XRAY_THREE_SOURCE_JOIN_REASONS="+json.dumps(result["errors"]))
    print("XRAY_THREE_SOURCE_JOIN_PRIMARY=0_NO_R92_NO_GO")
    if result["status"]=="BLOCKED":
        raise SystemExit(2)

if __name__=="__main__":
    main()
