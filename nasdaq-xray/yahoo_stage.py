#!/usr/bin/env python3
"""NASDAQ SWING X-RAY resumable zero-key OHLCV stage.
Yahoo chart JSON is an accelerator/fallback data source, never G9.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

TASK_ID="6a825366222081918997094d76e6ae46"
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
STATE=Path(__file__).resolve().parent/"yahoo_state.json"
BATCH=int(os.getenv("XRAY_YAHOO_BATCH","500"))
WORKERS=int(os.getenv("XRAY_YAHOO_WORKERS","12"))
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

def h(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def get_json(url, timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def get_text(url,timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def official_universe():
    text=get_text(NASDAQ_URL)
    lines=[x.strip("\r") for x in text.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rd=csv.DictReader(io.StringIO(body),delimiter="|")
    symbols=[]
    for row in rd:
        s=(row.get("Symbol") or "").strip().upper()
        if not s: continue
        if row.get("Test Issue")!="N": continue
        if row.get("ETF")=="Y": continue
        if row.get("NextShares")=="Y": continue
        symbols.append(s)
    symbols=sorted(set(symbols))
    if not footer or not symbols: raise RuntimeError("OFFICIAL_UNIVERSE_INVALID")
    return symbols,footer

def yahoo_symbol(s):
    return s.replace(".","-").replace("/","-")

def official_sessions():
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    start=(now.astimezone(ZoneInfo("America/New_York")).date()).isoformat()
    from datetime import timedelta
    d0=(now.date()-timedelta(days=800)).isoformat()
    d1=(now.date()+timedelta(days=1)).isoformat()
    sched=cal.schedule(start_date=d0,end_date=d1)
    completed=[]
    for idx,row in sched.iterrows():
        close=row["market_close"].to_pydatetime()
        if close<=now:
            completed.append(idx.date().isoformat())
    if len(completed)<260: raise RuntimeError("CALENDAR_TOO_SHORT")
    return completed[-520:], completed[-1], completed[-20:]

def parse_one(symbol,asof,expected20):
    ys=yahoo_symbol(symbol)
    q=urllib.parse.urlencode({"range":"2y","interval":"1d","events":"div,splits","includeAdjustedClose":"true"})
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ys,safe='')}?{q}"
    try:
        data=get_json(url)
        result=(data.get("chart") or {}).get("result")
        if not result: return symbol,"UNKNOWN","NO_RESULT"
        x=result[0]
        ts=x.get("timestamp") or []
        quote=((x.get("indicators") or {}).get("quote") or [{}])[0]
        closes=quote.get("close") or []
        vols=quote.get("volume") or []
        bydate={}
        for i,t in enumerate(ts):
            if i>=len(closes) or i>=len(vols): continue
            c=closes[i]; v=vols[i]
            if c is None or v is None: continue
            try: c=float(c); v=float(v)
            except: continue
            if not(math.isfinite(c) and math.isfinite(v) and c>0 and v>0): continue
            d=datetime.fromtimestamp(int(t),timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if d<=asof: bydate[d]=(c,v)
        events=x.get("events") or {}
        splits=(events.get("splits") or {}).values()
        recent_split=False
        for ev in splits:
            d=datetime.fromtimestamp(int(ev.get("date",0)),timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if d in expected20: recent_split=True
        if recent_split: return symbol,"UNKNOWN","RECENT_SPLIT"
        if asof not in bydate: return symbol,"UNKNOWN","ASOF_MISSING"
        if any(d not in bydate for d in expected20): return symbol,"UNKNOWN","EXACT20_MISSING"
        price=bydate[asof][0]
        dv20=sorted(bydate[d][0]*bydate[d][1] for d in expected20)
        med=(dv20[9]+dv20[10])/2.0
        n=len(bydate)
        if price<=10: return symbol,"FAIL_PRICE",{"price":price,"bars":n}
        if med<50_000_000: return symbol,"FAIL_DV20",{"price":price,"dv20":med,"bars":n}
        if n<260: return symbol,"FAIL_HISTORY",{"price":price,"dv20":med,"bars":n}
        return symbol,"PASS",{"price":price,"dv20":med,"bars":n}
    except Exception as e:
        return symbol,"UNKNOWN",f"{type(e).__name__}:{str(e)[:120]}"

def load():
    if STATE.exists():
        try:return json.loads(STATE.read_text())
        except:pass
    return {}

def save(s):
    tmp=STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s,sort_keys=True,indent=2)+"\n")
    tmp.replace(STATE)

def main():
    symbols,footer=official_universe()
    sessions,asof,expected20=official_sessions()
    uh=h(symbols)
    s=load()
    if s.get("universe_hash")!=uh or s.get("asof_et")!=asof or s.get("status")=="COMPLETE":
        s={
          "schema":"XRAY_YAHOO_RESUMABLE_V1","task_id":TASK_ID,"execution":"NONE","real_money":"NO-GO",
          "unknown_never_pass":True,"source":"YAHOO_CHART_JSON_ACCELERATOR_NOT_G9",
          "official_footer":footer,"universe_hash":uh,"asof_et":asof,"expected20":expected20,
          "cursor":0,"total":len(symbols),"pass":{},"unknown":{},"fail_price":0,"fail_dv20":0,"fail_history":0,
          "status":"PARTIAL"
        }
    start=int(s.get("cursor",0)); end=min(start+BATCH,len(symbols)); batch=symbols[start:end]
    results=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(parse_one,x,asof,expected20):x for x in batch}
        for f in as_completed(futs):
            results.append(f.result())
    for sym,status,info in results:
        if status=="PASS": s["pass"][sym]=info; s["unknown"].pop(sym,None)
        elif status=="UNKNOWN": s["unknown"][sym]=info
        elif status=="FAIL_PRICE": s["fail_price"]+=1
        elif status=="FAIL_DV20": s["fail_dv20"]+=1
        elif status=="FAIL_HISTORY": s["fail_history"]+=1
    s["cursor"]=end
    s["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    s["processed_this_run"]=len(batch)
    s["pass_count"]=len(s["pass"])
    s["unknown_count"]=len(s["unknown"])
    s["status"]="COMPLETE" if end>=len(symbols) else "PARTIAL"
    s["state_hash"]=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    save(s)
    print(json.dumps({"status":s["status"],"asof":asof,"cursor":end,"total":len(symbols),"pass":len(s["pass"]),"unknown":len(s["unknown"]),"fail_price":s["fail_price"],"fail_dv20":s["fail_dv20"],"fail_history":s["fail_history"]},sort_keys=True))

if __name__=="__main__":
    main()
