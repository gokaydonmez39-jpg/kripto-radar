#!/usr/bin/env python3
"""Official SEC free-access viability probe for the proposed MC successor.

This is a bounded, honest transport + historical filing-vintage test.
No commercial market-data API, purchased credits, account access,
market price, production MC classification, trade signal or broker use.
It cannot promote a C4.17 UNKNOWN into PRIMARY PASS.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ASOF="2026-10-08"
CIK="0000320193"  # Apple: transport canary, not a real trading candidate
FACTS_URL=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
SUB_URL=f"https://data.sec.gov/submissions/CIK{CIK}.json"
ACCEPTED_FORMS={"10-K","10-Q","10-K/A","10-Q/A"}
MAX_AGE_DAYS=120

def get_json(url: str, user_agent: str) -> dict:
    req=urllib.request.Request(
        url,headers={"User-Agent":user_agent,
                     "Accept":"application/json",
                     "Accept-Encoding":"identity"})
    try:
        with urllib.request.urlopen(req,timeout=15) as resp:
            if resp.status!=200:
                raise ValueError("SEC_NOT_200")
            data=resp.read(9_000_001)
            if len(data)>9_000_000:
                raise ValueError("SEC_PAYLOAD_TOO_LARGE")
    except urllib.error.HTTPError as exc:
        # Fail closed; never rotate IPs or user agents to bypass SEC blocks.
        raise ValueError("SEC_HTTP_"+str(exc.code)) from exc
    except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
        raise ValueError("SEC_TRANSPORT_UNAVAILABLE") from exc
    try:
        obj=json.loads(data)
    except (ValueError,UnicodeError) as exc:
        raise ValueError("SEC_JSON_INVALID") from exc
    if not isinstance(obj,dict):
        raise ValueError("SEC_RESPONSE_NOT_OBJECT")
    return obj

def accession_acceptance_index(sub: dict) -> dict:
    recent=((sub.get("filings") or {}).get("recent") or {})
    accessions=recent.get("accessionNumber") or []
    forms=recent.get("form") or []
    dates=recent.get("filingDate") or []
    accepted=recent.get("acceptanceDateTime") or []
    if not (len(accessions)==len(forms)==len(dates)==len(accepted)):
        raise ValueError("SEC_SUBMISSIONS_LIST_LENGTH_MISMATCH")
    idx={}
    for acc,form,filed,stamp in zip(accessions,forms,dates,accepted):
        if not isinstance(acc,str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}",acc):
            continue
        if not isinstance(stamp,str) or len(stamp)<19:
            continue
        idx[acc]={"form":form,"filed":filed,"accepted_at":stamp}
    return idx

def select_shares(facts:dict,sub:dict,asof:str) -> dict:
    cutoff=dt.date.fromisoformat(asof)
    if str(facts.get("cik") or "").lstrip("0")!=CIK.lstrip("0"):
        return {"status":"UNKNOWN","reason":"SEC_COMPANYFACTS_CIK_MISMATCH"}
    if str(sub.get("cik") or "").lstrip("0")!=CIK.lstrip("0"):
        return {"status":"UNKNOWN","reason":"SEC_SUBMISSIONS_CIK_MISMATCH"}
    concept=((((facts.get("facts") or {}).get("dei") or {})
              .get("EntityCommonStockSharesOutstanding") or {})
             .get("units") or {}).get("shares") or []
    try:idx=accession_acceptance_index(sub)
    except ValueError as exc:
        return {"status":"UNKNOWN","reason":str(exc)}
    valid=[]
    for row in concept:
        if not isinstance(row,dict):continue
        if row.get("form") not in ACCEPTED_FORMS:continue
        acc=row.get("accn")
        matched=idx.get(acc)
        if not matched or matched["form"]!=row.get("form") or matched["filed"]!=row.get("filed"):
            continue
        try:
            filed=dt.date.fromisoformat(str(row["filed"]))
            end=dt.date.fromisoformat(str(row["end"]))
            accepted=dt.datetime.fromisoformat(matched["accepted_at"].replace("Z","+00:00"))
            shares=row["val"]
            if isinstance(shares,bool) or not isinstance(shares,int) or shares<=0:
                continue
            age=(cutoff-end).days
            if not (0<=age<=MAX_AGE_DAYS and end<=filed<=cutoff and accepted.date()<=cutoff):
                continue
        except (KeyError,ValueError,TypeError):continue
        valid.append((accepted, end, acc, shares, age))
    if not valid:
        return {"status":"UNKNOWN","reason":"NO_FRESH_ACCEPTANCE_BOUND_SINGLE_ENTITY_SHARES"}
    valid.sort(key=lambda x:(x[0],x[1]))
    t,end,acc,shares,age=valid[-1]
    # SEC CompanyFacts can omit dimensional share-class facts. No class
    # cardinality, corporate actions, split-adjustment or price is asserted.
    return {"status":"SHADOW_SHARES_VINTAGE_ONLY",
            "reason":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED",
            "selected_filing_date":t.date().isoformat(),
            "observation_date":end.isoformat(),
            "shares_age_days":age,
            "accession_present":bool(acc),
            "share_count_available":shares>0,
            "production_mc_primary_pass":False}

def selftest():
    asof="2026-10-08"
    fak={"cik":320193,"facts":{"dei":{"EntityCommonStockSharesOutstanding":{
        "units":{"shares":[
        {"val":100,"end":"2026-09-30","filed":"2026-10-05",
         "form":"10-Q","accn":"0000320193-26-000001"},
        {"val":200,"end":"2026-10-02","filed":"2026-10-10",
         "form":"10-Q","accn":"0000320193-26-000002"}]}}}}}
    subs={"cik":320193,"filings":{"recent":{
      "accessionNumber":["0000320193-26-000001","0000320193-26-000002"],
      "form":["10-Q","10-Q"],"filingDate":["2026-10-05","2026-10-10"],
      "acceptanceDateTime":["2026-10-05T12:00:00Z","2026-10-10T12:00:00Z"]}}}
    r=select_shares(fak,subs,asof)
    assert r["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    assert r["observation_date"]=="2026-09-30"
    assert r["production_mc_primary_pass"] is False
    bad=json.loads(json.dumps(subs))
    bad["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-09T12:00:00Z"
    assert select_shares(fak,bad,asof)["status"]=="UNKNOWN"
    bad=json.loads(json.dumps(fak))
    bad["cik"]=1234
    assert select_shares(bad,subs,asof)["reason"]=="SEC_COMPANYFACTS_CIK_MISMATCH"
    bad=json.loads(json.dumps(subs))
    bad["filings"]["recent"]["acceptanceDateTime"].pop()
    assert select_shares(fak,bad,asof)["status"]=="UNKNOWN"
    bad=json.loads(json.dumps(fak))
    bad["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0]["val"]=True
    assert select_shares(bad,subs,asof)["status"]=="UNKNOWN"
    print("SEC_FREE_MC_PIT_SELFTEST=PASS_ACCEPTANCE_FUTURE_CIK_LIST_BOOL_NO_PRIMARY")

def run(asof:str) -> dict:
    base={"schema":"XRAY_SEC_FREE_MC_TRANSPORT_V1","asof_et":asof,
          "execution":"NONE","real_money":"NO-GO",
          "policy_unchanged":"C4.17","unknown_never_pass":True,
          "alpha_authority":False,"api_spend_usd":0,
          "production_mc_primary_pass":False,
          "probe_symbol":"AAPL","sec_transport":"UNTESTED",
          "issuer_shares_vintage":"UNKNOWN","reason":"NOT_RUN"}
    ua=os.environ.get("XRAY_SEC_USER_AGENT",
        "NASDAQ-XRAY-Research/1.0 (xray-dataplane-bot@users.noreply.github.com)")
    if not re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+",ua):
        return dict(base,sec_transport="BLOCKED",reason="SEC_DECLARED_UA_CONTACT_MISSING")
    try:
        facts=get_json(FACTS_URL,ua)
        subs=get_json(SUB_URL,ua)
        classified=select_shares(facts,subs,asof)
        return dict(base,sec_transport="HTTP_200_BOTH",
                    issuer_shares_vintage=classified["status"],
                    reason=classified["reason"],
                    shares_age_days=classified.get("shares_age_days"),
                    accession_present=classified.get("accession_present",False))
    except ValueError as exc:
        reason=str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+",reason):reason="PROBE_UNEXPECTED_DATA"
        return dict(base,sec_transport="BLOCKED_OR_UNAVAILABLE",reason=reason)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--asof",default=DEFAULT_ASOF)
    p.add_argument("--output")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    data=run(args.asof)
    if args.output:
        Path(args.output).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print("SEC_FREE_MC_TRANSPORT="+data["sec_transport"])
    print("SEC_FREE_MC_VINTAGE="+data["issuer_shares_vintage"])
    print("SEC_FREE_MC_REASON="+data["reason"])
    print("SEC_FREE_MC_PRIMARY=FORBIDDEN_UNTIL_NEW_POLICY_AND_SOURCE_TESTS")

if __name__=="__main__":
    main()
