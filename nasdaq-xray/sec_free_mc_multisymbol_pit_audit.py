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

def load_scope(offset:int=0,limit:int=0)->tuple[str,list[str]]:
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
    # A representative test is not a full-Nasdaq data coverage attestation.
    if offset==0 and limit==0:
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
    print("XRAY_SEC_MULTI_SCOPE_SELFTEST=PASS_CIK_EXCHANGE_DUPLICATE_FAIL_CLOSED")

def run(offset:int=0,limit:int=0)->dict:
    asof,syms=load_scope(offset,limit)
    result={"schema":"XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1",
            "master_git_blob_sha":git_blob_sha((ROOT/"canonical_current_master_manifest.json").read_bytes()),
            "price_git_blob_sha":git_blob_sha((ROOT/"canonical_current_price_dv30.json").read_bytes()),
            "sample_scope_sha256":hashlib.sha256(("\n".join(syms)+"\n").encode()).hexdigest(),
            "asof_et":asof,"source":"SEC_EDGAR_OFFICIAL",
            "ticker_map_timestamp":"CURRENT_ONLY_NOT_HISTORICAL_PIT",
            "sample_count":len(syms),"batch_offset":offset,"batch_limit":limit,
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
    if result["transport"]!="BLOCKED_FAIR_ACCESS_STOP":
        result["transport"]="SEC_OFFICIAL_MULTI_REQUESTS_COMPLETE_WITH_UNKNOWN_ALLOWED"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=Path)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=0)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    out=run(args.offset,args.limit)
    if args.output:
        args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_MULTI_TRANSPORT="+out["transport"])
    print("XRAY_SEC_MULTI_STATUS_COUNTS="+json.dumps(out["status_counts"],sort_keys=True))
    print("XRAY_SEC_MULTI_REASON_COUNTS="+json.dumps(out.get("reason_counts") or {},sort_keys=True))
    if args.offset==0 and args.limit==0:
        # Current canary symbols are public tickers; NO raw price/shares/filing.
        print("XRAY_SEC_CANARY_REASON_BY_SYMBOL="+json.dumps(
            {k:(out.get("reason_codes") or {}).get(k) for k,v in
             (out.get("statuses") or {}).items() if v=="UNKNOWN"},sort_keys=True))
    print("XRAY_SEC_MULTI_PRIMARY=0_NO_C417_PRODUCTION_AUTHORITY")
    if out["transport"].startswith("BLOCKED_"):
        raise SystemExit(2)

if __name__=="__main__":
    main()
