#!/usr/bin/env python3
"""Optional SIP EOD 260d/52w B-precursor monitor. NO AL / no order authority.

Alpaca historical SIP is a read-only research source. Credentials remain in
GitHub Actions secrets. No vendor OHLCV is ever written to an artifact.
Absence of credentials, incomplete cohort, or rights ambiguity is NOT PASS.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import statistics
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_SIP_EOD_260_52_B_RESEARCH_SHADOW_V1"

def require(ok,reason):
    if not ok: raise ValueError("XRAY_SIP_SHADOW_FAIL_CLOSED:"+reason)

def sha_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def symbol_hash(syms):
    return hashlib.sha256("\n".join(syms).encode()).hexdigest()

def mean(xs):
    require(bool(xs) and all(type(x) in (float,int) and math.isfinite(x) for x in xs),
            "INVALID_MEAN_INPUT")
    return sum(xs)/len(xs)

def ema(xs,length):
    require(len(xs)>=length,"EMA_NOT_ENOUGH_WEEKS")
    v=mean(xs[:length])
    for x in xs[length:]:v+=2/(length+1)*(x-v)
    return v

def completed_weeks(bars,asof):
    weeks={}
    for b in bars:
        date=dt.date.fromisoformat(b["date"])
        monday=date-dt.timedelta(days=date.weekday())
        # Do not use a partial current trading week as completed history.
        weeks[monday]=(date,b["close"])
    return [close for _,(date,close) in sorted(weeks.items())
            if date.weekday()==4 and date.isoformat()<=asof]

def validate_bars(symbol,bars,asof):
    require(type(bars) is list and len(bars)>=260,"NOT_260_BARS:"+symbol)
    prev=None
    for x in bars:
        require(type(x) is dict and type(x.get("date")) is str and
                type(x.get("open")) in (float,int) and
                type(x.get("high")) in (float,int) and
                type(x.get("low")) in (float,int) and
                type(x.get("close")) in (float,int) and
                type(x.get("volume")) in (float,int),"BAD_OHLCV:"+symbol)
        date=dt.date.fromisoformat(x["date"])
        require(date.weekday()<5 and (prev is None or date>prev) and
                x["date"]<=asof,"DATE_OR_DUPLICATE:"+symbol)
        prev=date
        o,h,l,c,v=(x[k] for k in ("open","high","low","close","volume"))
        require(all(math.isfinite(k) for k in (o,h,l,c,v)) and
                v>0 and l>0 and l<=min(o,c)<=max(o,c)<=h,
                "BAD_BAR_OR_SYNTHETIC:"+symbol)
    require(bars[-1]["date"]==asof,"ASOF_MISSING:"+symbol)
    require(len(completed_weeks(bars,asof))>=52,"NOT_52_WEEKS:"+symbol)

def aligned_returns(bars,qqq):
    d={x["date"]:x["close"] for x in qqq}
    common=[(x["close"],d[x["date"]]) for x in bars if x["date"] in d]
    require(len(common)>=61 and bars[-1]["date"]==qqq[-1]["date"],
            "QQQ_60_COMMON_SESSIONS")
    def rs(k):
        return common[-1][0]/common[-k-1][0]-common[-1][1]/common[-k-1][1]
    return rs(20),rs(60)

def evaluate_b_precursor(symbol,bars,qqq,asof):
    validate_bars(symbol,bars,asof)
    c=[x["close"] for x in bars];h=[x["high"] for x in bars]
    l=[x["low"] for x in bars];v=[x["volume"] for x in bars]
    tr=[max(x["high"]-x["low"],abs(x["high"]-(c[i-1] if i else c[0])),
            abs(x["low"]-(c[i-1] if i else c[0])))
        for i,x in enumerate(bars)]
    # First 14 completed TRs, frozen through trigger-1; Wilder recurrence.
    atr=mean(tr[1:15])
    for x in tr[15:-1]:atr=(atr*13+x)/14
    require(atr>0,"ZERO_ATR")
    weeks=completed_weeks(bars,asof)
    wkpass=(c[-1]>ema(weeks,10) and c[-1]>mean(weeks[-30:])
            and ema(weeks,10)>ema(weeks[:-4],10))
    rs20,rs60=aligned_returns(bars,qqq)
    rvol=v[-1]/mean(v[-21:-1])
    compression=mean(tr[-6:-1])<=.8*mean(tr[-26:-6])
    trend=c[-1]>mean(c[-50:]) and mean(c[-50:])>mean(c[-70:-20])
    choices=[]
    for k in (5,10,15,20):
        high=max(h[-k-1:-1]);wide=(high-min(l[-k-1:-1]))/atr
        if .30<=wide<=2.05 and c[-1]>high:choices.append((k,high,wide))
    chosen=choices[-1] if choices else None
    basic_pass=bool(chosen and wkpass and trend and rs20>0 and rs60>0
                    and rvol>=1.5 and compression)
    why=[]
    if not chosen:why.append("NO_VALID_NARROW_BREAKOUT")
    if not wkpass:why.append("WEEKLY_TREND_FAIL")
    if not trend:why.append("SMA50_TREND_FAIL")
    if rs20<=0 or rs60<=0:why.append("QQQ_RS20_RS60_FAIL")
    if rvol<1.5:why.append("RVOL_LT_1_5")
    if not compression:why.append("PRIOR_FIVE_BAR_COMPRESSION_FAIL")
    result={"symbol":symbol,"b_precursor":basic_pass,
            "eod_asof":asof,"base_sessions":chosen[0] if chosen else None,
            "reasons":why,"qualified_al":False,
            "market_cap_primary_verified":False,"final_r1_rr_verified":False,
            "official_event_legal_verified":False}
    if basic_pass:
        # This is NOT a final entry. Compute structural-risk diagnostics only.
        pivot=chosen[1];entry=pivot+.25*atr;chase=pivot+.5*atr
        lows=[(i,l[i]) for i in range(2,len(bars)-3)
              if l[i]<min(l[i-2],l[i-1],l[i+1],l[i+2])]
        recent=[x for x in lows if x[1]<pivot]
        # Without an unambiguous confirmed higher-low, no strict risk release.
        if not recent:
            result["reasons"]=["CONFIRMED_HIGHER_LOW_UNAVAILABLE"]
        else:
            anchor=recent[-1][1]
            previous=recent[-2][1] if len(recent)>=2 else None
            if previous is None or not anchor>previous:
                result["reasons"]=["ACTIVE_HIGHER_LOW_NOT_PROVEN"]
            else:
                stop=anchor-.2*atr;rp=(entry-stop)/entry
                result["risk_over_8_percent"]=rp>.08
                result["chase_crossed_on_asof_close"]=c[-1]>=chase
                result["risk_percent_derived"]=round(100*rp,3)
                if rp>.08:result["reasons"].append("C417_RISK_GT_8_PERCENT")
                if c[-1]>=chase:result["reasons"].append("C417_CHASE_NO_VALID_FILL")
                result["reasons"].append("OFFICIAL_R1_RR_AND_NONTECH_GATES_UNVERIFIED")
    return result

def read_canonical():
    def read(name):
        b=(ROOT/name).read_bytes()
        return json.loads(b),sha_blob(b)
    m,msha=read("canonical_current_master_manifest.json")
    p,psha=read("canonical_current_price_dv30.json")
    require(m.get("execution")=="NONE" and p.get("execution")=="NONE" and
            m.get("real_money")=="NO-GO" and p.get("real_money")=="NO-GO" and
            m.get("unknown_never_pass") is True and
            p.get("unknown_never_pass") is True,"PRODUCTION_SAFETY")
    require(m.get("asof_et")==p.get("asof_et"),"SOURCE_ASOF")
    names=p.get("pass_symbols")
    require(type(names) is list and names==sorted(set(names))
            and all(re.fullmatch(r"[A-Z0-9.-]+",x) for x in names),
            "PRICE_PASS_SYMBOLS")
    require(p.get("pass_hash")==symbol_hash(names) and
            p.get("pass_count")==len(names),"PRICE_HASH")
    require(m.get("queue_hash")==p.get("source_master_queue_hash") and
            set(names).issubset(m.get("pass_symbols") or []) and
            not set(names).intersection(m.get("unknown_symbols") or []),
            "MASTER_PRICE_IDENTITY")
    return m,p,{"master":msha,"price":psha}

def get_sip(symbols,asof,key,secret):
    et=ZoneInfo("America/New_York")
    end=(dt.datetime.fromisoformat(asof).replace(tzinfo=et)+dt.timedelta(days=1))
    start=end-dt.timedelta(days=470)
    params=urllib.parse.urlencode({"symbols":",".join(symbols),"timeframe":"1Day",
        "start":start.isoformat(),"end":end.isoformat(),
        "feed":"sip","sort":"asc","limit":"10000"})
    url="https://data.alpaca.markets/v2/stocks/bars?"+params
    result={x:[] for x in symbols}
    pages=0
    while url:
        pages+=1
        require(pages<=6,"PAGINATION_LIMIT")
        req=urllib.request.Request(url,headers={
            "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
            "Accept":"application/json","User-Agent":"xray-research-only-no-trades"})
        with urllib.request.urlopen(req,timeout=30) as resp:
            obj=json.load(resp)
        require(type(obj) is dict and type(obj.get("bars")) is dict,
                "ALPACA_SCHEMA")
        for sym,raw in obj["bars"].items():
            require(sym in result and type(raw) is list,"UNEXPECTED_SYMBOL")
            for x in raw:
                result[sym].append({"date":x["t"][:10],
                    "open":x["o"],"high":x["h"],"low":x["l"],
                    "close":x["c"],"volume":x["v"]})
        token=obj.get("next_page_token")
        url=("https://data.alpaca.markets/v2/stocks/bars?"+
             params+"&page_token="+urllib.parse.quote(token,safe="")) if token else None
    return result

def report(now):
    master,price,shas=read_canonical()
    asof=price["asof_et"]
    last=last_complete_session(now)
    initial={"schema":SCHEMA,"source_asof":asof,
        "latest_completed_session":last,"source_blob_shas":shas,
        "source":"ALPACA_READONLY_DELAYED_SIP_HISTORICAL_IF_AUTHORIZED",
        "cohort":len(price["pass_symbols"]),"260d_52w_verified_count":0,
        "b_precursor_count":0,"b_precursors":[],"blocked_symbols":[],
        "qualified_al_count":0,"qualified_al_symbols":[],
        "alpha_authority":False,"source_rights_not_elevated":True,
        "delivery_attested":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"orders":[]}
    if asof!=last:return dict(initial,status="BLOCKED_STALE_PRICE")
    key=os.environ.get("APCA_API_KEY_ID") or ""
    secret=os.environ.get("APCA_API_SECRET_KEY") or ""
    if not key or not secret:
        return dict(initial,status="BLOCKED_GITHUB_ALPACA_READONLY_CREDENTIALS")
    # Source and licensing conditions remain independent of API success.
    symbols=price["pass_symbols"]
    try:
        qb=get_sip(["QQQ"],asof,key,secret)["QQQ"]
        validate_bars("QQQ",qb,asof)
        positive=[];missing=[];complete=0
        for i in range(0,len(symbols),20):
            cohort=symbols[i:i+20]
            group=get_sip(cohort,asof,key,secret)
            for sym in cohort:
                try:
                    r=evaluate_b_precursor(sym,group[sym],qb,asof)
                    complete+=1
                    if r["b_precursor"]:positive.append(r)
                except (ValueError,KeyError,IndexError,OverflowError):
                    missing.append(sym)
        result=dict(initial,**{"260d_52w_verified_count":complete,
                                "b_precursor_count":len(positive),
                                "b_precursors":positive,
                                "blocked_symbols":missing})
        # Do not promote partial-source observations, even to current WATCH.
        if missing or complete!=len(symbols):
            return dict(result,status="BLOCKED_INCOMPLETE_COHORT",
                        b_precursors=[],b_precursor_count=0)
        return dict(result,status="B_PRECURSOR_RESEARCH_ONLY_NO_AL")
    except Exception as exc:
        # Never print vendor errors or credentials in public CI.
        return dict(initial,status="BLOCKED_SIP_SOURCE_OR_RIGHTS",
                    error_class=type(exc).__name__)

def selftest():
    for obj in ([],["B","A"],["A","A"],["A","?"]):
        try:
            require(type(obj) is list and bool(obj) and obj==sorted(set(obj)) and
                    all(re.fullmatch(r"[A-Z0-9.-]+",x) for x in obj),
                    "BAD_TEST_COHORT")
        except ValueError:pass
        else:raise RuntimeError("MALFORMED_COHORT_ACCEPTED")
    for x in (float("nan"),float("inf"),-1.0):
        try:mean([1.0,x])
        except ValueError:pass
        else:raise RuntimeError("UNSAFE_NUMERIC_ACCEPTED")
    try:ema([1.0]*9,10)
    except ValueError:pass
    else:raise RuntimeError("PARTIAL_WEEKLY_ACCEPTED")
    require(round(ema([10.0]*52,10),3)==10.0,"EMA_REPRODUCIBILITY")
    print("XRAY_ALPACA_SIP_EOD_B_SHADOW_SELFTEST=PASS_FAIL_CLOSED_8_NEGATIVE_NO_AL")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    if not args.out or args.out.resolve().is_relative_to(ROOT.parent.resolve()):
        ap.error("--out must be runner-private, never a tracked vendor artifact")
    r=report(dt.datetime.now(dt.timezone.utc))
    args.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_ALPACA_SIP_260_52_RESEARCH="+r["status"])
    print("XRAY_ALPACA_SIP_SOURCE_PROVEN="+str(r["260d_52w_verified_count"]))
    print("XRAY_ALPACA_SIP_B_PRECURSOR="+str(r["b_precursor_count"]))
    print("XRAY_ALPACA_SIP_AL_AUTHORITY=NONE")

if __name__=="__main__":main()
