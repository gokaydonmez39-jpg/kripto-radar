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


if __name__=="__main__":
    test_dual_transport_failure_is_bounded()
    test_map_failure_efts_success_remains_degraded_not_blocked()
    print("XRAY_SEC_OFFICIAL_WITNESS_SELFTEST=PASS")
