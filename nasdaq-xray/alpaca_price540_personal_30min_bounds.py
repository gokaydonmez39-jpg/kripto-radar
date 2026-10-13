#!/usr/bin/env python3
"""Frozen 2026-10-12 PRICE UNKNOWN 30-session 30Min SIP volume-bound census.

This is historical PERSONAL RESEARCH only. Reuses 8 prior CI-positive SHADOW
symbols without a second vendor download. 30Min RTH volume excludes any
unresolved correction or closing-auction venue volume; never PRIMARY DV30.
No raw market OHLCV is written to GitHub or artifacts.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
import time
import urllib.error
from pathlib import Path
import alpaca_sip_4symbol_30min_rth_shadow as engine
ROOT=Path(__file__).resolve().parent
ASOF="2026-10-12"
PRIOR=("AAON","AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA")
PRIOR_RUNS=(38468954318,38473340983)
BATCH=16
MAX_BATCHES=34
MAX_HTTP_CALLS=160
GOOD="LOWER_BOUND_GE_50M_SHADOW"
REUSED="PRIOR_VERIFIED_LOWER_BOUND_GE_50M_SHADOW"

def demand(ok,reason):
    if not ok:
        raise ValueError("XRAY_PRICE540_"+reason)

def exact_scope(price,master):
    symbols=price.get("unknown_symbols")
    demand(type(symbols) is list and len(symbols)==price.get("unknown_count")==540
           and symbols==sorted(set(symbols)),"UNKNOWN_SCOPE")
    demand(price.get("pass_count")==0 and price.get("asof_et")==ASOF
           and master.get("asof_et")==ASOF
           and set(symbols).issubset(set(master["pass_symbols"]))
           and set(PRIOR).issubset(set(symbols)),"SOURCE_EPOCH_AND_PRIORS")
    demand(price.get("unknown_never_pass") is True and
           master.get("unknown_never_pass") is True and
           all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
               for x in (price,master)),"SOURCE_SAFETY")
    demand(engine.git_blob(ROOT/"canonical_current_price_dv30.json")==
           engine.PRICE_SHA and
           engine.git_blob(ROOT/"canonical_current_master_manifest.json")==
           engine.MASTER_SHA,"EXACT_GIT_SOURCE_SHA")
    dates=list(engine.official_frozen_exact30())
    demand(len(dates)==30 and dates[-1]==ASOF,"OFFICIAL_DATE_COHORT")
    return symbols,dates

def classify(daily,halfhour,batch,dates):
    demand(type(daily) is dict and type(halfhour) is dict and
           set(daily).issubset(batch) and set(halfhour).issubset(batch),
           "PROVIDER_BATCH_KEY_SET")
    status={}
    for symbol in batch:
        try:
            status[symbol]=engine.classify_one(
                daily.get(symbol,[]),halfhour.get(symbol,[]),dates)
        except (ValueError,TypeError,KeyError,OverflowError):
            status[symbol]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    demand(len(status)==len(batch),"SYMBOL_TRUNCATION")
    return status

def report(unknown,dates):
    statuses={s:"UNKNOWN_NOT_YET_ATTEMPTED" for s in unknown}
    for s in PRIOR:statuses[s]=REUSED
    return {"schema":"XRAY_FROZEN_PRICE540_PERSONAL_30MIN_BOUNDS_SHADOW_V1",
            "asof_et":ASOF,"price_git_blob_sha":engine.PRICE_SHA,
            "master_git_blob_sha":engine.MASTER_SHA,
            "expected30_dates_sha256":engine.sha_lines(dates),
            "frozen_symbol_count":len(unknown),
            "prior_verified_symbols":list(PRIOR),
            "prior_verified_ci_runs":list(PRIOR_RUNS),
            "new_symbol_requests_expected":len(unknown)-len(PRIOR),
            "symbol_statuses":statuses,
            "current_classification_count":len(PRIOR),
            "scope_fully_classified":False,"api_calls":0,
            "api_call_budget":MAX_HTTP_CALLS,"batch_size_max":BATCH,
            "provider_stop_reason":None,"counts":{},
            "provider":"ALPACA_PERSONAL_SIP_1DAY_AND_30MIN_RAW",
            "close_auction_correction_verified":False,
            "daily_volume_exact_rth_proven":False,
            "corporate_action_pit_proven":False,
            "automated_feed_rights_independently_attested":False,
            "primary_price_or_dv30_created":False,
            "primary_mc_created":False,"r92_created":False,
            "provider_raw_ohlcv_persisted":False,
            "historical_replay_not_current":True,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def recompute(r):
    r["counts"]=dict(sorted(collections.Counter(
        r["symbol_statuses"].values()).items()))
    r["current_classification_count"]=sum(
        value!="UNKNOWN_NOT_YET_ATTEMPTED"
        for value in r["symbol_statuses"].values())
    r["scope_fully_classified"]=r["current_classification_count"]==r["frozen_symbol_count"]
    return r

def persist(path,r):
    demand(not path.resolve().is_relative_to(ROOT.parent.resolve()),
           "NO_REPOSITORY_OHLCV")
    path.write_text(json.dumps(recompute(r),sort_keys=True,indent=2)+"\n")

def selftest():
    dates=list(engine.official_frozen_exact30())
    fake=sorted(set(PRIOR)|{"OTHER"})
    p={"unknown_symbols":fake,"unknown_count":len(fake),"pass_count":0,
       "asof_et":ASOF,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True}
    # Pure metadata invariant; full file / exact SHA is independently checked live.
    r=report(fake,dates)
    demand(recompute(r)["current_classification_count"]==8
           and r["scope_fully_classified"] is False
           and r["counts"][REUSED]==8,"PRIOR_REUSE")
    r["symbol_statuses"]["OTHER"]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    demand(recompute(r)["scope_fully_classified"] is True
           and r["r92_created"] is False,"UNKNOWN_NOT_PASS")
    valid={}
    needreject=[
      ({"FOREIGN":[]},{},["OTHER"]),
      ({"OTHER":[]},{"FOREIGN":[]},["OTHER"])]
    for d,h,b in needreject:
        try:classify(d,h,b,dates)
        except ValueError:continue
        raise AssertionError("FOREIGN_BATCH_ACCEPTED")
    demand(MAX_HTTP_CALLS>=2*MAX_BATCHES
           and MAX_HTTP_CALLS<=160,"CALL_BUDGET")
    print("XRAY_PRICE540_SELFTEST=PASS_3_NEGATIVE_PRIOR_REUSE_UNKNOWN_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--frozen-20261012-all540",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        demand(not args.frozen_20261012_all540 and args.out is None,
               "SELFTEST_ARGS")
        selftest()
        return
    demand(args.frozen_20261012_all540 and args.out is not None,"ONE_SHOT_REQUIRED")
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    symbols,dates=exact_scope(price,master)
    r=report(symbols,dates)
    persist(args.out,r)
    creds=(os.getenv("XRAY_ALPACA_DATA_KEY_ID")
           or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY")
            or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    demand(creds and secret,"PRIVATE_KEYS_REQUIRED")
    pending=[s for s in symbols if s not in PRIOR]
    demand((len(pending)+BATCH-1)//BATCH<=MAX_BATCHES,
           "BATCH_LIMIT")
    for n in range(0,len(pending),BATCH):
        batch=pending[n:n+BATCH]
        engine.SYMBOLS=tuple(batch)
        try:
            daily,halfhour,calls=engine.fetch((creds,secret))
            demand(type(calls) is int and 2<=calls<=engine.MAX_CALLS,
                   "INVALID_CALL_COUNT")
            r["api_calls"]+=calls
            r["symbol_statuses"].update(classify(daily,halfhour,batch,dates))
        except (RuntimeError,ValueError,urllib.error.HTTPError,
                urllib.error.URLError,TimeoutError) as exc:
            message=str(exc)
            if isinstance(exc,urllib.error.HTTPError):
                message="HTTP_"+str(exc.code)
            if not (message.startswith("HTTP_") or
                    message.startswith("XRAY_") or
                    message.startswith("ALPACA_")):
                message="PROVIDER_FAILURE_REDACTED"
            r["provider_stop_reason"]=message
            for symbol in batch:
                r["symbol_statuses"][symbol]="UNKNOWN_PROVIDER_"+message
            persist(args.out,r)
            break
        demand(r["api_calls"]<=MAX_HTTP_CALLS,
               "GLOBAL_PROVIDER_CALL_BUDGET")
        persist(args.out,r)
        if n+BATCH<len(pending):time.sleep(0.8)
    recompute(r)
    print("XRAY_PRICE540_SHADOW_COUNTS="+json.dumps(r["counts"],sort_keys=True))
    print("XRAY_PRICE540_CLASSIFIED="+str(r["current_classification_count"])+"/540")
    print("XRAY_PRICE540_ACTUAL_API_CALLS="+str(r["api_calls"]))
    print("XRAY_PRICE540_NO_PRIMARY_MC_R92=PASS")

if __name__=="__main__":
    main()
