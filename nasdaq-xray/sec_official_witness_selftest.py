#!/usr/bin/env python3
from __future__ import annotations

import urllib.error
from datetime import date

import sec_official_witness as s


def forbidden(url):
    return urllib.error.HTTPError(url,403,"Forbidden",hdrs=None,fp=None)


def test_dual_transport_failure_is_bounded():
    calls=[]
    original=s.fetch_json

    def fake(provider,url,headers=None,**kwargs):
        calls.append((provider,url))
        raise forbidden(url)

    s.fetch_json=fake
    try:
        by,prefetch,transport=s.bounded_identity_resolution(["AAPL","MSFT","NVDA"],date(2026,10,6))
    finally:
        s.fetch_json=original

    assert by=={}
    assert prefetch=={}
    assert transport["status"]=="BLOCKED_BOUNDED_PROBE",transport
    assert transport["efts_probe_symbol"]=="AAPL",transport
    assert transport["map_error"]=="HTTPError:HTTP_403",transport
    assert transport["efts_probe_error"]=="HTTPError:HTTP_403",transport
    assert len(calls)==2,calls
    assert calls[0][0]=="SEC_TICKER_MAP",calls
    assert calls[1][0]=="SEC_EFTS",calls


def test_map_failure_efts_success_remains_degraded_not_blocked():
    calls=[]
    original=s.fetch_json

    def fake(provider,url,headers=None,**kwargs):
        calls.append((provider,url))
        if provider=="SEC_TICKER_MAP":
            raise forbidden(url)
        if provider=="SEC_EFTS":
            return {
                "hits":{
                    "hits":[{
                        "_source":{
                            "ciks":["0000320193"],
                            "tickers":["AAPL"],
                            "display_names":["Apple Inc. (AAPL)"],
                        }
                    }]
                }
            }
        raise AssertionError(provider)

    s.fetch_json=fake
    try:
        by,prefetch,transport=s.bounded_identity_resolution(["AAPL","MSFT"],date(2026,10,6))
    finally:
        s.fetch_json=original

    assert by=={}
    assert transport["status"]=="DEGRADED_MAP_FALLBACK",transport
    ident,reason=prefetch["AAPL"]
    assert reason is None
    assert ident["cik"]==320193,ident
    assert ident["resolver"]=="SEC_EFTS_EXACT_TICKER",ident
    assert len(calls)==2,calls


def require(value, label):
    if not value:
        raise AssertionError(label)


def test_access_fence():
    scope=["AAPL","MSFT","NVDA"]
    def run(mode):
        calls=[]
        old_fetch=s.fetch_json
        old_sleep=s.time.sleep
        old_last=s._SEC_LAST_REQUEST
        def fake(provider,url,headers=None,**kwargs):
            require(kwargs.get("retry_delays")==(), "SEC_AUTOMATIC_RETRY_ENABLED")
            calls.append(provider)
            if provider=="SEC_TICKER_MAP":
                if mode in ("map429","map401"):
                    code=429 if mode=="map429" else 401
                    raise urllib.error.HTTPError(url,code,"blocked",None,None)
                return {"fields":["cik","name","ticker","exchange"],
                        "data":[[i+1,k,k,"Nasdaq"] for i,k in enumerate(scope)]}
            if provider=="SEC_SUBMISSIONS":
                if len(calls)==3 and mode in ("sub403","sub429"):
                    code=403 if mode=="sub403" else 429
                    raise urllib.error.HTTPError(url,code,"blocked",None,None)
                name=scope[len(calls)-2]
                return {"cik":len(calls)-1,"tickers":[name],"name":name,"filings":{"recent":{}}}
            raise AssertionError("UNEXPECTED_PROVIDER:"+provider)
        s.fetch_json=fake
        s.time.sleep=lambda _:None
        s._SEC_LAST_REQUEST=None
        try:
            results,transport=s.build_witness_results(scope,date(2026,10,6))
        finally:
            s.fetch_json=old_fetch
            s.time.sleep=old_sleep
            s._SEC_LAST_REQUEST=old_last
        return results,transport,calls
    for mode in ("map429","map401"):
        results,transport,calls=run(mode)
        require(calls==["SEC_TICKER_MAP"],"MAP_ACCESS_STOP:"+mode)
        require(transport["status"]=="BLOCKED_BOUNDED_PROBE","MAP_STATUS:"+mode)
        require(all(x["identity_status"]=="UNKNOWN" for x in results.values()),"MAP_FALSE_PASS:"+mode)
    for mode in ("sub403","sub429"):
        results,transport,calls=run(mode)
        require(calls==["SEC_TICKER_MAP","SEC_SUBMISSIONS","SEC_SUBMISSIONS"],"SUB_ACCESS_STOP:"+mode)
        require(transport["status"]=="BLOCKED_DURING_SCOPE" and transport["blocked_provider"]=="SEC_SUBMISSIONS","SUB_STATUS:"+mode)
        require(results["AAPL"]["identity_status"]=="PASS","PRIOR_SUCCESS_LOST:"+mode)
        require(all(results[k]["identity_status"]=="UNKNOWN" for k in ("MSFT","NVDA")),"SUB_FALSE_PASS:"+mode)
        require(results["NVDA"]["filings"]==[],"FABRICATED_FILINGS:"+mode)
    results,transport,calls=run("ok")
    require(calls==["SEC_TICKER_MAP"]+["SEC_SUBMISSIONS"]*3,"NORMAL_CALLS")
    require(transport["status"]=="AVAILABLE" and all(x["identity_status"]=="PASS" for x in results.values()),"NORMAL_REGRESSION")


def test_exact_submissions_identity():
    scope=["AAPL"]
    cases=[
        ({"cik":320193,"tickers":["AAPL"]},"PASS",None),
        ({"cik":"0000320193","tickers":["aapl"]},"PASS",None),
        ({"cik":320193,"tickers":[]},"UNKNOWN","SEC_SUBMISSIONS_TICKERS_MISSING_OR_INVALID"),
        ({"cik":320193},"UNKNOWN","SEC_SUBMISSIONS_TICKERS_MISSING_OR_INVALID"),
        ({"cik":320193,"tickers":"AAPL"},"UNKNOWN","SEC_SUBMISSIONS_TICKERS_MISSING_OR_INVALID"),
        ({"cik":320193,"tickers":["AAPL",None]},"UNKNOWN","SEC_SUBMISSIONS_TICKERS_MISSING_OR_INVALID"),
        ({"cik":320193,"tickers":["MSFT"]},"UNKNOWN","SEC_SUBMISSIONS_TICKER_MISMATCH"),
        ({"cik":789019,"tickers":["AAPL"]},"UNKNOWN","SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH"),
        ({"tickers":["AAPL"]},"UNKNOWN","SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH"),
        ({"cik":True,"tickers":["AAPL"]},"UNKNOWN","SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH"),
        ({"cik":320193.0,"tickers":["AAPL"]},"UNKNOWN","SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH"),
        ({"cik":"320193x","tickers":["AAPL"]},"UNKNOWN","SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH"),
    ]
    for payload,status,reason in cases:
        old_fetch,old_sleep,old_last=s.fetch_json,s.time.sleep,s._SEC_LAST_REQUEST
        calls=[]
        def fake(provider,url,headers=None,**kwargs):
            calls.append(provider)
            require(kwargs.get("retry_delays")==(),"IDENTITY_RETRY")
            if provider=="SEC_TICKER_MAP":
                return {"fields":["cik","name","ticker","exchange"],"data":[[320193,"Apple","AAPL","Nasdaq"]]}
            if provider=="SEC_SUBMISSIONS":
                return dict(payload,filings={"recent":{"form":["8-K"],"filingDate":["2026-10-05"],"accessionNumber":["0000320193-26-000001"],"primaryDocument":["x.htm"]}})
            raise AssertionError(provider)
        s.fetch_json=fake
        s.time.sleep=lambda _:None
        s._SEC_LAST_REQUEST=None
        try:
            results,transport=s.build_witness_results(scope,date(2026,10,6))
        finally:
            s.fetch_json,s.time.sleep,s._SEC_LAST_REQUEST=old_fetch,old_sleep,old_last
        row=results["AAPL"]
        require(calls==["SEC_TICKER_MAP","SEC_SUBMISSIONS"],"EXACT_IDENTITY_CALLS")
        require(row["identity_status"]==status,"EXACT_IDENTITY:"+repr(payload)+":"+repr(row))
        require(row.get("reason")==reason,"EXACT_IDENTITY_REASON:"+repr(payload))
        require(len(row["filings"])==(1 if status=="PASS" else 0),"UNBOUND_FILINGS:"+repr(payload))
        require(transport["status"]=="AVAILABLE","IDENTITY_NOT_TRANSPORT")


if __name__=="__main__":
    test_dual_transport_failure_is_bounded()
    test_map_failure_efts_success_remains_degraded_not_blocked()
    test_access_fence()
    test_exact_submissions_identity()
    print("XRAY_SEC_OFFICIAL_WITNESS_SELFTEST=PASS")
