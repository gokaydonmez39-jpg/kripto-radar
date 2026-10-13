#!/usr/bin/env python3
"""Bounded single-session historical SIP minute RTH research probe.

One ticker / one official Nasdaq session / <=1 vendor request; never constructs
DV30. A valid 1Day bar does not attest exclusively regular-session volume.
This probe inspects a precise 09:30..close-1minute window, and explicitly
withholds auction/trade-condition and data-licensing production authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from alpaca_sip_exact30_backup_probe import PRICE, MASTER, expected_sessions, grant
from alpaca_rth_minute_integrity_shadow import official_window, inspect_minutes

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_ALPACA_SIP_RTH_MINUTE_ONECALL_SHADOW_V1"
SYMBOL="AAPL"
HOST="https://data.alpaca.markets/v2/stocks/AAPL/bars"
MAX_BYTES=140000
MAX_BARS=500

def params(asof):
    start,close,n=official_window(asof)
    # Alpaca 'end' is inclusive. Exclude the 16:00 bar: may mix official
    # auction executions and after-hours transactions.
    end=close-dt.timedelta(minutes=1)
    if start>=close or n<=0 or (close-start)!=dt.timedelta(minutes=n):
        raise ValueError("INVALID_OFFICIAL_SESSION_WINDOW")
    def fmt(x):
        return x.isoformat().replace("+00:00","Z")
    return {"start":fmt(start),"end":fmt(end),"timeframe":"1Min",
            "feed":"sip","adjustment":"raw","sort":"asc",
            "limit":str(MAX_BARS),"asof":asof}

def vendor_get(creds, asof):
    key,secret=creds
    query=urllib.parse.urlencode(params(asof))
    req=urllib.request.Request(HOST+"?"+query,headers={
        "APCA-API-KEY-ID":key, "APCA-API-SECRET-KEY":secret,
        "Accept":"application/json","User-Agent":"XRAY-Research-NoOrders/1.0"})
    with urllib.request.urlopen(req,timeout=20) as resp:
        body=resp.read(MAX_BYTES+1)
    if len(body)>MAX_BYTES:
        raise ValueError("VENDOR_RESPONSE_OVERSIZED")
    return json.loads(body)

def verify_vendor(doc, asof):
    if (type(doc) is not dict or doc.get("symbol")!=SYMBOL or
        not isinstance(doc.get("bars"),list) or
        doc.get("next_page_token")):
        raise ValueError("SYMBOL_SCHEMA_OR_PAGINATION")
    rows=doc["bars"]
    observed=len(rows)
    report=inspect_minutes(asof,rows)
    if not report["continuous_minute_window_exact"]:
        raise ValueError("NONCONTIGUOUS_RTH_WINDOW")
    return observed

def base(asof):
    return {"schema":SCHEMA,"asof_et":asof,"policy":"C4.17",
        "control":"C4.27","status":"BLOCKED_UNVERIFIED_INPUT",
        "ticker":SYMBOL,"feed":"sip","timeframe":"1Min",
        "requested_completed_official_sessions":1,
        "expected_official_session_minutes":0,
        "observed_valid_minutes":0,"api_calls":0,
        "runner_credentials_present":False,
        "operator_license_claimed":False,"license_independently_verified":False,
        "exact_minute_window_observed":False,"close_auction_allocation_verified":False,
        "trade_conditions_rth_lineage_verified":False,
        "daily_bar_volume_is_rth_proven":False,
        "historical_pit_revision_chain_verified":False,
        "full_540_symbol_coverage":False,"coverage_complete":False,
        "market_volume_persisted":False,"raw_ohlcv_persisted":False,
        "api_key_or_url_persisted":False,
        "primary_price_authority":False,"primary_mc_authority":False,
        "dv30_pass_created":False,"history_pass_created":False,
        "r92_created":False,"alpha_authority":False,
        "strict_g9_pass":False,"account_pass":False,"execution":"NONE",
        "real_money":"NO-GO","unknown_never_pass":True}

def run(price,master,latest,env,fetcher=vendor_get):
    result=base(price.get("asof_et"))
    try:
        dates=expected_sessions(price,master,latest)
        if dates[-1]!=latest:
            raise ValueError("INVALID_ASOF")
        _,_,n=official_window(latest)
        result["expected_official_session_minutes"]=n
    except Exception:
        result["status"]="BLOCKED_STALE_OR_INVALID_PRICE_SCOPE"
        return result
    key=env.get("XRAY_ALPACA_API_KEY_ID","").strip()
    secret=env.get("XRAY_ALPACA_API_SECRET_KEY","").strip()
    result["runner_credentials_present"]=bool(key and secret)
    result["operator_license_claimed"]=grant(env)
    if not key or not secret:
        result["status"]="BLOCKED_RUNNER_CREDENTIALS_NOT_CONFIGURED"
        return result
    if not grant(env):
        result["status"]="BLOCKED_UNATTESTED_UNATTENDED_RESEARCH_RIGHTS"
        return result
    result["api_calls"]=1
    try:
        doc=fetcher((key,secret),latest)
        n=verify_vendor(doc,latest)
        result["observed_valid_minutes"]=n
        result["exact_minute_window_observed"]=True
        result["status"]="SHADOW_EXACT_RTH_MINUTE_WINDOW_NO_AUCTION_NO_DV30_AUTHORITY"
    except urllib.error.HTTPError as exc:
        result["status"]=("BLOCKED_HTTP_401_403" if exc.code in (401,403)
                           else "BLOCKED_HTTP_429" if exc.code==429
                           else "BLOCKED_VENDOR_HTTP")
    except (urllib.error.URLError,OSError,TimeoutError):
        result["status"]="BLOCKED_VENDOR_TRANSPORT"
    except Exception:
        result["status"]="BLOCKED_VENDOR_SCHEMA_OR_RTH_WINDOW_INCOMPLETE"
    return result

def selftest():
    from copy import deepcopy
    import pandas_market_calendars as mcal
    days=[d.date().isoformat() for d in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date="2026-10-12")]
    if len(days)!=30:
        raise AssertionError("WRONG_OFFICIAL_30_FIXTURE")
    asof=days[-1]
    src={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
         "unknown_never_pass":True,"expected30":days,"pass_symbols":[],
         "pass_count":0,"unknown_symbols":["AAPL","AAL","AAON","AAOI","NVDA"],
         "unknown_count":5}
    master={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"pass_symbols":["AAPL","AAL","AAON","AAOI","NVDA"],
            "pass_count":5}
    start,close,count=official_window(asof)
    def fixture():
        return {"symbol":SYMBOL,"bars":[
            {"t":(start+dt.timedelta(minutes=i)).isoformat().replace("+00:00","Z"),
             "v":1000} for i in range(count)],"next_page_token":None}
    from unittest.mock import patch
    # This guard must still reject malformed calendars with python -O.
    for broken in ((close,start,count),(start,start,0),(start,close,count-1)):
        with patch(__name__+".official_window",return_value=broken):
            try:params(asof)
            except ValueError:pass
            else:raise AssertionError("INVALID_OFFICIAL_SESSION_WINDOW_ACCEPTED")
    p=params(asof)
    if (p["feed"]!="sip" or p["timeframe"]!="1Min" or
        p["adjustment"]!="raw" or p["limit"]!="500" or
        p["start"]!=start.isoformat().replace("+00:00","Z") or
        p["end"]!=(close-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z")):
        raise AssertionError("EXCLUSIVE_AUCTION_REQUEST_PARAMETERS")
    if verify_vendor(fixture(),asof)!=390:
        raise AssertionError("VALID_SESSION_WINDOW_REJECTED")
    tests=[
        lambda o:o.update(symbol="MSFT"),
        lambda o:o.update(next_page_token="MORE"),
        lambda o:o["bars"].pop(),
        lambda o:o["bars"][0].update(v=1000.125),
        lambda o:o["bars"][0].update(v=0),
        lambda o:o["bars"][0].update(t=o["bars"][1]["t"]),
        lambda o:o["bars"][-1].update(t=close.isoformat().replace("+00:00","Z")),
        lambda o:o["bars"].reverse(),
    ]
    for mutate in tests:
        x=deepcopy(fixture());mutate(x)
        try:verify_vendor(x,asof)
        except (ValueError,TypeError):pass
        else:raise AssertionError("UNSAFE_RTH_VENDOR_PAYLOAD_ACCEPTED")
    calls=[]
    def fake(creds,day):
        calls.append(day)
        return fixture()
    empty=run(src,master,asof,{},fake)
    if empty["api_calls"]!=0 or calls:
        raise AssertionError("UNAUTHORIZED_NETWORK_CALL")
    env={"XRAY_ALPACA_API_KEY_ID":"TEST_ID","XRAY_ALPACA_API_SECRET_KEY":"TEST_SECRET"}
    blocked=run(src,master,asof,env,fake)
    if blocked["api_calls"]!=0 or blocked["status"]!="BLOCKED_UNATTESTED_UNATTENDED_RESEARCH_RIGHTS":
        raise AssertionError("UNATTESTED_REQUEST_ALLOWED")
    env["XRAY_ALPACA_SIP_HISTORY_RESEARCH_LICENSE_OK"]="true"
    env["XRAY_ALPACA_SIP_HISTORY_LICENSE_EVIDENCE_SHA256"]="a"*64
    yes=run(src,master,asof,env,fake)
    if (yes["api_calls"]!=1 or len(calls)!=1 or yes["observed_valid_minutes"]!=390 or
        not yes["exact_minute_window_observed"] or
        yes["status"]!="SHADOW_EXACT_RTH_MINUTE_WINDOW_NO_AUCTION_NO_DV30_AUTHORITY"):
        raise AssertionError("VALID_AUTHORIZED_MOCK_SHADOW_FAILED")
    for label in ("license_independently_verified","close_auction_allocation_verified",
                  "trade_conditions_rth_lineage_verified","daily_bar_volume_is_rth_proven",
                  "dv30_pass_created","primary_price_authority","primary_mc_authority",
                  "r92_created","history_pass_created","alpha_authority"):
        if yes[label] is not False:
            raise AssertionError("INAPPROPRIATE_PRIMARY_ALPHA_RELEASE_"+label)
    bad=run(src,master,"2026-10-09",env,fake)
    if bad["api_calls"]!=0 or len(calls)!=1:
        raise AssertionError("STALE_DATE_REUSED")
    if any(x in json.dumps(yes) for x in ("TEST_SECRET","TEST_ID","390000")):
        raise AssertionError("SECRET_OR_VENDOR_VOLUME_PERSISTED")
    print("XRAY_SIP_RTH_ONECALL_SELFTEST=PASS_390_FULL_8_NEGATIVES_ZERO_UNLICENSED_REQUESTS_NO_DV30")
    print("XRAY_SIP_RTH_WINDOW_OPTIMIZED_NEGATIVES=PASS_3")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.out is None or a.out.resolve().is_relative_to(REPO.resolve()):
        p.error("--out must be private outside repository")
    from source_epoch_freshness_guard import last_complete_session
    try:
        latest=last_complete_session(dt.datetime.now(dt.timezone.utc))
        src=json.loads(PRICE.read_text())
        master=json.loads(MASTER.read_text())
        result=run(src,master,latest,os.environ)
    except Exception:
        result=base(None)
        result["status"]="BLOCKED_SOURCE_OR_EXCHANGE_CALENDAR_UNVERIFIED"
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_SIP_RTH_MINUTE_ONECALL="+result["status"])
    print("XRAY_SIP_RTH_MINUTE_REQUEST_COUNT="+str(result["api_calls"]))
    print("XRAY_SIP_RTH_MINUTE_NO_PRIMARY_R92_G9_ACCOUNT=PASS")

if __name__=="__main__":
    main()
