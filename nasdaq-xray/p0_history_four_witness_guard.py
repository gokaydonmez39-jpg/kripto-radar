#!/usr/bin/env python3
"""4-witness exact 497-stock HISTORY CA/split research consolidation.

Four independently-run *sanitized* GitHub Actions artifacts:
  515 Alpaca exact260 SIP, 515 raw+split, 515 CA event census, 11 split events.
Validates source-set equality and original production official-listing fail-only
from p0_history_official_reconciliation.audit. Does NOT persist vendor OHLCV,
invent completed weeks, create canonical HISTORY PASS, PRIMARY MC, R92 or GO.
"""
from __future__ import annotations
import argparse,copy,hashlib,json
from pathlib import Path

from p0_history_official_reconciliation import audit as official_history_audit
from alpaca_free_sip_shadow_guard import blob_sha
from alpaca_full_scope_260_shadow import scope,PRICE,MASTER

ROOT=Path(__file__).resolve().parent
REG=ROOT/"history_official_identity_evidence.json"
SCHEMA="XRAY_P0_HISTORY_497_4_SOURCE_SYNCHRONIZED_SHADOW_V1"

def require(ok,why):
    if not ok:raise ValueError("P0_497_HISTORY_FOUR_WITNESSES:"+why)

def audit(full,dual,ca,bridge):
    pb=PRICE.read_bytes()
    mb=MASTER.read_bytes()
    price=json.loads(pb);master=json.loads(mb)
    asof,targets,daily,weeks=scope(price,master)
    prod=official_history_audit(price,master,full,json.loads(REG.read_text()),pb,mb)
    require(prod["classification"]=="RECONCILED_OBSERVATION_SHADOW_NOT_PRODUCTION",
            "OFFICIAL_17_NOT_VERIFIED")
    require(prod["full_scope_with_qqq"]==len(targets) and
            prod["official_listing_ineligible"]==17 and
            prod["observed_exact_260_52"]==498 and
            len(targets)==515,"SOURCE_515_PARTITION_CHANGED")
    psha=blob_sha(PRICE);msha=blob_sha(MASTER)
    for name,doc,pfield,mfield in (
        ("DUAL",dual,"source_price_blob_sha","source_master_blob_sha"),
        ("CORPORATE_ACTIONS",ca,"source_price_blob_sha","source_master_blob_sha"),
        ("EVENT_BRIDGE",bridge,"source_price_blob_sha","source_master_blob_sha")):
        require(doc.get("asof_et")==asof and
                doc.get(pfield)==psha and doc.get(mfield)==msha and
                doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO",
                "SOURCE_SHA_OR_ASOF_DRIFT_"+name)
    require(dual.get("schema")=="XRAY_ALPACA_515_DUAL_RAW_SPLIT_SHADOW_V1"
            and dual.get("status")=="SHADOW_DUAL_ADJUSTMENT_SCOPE_MEASURED_NO_PIT_AUTHORITY"
            and dual.get("scope_with_qqq")==515
            and dual.get("measured_scope")==515
            and dual.get("ticker_identity_mapping_asof_et")==asof
            and dual.get("unresolved_symbols")=={}
            and dual.get("production_HISTORY_PASS_created")==0
            and dual.get("C417_PRIMARY_MC_created")==0
            and dual.get("R92_created") is False
            and dual.get("GO") is False,"DUAL_ADJUSTMENT_SOURCE_INVALID")
    dstatus=dual.get("source_symbol_statuses")
    require(isinstance(dstatus,dict) and set(dstatus)==set(targets),
            "DUAL_SYMBOL_SET_DRIFT")
    full_h={sym for sym,row in dstatus.items()
            if row.get("raw_calendar_classification")=="SHADOW_260_DAILY_52_WEEK_OBSERVED"}
    short_h=set(targets)-full_h
    official_short=set(prod["official_listing_ineligible_symbols"])
    require(len(full_h)==498 and len(short_h)==17
            and short_h==official_short and "QQQ" in full_h
            and "QQQ" not in short_h,
            "LATEST_260_52_SET_NOT_OFFICIAL_PARTITION")
    for sym in targets:
        require(dstatus[sym].get("split_calendar_classification")==
                dstatus[sym].get("raw_calendar_classification"),
                "SPLIT_CHANGED_OFFICIAL_SESSION_SET_"+sym)
    changed=set(dual.get("numeric_restatement_symbols") or [])
    require(len(changed)==dual.get("numeric_restatement_count")==11
            and changed.issubset(full_h-{"QQQ"}),
            "CHANGED_SPLIT_SYMBOLS_NOT_ELIGIBLE")
    for sym in targets:
        expected=("SHADOW_SPLIT_RESTATEMENT_NUMERICALLY_CONSISTENT"
                  if sym in changed else "SHADOW_NO_RESTATEMENT_SEEN")
        require(dstatus[sym]["dual_classification"]==expected,
                "INVALID_NUMERIC_RESTATEMENT_CLASS_"+sym)
    require(ca.get("schema")=="XRAY_ALPACA_515_CORPORATE_ACTIONS_CENSUS_SHADOW_V1"
            and ca.get("status")=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT"
            and ca.get("expected_symbols")==515 and ca.get("measured_symbols")==515
            and ca.get("source_price_pass_hash")==price.get("pass_hash")
            and ca.get("source_price_count")==price["pass_count"]
            and ca.get("unknown_vendor_group_events")==0
            and ca.get("subject_not_in_requested_batch")==0
            and ca.get("total_events_seen")==sum((ca.get("counts_by_group") or {}).values())
            and ca.get("provider_publication_time_attested") is False
            and ca.get("independent_issuer_corporate_actions_reconciled") is False
            and ca.get("canonical_pass_created")==0
            and ca.get("r92_created") is False,"CORPORATE_ACTIONS_CENSUS_INVALID")
    require(bridge.get("schema")=="XRAY_P0_SPLIT_EVENT_RESTATEMENT_BRIDGE_SHADOW_V1"
            and bridge.get("status")=="SAME_PROVIDER_EVENT_EXISTENCE_RESEARCH_ONLY"
            and bridge.get("source_raw_split_run_id")==38178676524
            and bridge.get("numerically_restated_symbols")==11
            and bridge.get("full_515_raw_split_measured")==515
            and set(bridge.get("actual_changed_symbols") or [])==changed
            and set(bridge.get("correlations") or {})==changed
            and all(row.get("status")=="SHADOW_MATCHED_SPLIT_CA_EVENT"
                    and type(row.get("split_ca_count")) is int and row["split_ca_count"]>=1
                    for row in bridge["correlations"].values())
            and bridge.get("can_create_HISTORY_PASS") is False
            and bridge.get("can_create_C417_PRIMARY_MC") is False
            and bridge.get("can_register_R92") is False
            and bridge.get("GO") is False,
            "SPLIT_EVENT_BRIDGE_NOT_PROVEN")
    complete_stocks=full_h-{"QQQ"}
    return {
        "schema":SCHEMA,"asof_et":asof,
        "status":"SHADOW_497_STOCKS_11_SPLIT_CONFIRMED_PROVIDER_17_OFFICIAL_TOO_YOUNG",
        "source_price_blob_sha":psha,"source_master_blob_sha":msha,
        "source_price_pass_hash":price["pass_hash"],
        "source_alpaca_sip_515_run_id":38178518447,
        "source_raw_split_515_run_id":38178676524,
        "source_ca_515_run_id":38178327791,
        "source_split_event_11_run_id":38178886981,
        "scope_with_qqq":len(targets),
        "stock_scope":len(targets)-1,
        "full_260_52_stock_count":len(complete_stocks),
        "qqq_full_benchmark":True,
        "official_IPO_too_young_count":len(short_h),
        "full_260_stocks_numeric_split_restated":len(changed),
        "full_260_stocks_no_split_restatement_seen":len(complete_stocks-changed),
        "split_restated_stock_symbols":sorted(changed),
        "split_event_match_same_provider":len(changed),
        "corp_action_census_event_count":ca["total_events_seen"],
        "corp_action_census_non_cash_dividend_count":ca["non_cash_dividend_events"],
        "raw_adjusted_ohlcv_or_corporate_actions_persisted":False,
        "historical_issuer_security_class_and_CA_independent_PIT":False,
        "licensed_unattended_stock_history_rights_independently_attested":False,
        "production_canonical_history_pass_created":0,
        "production_C417_primary_mc_pass_created":0,
        "can_register_R92":False,"GO":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True
    }

def selftest(full,dual,ca,bridge):
    ans=audit(full,dual,ca,bridge)
    require((ans["stock_scope"],ans["full_260_52_stock_count"],
             ans["full_260_stocks_numeric_split_restated"],
             ans["full_260_stocks_no_split_restatement_seen"],
             ans["official_IPO_too_young_count"])==(514,497,11,486,17),
            "EXACT_REAL_SOURCE_PARTITION")
    mutations=[
        ("CA_BAD_SOURCE_SHA","ca","source_price_blob_sha","0"*40),
        ("CA_FALSE_PIT","ca","independent_issuer_corporate_actions_reconciled",True),
        ("RAW_SOURCE_WRONG_ASOF","dual","asof_et","2026-10-08"),
        ("RAW_FALSE_HISTORY_PRIMARY","dual","production_HISTORY_PASS_created",1),
        ("BRIDGE_BOGUS_NO_CA","bridge","status","PRIMARY_GO"),
        ("BRIDGE_FALSE_AUTHORITY","bridge","can_create_HISTORY_PASS",True),
        ("HISTORY_FALSE_LICENSE","full","source_market_data_rights_independently_attested",True)
    ]
    for name,group,key,value in mutations:
        args={"full":copy.deepcopy(full),"dual":copy.deepcopy(dual),
              "ca":copy.deepcopy(ca),"bridge":copy.deepcopy(bridge)}
        args[group][key]=value
        try:audit(**args)
        except ValueError:pass
        else:raise AssertionError("FOUR_WITNESS_FALSE_PASS:"+name)
    print("XRAY_P0_497_FOUR_WITNESS=PASS_REAL_SOURCE_7_NEGATIVE_PYTHON_O_SAFE_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    for name in ("full","dual","ca","bridge"):
        ap.add_argument("--"+name,required=True,type=Path)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    docs={k:json.loads(getattr(a,k).read_text()) for k in ("full","dual","ca","bridge")}
    if a.selftest:return selftest(**docs)
    require(a.out is not None,"EXPLICIT_OUTPUT_REQUIRED")
    d=audit(**docs)
    a.out.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
    print("XRAY_497_FOUR_WITNESS_STATUS="+d["status"])
    print("XRAY_497_FOUR_WITNESS_COUNTS="+json.dumps({
        k:d[k] for k in (
        "stock_scope","full_260_52_stock_count",
        "full_260_stocks_numeric_split_restated",
        "full_260_stocks_no_split_restatement_seen",
        "official_IPO_too_young_count")},sort_keys=True))
    print("XRAY_497_HISTORY_PRIMARY=0_RESEARCH_ONLY")

if __name__=="__main__":main()
