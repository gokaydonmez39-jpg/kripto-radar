#!/usr/bin/env python3
"""Recover Oct13 exact30 historical SIP 50 names at a time, one ticker/request.

Single-symbol SIP HTTP 200 proven on GitHub runner 38529450611 after
mixed 8-symbol batch 403. No global halt on isolated ticker 403.
Research RTH lower bound only, never official settlement or primary.
"""
from __future__ import annotations
import argparse,collections,json,os,time,urllib.error
from pathlib import Path
import alpaca_personal_price_20261013_exact30_census as engine

ROOT=Path(__file__).resolve().parent
PAGE=50
MAX_CALLS=160
def demand(ok,reason):
    if not ok:raise ValueError("XRAY_LOCAL_PRICE50_"+reason)
def source(page):
    syms,dates,master_sha,price_sha=engine.scope()
    demand(len(syms)==545 and len(dates)==30,"EXACT_SCOPE")
    demand(type(page) is int and 0<=page<=10,"PAGE_RANGE")
    return syms[page*PAGE:(page+1)*PAGE],dates,master_sha,price_sha
def selftest():
    # A frozen October-13 research page is NOT the latest current ASOF.
    # Test pagination with an offline disposable fixture; the real source()
    # still enforces engine.scope() and rejects expired source in production.
    from unittest.mock import patch
    syms=[f"OFFLINE_{i:04d}" for i in range(545)]
    dates=engine.dates30()
    demand(len(dates)==30 and dates[-1]=="2026-10-13","OFFICIAL_CALENDAR")
    master_sha="a"*40
    price_sha="b"*40
    parts=[syms[i*PAGE:(i+1)*PAGE] for i in range(11)]
    demand([len(x) for x in parts]==[50]*10+[45],"EXACT_PARTS")
    demand(len(set(x for part in parts for x in part))==545,"NO_DUP")
    with patch.object(engine,"scope",return_value=(syms,dates,master_sha,price_sha)) as guarded:
        first=source(0)
        last=source(10)
        demand(first[0]==syms[:50] and last[0]==syms[-45:],"PAGE_BOUNDARIES")
        demand(first[1:]==last[1:]==(dates,master_sha,price_sha),"SOURCE_BINDINGS")
        demand(guarded.call_count==2,"STRICT_SCOPE_CALLED")
        for i in (-1,11):
            try:source(i)
            except ValueError as exc:
                demand("PAGE_RANGE" in str(exc),"NEGATIVE_PAGE_REASON")
            else:raise AssertionError("PAGE_NOT_REJECTED")
    with patch.object(engine,"scope",return_value=(syms[:-1],dates,master_sha,price_sha)):
        try:source(0)
        except ValueError as exc:
            demand("EXACT_SCOPE" in str(exc),"TRUNCATED_SOURCE_REASON")
        else:raise AssertionError("TRUNCATED_SCOPE_ACCEPTED")
    with patch.object(engine,"scope",side_effect=ValueError("XRAY_PRICE_20261013_NOT_LATEST_COMPLETED_ASOF")):
        try:source(0)
        except ValueError as exc:
            demand("NOT_LATEST_COMPLETED_ASOF" in str(exc),"STALE_SOURCE_REASON")
        else:raise AssertionError("STALE_SOURCE_ACCEPTED")
    print("XRAY_LOCAL_PRICE50_SELFTEST=PASS_FROZEN_FIXTURE_545_11_NO_LIVE_SOURCE_NO_VENDOR")
def run(page,out):
    demand(out and not out.resolve().is_relative_to(ROOT.parent.resolve()),
           "NO_REPO_PROVIDER_EXPORT")
    scope,dates,master_sha,price_sha=source(page)
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    demand(key and secret,"RUNNER_CREDENTIALS_MISSING")
    report={"schema":"XRAY_OCT13_ALPACA_50_SINGLE_SYMBOL_SIP_RTH_BOUNDS_V1",
        "asof_et":"2026-10-13","page":page,
        "target_count":len(scope),"target_symbols":scope,
        "statuses":{s:"UNKNOWN_NOT_ATTEMPTED" for s in scope},
        "counts":{},"request_count":0,"max_requests":MAX_CALLS,
        "verified_official_30_session_count":30,
        "master_source_git_blob_sha":master_sha,
        "price_source_git_blob_sha":price_sha,
        "source":"ALPACA_HISTORICAL_SIP_GITHUB_RUNNER",
        "single_symbol_isolation":True,
        "no_vendor_raw_ohlcv_exported":True,
        "correction_and_close_auction_verified":False,
        "price_primary_created":False,
        "mc_primary_created":False,"r92_created":False,
        "canonical_files_mutated":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    def save():
        report["counts"]=dict(sorted(collections.Counter(report["statuses"].values()).items()))
        out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    save()
    calls=[0]
    for pos,sym in enumerate(scope):
        if calls[0]+2>MAX_CALLS:
            report["stop_reason"]="SIP_CALL_BUDGET"
            break
        try:
            daily,half=engine.fetch([sym],dates,(key,secret),calls)
            answer=engine.analyze([sym],daily,half,dates)
            report["statuses"][sym]=answer[sym]
        except urllib.error.HTTPError as exc:
            report["statuses"][sym]="UNKNOWN_SIP_HTTP_"+str(exc.code)
            if exc.code==429:
                report["stop_reason"]="PROVIDER_429_FAIR_ACCESS"
                break
        except (urllib.error.URLError,ValueError,TimeoutError,RuntimeError):
            report["statuses"][sym]="UNKNOWN_SIP_SOURCE_OR_INTEGRITY"
        report["request_count"]=calls[0]
        save()
        time.sleep(.65)
    report["request_count"]=calls[0]
    save()
    demand(len(report["statuses"])==len(scope) and
           sum(report["counts"].values())==len(scope),"COMPLETE_PARTITION")
    print("XRAY_LOCAL_PRICE50_PAGE="+str(page))
    print("XRAY_LOCAL_PRICE50_REAL_HTTP_REQUESTS="+str(calls[0]))
    print("XRAY_LOCAL_PRICE50_COUNTS="+json.dumps(report["counts"],sort_keys=True))
    print("XRAY_LOCAL_PRICE50_NO_PRIMARY_MC_R92=PASS")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--page",type=int,default=0)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:selftest();return
    run(a.page,a.out)
if __name__=="__main__":main()
