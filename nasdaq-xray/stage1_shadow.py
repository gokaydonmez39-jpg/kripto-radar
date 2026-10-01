#!/usr/bin/env python3
"""XRAY Stage1 shadow technical engine.
Input: canonical-Bigdata MC pass list.
History: Sina raw daily accelerator (shadow only, never G9/canonical fill authority).
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
MC=Path(os.getenv("XRAY_MC_STATE", str(ROOT/"mc_final_state.json")))
OUT=Path(os.getenv("XRAY_STAGE1_OUT", str(ROOT/"stage1_shadow.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_STAGE1_WORKERS","8"))

def wilder_atr(df, n=14):
    h=df["high"].astype(float); l=df["low"].astype(float); c=df["close"].astype(float)
    pc=c.shift(1)
    tr=pd.concat([(h-l).abs(),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    if len(tr)<n+1: return None
    vals=tr.to_list()
    atr=sum(vals[:n])/n
    series=[None]*(n-1)+[atr]
    for x in vals[n:]:
        atr=((n-1)*atr+x)/n
        series.append(atr)
    return pd.Series(series,index=df.index,dtype="float64")

def build_week_last(asof):
    cal=mcal.get_calendar("NASDAQ")
    a=datetime.fromisoformat(asof).date()
    sched=cal.schedule(start_date=(a-timedelta(days=900)).isoformat(),end_date=(a+timedelta(days=10)).isoformat())
    week_last={}
    for idx,_ in sched.iterrows():
        d=idx.date()
        k=pd.Timestamp(d).to_period("W-FRI").start_time.date().isoformat()
        week_last[k]=d.isoformat()
    return week_last

def weekly_gate(df, asof, week_last):
    x=df.copy()
    x["week_key"]=x["date"].dt.to_period("W-FRI").apply(lambda p:p.start_time.date().isoformat())
    groups=[]
    for k,g in x.groupby("week_key"):
        expected=week_last.get(k)
        if not expected or expected>asof: continue
        if g["date"].dt.date.max().isoformat()!=expected: continue
        groups.append((k,float(g.iloc[-1]["close"])))
    groups=sorted(groups)
    if len(groups)<52: return {"pass":False,"reason":"WEEKLY_HISTORY_LT52","weeks":len(groups)}
    closes=pd.Series([v for _,v in groups],dtype="float64")
    ema10=closes.ewm(span=10,adjust=False).mean()
    sma30=closes.rolling(30).mean()
    if len(ema10)<4 or pd.isna(sma30.iloc[-1]):
        return {"pass":False,"reason":"WEEKLY_INDICATOR_MISSING","weeks":len(groups)}
    p=bool(
      closes.iloc[-1]>ema10.iloc[-1] and
      ema10.iloc[-1]>ema10.iloc[-2]>ema10.iloc[-3]>ema10.iloc[-4] and
      closes.iloc[-1]>sma30.iloc[-1]
    )
    return {
      "pass":p,"weeks":len(groups),"close":float(closes.iloc[-1]),
      "ema10":float(ema10.iloc[-1]),"ema10_m1":float(ema10.iloc[-2]),
      "ema10_m2":float(ema10.iloc[-3]),"ema10_m3":float(ema10.iloc[-4]),
      "sma30":float(sma30.iloc[-1])
    }

def base_pool(df):
    if len(df)<40:return []
    atr=wilder_atr(df,14)
    if atr is None or pd.isna(atr.iloc[-2]):return []
    A=float(atr.iloc[-2])
    if not math.isfinite(A) or A<=0:return []
    # trigger bar = last completed daily row. Base is immediately preceding trigger.
    out=[]
    tr=pd.concat([
      (df["high"]-df["low"]).abs(),
      (df["high"]-df["close"].shift(1)).abs(),
      (df["low"]-df["close"].shift(1)).abs()
    ],axis=1).max(axis=1)
    for n in [5,10,15,20]:
        if len(df)<n+21:continue
        base=df.iloc[-(n+1):-1]
        bh=float(base["high"].max()); bl=float(base["low"].min())
        width=(bh-bl)/A
        last5=tr.iloc[-6:-1].mean()
        prev20=tr.iloc[-26:-6].mean()
        compression=bool(math.isfinite(last5) and math.isfinite(prev20) and prev20>0 and last5<=0.8*prev20)
        if 0.30<=width<=2.05 and compression:
            out.append({"window":n,"base_high":bh,"base_low":bl,"width_atr":width,"atr14_frozen":A})
    return out

def process(sym,asof,week_last):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:return sym,{"status":"UNKNOWN","reason":"SINA_EMPTY"}
        cols={c.lower():c for c in df.columns}
        need=["date","open","high","low","close","volume"]
        if any(k not in cols for k in need):return sym,{"status":"UNKNOWN","reason":"COLUMNS_MISSING"}
        x=df[[cols[k] for k in need]].copy()
        x.columns=need
        x["date"]=pd.to_datetime(x["date"],errors="coerce")
        for k in ["open","high","low","close","volume"]:x[k]=pd.to_numeric(x[k],errors="coerce")
        x=x.dropna().sort_values("date")
        x=x[x["date"]<=pd.Timestamp(asof)]
        if len(x)<260:return sym,{"status":"HISTORY_FAIL","reason":"DAILY_LT260","bars":len(x)}
        wg=weekly_gate(x,asof,week_last)
        if not wg.get("pass"):
            return sym,{"status":"WEEKLY_FAIL","weekly":wg}
        close=x["close"].astype(float)
        sma50=close.rolling(50).mean()
        recent20_high=x["high"].astype(float).rolling(20).max()
        a_pool=False
        if len(x)>=70 and pd.notna(sma50.iloc[-1]) and pd.notna(sma50.iloc[-21]) and pd.notna(recent20_high.iloc[-1]):
            rh=float(recent20_high.iloc[-1]); last=float(close.iloc[-1])
            a_pool=bool(last>float(sma50.iloc[-1]) and float(sma50.iloc[-1])>float(sma50.iloc[-21]) and rh>0 and 0.88*rh<=last<=rh)
        b=base_pool(x)
        h252=float(close.iloc[-252:].max()); h120=float(close.iloc[-120:].max()); last=float(close.iloc[-1])
        dd252=last/h252-1 if h252>0 else None
        dd120=last/h120-1 if h120>0 else None
        d_pool=bool((dd252 is not None and dd252<=-0.15) or (dd120 is not None and dd120<=-0.20))
        return sym,{
          "status":"WEEKLY_PASS","weekly":wg,
          "a_trend_pool":a_pool,
          "b_tight_base_pool":b,
          "d_drawdown_pool":d_pool,
          "dd252":dd252,"dd120":dd120,
          "last_close":last
        }
    except Exception as e:
        return sym,{"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"}

def main():
    mc=json.loads(MC.read_text())
    syms=list(mc.get("current_core_mc_pass") or [])
    asof=mc["asof_et"]
    state_caps={s:(mc.get("state_caps") or {}).get(s,"NORMAL") for s in syms}
    r92_ineligible=set(mc.get("r92_ineligible") or [])
    week_last=build_week_last(asof)
    results={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(process,s,asof,week_last):s for s in syms}
        for fut in as_completed(futs):
            sym,res=fut.result();results[sym]=res
    for s,r in results.items():
        r["state_cap"]=state_caps.get(s,"NORMAL")
        r["r92_eligible"]=s not in r92_ineligible
    weekly=[s for s,r in results.items() if r.get("status")=="WEEKLY_PASS"]
    a=[s for s in weekly if results[s].get("a_trend_pool")]
    b=[s for s in weekly if results[s].get("b_tight_base_pool")]
    d=[s for s in weekly if results[s].get("d_drawdown_pool")]
    unknown=[s for s,r in results.items() if r.get("status")=="UNKNOWN"]
    out={
      "schema":"XRAY_STAGE1_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "input_current_core_count":len(syms),
      "weekly_pass_count":len(weekly),"weekly_pass":sorted(weekly),
      "a_trend_pool_count":len(a),"a_trend_pool":sorted(a),
      "b_tight_base_pool_count":len(b),"b_tight_base_pool":sorted(b),
      "d_drawdown_pool_count":len(d),"d_drawdown_pool":sorted(d),
      "unknown_count":len(unknown),"unknown":sorted(unknown),
      "state_caps":state_caps,
      "r92_ineligible":sorted(r92_ineligible & set(syms)),
      "results":results,
      "source_authority":"SHADOW_TECHNICAL_ACCELERATOR_ONLY",
      "notes":["C post-earnings family is evaluated later from official earnings/event evidence.","No setup signal or R92 registration is created here."]
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ["input_current_core_count","weekly_pass_count","a_trend_pool_count","b_tight_base_pool_count","d_drawdown_pool_count","unknown_count"]},sort_keys=True))

if __name__=="__main__":
    main()
