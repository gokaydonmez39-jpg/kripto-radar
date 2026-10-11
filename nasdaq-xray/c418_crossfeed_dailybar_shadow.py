#!/usr/bin/env python3
"""Provider-neutral same-Nasdaq-session daily OHLCV crosscheck.

Research-only: no HTTP, vendor output, DV30/MC/HISTORY approval or R92. It
detects incompatible daily timestamp conventions and distinguishes matching
prices from unverified volume/trade-condition semantics. Numerical agreement
is not independent feed licensing, corporate-action or PIT proof.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import math
import re
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

SCHEMA="XRAY_C418_DAILY_CROSSFEED_SHADOW_V1"
NY=ZoneInfo("America/New_York")
TICKER=re.compile(r"^[A-Z][A-Z0-9.\\-]{0,11}$")
FIELDS=("open","high","low","close","volume")

def require(ok, code):
    if not ok: raise ValueError("C418_CROSSFEED_BLOCKED:"+code)

def clock(raw):
    require(isinstance(raw,str), "TIMESTAMP_NOT_STRING")
    try:
        x=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except (ValueError,OverflowError) as exc:
        raise ValueError("C418_CROSSFEED_BLOCKED:TIMESTAMP_INVALID") from exc
    require(x.tzinfo is not None and x.utcoffset() is not None,"TIMESTAMP_NAIVE")
    return x.astimezone(dt.timezone.utc)

def session_date(timestamp, convention):
    t=clock(timestamp)
    if convention=="ALPACA_DAILY_DATE_START":
        n=t.astimezone(NY)
        require(n.hour==0 and n.minute==0 and n.second==0 and n.microsecond==0,
                "ALPACA_NOT_EXACT_EASTERN_MIDNIGHT")
        return n.date().isoformat()
    require(convention=="MASSIVE_GROUPED_WINDOW_CLOSE","UNKNOWN_TIME_CONVENTION")
    # A grouped daily window close must match exact official NASDAQ session
    # closing minute, accounting for the half-day calendar and DST.
    import pandas_market_calendars as mcal
    d=t.astimezone(NY).date().isoformat()
    s=mcal.get_calendar("NASDAQ").schedule(start_date=d,end_date=d)
    require(len(s)==1,"NOT_OFFICIAL_NASDAQ_SESSION")
    official=s.iloc[0]["market_close"].to_pydatetime().astimezone(dt.timezone.utc)
    require(t==official,"MASSIVE_CLOSE_NOT_OFFICIAL_RTH_CUTOFF")
    return d

def positive_number(raw):
    require(type(raw) in (int,float,str,Decimal),"NUMBER_TYPE")
    try: value=Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("C418_CROSSFEED_BLOCKED:NUMBER_INVALID") from exc
    require(value.is_finite() and value>0,"NUMBER_NOT_POSITIVE_FINITE")
    return value

def parse(row, expected, convention):
    require(isinstance(row,dict),"BAR_NOT_OBJECT")
    require(row.get("symbol")==expected,"SYMBOL_IDENTITY_MISMATCH")
    d=session_date(row.get("timestamp"),convention)
    nums={k:positive_number(row.get(k)) for k in FIELDS}
    require(nums["high"]>=max(nums["open"],nums["low"],nums["close"])
            and nums["low"]<=min(nums["open"],nums["close"]),
            "BAD_HIGH_LOW_RANGE")
    return d,nums

def check(symbol,asof,alpaca,massive):
    require(isinstance(symbol,str) and bool(TICKER.fullmatch(symbol)),
            "TICKER_INVALID")
    require(isinstance(asof,str) and len(asof)==10,"ASOF_INVALID")
    try:
        parsed=dt.date.fromisoformat(asof)
    except ValueError as exc:
        raise ValueError("C418_CROSSFEED_BLOCKED:ASOF_INVALID") from exc
    require(parsed.isoformat()==asof,"ASOF_INVALID")
    day_a,bar_a=parse(alpaca,symbol,"ALPACA_DAILY_DATE_START")
    day_b,bar_b=parse(massive,symbol,"MASSIVE_GROUPED_WINDOW_CLOSE")
    require(day_a==day_b==asof,"MIXED_ASOF_SESSIONS")
    price_fields_equal=all(bar_a[k]==bar_b[k] for k in FIELDS if k!="volume")
    volume_equal=bar_a["volume"]==bar_b["volume"]
    return {
        "schema":SCHEMA,"symbol":symbol,"asof_et":asof,
        "price_fields_equal":price_fields_equal,
        "volume_fields_equal":volume_equal,
        "volume_semantics_independently_attested":False,
        "status":("OHLC_EQUAL_VOLUME_SEMANTICS_UNVERIFIED" if price_fields_equal
                  else "OHLC_MISMATCH_RESEARCH_BLOCKED"),
        "can_create_PRICE_DV30_PASS":False,
        "can_create_HISTORY_PASS":False,
        "can_create_PRIMARY_MC":False,"can_register_R92":False,
        "production_authority":False,"execution":"NONE",
        "real_money":"NO-GO",
        "vendor_raw_prices_exported":False,
    }

def example():
    return (
        {"symbol":"AAPL","timestamp":"2026-10-09T04:00:00+00:00",
         "open":"331.695","high":"338.61","low":"330.70","close":"336.64","volume":38038338},
        {"symbol":"AAPL","timestamp":"2026-10-09T20:00:00+00:00",
         "open":"331.695","high":"338.61","low":"330.70","close":"336.64","volume":37881200},
    )

def selftest():
    a,b=example()
    output=check("AAPL","2026-10-09",a,b)
    require(output["status"]=="OHLC_EQUAL_VOLUME_SEMANTICS_UNVERIFIED"
            and not output["volume_fields_equal"]
            and not output["can_create_PRICE_DV30_PASS"],"PRICE_EQUAL_VOLUME_UNPROVEN_POSITIVE")
    same=copy.deepcopy(b);same["volume"]=a["volume"]
    require(check("AAPL","2026-10-09",a,same)["volume_fields_equal"],
            "SAME_VOLUME_POSITIVE")
    # US post-Thanksgiving 2026 is an official 13:00 Eastern close.
    winter_a=copy.deepcopy(a);winter_b=copy.deepcopy(b)
    winter_a["timestamp"]="2026-11-27T05:00:00+00:00"
    winter_b["timestamp"]="2026-11-27T18:00:00+00:00"
    require(check("AAPL","2026-11-27",winter_a,winter_b)["price_fields_equal"],
            "OFFICIAL_EARLY_CLOSE_POSITIVE")
    def reject(name,aa,bb,asof="2026-10-09"):
        try:check("AAPL",asof,aa,bb)
        except ValueError:return
        raise AssertionError("C418_CROSSFEED_NEGATIVE_BYPASS:"+name)
    wrong=copy.deepcopy(b);wrong["timestamp"]="2026-10-09T19:00:00+00:00"
    reject("MASSIVE_WRONG_CUTOFF",a,wrong)
    wrong=copy.deepcopy(a);wrong["timestamp"]="2026-10-09T20:00:00+00:00"
    reject("ALPACA_WRONG_START",wrong,b)
    wrong=copy.deepcopy(a);wrong["symbol"]="PLTR"
    reject("IDENTITY_COLLISION",wrong,b)
    wrong=copy.deepcopy(b);wrong["close"]=0
    reject("ZERO_CLOSE",a,wrong)
    wrong=copy.deepcopy(b);wrong["volume"]=float("nan")
    reject("NAN_VOLUME",a,wrong)
    wrong=copy.deepcopy(b);wrong["high"]=10
    reject("BAD_BAR_RANGE",a,wrong)
    wrong=copy.deepcopy(b);wrong["timestamp"]="2026-10-12T20:00:00+00:00"
    reject("MIXED_SESSION",a,wrong)
    wrong=copy.deepcopy(a);wrong["timestamp"]="2026-10-09T04:00:00"
    reject("NAIVE_TIME",wrong,b)
    reject("NOT_A_TRADING_SESSION",a,b,"2026-10-10")
    wrong=copy.deepcopy(b);wrong["timestamp"]="2026-11-27T21:00:00+00:00"
    reject("EARLY_CLOSE_WRONG_FULL_DAY",winter_a,wrong,"2026-11-27")
    print("XRAY_C418_DAILY_CROSSFEED_SELFTEST=PASS_3_POSITIVE_10_NEGATIVE_PYTHON_O_SAFE_NO_AUTHORITY")

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--selftest",action="store_true")
    args=cli.parse_args()
    if args.selftest:selftest()
    else:cli.error("Only --selftest is permitted; no raw provider input is stored")
