#!/usr/bin/env python3
"""Exact 2026-10-09 515 dual-history vs corporate-action issuer risk.

Reads two independently completed original GitHub Actions sanitized
artifacts. Proves SET partition, not count-only equality: 497 full-history
NASDAQ stocks, 17 official short; among the 497, 31 have Alpaca-reported
NON-SPLIT corporate-action event types and 466 have no such type observed.
This is a triage queue, NOT evidence that no corporate action ever occurred,
not independent issuer/PIT/stock-class/ADR rights, no HISTORY PRIMARY, MC
PRIMARY, R92, AL, real money, or GO.
"""
from __future__ import annotations
import argparse,copy,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_497_31_466_CA_LOCAL_RISK_PARTITION_SHADOW_V1"
SOURCE_PRICE="canonical_current_price_dv30.json"
SOURCE_MASTER="canonical_current_master_manifest.json"
FULL="SHADOW_260_DAILY_52_WEEK_OBSERVED"

def require(ok,why):
    if not ok:raise ValueError("XRAY_HISTORY_497_CA_PARTITION:"+why)

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def classify(dual,ca,pbytes,mbytes):
    price=json.loads(pbytes);master=json.loads(mbytes)
    asof=price.get("asof_et")
    require(asof=="2026-10-09" and asof==master.get("asof_et")
            and asof==dual.get("asof_et")==ca.get("asof_et"),
            "EXACT_ASOF_2026_10_09_NOT_SHARED")
    require(price.get("execution")==master.get("execution")=="NONE"
            and price.get("real_money")==master.get("real_money")=="NO-GO",
            "UNSAFE_CANONICAL_SOURCE")
    require(dual.get("schema")=="XRAY_ALPACA_515_DUAL_RAW_SPLIT_SHADOW_V1"
            and ca.get("schema")=="XRAY_ALPACA_515_CORPORATE_ACTIONS_CENSUS_SHADOW_V1"
            and dual.get("status")=="SHADOW_DUAL_ADJUSTMENT_SCOPE_MEASURED_NO_PIT_AUTHORITY"
            and ca.get("status")=="SHADOW_SCOPE_COMPLETE_CA_NOT_PIT",
            "SOURCE_SCHEMA_OR_STATUS_INVALID")
    sha_price=blob(pbytes);sha_master=blob(mbytes)
    for source in (dual,ca):
        require(source.get("source_price_blob_sha")==sha_price
                and source.get("source_master_blob_sha")==sha_master,
                "SOURCE_GIT_BLOB_MISMATCH")
    require(dual.get("source_price_pass_hash")==price.get("pass_hash")
            and ca.get("source_price_pass_hash")==price.get("pass_hash")
            and price.get("pass_count")==514
            and ca.get("source_price_count")==514
            and dual.get("scope_with_qqq")==ca.get("expected_symbols")==515
            and dual.get("measured_scope")==ca.get("measured_symbols")==515
            and ca.get("symbol_local_CA_registry_completed") is True
            and ca.get("unknown_vendor_group_events")==ca.get("subject_not_in_requested_batch")==0,
            "FULL_SCOPE_OR_CA_SCHEMA_INCOMPLETE")
    dual_symbols=dual.get("source_symbol_statuses")
    require(type(dual_symbols) is dict and set(dual_symbols)==
            (set(price["pass_symbols"])|{"QQQ"}),
            "DUAL_BAR_SYMBOL_SET_MISMATCH")
    full={s for s,e in dual_symbols.items()
          if e.get("raw_calendar_classification")==FULL}
    short=set(dual_symbols)-full
    require(len(full)==498 and len(short)==17 and "QQQ" in full,
            "260_52_EXACT_SYMBOL_SETS_UNVERIFIED")
    for sym in dual_symbols:
        require(dual_symbols[sym].get("raw_calendar_classification")==
                dual_symbols[sym].get("split_calendar_classification"),
                "RAW_SPLIT_SESSIONS_DIFFER_"+sym)
    ca_ledger=ca.get("symbol_local_CA_type_ledger")
    non_split=ca.get("symbol_local_non_split_review")
    require(type(ca_ledger) is dict and type(non_split) is dict
            and len(non_split)==ca.get("symbol_local_non_split_review_count")
            and len(ca_ledger)==ca.get("symbol_local_CA_affected_count")
            and set(non_split).issubset(set(ca_ledger))
            and set(ca_ledger).issubset(set(dual_symbols)),
            "CORPORATE_EVENT_SYMBOL_SET_DRIFT")
    require(ca.get("total_events_seen")==859
            and ca.get("non_cash_dividend_events")==56,
            "OFFICIAL_VENDOR_EVENT_COUNT_DRIFT")
    require(dual.get("production_HISTORY_PASS_created")==0
            and dual.get("C417_PRIMARY_MC_created")==0
            and dual.get("GO") is False
            and ca.get("canonical_pass_created")==0
            and ca.get("current_c417_history_primary_authority") is False
            and ca.get("independent_issuer_corporate_actions_reconciled") is False,
            "SHADOW_WITNESS_MUST_NOT_BE_PRIMARY")
    full_stocks=full-{"QQQ"}
    affected=full_stocks&set(non_split)
    short_affected=short&set(non_split)
    unchanged=full_stocks-affected
    split_changed=set(dual["numeric_restatement_symbols"])
    require(len(full_stocks)==497 and len(affected)==31
            and len(unchanged)==466 and len(short_affected)==6
            and len(split_changed)==11 and
            len(split_changed&affected)==4 and
            len((full_stocks-split_changed)&affected)==27
            and len(set(non_split))==37,
            "EXACT_497_31_466_17_PARTITION_FAILED")
    no_noncash={sym for sym in full_stocks if not
                ca_ledger.get(sym,{}).get("has_non_cash_CA",False)}
    require(len(no_noncash)==458,"NO_NONCASH_OBSERVED_COHORT_DRIFT")
    return {"schema":SCHEMA,"asof_et":asof,
            "source_price_blob_sha":sha_price,
            "source_master_blob_sha":sha_master,
            "source_515_raw_split_run":38178676524,
            "source_515_CA_symbol_local_run":38181356461,
            "status":"SHADOW_CA_NON_SPLIT_RESIDUAL_EXACTLY_LOCALIZED",
            "total_target_with_QQQ":len(dual_symbols),
            "stock_scope":len(full_stocks|short),
            "full_history_stock_count":len(full_stocks),
            "short_history_official_age_count":len(short),
            "full_history_no_non_split_event_observed":len(unchanged),
            "full_history_non_split_CA_review_required":len(affected),
            "full_history_non_split_review_symbols":sorted(affected),
            "official_short_with_non_split_CA":len(short_affected),
            "official_short_non_split_CA_symbols":sorted(short_affected),
            "split_ratio_replay_stocks":len(split_changed),
            "split_replay_also_non_split_CA_affected":len(split_changed&affected),
            "no_non_cash_CA_observed_stock_count":len(no_noncash),
            "CA_event_census_count":ca["total_events_seen"],
            "CA_event_noncash_count":ca["non_cash_dividend_events"],
            "no_event_observed_is_not_official_absence_evidence":True,
            "independent_issuer_non_split_CA_asof_PIT_attested":False,
            "single_shareclass_and_CUSIP_lineage_attested":False,
            "production_C417_PRIMARY_MC_created":0,
            "production_HISTORY_PASS_created":0,
            "can_register_R92":False,"GO":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest(dual,ca,pbytes,mbytes):
    positive=classify(dual,ca,pbytes,mbytes)
    require(positive["full_history_non_split_CA_review_required"]==31,
            "REAL_POSITIVE_NOT_31")
    def red(label,d=dual,c=ca,p=pbytes,m=mbytes):
        try:classify(d,c,p,m)
        except ValueError:return
        raise AssertionError("FALSE_CA_HISTORY_PASS:"+label)
    x=copy.deepcopy(dual);x["source_price_blob_sha"]="0"*40
    red("PRICE_BLOB_TAMPER",d=x)
    x=copy.deepcopy(ca);x["source_master_blob_sha"]="0"*40
    red("MASTER_BLOB_TAMPER",c=x)
    x=copy.deepcopy(ca);x["symbol_local_non_split_review_count"]=0
    red("FALSE_NON_SPLIT_ZERO",c=x)
    x=copy.deepcopy(ca);x["independent_issuer_corporate_actions_reconciled"]=True
    red("FALSE_ISSUER_PIT_AUTHORITY",c=x)
    x=copy.deepcopy(dual);x["production_HISTORY_PASS_created"]=497
    red("FALSE_PRODUCTION_HISTORY_PASS",d=x)
    print("XRAY_P0_497_NON_SPLIT_CA_PARTITION=PASS_REAL_1_POSITIVE_5_NEGATIVE_PYTHON_O")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dual",type=Path,required=True)
    ap.add_argument("--ca",type=Path,required=True)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    d=json.loads(args.dual.read_text());c=json.loads(args.ca.read_text())
    p=(ROOT/SOURCE_PRICE).read_bytes();m=(ROOT/SOURCE_MASTER).read_bytes()
    if args.selftest:return selftest(d,c,p,m)
    require(args.out is not None,"EXPLICIT_OUTPUT_REQUIRED")
    result=classify(d,c,p,m)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_497_NON_SPLIT_CA_P0="+result["status"])
    print("XRAY_497_NON_SPLIT_CA_COUNTS="+json.dumps({
      k:result[k] for k in ("full_history_stock_count",
       "full_history_no_non_split_event_observed",
       "full_history_non_split_CA_review_required",
       "short_history_official_age_count")},sort_keys=True))
    print("XRAY_HISTORY_MC_PRIMARY_CREATED=0")

if __name__=="__main__":main()
