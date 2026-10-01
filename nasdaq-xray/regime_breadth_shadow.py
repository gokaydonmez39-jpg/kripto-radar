#!/usr/bin/env python3
"""XRAY REGIME/BREADTH shadow engine.
Universe = canonical Bigdata-MC CURRENT_CORE names only.
History accelerator = Sina. UNKNOWN!=PASS. Never G9.
"""
from __future__ import annotations
import json, math, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
MC=Path(os.getenv("XRAY_MC_STATE", str(ROOT/"mc_final_state.json")))
OUT=ROOT/"regime_breadth_shadow.json"
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_BREADTH_WORKERS","8"))

def hist(sym,asof):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:return sym,None,"EMPTY"
        cols={c.lower():c for c in df.columns}
        if "date" not in cols or "close" not in cols:return sym,None,"COLUMNS"
        x=df[[cols["date"],cols["close"]]].copy()
        x.columns=["date","close"]
        x["date"]=pd.to_datetime(x["date"],errors="coerce")
        x["close"]=pd.to_numeric(x["close"],errors="coerce")
        x=x.dropna().sort_values("date")
        x=x[x["date"]<=pd.Timestamp(asof)]
        if len(x)<200:return sym,None,"LT200"
        return sym,x,None
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:120]}"

def main():
    mc=json.loads(MC.read_text())
    syms=list(mc["current_core_mc_pass"])
    asof=mc["asof_et"]
    data={};missing={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e=fut.result()
            if x is None:missing[s]=e
            else:data[s]=x

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
      "source_authority":"SHADOW_REGIME_ACCELERATOR_ONLY"
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:out[k] for k in ["current_core_count","history_ok_count","breadth_missing_count","breadth_above_sma50_pct","nh20","nl20","regime"]},sort_keys=True))

if __name__=="__main__":
    main()
