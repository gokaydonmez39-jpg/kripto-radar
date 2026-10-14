#!/usr/bin/env python3
"""SEC current issuer CIK candidate mapping for SHA-bound 406 RTH-research set.

One SEC official ticker/CIK/venue index download, not 406 companyfacts calls.
Current associations are not point-in-time ASOF proof, issuer-class shares,
corporate-actions, license entitlement, actual MC, C4.17 price or R92.
No traded/vendor OHLCV, account operations or market-price output.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

from alpaca_full_universe_asof_sip_availability import sha
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_SEC_PERSONAL_MC_CURRENT_CIK_ASSOCIATION_SHADOW_V1"
CAUSE="XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1"
SEC_URL="https://www.sec.gov/files/company_tickers_exchange.json"
MATCH="CURRENT_NASDAQ_CIK_ASSOCIATION_ONLY_NO_PIT_MC"
NOT_FOUND="UNKNOWN_SEC_TICKER_NOT_FOUND"
WRONG="UNKNOWN_SEC_TICKER_EXCHANGE_NOT_NASDAQ"
MULTI="UNKNOWN_MULTIPLE_ISSUER_CIK_FOR_TICKER"
SOURCE="UNKNOWN_SEC_OFFICIAL_CURRENT_INDEX_UNAVAILABLE"

def need(v,why):
    if not v:raise ValueError("XRAY_SEC_CIK_PERSONAL_"+why)

def index_scope(raw):
    need(type(raw) is dict and
         type(raw.get("fields")) is list and
         type(raw.get("data")) is list,
         "SEC_INDEX_SHAPE")
    fields=raw["fields"]
    need(len(fields)==len(set(fields)) and
         all(k in fields for k in ("cik","name","ticker","exchange")),
         "SEC_INDEX_COLUMNS")
    ix={k:fields.index(k) for k in ("cik","ticker","exchange")}
    found=defaultdict(set)
    for row in raw["data"]:
        need(type(row) is list and len(row)==len(fields),
             "SEC_INDEX_ROW_SHAPE")
        cik,ticker,exchange=(row[ix[k]] for k in
                             ("cik","ticker","exchange"))
        need(type(ticker) is str and type(exchange) is str and
             type(cik) in (int,str),"SEC_INDEX_ROW_TYPES")
        clean=ticker.upper().strip()
        if not clean:continue
        digits=str(cik).strip()
        need(digits.isdigit() and len(digits)<=10,
             "SEC_CIK_MALFORMED")
        found[clean].add((digits.zfill(10),exchange.strip().upper()))
    return found


def resolve(symbols,sec):
    need(symbols==sorted(set(symbols)) and
         all(type(s) is str and s for s in symbols),
         "RTH_COHORT_SCOPE")
    out={};cik_candidates={}
    for sym in symbols:
        choices=sec.get(sym, set())
        ciks={cik for cik,_ in choices}
        nasdaq={cik for cik,exchange in choices
                if "NASDAQ" in exchange}
        if not choices:out[sym]=NOT_FOUND
        elif len(ciks)>1:out[sym]=MULTI
        elif len(nasdaq)!=1:out[sym]=WRONG
        else:
            out[sym]=MATCH
            cik_candidates[sym]=next(iter(nasdaq))
    return out,cik_candidates


def validate_route(route,now):
    need(type(route) is dict and
         route.get("schema")==CAUSE and
         route.get("execution")=="NONE" and
         route.get("real_money")=="NO-GO" and
         route.get("no_canonical_mutations") is True and
         route.get("no_vendor_ohlcv_persisted") is True and
         route.get("issuer_class_mc_current_attested") is False and
         route.get("c417_price_dv30_primary_attested") is False and
         route.get("registered_r92_count")==0,
         "CAUSAL_SOURCE_AUTHORITY")
    need(route.get("asof_et")==last_complete_session(now),
         "LATEST_SOURCE_ASOF")
    cohort=route.get("next_gate_mc_sec_research_only_symbols")
    need(type(cohort) is list and
         cohort==sorted(set(cohort)) and
         len(cohort)==route.get("rth30_lower_bound_observed") and
         sha(cohort)==route.get("rth30_lower_bound_sha256"),
         "RTH_COHORT_HASH_PROOF")
    return route["asof_et"],cohort


def run(route,now,download):
    asof,syms=validate_route(route,now)
    status={s:SOURCE for s in syms}
    ciks={};problem=None;sec_sha=None
    try:
        raw=download()
        need(type(raw) is bytes and len(raw)<=8_000_000,
             "SEC_BOUNDED_BYTES")
        sec_sha=hashlib.sha256(raw).hexdigest()
        sec=index_scope(json.loads(raw))
        status,ciks=resolve(syms,sec)
    except (OSError,RuntimeError,ValueError,TypeError,
            urllib.error.URLError,json.JSONDecodeError) as exc:
        # Any source issue leaves ALL symbols UNKNOWN, never becomes MC pass.
        problem=("SEC_CURRENT_INDEX_UNAVAILABLE_OR_INVALID" if not
                 str(exc).startswith("XRAY_SEC_CIK_PERSONAL_") else
                 "SEC_CURRENT_INDEX_INTEGRITY_FAILED")
        status={s:SOURCE for s in syms};ciks={}
    cnt=dict(sorted(Counter(status.values()).items()))
    need(len(status)==len(syms) and sum(cnt.values())==len(syms)
         and set(ciks)=={s for s in syms if status[s]==MATCH},
         "SEC_FULL_PARTITION")
    return {
        "schema":SCHEMA, "asof_et":asof,
        "source_causal_cohort_sha256":sha(syms),
        "scope_count":len(syms),
        "sec_current_index_sha256":sec_sha,
        "sec_lookup_state":problem or "SEC_CURRENT_INDEX_PARSED",
        "classifications":dict(sorted(status.items())),
        "classification_counts":cnt,
        "sec_current_cik_candidates":dict(sorted(ciks.items())),
        "sec_mapping_is_current_only_not_asof_pit":True,
        "sec_companyfacts_class_share_count_verified":False,
        "issuer_class_and_corporate_actions_verified":False,
        "current_mc_2b_attested":False,
        "c417_price_dv30_primary_attested":False,
        "technical_pass_attested":False,
        "registered_R92_count":0,
        "vendor_ohlcv_persisted":False,
        "source_rights_not_inferred":True,
        "execution":"NONE","real_money":"NO-GO",
        "status":"SEC_ISSUER_IDENTITY_RESEARCH_NOT_MC_PASS",
    }


def selftest():
    asof="2026-10-14"
    now=dt.datetime(2026,10,14,22,tzinfo=dt.timezone.utc)
    syms=["AAA","BBB","CCC","DDD"]
    route={"schema":CAUSE,"asof_et":asof,
           "execution":"NONE","real_money":"NO-GO",
           "no_canonical_mutations":True,"no_vendor_ohlcv_persisted":True,
           "issuer_class_mc_current_attested":False,
           "c417_price_dv30_primary_attested":False,
           "registered_r92_count":0,
           "next_gate_mc_sec_research_only_symbols":syms,
           "rth30_lower_bound_observed":4,
           "rth30_lower_bound_sha256":sha(syms)}
    raw={"fields":["cik","name","ticker","exchange"],
         "data":[[12,"A","AAA","Nasdaq"],[13,"B","BBB","NYSE"],
                 [14,"C","CCC","Nasdaq"],[15,"C","CCC","Nasdaq"]]}
    obj=run(route,now,lambda:json.dumps(raw).encode())
    need(obj["classification_counts"]=={
             MATCH:1, WRONG:1,MULTI:1,NOT_FOUND:1} and
         obj["sec_current_cik_candidates"]=={"AAA":"0000000012"} and
         obj["current_mc_2b_attested"] is False,
         "NO_CLASS_MC_FALSE_PROOF")
    blocked=run(route,now,lambda:(_ for _ in ()).throw(
        urllib.error.URLError("403")))
    need(blocked["classification_counts"]=={SOURCE:4} and
         not blocked["sec_current_cik_candidates"],
         "OFFICIAL_HTTP_SOURCE_FAIL_CLOSED")
    import copy
    bad=copy.deepcopy(route);bad["rth30_lower_bound_sha256"]="x"*64
    try:run(bad,now,lambda:b"{}")
    except ValueError as exc:
        need("RTH_COHORT_HASH" in str(exc),"WRONG_SHA_REASON")
    else:raise AssertionError("WRONG_COHORT_ACCEPTED")
    bad=copy.deepcopy(route);bad["issuer_class_mc_current_attested"]=True
    try:validate_route(bad,now)
    except ValueError as exc:
        need("CAUSAL_SOURCE_AUTHORITY" in str(exc),"MC_FALSE_AUTH_REASON")
    else:raise AssertionError("UNVERIFIED_MC_PASS")
    bad=copy.deepcopy(route);bad["asof_et"]="2026-10-13"
    try:validate_route(bad,now)
    except ValueError as exc:
        need("LATEST_SOURCE_ASOF" in str(exc),"STALE_EPOCH_REASON")
    else:raise AssertionError("STALE_SOURCE_ACCEPTED")
    print("XRAY_SEC_CIK_PERSONAL_SELFTEST=PASS_SHA_PIT_MC_5_NEGATIVES_NO_ALPHA")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--causal",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    need(a.causal is not None and a.causal.is_file() and
         a.out is not None and
         not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "SOURCE_ARTIFACTS_ONLY")
    obj=json.loads(a.causal.read_text())
    now=dt.datetime.now(dt.timezone.utc)
    def fetch():
        req=urllib.request.Request(SEC_URL,headers={
            "User-Agent":"NASDAQ-XRAY Personal research bot (contact: https://github.com/gokaydonmez39-jpg/kripto-radar)",
            "Accept":"application/json",
        })
        with urllib.request.urlopen(req,timeout=30) as res:
            need(res.status==200,"SEC_HTTP_NON200")
            return res.read(8_000_001)
    result=run(obj,now,fetch)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_SEC_PERSONAL_ISSUER_CIK="+json.dumps({
        "status":result["status"],"asof_et":result["asof_et"],
        "scope":result["scope_count"],
        "counts":result["classification_counts"],
        "mc2b_confirmed":result["current_mc_2b_attested"],
        "sec_state":result["sec_lookup_state"],"R92":0
    },sort_keys=True))


if __name__=="__main__":
    main()
