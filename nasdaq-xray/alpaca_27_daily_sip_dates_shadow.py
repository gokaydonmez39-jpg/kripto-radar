#!/usr/bin/env python3
"""One-shot bounded 27-symbol personal SIP anomalous-session date finder.

Reuses frozen 540 census, exact current source scope and only ONE new HTTP
request for the 27 unresolved daily-bar shapes. No vendor price, volume,
raw bar, C4.17 PRICE PASS, market cap or R92 is published or created.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import subprocess
import urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo

from alpaca_540_personal_daily_sip_coverage import (
    ROOT,REPO,UTC,NY,exact_source,fetch_live,sha_lines,
)
from alpaca_sip_exact30_backup_probe import personal_shadow_access

CHECKPOINT=ROOT/"research/continuation_checkpoint_20261013_alpaca_540_anomaly_queue_v1.json"
MASTER=ROOT/"canonical_current_master_manifest.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_PERSONAL_27_SIP_ANOMALOUS_DATES_SHADOW_V1"

def need(ok,msg):
    if not ok:raise ValueError("XRAY_27_"+msg)

def symbols_from_checkpoint(checkpoint,master_sha,price_sha,scope,days):
    need(checkpoint.get("schema")=="XRAY_C417_PERSONAL_SIP_ANOMALY_FROZEN_QUEUE_V1"
         and checkpoint.get("source_master_blob_sha")==master_sha
         and checkpoint.get("source_price_blob_sha")==price_sha,
         "SOURCE_BLOB_MISMATCH")
    need(checkpoint.get("asof_et")==days[-1]
         and checkpoint.get("source_exact30_sha256")==sha_lines(days)
         and checkpoint.get("source_540_symbol_set_sha256")==sha_lines(sorted(scope)),
         "SOURCE_EPOCH_DRIFT")
    rows=checkpoint.get("affected")
    need(type(rows) is list and len(rows)==27,"DIAGNOSTIC_COUNT")
    expected_reason_counts={"NONPOSITIVE_VOLUME":26,"BAR_COUNT_NOT_30":1}
    symbols=[]
    for row in rows:
        need(type(row) is dict
             and set(row)=={"symbol","classification","reason"}
             and row["reason"] in expected_reason_counts
             and type(row["symbol"]) is str
             and row["symbol"] in scope,"BAD_ANOMALY_ROW")
        symbols.append(row["symbol"])
    need(len(symbols)==len(set(symbols))
         and sha_lines(sorted(symbols))==checkpoint.get("source_affected_symbols_sha256")
         and {reason:sum(r["reason"]==reason for r in rows)
              for reason in expected_reason_counts}==expected_reason_counts,
         "SCOPE_OR_REASON_HASH_DRIFT")
    return rows

def inspect_dates(bars,days):
    """Dates only. Never serialize price/volume or vendor trade records."""
    expected=set(days)
    if type(bars) is not list:
        return {"observed_bars":0,"missing_official_days":list(days),
                "nonpositive_volume_days":[],"bad_shape_days":[],
                "reason":"MISSING_SYMBOL_BARS"}
    seen=set();bad=[];nonpositive=[];alien=[]
    for bar in bars:
        if type(bar) is not dict or type(bar.get("t")) is not str:
            return {"observed_bars":len(bars),"missing_official_days":[],
                    "nonpositive_volume_days":[],"bad_shape_days":[],
                    "reason":"MALFORMED_TIMESTAMP_OR_BAR"}
        try:
            instant=dt.datetime.fromisoformat(bar["t"].replace("Z","+00:00"))
            if instant.tzinfo is None:raise ValueError("naive")
            day=instant.astimezone(NY).date().isoformat()
        except (TypeError,ValueError,OverflowError):
            return {"observed_bars":len(bars),"missing_official_days":[],
                    "nonpositive_volume_days":[],"bad_shape_days":[],
                    "reason":"INVALID_DATETIME"}
        if day not in expected:alien.append(day);continue
        if day in seen:bad.append(day)
        seen.add(day)
        vol=bar.get("v")
        if type(vol) is int and vol<=0:nonpositive.append(day)
        elif type(vol) is not int:bad.append(day)
    return {"observed_bars":len(bars),
            "missing_official_days":sorted(expected-seen),
            "nonpositive_volume_days":sorted(set(nonpositive)),
            "bad_shape_days":sorted(set(bad+alien)),
            "reason":"OBSERVED_DATE_METADATA_ONLY"}

def measure(master,price,checkpoint,env,now,master_sha,price_sha,getter=None):
    report={"schema":SCHEMA,"asof_et":price.get("asof_et"),
            "status":"BLOCKED_PRECONDITIONS","api_calls":0,"requested":27,
            "completed":0,"remaining":27,"details":[],
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "personal_research_only":True,"raw_vendor_bars_persisted":False,
            "prices_or_volumes_persisted":False,"primary_dv30_created":0,
            "primary_mc_created":0,"r92_created":0}
    try:
        scope,days=exact_source(master,price,now)
        rows=symbols_from_checkpoint(checkpoint,master_sha,price_sha,scope,days)
    except (KeyError,TypeError,ValueError,IndexError):
        return report
    report["source_master_blob_sha"]=master_sha
    report["source_price_blob_sha"]=price_sha
    report["frozen_affected_symbols_sha256"]=sha_lines(sorted(r["symbol"] for r in rows))
    if not personal_shadow_access(env):
        report["status"]="BLOCKED_PERSONAL_SHADOW_OPT_IN"
        return report
    key=env.get("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=env.get("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    if not key or not secret:
        report["status"]="BLOCKED_CREDENTIALS"
        return report
    report["api_calls"]=1
    try:
        fetch=getter if getter is not None else fetch_live((key,secret))
        vendor=fetch([r["symbol"] for r in rows],days,None)
        need(type(vendor) is dict and type(vendor.get("bars")) is dict,
             "VENDOR_SCHEMA")
        need(not vendor.get("next_page_token"),"ONE_CALL_PAGINATION_INCOMPLETE")
        data=vendor["bars"]
        expected_symbols={r["symbol"] for r in rows}
        # An empty or partially missing map is not 27 observed symbols.
        # Such provider responses must never be counted as completed.
        need(set(data)==expected_symbols,"PARTIAL_OR_FOREIGN_SYMBOL_RESPONSE")
        need(all(type(data[s]) is list and len(data[s])>0 for s in expected_symbols),
             "EMPTY_SYMBOL_RESPONSE")
        details=[]
        for row in rows:
            item=inspect_dates(data.get(row["symbol"]),days)
            details.append({"symbol":row["symbol"],
                            "prior_reason":row["reason"],
                            **item})
        report["details"]=details
        report["completed"]=27
        report["remaining"]=0
        report["status"]="SHADOW_27_DATE_DIAGNOSTICS_ONLY_NOT_PRIMARY"
    except (ValueError,urllib.error.HTTPError,urllib.error.URLError,
            TimeoutError,OSError,RuntimeError,TypeError):
        report["status"]="BLOCKED_ONE_CALL_VENDOR_OR_INTEGRITY"
    return report

def selftest():
    from copy import deepcopy
    import pandas_market_calendars as mcal
    days=[d.date().isoformat() for d in mcal.get_calendar("NASDAQ").valid_days(
         start_date="2026-08-31",end_date="2026-10-12")]
    need(len(days)==30,"SELFTEST_DAYS")
    import hashlib
    def sha_file(data):
        raw=json.dumps(data,sort_keys=True).encode()
        return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    scope=[f"T{i:03d}" for i in range(540)]
    changed=[{"symbol":s,"reason":"NONPOSITIVE_VOLUME","classification":"INTEGRITY"}
             for s in scope[:26]]
    changed.append({"symbol":scope[26],"reason":"BAR_COUNT_NOT_30",
                    "classification":"INCOMPLETE"})
    master={"asof_et":days[-1],"execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"pass_symbols":scope}
    price={"asof_et":days[-1],"execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True,"unknown_count":540,"unknown_symbols":scope,
           "expected30":days}
    ms="a"*40;ps="b"*40
    ck={"schema":"XRAY_C417_PERSONAL_SIP_ANOMALY_FROZEN_QUEUE_V1",
        "source_master_blob_sha":ms,"source_price_blob_sha":ps,
        "asof_et":days[-1],"source_exact30_sha256":sha_lines(days),
        "source_540_symbol_set_sha256":sha_lines(sorted(scope)),
        "source_affected_symbols_sha256":sha_lines(sorted(x["symbol"] for x in changed)),
        "affected":changed}
    def bar(date):
        t=dt.datetime.combine(dt.date.fromisoformat(date),dt.time.min,NY)
        return {"t":t.astimezone(UTC).isoformat().replace("+00:00","Z"),
                "v":1000}
    allrows=[bar(day) for day in days]
    calls=[]
    def mock(symbols,dates,token):
        calls.append((len(symbols),token))
        result={}
        for x in symbols:
            q=deepcopy(allrows)
            if x==scope[26]:q.pop()
            else:q[0]["v"]=0
            result[x]=q
        return {"bars":result,"next_page_token":None}
    now=dt.datetime(2026,10,13,19,50,tzinfo=UTC)
    enabled={"XRAY_ALPACA_PERSONAL_BASIC_SHADOW_ENABLED":"true",
             "XRAY_ALPACA_DATA_KEY_ID":"fake","XRAY_ALPACA_DATA_SECRET_KEY":"fake"}
    q=measure(master,price,ck,enabled,now,ms,ps,mock)
    need(q["completed"]==27 and q["api_calls"]==1
         and q["remaining"]==0 and calls==[(27,None)]
         and q["details"][0]["nonpositive_volume_days"]==[days[0]]
         and q["details"][-1]["missing_official_days"]==[days[-1]]
         and q["primary_dv30_created"]==0 and q["r92_created"]==0,"PASS_FIXTURE")
    # These three missing/empty payloads previously produced a fake
    # completed=27 success, even with no observed symbol data.
    def require_blocked_response(payload,label):
        observed=measure(master,price,ck,enabled,now,ms,ps,
                         lambda syms,dates,token:payload)
        need(observed["status"]=="BLOCKED_ONE_CALL_VENDOR_OR_INTEGRITY"
             and observed["completed"]==0 and observed["remaining"]==27
             and observed["api_calls"]==1 and observed["details"]==[],
             label)
    require_blocked_response({"bars":{},"next_page_token":None},
                             "EMPTY_MAP_FAKE_SUCCESS")
    require_blocked_response({"bars":{scope[0]:deepcopy(allrows)},
                              "next_page_token":None},
                             "PARTIAL_MAP_FAKE_SUCCESS")
    require_blocked_response({"bars":{s:deepcopy(allrows) if s!=scope[0] else []
                                      for s in (r["symbol"] for r in changed)},
                              "next_page_token":None},
                             "EMPTY_TICKER_FAKE_SUCCESS")
    no=measure(master,price,ck,{},now,ms,ps,mock)
    need(no["api_calls"]==0 and len(calls)==1,"OPT_IN_GATE")
    altered=dict(ck,source_price_blob_sha="0"*40)
    bad=measure(master,price,altered,enabled,now,ms,ps,mock)
    need(bad["api_calls"]==0 and len(calls)==1,"BLOB_DRIFT_GATE")
    drift=measure(master,price,ck,enabled,now,ms,ps,
         lambda syms,dates,token:{"bars":{},"next_page_token":"more"})
    need(drift["status"]=="BLOCKED_ONE_CALL_VENDOR_OR_INTEGRITY"
         and drift["api_calls"]==1 and drift["completed"]==0,"PAGINATION_GATE")
    print("XRAY_PERSONAL_27_DATE_SCOPE_SELFTEST=PASS_ONE_CALL_27_DATES_3_PARTIAL_RESPONSE_NEGATIVES_NO_HTTP")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    need(args.out is not None and
         not args.out.resolve().is_relative_to(REPO.resolve()),"OUTPUT_PRIVATE")
    master=json.loads(MASTER.read_text(encoding="utf-8"))
    price=json.loads(PRICE.read_text(encoding="utf-8"))
    checkpoint=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    sha=lambda path:subprocess.check_output(
        ["git","hash-object",str(path)],text=True).strip()
    report=measure(master,price,checkpoint,os.environ,dt.datetime.now(UTC),
         sha(MASTER),sha(PRICE))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                        encoding="utf-8")
    print("XRAY_27_DATES_STATUS="+report["status"])
    print("XRAY_27_DATES_COUNTS="+json.dumps({
          "requested":report["requested"],"completed":report["completed"],
          "remaining":report["remaining"],"api_calls":report["api_calls"],
          "nonpositive_symbols":sum(bool(x["nonpositive_volume_days"])
             for x in report["details"]),
          "missing_day_symbols":sum(bool(x["missing_official_days"])
             for x in report["details"])},sort_keys=True))
    print("XRAY_27_NO_PRIMARY_MC_R92=PASS")

if __name__=="__main__":
    main()
