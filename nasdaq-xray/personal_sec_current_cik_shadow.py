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
import re
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
MIRROR="RESEARCH_EXACT_ASOF_VERIFIED_MIRROR_CIK_NOT_OFFICIAL_CURRENT"
MIRROR_REPO="TylerJForstrom/Stock-Data"

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


def run(route,now,download,mirror_discover=None):
    asof,syms=validate_route(route,now)
    status={s:SOURCE for s in syms}
    ciks={};problem=None;sec_sha=None
    # A third-party mirror is never interchangeable with the SEC primary.
    # Keep source identity, provenance and decision authority separate.
    mirror_ciks={};mirror_sha=None;mirror_commit=None;mirror_date=None
    mirror_state="NOT_USED_PRIMARY_REQUEST_SUCCEEDED"
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
        mirror_state="NOT_REQUESTED"
        if mirror_discover is not None:
            try:
                # discover_exact_asof() verifies immutable commit, snapshot
                # date, declared upstream success date, payload bytes & SHA256.
                # It never uses a stale or future SEC ticker association.
                proof=mirror_discover(asof,syms)
                need(type(proof) is dict and
                     proof.get("status")=="EXACT_ASOF_CIK_DISCOVERY_ONLY" and
                     proof.get("source_repository")==MIRROR_REPO and
                     proof.get("snapshot_date")==asof and
                     type(proof.get("source_commit")) is str and
                     re.fullmatch(r"[0-9a-f]{40}",proof["source_commit"]) and
                     type(proof.get("source_sha256")) is str and
                     re.fullmatch(r"[0-9a-f]{64}",proof["source_sha256"]) and
                     proof.get("unknown_total")==len(syms) and
                     type(proof.get("ciK_discovery_only")) is dict and
                     proof.get("ciK_discovered_count")==
                         len(proof["ciK_discovery_only"]),
                     "MIRROR_EXACT_ASOF_SOURCE_PROOF")
                mirror_ciks=proof["ciK_discovery_only"]
                need(set(mirror_ciks)<=set(syms) and
                     all(type(cik) is str and
                         re.fullmatch(r"[0-9]{10}",cik) and int(cik)>0
                         for cik in mirror_ciks.values()),
                     "MIRROR_INVALID_CIK_OR_SCOPE")
                mirror_ciks=dict(sorted(mirror_ciks.items()))
                status.update({sym:MIRROR for sym in mirror_ciks})
                mirror_sha=proof["source_sha256"]
                mirror_commit=proof["source_commit"]
                mirror_date=proof["snapshot_date"]
                mirror_state="VERIFIED_EXACT_ASOF_THIRD_PARTY_RESEARCH_ONLY"
            except Exception:
                # A failed, malformed, stale or future mirror remains UNKNOWN.
                mirror_state="MIRROR_UNAVAILABLE_OR_NOT_EXACT_ASOF"
                mirror_ciks={};mirror_sha=None;mirror_commit=None;mirror_date=None
                status={s:SOURCE for s in syms}
    cnt=dict(sorted(Counter(status.values()).items()))
    need(len(status)==len(syms) and sum(cnt.values())==len(syms)
         and set(ciks)=={s for s in syms if status[s]==MATCH}
         and set(mirror_ciks)=={s for s in syms if status[s]==MIRROR}
         and not (set(ciks)&set(mirror_ciks)),
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
        "mirror_exact_asof_cik_research_candidates":mirror_ciks,
        "mirror_snapshot_date":mirror_date,
        "mirror_source_repository":MIRROR_REPO if mirror_commit else None,
        "mirror_source_commit":mirror_commit,
        "mirror_source_sha256":mirror_sha,
        "mirror_verification_state":mirror_state,
        "mirror_cik_never_substitutes_sec_primary_or_mc":True,
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
    # Realistic primary SEC 403: an exact-date, SHA-attested third-party
    # snapshot may help RESEARCH ONLY; official SEC CIK authority stays empty.
    mirror={
        "status":"EXACT_ASOF_CIK_DISCOVERY_ONLY",
        "source_repository":MIRROR_REPO,
        "snapshot_date":asof,
        "source_commit":"a"*40,
        "source_sha256":"b"*64,
        "unknown_total":len(syms),
        "ciK_discovered_count":2,
        "ciK_discovery_only":{"AAA":"0000000012","DDD":"0000000016"},
    }
    no_sec=lambda:(_ for _ in ()).throw(urllib.error.URLError("403"))
    mirror_ok=run(route,now,no_sec,lambda a,s:mirror)
    need(mirror_ok["classification_counts"]=={MIRROR:2,SOURCE:2}
         and mirror_ok["sec_current_cik_candidates"]=={}
         and mirror_ok["mirror_exact_asof_cik_research_candidates"]==
             mirror["ciK_discovery_only"]
         and mirror_ok["mirror_verification_state"]==
             "VERIFIED_EXACT_ASOF_THIRD_PARTY_RESEARCH_ONLY"
         and mirror_ok["current_mc_2b_attested"] is False
         and mirror_ok["registered_R92_count"]==0,
         "MIRROR_RESEARCH_ONLY_NO_MC_PROMOTION")
    mirror_bad_cases=[
        dict(mirror,snapshot_date="2026-10-13"),
        dict(mirror,source_commit="x"*40),
        dict(mirror,source_sha256="bad"),
        dict(mirror,ciK_discovery_only={"OUTSIDE":"0000000012"}),
        dict(mirror,ciK_discovered_count=77),
        dict(mirror,ciK_discovery_only={"AAA":"0000000000"}),
        dict(mirror,source_repository="unapproved/mirror"),
    ]
    for invalid in mirror_bad_cases:
        quarantined=run(route,now,no_sec,lambda a,s,p=invalid:p)
        need(quarantined["classification_counts"]=={SOURCE:4}
             and quarantined["sec_current_cik_candidates"]=={}
             and quarantined["mirror_exact_asof_cik_research_candidates"]=={}
             and quarantined["current_mc_2b_attested"] is False,
             "MIRROR_BAD_SOURCE_FALSE_ACCEPT")
    no_snapshot=run(route,now,no_sec,
        lambda a,s:(_ for _ in ()).throw(OSError("no exact snapshot")))
    need(no_snapshot["classification_counts"]=={SOURCE:4}
         and no_snapshot["mirror_verification_state"]==
             "MIRROR_UNAVAILABLE_OR_NOT_EXACT_ASOF",
         "MIRROR_OUTAGE_NOT_FAIL_CLOSED")
    primary=run(route,now,lambda:json.dumps(raw).encode(),
        lambda a,s:(_ for _ in ()).throw(AssertionError("called mirror on SEC success")))
    need(primary["classification_counts"]==obj["classification_counts"]
         and primary["mirror_verification_state"]==
             "NOT_USED_PRIMARY_REQUEST_SUCCEEDED",
         "PRIMARY_SUCCESS_UNNECESSARY_MIRROR_CALL")
    print("XRAY_SEC_CIK_PERSONAL_SELFTEST=PASS_PRIMARY_403_VERIFIED_MIRROR_9_NEGATIVE_NO_MC_NO_ALPHA")


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
    from sec_mirror_cik_shadow import discover as discover_exact_asof
    result=run(obj,now,fetch,mirror_discover=discover_exact_asof)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_SEC_PERSONAL_ISSUER_CIK="+json.dumps({
        "status":result["status"],"asof_et":result["asof_et"],
        "scope":result["scope_count"],
        "counts":result["classification_counts"],
        "mc2b_confirmed":result["current_mc_2b_attested"],
        "sec_state":result["sec_lookup_state"],
        "mirror_state":result["mirror_verification_state"],
        "mirror_research_count":len(result["mirror_exact_asof_cik_research_candidates"]),
        "official_cik_count":len(result["sec_current_cik_candidates"]),"R92":0
    },sort_keys=True))


if __name__=="__main__":
    main()
