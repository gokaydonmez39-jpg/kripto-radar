#!/usr/bin/env python3
"""Personal-only free IEX EOD swing-research overlay; NO R92 or trade orders.

IEX is a SINGLE venue, NOT consolidated Nasdaq/SIP RTH volume. Indicators
are research observations, NEVER certified C4.17 PRICE/MC/HISTORY/AL. No raw
vendor OHLCV or price levels are exported. API calls require existing Alpaca
personal market-data credentials and are always zero-dollar, read-only.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_FREE_IEX_EOD_RESEARCH_V1"
PROVIDER="ALPACA_BASIC_IEX_SINGLE_EXCHANGE"
MAX_CALLS=64
BATCH=10
N=260
NY=ZoneInfo("America/New_York")
VALID_LABELS={"RESEARCH_BREAKOUT_WATCH","RESEARCH_RECLAIM_WATCH",
              "TREND_WATCH","WATCH_ONLY","UNKNOWN_IEX_COVERAGE"}

def need(v,why):
    if not v: raise ValueError("XRAY_PERSONAL_IEX_"+why)

def seal(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def source_scope(root,asof):
    watch=root.get("watch_radar") or {}
    tech=root.get("candidate_technical_funnel") or {}
    rows=watch.get("watchlist")
    need(root.get("asof_et")==asof==watch.get("asof_et")==tech.get("asof_et")
         and root.get("execution")=="NONE" and root.get("real_money")=="NO-GO"
         and watch.get("execution")=="NONE" and watch.get("real_money")=="NO-GO"
         and watch.get("unknown_never_pass") is True
         and watch.get("all_eligible_candidates_tracked") is True
         and watch.get("watchlist_cap") is None
         and watch.get("source_candidates_sha256")==tech.get("source_candidates_sha256")
         and isinstance(rows,list) and bool(rows)
         and len(rows)==watch.get("watchlist_count")==watch.get("price_liquidity_screened_count"),
         "WATCH_ASOF_UNIVERSE_NOT_EXACT")
    symbols=[x.get("symbol") for x in rows if isinstance(x,dict)]
    need(len(symbols)==len(rows) and len(symbols)==len(set(symbols))
         and all(isinstance(x,str) and x.isascii() and x.replace(".","").isalnum()
                 and x==x.upper() for x in symbols)
         and all(row.get("buy_signal") is False
                 and row.get("classification")=="WATCH_LIQUIDITY_PRE_SCREEN_ONLY"
                 for row in rows), "WATCH_IDENTITY_OR_FAKE_BUY")
    return sorted(symbols)

def indicator(bars,days):
    """Return source-graded NON-AL research state for exactly 260 sessions."""
    if not isinstance(bars,list) or len(bars)!=N:
        return "UNKNOWN_IEX_COVERAGE",["MISSING_260_IEX_SESSIONS"]
    close=[];high=[];low=[];volume=[];got=[]
    try:
        for bar in bars:
            t=datetime.fromisoformat(str(bar["t"]).replace("Z","+00:00"))
            need(t.tzinfo is not None,"BAR_NAIVE_TIME")
            d=t.astimezone(NY).date().isoformat()
            o,h,l,c,v=(float(bar[k]) for k in ("o","h","l","c","v"))
            need(all(math.isfinite(x) and x>0 for x in (o,h,l,c,v))
                 and h>=max(o,c,l) and l<=min(o,c,h),
                 "BAR_OHLCV_UNRELIABLE")
            got.append(d);close.append(c);high.append(h);low.append(l);volume.append(v)
    except (TypeError,ValueError,KeyError,OverflowError):
        return "UNKNOWN_IEX_COVERAGE",["INVALID_IEX_BAR"]
    if got!=days or len(got)!=len(set(got)):
        return "UNKNOWN_IEX_COVERAGE",["SESSION_MISMATCH_IEX_NOT_PIT"]
    ma20=statistics.mean(close[-20:])
    ma50=statistics.mean(close[-50:])
    ma200=statistics.mean(close[-200:])
    pma20=statistics.mean(close[-21:-1])
    pma50=statistics.mean(close[-51:-1])
    moves=[close[i]-close[i-1] for i in range(len(close)-14,len(close))]
    gain=sum(max(0,z) for z in moves)
    loss=sum(max(0,-z) for z in moves)
    rsi=100*gain/(gain+loss) if gain+loss else 50
    trs=[max(high[i]-low[i],abs(high[i]-close[i-1]),abs(low[i]-close[i-1]))
         for i in range(len(close)-14,len(close))]
    atr_ratio=statistics.mean(trs)/close[-1]
    rv=volume[-1]/statistics.median(volume[-21:-1])
    need(math.isfinite(rv) and rv>0,"INVALID_RELATIVE_IEX_VOLUME")
    if atr_ratio>0.08:
        return "WATCH_ONLY",["ATR14_OVER_8PCT","IEX_VOLUME_NOT_CONSOLIDATED"]
    if (close[-1]>max(high[-21:-1]) and close[-1]>ma50>ma200
            and 52<=rsi<=82 and rv>=1.2):
        return "RESEARCH_BREAKOUT_WATCH",["IEX_ONLY_NO_EVENT_OR_MC_CLEARANCE"]
    if (close[-1]>=ma20 and close[-2]<pma20 and close[-1]>ma50
            and ma50>pma50 and 43<=rsi<=77 and rv>=1.0):
        return "RESEARCH_RECLAIM_WATCH",["IEX_ONLY_NO_EVENT_OR_MC_CLEARANCE"]
    if close[-1]>ma20>ma50>ma200 and 48<=rsi<=82:
        return "TREND_WATCH",["NO_BREAKOUT_OR_RECLAIM_CONFIRMATION"]
    return "WATCH_ONLY",["NO_RESEARCH_SETUP_OBSERVED"]

def api_batch(symbols,dates,key,secret,urlopen=urllib.request.urlopen):
    args={"symbols":",".join(symbols),"timeframe":"1Day","feed":"iex",
          "start":dates[0]+"T00:00:00Z",
          "end":(datetime.fromisoformat(dates[-1])+timedelta(days=1)).date().isoformat()+"T00:00:00Z",
          "limit":"10000","sort":"asc"}
    token=None;combined={s:[] for s in symbols};calls=0
    while True:
        qs=dict(args)
        if token:qs["page_token"]=token
        endpoint="https://data.alpaca.markets/v2/stocks/bars?"+urllib.parse.urlencode(qs)
        request=urllib.request.Request(endpoint,headers={
            "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
            "Accept":"application/json"})
        with urlopen(request,timeout=20) as response:
            payload=response.read(5_000_001)
            need(len(payload)<=5_000_000,"API_BODY_TOO_LARGE")
            body=json.loads(payload)
        need(isinstance(body,dict) and isinstance(body.get("bars"),dict),
             "API_SCHEMA_INVALID")
        need(set(body["bars"]).issubset(symbols),"API_SYMBOL_INJECTION")
        for sym,rows in body["bars"].items():
            need(isinstance(rows,list) and len(rows)<=10000,"API_PAGE_ROWS_INVALID")
            combined[sym].extend(rows)
        calls+=1
        token=body.get("next_page_token")
        need(token is None or isinstance(token,str) and 0<len(token)<=512,
             "API_PAGE_TOKEN_INVALID")
        if not token:break
        need(calls<=3,"EXCESSIVE_IEX_PAGINATION")
    return combined,calls

def evaluate(root,root_blob_sha,dates,fetch,asof):
    names=source_scope(root,asof)
    need(len(dates)==N and dates==sorted(set(dates))
         and dates[-1]==asof, "260_OFFICIAL_SESSION_ORDER")
    entries={};calls=0;exhausted=False
    for start in range(0,len(names),BATCH):
        part=names[start:start+BATCH]
        if exhausted:
            for sym in part:
                entries[sym]={"label":"UNKNOWN_IEX_COVERAGE",
                              "reasons":["PROVIDER_BUDGET_OR_ACCESS_UNVERIFIED"]}
            continue
        try:
            bars,n=fetch(part,dates)
            need(isinstance(bars,dict) and set(bars).issubset(part)
                 and isinstance(n,int) and 1<=n<=4,"BOUNDED_BATCH_INTEGRITY")
            calls+=n
            if calls>MAX_CALLS:raise ValueError("ZERO_DOLLAR_JOB_CALL_CAP")
            for sym in part:
                label,reasons=indicator(bars.get(sym,[]),dates)
                entries[sym]={"label":label,"reasons":reasons}
        except (ValueError,urllib.error.URLError,TimeoutError,OSError):
            exhausted=True
            for sym in part:
                entries[sym]={"label":"UNKNOWN_IEX_COVERAGE",
                              "reasons":["PROVIDER_TRANSPORT_OR_QUOTA_BLOCK"]}
    counts=dict(sorted(Counter(v["label"] for v in entries.values()).items()))
    selected=sorted(sym for sym,v in entries.items()
                    if v["label"] in ("RESEARCH_BREAKOUT_WATCH","RESEARCH_RECLAIM_WATCH"))
    return {"schema":SCHEMA,"asof_et":asof,"root_blob_sha":root_blob_sha,
            "population_sha256":hashlib.sha256("\n".join(names).encode()).hexdigest(),
            "total_watch_symbols":len(names),"attempted_symbols":len(entries),
            "vendor_requests":calls,"max_vendor_requests":MAX_CALLS,
            "confidence":{"grade":"LOW","feed":"IEX_SINGLE_EXCHANGE",
              "consolidated_rth_volume_verified":False,
              "independent_issuer_mc_verified":False,
              "issuer_event_clearance_verified":False,
              "is_probability":False},
            "state_counts":counts,"research_review_symbols":selected,
            "research_review_count":len(selected),
            "per_symbol":entries,"source":"ALPACA_FREE_IEX_EOD_NONCOMMERCIAL",
            "source_data_not_current_intraday":True,
            "canonical_price_promoted":False,"canonical_history_promoted":False,
            "canonical_mc_promoted":False,"registered_r92_count":0,
            "certified_buy_count":0,"orders":[],"broker":False,
            "iphone_receipt_attested":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "raw_vendor_ohlcv_exported":False}

def selftest():
    from current_history_source_request import expected_dates
    import copy
    dates,_=expected_dates("2026-10-21")
    need(len(dates)==260,"FIXTURE_SESSIONS")
    def raw(i):
        c=100+0.19*i+((i%7)-3)*0.6
        return c
    series=[]
    for i,d in enumerate(dates):
        c=raw(i)
        if i==259:c=raw(258)+4
        # Real Alpaca day bars are stamped at New York midnight; UTC
        # offset changes between EST and EDT.
        utc_midnight=datetime.fromisoformat(d+"T00:00:00").replace(
            tzinfo=NY).astimezone(timezone.utc).isoformat()
        series.append({"t":utc_midnight,"o":c-0.1,
                       "h":c+0.24,"l":c-0.4,"c":c,
                       "v":25000 if i==259 else 10000})
    label,_=indicator(series,dates)
    need(label in VALID_LABELS and label!="UNKNOWN_IEX_COVERAGE",
         "VALID_REALISTIC_IEX_SAMPLE")
    invalid=copy.deepcopy(series);invalid[0]["t"]=invalid[1]["t"]
    need(indicator(invalid,dates)[0]=="UNKNOWN_IEX_COVERAGE",
         "DUPLICATE_DATE_NEGATIVE")
    invalid=copy.deepcopy(series);invalid.pop()
    need(indicator(invalid,dates)[0]=="UNKNOWN_IEX_COVERAGE",
         "TRUNCATED_NEGATIVE")
    invalid=copy.deepcopy(series);invalid[-1]["v"]=-1
    need(indicator(invalid,dates)[0]=="UNKNOWN_IEX_COVERAGE",
         "NEGATIVE_VOLUME")
    invalid=copy.deepcopy(series);invalid[1]["h"]=0.1
    need(indicator(invalid,dates)[0]=="UNKNOWN_IEX_COVERAGE",
         "BAD_HL_NEGATIVE")
    fake={"asof_et":"2026-10-21","execution":"NONE","real_money":"NO-GO",
          "watch_radar":{"asof_et":"2026-10-21","execution":"NONE",
          "real_money":"NO-GO","unknown_never_pass":True,
          "all_eligible_candidates_tracked":True,"watchlist_cap":None,
          "watchlist_count":1,"price_liquidity_screened_count":1,
          "source_candidates_sha256":"a"*64,
          "watchlist":[{"symbol":"AAPL","buy_signal":False,
                        "classification":"WATCH_LIQUIDITY_PRE_SCREEN_ONLY"}]},
          "candidate_technical_funnel":{"asof_et":"2026-10-21",
                                        "source_candidates_sha256":"a"*64}}
    got=evaluate(fake,"f"*40,dates,lambda sy,ds:({sy[0]:series},1),"2026-10-21")
    need(got["attempted_symbols"]==1 and got["vendor_requests"]==1
         and got["registered_r92_count"]==0 and got["orders"]==[]
         and got["confidence"]["grade"]=="LOW"
         and got["raw_vendor_ohlcv_exported"] is False,
         "SAFE_EVALUATION")
    mutated=copy.deepcopy(fake);mutated["watch_radar"]["watchlist"][0]["buy_signal"]=True
    try:source_scope(mutated,"2026-10-21")
    except ValueError:pass
    else:raise AssertionError("FAKE_ROOT_BUY_PROMOTED")
    mutated=copy.deepcopy(fake);mutated["asof_et"]="2026-10-20"
    try:source_scope(mutated,"2026-10-21")
    except ValueError:pass
    else:raise AssertionError("CROSS_ASOF_ACCEPTED")
    missing=evaluate(fake,"f"*40,dates,lambda sy,ds:({},1),"2026-10-21")
    need(missing["state_counts"]=={"UNKNOWN_IEX_COVERAGE":1}
         and missing["research_review_count"]==0,
         "EMPTY_VENDOR_RESPONSE_NOT_A_CANDIDATE")
    print("XRAY_PERSONAL_FREE_IEX_SELFTEST=PASS_10_BOUNDARIES_NO_R92_NO_VENDOR_IO")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--out",type=Path)
    z=a.parse_args()
    if z.selftest:
        selftest()
        return
    need(z.out is not None and not z.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "PRIVATE_OUTPUT_REQUIRED")
    from source_epoch_freshness_guard import last_complete_session
    from current_history_source_request import expected_dates
    raw=(ROOT/"orchestrator_state.json").read_bytes()
    root=json.loads(raw)
    asof=last_complete_session(datetime.now(timezone.utc))
    need(root.get("asof_et")==asof,"STALE_COMPLETED_SESSION")
    dates,weeks=expected_dates(asof)
    need(len(weeks)==52,"OFFICIAL_WEEKLY_WINDOW_INVALID")
    key=os.environ.get("XRAY_ALPACA_DATA_KEY_ID") or os.environ.get("XRAY_ALPACA_API_KEY_ID")
    secret=os.environ.get("XRAY_ALPACA_DATA_SECRET_KEY") or os.environ.get("XRAY_ALPACA_API_SECRET_KEY")
    if not key or not secret:
        print("XRAY_PERSONAL_IEX=BLOCKED_NO_EXISTING_ALPACA_DATA_CREDENTIALS_NO_API_CALLS")
        raise SystemExit(3)
    report=evaluate(root,seal(raw),dates,
                    lambda names,days:api_batch(names,days,key,secret),asof)
    z.out.parent.mkdir(parents=True,exist_ok=True)
    z.out.write_text(json.dumps(report,sort_keys=True,separators=(",",":"))+"\n")
    print("XRAY_PERSONAL_IEX=RESEARCH_EVIDENCE_ONLY_NOT_R92")
    print("XRAY_PERSONAL_IEX_WATCH_TOTAL="+str(report["total_watch_symbols"]))
    print("XRAY_PERSONAL_IEX_REVIEW_CANDIDATES="+str(report["research_review_count"]))
    print("XRAY_PERSONAL_IEX_COUNTS="+json.dumps(report["state_counts"],sort_keys=True))
    print("XRAY_PERSONAL_IEX_VENDOR_CALLS="+str(report["vendor_requests"]))
    print("XRAY_PERSONAL_IEX_CONFIDENCE=LOW_SINGLE_VENUE_NO_BUY")

if __name__=="__main__":main()
