#!/usr/bin/env python3
"""Free delayed SIP independent price/HISTORY feasibility; SHADOW ONLY.

No C4.17 gate writes, no vendor bars or price/volume persisted in public GitHub.
Historical SIP is only queried after the 15-minute holdback and with a read-only
authenticated data endpoint. The external Alpaca key must stay in Actions Secrets.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parent
EST=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
SCHEMA="XRAY_ALPACA_FREE_SIP_SHADOW_GUARD_V1"
BASE="https://data.alpaca.markets/v2/stocks/bars"
SAMPLE=("AAPL","MSFT","NVDA","AMZN","GOOGL","META","ADBE","ADI")
GUARD_DELAY=dt.timedelta(minutes=20)  # strictly above provider's 15-minute holdback

def blob_sha(path:pathlib.Path)->str:
    raw=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def parse_date(s):
    return dt.date.fromisoformat(s)

def timestamp_date(s):
    if not isinstance(s,str):
        raise ValueError("BAR_TIMESTAMP_INVALID")
    t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("BAR_TIMESTAMP_NAIVE")
    return t.astimezone(EST).date()

def sufficient_delay(asof:str,now:dt.datetime)->bool:
    if now.tzinfo is None:
        raise ValueError("NOW_UNZONED")
    day=parse_date(asof)
    period_end=dt.datetime.combine(day+dt.timedelta(days=1),dt.time(0,0),EST)
    return now.astimezone(UTC)>=period_end.astimezone(UTC)+GUARD_DELAY

def evaluate_daily(symbol_rows:list,expected30:list[str],asof:str,now:dt.datetime) -> tuple[str,str,int]:
    if not sufficient_delay(asof,now):
        return "UNKNOWN","HISTORICAL_SIP_HOLDBACK_NOT_EXPIRED",0
    if len(expected30)!=30 or len(set(expected30))!=30 or expected30!=sorted(expected30):
        return "UNKNOWN","OFFICIAL_30_SESSION_LIST_UNVERIFIED",0
    if expected30[-1]!=asof:
        return "UNKNOWN","ASOF_LAST_SESSION_NOT_EXACT",0
    if not isinstance(symbol_rows,list):
        return "UNKNOWN","PROVIDER_ROWS_NOT_LIST",0
    observed={}
    for row in symbol_rows:
        if not isinstance(row,dict):
            return "UNKNOWN","PROVIDER_ROW_NOT_OBJECT",0
        try:
            d=timestamp_date(row["t"])
            vals=[row[k] for k in ("o","h","l","c","v")]
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in vals):
                return "UNKNOWN","OHLCV_NOT_NUMERIC",0
            if any(not math.isfinite(v) for v in vals):
                return "UNKNOWN","OHLCV_NOT_FINITE",0
            o,h,l,c,v=vals
            if not (0<o<=h and 0<l<=h and 0<c<=h and l<=o and l<=c and v>=0):
                return "UNKNOWN","OHLCV_INVALID",0
        except (KeyError,ValueError,TypeError,OverflowError):
            return "UNKNOWN","OHLCV_OR_DATE_PARSE_ERROR",0
        if d>parse_date(asof):
            return "UNKNOWN","FUTURE_BAR_LEAK",0
        if d in observed:
            return "UNKNOWN","DUPLICATE_SESSION",0
        observed[d]=row
    dates=[parse_date(d) for d in expected30]
    missing=[d for d in dates if d not in observed]
    if missing:
        return "UNKNOWN","MISSING_30_COMPLETED_SESSIONS",len(dates)-len(missing)
    if any(observed[d]["v"]==0 for d in dates):
        return "UNKNOWN","ZERO_VOLUME_SESSION_NOT_COMPLETE",30
    # 260+ rows are evidence of apparent availability, not a verified
    # 260-session official holiday calendar nor 52-week corporate adjustment.
    return "SHADOW_30_BARS_OBSERVED","RTH_AND_SPLIT_ADJUSTMENT_NOT_PRIMARY_ATTESTED",30

def load_scope():
    master_path=ROOT/"canonical_current_master_manifest.json"
    price_path=ROOT/"canonical_current_price_dv30.json"
    m=json.loads(master_path.read_text(encoding="utf-8"))
    p=json.loads(price_path.read_text(encoding="utf-8"))
    if (m.get("asof_et")!=p.get("asof_et") or not p.get("asof_et")
       or p.get("unknown_never_pass") is not True
       or m.get("unknown_never_pass") is not True):
        raise ValueError("EXACT_ASOF_SAFETY_SCOPE_INVALID")
    master_set=set(m.get("pass_symbols") or [])
    price_set=set(p.get("pass_symbols") or [])
    if not price_set.issubset(master_set) or len(price_set)!=int(p.get("pass_count",-1)):
        raise ValueError("UNIVERSE_PRICE_SET_MISMATCH")
    symbols=[x for x in SAMPLE if x in price_set]
    if len(symbols)<3:
        raise ValueError("NO_REPRESENTATIVE_CURRENT_PRICE_SCOPE")
    dates=p.get("expected30") or []
    if len(dates)!=30 or len(set(dates))!=30 or dates[-1]!=p["asof_et"]:
        raise ValueError("UNVERIFIED_EXPECTED_30_SESSIONS")
    return m,p,symbols,dates,blob_sha(master_path),blob_sha(price_path)

def request_batch(symbols,start,period_end,key,secret):
    query=urllib.parse.urlencode({
        "symbols":",".join(symbols),"start":start,"end":period_end,
        "timeframe":"1Day","feed":"sip","adjustment":"raw","limit":10000})
    if not key or not secret:
        raise RuntimeError("ALPACA_SECRETS_MISSING")
    req=urllib.request.Request(BASE+"?"+query,headers={
        "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
        "Accept":"application/json","User-Agent":"NASDAQ-XRAY-Research/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=25) as reply:
            if reply.status!=200:raise RuntimeError("ALPACA_HTTP_NON200")
            raw=reply.read(3_000_001)
            if len(raw)>3_000_000:raise RuntimeError("ALPACA_RESPONSE_TOO_LARGE")
    except urllib.error.HTTPError as exc:
        # Account/auth/rate/entitlement errors are diagnostics, never synthetic
        # fallback price data. Do not surface credentials in logs.
        raise RuntimeError("ALPACA_HTTP_"+str(exc.code)) from exc
    except (TimeoutError,urllib.error.URLError) as exc:
        raise RuntimeError("ALPACA_NETWORK_UNAVAILABLE") from exc
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get("bars"),dict):
        raise RuntimeError("ALPACA_RESPONSE_SCHEMA_INVALID")
    if data.get("next_page_token"):
        # Reject partial paginated windows; a later complete parser must
        # explicitly iterate bounded tokens with same exact scope SHA.
        raise RuntimeError("ALPACA_PAGE_INCOMPLETE_FAIL_CLOSED")
    return data["bars"]

def run(now=None):
    if now is None:now=dt.datetime.now(UTC)
    m,p,symbols,expected30,msha,psha=load_scope()
    asof=p["asof_et"]
    output={
        "schema":SCHEMA,"asof_et":asof,"policy":"C4.17",
        "mode":"RESEARCH_ONLY_MANUAL_DECISION","execution":"NONE",
        "real_money":"NO-GO","unknown_never_pass":True,
        "master_git_blob_sha":msha,"price_git_blob_sha":psha,
        "sample_count":len(symbols),"feed":"SIP_DELAYED_HISTORICAL",
        "price_adjustment":"RAW_NOT_CORP_ACTION_RECONCILED",
        "primary_mc_authority":False,"c417_price_pass_promoted":False,
        "candidate_created":False,"device_receipt_proven":False,
        "vendor_raw_bars_persisted":False,"reason_counts":{},"status":"BLOCKED",
    }
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID","")
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY","")
    if not key or not secret:
        output["reason_counts"]={"ALPACA_PRIVATE_API_CREDENTIALS_REQUIRED":len(symbols)}
        return output
    if not sufficient_delay(asof,now):
        output["reason_counts"]={"HISTORICAL_SIP_HOLDBACK_NOT_EXPIRED":len(symbols)}
        return output
    start=dt.datetime.combine(parse_date(asof)-dt.timedelta(days=440),dt.time(0,0),EST).astimezone(UTC).isoformat()
    end=dt.datetime.combine(parse_date(asof)+dt.timedelta(days=1),dt.time(0,0),EST).astimezone(UTC).isoformat()
    try:res=request_batch(symbols,start,end,key,secret)
    except (RuntimeError,ValueError) as exc:
        why=str(exc)
        output["reason_counts"]={why if why.startswith("ALPACA_") else "ALPACA_UNEXPECTED_RESPONSE":len(symbols)}
        return output
    statuses=[]
    for symbol in symbols:
        status,reason,covered=evaluate_daily(res.get(symbol,[]),expected30,asof,now)
        statuses.append(status+"|"+reason)
    output["reason_counts"]=dict(sorted(Counter(statuses).items()))
    output["status"]="SHADOW_MEASUREMENT_COMPLETED_NO_PRIMARY_AUTHORITY"
    return output

def selftest():
    dates=["2026-09-%02d"%x for x in range(1,29)]+["2026-10-07","2026-10-08"]
    now=dt.datetime(2026,10,9,14,tzinfo=UTC)
    assert sufficient_delay("2026-10-08",now) is True
    assert sufficient_delay("2026-10-08",dt.datetime(2026,10,9,4,5,tzinfo=UTC)) is False
    def bar(day,vol=10000):
        t=dt.datetime.combine(parse_date(day),dt.time(0,0),EST).astimezone(UTC).isoformat()
        return {"t":t,"o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":vol}
    sample=[bar(x) for x in dates]
    assert evaluate_daily(sample,dates,"2026-10-08",now)[0]=="SHADOW_30_BARS_OBSERVED"
    assert evaluate_daily(sample[:-1],dates,"2026-10-08",now)[1]=="MISSING_30_COMPLETED_SESSIONS"
    assert evaluate_daily(sample+[sample[-1]],dates,"2026-10-08",now)[1]=="DUPLICATE_SESSION"
    assert evaluate_daily(sample+[bar("2026-10-09")],dates,"2026-10-08",now)[1]=="FUTURE_BAR_LEAK"
    assert evaluate_daily(sample[:-1]+[bar(dates[-1],vol=0)],dates,"2026-10-08",now)[1]=="ZERO_VOLUME_SESSION_NOT_COMPLETE"
    assert evaluate_daily(sample,dates[:-1], "2026-10-08",now)[1]=="OFFICIAL_30_SESSION_LIST_UNVERIFIED"
    from copy import deepcopy
    corrupted=deepcopy(sample);corrupted[-1]["c"]=float("nan")
    assert evaluate_daily(corrupted,dates,"2026-10-08",now)[1]=="OHLCV_NOT_FINITE"
    for field,bad_value in (("o",float("inf")),("h",float("inf")),
                            ("l",float("-inf")),("c",float("nan")),
                            ("v",float("inf"))):
        corrupted=deepcopy(sample)
        corrupted[0][field]=bad_value
        assert evaluate_daily(corrupted,dates,"2026-10-08",now)[1]=="OHLCV_NOT_FINITE",field
    corrupted=deepcopy(sample)
    corrupted[0]["t"]="2026-09-01T00:00:00"
    assert evaluate_daily(corrupted,dates,"2026-10-08",now)[1]=="OHLCV_OR_DATE_PARSE_ERROR"
    corrupted=deepcopy(sample);corrupted[-1]["c"]=True
    assert evaluate_daily(corrupted,dates,"2026-10-08",now)[1]=="OHLCV_NOT_NUMERIC"
    print("XRAY_ALPACA_FREE_SIP_SHADOW_SELFTEST=PASS_HOLDBACK_30_SESSIONS_DUPLICATE_GAPS_ZERO_VOL_FUTURE")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    if args.selftest:selftest()
    else:
        obj=run()
        if args.output:args.output.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print("XRAY_ALPACA_FREE_SIP_SOURCE="+obj["status"])
        print("XRAY_ALPACA_FREE_SIP_REASONS="+json.dumps(obj["reason_counts"],sort_keys=True))
        print("XRAY_ALPACA_C417_PRIMARY=BLOCKED_UNTIL_EXPLICIT_POLICY_AND_ISSUER_CAP_PROOFS")
