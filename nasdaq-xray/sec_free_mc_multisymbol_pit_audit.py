#!/usr/bin/env python3
"""Bounded free official SEC issuer-share vintage audit for current PRICE PASS.

Research only: ticker map is CURRENT, not historical PIT as-of listing evidence.
No price, derived market cap, share counts, or C4.17 PRIMARY promotion.
Never publishes vendor market data. Current Nasdaq master limits candidate scope.
"""
from __future__ import annotations
import argparse
import collections
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

def load_scope()->tuple[str,list[str]]:
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
    symbols=[s for s in DEFAULT_CANARIES if s in p and s in m]
    if len(symbols)<3:
        raise ValueError("INSUFFICIENT_CURRENT_CANARY_SCOPE")
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
    print("XRAY_SEC_MULTI_SCOPE_SELFTEST=PASS_CIK_EXCHANGE_DUPLICATE_FAIL_CLOSED")

def run()->dict:
    asof,syms=load_scope()
    result={"schema":"XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1",
            "asof_et":asof,"source":"SEC_EDGAR_OFFICIAL",
            "ticker_map_timestamp":"CURRENT_ONLY_NOT_HISTORICAL_PIT",
            "sample_count":len(syms),"execution":"NONE","real_money":"NO-GO",
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
    for i,sym in enumerate(syms):
        cik=routes.get(sym)
        if not cik:
            status[sym]="UNKNOWN_OFFICIAL_CIK_ROUTE"
            continue
        # Max 2 SEC calls/s, below official fair-access limit. No proxy
        # rotation, no bypass attempts and no unbounded retry.
        try:
            cf=sec.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",ua)
            time.sleep(0.55)
            submissions=sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
            classified=sec.select_shares(cf,submissions,asof,expected_cik=cik)
            status[sym]=str(classified.get("status") or "UNKNOWN")
        except ValueError as exc:
            status[sym]="UNKNOWN_SEC_TRANSPORT_"+str(exc)
        if i+1<len(syms):
            time.sleep(0.55)
    result["statuses"]=dict(sorted(status.items()))
    result["status_counts"]=dict(sorted(collections.Counter(status.values()).items()))
    result["transport"]="SEC_OFFICIAL_MULTI_REQUESTS_COMPLETE_WITH_UNKNOWN_ALLOWED"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    out=run()
    if args.output:
        args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_MULTI_TRANSPORT="+out["transport"])
    print("XRAY_SEC_MULTI_STATUS_COUNTS="+json.dumps(out["status_counts"],sort_keys=True))
    print("XRAY_SEC_MULTI_PRIMARY=0_NO_C417_PRODUCTION_AUTHORITY")
    if out["transport"].startswith("BLOCKED_"):
        raise SystemExit(2)

if __name__=="__main__":
    main()
