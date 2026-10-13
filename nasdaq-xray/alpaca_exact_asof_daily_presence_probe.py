#!/usr/bin/env python3
"""One-read, four-symbol historical SIP completed-day presence witness.

Isolates stale Sina current-day coverage from personal historical Alpaca SIP.
One exact day only; never creates C4.17 PRICE/DV30, PRIMARY MC, HISTORY,
R92, or any execution authority. No vendor OHLCV is persisted.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from alpaca_sip_exact30_backup_probe import personal_shadow_access
from alpaca_sip_30min_rth_lower_bound_pilot import stamp,data_check

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
SYMBOLS=("AAPL","AMZN","MSFT","NVDA")
SCHEMA="XRAY_ALPACA_EXACT_ASOF_4SYM_DAILY_PRESENCE_SHADOW_V1"
NY=ZoneInfo("America/New_York")
MAX_BYTES=120000
BASE="https://data.alpaca.markets/v2/stocks/bars"

def need(predicate,reason):
    if not predicate:
        raise ValueError("XRAY_DAILY_PRESENCE_"+reason)

def check_scope():
    import pandas_market_calendars as mcal
    days=[x.date().isoformat() for x in
          mcal.get_calendar("NASDAQ").valid_days(
             start_date=ASOF,end_date=ASOF)]
    need(days==[ASOF],"NOT_OFFICIAL_SESSION")
    now=dt.datetime.now(dt.timezone.utc)
    closing=dt.datetime.fromisoformat(ASOF+"T16:20:00").replace(tzinfo=NY)
    need(now>=closing.astimezone(dt.timezone.utc),"MARKET_NOT_CLOSED_PLUS_DELAY")
    state=json.loads((ROOT/"sina_state.json").read_text())
    need(state.get("asof_et")==ASOF and
         state.get("status")=="HISTORY_PARTIAL" and
         state.get("unknown_count",0)>0,"NOT_ROOT_PARTIAL_SAME_ASOF")
    need(personal_shadow_access(os.environ),"PERSONAL_SHADOW_ENTITLEMENT")

def classify(bars):
    need(type(bars) is dict and set(bars).issubset(SYMBOLS),"UNLISTED_SYMBOL")
    result={}
    for symbol in SYMBOLS:
        rows=bars.get(symbol,[])
        if type(rows) is not list or len(rows)!=1:
            result[symbol]="UNKNOWN_ABSENT_OR_DUPLICATE"
            continue
        try:
            bar=rows[0]
            t=stamp(bar).astimezone(NY).date().isoformat()
            volume=data_check(bar)
            if t!=ASOF or volume<=0:
                result[symbol]="UNKNOWN_WRONG_DAY_OR_VOLUME"
            else:
                result[symbol]="OBSERVED_EXACT_ASOF_SIP_DAILY_SHADOW"
        except (ValueError,TypeError,KeyError,OverflowError):
            result[symbol]="UNKNOWN_INVALID_BAR"
    return result

def metadata(statuses,call_count,status):
    good=sum(s=="OBSERVED_EXACT_ASOF_SIP_DAILY_SHADOW" for s in statuses.values())
    return {"schema":SCHEMA,"asof_et":ASOF,"symbols_requested":list(SYMBOLS),
            "counts":{"observed_exact_asof":good,"unknown":len(SYMBOLS)-good},
            "statuses":statuses,"api_calls":call_count,
            "status":status,"feed":"sip","timeframe":"1Day",
            "scope":"PERSONAL_HISTORICAL_SIP_ONE_DAY_4_SYMBOLS",
            "provider_daily_volume_proves_rth_volume":False,
            "official_close_settlement_verified":False,
            "rights_automated_non_display_verified":False,
            "primary_dv30_created":False,"primary_mc_created":False,
            "history_260_52_created":False,"r92_created":False,
            "raw_ohlcv_persisted":False,"unknown_never_pass":True,
            "execution":"NONE","real_money":"NO-GO"}

def selftest():
    valid={"t":"2026-10-13T04:00:00Z","o":10,"h":11,"l":9,"c":10,"v":1000}
    positive=classify({s:[dict(valid)] for s in SYMBOLS})
    need(all(z=="OBSERVED_EXACT_ASOF_SIP_DAILY_SHADOW" for z in positive.values()),
         "POSITIVE")
    missing=classify({"AAPL":[dict(valid)]})
    need(missing["AAPL"]=="OBSERVED_EXACT_ASOF_SIP_DAILY_SHADOW"
         and missing["MSFT"]=="UNKNOWN_ABSENT_OR_DUPLICATE","MISSING")
    wrong=classify({"AAPL":[dict(valid,t="2026-10-12T04:00:00Z")]})
    need(wrong["AAPL"]=="UNKNOWN_WRONG_DAY_OR_VOLUME","WRONG_ASOF")
    invalid=classify({"AAPL":[dict(valid,v=False)]})
    need(invalid["AAPL"]=="UNKNOWN_INVALID_BAR","BOOL_VOLUME")
    duplicate=classify({"AAPL":[dict(valid),dict(valid)]})
    need(duplicate["AAPL"]=="UNKNOWN_ABSENT_OR_DUPLICATE","DUPLICATE")
    try:classify({"UNKNOWN":[dict(valid)]})
    except ValueError:pass
    else:raise AssertionError("FOREIGN_SYMBOL_ACCEPTED")
    x=metadata(positive,1,"OBSERVED_SIP_DAILY_ONLY")
    need(x["counts"]["observed_exact_asof"]==4
         and x["primary_dv30_created"] is False
         and x["r92_created"] is False,"NO_ALPHA")
    print("XRAY_DAILY_ASOF_PRESENCE_SELFTEST=PASS_5_NEGATIVES_ONE_POSITIVE_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--one-shot-20261013",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        need(not args.one_shot_20261013 and args.out is None,"SELFTEST_ARGS")
        selftest()
        return
    need(args.one_shot_20261013 and args.out is not None,"EXPLICIT_ONE_SHOT")
    need(not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "NO_REPOSITORY_DATA_ARTIFACT")
    check_scope()
    creds=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
           os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
            os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    need(bool(creds and secret),"MISSING_API_KEYS")
    params={"symbols":",".join(SYMBOLS),"timeframe":"1Day",
            "feed":"sip","adjustment":"raw","sort":"asc","limit":"1000",
            "start":"2026-10-13T00:00:00-04:00",
            "end":"2026-10-13T23:59:59-04:00"}
    req=urllib.request.Request(BASE+"?"+urllib.parse.urlencode(params),
          headers={"APCA-API-KEY-ID":creds,"APCA-API-SECRET-KEY":secret,
                   "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=25) as response:
        raw=response.read(MAX_BYTES+1)
    need(len(raw)<=MAX_BYTES,"RESPONSE_OVERSIZE")
    data=json.loads(raw)
    need(type(data) is dict and type(data.get("bars")) is dict,
         "RESPONSE_SCHEMA")
    if data.get("next_page_token"):
        result=metadata({s:"UNKNOWN_PAGINATION" for s in SYMBOLS},1,
                        "BLOCKED_PAGINATION_ONE_PAGE_ONLY")
    else:
        statuses=classify(data["bars"])
        result=metadata(statuses,1,"RESEARCH_METADATA_ONLY")
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_DAILY_ASOF_PRESENCE="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_DAILY_ASOF_NO_DV30_MC_R92=PASS")

if __name__=="__main__":main()
