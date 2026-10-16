#!/usr/bin/env python3
"""Preopen EOD-research receipt readback, NEVER C4.17/AL or a phone receipt.

The last completed session may have 14 research technical WATCH observations.
Only accept independently signed three-artifact receipt from the latest fully
successful same-ASOF source run. This is NOT a real-time intraday quote.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,re
from collections import Counter
from pathlib import Path
from source_epoch_freshness_guard import last_complete_session

SCHEMA="XRAY_PREOPEN_EOD_WATCH_RECEIPT_GATE_V1"
RECEIPT="XRAY_PERSONAL_RESEARCH_OPERATIONS_ACCEPTANCE_V1"
def need(v,why):
    if not v:raise ValueError("XRAY_PREOPEN_WATCH_RECEIPT_"+why)
def hash_json(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,
             separators=(",",":")).encode()).hexdigest()
def sha_ok(s):return type(s) is str and re.fullmatch(r"[0-9a-f]{64}",s)
def out(asof,state,detail,receipt=None):
    r=receipt or {}
    observed=state=="RESEARCH_LAST_COMPLETE_ASOF_CROSS_ARTIFACT_VERIFIED"
    return {
      "schema":SCHEMA,"asof_et":asof,
      "status":state,"reason":detail,
      "source_exact_three_artifact_research_eod_observed":observed,
      "source_universe_identity_count":r.get("research_source_identity_count",0) if observed else 0,
      "research_rth_proxy_count":r.get("rth_research_proxy_count",0) if observed else 0,
      "research_watch_count":r.get("research_technical_watch_count",0) if observed else 0,
      "watch_symbols":r.get("research_watch_symbols",[]) if observed else [],
      "source_workflow_run_id":r.get("source_workflow_run_id") if observed else None,
      "independent_c417_price_dv30_attested":False,
      "independent_c417_mc_and_corporate_events_attested":False,
      "fresh_live_rth_intraday_or_g9_attested":False,
      "platform_notification_sent_by_this_audit":False,
      "iphone_delivery_receipt_attested":False,
      "registered_R92_count":0,"no_broker_orders":True,
      "can_claim_opening_full_go":False,
      "cannot_infer_delivery_from_actions_success":True,
      "execution":"NONE","real_money":"NO-GO"}
def check(receipt,now,source_run_id=None):
    need(type(now) is dt.datetime and now.tzinfo is not None,
         "AWARE_NOW")
    asof=last_complete_session(now)
    if receipt is None:
        return out(asof,"UNKNOWN_NO_ACCEPTANCE_ARTIFACT",
                   "Latest signed research receipt not available; no watch may be inferred")
    need(type(receipt) is dict and receipt.get("schema")==RECEIPT,
         "RECEIPT_SCHEMA")
    if receipt.get("asof_et")!=asof:
        return out(asof,"UNKNOWN_STALE_OR_FUTURE_SOURCE_ASOF",
                   "Cannot reuse a research setup from a different last-completed NASDAQ session")
    need(all(receipt.get(k) is True for k in (
         "research_all_three_artifacts_same_asof_and_sha",
         "research_cohort_full_symbolic_partition_checked"))
         and receipt.get("research_operational_state")==
               "RESEARCH_EVIDENCE_VERIFIED_NO_RELEASE_OR_DEVICE_RECEIPT"
         and receipt.get("c417_primary_price_mc_release_attested") is False
         and receipt.get("operational_final_with_real_user_delivery_attested") is False
         and receipt.get("source_rights_attested") is False
         and receipt.get("registered_R92_count")==0
         and receipt.get("orders")==[]
         and receipt.get("execution")=="NONE"
         and receipt.get("real_money")=="NO-GO",
         "NO_FALSE_RELEASE_OR_NOTIFICATION")
    tickers=receipt.get("research_watch_symbols")
    family=receipt.get("research_watch_families")
    need(type(tickers) is list and
         tickers==sorted(set(tickers)) and
         all(type(x) is str and x and x.isupper() for x in tickers)
         and type(family) is dict and set(family)==set(tickers)
         and all(type(v) is list and v and v==sorted(set(v))
                 and set(v).issubset({"A","B","D"}) for v in family.values())
         and receipt.get("research_technical_watch_count")==len(tickers)
         and sha_ok(receipt.get("watch_membership_digest_sha256"))
         and receipt["watch_membership_digest_sha256"]==hash_json({
             "asof_et":asof,
             "technical_setup_family_verified":family}),
         "TECHNICAL_SYMBOL_FAMILY_SHA")
    need(type(receipt.get("research_source_identity_count")) is int and
         type(receipt.get("rth_research_proxy_count")) is int and
         type(receipt.get("research_secondary_cik_discovered_count")) is int and
         0<=len(tickers)<=receipt["rth_research_proxy_count"]<=
             receipt["research_source_identity_count"]
         and receipt["research_secondary_cik_discovered_count"]<=
             receipt["rth_research_proxy_count"]
         and all(sha_ok(receipt.get(key)) for key in (
             "research_symbol_set_sha256","source_causal_digest_sha256"))
         and all(type(receipt.get(k)) is int and receipt[k]>0 for k in (
             "source_workflow_run_id","technical_watch_workflow_run_id",
             "mirror_workflow_run_id")),
         "FULL_SOURCE_PARTITION_AND_SHA")
    if source_run_id is None:
        return out(asof,"UNKNOWN_LATEST_SOURCE_RUN_NOT_VERIFIED",
                   "Acceptance receipt alone is not proof it follows the latest completed EOD scan")
    need(type(source_run_id) is int and source_run_id>0,
         "LATEST_SOURCE_RUN_ID")
    if source_run_id!=receipt["source_workflow_run_id"]:
        return out(asof,"UNKNOWN_PENDING_NEWER_SOURCE_ATTESTATION",
                   "A newer full-universe SIP source completed after this acceptance receipt")
    return out(asof,"RESEARCH_LAST_COMPLETE_ASOF_CROSS_ARTIFACT_VERIFIED",
               "Exact symbolic EOD-only research WATCH; no official AL, G9, phone or price authority",receipt)

def selftest():
    now=dt.datetime(2026,10,16,13,19,tzinfo=dt.timezone.utc)
    asof="2026-10-15"
    t=["AAPL","MSFT"];f={"AAPL":["D"],"MSFT":["B","D"]}
    obj={
      "schema":RECEIPT,"asof_et":asof,
      "research_all_three_artifacts_same_asof_and_sha":True,
      "research_cohort_full_symbolic_partition_checked":True,
      "research_operational_state":"RESEARCH_EVIDENCE_VERIFIED_NO_RELEASE_OR_DEVICE_RECEIPT",
      "c417_primary_price_mc_release_attested":False,
      "operational_final_with_real_user_delivery_attested":False,
      "source_rights_attested":False,
      "registered_R92_count":0,"orders":[],
      "execution":"NONE","real_money":"NO-GO",
      "research_watch_symbols":t,"research_watch_families":f,
      "research_technical_watch_count":2,
      "watch_membership_digest_sha256":hash_json({
          "asof_et":asof,"technical_setup_family_verified":f}),
      "research_source_identity_count":3189,
      "rth_research_proxy_count":416,
      "research_secondary_cik_discovered_count":416,
      "research_symbol_set_sha256":"0"*64,
      "source_causal_digest_sha256":"1"*64,
      "source_workflow_run_id":10,"technical_watch_workflow_run_id":11,
      "mirror_workflow_run_id":12,
    }
    good=check(obj,now,10)
    need(good["research_watch_count"]==2 and
         good["source_exact_three_artifact_research_eod_observed"] is True
         and good["can_claim_opening_full_go"] is False,
         "POSITIVE_SOURCE_WATCH_ONLY")
    missing=check(None,now,10)
    need(missing["research_watch_count"]==0 and
         missing["source_exact_three_artifact_research_eod_observed"] is False,
         "MISSING_SOURCE_ZERO_CLAIM")
    stale=dict(obj,asof_et="2026-10-14")
    need(check(stale,now,10)["status"]=="UNKNOWN_STALE_OR_FUTURE_SOURCE_ASOF",
         "CROSS_ASOF_REJECTED")
    need(check(obj,now,None)["research_watch_count"]==0 and
         check(obj,now,99)["status"]=="UNKNOWN_PENDING_NEWER_SOURCE_ATTESTATION",
         "NEWEST_SIP_SOURCE_FENCE")
    import copy
    for k,v in (
        ("registered_R92_count",1),
        ("c417_primary_price_mc_release_attested",True),
        ("operational_final_with_real_user_delivery_attested",True),
        ("watch_membership_digest_sha256","0"*64),
        ("research_watch_symbols",["AAPL","FAKE","MSFT"]),
        ("research_technical_watch_count",3),
        ("research_secondary_cik_discovered_count",999),
        ("research_all_three_artifacts_same_asof_and_sha",False),
        ("orders",["BUY"]),
    ):
        evil=copy.deepcopy(obj);evil[k]=v
        try:check(evil,now,10)
        except ValueError:pass
        else:raise AssertionError("FORGED_RESEARCH_PREOPEN_ACCEPTED_"+k)
    print("XRAY_PREOPEN_WATCH_RECEIPT_SELFTEST=PASS_9_FORGERIES_SOURCE_FRESHNESS_ZERO_FALSE_AL")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--receipt",type=Path)
    ap.add_argument("--source-run-id",type=int)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    obj=(json.loads(args.receipt.read_text()) if
         args.receipt is not None and args.receipt.is_file() else None)
    result=check(obj,dt.datetime.now(dt.timezone.utc),args.source_run_id)
    if args.out is not None:
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_PREOPEN_EOD_RESEARCH="+json.dumps({
        "asof_et":result["asof_et"],"status":result["status"],
        "cohort":result["research_rth_proxy_count"],
        "watch":result["research_watch_count"],
        "C417":False,"G9":False,"iPhone_receipt":False,"AL":0},sort_keys=True))
if __name__=="__main__":main()
