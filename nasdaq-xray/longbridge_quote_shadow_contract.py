#!/usr/bin/env python3
"""Longbridge Quote-only market cap research contract. NO trading or PRIMARY.

OpenAPI QuoteContext.calc_indexes([symbols], [CalcIndex.TotalMarketValue])
is supported, max 500 symbols/request, with quote permissions separate
from account and trade permissions. It returns a *current* calculated market
value WITHOUT an independent MC-as-of publication timestamp. It MUST NOT
become exact historical point-in-time PRIMARY, regardless of a concurrent
quote-close timestamp. All numeric provider observations remain in RAM.
No raw market cap, symbol classifications or vendor data persisted.

Official docs: https://open.longbridge.com/docs/quote/pull/calc-index
Market data rights must be separately verified for unattended/non-display
automated research. A declared hash is not an actual signed license.
"""
from __future__ import annotations
import argparse
from decimal import Decimal,InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_LONGBRIDGE_QUOTE_MC_SHADOW_V1"
FLOOR=Decimal("2000000000")
MAX_OPENAPI_SYMBOLS_PER_CALL=500
SOURCE="LONGBRIDGE_QUOTE_CALC_INDEX_TOTAL_MARKET_VALUE_UNTIMESTAMPED"
PRICE="nasdaq-xray/canonical_current_price_dv30.json"
MASTER="nasdaq-xray/canonical_current_master_manifest.json"

def blob_sha(content:bytes)->str:
    return hashlib.sha1(("blob "+str(len(content))+"\0").encode()+content).hexdigest()

def hash_lines(rows:list[str])->str:
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def current_scope(root:Path=ROOT)->dict:
    pb=(root/"canonical_current_price_dv30.json").read_bytes()
    mb=(root/"canonical_current_master_manifest.json").read_bytes()
    p=json.loads(pb)
    m=json.loads(mb)
    day=str(p.get("asof_et") or "")
    ps=p.get("pass_symbols")
    ms=m.get("pass_symbols")
    if (not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day)
        or m.get("asof_et")!=day
        or not isinstance(ps,list) or ps!=sorted(set(ps))
        or not isinstance(ms,list) or len(ms)!=len(set(ms))
        or not set(ps).issubset(ms)
        or len(ps)!=p.get("pass_count")
        or hash_lines(ps)!=p.get("pass_hash")
        or p.get("unknown_count")!=0
        or set(ps)&set(p.get("blocked_symbols") or [])
        or any(x.get("execution")!="NONE" or x.get("real_money")!="NO-GO"
               or x.get("unknown_never_pass") is not True for x in (p,m))):
        raise ValueError("CANONICAL_PRICE_MASTER_EPOCH_OR_SCOPE_INVALID")
    return {"asof_et":day,"symbols":ps,
            "price_pass_hash":p["pass_hash"],
            "price_blob_sha":blob_sha(pb),
            "master_blob_sha":blob_sha(mb)}

def rights_attested(env)->bool:
    # Declaration only; compliance review is independently required.
    return (str(env.get("XRAY_LONGBRIDGE_NONDISPLAY_LICENSE_OK","")).lower()=="true"
        and bool(re.fullmatch(r"[a-f0-9]{64}",
                str(env.get("XRAY_LONGBRIDGE_LICENSE_GRANT_SHA256","")))))

def amount(x):
    if isinstance(x,bool) or x is None or not isinstance(x,(str,int,float,Decimal)):
        return None
    try:
        n=Decimal(str(x))
    except InvalidOperation:
        return None
    return n if n.is_finite() and n>0 else None

def telemetry(scope,rows,source_rights_attested=False):
    symbols=scope["symbols"]
    expected=set(symbols)
    records={}
    invalid=0
    outside=0
    duplicates=0
    scope_invalid=False
    if not isinstance(rows,list):
        rows=[]
        scope_invalid=True
    for record in rows:
        if not isinstance(record,dict):
            invalid+=1
            continue
        name=record.get("symbol")
        symbol=name[:-3] if isinstance(name,str) and name.endswith(".US") else None
        if symbol not in expected:
            outside+=1
            continue
        if symbol in records:
            duplicates+=1
            continue
        value=amount(record.get("total_market_value"))
        if value is None:
            invalid+=1
        records[symbol]=value
    present=sum(v is not None for v in records.values())
    count_ge=sum(v>=FLOOR for v in records.values() if v is not None)
    count_lt=sum(v<FLOOR for v in records.values() if v is not None)
    complete=(not scope_invalid and duplicates==0 and outside==0
              and invalid==0 and len(records)==len(expected) and present==len(expected))
    if duplicates or outside or scope_invalid:
        status="BLOCKED_PROVIDER_SCOPE_INTEGRITY"
    elif not complete:
        status="BLOCKED_INCOMPLETE_OR_INVALID_OBSERVATIONS"
    elif not source_rights_attested:
        status="SHADOW_ONLY_PRIMARY_BLOCKED_RIGHTS_AND_PIT"
    else:
        status="SHADOW_ONLY_PRIMARY_BLOCKED_PIT"
    # Only operational aggregate counts, no per-company vendor data survives.
    return {
        "schema":SCHEMA,
        "asof_price_master":scope["asof_et"],
        "price_blob_sha":scope["price_blob_sha"],
        "master_blob_sha":scope["master_blob_sha"],
        "price_pass_hash":scope["price_pass_hash"],
        "price_pass_count":len(expected),
        "source":SOURCE,
        "source_product":"LONG_BRIDGE_QUOTE_ONLY_NO_ACCOUNT_TRADE_SCOPE",
        "max_symbols_per_provider_call":MAX_OPENAPI_SYMBOLS_PER_CALL,
        "minimum_provider_calls_for_current_scope":
            (len(expected)+MAX_OPENAPI_SYMBOLS_PER_CALL-1)//MAX_OPENAPI_SYMBOLS_PER_CALL,
        "status":status,
        "coverage":present,
        "above_2b":count_ge,
        "below_2b":count_lt,
        "missing_or_invalid":len(expected)-present,
        "scope_collision_count":duplicates,
        "scope_outside_count":outside,
        "observed_complete":complete,
        "source_rights_attested":bool(source_rights_attested),
        "source_market_cap_asof_attested":False,
        "date_filtered_market_cap_available":False,
        "independent_filing_acceptance_pit_verified":False,
        "independent_market_cap_crosscheck_verified":False,
        "vendor_numeric_values_persisted":False,
        "candidate_created":False,"r92_created":False,
        "primary_mc_pass_created":False,
        "alpha_authority":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }

def preflight(scope):
    return {
        "schema":SCHEMA,"asof_price_master":scope["asof_et"],
        "price_blob_sha":scope["price_blob_sha"],
        "master_blob_sha":scope["master_blob_sha"],
        "status":"BLOCKED_OPENAPI_RUNTIME_AND_NONDISPLAY_RIGHTS",
        "source":SOURCE,"price_pass_count":len(scope["symbols"]),
        "coverage":0,"source_market_cap_asof_attested":False,
        "source_rights_attested":False,
        "primary_mc_pass_created":False,
        "candidate_created":False,"r92_created":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--selftest",action="store_true")
    opt=p.parse_args()
    scope=current_scope()
    if opt.selftest:
        sample=[{"symbol":s+".US","total_market_value":"2000000000"} for s in scope["symbols"]]
        result=telemetry(scope,sample,rights_attested(os.environ))
        assert result["coverage"]==len(scope["symbols"])
        assert result["primary_mc_pass_created"] is False
        assert result["source_market_cap_asof_attested"] is False
        print("XRAY_LONGBRIDGE_SHADOW=PASS_EXACT_SOURCE_NO_VENDOR_CALLS_NO_PRIMARY")
        return
    if opt.preflight:
        print(json.dumps(preflight(scope),sort_keys=True))
        return
    p.error("only --selftest or --preflight; live vendor API use requires separately approved account authorization and source rights")

if __name__=="__main__":
    main()
