#!/usr/bin/env python3
"""PERSONAL use, no-trade SEC+Alpaca issuer-MC cohort probe.

Proves read-only, official exact Nasdaq ticker->CIK SEC filing vintage and
Alpaca delayed SIP close arithmetic for the 8 canonical canaries. Issuer/entity
shares are not guaranteed to be the listed stock class. Does not establish
share-class, ADR, post-filing issuance, split basis, license, vendor MC parity,
PRIMARY, R92, or GO. Vendor bars/share counts never leave process RAM.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
import time
from pathlib import Path

from alpaca_free_sip_shadow_guard import (
    request_batch, sufficient_delay, blob_sha
)
from current_history_source_request import sha256_lines
from sec_free_mc_multisymbol_pit_audit import map_ciks,SEC_MAP,DEFAULT_CANARIES
from sec_official_free_mc_transport_probe import get_json,valid_operator_contact
from p0_sec_alpaca_personal_mc_canary import measure

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_SEC_ALPACA_8_ISSUER_MC_SHADOW_V1"
MIN_SEC_REQUEST_GAP_SECONDS=0.65
SUCCESS="SHADOW_SEC_PIT_AND_SIP_CLOSE_ARITHMETIC_VERIFIED_CLASS_CA_UNPROVEN"

def require(ok,why):
    if not ok:raise ValueError("XRAY_PERSONAL_MC_COHORT:"+why)

def scope(price,master,sec_map):
    asof=price.get("asof_et")
    p=price.get("pass_symbols")
    m=master.get("pass_symbols")
    require(isinstance(asof,str) and asof==master.get("asof_et"),
            "PRICE_MASTER_ASOF")
    require(isinstance(p,list) and p==sorted(set(p)) and
            len(p)==price.get("pass_count") and
            sha256_lines(p)==price.get("pass_hash") and
            isinstance(m,list) and set(p).issubset(set(m)),
            "PRICE_MASTER_SET_SHA")
    require(all(x.get("execution")=="NONE" and
                x.get("real_money")=="NO-GO" and
                x.get("unknown_never_pass") is True
                for x in (price,master)),"SOURCE_SAFETY")
    require(isinstance(sec_map,dict),"SEC_ROUTE_MALFORMED")
    expected=sorted(set(DEFAULT_CANARIES)&set(p))
    require(len(expected)>=4 and
            len(expected)==len(set(expected)),
            "CANONICAL_CURRENT_BOUNDED_COHORT_TOO_SMALL")
    route={sym:sec_map[sym] for sym in expected if sym in sec_map}
    require(len(route)==len(expected)
            and all(isinstance(x,str) and len(x)==10 and x.isdigit()
                    for x in route.values()),"OFFICIAL_EXACT_TICKER_CIK_MISSING")
    return asof,route

def audited_results(price,master,route,sec_transport,alpaca_batch,asof):
    require(isinstance(route,dict) and len(route)>0,"EMPTY_ROUTE")
    require(isinstance(alpaca_batch,dict) and
            not(set(alpaca_batch)-set(route)),"FOREIGN_ALPACA_TICKER")
    outputs={}
    for sym,cik in route.items():
        try:
            facts,sub=sec_transport(sym,cik)
            assert isinstance(facts,dict) and isinstance(sub,dict)
            result=measure(price,master,facts,sub,
                           alpaca_batch.get(sym,[]),asof,
                           symbol=sym,cik=cik)
            require(result.get("C417_PRIMARY_MC") is False
                    and result.get("GO") is False and
                    result.get("numeric_shares_price_or_marketcap_persisted") is False,
                    "UNSAFE_INTERNAL_SINGLE_ISSUER_AUTHORITY")
            outputs[sym]={
                "status":result["status"],
                "derived_mc_above_2b_shadow":result["calculated_MC_above_2B_unadjusted"],
                "sec_share_age_days":result.get("SEC_share_age_days"),
                "identity_class_CA_PIT_primary_attested":False}
        except (ValueError,RuntimeError,KeyError,TypeError,AssertionError):
            # Neither exception text (which might contain URL/secret) nor
            # sensitive issuer/share/market-price values enter the artifact.
            outputs[sym]={"status":"UNKNOWN_SEC_OR_SIP_PROVENANCE",
                          "derived_mc_above_2b_shadow":None,
                          "identity_class_CA_PIT_primary_attested":False}
    require(set(outputs)==set(route),"UNMEASURED_BOUND_COHORT")
    counts=collections.Counter(x["status"] for x in outputs.values())
    return {"schema":SCHEMA,"asof_et":asof,"requested_count":len(route),
            "requested_tickers":sorted(route),
            "SEC_ticker_CIK_current_not_historical_mapping":True,
            "attempted_count":len(outputs),
            "outcomes":outputs,
            "status_counts":dict(sorted(counts.items())),
            "status":"RESEARCH_EXACT_COHORT_COMPLETED_SHADOW_ONLY",
            "full_514_current_MC_primary_proven":False,
            "independent_market_cap_comparator_verified":False,
            "issuer_class_and_all_CA_attested":False,
            "HISTORY_260_52_primary_proven":False,
            "vendor_price_shares_and_derived_marketcap_archived":False,
            "can_register_R92":False,"primary_mc_created":0,
            "alpha_candidate_created":0,"execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True}

def selftest():
    from copy import deepcopy
    a="2026-10-09"
    ps=sorted(DEFAULT_CANARIES)
    p={"asof_et":a,"pass_symbols":ps,"pass_count":len(ps),
       "pass_hash":sha256_lines(ps),"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True}
    m={"asof_et":a,"pass_symbols":ps+["QQQ"],
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    route={s:f"{1000+i:010d}" for i,s in enumerate(ps)}
    aa,rr=scope(p,m,route)
    require(aa==a and rr==route,"EXACT_SCOPE_POSITIVE")
    failures=0
    def red(name,fn):
        nonlocal failures
        failures+=1
        try:fn()
        except ValueError:return
        raise AssertionError("FALSE_BOUND_COHORT_ACCEPTED:"+name)
    pp=deepcopy(p);pp["pass_hash"]="0"*64
    red("PRICE_DIGEST",lambda:scope(pp,m,route))
    pp=deepcopy(p);pp["asof_et"]="2026-10-08"
    red("ASOF_MISMATCH",lambda:scope(pp,m,route))
    pp=deepcopy(p);pp["execution"]="BUY"
    red("EXECUTION",lambda:scope(pp,m,route))
    pp=deepcopy(p);pp["unknown_never_pass"]=False
    red("UNKNOWN_PASS",lambda:scope(pp,m,route))
    mm=deepcopy(m);mm["pass_symbols"]=["QQQ"]
    red("MASTER_SET",lambda:scope(p,mm,route))
    red("MISSING_CIK",lambda:scope(p,m,{k:v for k,v in route.items() if k!="AAPL"}))
    rr2=deepcopy(route);rr2["AAPL"]="bad"
    red("CIK_INVALID",lambda:scope(p,m,rr2))
    pp=deepcopy(p);pp["pass_symbols"]=["AAPL"]
    red("TOO_SMALL",lambda:scope(pp,m,route))
    red("FOREIGN_ALPACA_TICKER",lambda:audited_results(p,m,route,lambda *x:({},{}),{"FAKE":[]},a))
    def denied(*args):raise ValueError("UNKNOWN_DATA")
    result=audited_results(p,m,route,denied,{},a)
    require(result["attempted_count"]==len(route) and
            all(x["status"]=="UNKNOWN_SEC_OR_SIP_PROVENANCE"
                for x in result["outcomes"].values()) and
            result["primary_mc_created"]==0 and
            result["can_register_R92"] is False,"UNKNOWN_STAYS_UNKNOWN")
    print("XRAY_PERSONAL_MC_8_COHORT_SELFTEST=PASS_2_POSITIVE_9_NEGATIVE_NO_VENDOR_NO_PRIMARY_PYTHON_O_SAFE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"EXPLICIT_OUTPUT_REQUIRED")
    price_path=ROOT/"canonical_current_price_dv30.json"
    master_path=ROOT/"canonical_current_master_manifest.json"
    price=json.loads(price_path.read_text())
    master=json.loads(master_path.read_text())
    asof=price.get("asof_et")
    result={"schema":SCHEMA,"status":"UNKNOWN_NOT_MEASURED",
            "asof_et":asof,"primary_mc_created":0,
            "can_register_R92":False,"execution":"NONE","real_money":"NO-GO",
            "vendor_price_shares_and_derived_marketcap_archived":False}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","")
    if not valid_operator_contact(ua):
        result["status"]="BLOCKED_SEC_OPERATOR_IDENTITY"
    elif not key or not secret:
        result["status"]="BLOCKED_ALPACA_PERSONAL_DATA_KEYS"
    elif not sufficient_delay(asof,dt.datetime.now(dt.timezone.utc)):
        result["status"]="BLOCKED_ASOF_CLOSE_OR_PROVIDER_HOLDBACK"
    else:
        try:
            sec_map=map_ciks(get_json(SEC_MAP,ua))
            asof,route=scope(price,master,sec_map)
            nextday=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()
            bars=request_batch(sorted(route),asof+"T00:00:00Z",
                                nextday+"T00:00:00Z",key,secret,
                                adjustment="raw",asof=asof)
            last_request=[0.0]
            def fetch(sym,cik):
                # Never bypass official SEC fair-access limits (<=2 requests/s).
                objects=[]
                for url in (f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                            f"https://data.sec.gov/submissions/CIK{cik}.json"):
                    remaining=MIN_SEC_REQUEST_GAP_SECONDS-(time.monotonic()-last_request[0])
                    if remaining>0:time.sleep(remaining)
                    last_request[0]=time.monotonic()
                    objects.append(get_json(url,ua))
                return tuple(objects)
            result=audited_results(price,master,route,fetch,bars,asof)
        except (ValueError,RuntimeError,KeyError,TypeError):
            result["status"]="UNKNOWN_CURRENT_SCOPE_OR_BOUNDED_PROVIDER_ACCESS"
    result["source_price_blob_sha"]=blob_sha(price_path)
    result["source_master_blob_sha"]=blob_sha(master_path)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_MC_8_COHORT_STATUS="+result["status"])
    print("XRAY_PERSONAL_MC_8_COHORT_COUNTS="+json.dumps(result.get("status_counts",{}),sort_keys=True))
    print("XRAY_PERSONAL_MC_PRIMARY=0_RESEARCH_ONLY_NO_FALSE_GO")

if __name__=="__main__":main()
