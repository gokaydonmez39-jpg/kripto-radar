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
from zoneinfo import ZoneInfo

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

def select_shares(facts:dict,sub:dict,asof:str,expected_cik:str=CIK) -> dict:
    cutoff=dt.date.fromisoformat(asof)
    # PIT authority is bounded at the completed regular Nasdaq session close,
    # NOT midnight UTC: otherwise late SEC filings cause lookahead leakage.
    session_close_utc=dt.datetime.combine(
        cutoff,dt.time(16,0),tzinfo=ZoneInfo("America/New_York")
    ).astimezone(dt.timezone.utc)
    if str(facts.get("cik") or "").lstrip("0")!=expected_cik.lstrip("0"):
        return {"status":"UNKNOWN","reason":"SEC_COMPANYFACTS_CIK_MISMATCH"}
    if str(sub.get("cik") or "").lstrip("0")!=expected_cik.lstrip("0"):
        return {"status":"UNKNOWN","reason":"SEC_SUBMISSIONS_CIK_MISMATCH"}
    concept=((((facts.get("facts") or {}).get("dei") or {})
              .get("EntityCommonStockSharesOutstanding") or {})
             .get("units") or {}).get("shares") or []
    try:idx=accession_acceptance_index(sub)
    except ValueError as exc:
        return {"status":"UNKNOWN","reason":str(exc)}
    valid=[]
    # Diagnostic counters contain no raw shares, filings or proprietary prices.
    diag={"missing_accession":0,"form_nonannual":0,"stale":0,
          "post_close":0,"invalid_fact":0}
    for row in concept:
        if not isinstance(row,dict):continue
        if row.get("form") not in ACCEPTED_FORMS:
            diag["form_nonannual"]+=1
            continue
        # PIT eligibility precedes accession diagnostics. A filing AFTER
        # ASOF or an old share observation cannot be rescued by chasing a
        # historical accession: doing so misclassifies stale data as a gap.
        try:
            filed=dt.date.fromisoformat(str(row["filed"]))
            end=dt.date.fromisoformat(str(row["end"]))
            age=(cutoff-end).days
        except (KeyError,ValueError,TypeError):
            diag["invalid_fact"]+=1
            continue
        if not (0<=age<=MAX_AGE_DAYS and end<=filed<=cutoff):
            diag["stale"]+=1
            continue
        acc=row.get("accn")
        matched=idx.get(acc)
        if not matched or matched["form"]!=row.get("form") or matched["filed"]!=row.get("filed"):
            diag["missing_accession"]+=1
            continue
        try:
            accepted=dt.datetime.fromisoformat(matched["accepted_at"].replace("Z","+00:00"))
            shares=row["val"]
            if isinstance(shares,bool) or not isinstance(shares,int) or shares<=0 or accepted.tzinfo is None:
                diag["invalid_fact"]+=1
                continue
            if accepted.astimezone(dt.timezone.utc)>session_close_utc:
                diag["post_close"]+=1
                continue
        except (KeyError,ValueError,TypeError):
            diag["invalid_fact"]+=1
            continue
        valid.append((accepted, end, acc, shares, age))
    if not valid:
        if not concept:
            # SEC companyfacts excludes dimensional facts; multiple-class
            # issuers (e.g. dual-class A/B) can have no DEI entity rows.
            # GAAP balance-sheet shares are only a diagnostic ALTERNATIVE,
            # never a substitute for exact tradable listing class count.
            gaap=((((facts.get("facts") or {}).get("us-gaap") or {})
                   .get("CommonStockSharesOutstanding") or {})
                  .get("units") or {}).get("shares") or []
            reason=("NO_DEI_BUT_GAAP_SHARES_AVAILABLE_CLASS_UNRESOLVED"
                    if gaap else "NO_SEC_DEI_OR_GAAP_SHARES_FACT")
        elif diag["missing_accession"]>0:
            # A viable PIT fact without exact accession is actionable even if
            # other unrelated XBRL facts are stale/future; don't hide the
            # candidate-specific missing evidence behind unrelated rows.
            reason="SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS"
        elif diag["post_close"]>0:
            reason="SEC_FACT_ACCEPTED_AFTER_RTH_CLOSE"
        elif diag["stale"]>0:
            reason="SEC_SHARES_STALE_OR_FUTURE_OBSERVATION"
        elif diag["invalid_fact"]>0:
            reason="SEC_FACT_MALFORMED_OR_INVALID"
        else:
            reason="NO_FRESH_ACCEPTANCE_BOUND_SINGLE_ENTITY_SHARES"
        return {"status":"UNKNOWN","reason":reason}
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
    # A mismatched accession on an ineligible post-ASOF vintage is NOT
    # evidence of missing official archive coverage.
    stale=json.loads(json.dumps(fak))
    stale_rows=stale["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
    stale_rows[0]["filed"]="2026-10-09"
    stale_rows[0]["end"]="2026-10-09"
    assert select_shares(stale,subs,asof)["reason"]=="SEC_SHARES_STALE_OR_FUTURE_OBSERVATION"
    # A genuinely valid pre-ASOF vintage with an unmatched accession must
    # remain UNKNOWN and may be eligible for a historical-archive probe.
    missing=json.loads(json.dumps(subs))
    missing["filings"]["recent"]["accessionNumber"][0]="0000320193-26-999999"
    assert select_shares(fak,missing,asof)["reason"]=="SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS"
    bad=json.loads(json.dumps(subs))
    bad["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-09T12:00:00Z"
    assert select_shares(fak,bad,asof)["status"]=="UNKNOWN"
    # Same calendar date, but filing AFTER the 16:00 New York RTH close:
    # a date-only comparison would incorrectly admit lookahead data.
    same_close=json.loads(json.dumps(fak))
    same_close["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0]["end"]="2026-10-08"
    same_close["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0]["filed"]="2026-10-08"
    sub_close=json.loads(json.dumps(subs))
    sub_close["filings"]["recent"]["filingDate"][0]="2026-10-08"
    sub_close["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-08T20:01:00Z"
    assert select_shares(same_close,sub_close,asof)["status"]=="UNKNOWN"
    sub_close["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-08T19:59:00Z"
    assert select_shares(same_close,sub_close,asof)["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    # RED: Black Friday 27 Nov 2026 closed 13:00 New York, not 16:00.
    # At 14:05 ET the filing is AFTER RTH; it must not enter the EOD ASOF.
    early_facts=json.loads(json.dumps(fak))
    early_sub=json.loads(json.dumps(subs))
    early_fact=early_facts["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0]
    early_fact["end"]="2026-11-25"
    early_fact["filed"]="2026-11-27"
    early_sub["filings"]["recent"]["filingDate"][0]="2026-11-27"
    early_sub["filings"]["recent"]["acceptanceDateTime"][0]="2026-11-27T19:05:00Z"
    assert select_shares(early_facts,early_sub,"2026-11-27")["status"]=="UNKNOWN"
    early_sub["filings"]["recent"]["acceptanceDateTime"][0]="2026-11-27T17:59:00Z"
    assert select_shares(early_facts,early_sub,"2026-11-27")["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    assert select_shares(early_facts,early_sub,"2026-11-26")["status"]=="UNKNOWN"
    bad=json.loads(json.dumps(fak))
    bad["cik"]=1234
    assert select_shares(bad,subs,asof)["reason"]=="SEC_COMPANYFACTS_CIK_MISMATCH"
    bad=json.loads(json.dumps(subs))
    bad["filings"]["recent"]["acceptanceDateTime"].pop()
    assert select_shares(fak,bad,asof)["status"]=="UNKNOWN"
    bad=json.loads(json.dumps(fak))
    bad["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][0]["val"]=True
    assert select_shares(bad,subs,asof)["status"]=="UNKNOWN"
    empty_dei=json.loads(json.dumps(fak))
    empty_dei["facts"]["dei"]={}
    empty_dei["facts"]["us-gaap"]={"CommonStockSharesOutstanding":{
        "units":{"shares":[{"val":100,"end":"2026-09-30",
                             "filed":"2026-10-05","form":"10-Q",
                             "accn":"0000320193-26-000001"}]}}}
    gaap_row=select_shares(empty_dei,subs,asof)
    assert gaap_row["status"]=="UNKNOWN"
    assert gaap_row["reason"]=="NO_DEI_BUT_GAAP_SHARES_AVAILABLE_CLASS_UNRESOLVED"
    empty_dei["facts"]["us-gaap"]={}
    assert select_shares(empty_dei,subs,asof)["reason"]=="NO_SEC_DEI_OR_GAAP_SHARES_FACT"
    alt_facts=json.loads(json.dumps(fak))
    alt_sub=json.loads(json.dumps(subs))
    alt_facts["cik"]=1234567
    alt_sub["cik"]=1234567
    assert select_shares(alt_facts,alt_sub,asof,expected_cik="0001234567")["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    assert select_shares(alt_facts,alt_sub,asof,expected_cik=CIK)["status"]=="UNKNOWN"
    assert not valid_operator_contact("NASDAQ-XRAY bot <bot@users.noreply.github.com>")
    assert not valid_operator_contact("")
    assert not valid_operator_contact("bot@example.com")
    assert valid_operator_contact("NASDAQ-XRAY operator (operator@sample.org)")
    # No HTTP calls when the secret is absent or invalid.
    from unittest.mock import patch
    with patch.dict(os.environ,{"XRAY_SEC_USER_AGENT":""}),patch(__name__+".get_json",side_effect=AssertionError("NETWORK_REQUEST_WHEN_SECRET_MISSING")):
        assert run("2026-10-08")["reason"]=="SEC_OPERATOR_CONTACT_CONFIG_MISSING"
    with patch.dict(os.environ,{"XRAY_SEC_USER_AGENT":"bot@users.noreply.github.com"}),patch(__name__+".get_json",side_effect=AssertionError("NETWORK_REQUEST_WHEN_CONTACT_INVALID")):
        assert run("2026-10-08")["reason"]=="SEC_OPERATOR_CONTACT_FORMAT_INVALID"
    print("SEC_FREE_MC_PIT_SELFTEST=PASS_ACCEPTANCE_FUTURE_CIK_LIST_BOOL_CONTACT_DIAG_NO_PRIMARY")

def valid_operator_contact(ua:str) -> bool:
    """SEC requires a real contact; GitHub noreply cannot identify an operator."""
    if not isinstance(ua,str) or len(ua)>220:
        return False
    if any(x in ua.lower() for x in ("noreply", "no-reply", "example.com", "localhost")):
        return False
    return bool(re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+",ua))

def run(asof:str) -> dict:
    base={"schema":"XRAY_SEC_FREE_MC_TRANSPORT_V1","asof_et":asof,
          "execution":"NONE","real_money":"NO-GO",
          "policy_unchanged":"C4.17","unknown_never_pass":True,
          "alpha_authority":False,"api_spend_usd":0,
          "production_mc_primary_pass":False,
          "probe_symbol":"AAPL","sec_transport":"UNTESTED",
          "issuer_shares_vintage":"UNKNOWN","reason":"NOT_RUN"}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    if not ua.strip():
        # GitHub Actions secret was not injected; report only presence, never value.
        return dict(base,sec_transport="BLOCKED",reason="SEC_OPERATOR_CONTACT_CONFIG_MISSING")
    if not valid_operator_contact(ua):
        return dict(base,sec_transport="BLOCKED",reason="SEC_OPERATOR_CONTACT_FORMAT_INVALID")
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
