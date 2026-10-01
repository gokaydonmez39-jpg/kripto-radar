#!/usr/bin/env python3
"""XRAY REGIME/BREADTH shadow engine.
Universe = canonical Bigdata-MC CURRENT_CORE names only.
History accelerator = Sina. UNKNOWN!=PASS. Never G9.
"""
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
MC=Path(os.getenv("XRAY_MC_STATE", str(ROOT/"mc_final_state.json")))
OUT=Path(os.getenv("XRAY_REGIME_OUT", str(ROOT/"regime_breadth_shadow.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_BREADTH_WORKERS","8"))

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")

def yahoo_close_history(sym,asof):
    end=datetime.fromisoformat(asof).replace(tzinfo=NY)+timedelta(days=1)
    start=end-timedelta(days=900)
    ticker=sym.replace(".","-")
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(ticker)+"?"+urllib.parse.urlencode({
      "period1":int(start.timestamp()),"period2":int(end.timestamp()),"interval":"1d",
      "events":"history","includeAdjustedClose":"false"
    })
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"})
    with urllib.request.urlopen(req,timeout=25) as r:
        obj=json.loads(r.read().decode("utf-8"))
    res=((obj.get("chart") or {}).get("result") or [])
    if not res:return None,"YAHOO_EMPTY"
    z=res[0]; ts=z.get("timestamp") or []
    q=(((z.get("indicators") or {}).get("quote") or [{}])[0]); closes=q.get("close") or []
    rows=[]
    for t,v in zip(ts,closes):
        try:
            vv=float(v)
            if not math.isfinite(vv) or vv<=0:continue
            day=datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat()
            if day<=asof:rows.append((day,vv))
        except Exception:continue
    if not rows:return None,"YAHOO_NO_USABLE"
    x=pd.DataFrame(rows,columns=["date","close"])
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    x=x.dropna().drop_duplicates("date",keep="last").sort_values("date")
    if len(x)<200:return None,f"YAHOO_LT200:{len(x)}"
    return x,None

def hist(sym,asof):
    primary_error=None
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is not None and not df.empty:
            cols={c.lower():c for c in df.columns}
            if "date" in cols and "close" in cols:
                x=df[[cols["date"],cols["close"]]].copy()
                x.columns=["date","close"]
                x["date"]=pd.to_datetime(x["date"],errors="coerce")
                x["close"]=pd.to_numeric(x["close"],errors="coerce")
                x=x.dropna().sort_values("date")
                x=x[x["date"]<=pd.Timestamp(asof)]
                if len(x)>=200:return sym,x,None,"SINA_US_DAILY"
                primary_error=f"SINA_LT200:{len(x)}"
            else:primary_error="SINA_COLUMNS"
        else:primary_error="SINA_EMPTY"
    except Exception as e:
        primary_error=f"SINA_{type(e).__name__}:{str(e)[:100]}"
    try:
        y,e=yahoo_close_history(sym,asof)
        if y is not None:return sym,y,None,"YAHOO_CHART_FREE_FALLBACK"
        return sym,None,f"{primary_error}|{e}",None
    except Exception as e:
        return sym,None,f"{primary_error}|YAHOO_{type(e).__name__}:{str(e)[:100]}",None

def main():
    mc=json.loads(MC.read_text())
    syms=list(mc["current_core_mc_pass"])
    asof=mc["asof_et"]
    data={};missing={};history_source={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:missing[s]=e
            else:
                data[s]=x
                history_source[s]=src

    if "QQQ" not in data:
        regime="UNKNOWN"
        q={}
    else:
        qdf=data["QQQ"]; c=qdf["close"]
        sma50=c.rolling(50).mean(); sma200=c.rolling(200).mean()
        slope20=float(sma50.iloc[-1]-sma50.iloc[-21]) if len(sma50)>=21 else float("nan")
        qclose=float(c.iloc[-1])
        q={
          "close":qclose,"sma50":float(sma50.iloc[-1]),"sma200":float(sma200.iloc[-1]),
          "sma50_slope20":slope20
        }
        regime="PENDING_BREADTH"

    eligible=[s for s in syms if s in data]
    above50=0; nh20=0; nl20=0
    breadth_missing=[]
    for s in syms:
        x=data.get(s)
        if x is None:
            breadth_missing.append(s);continue
        c=x["close"]
        if len(c)<200:
            breadth_missing.append(s);continue
        last=float(c.iloc[-1]); sma50=float(c.rolling(50).mean().iloc[-1])
        if last>sma50:above50+=1
        win=c.iloc[-20:]
        if last>=float(win.max())-1e-12:nh20+=1
        if last<=float(win.min())+1e-12:nl20+=1

    breadth_pct=above50/len(syms) if syms else None
    if breadth_missing or "QQQ" not in data:
        regime="UNKNOWN"
    else:
        if q["close"]<q["sma200"] or q["sma50_slope20"]<0:
            regime="WEAK"
        elif q["close"]>q["sma50"] and q["close"]>q["sma200"] and q["sma50_slope20"]>0 and breadth_pct>=0.55 and nh20>nl20:
            regime="STRONG"
        else:
            regime="MIXED"

    out={
      "schema":"XRAY_REGIME_BREADTH_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "current_core_count":len(syms),"history_ok_count":len(eligible),
      "breadth_missing_count":len(breadth_missing),"breadth_missing":sorted(breadth_missing),
      "qqq":q,"breadth_above_sma50_count":above50,"breadth_above_sma50_pct":breadth_pct,
      "nh20":nh20,"nl20":nl20,"regime":regime,
      "history_source_by_symbol":history_source,
      "history_source_counts":{
        "SINA_US_DAILY":sum(1 for v in history_source.values() if v=="SINA_US_DAILY"),
        "YAHOO_CHART_FREE_FALLBACK":sum(1 for v in history_source.values() if v=="YAHOO_CHART_FREE_FALLBACK")
      },
      "source_authority":"SHADOW_REGIME_ACCELERATOR_ONLY_SINA_PRIMARY_YAHOO_FALLBACK"
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:out[k] for k in ["current_core_count","history_ok_count","breadth_missing_count","breadth_above_sma50_pct","nh20","nl20","regime"]},sort_keys=True))

if __name__=="__main__":
    main()
