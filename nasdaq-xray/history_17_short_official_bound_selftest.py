#!/usr/bin/env python3
"""Fail-only exact listing-age proof for actual 17 short HISTORY symbols.

No market data queries; never replaces missing pre-IPO bars, never admits
HISTORY/MC/PIT license/R92. Registry dates require primary issuer/SEC/Nasdaq
evidence. This validates the actual production upper-bound calculation.
"""
from __future__ import annotations
import ast
import copy
import json
from datetime import datetime,timedelta
from pathlib import Path
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-09"
SHORT=("BSP","CBRS","EQPT","FRVO","HONA","INIO","MDLN","MMED",
       "NAVN","PURR","QNT","SHAZ","SKHY","SOLS","SPCX","VSNT","XE")
def require(ok,label):
    if not ok:raise ValueError("XRAY_SHORT_17_OFFICIAL_FAIL_ONLY:"+label)

def isolated_prod(records):
    text=(ROOT/"history_phase.py").read_text()
    tree=ast.parse(text)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
               n.name in ("week_count","official_listing_upper_bound_fail")]
    require(len(functions)==2,"PRODUCTION_FUNCTIONS_UNAVAILABLE")
    ns={"OFFICIAL_RECORDS":records,"mcal":mcal,"HARD_DAILY":260,
        "HARD_WEEKLY":52,"datetime":datetime,"timedelta":timedelta}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),
                 str(ROOT/"history_phase.py"),"exec"),ns)
    return ns["official_listing_upper_bound_fail"]

def guard(records,scope):
    require(set(SHORT)<=set(scope),"PRICE_SCOPE_SHORT_COHORT_DRIFT")
    require(all(s in records for s in SHORT),"OFFICIAL_LISTING_PROOF_MISSING")
    prod=isolated_prod(records)
    proofs={}
    for symbol in SHORT:
        item=records[symbol]
        require(item.get("mode")=="OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY",
                "ROLE_TAMPERING_"+symbol)
        sources=item.get("sources")
        require(isinstance(sources,list) and bool(sources)
                and all(isinstance(x,str) and x.startswith((
                "https://www.sec.gov/","https://www.nasdaq.com/",
                "https://www.nasdaqtrader.com/","https://classic.nasdaqtrader.com/",
                "https://ir.quantinuum.com/","https://investors.navan.com/",
                "https://navan.gcs-web.com/","https://investors.versantmedia.com/",
                "https://investors.honeywell.com/","https://www.torm.com/",
                "https://investors.maxlinear.com/")) for x in sources),
                "OFFICIAL_SOURCE_MISSING_"+symbol)
        first=item.get("earliest_public_trading_date")
        try:dt=datetime.fromisoformat(first).date()
        except (TypeError,ValueError) as err:
            raise ValueError("XRAY_SHORT_17_OFFICIAL_FAIL_ONLY:INVALID_FIRST_DATE_"+symbol) from err
        require(dt.isoformat()==first and first<=ASOF,"INVALID_FIRST_DATE_"+symbol)
        outcome=prod(symbol,ASOF)
        require(isinstance(outcome,dict),"FAIL_ONLY_BOUND_NOT_ESTABLISHED_"+symbol)
        require(outcome.get("proof")=="OFFICIAL_LISTING_DATE_HISTORY_UPPER_BOUND",
                "UNEXPECTED_BOUND_CLASS_"+symbol)
        require(isinstance(outcome.get("max_possible_daily_bars"),int)
                and 0<outcome["max_possible_daily_bars"]<260,
                "DAILY_260_FALSE_ADMISSION_"+symbol)
        require(isinstance(outcome.get("max_possible_completed_weeks"),int)
                and 0<outcome["max_possible_completed_weeks"]<52,
                "WEEKLY_52_FALSE_ADMISSION_"+symbol)
        require(outcome.get("thresholds")=={"daily":260,"weekly_completed":52},
                "ALPHA_THRESHOLD_DRIFT_"+symbol)
        proofs[symbol]={"max_possible_daily_bars":outcome["max_possible_daily_bars"],
                        "max_possible_completed_weeks":outcome["max_possible_completed_weeks"]}
    return proofs

def main():
    registry=json.loads((ROOT/"history_official_identity_evidence.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    require(price.get("asof_et")==ASOF,"PRICE_ASOF_DRIFT")
    require(price.get("execution")=="NONE" and price.get("real_money")=="NO-GO",
            "PRICE_SAFETY_DRIFT")
    require(registry.get("execution")=="NONE" and registry.get("real_money")=="NO-GO"
            and registry.get("alpha_authority") is False and
            registry.get("unknown_never_pass") is True,"REGISTRY_SAFETY_DRIFT")
    records=registry["records"];scope=price["pass_symbols"]
    valid=guard(records,scope)
    require(len(valid)==17,"EXACT_SHORT_COHORT")
    def negative(name,recs,syms):
        try:guard(recs,syms)
        except ValueError:return
        raise AssertionError("OFFICIAL_SHORT_17_NEGATIVE_BYPASS:"+name)
    negative("MISSING_PURR",{k:v for k,v in records.items() if k!="PURR"},scope)
    negative("MISSING_SHAZ",{k:v for k,v in records.items() if k!="SHAZ"},scope)
    bad=copy.deepcopy(records);bad["PURR"]["mode"]="SHADOW_HISTORY_CAN_PASS"
    negative("ROLE_CHANGE",bad,scope)
    bad=copy.deepcopy(records);bad["SHAZ"]["earliest_public_trading_date"]="2025-01-01"
    negative("HISTORY_260_FALSE_BACKFILL",bad,scope)
    bad=copy.deepcopy(records);bad["PURR"]["sources"]=[]
    negative("NO_OFFICIAL_AUTHORITY",bad,scope)
    negative("PRICE_SCOPE_CHANGED",records,[x for x in scope if x!="FRVO"])
    print("XRAY_SHORT_17_OFFICIAL_NASDAQ_FAIL_ONLY=PASS_17_POSITIVE_6_NEGATIVE_PYTHON_O_SAFE_NO_HISTORY_PASS")

if __name__=="__main__":main()
