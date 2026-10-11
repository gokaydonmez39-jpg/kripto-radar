#!/usr/bin/env python3
"""Bounded free official SEC issuer-share vintage audit for current PRICE PASS.

Research only: ticker map is CURRENT, not historical PIT as-of listing evidence.
No price, derived market cap, share counts, or C4.17 PRIMARY promotion.
Never publishes vendor market data. Current Nasdaq master limits candidate scope.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import time
from pathlib import Path
import sec_official_free_mc_transport_probe as sec

ROOT=Path(__file__).resolve().parent
SEC_MAP="https://www.sec.gov/files/company_tickers_exchange.json"
DEFAULT_CANARIES=("AAPL","MSFT","NVDA","AMZN","GOOGL","META","ADBE","ADI")
MAX_FULL_PRICE_PASS_SCOPE=650  # bounded ~15 min at <=2 SEC requests/s

def map_ciks(source:dict)->dict:
    fields=source.get("fields") or []
    rows=source.get("data") or []
    if not all(k in fields for k in ("ticker","cik","exchange")):
        raise ValueError("SEC_TICKER_EXCHANGE_FIELDS_MISSING")
    i={k:fields.index(k) for k in ("ticker","cik","exchange")}
    route={}
    duplicates=set()
    for row in rows:
        if not isinstance(row,list) or len(row)<len(fields):
            continue
        ticker=str(row[i["ticker"]] or "").strip().upper()
        exchange=str(row[i["exchange"]] or "").strip().lower()
        try:
            cik=int(row[i["cik"]])
        except (ValueError,TypeError):
            continue
        if not ticker or cik<=0 or exchange!="nasdaq":
            continue
        if ticker in route:
            duplicates.add(ticker)
        else:
            route[ticker]=f"{cik:010d}"
    for ticker in duplicates:
        route.pop(ticker,None)
    return route

def git_blob_sha(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def load_scope(offset:int=0,limit:int=0,*,full_current:bool=False)->tuple[str,list[str]]:
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    asof=price.get("asof_et")
    p=price.get("pass_symbols") or []
    m=master.get("pass_symbols") or []
    if not isinstance(asof,str) or master.get("asof_et")!=asof:
        raise ValueError("CANONICAL_ASOF_MISMATCH")
    if len(set(p))!=len(p) or len(p)!=price.get("pass_count"):
        raise ValueError("PRICE_SCOPE_INVALID")
    if len(set(m))!=len(m) or not set(p).issubset(set(m)):
        raise ValueError("MASTER_SCOPE_INVALID")
    # Full current PRICE scope is dynamic; never silently truncate a changing
    # daily universe to the historical 514-symbol cutoff.
    if full_current:
        if offset!=0 or limit!=0:
            raise ValueError("FULL_SCOPE_REJECTS_OFFSET_AND_LIMIT")
        if not p or len(p)>MAX_FULL_PRICE_PASS_SCOPE:
            raise ValueError("FULL_PRICE_PASS_EXCEEDS_BOUNDED_SEC_CENSUS")
        symbols=sorted(p)
    # A representative test is not a full-Nasdaq data coverage attestation.
    elif offset==0 and limit==0:
        symbols=[s for s in DEFAULT_CANARIES if s in p and s in m]
        if len(symbols)<3:
            raise ValueError("INSUFFICIENT_CURRENT_CANARY_SCOPE")
    else:
        # Deterministic, unique, bounded slice; source identity always binds
        # to the exact PRICE/Master PASS intersection in the checked-out main.
        if not (0<=offset<len(p) and 1<=limit<=514):
            raise ValueError("INVALID_BOUNDED_BATCH")
        symbols=sorted(p)[offset:offset+limit]
        if not symbols: raise ValueError("EMPTY_SEC_BATCH")
    return asof,symbols

def root_cause_class(status:str,reason:str)->str:
    """A source-remediation queue only; no authority for C4.17 MC or R92."""
    if status=="SHADOW_SHARES_VINTAGE_ONLY":
        return "PIT_SHARES_PRESENT_MORE_VALIDATION_REQUIRED"
    if reason in ("SEC_HTTP_403","SEC_HTTP_429","SEC_FAIR_ACCESS_STOP"):
        return "FAIR_ACCESS_HALT"
    if status in ("UNKNOWN","UNKNOWN_SEC_TRANSPORT","UNKNOWN_OFFICIAL_CIK_ROUTE"):
        return {
            "NO_DEI_BUT_GAAP_SHARES_AVAILABLE_CLASS_UNRESOLVED":
                "ISSUER_SHARE_CLASS_AMBIGUITY",
            "NO_FRESH_ACCEPTANCE_BOUND_SINGLE_ENTITY_SHARES":
                "SEC_FILING_VINTAGE_NOT_PIT_VERIFIED",
            "NO_SEC_DEI_OR_GAAP_SHARES_FACT":
                "SEC_SHARES_TAG_ABSENT",
            "SEC_SHARES_STALE_OR_FUTURE_OBSERVATION":
                "SEC_SHARES_FACT_OUTSIDE_ASOF_WINDOW",
            "SEC_HTTP_404": "SEC_IDENTIFIER_OR_RESOURCE_REVIEW",
            "SEC_CURRENT_CIK_ROUTE_MISSING":"SEC_IDENTIFIER_OR_RESOURCE_REVIEW",
        }.get(reason,"UNRESOLVED_SOURCE")
    return "UNRESOLVED_SOURCE"


def selftest():
    rows={"fields":["cik","ticker","title","exchange"],
          "data":[[320193,"AAPL","Apple Inc.","Nasdaq"],
                  [1,"TSM","Example","NYSE"],
                  [789,"DUP","A","Nasdaq"],
                  [790,"DUP","B","Nasdaq"],
                  [0,"ZERO","Invalid","Nasdaq"],
                  [101,"QQQ","Index ETF","Nasdaq"]]}
    result=map_ciks(rows)
    assert result["AAPL"]=="0000320193"
    assert "TSM" not in result and "DUP" not in result and "ZERO" not in result
    # Nasdaq-listed ETFs could be in the SEC ticker map, but cannot enter
    # without explicit master and PRICE PASS intersections.
    assert result["QQQ"]=="0000000101"
    for bad in ({}, {"fields":["ticker"],"data":[]}, {"fields":[]}):
        try:map_ciks(bad)
        except ValueError:pass
        else:raise AssertionError("SEC_MAP_INVALID_SCHEMA_ACCEPTED")
    for bad_offset,bad_limit in ((-1,1),(0,-1),(0,515)):
        try:load_scope(bad_offset,bad_limit)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_BATCH_INPUT_ACCEPTED")
    # The full-scope mode is a separate explicit switch; the default
    # continues to mean a small canary probe.
    asof, full = load_scope(full_current=True)
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    assert asof==price["asof_et"]
    assert full==sorted(price["pass_symbols"])
    for off,lim in ((1,0),(0,1),(-1,1)):
        try:load_scope(off,lim,full_current=True)
        except ValueError:pass
        else:raise AssertionError("FULL_SCOPE_MUST_NOT_SLICE_OR_TRUNCATE")
    categories={
        ("SHADOW_SHARES_VINTAGE_ONLY","SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED"):"PIT_SHARES_PRESENT_MORE_VALIDATION_REQUIRED",
        ("UNKNOWN","NO_DEI_BUT_GAAP_SHARES_AVAILABLE_CLASS_UNRESOLVED"):"ISSUER_SHARE_CLASS_AMBIGUITY",
        ("UNKNOWN","NO_FRESH_ACCEPTANCE_BOUND_SINGLE_ENTITY_SHARES"):"SEC_FILING_VINTAGE_NOT_PIT_VERIFIED",
        ("UNKNOWN","NO_SEC_DEI_OR_GAAP_SHARES_FACT"):"SEC_SHARES_TAG_ABSENT",
        ("UNKNOWN","SEC_SHARES_STALE_OR_FUTURE_OBSERVATION"):"SEC_SHARES_FACT_OUTSIDE_ASOF_WINDOW",
        ("UNKNOWN_SEC_TRANSPORT","SEC_HTTP_404"):"SEC_IDENTIFIER_OR_RESOURCE_REVIEW"}
    for (status,reason),expected in categories.items():
        assert root_cause_class(status,reason)==expected,("WRONG_SEC_REMEDIATION",reason)
    assert root_cause_class("UNKNOWN","SEC_HTTP_429")=="FAIR_ACCESS_HALT"
    assert root_cause_class("UNKNOWN","UNCLASSIFIED")=="UNRESOLVED_SOURCE"
    print("XRAY_SEC_MULTI_SCOPE_SELFTEST=PASS_CIK_EXCHANGE_DUPLICATE_FAIL_CLOSED")

def run(offset:int=0,limit:int=0,*,full_current:bool=False)->dict:
    asof,syms=load_scope(offset,limit,full_current=full_current)
    result={"schema":"XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1",
            "master_git_blob_sha":git_blob_sha((ROOT/"canonical_current_master_manifest.json").read_bytes()),
            "price_git_blob_sha":git_blob_sha((ROOT/"canonical_current_price_dv30.json").read_bytes()),
            "sample_scope_sha256":hashlib.sha256(("\n".join(syms)+"\n").encode()).hexdigest(),
            "asof_et":asof,"source":"SEC_EDGAR_OFFICIAL",
            "ticker_map_timestamp":"CURRENT_ONLY_NOT_HISTORICAL_PIT",
            "sample_count":len(syms),"batch_offset":offset,
            "batch_limit":len(syms) if full_current else limit,
            "full_current_price_pass_scope":bool(full_current),
            "execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"production_alpha_authority":False,
            "c417_primary_mc_count":0,"market_cap_calculated":False,
            "price_binding_attested":False,
            "corporate_action_binding_attested":False,
            "no_real_candidate_claim":True,
            "official_exchange_current_mapping_only":True,
            "statuses":{},"status_counts":{},"transport":"NOT_RUN"}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    if not sec.valid_operator_contact(ua):
        return dict(result,transport="BLOCKED_CONFIG",status_counts={"CONTACT_MISSING_OR_INVALID":len(syms)})
    try:
        official=sec.get_json(SEC_MAP,ua)
        routes=map_ciks(official)
    except ValueError as exc:
        return dict(result,transport="BLOCKED_MAP",status_counts={str(exc):len(syms)})
    result["transport"]="SEC_MAP_HTTP200_VALIDATED"
    status={}
    reason_codes={}
    for i,sym in enumerate(syms):
        cik=routes.get(sym)
        if not cik:
            status[sym]="UNKNOWN_OFFICIAL_CIK_ROUTE"
            reason_codes[sym]="SEC_CURRENT_CIK_ROUTE_MISSING"
            continue
        # Max 2 SEC calls/s, below official fair-access limit. No proxy
        # rotation, no bypass attempts and no unbounded retry.
        try:
            cf=sec.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",ua)
            time.sleep(0.55)
            submissions=sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
            classified=sec.select_shares(cf,submissions,asof,expected_cik=cik)
            status[sym]=str(classified.get("status") or "UNKNOWN")
            reason_codes[sym]=str(classified.get("reason") or "SEC_REASON_UNKNOWN")
        except ValueError as exc:
            status[sym]="UNKNOWN_SEC_TRANSPORT"
            # SEC transport failures never authorize a share-count PASS.
            reason_codes[sym]=str(exc)
            if str(exc) in ("SEC_HTTP_403","SEC_HTTP_429"):
                # Do not hammer SEC when blocked; no retry or bypass.
                for unattempted in syms[i+1:]:
                    status[unattempted]="UNKNOWN_NOT_ATTEMPTED_UPSTREAM_SEC_BLOCK"
                    reason_codes[unattempted]="SEC_FAIR_ACCESS_STOP"
                result["transport"]="BLOCKED_FAIR_ACCESS_STOP"
                break
        if i+1<len(syms):
            time.sleep(0.55)
    result["statuses"]=dict(sorted(status.items()))
    result["reason_codes"]=dict(sorted(reason_codes.items()))
    result["status_counts"]=dict(sorted(collections.Counter(status.values()).items()))
    result["reason_counts"]=dict(sorted(collections.Counter(reason_codes.values()).items()))
    # Deterministic root-cause routing exposes the exact 168 unresolved
    # reasons without inventing shares, quote prices or C4.17 PRIMARY passes.
    remediation={sym:root_cause_class(status[sym],reason_codes[sym])
                 for sym in status}
    result["remediation_counts"]=dict(sorted(collections.Counter(
        remediation.values()).items()))
    result["remediation_count_exact"]=sum(result["remediation_counts"].values())==len(syms)
    if not result["remediation_count_exact"]:
        raise ValueError("SEC_REMEDIATION_SCOPE_MISMATCH")
    if result["transport"]!="BLOCKED_FAIR_ACCESS_STOP":
        result["transport"]="SEC_OFFICIAL_MULTI_REQUESTS_COMPLETE_WITH_UNKNOWN_ALLOWED"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=Path)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=0)
    p.add_argument("--all-price-pass",action="store_true")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    out=run(args.offset,args.limit,full_current=args.all_price_pass)
    if args.output:
        args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_MULTI_TRANSPORT="+out["transport"])
    print("XRAY_SEC_MULTI_STATUS_COUNTS="+json.dumps(out["status_counts"],sort_keys=True))
    print("XRAY_SEC_MULTI_REASON_COUNTS="+json.dumps(out.get("reason_counts") or {},sort_keys=True))
    if args.offset==0 and args.limit==0 and not args.all_price_pass:
        # Current canary symbols are public tickers; NO raw price/shares/filing.
        print("XRAY_SEC_CANARY_REASON_BY_SYMBOL="+json.dumps(
            {k:(out.get("reason_codes") or {}).get(k) for k,v in
             (out.get("statuses") or {}).items() if v=="UNKNOWN"},sort_keys=True))
    print("XRAY_SEC_REMEDIATION_COUNTS="+json.dumps(out.get("remediation_counts") or {},sort_keys=True))
    print("XRAY_SEC_MULTI_PRIMARY=0_NO_C417_PRODUCTION_AUTHORITY")
    if out["transport"].startswith("BLOCKED_"):
        raise SystemExit(2)

if __name__=="__main__":
    main()
