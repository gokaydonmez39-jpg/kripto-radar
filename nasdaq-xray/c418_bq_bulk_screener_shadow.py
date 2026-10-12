#!/usr/bin/env python3
"""Strict read-only BusinessQuant bulk screener response guard (NO PRIMARY).

The public screener documentation permits large latest-snapshot pages but has
no historical ASOF selector or SEC acceptance-time lineage. No HTTP/API key
handling in this file; licensed caller supplies an ephemeral response. This
contract persists only aggregate counts, never vendor market caps or CIKs.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path

SCHEMA = "XRAY_BQ_BULK_LATEST_SCREENER_SHADOW_V1"
MAX_PAGE_SIZE = 10000
MAX_PAGES_RESEARCH = 3


def require(ok: bool, code: str) -> None:
    if not ok: raise ValueError("BQ_BULK_SCREENER_FAIL_CLOSED:"+code)


def test_positive_real(v: object) -> bool:
    return type(v) in (int,float) and math.isfinite(v) and v > 0


def validate(cohort: list[str], pages: list[dict], *, rights_grant: bool=False) -> dict:
    require(isinstance(cohort,list) and all(isinstance(s,str) and s and s==s.upper() for s in cohort),"BAD_COHORT")
    require(len(cohort)==len(set(cohort)),"DUPLICATE_COHORT")
    require(isinstance(pages,list) and 1<=len(pages)<=MAX_PAGES_RESEARCH,"BAD_PAGE_COUNT")
    require(rights_grant is True,"MISSING_UNATTENDED_RESEARCH_GRANT")
    target=set(cohort)
    seen=set(); tracked=set(); total=0
    for num,response in enumerate(pages,1):
        require(isinstance(response,dict),"BAD_RESPONSE")
        meta=response.get("metadata")
        rows=response.get("data")
        require(isinstance(meta,dict) and isinstance(rows,list),"BAD_VENDOR_SCHEMA")
        require(type(meta.get("page")) is int and meta["page"]==num,"PAGE_SEQUENCE")
        require(type(meta.get("limit")) is int and 1<=meta["limit"]<=MAX_PAGE_SIZE,"PAGE_LIMIT")
        require(type(meta.get("total_pages")) is int and 1<=meta["total_pages"]<=MAX_PAGES_RESEARCH,"TOTAL_PAGES_LIMIT")
        require(type(meta.get("total_records")) is int and meta["total_records"]>=0,"TOTAL_RECORDS")
        require(meta["total_pages"]==len(pages),"PAGINATION_INCOMPLETE")
        require(len(rows)<=meta["limit"],"PAGE_OVERSIZED")
        for r in rows:
            require(isinstance(r,dict),"BAD_ROW")
            symbol=r.get("ticker")
            require(isinstance(symbol,str) and symbol and symbol==symbol.upper(),"BAD_TICKER")
            require(symbol not in seen,"DUPLICATE_SYMBOL_PAGES")
            seen.add(symbol)
            if symbol not in target:
                continue
            # CIK is a positive integer; recording is deliberately forbidden.
            require(type(r.get("cik")) is int and r["cik"]>0,"INVALID_CIK")
            require(test_positive_real(r.get("Market Capitalization")),"BAD_LATEST_MC")
            tracked.add(symbol)
        total+=len(rows)
    require(total==pages[0]["metadata"]["total_records"],"TOTAL_RECORDS_MISMATCH")
    return {
      "schema":SCHEMA,"source":"BUSINESSQUANT_SCREENER_LATEST_NOT_HISTORICAL",
      "cohort_count":len(cohort),"observed_vendor_universe_count":total,
      "matched_cohort_count":len(tracked),"missing_cohort_count":len(target-tracked),
      "vendor_page_count":len(pages),"full_cohort_covered":len(tracked)==len(target),
      "source_historical_asof_attested":False,"SEC_acceptance_PIT_attested":False,
      "can_create_PRIMARY":False,"can_register_R92":False,"can_enable_G9":False,
      "status":"REFERENCE_LATEST_SCREENER_NOT_PIT_NOT_PRIMARY",
      "reason_codes":["NO_VENDOR_HISTORICAL_ASOF_SELECTOR", "NO_FILING_ACCEPTANCE_PIT_PROOF", "NO_INDEPENDENT_UPSTREAM_PROOF"],
      "execution":"NONE","real_money":"NO-GO","vendor_market_caps_or_ciks_stored":False
    }


def selftest() -> None:
    row=lambda s,c,v:{"ticker":s,"cik":c,"Market Capitalization":v}
    fixture={"metadata":{"page":1,"limit":10000,"total_pages":1,"total_records":3},
             "data":[row("AAPL",320193,4e12),row("AAON",824142,7e9),row("PLTR",1321655,5e11)]}
    r=validate(["AAPL","PLTR"],[fixture],rights_grant=True)
    require(r["matched_cohort_count"]==2 and r["full_cohort_covered"] is True,"STRUCTURAL_POSITIVE")
    require(r["can_create_PRIMARY"] is False and not r["source_historical_asof_attested"],"FALSE_PRIMARY")
    zero=validate(["MISSING"],[fixture],rights_grant=True)
    require(zero["matched_cohort_count"]==0 and zero["missing_cohort_count"]==1,"MISSING_IS_NOT_PASS")
    failcases=[
      ("MISSING_UNATTENDED_RESEARCH_GRANT",lambda v:v,False),
      ("INVALID_CIK",lambda v:v["data"][0].update(cik=None),True),
      ("BAD_LATEST_MC",lambda v:v["data"][0].update({"Market Capitalization":float("nan")}),True),
      ("BAD_TICKER",lambda v:v["data"][0].update(ticker="aapl"),True),
      ("TOTAL_PAGES_LIMIT",lambda v:v["metadata"].update(total_pages=4),True),
      ("TOTAL_RECORDS_MISMATCH",lambda v:v["metadata"].update(total_records=4),True),
      ("PAGE_LIMIT",lambda v:v["metadata"].update(limit=0),True),
      ("PAGINATION_INCOMPLETE",lambda v:v["metadata"].update(total_pages=2),True),
      ("BAD_ROW",lambda v:v["data"].__setitem__(0,None),True),
      ("PAGE_SEQUENCE",lambda v:v["metadata"].update(page=2),True),
    ]
    for reason,mutate,right in failcases:
        data=copy.deepcopy(fixture);mutate(data)
        try:validate(["AAPL","PLTR"],[data],rights_grant=right)
        except ValueError as err:require(reason in str(err),"WRONG_REASON:"+reason)
        else:raise RuntimeError("BULK_SCREENER_UNSAFE_ACCEPT:"+reason)
    d=copy.deepcopy(fixture)
    d["data"][1]["ticker"]="AAPL"
    try:validate(["AAPL"],[d],rights_grant=True)
    except ValueError as err: require("DUPLICATE_SYMBOL_PAGES" in str(err),"DUPLICATE_WRONG_REASON")
    else: raise RuntimeError("DUPLICATE_ACCEPTED")
    print("XRAY_BQ_BULK_SCREENER=PASS_2_STRUCTURAL_11_NEGATIVE_NO_PIT_NO_PRIMARY_NO_MC_VALUES")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args=ap.parse_args()
    if not args.selftest:
        raise SystemExit("SHADOW_CONTRACT_ONLY_NO_NETWORK_NO_PRIMARY_RUN_WITH_SELFTEST")
    selftest()

if __name__=="__main__":main()
