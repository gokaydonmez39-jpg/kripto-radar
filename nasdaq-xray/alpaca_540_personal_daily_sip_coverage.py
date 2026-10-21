#!/usr/bin/env python3
"""One-shot, bounded 540-symbol personal historical SIP coverage measurement.

The public GitHub artifact contains only coverage counts, exact source blob SHAs
and safety flags, NEVER OHLCV, proprietary prices/volumes, per-symbol market
measurements or credentials. This is not C4.17 RTH DV30/PRIMARY market cap.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from alpaca_sip_exact30_backup_probe import personal_shadow_access
from alpaca_sip_paginated_transport_shadow import collect_pages
from alpaca_free_sip_shadow_guard import bounded_sip_end
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
SCHEMA="XRAY_PERSONAL_540_EXACT30_DAILY_SIP_COVERAGE_SHADOW_V1"
URL="https://data.alpaca.markets/v2/stocks/bars"
MAX_CALLS=24
CHUNK=32
MAX_RESPONSE_BYTES=1_800_000

def need(ok,code):
    if not ok:
        raise ValueError("SIP540_"+code)

def sha_lines(lines):
    return hashlib.sha256(("\n".join(lines)+"\n").encode()).hexdigest()

def exact_source(master,price,now):
    import pandas_market_calendars as mcal
    require=("execution","real_money","unknown_never_pass")
    for row in (master,price):
        need(type(row) is dict and
             row.get("execution")=="NONE" and
             row.get("real_money")=="NO-GO" and
             row.get("unknown_never_pass") is True,
             "CANONICAL_SAFETY")
    asof=last_complete_session(now)
    need(master.get("asof_et")==price.get("asof_et")==asof,"STALE_ASOF")
    symbols=price.get("unknown_symbols")
    need(type(symbols) is list and len(symbols)==540 and
         len(symbols)==len(set(symbols)) and
         len(symbols)==price.get("unknown_count") and
         set(symbols).issubset(set(master.get("pass_symbols") or [])),
         "NOT_EXACT_CURRENT_540_SCOPE")
    import re
    need(all(type(s) is str and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,12}",s)
             for s in symbols),"BAD_TICKER")
    days=price.get("expected30")
    need(type(days) is list and len(days)==30 and len(set(days))==30,"DATE_COUNT")
    expected=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date=days[0],end_date=asof)]
    need(days==expected and days[-1]==asof,"NOT_OFFICIAL30")
    return symbols,days

def classify(rows,dates):
    if type(rows) is not list or len(rows)!=30:
        return "INCOMPLETE"
    seen={}
    for x in rows:
        if type(x) is not dict or type(x.get("t")) is not str:
            return "INTEGRITY"
        try:
            stamp=dt.datetime.fromisoformat(x["t"].replace("Z","+00:00"))
            if stamp.tzinfo is None:return "INTEGRITY"
            day=stamp.astimezone(NY).date().isoformat()
            if day in seen:return "INTEGRITY"
            seen[day]=True
            o,h,l,c=(x.get(k) for k in ("o","h","l","c"))
            v=x.get("v")
            if not all(type(y) in (int,float) and math.isfinite(y) and y>0
                       for y in (o,h,l,c)):return "INTEGRITY"
            if not (h>=max(o,l,c) and l<=min(o,h,c)):return "INTEGRITY"
            if type(v) is not int or v<=0:return "INTEGRITY"
        except (TypeError,ValueError,OverflowError):
            return "INTEGRITY"
    return "DAILY_SIP_30_VALID_NOT_RTH" if set(seen)==set(dates) else "INCOMPLETE"

def diagnostic_reason(rows,dates):
    """Data-shape diagnosis only: not a statement about exchange causation."""
    if type(rows) is not list:
        return "SYMBOL_MISSING_IN_RESPONSE"
    if len(rows)!=30:
        return "BAR_COUNT_NOT_30"
    observed=set()
    for row in rows:
        if type(row) is not dict or type(row.get("t")) is not str:
            return "MALFORMED_BAR_OR_TIMESTAMP"
        try:
            stamp=dt.datetime.fromisoformat(row["t"].replace("Z","+00:00"))
        except ValueError:
            return "BAD_TIMESTAMP"
        if stamp.tzinfo is None:
            return "NAIVE_TIMESTAMP"
        day=stamp.astimezone(NY).date().isoformat()
        if day in observed:return "DUPLICATE_SESSION"
        observed.add(day)
        vals=[row.get(k) for k in ("o","h","l","c")]
        if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in vals):
            return "BAD_OHLC_NUMBER"
        o,h,l,last=vals
        if h<max(o,l,last) or l>min(o,h,last):
            return "OHLC_ORDER_VIOLATION"
        v=row.get("v")
        if type(v) is not int:
            return "NONINTEGER_OR_UNTYPED_VOLUME"
        if v<=0:return "NONPOSITIVE_VOLUME"
    if observed!=set(dates):
        return "OFFICIAL_DATE_SET_MISMATCH"
    return "UNKNOWN_VALIDATOR_DISAGREEMENT"

def official_close_price_research_bucket(rows,dates):
    """Offline SIP 1Day close triage, no authorization to set canonical PRICE.

    Alpaca market-data FAQ: on tape C, T contributes to DAILY VOLUME but
    NOT to DAILY CLOSE, and 6 contributes to both. This function never
    consumes daily volume as RTH, nor makes a price PASS.
    Only a fully validated, distinct exact30 daily set is eligible.
    """
    need(classify(rows,dates)=="DAILY_SIP_30_VALID_NOT_RTH",
         "UNVERIFIED_DAILY_BAR_INPUT")
    asof=dates[-1]
    matching=[row for row in rows if
        dt.datetime.fromisoformat(row["t"].replace("Z","+00:00"))
          .astimezone(NY).date().isoformat()==asof]
    need(len(matching)==1,"ASOF_CLOSE_EXACTLY_ONE")
    close=matching[0]["c"]
    need(type(close) in (int,float) and math.isfinite(close) and close>0,
         "BAD_ASOF_CLOSE")
    # 5.00 USD is an exact, inclusive C4.17 threshold.
    return "BELOW_5_SHADOW" if close<5.0 else "AT_LEAST_5_SHADOW"

def collect(scope,dates,fetch):
    """At most 24 actual HTTP page attempts TOTAL, even under pagination."""
    calls=[0]
    counters={"DAILY_SIP_30_VALID_NOT_RTH":0,"INCOMPLETE":0,"INTEGRITY":0}
    reasons={}
    affected=[]
    price_buckets={"BELOW_5_SHADOW":0,"AT_LEAST_5_SHADOW":0}
    below_five_symbols=[]
    attempted=0
    failure=None
    for offset in range(0,len(scope),CHUNK):
        chunk=scope[offset:offset+CHUNK]
        def getpage(token):
            if calls[0]>=MAX_CALLS:
                raise RuntimeError("GLOBAL_CALL_BUDGET_EXHAUSTED")
            calls[0]+=1
            return fetch(chunk,dates,token)
        try:
            data=collect_pages(chunk,getpage,max_pages=3)
        except (RuntimeError,urllib.error.HTTPError,urllib.error.URLError,
                TimeoutError,OSError,ValueError):
            failure="UPSTREAM_OR_BUDGET_FAIL_CLOSED"
            break
        for s in chunk:
            rows=data.get(s)
            status=classify(rows,dates)
            counters[status]+=1
            if status=="DAILY_SIP_30_VALID_NOT_RTH":
                classification=official_close_price_research_bucket(rows,dates)
                price_buckets[classification]+=1
                if classification=="BELOW_5_SHADOW":
                    below_five_symbols.append(s)
            else:
                cause=diagnostic_reason(rows,dates)
                reasons[cause]=reasons.get(cause,0)+1
                affected.append({"symbol":s,"classification":status,"reason":cause})
        attempted+=len(chunk)
    need(sum(reasons.values())==len(affected) and
         len(affected)==counters["INCOMPLETE"]+counters["INTEGRITY"],
         "DIAGNOSTIC_ACCOUNTING")
    need(sum(price_buckets.values())==counters["DAILY_SIP_30_VALID_NOT_RTH"]
         and len(below_five_symbols)==price_buckets["BELOW_5_SHADOW"],
         "RESEARCH_PRICE_BUCKET_ACCOUNTING")
    return {"attempted":attempted,"remaining":len(scope)-attempted,
            "api_calls":calls[0],"counts":counters,
            "price_close_research_only":dict(price_buckets),
            "below_5_research_symbol_sha256":sha_lines(sorted(below_five_symbols)),
            "price_source_not_primary":True,
            "confirmed_c417_price_fail_count":0,
            "confirmed_c417_dv30_pass_count":0,
            "diagnostic_reasons":dict(sorted(reasons.items())),
            "affected_symbols":affected,
            "affected_symbols_sha256":sha_lines(sorted(x["symbol"] for x in affected)),
            "failure":failure,"coverage_complete":attempted==len(scope),
            "verified_rth_primary_count":0,"r92_created":False}

def fetch_live(keys,now):
    kid,secret=keys
    def fetch(symbols,dates,token):
        start=dates[0]+"T00:00:00Z"
        end=bounded_sip_end(dates[-1],now,
             (dt.date.fromisoformat(dates[-1])+dt.timedelta(days=1)).isoformat()+"T00:00:00Z")
        params={"symbols":",".join(symbols),"timeframe":"1Day","start":start,
                "end":end,"feed":"sip","adjustment":"raw",
                "limit":"10000","sort":"asc"}
        if token:params["page_token"]=token
        req=urllib.request.Request(URL+"?"+urllib.parse.urlencode(params),
             headers={"APCA-API-KEY-ID":kid,"APCA-API-SECRET-KEY":secret,
             "Accept":"application/json","User-Agent":"XRAY-Personal-Research/1.0"})
        with urllib.request.urlopen(req,timeout=30) as response:
            raw=response.read(MAX_RESPONSE_BYTES+1)
        need(len(raw)<=MAX_RESPONSE_BYTES,"RESPONSE_SIZE")
        return json.loads(raw)
    return fetch

def main_report(master,price,now,env,fetch=None):
    result={"schema":SCHEMA,"asof_et":price.get("asof_et"),
        "status":"BLOCKED_INPUT","execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"personal_noncommercial_research":True,
        "rights_for_raw_redistribution_claimed":False,
        "source_non_display_license_independently_verified":False,
        "primary_dv30_authority":False,"primary_mc_authority":False,
        "vendor_raw_bars_persisted":False,"vendor_raw_quotes_persisted":False,
        "vendor_price_or_volume_values_persisted":False,"r92_created":False,
        "api_calls":0,"attempted":0,"remaining":540,"coverage_complete":False,
        "counts":{"DAILY_SIP_30_VALID_NOT_RTH":0,"INCOMPLETE":0,"INTEGRITY":0}}
    try: scope,days=exact_source(master,price,now)
    except (ValueError,TypeError,KeyError,IndexError):
        return result
    result["unknown_symbol_set_sha256"]=sha_lines(sorted(scope))
    result["exact30_session_sha256"]=sha_lines(days)
    result["requested"]=len(scope)
    if not personal_shadow_access(env):
        result["status"]="BLOCKED_PERSONAL_SHADOW_OPT_IN_MISSING"
        return result
    kid=env.get("XRAY_ALPACA_DATA_KEY_ID","").strip()
    secret=env.get("XRAY_ALPACA_DATA_SECRET_KEY","").strip()
    if not kid or not secret:
        result["status"]="BLOCKED_CREDENTIALS_MISSING"
        return result
    out=collect(scope,days,fetch if fetch is not None else fetch_live((kid,secret),now))
    result.update(out)
    result["status"]=("SHADOW_540_DAILY_SIP_SCOPE_MEASURED_NOT_RTH"
        if out["coverage_complete"] else "BLOCKED_TRANSPORT_OR_PAGINATION_INCOMPLETE")
    return result

def selftest():
    import pandas_market_calendars as mcal
    days=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date="2026-10-12")]
    need(len(days)==30,"FIXTURE_SESSION_COUNT")
    def sample(day):
        stamp=dt.datetime.combine(dt.date.fromisoformat(day),dt.time.min,NY)
        return {"t":stamp.astimezone(UTC).isoformat().replace("+00:00","Z"),
                "o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":100000}
    records=[sample(d) for d in days]
    need(classify(records,days)=="DAILY_SIP_30_VALID_NOT_RTH","VALID")
    need(official_close_price_research_bucket(records,days)=="AT_LEAST_5_SHADOW",
         "ABOVE_THRESHOLD")
    from copy import deepcopy
    below=deepcopy(records)
    below[-1].update(o=4.99,h=5.1,l=4.5,c=4.99)
    need(official_close_price_research_bucket(below,days)=="BELOW_5_SHADOW",
         "BELOW_THRESHOLD")
    boundary=deepcopy(records)
    boundary[-1].update(o=5.00,h=5.5,l=4.5,c=5.00)
    need(official_close_price_research_bucket(boundary,days)=="AT_LEAST_5_SHADOW",
         "EXACT_FIVE_INCLUSIVE")
    bad=deepcopy(records);bad.pop()
    try:official_close_price_research_bucket(bad,days)
    except ValueError:pass
    else:raise AssertionError("MISSING_DAY_PRICE_FALSE_ACCEPT")
    import copy
    negatives=[
        lambda x:x.pop(),lambda x:x[0].update(v=1.5),
        lambda x:x[0].update(v=True),
        lambda x:x[0].update(v=0),
        lambda x:x[0].update(c=float("nan")),
        lambda x:x[0].update(h=8),
        lambda x:x[0].update(t=x[1]["t"]),
        lambda x:x[0].update(t="2026-10-31T00:00:00Z"),
    ]
    for mutate in negatives:
        arr=copy.deepcopy(records);mutate(arr)
        need(classify(arr,days)!="DAILY_SIP_30_VALID_NOT_RTH","NEGATIVE_ACCEPTED")
    calls=[]
    def fake(syms,dates,token):
        calls.append((tuple(syms),token))
        return {"bars":{s:copy.deepcopy(records) for s in syms},
                "next_page_token":None}
    r=collect(["AAPL","NVDA","MSFT"],days,fake)
    need(r["attempted"]==3 and r["remaining"]==0
         and r["api_calls"]==1
         and r["counts"]["DAILY_SIP_30_VALID_NOT_RTH"]==3
         and r["price_close_research_only"]=={
             "BELOW_5_SHADOW":0,"AT_LEAST_5_SHADOW":3}
         and r["confirmed_c417_price_fail_count"]==0
         and r["confirmed_c417_dv30_pass_count"]==0
         and r["verified_rth_primary_count"]==0
         and r["r92_created"] is False,"MOCK_CALL")
    mixed=collect(["AAPL","NVDA"],days,
        lambda syms,dates,token:{"bars":{
            "AAPL":deepcopy(below),"NVDA":deepcopy(boundary)},
            "next_page_token":None})
    need(mixed["price_close_research_only"]=={
             "BELOW_5_SHADOW":1,"AT_LEAST_5_SHADOW":1}
         and mixed["confirmed_c417_price_fail_count"]==0
         and mixed["confirmed_c417_dv30_pass_count"]==0,
         "MIXED_BUCKET_SHADOW_ONLY")
    sample_bad=copy.deepcopy(records)
    sample_bad[0]["v"]=1.5
    d=collect(["AAPL","NVDA"],days,lambda a,b,t:{
        "bars":{"AAPL":copy.deepcopy(records),"NVDA":copy.deepcopy(sample_bad)},
        "next_page_token":None})
    need(d["api_calls"]==1 and d["attempted"]==2 and
         d["counts"]["INTEGRITY"]==1 and
         d["diagnostic_reasons"]=={"NONINTEGER_OR_UNTYPED_VOLUME":1} and
         d["affected_symbols"]==[{
             "symbol":"NVDA","classification":"INTEGRITY",
             "reason":"NONINTEGER_OR_UNTYPED_VOLUME"}],
         "DIAGNOSTIC_NEGATIVE_AND_SCOPING")
    e=collect(["AAPL"],days,lambda a,b,t:{"bars":{},"next_page_token":"x"})
    need(e["attempted"]==0 and not e["coverage_complete"]
         and e["api_calls"]<=MAX_CALLS,"PAGINATION_BLOCK")
    # The original October 12 session closes at 20:00 UTC, but the
    # requested next-day 00:00 UTC is in the future at the 21:10 UTC run.
    # Intercept the outgoing request; no vendor IO, no quota expenditure.
    from unittest.mock import patch
    from contextlib import contextmanager
    captured=[]
    @contextmanager
    def fake_urlopen(req,timeout=30):
        from urllib.parse import urlparse,parse_qs
        qs=parse_qs(urlparse(req.full_url).query)
        captured.append(qs)
        class FakeReply:
            def read(self,size):return b'{"bars":{},"next_page_token":null}'
        yield FakeReply()
    with patch("urllib.request.urlopen",new=fake_urlopen):
        fetch_live(("offline-id","offline-secret"),
             dt.datetime(2026,10,12,21,10,tzinfo=UTC))(
                 ["AAPL"],days,None)
    assert len(captured)==1 and captured[0]["end"]==[
        "2026-10-12T20:50:00+00:00"],captured
    print("XRAY_540_DELAYED_SIP_END=PASS_OFFLINE_FUTURE_MIDNIGHT_CAPPED")
    print("XRAY_PERSONAL_540_SIP_SELFTEST=PASS_8_BAR_NEGATIVES_3_SCOPE_CASES_PRICE_TRIAGE_5USD_NO_HTTP")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:selftest();return
    if args.out is None:parser.error("--out required")
    need(not args.out.resolve().is_relative_to(REPO.resolve()),"PUBLIC_REPO_OUTPUT")
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    result=main_report(master,price,dt.datetime.now(UTC),os.environ)
    result["source_master_blob_sha"]=subprocess.check_output(
        ["git","hash-object",str(ROOT/"canonical_current_master_manifest.json")],
        text=True).strip()
    result["source_price_blob_sha"]=subprocess.check_output(
        ["git","hash-object",str(ROOT/"canonical_current_price_dv30.json")],
        text=True).strip()
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_540_STATUS="+result["status"])
    print("XRAY_PERSONAL_540_COUNTERS="+json.dumps(
        {"attempted":result["attempted"],"remaining":result["remaining"],
         "api_calls":result["api_calls"],"counts":result["counts"]},
        sort_keys=True))
    print("XRAY_PERSONAL_540_PRIMARY_PRICE=0_MC=0_R92=0")

if __name__=="__main__":
    main()
