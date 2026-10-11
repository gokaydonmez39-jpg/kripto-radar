#!/usr/bin/env python3
"""P0 HISTORY source-bound 498/17 research reconciliation; fail closed.

The supplied full-scope Alpaca artifact contains per-symbol STATUS ONLY,
not licensed OHLCV. This checker independently binds the exact source PRICE
and MASTER Git blobs and proves official issuer-listing upper bounds via the
*actual production history functions*, without granting HISTORY PRIMARY,
market cap, candidate signals, GO, or automated trading.
"""
from __future__ import annotations
import argparse
import ast
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas_market_calendars as mcal

HERE=Path(__file__).resolve().parent
REPO=HERE.parent
SCHEMA="XRAY_P0_HISTORY_515_OFFICIAL_498_17_RECONCILED_SHADOW_V1"
ALPACA_SCHEMA="XRAY_ALPACA_CURRENT_515_EXACT260_SIP_SHADOW_V1"
IPO_SCHEMA="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1"
SUCCESS="SHADOW_260_DAILY_52_WEEK_OBSERVED"
SHORT="MISSING_EXACT_COMPLETED_SESSIONS"

def require(ok, code):
    if not ok:
        raise ValueError("XRAY_P0_498_17_FAIL_CLOSED:"+code)

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def digest(symbols):
    return hashlib.sha256("\n".join(sorted(symbols)).encode()).hexdigest()

def official_function(records):
    code=(HERE/"history_phase.py").read_text(encoding="utf-8")
    tree=ast.parse(code)
    functions=[x for x in tree.body if isinstance(x,ast.FunctionDef)
               and x.name in ("week_count","official_listing_upper_bound_fail")]
    require(len(functions)==2,"PRODUCTION_LISTING_FN_MISSING")
    ns={"mcal":mcal,"OFFICIAL_RECORDS":records,"HARD_DAILY":260,
        "HARD_WEEKLY":52,"datetime":dt.datetime,"timedelta":dt.timedelta}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),
                 str(HERE/"history_phase.py"),"exec"),ns)
    return ns["official_listing_upper_bound_fail"]

def audit(price,master,alpaca,registry,pbytes,mbytes,*,expected_asof=None):
    asof=price.get("asof_et")
    require(isinstance(asof,str) and asof==master.get("asof_et")
            and asof==alpaca.get("asof_et"),"MISMATCH_ASOF")
    if expected_asof:
        require(asof==expected_asof,"STALE_ASOF")
    require(price.get("execution")=="NONE" and price.get("real_money")=="NO-GO"
            and master.get("execution")=="NONE" and master.get("real_money")=="NO-GO"
            and price.get("unknown_never_pass") is True
            and master.get("unknown_never_pass") is True,"CANONICAL_SOURCE_SAFETY")
    symbols=price.get("pass_symbols")
    require(isinstance(symbols,list) and len(symbols)>0 and
            symbols==sorted(set(symbols)) and
            len(symbols)==price.get("pass_count") and
            digest(symbols)==price.get("pass_hash"),"PRICE_SET_HASH_INVALID")
    require(set(symbols).issubset(set(master.get("pass_symbols") or [])),
            "MASTER_NOT_SUPERSET")
    target=sorted(set(symbols)|{"QQQ"})
    require("QQQ" not in symbols and len(target)==len(symbols)+1,
            "PRICE_QQQ_OVERLAP")
    require(alpaca.get("schema")==ALPACA_SCHEMA
            and alpaca.get("policy")=="C4.17"
            and alpaca.get("control")=="C4.27"
            and alpaca.get("source_price_blob_sha")==blob(pbytes)
            and alpaca.get("source_master_blob_sha")==blob(mbytes)
            and alpaca.get("source_price_pass_hash")==price["pass_hash"]
            and alpaca.get("price_pass_count")==len(symbols),
            "PROVIDER_BLOB_OR_POLICY_MISMATCH")
    require(alpaca.get("status")=="SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY"
            and alpaca.get("expected_scope_count")==len(target)
            and alpaca.get("measured_scope_count")==len(target)
            and alpaca.get("transport_error_class") is None
            and alpaca.get("api_feed")=="sip"
            and alpaca.get("api_timeframe")=="1Day"
            and alpaca.get("api_adjustment")=="raw"
            and alpaca.get("expected_daily_sessions")==260
            and alpaca.get("required_completed_week_closes")==52,
            "HISTORY_SCOPE_OR_PERIOD_NOT_PROVEN")
    counts=alpaca.get("counts")
    missing=alpaca.get("unverified_symbols")
    require(isinstance(counts,dict) and isinstance(missing,dict)
            and set(counts)=={SUCCESS,SHORT}
            and set(missing).issubset(set(target))
            and all(v==SHORT for v in missing.values())
            and counts.get(SHORT)==len(missing)
            and counts.get(SUCCESS)==len(target)-len(missing)
            and sum(counts.values())==len(target),"PARTITION_INEXACT")
    require(alpaca.get("execution")=="NONE" and
            alpaca.get("real_money")=="NO-GO" and
            alpaca.get("unknown_never_pass") is True and
            alpaca.get("vendor_ohlcv_in_artifact") is False and
            alpaca.get("vendor_raw_bars_persisted") is False and
            alpaca.get("canonical_history_pass_created")==0 and
            alpaca.get("primary_mc_pass_created")==0 and
            alpaca.get("r92_created") is False and
            alpaca.get("current_c417_history_primary_authority") is False and
            alpaca.get("source_market_data_rights_independently_attested") is False and
            alpaca.get("corporate_action_adjustment_and_share_class_attested") is False,
            "SHADOW_AUTHORITY_OR_VENDOR_LEAK")
    require(registry.get("schema")==IPO_SCHEMA and
            registry.get("execution")=="NONE" and
            registry.get("real_money")=="NO-GO" and
            registry.get("alpha_authority") is False and
            registry.get("unknown_never_pass") is True,
            "OFFICIAL_IDENTITY_AUTHORITY_INVALID")
    records=registry.get("records")
    require(isinstance(records,dict),"OFFICIAL_REGISTRY_MISSING")
    production=official_function(records)
    reason={"OFFICIAL_LISTING_DATE_HISTORY_UPPER_BOUND"}
    official_short={}
    for sym in symbols:
        if sym not in records:continue
        rec=records[sym]
        if rec.get("mode")!="OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY":
            continue
        urls=rec.get("sources") or []
        require(isinstance(urls,list) and urls
                and all(isinstance(u,str) and u.startswith("https://") for u in urls),
                "MISSING_OFFICIAL_EVIDENCE_"+sym)
        witness=production(sym,asof)
        if witness is not None:
            require(witness.get("proof") in reason
                    and isinstance(witness.get("max_possible_daily_bars"),int)
                    and isinstance(witness.get("max_possible_completed_weeks"),int)
                    and witness["max_possible_daily_bars"]<260
                    and witness["max_possible_completed_weeks"]<52
                    and witness.get("thresholds")=={"daily":260,"weekly_completed":52},
                    "PRODUCTION_LISTING_PROOF_INVALID_"+sym)
            official_short[sym]=witness
    # A too-young listing MUST remain a local nonpass, never fill with
    # predecessor/OTC/synthetic bars; every observed gap must have an official
    # age witness, else UNKNOWN and no reconciled full-scope witness.
    require(set(official_short)==set(missing),
            "OFFICIAL_LISTING_AND_VENDOR_GAP_SETS_DIFFER")
    require("QQQ" not in missing,"BENCHMARK_MISSING")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "source_price_blob_sha":blob(pbytes),
        "source_master_blob_sha":blob(mbytes),
        "price_pass_hash":price["pass_hash"],
        "full_scope_with_qqq":len(target),
        "observed_exact_260_52":counts[SUCCESS],
        "official_listing_ineligible":len(official_short),
        "official_listing_ineligible_symbols":sorted(official_short),
        "other_unresolved_symbols":[],
        "classification":"RECONCILED_OBSERVATION_SHADOW_NOT_PRODUCTION",
        "production_history_primary_pass":0,"c417_primary_mc_pass":0,
        "alpaca_personal_api_research_observed":True,
        "stock_split_ca_adjustment_and_license_rights_asserted":False,
        "can_register_R92":False,"research_go":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True
    }

def selftest():
    # Synthetic TEST symbols; real PRICE, MC, and vendor bar values absent.
    price={"asof_et":"2026-10-09","pass_symbols":["TEST","TWO"],"pass_count":2,
           "pass_hash":digest(["TEST","TWO"]),
           "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    master={"asof_et":"2026-10-09","pass_symbols":["TEST","TWO"],
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    pb=json.dumps(price,sort_keys=True).encode()
    mb=json.dumps(master,sort_keys=True).encode()
    reg={"schema":IPO_SCHEMA,"execution":"NONE","real_money":"NO-GO",
         "alpha_authority":False,"unknown_never_pass":True,
         "records":{"TWO":{"mode":"OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY",
                  "earliest_public_trading_date":"2026-07-01",
                  "sources":["https://www.sec.gov/example/test-only"]}}}
    src={"schema":ALPACA_SCHEMA,"policy":"C4.17","control":"C4.27",
         "asof_et":"2026-10-09","source_price_blob_sha":blob(pb),
         "source_master_blob_sha":blob(mb),
         "source_price_pass_hash":price["pass_hash"],
         "price_pass_count":2,"expected_scope_count":3,"measured_scope_count":3,
         "status":"SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY",
         "transport_error_class":None,"api_feed":"sip","api_timeframe":"1Day",
         "api_adjustment":"raw","expected_daily_sessions":260,
         "required_completed_week_closes":52,
         "counts":{SUCCESS:2,SHORT:1},"unverified_symbols":{"TWO":SHORT},
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
         "vendor_ohlcv_in_artifact":False,"vendor_raw_bars_persisted":False,
         "canonical_history_pass_created":0,"primary_mc_pass_created":0,
         "r92_created":False,"current_c417_history_primary_authority":False,
         "source_market_data_rights_independently_attested":False,
         "corporate_action_adjustment_and_share_class_attested":False}
    def go(p=price,m=master,a=src,r=reg,pp=pb,mm=mb):
        return audit(p,m,a,r,pp,mm)
    result=go()
    require(result["observed_exact_260_52"]==2 and
            result["official_listing_ineligible"]==1 and
            result["production_history_primary_pass"]==0,
            "POSITIVE_FABRICATED_SCOPE")
    def red(label,p=price,m=master,a=src,r=reg,pp=pb,mm=mb):
        try:go(p,m,a,r,pp,mm)
        except ValueError:return
        raise AssertionError("UNSAFE_SHADOW_RECONCILIATION:"+label)
    for field,value in [
       ("asof_et","2026-10-08"),("source_price_blob_sha","0"*40),
       ("source_master_blob_sha","1"*40),("source_price_pass_hash","z"*64),
       ("policy","C4.16"),("control","C4.26"),
       ("expected_scope_count",2),("measured_scope_count",2),
       ("status","INCOMPLETE"),("transport_error_class","HTTP_429"),
       ("api_feed","iex"),("api_timeframe","1Min"),
       ("api_adjustment","split"),("expected_daily_sessions",259),
       ("required_completed_week_closes",51),
       ("counts",{SUCCESS:3,SHORT:0}),
       ("unverified_symbols",{}),
       ("vendor_raw_bars_persisted",True),
       ("current_c417_history_primary_authority",True),
       ("corporate_action_adjustment_and_share_class_attested",True),
       ("canonical_history_pass_created",1),
       ("r92_created",True)
    ]:
       variant=copy.deepcopy(src);variant[field]=value
       red(field,a=variant)
    for field,value in [
        ("earliest_public_trading_date","2025-01-01"),
        ("sources",[]),("mode","CAN_CREATE_PASS")
    ]:
       variant=copy.deepcopy(reg);variant["records"]["TWO"][field]=value
       red(field,r=variant)
    variant=copy.deepcopy(price);variant["pass_symbols"]=["TEST","OTHER"]
    red("PRICE_SET_TAMPERED",p=variant)
    red("RAW_PRICE_BLOB_CHANGED",pp=pb+b"tamper")
    variant=copy.deepcopy(master);variant["pass_symbols"]=["TEST"]
    red("MASTER_MISSING_PRICE_SYMBOL",m=variant)
    print("XRAY_P0_HISTORY_OFFICIAL_RECONCILIATION=PASS_1_SYNTHETIC_POSITIVE_28_NEGATIVE_PYTHON_O_SAFE_NO_AUTHORITY")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--alpaca",type=Path)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest();return
    require(args.alpaca is not None and args.out is not None,
            "MISSING_EXPLICIT_INPUT_PATH")
    pb=(HERE/"canonical_current_price_dv30.json").read_bytes()
    mb=(HERE/"canonical_current_master_manifest.json").read_bytes()
    a=json.loads(args.alpaca.read_text())
    result=audit(json.loads(pb),json.loads(mb),a,
                 json.loads((HERE/"history_official_identity_evidence.json").read_text()),
                 pb,mb)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_P0_HISTORY_OFFICIAL_RECONCILIATION="+result["classification"])
    print("XRAY_P0_HISTORY_COUNTS="+json.dumps(
        {x:result[x] for x in ("full_scope_with_qqq","observed_exact_260_52",
                              "official_listing_ineligible")},sort_keys=True))

if __name__=="__main__":main()
