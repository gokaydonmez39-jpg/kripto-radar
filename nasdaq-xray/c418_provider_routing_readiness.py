#!/usr/bin/env python3
"""Current-ASOF C4.17 source-exact cohort provider feasibility report.

This is a production-risk RED/GREEN router for source *eligibility*, not a
source of prices. It reads CURRENT tracked canonical artifacts and separately
source-backed provider inventory. It never makes external requests, trades,
creates MC PRIMARY, registers R92 or sends an alert. The C4.18 policy successor
remains inactive pending external entitlements and actual PIT evidence.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INVENTORY = ROOT / "c418_provider_inventory_20261012.json"
PROPOSAL = ROOT / "source_successor_c418_proposal.json"
MASTER = ROOT / "canonical_current_master_manifest.json"
PRICE = ROOT / "canonical_current_price_dv30.json"
G9 = ROOT / "g9_entitlement_authority.json"
SCHEMA = "XRAY_C418_DYNAMIC_MULTI_PROVIDER_ROUTING_READINESS_V2"

EXPECTED_IDS = {
    "SEC_EDGAR","ALPACA","RALLIES","LONGBRIDGE","MASSIVE",
    "FMP","ALPHA_VANTAGE","EODHD","TIINGO",
    "NASDAQ_DATA_LINK_SHARADAR","OPENBB","BUSINESSQUANT",
}
DANGEROUS_KEYS = {"raw","api_key","apikey","token","password",
                  "market_cap_usd","close_usd","positions"}

def require(ok, reason):
    if not ok:
        raise ValueError("XRAY_SOURCE_ROUTER_FAIL_CLOSED:" + reason)

def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\0" + data).hexdigest()

def symbol_hash(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def valid_set(rows):
    return bool(type(rows) is list and rows == sorted(set(rows))
                and all(type(x) is str and re.fullmatch(r"[A-Z0-9.-]+",x) for x in rows))

def cap(n,rate):
    require(type(n) is int and n>=0 and type(rate) is int and rate>0,
            "INVALID_QUOTA_ARITHMETIC")
    return (n+rate-1)//rate

def provider_table(inv):
    require(type(inv) is dict and inv.get("schema")=="XRAY_C418_PROVIDER_FEASIBILITY_INVENTORY_V1",
            "INVENTORY_SCHEMA")
    require(inv.get("effective_policy")=="C4.17"
            and inv.get("successor_status")=="C4.18_PROPOSED_NOT_ACTIVATED"
            and inv.get("execution")=="NONE" and inv.get("real_money")=="NO-GO"
            and inv.get("unknown_never_pass") is True
            and inv.get("source_rights_not_inferred_from_free_price") is True
            and inv.get("no_provider_automatically_activated") is True
            and inv.get("no_vendor_raw_data_in_public_artifact") is True,
            "INVENTORY_SHADOW_FROZEN")
    rows=inv.get("sources")
    require(type(rows) is list and len(rows)==12,"INVENTORY_SOURCE_CARDINALITY")
    ids=[r.get("id") for r in rows if type(r) is dict]
    require(len(ids)==len(rows) and set(ids)==EXPECTED_IDS
            and len(ids)==len(set(ids)),"INVENTORY_SOURCE_IDENTITY")
    for r in rows:
        require(type(r.get("official_docs")) is str
                and r["official_docs"].startswith("https://")
                and r.get("runner_key_attested") is False
                and r.get("mc_current_exact") is False
                and type(r.get("market_cap_direct")) is bool
                and type(r.get("lookahead_guard")) is str
                and type(r.get("rights_state")) is str,
                "SOURCE_PREMATURE_AUTHORITY_" + str(r.get("id")))
        for field in ("daily_requests","max_unique_symbols","rate_per_minute"):
            v=r.get(field)
            require(v is None or (type(v) is int and v>0),"BAD_QUOTA:"+r["id"])
        require(not any(k in r for k in DANGEROUS_KEYS),"NO_RAW_VENDOR_MARKET_DATA")
    sample=inv.get("live_shadow_probe_summary") or {}
    require(sample.get("asof")=="2026-10-09"
            and sample.get("symbols_sampled_count")==3
            and sample.get("same_or_integer_rounding_equivalent_mc_count")==3
            and sample.get("upstream_independence_verified") is False
            and sample.get("issuer_class_outstanding_cross_source_proven") is False
            and sample.get("rights_grant_for_unattended_runner") is False
            and sample.get("production_mc_primary_created")==0,
            "INTERACTIVE_SAMPLES_NOT_SOURCE_INDEPENDENCE")
    return {x["id"]:x for x in rows}

def source_obstacles(records):
    return {
        "C417_BIGDATA_PRIMARY":"CREDIT_EXHAUSTED_OBSERVED_NO_PAID_TOPUP",
        "C418_DIRECT_VENDOR_MC":"RUNNER_RIGHTS_AND_FILING_ACCEPTANCE_PIT_NOT_ATTESTED",
        "C418_DERIVED_SEC_AND_ALPACA_MC":"SINGLE_SHARE_CLASS_CA_FULL_INTERVAL_AND_INDEPENDENT_MC_NOT_ATTESTED",
        "C418_PERSONAL_BASIC_MASSIVE":"DISPLAY_ONLY_STANDARD_LICENSE_AND_PERIOD_END_LOOKAHEAD",
        "C417_RALLIES_LONGBRIDGE_FALLBACK":"WATCH_NOT_PRIMARY_R92_FALSE",
        "C418_CROSSCHECK_SOURCE_INDEPENDENCE":"RALLIES_MASSIVE_IDENTICAL_SAMPLE_DOES_NOT_PROVE_INDEPENDENCE",
        "G9_FULL_REALTIME":"MUST_HAVE_CONSOLIDATED_NBBO_LIVE_ENTITLEMENT_INDEPENDENT_OF_EOD",
        "PHONE_RECEIPT":"NO_USER_DEVICE_RECEIPT_WITNESS",
    }

def analyze(master,price,inv,proposal,g9,sha_master,sha_price,sha_inventory):
    providers=provider_table(inv)
    require(type(proposal) is dict
            and proposal.get("schema")=="XRAY_SOURCE_SUCCESSOR_POLICY_PROPOSAL_V1"
            and proposal.get("activation_status")=="PROPOSED_NOT_ACTIVATED"
            and proposal.get("effective_production_policy")=="C4.17"
            and proposal.get("explicit_source_promotion_authorized") is False
            and proposal.get("can_create_PRIMARY") is False
            and proposal.get("can_register_R92") is False
            and proposal.get("execution")=="NONE" and proposal.get("real_money")=="NO-GO"
            and proposal.get("unknown_never_pass") is True,
            "NO_POLICY_CUTOVER")
    require(g9.get("status")=="BLOCKED_STRICT_PERMANENT_ZERO","G9_UNEXPECTED_CHANGE_REVIEW")
    asof=price.get("asof_et")
    require(type(asof) is str and re.fullmatch(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]",asof or "") is not None
            and dt.date.fromisoformat(asof).isoformat()==asof
            and master.get("asof_et")==asof, "ASOF_MASTER_PRICE_NOT_EXACT")
    require(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                and x.get("unknown_never_pass") is True for x in (master,price)),
            "CANONICAL_SAFETY_INVALID")
    ms,ps,us=master.get("pass_symbols"),price.get("pass_symbols"),master.get("unknown_symbols")
    require(all(valid_set(x) for x in (ms,ps,us)),"SYMBOL_SET_MALFORMED")
    require(type(master.get("pass_count")) is int and len(ms)==master["pass_count"]
            and type(master.get("unknown_count")) is int and len(us)==master["unknown_count"]
            and type(price.get("pass_count")) is int and len(ps)==price["pass_count"],
            "SOURCE_COUNT_INVALID")
    require(set(ps).issubset(ms) and set(us).isdisjoint(ms),"SYMBOL_LINEAGE_NOT_DISJOINT")
    require(price.get("source_master_queue_hash")==master.get("queue_hash")
            and price.get("pass_hash")==symbol_hash(ps)
            and master.get("queue_hash")==symbol_hash(ms)
            and type(price.get("unknown_count")) is int
            and price.get("unknown_count")==0
            and type(price.get("blocked_count")) is int
            and price.get("blocked_count")==0,
            "SOURCE_HASH_SCOPE_OR_PRICE_NOT_COMPLETE")
    require(len(ms)>0 and len(ps)<=len(ms),"MASTER_SCOPE_OR_PRICE_COHORT_BAD")
    # Earlier interactive source samples remain historical when ASOF changes.
    sample_asof=inv["live_shadow_probe_summary"]["asof"]
    require(sample_asof<=asof,"HISTORICAL_SAMPLE_FROM_FUTURE")
    require(len(sha_master)==len(sha_price)==40 and len(sha_inventory)==40,
            "GIT_BLOB_NOT_40")
    candidate_local_unknown=sorted(set(ps)&set(us))
    require(len(candidate_local_unknown)==0,"IDENTITY_UNKNOWN_IN_PRICE_SCOPE")
    estimates={}
    for src in ("MASSIVE","FMP","ALPHA_VANTAGE","EODHD","BUSINESSQUANT"):
        r=providers[src]
        d=r.get("daily_requests")
        m=r.get("rate_per_minute")
        estimates[src]={
            "conditional_calls_per_symbol":1,
            "minimum_days_if_one_request_per_symbol":cap(len(ps),d) if d else None,
            "minimum_minutes_if_one_request_per_symbol":cap(len(ps),m) if m else None,
            "actual_same_asof_mc_entitlement":"UNVERIFIED",
            "conditional_only_not_scheduled":True,
        }
    ti=providers["TIINGO"]
    estimates["TIINGO"]={
        "unique_symbol_quota_month":ti["max_unique_symbols"],
        "single_account_full_current_cohort_coverage_possible":bool(ti["max_unique_symbols"]>=len(ps)),
        "not_a_mc_source":True,
        "actual_same_asof_mc_entitlement":"UNVERIFIED",
    }
    return {
        "schema":SCHEMA,
        "asof_et":price["asof_et"],
        "source_git_blob_shas":{"master":sha_master,"price":sha_price,"inventory":sha_inventory},
        "historical_3_ticker_sample_asof_et":sample_asof,
        "historical_3_ticker_sample_is_current_asof":sample_asof==asof,
        "historical_sample_may_grant_primary":False,
        "canonical_price_pass_count":len(ps),
        "master_identity_pass_count":len(ms),
        "master_identity_unknown_count":len(us),
        "identity_unknown_intersect_price_count":0,
        "discovered_source_rows":len(providers),
        "market_cap_direct_provider_count":sum(x["market_cap_direct"] for x in providers.values()),
        "historical_source_count":4,
        "historical_interactive_massive_rallies_samples":3,
        "verified_distinct_market_cap_origin_count":0,
        "new_primary_mc_authority_count":0,
        "production_mc_primary_pass_count_created":0,
        "new_r92_count_created":0,
        "g9_strict_release_allowed":False,
        "source_proposal_status":"NOT_ACTIVATED",
        "rights_and_pit_evidence_sufficient":False,
        "per_source_capacity_scenarios":estimates,
        "obstacles":source_obstacles(providers),
        "routing_order":[
            "SEC_ORIGINAL_PRE_CLOSE_FILING_CIK_AND_SHARE_CLASS_IDENTITY_ONLY",
            "ALPACA_DELAYED_HISTORICAL_SIP_260_52_SPLIT_CA_WITH_EXACT_ASOF_BLOB",
            "EXACT_DATE_AUTHORIZED_DIRECT_MC_VENDOR_IF_RIGHTS_AND_PIT_AVAILABLE",
            "SECOND_UPSTREAM_INDEPENDENT_MC_SOURCE_AND_LEGAL_RIGHTS_ATTESTATION",
            "UNRESOLVED_CLASS_CA_AND_REPORT_LOOKAHEAD_REMAIN_UNKNOWN",
            "C417_RALLIES_LONGBRIDGE_WATCH_NEVER_R92",
            "G9_AND_DELIVERY_REQUIRE_SEPARATE_EVIDENCE",
        ],
        "no_unattended_paid_calls_performed":True,
        "no_external_provider_called_by_this_script":True,
        "no_vendor_raw_data_exported":True,
        "effective_policy":"C4.17",
        "go":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def source_sha(path):
    return blob_sha(path.read_bytes())

def selftest():
    inv=load(INVENTORY); proposal=load(PROPOSAL)
    price={"asof_et":"2026-10-09","execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True,"pass_symbols":["A","B"],"pass_count":2,
           "pass_hash":symbol_hash(["A","B"]),"unknown_count":0,"blocked_count":0,
           "source_master_queue_hash":symbol_hash(["A","B"])}
    master={"asof_et":"2026-10-09","execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"pass_symbols":["A","B"],"pass_count":2,
            "unknown_symbols":["SPAC"],"unknown_count":1,
            "queue_hash":symbol_hash(["A","B"])}
    # The test starts from real Oct-09 counts, but dynamically shifts ASOF
    # and cohort size to prove future exact-source sessions remain routable.
    master["pass_symbols"]=[f"S{i:04d}" for i in range(3184)]
    master["pass_count"]=3184
    master["unknown_symbols"]=[f"U{i:02d}" for i in range(12)]
    master["unknown_count"]=12
    master["queue_hash"]=symbol_hash(master["pass_symbols"])
    price["pass_symbols"]=master["pass_symbols"][:514]
    price["pass_count"]=514;price["pass_hash"]=symbol_hash(price["pass_symbols"])
    price["source_master_queue_hash"]=master["queue_hash"]
    g9={"status":"BLOCKED_STRICT_PERMANENT_ZERO"}
    args=(master,price,inv,proposal,g9,"a"*40,"b"*40,"c"*40)
    got=analyze(*args)
    require(got["discovered_source_rows"]==12 and got["identity_unknown_intersect_price_count"]==0,
            "SELFTEST_POSITIVE")
    require(got["go"] is False and got["new_primary_mc_authority_count"]==0
            and got["verified_distinct_market_cap_origin_count"]==0,
            "SELFTEST_MUST_NOT_GO")
    require(got["per_source_capacity_scenarios"]["MASSIVE"]["minimum_minutes_if_one_request_per_symbol"]==103,"MASSIVE_CAP_103")
    require(got["per_source_capacity_scenarios"]["FMP"]["minimum_days_if_one_request_per_symbol"]==3,"FMP_CAP_3")
    require(got["per_source_capacity_scenarios"]["ALPHA_VANTAGE"]["minimum_days_if_one_request_per_symbol"]==21,"ALPHA_CAP_21")
    require(got["per_source_capacity_scenarios"]["EODHD"]["minimum_days_if_one_request_per_symbol"]==26,"EODHD_CAP_26")
    require(got["per_source_capacity_scenarios"]["BUSINESSQUANT"]["minimum_days_if_one_request_per_symbol"]==18,"BUSINESSQUANT_CAP_18_IF_ONE_PER_SYMBOL")
    require(got["new_primary_mc_authority_count"]==0 and got["new_r92_count_created"]==0,"BQ_NOT_PRIMARY")
    bq=next(s for s in inv["sources"] if s["id"]=="BUSINESSQUANT")
    require(bq["current_connected"]=="IN_REPO_RESEARCH_ADAPTER_NO_VERIFIED_KEY"
            and bq["lookahead_guard"].startswith("SCREEN_RECALCULATED_EVERY_MINUTE")
            and bq["runner_key_attested"] is False
            and bq["mc_current_exact"] is False, "BQ_NOT_PIT_OR_LICENSED")

    require(got["per_source_capacity_scenarios"]["TIINGO"]["single_account_full_current_cohort_coverage_possible"] is False,"TIINGO_514_CANNOT")
    # Regression: next exact MASTER/PRICE ASOF is not an error because a
    # historical 2026-10-09 research sample remains in the source inventory.
    shifted=[copy.deepcopy(z) for z in args]
    shifted[0]["asof_et"]=shifted[1]["asof_et"]="2026-10-12"
    shifted[0]["unknown_symbols"]=[f"U{i:02d}" for i in range(9)]
    shifted[0]["unknown_count"]=9
    shifted[1]["pass_symbols"]=shifted[0]["pass_symbols"][:520]
    shifted[1]["pass_count"]=520
    shifted[1]["pass_hash"]=symbol_hash(shifted[1]["pass_symbols"])
    new_epoch=analyze(*shifted)
    require(new_epoch["canonical_price_pass_count"]==520
            and new_epoch["master_identity_unknown_count"]==9
            and new_epoch["historical_3_ticker_sample_is_current_asof"] is False
            and new_epoch["verified_distinct_market_cap_origin_count"]==0
            and new_epoch["go"] is False,"NEXT_EPOCH_520_9_NO_FALSE_MC")
    # No PRICE-eligible stocks is valid and cannot divide by zero.
    shifted[1]["pass_symbols"]=[]
    shifted[1]["pass_count"]=0
    shifted[1]["pass_hash"]=symbol_hash([])
    no_price=analyze(*shifted)
    require(no_price["canonical_price_pass_count"]==0
            and no_price["per_source_capacity_scenarios"]["MASSIVE"]["minimum_minutes_if_one_request_per_symbol"]==0
            and no_price["go"] is False,"NO_PRICE_ZERO_NOT_VALID")
    # A past-source-data sample which lies in the future of the current
    # canonical price epoch must be rejected as invalid research lineage.
    bad_inventory=copy.deepcopy(inv)
    bad_inventory["live_shadow_probe_summary"]["asof"]="2026-10-14"
    futures=[copy.deepcopy(z) for z in args]
    futures[2]=bad_inventory
    try:analyze(*futures)
    except ValueError:pass
    else:raise RuntimeError("FUTURE_VENDOR_SAMPLE_MUST_FAIL_CLOSED")
    mutations=[
        (0,lambda x:x.update(unknown_count=0),"MASTER_COUNT"),
        (0,lambda x:x["unknown_symbols"].append("S0000"),"UNKNOWN_OVERLAP"),
        (0,lambda x:x.update(queue_hash="0"*64),"QUEUE_SHA"),
        (1,lambda x:x.update(pass_hash="0"*64),"PRICE_HASH"),
        (1,lambda x:x.update(blocked_count=1),"BLOCKED_NOT_EMPTY"),
        (1,lambda x:x["pass_symbols"].pop(),"SHORTENED_514"),
        (1,lambda x:x.update(source_master_queue_hash="0"*64),"MASTER_BIND"),
        (1,lambda x:x.update(real_money="GO"),"REAL_MONEY"),
        (2,lambda x:x.update(source_rights_not_inferred_from_free_price=False),"FAKE_LICENSE"),
        (2,lambda x:x["sources"][4].update(runner_key_attested=True),"FAKE_RUNNER_KEY"),
        (2,lambda x:x["live_shadow_probe_summary"].update(upstream_independence_verified=True),"FAKE_INDEPENDENCE"),
        (2,lambda x:x["live_shadow_probe_summary"].update(production_mc_primary_created=1),"FAKE_MC"),
        (3,lambda x:x.update(explicit_source_promotion_authorized=True),"FAKE_C418_CUTOVER"),
        (3,lambda x:x.update(activation_status="ACTIVATED"),"FAKE_ACTIVATION"),
        (4,lambda x:x.update(status="PASS"),"G9_DRIFT"),
    ]
    n=0
    for pos,mutate,label in mutations:
        m=[copy.deepcopy(z) for z in args]
        mutate(m[pos])
        try:analyze(*m)
        except ValueError:n+=1
        else:raise RuntimeError("UNSAFE_ROUTER_MUTANT_ACCEPTED:"+label)
    print("XRAY_C418_12_SOURCE_ROUTING_DYNAMIC_ASOF=PASS_REAL_SOURCE_SCHEMA_"
          +str(n)+"_NEGATIVE_C417_NO_MC_NO_R92")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--out",type=Path)
    opt=a.parse_args()
    if opt.selftest:
        selftest()
        return
    result=analyze(load(MASTER),load(PRICE),load(INVENTORY),load(PROPOSAL),
                   load(G9),source_sha(MASTER),source_sha(PRICE),source_sha(INVENTORY))
    if opt.out:
        opt.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_C418_MULTI_PROVIDER_FEASIBILITY=VALID_ROUTING_NO_PRODUCTION_GO")
    print("XRAY_C418_CURRENT_ASOF="+result["asof_et"])
    print("XRAY_C418_SCOPE="+str(result["canonical_price_pass_count"]))
    print("XRAY_C418_SOURCES="+str(result["discovered_source_rows"]))
    print("XRAY_C418_LIVE_PRIMARY=0_SOURCE_LICENSE_AND_PIT_UNVERIFIED")

if __name__=="__main__":
    main()
