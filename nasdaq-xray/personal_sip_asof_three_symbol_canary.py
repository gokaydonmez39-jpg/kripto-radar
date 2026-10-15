#!/usr/bin/env python3
"""Three-symbol bounded runner-side SIP ASOF diagnostic; NEVER alpha authority.

Only counts whether an independently observed historical SIP daily bar exists
when the current Sina root says the same completed ASOF is missing. No vendor
OHLCV, prices, volumes, symbols, secrets or user/account data are persisted.
The Alpaca connector inside ChatGPT and runner credentials are distinct.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import urllib.error
from pathlib import Path

from alpaca_full_universe_asof_sip_availability import (
    historical_request_window, query_sip, validate_one,
)
from sina_state_hash_guard import seal, verify
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_THREE_SYMBOL_RUNNER_SIP_ASOF_CANARY_V1"
SAMPLES=("AAPL","MSFT","NVDA")
REASON="ASOF_MISSING_REQUIRES_RESOLUTION"


def need(condition, code):
    if not condition:
        raise ValueError("XRAY_SIP_CANARY_"+code)


def select(root, sina, asof):
    """Exact newest root/source epoch; source missing is NOT proof of a bad ticker."""
    need(type(root) is dict and type(sina) is dict, "SOURCE_OBJECT")
    need(root.get("status")=="PARTIAL_HISTORY" and
         sina.get("status")=="HISTORY_PARTIAL", "SOURCE_PARTIAL_STATE")
    need(root.get("asof_et")==sina.get("asof_et")==asof, "SOURCE_EPOCH")
    need(root.get("execution")==sina.get("execution")=="NONE" and
         root.get("real_money")==sina.get("real_money")=="NO-GO" and
         sina.get("unknown_never_pass") is True, "NO_EXECUTION_NO_PROMOTION")
    queue=sina.get("queue")
    rows=sina.get("results")
    need(type(queue) is list and type(rows) is dict and
         set(SAMPLES).issubset(queue) and
         queue==sorted(set(queue)) and set(rows)==set(queue) and
         len(queue)==sina.get("queue_total")==root.get("queue_total")==
         sina.get("cursor") and
         hashlib.sha256("\n".join(queue).encode()).hexdigest()==
         sina.get("queue_hash")==root.get("queue_hash"), "QUEUE_PARTITION_SHA")
    need(verify(sina)=="PASS_DETERMINISTIC_BLOB_INTERNAL",
         "SOURCE_STATE_INTEGRITY")
    missing=[]
    for symbol in SAMPLES:
        row=rows[symbol]
        need(type(row) is dict and type(row.get("status")) is str,
             "SOURCE_SYMBOL_STATUS")
        info=row.get("info")
        if (row["status"]=="UNKNOWN_STATIC" and type(info) is dict
            and info.get("reason")==REASON):
            missing.append(symbol)
    return missing


def evaluate(root, sina, asof, credentials, provider, validator=validate_one):
    missing=select(root,sina,asof)
    counts={"sina_asof_missing_sampled":len(missing),
            "independent_sip_daily_observed":0,
            "independent_sip_daily_unknown":len(missing)}
    report={
        "schema":SCHEMA,"asof_et":asof,
        "source_queue_hash":sina["queue_hash"],
        "source_scope_count":sina["queue_total"],
        "sample_size":len(SAMPLES),
        "counts":counts,"provider_page_requests":0,
        "status":"NO_SINA_MISSING_SAMPLES_NO_REQUEST",
        "source":"ALPACA_HISTORICAL_SIP_RESEARCH_CANARY",
        "scope":"INDEPENDENT_ROOT_HISTORY_SOURCE_DIAGNOSTIC_ONLY",
        "same_asof_root_sina_bound":True,
        "connector_access_is_not_runner_entitlement":True,
        "canonical_price_dv30_attested":False,
        "canonical_history_260_52_attested":False,
        "mc_authority_attested":False,
        "registered_r92":False,
        "device_receipt_attested":False,
        "no_vendor_ohlcv_persisted":True,
        "no_canonical_mutations":True,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }
    if not missing:
        return report
    key,secret=credentials
    if not key or not secret:
        report["status"]="RUNNER_CREDENTIALS_NOT_CONFIGURED"
        return report
    try:
        bars,pages=provider(missing,asof,key,secret)
        need(type(bars) is dict and 1<=pages<=2 and
             set(bars).issubset(missing), "PROVIDER_SCOPE_OR_PAGINATION")
        yes=0
        for symbol in missing:
            rows=bars.get(symbol,[])
            need(type(rows) is list, "PROVIDER_BAR_STRUCTURE")
            if len(rows)==1 and validator(rows[0],asof):
                yes+=1
        counts["independent_sip_daily_observed"]=yes
        counts["independent_sip_daily_unknown"]=len(missing)-yes
        report["provider_page_requests"]=pages
        report["status"]=(
            "INDEPENDENT_SIP_ASOF_OBSERVED_SOURCE_DIFFERENTIAL_NOT_ALPHA"
            if yes else "INDEPENDENT_SIP_ASOF_NOT_OBSERVED_UNKNOWN")
    except urllib.error.HTTPError as exc:
        report["status"]=(
            "RUNNER_SIP_HTTP_403_DENIED" if exc.code in (401,403) else
            "RUNNER_SIP_HTTP_429_QUOTA" if exc.code==429 else
            "RUNNER_SIP_HTTP_OTHER_UNKNOWN")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
        report["status"]="RUNNER_SIP_SOURCE_OR_INTEGRITY_UNKNOWN"
    return report


def selftest():
    symbols=list(SAMPLES)
    h=hashlib.sha256("\n".join(symbols).encode()).hexdigest()
    rows={s:{"status":"UNKNOWN_STATIC","info":{"reason":REASON},
             "attempts":1,"updated_at_utc":"2026-10-15T21:05:00+00:00"}
          for s in symbols}
    src={"schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
         "status":"HISTORY_PARTIAL","execution":"NONE","real_money":"NO-GO",
         "unknown_never_pass":True,"asof_et":"2026-10-15",
         "queue":symbols,"queue_total":3,"queue_hash":h,"cursor":3,
         "results":rows,"counts":{"UNKNOWN_STATIC":3},"unknown_count":3,
         "pending_retry":0}
    seal(src)
    root={"status":"PARTIAL_HISTORY","execution":"NONE",
          "real_money":"NO-GO","queue_total":3,"queue_hash":h,
          "asof_et":"2026-10-15"}
    called=[]
    def fake(group,asof,key,secret):
        called.append(tuple(group))
        return {s:[{"t":"2026-10-15T04:00:00Z","c":100.0,"v":3000}]
                for s in group},1
    positive=evaluate(root,src,"2026-10-15",("key","secret"),fake)
    assert positive["counts"]=={"sina_asof_missing_sampled":3,
            "independent_sip_daily_observed":3,
            "independent_sip_daily_unknown":0}
    assert positive["provider_page_requests"]==1 and len(called)==1
    assert not positive["canonical_history_260_52_attested"]
    assert not positive["registered_r92"] and positive["no_vendor_ohlcv_persisted"]
    assert "bars" not in positive and "symbols" not in positive
    negative=evaluate(root,src,"2026-10-15",("key","secret"),
                      lambda x,y,k,v:({},1))
    assert negative["counts"]["independent_sip_daily_unknown"]==3
    unavailable=evaluate(root,src,"2026-10-15",("",""),fake)
    assert unavailable["status"]=="RUNNER_CREDENTIALS_NOT_CONFIGURED"
    assert len(called)==1
    other=copy.deepcopy(src)
    other["results"]["AAPL"]={"status":"FAIL_HISTORY","info":{},
                                    "attempts":1}
    seal(other)
    subset=evaluate(root,other,"2026-10-15",("key","secret"),fake)
    assert subset["counts"]["sina_asof_missing_sampled"]==2
    cases=[
        (lambda a,b: a.update(asof_et="2026-10-14"),"SOURCE_EPOCH"),
        (lambda a,b: b.update(queue_hash="0"*64),"QUEUE_PARTITION_SHA"),
        (lambda a,b: b.update(state_hash="0"*64),"SOURCE_STATE_INTEGRITY"),
        (lambda a,b: a.update(execution="TRADE"),"NO_EXECUTION_NO_PROMOTION"),
        (lambda a,b: b.update(unknown_never_pass=False),"NO_EXECUTION_NO_PROMOTION"),
        (lambda a,b: b["results"].pop("MSFT"),"QUEUE_PARTITION_SHA"),
    ]
    for mutate,code in cases:
        a,b=copy.deepcopy(root),copy.deepcopy(src)
        mutate(a,b)
        try:evaluate(a,b,"2026-10-15",("key","secret"),fake)
        except ValueError as ex:assert code in str(ex),(code,str(ex))
        else:raise AssertionError("UNSAFE_SOURCE_ACCEPTED:"+code)
    assert len(called)==2
    print("XRAY_SIP_CANARY_SELFTEST=PASS_3_POSITIVE_6_NEGATIVE_NO_OHLCV_NO_ALPHA")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--out",type=Path)
    options=parser.parse_args()
    if options.selftest:
        selftest()
        return
    if not options.live or not options.out:
        parser.error("Use --selftest or --live --out")
    root=json.loads((ROOT/"orchestrator_state.json").read_text())
    sina=json.loads((ROOT/"sina_state.json").read_text())
    asof=last_complete_session(dt.datetime.now(dt.timezone.utc))
    keys=(
        os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
        os.getenv("XRAY_ALPACA_API_KEY_ID") or "",
        os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
        os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "",
    )
    result=evaluate(root,sina,asof,keys,
        lambda symbols,epoch,key,secret:
            query_sip(symbols,epoch,key,secret,page_cap=2))
    options.out.parent.mkdir(parents=True,exist_ok=True)
    options.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    # Status and counts only. No provider response details in logs.
    print("XRAY_RUNNER_SIP_CANARY="+json.dumps({
        "asof_et":result["asof_et"],"status":result["status"],
        "counts":result["counts"],"requests":result["provider_page_requests"],
        "no_alpha":not result["canonical_history_260_52_attested"],
    },sort_keys=True))


if __name__=="__main__":
    main()
