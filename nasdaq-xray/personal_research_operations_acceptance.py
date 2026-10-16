#!/usr/bin/env python3
"""Three-artifact independent personal NASDAQ research readiness receipt.

Never an AL or C4.17 final release. Reconcile exact same-ASOF causal,
symbolic A/B/D WATCH and frozen secondary SEC identity evidence. No vendor
OHLCV, private account, order execution, or claimed phone delivery.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re
from pathlib import Path
from collections import Counter

SCHEMA="XRAY_PERSONAL_RESEARCH_OPERATIONS_ACCEPTANCE_V1"
CAUSAL="XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1"
WATCH="XRAY_PERSONAL_FULL_COHORT_EARLY_TECH_WATCH_V1"
MIRROR="XRAY_PERSONAL_SEC_ASOF_MIRROR_414_DISCOVERY_RESEARCH_V1"
TECH="TECHNICAL_WATCH_OBSERVED_RESEARCH_NOT_AL"
CIK="MIRROR_EXACT_ASOF_SEC_TICKER_CIK_DISCOVERY_NOT_OFFICIAL_ATTESTATION"
SYMBOL=re.compile(r"[A-Z][A-Z0-9.-]{0,9}")
SHA40=re.compile(r"[0-9a-f]{40}")
CIK10=re.compile(r"[0-9]{10}")
def need(x,why):
    if not x:raise ValueError("XRAY_RESEARCH_ACCEPTANCE_"+why)
def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,
                  separators=(",",":")).encode()).hexdigest()
def symbols_digest(names):
    return hashlib.sha256("\n".join(names).encode()).hexdigest()
def valid_set(names):
    return type(names) is list and names==sorted(set(names)) and all(
        type(n) is str and SYMBOL.fullmatch(n) is not None for n in names)
def reconcile(c,w,m,*,source_run_id,watch_run_id,mirror_run_id,asof_required=None):
    for label,obj in (("CAUSAL",c),("WATCH",w),("MIRROR",m)):
        need(type(obj) is dict,"OBJECT_"+label)
        need(obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO",
             "NO_EXECUTION_"+label)
    need(c.get("schema")==CAUSAL and w.get("schema")==WATCH and
         m.get("schema")==MIRROR,"SCHEMA_MISMATCH")
    asof=c.get("asof_et")
    need(type(asof) is str and len(asof)==10 and
         asof==w.get("asof_et")==m.get("asof_et"),"SAME_ASOF")
    if asof_required is not None:need(asof==asof_required,"CURRENT_ASOF")
    need(all(type(r) is int and r>0 for r in
             (source_run_id,watch_run_id,mirror_run_id)),"RUN_IDS_REQUIRED")
    names=c.get("next_gate_mc_sec_research_only_symbols")
    need(valid_set(names) and len(names)==c.get("rth30_lower_bound_observed")
         and symbols_digest(names)==c.get("rth30_lower_bound_sha256")
         and c.get("rth30_partial_notional_is_proxy_not_trade_floor") is True
         and c.get("rth30_partial_research_never_primary") is True
         and c.get("rth30_data_unknown_count",0)>=
             c.get("rth30_partial_missing_slot_high_research_only_count",0)
         and c.get("c417_price_dv30_primary_attested") is False
         and c.get("issuer_class_mc_current_attested") is False
         and c.get("technical_a_b_d_r1_event_regime_attested") is False
         and c.get("registered_r92_count")==0
         and c.get("no_vendor_ohlcv_persisted") is True
         and c.get("no_canonical_mutations") is True
         and c.get("source_rights_not_inferred") is True,
         "SOURCE_PROXY_NEVER_PRIMARY")
    scope=c.get("per_symbol_causal_routing")
    need(type(scope) is dict and len(scope)==c.get("scope_count")
         and set(names).issubset(scope),"COMPLETE_CAUSAL_SCOPE")
    counts=dict(sorted(Counter(
        row["first_unresolved_gate"] for row in scope.values()).items()))
    need(counts==c.get("first_unresolved_gate_counts"),"CAUSAL_COUNTS")
    need(w.get("source_workflow_run_id")==source_run_id and
         w.get("source_causal_digest_sha256")==digest(c) and
         w.get("source_rth_lower_bound_cohort_sha256")==symbols_digest(names)
         and w.get("scope_count")==len(names)
         and w.get("source_causal_scope_count")==len(scope)
         and w.get("research_partial_rth_source_count")+
             w.get("research_complete_rth_source_count")==len(names)
         and w.get("outside_technical_cohort_count")==len(scope)-len(names)
         and w.get("full_identity_source_partition_checked") is True
         and w.get("all_symbols_classified") is True
         and w.get("full_identity_technical_scan_attested") is
             (len(names)==len(scope)),"WATCH_SOURCE_SHA_IDENTITY")
    statuses=w.get("technical_status_by_symbol")
    group=w.get("technical_setup_family_verified")
    watches=w.get("technical_research_watch_symbols")
    need(type(statuses) is dict and set(statuses)==set(names)
         and w.get("classification_counts")==dict(sorted(
             Counter(statuses.values()).items()))
         and type(group) is dict and valid_set(watches)
         and set(group)==set(watches)
         and set(watches)=={s for s in names if statuses[s]==TECH}
         and all(type(v) is list and bool(v) and
                 v==sorted(set(v)) and
                 set(v).issubset({"A","B","D"})
                 for v in group.values())
         and w.get("watch_membership_digest_sha256")==digest({
             "asof_et":asof,"technical_setup_family_verified":group}),
         "WATCH_SYMBOLS_FAMILY_DIGEST")
    need(m.get("scope_count")==len(names) and
         m.get("source_causal_cohort_sha256")==symbols_digest(names)
         and m.get("mirror_asof_pinned") is True
         and m.get("mirror_status")==
             "EXACT_ASOF_SHA_VERIFIED_SECONDARY_DISCOVERY"
         and m.get("mirror_source_repository")=="TylerJForstrom/Stock-Data"
         and type(m.get("mirror_source_commit")) is str
         and SHA40.fullmatch(m["mirror_source_commit"]) is not None
         and m["mirror_source_commit"]!="0"*40
         and m.get("source_rights_not_inferred") is True
         and m.get("technical_watch_generated_here") is False,
         "MIRROR_SHA_SOURCE")
    labels=m.get("classifications")
    ciks=m.get("ciK_secondary_discovery_only")
    need(type(labels) is dict and type(ciks) is dict
         and set(labels)==set(names)
         and m.get("classification_counts")==dict(sorted(
             Counter(labels.values()).items()))
         and set(ciks)=={s for s in names if labels[s]==CIK}
         and m.get("mirror_found_count")==len(ciks)
         and all(type(v) is str and CIK10.fullmatch(v) is not None
                 and int(v)>0 for v in ciks.values()),"MIRROR_CIK_PARTITION")
    # A research receipt MUST reject any accidental elevation anywhere.
    for flag in ("source_independent_primary_dv30_attested",
                 "source_independent_primary_history_attested",
                 "source_independent_primary_mc_attested",
                 "source_event_and_regime_release_attested",
                 "user_notification_sent","platform_notification_sent",
                 "iphone_delivery_receipt_attested"):
        need(w.get(flag) is False,"WATCH_FALSE_PRIMARY_OR_DELIVERY_"+flag)
    for flag in ("independent_official_sec_lookup_pass",
                 "exchange_listing_asof_pit_attested",
                 "issuer_class_shares_current_pit_attested",
                 "market_cap_2b_attested",
                 "official_c417_primary_price_dv30_attested",
                 "iphone_delivery_receipt_attested",
                 "canonical_files_mutated"):
        need(m.get(flag) is False,"MIRROR_FALSE_PRIMARY_"+flag)
    need(w.get("registered_r92_count")==m.get("registered_R92_count")==0
         and w.get("orders")==w.get("buy_signals")==[]
         and w.get("no_vendor_ohlcv_or_price_levels_persisted") is True
         and m.get("raw_vendor_ohlcv_persisted") is False,
         "NO_R92_NO_VENDOR_DATA_NO_TRADE")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "source_workflow_run_id":source_run_id,
        "technical_watch_workflow_run_id":watch_run_id,
        "mirror_workflow_run_id":mirror_run_id,
        "source_causal_digest_sha256":digest(c),
        "research_symbol_set_sha256":symbols_digest(names),
        "watch_membership_digest_sha256":w["watch_membership_digest_sha256"],
        "research_source_identity_count":len(scope),
        "rth_research_proxy_count":len(names),
        "research_technical_watch_count":len(watches),
        "research_secondary_cik_discovered_count":len(ciks),
        "research_watch_symbols":watches,
        "research_watch_families":dict(sorted(group.items())),
        "research_all_three_artifacts_same_asof_and_sha":True,
        "research_cohort_full_symbolic_partition_checked":True,
        "research_technical_family_coverage_of_full_universe":len(names)==len(scope),
        "research_operational_state":"RESEARCH_EVIDENCE_VERIFIED_NO_RELEASE_OR_DEVICE_RECEIPT",
        "operational_final_with_real_user_delivery_attested":False,
        "c417_primary_price_mc_release_attested":False,
        "source_rights_attested":False,
        "registered_R92_count":0,"orders":[],"execution":"NONE",
        "real_money":"NO-GO",
    }

def selftest():
    c={"schema":CAUSAL,"asof_et":"2026-10-15","execution":"NONE",
       "real_money":"NO-GO","rth30_lower_bound_observed":2,
       "rth30_lower_bound_sha256":symbols_digest(["AAA","BBB"]),
       "next_gate_mc_sec_research_only_symbols":["AAA","BBB"],
       "rth30_partial_notional_is_proxy_not_trade_floor":True,
       "rth30_partial_research_never_primary":True,
       "rth30_data_unknown_count":2,
       "rth30_partial_missing_slot_high_research_only_count":2,
       "c417_price_dv30_primary_attested":False,
       "issuer_class_mc_current_attested":False,
       "technical_a_b_d_r1_event_regime_attested":False,
       "registered_r92_count":0,"no_vendor_ohlcv_persisted":True,
       "no_canonical_mutations":True,
       "source_rights_not_inferred":True,
       "per_symbol_causal_routing":{
           "AAA":{"first_unresolved_gate":"PRICE_DV30"},
           "BBB":{"first_unresolved_gate":"PRICE_DV30"},
           "CCC":{"first_unresolved_gate":"SOURCE"}},
       "scope_count":3,
       "first_unresolved_gate_counts":{"PRICE_DV30":2,"SOURCE":1}}
    groups={"AAA":["B","D"]}
    w={"schema":WATCH,"asof_et":"2026-10-15","execution":"NONE",
       "real_money":"NO-GO","source_workflow_run_id":101,
       "source_causal_digest_sha256":digest(c),
       "source_rth_lower_bound_cohort_sha256":symbols_digest(["AAA","BBB"]),
       "scope_count":2,"source_causal_scope_count":3,
       "research_partial_rth_source_count":2,
       "research_complete_rth_source_count":0,
       "outside_technical_cohort_count":1,
       "full_identity_source_partition_checked":True,
       "full_identity_technical_scan_attested":False,
       "all_symbols_classified":True,
       "technical_status_by_symbol":{
           "AAA":TECH,"BBB":"UNKNOWN_CORPORATE_ACTION_PIT"},
       "classification_counts":{
           TECH:1,"UNKNOWN_CORPORATE_ACTION_PIT":1},
       "technical_setup_family_verified":groups,
       "technical_research_watch_symbols":["AAA"],
       "watch_membership_digest_sha256":digest({
           "asof_et":"2026-10-15","technical_setup_family_verified":groups}),
       "registered_r92_count":0,"orders":[],"buy_signals":[],
       "no_vendor_ohlcv_or_price_levels_persisted":True,
       **{k:False for k in (
          "source_independent_primary_dv30_attested",
          "source_independent_primary_history_attested",
          "source_independent_primary_mc_attested",
          "source_event_and_regime_release_attested",
          "user_notification_sent","platform_notification_sent",
          "iphone_delivery_receipt_attested")}}
    m={"schema":MIRROR,"asof_et":"2026-10-15","execution":"NONE",
       "real_money":"NO-GO",
       "scope_count":2,
       "source_causal_cohort_sha256":symbols_digest(["AAA","BBB"]),
       "mirror_asof_pinned":True,
       "mirror_status":"EXACT_ASOF_SHA_VERIFIED_SECONDARY_DISCOVERY",
       "mirror_source_repository":"TylerJForstrom/Stock-Data",
       "mirror_source_commit":"a"*40,
       "source_rights_not_inferred":True,
       "technical_watch_generated_here":False,
       "classifications":{"AAA":CIK,"BBB":CIK},
       "classification_counts":{CIK:2},
       "ciK_secondary_discovery_only":{
           "AAA":"0000000001","BBB":"0000000002"},
       "mirror_found_count":2,"registered_R92_count":0,
       "raw_vendor_ohlcv_persisted":False,
       **{k:False for k in (
          "independent_official_sec_lookup_pass",
          "exchange_listing_asof_pit_attested",
          "issuer_class_shares_current_pit_attested",
          "market_cap_2b_attested",
          "official_c417_primary_price_dv30_attested",
          "iphone_delivery_receipt_attested",
          "canonical_files_mutated")}}
    good=reconcile(c,w,m,source_run_id=101,watch_run_id=102,
                   mirror_run_id=103,asof_required="2026-10-15")
    need(good["research_technical_watch_count"]==1 and
         good["research_secondary_cik_discovered_count"]==2 and
         good["registered_R92_count"]==0 and
         good["operational_final_with_real_user_delivery_attested"] is False,
         "POSITIVE_WITH_ZERO_ALPHA")
    def attack(target,key,value):
        x=[copy.deepcopy(c),copy.deepcopy(w),copy.deepcopy(m)]
        {"c":x[0],"w":x[1],"m":x[2]}[target][key]=value
        try:reconcile(*x,source_run_id=101,watch_run_id=102,mirror_run_id=103,
                      asof_required="2026-10-15")
        except ValueError:return
        raise AssertionError("FORGED_EVIDENCE_ACCEPTED_"+target+"_"+key)
    for target,key,value in (
        ("c","rth30_lower_bound_sha256","0"*64),
        ("c","rth30_partial_notional_is_proxy_not_trade_floor",False),
        ("c","c417_price_dv30_primary_attested",True),
        ("c","source_rights_not_inferred",False),
        ("w","asof_et","2026-10-14"),
        ("w","source_workflow_run_id",900),
        ("w","source_causal_digest_sha256","0"*64),
        ("w","technical_research_watch_symbols",["AAA","BBB"]),
        ("w","watch_membership_digest_sha256","0"*64),
        ("w","user_notification_sent",True),
        ("w","source_independent_primary_mc_attested",True),
        ("w","registered_r92_count",1),
        ("m","source_causal_cohort_sha256","0"*64),
        ("m","mirror_found_count",1),
        ("m","market_cap_2b_attested",True),
        ("m","iphone_delivery_receipt_attested",True),
        ("m","mirror_asof_pinned",False),
        ("m","mirror_source_commit","bad"),
        ("m","mirror_source_commit","0"*40),
        ("m","source_rights_not_inferred",False),
        ("m","technical_watch_generated_here",True),
        ("m","ciK_secondary_discovery_only",{"AAA":"١٢٣٤٥٦٧٨٩٠","BBB":"0000000002"}),
        ("m","ciK_secondary_discovery_only",{"AAA":"0000000000","BBB":"0000000002"}),
    ):
        attack(target,key,value)
    print("XRAY_RESEARCH_OPERATIONS_ACCEPTANCE_SELFTEST=PASS_23_FORGED_AND_ONE_POSITIVE_NO_FALSE_FINAL")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--causal",type=Path)
    p.add_argument("--watch",type=Path)
    p.add_argument("--mirror",type=Path)
    p.add_argument("--source-run-id",type=int)
    p.add_argument("--watch-run-id",type=int)
    p.add_argument("--mirror-run-id",type=int)
    p.add_argument("--asof")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    need(all(x is not None for x in (
        a.causal,a.watch,a.mirror,a.out,a.source_run_id,
        a.watch_run_id,a.mirror_run_id,a.asof)),
        "INPUTS_REQUIRED")
    report=reconcile(
        json.loads(a.causal.read_text()),json.loads(a.watch.read_text()),
        json.loads(a.mirror.read_text()),
        source_run_id=a.source_run_id,watch_run_id=a.watch_run_id,
        mirror_run_id=a.mirror_run_id,asof_required=a.asof)
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_RESEARCH_ACCEPTANCE="+json.dumps({
        "asof_et":report["asof_et"],
        "scope":report["rth_research_proxy_count"],
        "watch":report["research_technical_watch_count"],
        "secondary_cik":report["research_secondary_cik_discovered_count"],
        "same_asof_sha":report["research_all_three_artifacts_same_asof_and_sha"],
        "release":False,"device_receipt":False,"R92":0,
    },sort_keys=True))
if __name__=="__main__":main()
