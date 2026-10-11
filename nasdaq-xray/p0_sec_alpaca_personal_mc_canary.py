#!/usr/bin/env python3
"""P0 Personal Research: FREE SEC filing-vintage shares * Alpaca SIP EOD.
AAPL canary only. Computes in memory; no raw shares/prices or derived
market cap are published, and no C4.17 PRIMARY promotion is possible.
"""
from __future__ import annotations
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from sec_official_free_mc_transport_probe import (
    select_shares, get_json, accession_acceptance_index,
    official_nasdaq_close_utc, valid_operator_contact
)
from alpaca_free_sip_shadow_guard import request_batch, timestamp_date, sufficient_delay
from current_history_source_request import sha256_lines

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_SEC_ALPACA_MC_PERSONAL_CANARY_SHADOW_V1"
SEC_CIK="0000320193"
TICKER="AAPL"
FLOOR=Decimal("2000000000")
UTC=dt.timezone.utc
EAST=ZoneInfo("America/New_York")

def require(ok,code):
    if not ok:raise ValueError("P0_SEC_ALPACA_MC_FAIL_CLOSED:"+code)

def exact_accepted_share_count(facts,sub,asof,*,cik=SEC_CIK):
    # Use the existing strict SEC PIT classifier FIRST, not our own heuristic.
    finding=select_shares(facts,sub,asof,expected_cik=cik)
    require(finding.get("status")=="SHADOW_SHARES_VINTAGE_ONLY",
            "SEC_NO_EXACT_VINTAGE")
    idx=accession_acceptance_index(sub)
    close=official_nasdaq_close_utc(asof)
    values=set()
    for item in ((((facts.get("facts") or {}).get("dei") or {})
                .get("EntityCommonStockSharesOutstanding") or {})
                .get("units") or {}).get("shares") or []:
        if not isinstance(item,dict):continue
        if item.get("end")!=finding.get("observation_date"):continue
        acc=item.get("accn")
        submission=idx.get(acc)
        if not submission or item.get("filed")!=submission.get("filed"):continue
        stamp=submission.get("accepted_at")
        if not isinstance(stamp,str):continue
        try:
            accepted=dt.datetime.fromisoformat(stamp.replace("Z","+00:00"))
            share=item.get("val")
            if accepted.tzinfo is None or accepted.date().isoformat()!=finding["selected_filing_date"]:
                continue
            if stamp.endswith("Z") or stamp.endswith("+00:00"):
                eastern=accepted.replace(tzinfo=None).replace(tzinfo=EAST).astimezone(UTC)
                if not (accepted<=close and eastern<=close):continue
            elif accepted>close:continue
            if type(share) is not int or share<=0:continue
            if item.get("form") not in {"10-K","10-Q","10-K/A","10-Q/A"}:continue
            if (dt.date.fromisoformat(asof)-dt.date.fromisoformat(item["end"])).days>120:continue
            values.add(share)
        except (TypeError,ValueError,KeyError):
            continue
    require(len(values)==1,"LATEST_OFFICIAL_VINTAGE_NOT_UNIQUE")
    return next(iter(values)),finding

def measure(price,master,facts,sub,bars,asof,*,symbol=TICKER,cik=SEC_CIK):
    require(isinstance(symbol,str) and symbol and isinstance(cik,str)
            and len(cik)==10 and cik.isdigit(),"CANARY_IDENTITY_INVALID")
    require(price.get("asof_et")==master.get("asof_et")==asof,
            "CANONICAL_ASOF_DRIFT")
    require(symbol in (price.get("pass_symbols") or []),"PRICE_NOT_IN_CANONICAL_PASS")
    require(symbol in (master.get("pass_symbols") or []),"MASTER_NO_EXACT_SECURITY")
    require(price.get("unknown_never_pass") is True and master.get("unknown_never_pass") is True
            and price.get("execution")=="NONE" and master.get("execution")=="NONE"
            and price.get("real_money")=="NO-GO" and master.get("real_money")=="NO-GO",
            "CANONICAL_SAFETY_INVALID")
    require(sha256_lines(price["pass_symbols"])==price["pass_hash"],
            "PRICE_PASS_SHA256_INVALID")
    require(str(facts.get("cik")).lstrip("0")==cik.lstrip("0") and
            str(sub.get("cik")).lstrip("0")==cik.lstrip("0"),
            "ISSUER_CIK_MISMATCH")
    shares,provenance=exact_accepted_share_count(facts,sub,asof,cik=cik)
    require(isinstance(bars,list) and len(bars)==1,"ALPACA_ONE_SESSION_REQUIRED")
    bar=bars[0]
    require(timestamp_date(bar.get("t"))==dt.date.fromisoformat(asof),
            "WRONG_ALPACA_ET_SESSION")
    nums=[bar.get(k) for k in ("o","h","l","c","v")]
    require(all(type(x) in (float,int) and not isinstance(x,bool)
                for x in nums),"BAR_TYPE_INVALID")
    try:
        o,h,l,c,v=(Decimal(str(x)) for x in nums)
        require(all(x.is_finite() and x>0 for x in (o,h,l,c,v))
                and h>=max(o,l,c) and l<=min(o,c),
                "INVALID_EOD_OHLCV")
        marketcap=Decimal(shares)*c
        require(marketcap.is_finite() and marketcap>0,"MC_ARITHMETIC")
    except (ValueError,InvalidOperation) as exc:
        raise ValueError("P0_SEC_ALPACA_MC_FAIL_CLOSED:BAD_MARKET_DATA") from exc
    # SEC EntityCommonStockSharesOutstanding is entity-level, not necessarily
    # the traded share CLASS. Issuance/splits/ADR from the filing to EOD
    # remain unverified. No independent primary MC crosscheck. Do not promote.
    return {"schema":SCHEMA,"asof_et":asof,"symbol":symbol,
            "status":"SHADOW_SEC_PIT_AND_SIP_CLOSE_ARITHMETIC_VERIFIED_CLASS_CA_UNPROVEN",
            "SEC_exact_CIK_and_filing_vintage_checked":True,
            "SEC_share_age_days":provenance.get("shares_age_days"),
            "Alpaca_sip_one_session_et_midnight_verified":True,
            "calculated_MC_above_2B_unadjusted":bool(marketcap>=FLOOR),
            "official_tradable_share_class_verified":False,
            "corporate_actions_from_SEC_filing_to_asof_verified":False,
            "independent_market_cap_crosscheck_verified":False,
            "C417_PRIMARY_MC":False,"C417_CURRENT_PRIMARY_CREATED":0,
            "R92_created":False,"GO":False,"execution":"NONE","real_money":"NO-GO",
            "numeric_shares_price_or_marketcap_persisted":False}

def selftest():
    asof="2026-10-09"
    p={"asof_et":asof,"pass_symbols":[TICKER],
       "pass_hash":sha256_lines([TICKER]),"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True}
    m={"asof_et":asof,"pass_symbols":[TICKER],
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    acc="0000320193-26-000999"
    f={"cik":320193,"facts":{"dei":{"EntityCommonStockSharesOutstanding":{
      "units":{"shares":[{"form":"10-Q","end":"2026-09-30",
          "filed":"2026-10-05","accn":acc,"val":1000000000}]}}}}}
    sub={"cik":320193,"filings":{"recent":{
        "accessionNumber":[acc],"form":["10-Q"],
        "filingDate":["2026-10-05"],
        "acceptanceDateTime":["2026-10-05T12:00:00Z"]}}}
    bar={"t":"2026-10-09T04:00:00Z",
         "o":10.0,"h":11.0,"l":9.0,"c":10.0,"v":1000}
    from copy import deepcopy
    result=measure(p,m,f,sub,[bar],asof)
    require(result["calculated_MC_above_2B_unadjusted"] and
            not result["C417_PRIMARY_MC"] and not result["GO"],
            "CANARY_POSITIVE")
    tests=0
    def red(label,P=p,M=m,F=f,S=sub,B=[bar],A=asof):
        nonlocal tests
        tests+=1
        try:measure(P,M,F,S,B,A)
        except (ValueError,KeyError,TypeError):return
        raise AssertionError("FALSE_MC_CANARY_ACCEPTED:"+label)
    for key,val in [("val",0),("val",True),("val",1.5),
                     ("end","2025-01-01"),("filed","2026-10-10"),
                     ("accn","UNVERIFIED")]:
        ff=deepcopy(f);ff["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0][key]=val
        red("SEC_"+key,F=ff)
    for key,val in [("acceptanceDateTime",["2026-10-10T13:00:00Z"]),
                    ("filingDate",["2026-10-06"]),
                    ("accessionNumber",["0000320193-26-000998"])]:
        ss=deepcopy(sub);ss["filings"]["recent"][key]=val
        red("SEC_SUB_"+key,S=ss)
    for key,val in [("t","2026-10-09T19:00:00Z"),
                    ("t","2026-10-08T04:00:00Z"),
                    ("v",0),("c",0),("h",1),("c",True),("v",float("nan"))]:
        bb=deepcopy(bar);bb[key]=val
        red("ALPACA_"+key,B=[bb])
    red("EMPTY_EOD_BARS",B=[])
    red("DUPLICATE_EOD_BARS",B=[bar,bar])
    red("ASOF_CHANGED",A="2026-10-08")
    pp=deepcopy(p);pp["pass_hash"]="0"*64
    red("PRICE_HASH",P=pp)
    mm=deepcopy(m);mm["pass_symbols"]=[]
    red("MASTER_IDENTITY",M=mm)
    print("XRAY_P0_PERSONAL_SEC_ALPACA_MC_CANARY=PASS_1_POSITIVE_21_NEGATIVE_OPTIMIZER_SAFE_NO_PRIMARY")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--out",type=Path)
    args=a.parse_args()
    if args.selftest:
        selftest();return
    require(args.out is not None,"OUTPUT_PATH_REQUIRED")
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    asof=price.get("asof_et")
    out={"schema":SCHEMA,"asof_et":asof,"symbol":TICKER,
         "status":"UNKNOWN","C417_PRIMARY_MC":False,
         "C417_CURRENT_PRIMARY_CREATED":0,"R92_created":False,
         "GO":False,"execution":"NONE","real_money":"NO-GO",
         "numeric_shares_price_or_marketcap_persisted":False}
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY","")
    if not valid_operator_contact(ua):
        out["status"]="BLOCKED_OFFICIAL_SEC_USER_AGENT"
    elif not key or not secret:
        out["status"]="BLOCKED_ALPACA_PERSONAL_API_KEY"
    elif not sufficient_delay(asof,dt.datetime.now(UTC)):
        out["status"]="BLOCKED_BEFORE_SETTLED_OFFICIAL_NASDAQ_SESSION"
    else:
        try:
            facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{SEC_CIK}.json",ua)
            sub=get_json(f"https://data.sec.gov/submissions/CIK{SEC_CIK}.json",ua)
            nextday=(dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()
            bars=request_batch([TICKER],asof+"T00:00:00Z",
                               nextday+"T00:00:00Z",key,secret).get(TICKER,[])
            out=measure(price,master,facts,sub,bars,asof)
        except (ValueError,RuntimeError,KeyError,TypeError) as err:
            # Never echo vendor responses, secrets, share count, or prices.
            out["status"]="UNKNOWN_SEC_ALPACA_PIT_SOURCE_OR_ARITHMETIC"
            out["source_failure_class"]=str(err).split(":")[0][:48]
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_P0_PERSONAL_SEC_ALPACA_MC="+out["status"])
    print("XRAY_P0_MC_PRIMARY=0_NO_C417_AUTHORITY")

if __name__=="__main__":main()
