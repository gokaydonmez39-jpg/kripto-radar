#!/usr/bin/env python3
"""Entire frozen 2026-10-13 ROOT UNKNOWN cohort, personal SIP research only.

Reads up to 16 symbols per bounded request; saves ONLY non-vendor metadata,
per-symbol status, official calendar & exact frozen root blob SHA. The four
symbols already measured in verified CI #38477817138 are not re-downloaded.
No changes to canonical PRICE, MASTER, MC, HISTORY, R92, account or G9.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import alpaca_root_asof_260_four_symbol_shadow as evidence

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
PREVIOUS=("AAPL","AMZN","MSFT","NVDA")
PREVIOUS_CI_RUN=38477817138
PREVIOUS_JSON_SHA256="79f109ae26c8759a03f60098125388adaface20f57a6838104528acf3f0295a9"
MAX_BATCH=16
MAX_CALLS=210
RESPONSE_LIMIT=5_000_000
FEED_URL="https://data.alpaca.markets/v2/stocks/bars"
POSITIVE="OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY"
REUSED="PRIOR_VERIFIED_260_52_SIP_SHADOW_NOT_PRIMARY"

def require(ok,why):
    if not ok:
        raise ValueError("XRAY_FULL_ROOT260_"+why)

def frozen_scope(state):
    require(type(state) is dict,"ROOT_TYPE")
    require(state.get("asof_et")==ASOF and state.get("status")=="HISTORY_PARTIAL"
            and state.get("unknown_never_pass") is True
            and state.get("execution")=="NONE"
            and state.get("real_money")=="NO-GO","EPOCH_SAFETY")
    queue=state.get("queue")
    results=state.get("results")
    require(type(queue) is list and queue==sorted(set(queue))
            and len(queue)==state.get("queue_total")==state.get("unknown_count")
            and type(results) is dict and set(queue)==set(results),
            "ROOT_EXACT_UNKNOWN_SCOPE")
    require(all(type(x) is str and results[x].get("status","").startswith("UNKNOWN")
                for x in queue),"SOURCE_ROOT_FALSE_PASS")
    require(set(PREVIOUS).issubset(queue),"PRIOR_COHORT_NOT_IN_ROOT")
    return queue

def verify_page(data,batch):
    require(type(data) is dict and type(data.get("bars")) is dict,
            "PROVIDER_RESPONSE")
    bars=data["bars"]
    require(set(bars).issubset(set(batch)),"FOREIGN_SYMBOL")
    require(data.get("next_page_token") is None,"INCOMPLETE_PAGE_NEVER_PASS")
    require(all(type(v) is list for v in bars.values()),"MALFORMED_ROWS")
    return bars

def request_one(batch,first_date,key,secret):
    require(type(batch) is list and 1<=len(batch)<=MAX_BATCH
            and len(set(batch))==len(batch),"BATCH_SCOPE")
    start=(dt.date.fromisoformat(first_date)-dt.timedelta(days=7)).isoformat()
    params={"symbols":",".join(batch),"timeframe":"1Day","feed":"sip",
            "adjustment":"raw","sort":"asc","limit":"10000",
            "asof":ASOF,"start":start+"T00:00:00-04:00",
            "end":"2026-10-13T16:30:00-04:00"}
    req=urllib.request.Request(
        FEED_URL+"?"+urllib.parse.urlencode(params),headers={
         "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
         "Accept":"application/json","User-Agent":"XRAY-Personal-Research/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=35) as f:
            require(f.status==200,"HTTP_NON200")
            raw=f.read(RESPONSE_LIMIT+1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP_"+str(exc.code)) from exc
    except (urllib.error.URLError,TimeoutError) as exc:
        raise RuntimeError("NETWORK_UNAVAILABLE") from exc
    require(len(raw)<=RESPONSE_LIMIT,"RESPONSE_OVERSIZE")
    try:payload=json.loads(raw)
    except (TypeError,ValueError) as exc:
        raise RuntimeError("PROVIDER_JSON_INVALID") from exc
    return verify_page(payload,batch)

def output(state,queue,dates,weeks):
    statuses={s:"UNKNOWN_NOT_YET_ATTEMPTED" for s in queue}
    for symbol in PREVIOUS:
        statuses[symbol]=REUSED
    return {"schema":"XRAY_FULL_ROOT_260_52_PERSONAL_SIP_COHORT_V1",
            "asof_et":ASOF,"source_root_git_blob_sha":
                evidence.blob_sha(ROOT/"sina_state.json"),
            "source_root_unknown_count":len(queue),
            "official_daily_session_count":len(dates),
            "official_weekly_close_count":len(weeks),
            "official_first_daily_session":dates[0],
            "official_last_daily_session":dates[-1],
            "prior_ci_run":PREVIOUS_CI_RUN,
            "prior_ci_json_sha256":PREVIOUS_JSON_SHA256,
            "prior_reused_symbols":list(PREVIOUS),
            "provider":"ALPACA_PERSONAL_HISTORICAL_SIP_RAW",
            "total_scope":len(queue),"requested_new_count":len(queue)-len(PREVIOUS),
            "actual_api_calls":0,"batch_size_max":MAX_BATCH,
            "api_call_cap":MAX_CALLS,"provider_problem":None,
            "classified_source_count":len(PREVIOUS),
            "symbol_statuses":statuses,"counts":{},
            "full_scope_reached":False,
            "canonical_history_written":False,
            "c417_primary_price_created":False,
            "c417_primary_history_created":False,
            "c417_primary_mc_created":False,
            "r92_created":False,"vendor_raw_ohlcv_persisted":False,
            "non_display_enterprise_entitlement_inferred":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def summarize(report):
    states=report["symbol_statuses"]
    report["counts"]=dict(sorted(collections.Counter(states.values()).items()))
    report["classified_source_count"]=sum(
        x not in {"UNKNOWN_NOT_YET_ATTEMPTED"} for x in states.values())
    report["full_scope_reached"]=report["classified_source_count"]==report["total_scope"]
    return report

def persist(out,report):
    require(not out.resolve().is_relative_to(ROOT.parent.resolve()),
            "NO_REPOSITORY_ARTIFACT")
    out.write_text(json.dumps(summarize(report),sort_keys=True,indent=2)+"\n")

def selftest():
    state={"asof_et":ASOF,"status":"HISTORY_PARTIAL",
        "unknown_never_pass":True,"execution":"NONE","real_money":"NO-GO",
        "queue":list(PREVIOUS)+["ZZZZ"],"queue_total":5,"unknown_count":5,
        "results":{k:{"status":"UNKNOWN_STATIC"} for k in
                   list(PREVIOUS)+["ZZZZ"]}}
    state["queue"]=sorted(state["queue"])
    q=frozen_scope(state)
    require(q==sorted(q),"POSITIVE_SCOPE")
    x=output(state,q,["2025-09-30","2026-10-13"],["2026-10-13"])
    require(summarize(x)["classified_source_count"]==4
            and x["full_scope_reached"] is False
            and x["counts"][REUSED]==4,"PRIOR_PROVENANCE")
    x["symbol_statuses"]["ZZZZ"]="UNKNOWN_PROVIDER_HTTP_429"
    require(summarize(x)["full_scope_reached"] is True
            and x["counts"]["UNKNOWN_PROVIDER_HTTP_429"]==1
            and x["r92_created"] is False,"FAIL_CLOSED_COMPLETE")
    a={"bars":{"ZZZZ":[]},"next_page_token":None}
    require(verify_page(a,["ZZZZ"])=={"ZZZZ":[]},"GOOD_PAGE")
    cases=[
        ("FOREIGN",{"bars":{"AAPL":[]}}),
        ("TOKEN",{"bars":{"ZZZZ":[]},"next_page_token":"next"}),
        ("SCHEMA",{"bars":[]}),
        ("BAD_ROWS",{"bars":{"ZZZZ":{}}})]
    for label,bad in cases:
        try:verify_page(bad,["ZZZZ"])
        except ValueError:continue
        raise AssertionError("FALSE_PASS_"+label)
    bad=dict(state,unknown_count=4)
    try:frozen_scope(bad)
    except ValueError:pass
    else:raise AssertionError("FALSE_PASS_ROOT_COUNT")
    print("XRAY_FULL_ROOT260_SELFTEST=PASS_PREVIOUS_REUSE_5_NEGATIVES_NO_PRIMARY")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--all-root-unknown",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        require(not args.all_root_unknown and args.out is None,"SELFTEST_MODE")
        selftest()
        return
    require(args.all_root_unknown and args.out is not None,"EXPLICIT_MODE")
    state=json.loads((ROOT/"sina_state.json").read_text())
    queue=frozen_scope(state)
    dates,weeks,refstate=evidence.source_scope()
    require(refstate["unknown_count"]==len(queue),"ROOT_CALENDAR_SCOPE")
    report=output(state,queue,dates,weeks)
    persist(args.out,report)
    key=(os.environ.get("XRAY_ALPACA_DATA_KEY_ID") or
         os.environ.get("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.environ.get("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    if not (key and secret):
        report["provider_problem"]="NO_PRIVATE_ALPACA_SOURCE_KEYS"
        persist(args.out,report)
        raise SystemExit("XRAY_FULL_ROOT260_NO_SOURCE_KEYS")
    todo=[s for s in queue if s not in PREVIOUS]
    required_calls=(len(todo)+MAX_BATCH-1)//MAX_BATCH
    require(required_calls<=MAX_CALLS,"PROVIDER_CALL_BUDGET")
    require(evidence.sufficient_delay(ASOF,dt.datetime.now(dt.timezone.utc)),
            "HISTORICAL_DELAY_NOT_EXPIRED")
    for pos in range(0,len(todo),MAX_BATCH):
        batch=todo[pos:pos+MAX_BATCH]
        report["actual_api_calls"]+=1
        try:
            bars=request_one(batch,dates[0],key,secret)
            for symbol in batch:
                report["symbol_statuses"][symbol]=evidence.classify(
                    bars.get(symbol,[]),dates,weeks)
        except (RuntimeError,ValueError) as exc:
            detail=str(exc)
            if not detail.startswith(("HTTP_","NETWORK_","PROVIDER_",
                    "XRAY_FULL_ROOT260_")):
                detail="UNCLASSIFIED_TRANSPORT"
            report["provider_problem"]=detail
            for symbol in batch:
                report["symbol_statuses"][symbol]="UNKNOWN_PROVIDER_"+detail
            persist(args.out,report)
            print("XRAY_FULL_ROOT260_BATCH_FAILED="+detail)
            if "HTTP_429" in detail or "HTTP_403" in detail:
                break
        persist(args.out,report)
        if pos+MAX_BATCH<len(todo):
            time.sleep(0.65)
    summarize(report)
    print("XRAY_FULL_ROOT260_COUNTS="+json.dumps(report["counts"],sort_keys=True))
    print("XRAY_FULL_ROOT260_CLASSIFIED="+str(report["classified_source_count"])
          +"/"+str(report["total_scope"]))
    print("XRAY_FULL_ROOT260_PROVIDER_CALLS="+str(report["actual_api_calls"]))
    print("XRAY_FULL_ROOT260_PRIMARY_R92=0")

if __name__=="__main__":
    main()
