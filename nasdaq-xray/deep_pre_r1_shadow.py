#!/usr/bin/env python3
"""XRAY deep pre-R1 shadow engine for A/B/D.
Exact policy geometry where supported by shadow daily data.
No signal, no R92 registration, no G9 authority.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
import akshare as ak
import pandas as pd

ROOT=Path(__file__).resolve().parent
STAGE1=ROOT/"stage1_shadow.json"
REGIME=ROOT/"regime_breadth_shadow.json"
EVENTS=ROOT/"event_official_state.json"
OUT=ROOT/"deep_pre_r1_shadow.json"
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_DEEP_WORKERS","8"))

def get_hist(sym,asof):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:return sym,None,"EMPTY"
        cols={c.lower():c for c in df.columns}
        need=["date","open","high","low","close","volume"]
        if any(k not in cols for k in need):return sym,None,"COLS"
        x=df[[cols[k] for k in need]].copy();x.columns=need
        x["date"]=pd.to_datetime(x["date"],errors="coerce")
        for k in need[1:]:x[k]=pd.to_numeric(x[k],errors="coerce")
        x=x.dropna().sort_values("date");x=x[x["date"]<=pd.Timestamp(asof)]
        if len(x)<260:return sym,None,"LT260"
        return sym,x.reset_index(drop=True),None
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}"

def atr14(df):
    h=df.high.astype(float);l=df.low.astype(float);c=df.close.astype(float)
    pc=c.shift(1)
    tr=pd.concat([(h-l).abs(),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1).to_list()
    if len(tr)<15:return None
    a=sum(tr[:14])/14
    vals=[None]*13+[a]
    for x in tr[14:]:
        a=(13*a+x)/14
        vals.append(a)
    return pd.Series(vals,index=df.index,dtype="float64")

def strict_swings(df):
    hs=[];ls=[]
    H=df.high.to_list();L=df.low.to_list()
    n=len(df)
    for i in range(2,n-2):
        h=H[i]; l=L[i]
        if all(h>H[j] for j in [i-2,i-1,i+1,i+2]):
            hs.append(i)
        if all(l<L[j] for j in [i-2,i-1,i+1,i+2]):
            ls.append(i)
    return hs,ls

def common_rs(stock,qqq,n):
    s={d.strftime("%Y-%m-%d"):float(c) for d,c in zip(stock.date,stock.close)}
    q={d.strftime("%Y-%m-%d"):float(c) for d,c in zip(qqq.date,qqq.close)}
    common=sorted(set(s)&set(q))
    if len(common)<n+1:return None
    t=common[-1]; p=common[-1-n]
    return (s[t]/s[p])/(q[t]/q[p])-1

def rvol20(df):
    if len(df)<22:return None
    v=float(df.volume.iloc[-1])
    prev=[float(x) for x in df.volume.iloc[-21:-1] if float(x)>0]
    if len(prev)!=20:return None
    return v/median(prev)

def family_b(df):
    Aser=atr14(df)
    if Aser is None or pd.isna(Aser.iloc[-2]):return None
    A=float(Aser.iloc[-2])
    if not math.isfinite(A) or A<=0:return None
    tr=pd.concat([(df.high-df.low).abs(),(df.high-df.close.shift(1)).abs(),(df.low-df.close.shift(1)).abs()],axis=1).max(axis=1)
    passing=[]
    for n in [5,10,15,20]:
        if len(df)<n+26:continue
        base=df.iloc[-(n+1):-1]
        bh=float(base.high.max());bl=float(base.low.min())
        b=(bh-bl)/A
        last5=float(tr.iloc[-6:-1].mean());prev20=float(tr.iloc[-26:-6].mean())
        if 0.30<=b<=2.05 and prev20>0 and last5<=0.8*prev20:
            passing.append((n,bh,bl,b))
    if not passing:return {"pool":False}
    n,P,anchor,b=max(passing,key=lambda z:z[0])
    rv=rvol20(df); close=float(df.close.iloc[-1])
    confirmed=bool(close>P and rv is not None and rv>=1.5)
    return {"pool":True,"window":n,"P":P,"anchor":anchor,"b":b,"A":A,"rvol20":rv,"close":close,"breakout_confirmed":confirmed}

def active_hl_and_sh(df):
    hs,ls=strict_swings(df)
    last_idx=len(df)-1
    # confirmed by t+2 and therefore centers <= last-2
    hs=[i for i in hs if i+2<=last_idx]
    ls=[i for i in ls if i+2<=last_idx]
    if len(ls)<2 or not hs:return None
    # active HL = latest swing low strictly above preceding relevant swing low and not later undercut
    hl=None; prev=None
    for i in ls:
        if prev is not None and float(df.low.iloc[i])>float(df.low.iloc[prev]):
            if float(df.low.iloc[i+1:].min())>=float(df.low.iloc[i]):
                hl=i
        prev=i
    if hl is None:return None
    # nearest prior confirmed SH structurally before/around active HL; for recovery require a high before reclaim
    prior_h=[i for i in hs if i<hl]
    later_h=[i for i in hs if i>hl]
    return {"hl":hl,"prior_hs":prior_h,"later_hs":later_h,"hs":hs,"ls":ls}

def family_d(df,rs20,rs60):
    st=active_hl_and_sh(df)
    if not st:return {"pool":False,"reason":"NO_ACTIVE_HL"}
    hl=st["hl"]; prior=st["prior_hs"]
    if not prior:return {"pool":False,"reason":"NO_MEANINGFUL_SH"}
    sh=prior[-1]
    P=float(df.high.iloc[sh]); anchor=float(df.low.iloc[hl])
    Aser=atr14(df)
    if Aser is None or pd.isna(Aser.iloc[-2]):return {"pool":False,"reason":"ATR"}
    A=float(Aser.iloc[-2]); d=(P-anchor)/A if A>0 else None
    c=df.close.astype(float); last=float(c.iloc[-1])
    ema50=float(c.ewm(span=50,adjust=False).mean().iloc[-1])
    rv=rvol20(df)
    h252=float(c.iloc[-252:].max());h120=float(c.iloc[-120:].max())
    dd252=last/h252-1;dd120=last/h120-1
    pool=bool(dd252<=-0.15 or dd120<=-0.20)
    reclaim=bool(pool and d is not None and 0.30<=d<=2.05 and last>P and last>ema50 and rs20 is not None and rs60 is not None and rs20>0 and rs60>0 and rv is not None and rv>=1.2)
    return {"pool":pool,"hl_date":df.date.iloc[hl].strftime("%Y-%m-%d"),"P":P,"anchor":anchor,"A":A,"d":d,"close":last,"ema50":ema50,"rs20":rs20,"rs60":rs60,"rvol20":rv,"dd252":dd252,"dd120":dd120,"dk3_pre_r1":reclaim}

def family_a(df):
    st=active_hl_and_sh(df)
    if not st:return {"pool":False,"reason":"NO_ACTIVE_HL"}
    hl=st["hl"]; hs=st["hs"]
    # SH must precede HL and trigger within 2-8 sessions after confirmed SH availability.
    prev_h=[i for i in hs if i<hl]
    if not prev_h:return {"pool":False,"reason":"NO_SH"}
    sh=prev_h[-1]
    sessions_since_confirm=(len(df)-1)-(sh+2)
    if not (2<=sessions_since_confirm<=8):
        return {"pool":False,"reason":"SH_AGE","sessions_since_confirm":sessions_since_confirm}
    Aser=atr14(df)
    if Aser is None or pd.isna(Aser.iloc[-2]):return {"pool":False,"reason":"ATR"}
    A=float(Aser.iloc[-2]); anchor=float(df.low.iloc[hl]); SH=float(df.high.iloc[sh])
    # Find later reversal bar whose close > prior high; P is that prior high, after HL is confirmed.
    hl_available=hl+2
    trigger=None
    for i in range(max(hl_available+1,1),len(df)):
        if float(df.close.iloc[i])>float(df.high.iloc[i-1]):
            trigger=i
    if trigger is None:return {"pool":False,"reason":"NO_REVERSAL"}
    P=float(df.high.iloc[trigger-1])
    prelow=float(df.low.iloc[max(hl,trigger-2):trigger+1].min())
    near_hl=abs(prelow-anchor)<=0.5*A
    d=(P-anchor)/A if A>0 else None
    depth=(SH-anchor)/A if A>0 else None
    geom=bool(near_hl and d is not None and depth is not None and 0.30<=d<=1.07 and 2.15<=depth<=4.00)
    return {"pool":geom,"sh_date":df.date.iloc[sh].strftime("%Y-%m-%d"),"hl_date":df.date.iloc[hl].strftime("%Y-%m-%d"),"trigger_date":df.date.iloc[trigger].strftime("%Y-%m-%d"),"P":P,"anchor":anchor,"A":A,"d":d,"depth":depth,"prelow_near_hl":near_hl}

def main():
    st=json.loads(STAGE1.read_text()); rg=json.loads(REGIME.read_text())
    ev=json.loads(EVENTS.read_text()) if EVENTS.exists() else {"confirmed_blocks":{},"unresolved":{}}
    asof=st["asof_et"]
    if rg.get("asof_et")!=asof:
        raise RuntimeError("ASOF_MISMATCH_STAGE1_REGIME")
    event_state_fresh=(ev.get("asof_et")==asof)
    syms=sorted(set(st["weekly_pass"]))
    data={};unknown={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(get_hist,s,asof):s for s in syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e=fut.result()
            if x is None:unknown[s]=e
            else:data[s]=x
    if "QQQ" not in data:
        raise RuntimeError("QQQ_HISTORY_UNKNOWN")
    qqq=data["QQQ"]
    outres={}
    for s in syms:
        x=data.get(s)
        if x is None:
            outres[s]={"status":"UNKNOWN","reason":unknown.get(s)};continue
        rs20=common_rs(x,qqq,20);rs60=common_rs(x,qqq,60)
        mix_pass=bool(rs20 is not None and rs60 is not None and rs20>0 and rs60>0) if rg.get("regime")=="MIXED" else True
        A=family_a(x) if s in st["a_trend_pool"] else {"pool":False,"reason":"NOT_A_STAGE1"}
        B=family_b(x) if s in st["b_tight_base_pool"] else {"pool":False,"reason":"NOT_B_STAGE1"}
        D=family_d(x,rs20,rs60) if s in st["d_drawdown_pool"] else {"pool":False,"reason":"NOT_D_STAGE1"}
        event="UNKNOWN_STALE_EVENT_STATE"
        if event_state_fresh:
            event="CLEAN_DISCOVERY"
            if s in (ev.get("confirmed_blocks") or {}): event="BLOCK_CONFIRMED_8SESSION"
            elif s in (ev.get("unresolved") or {}): event="UNKNOWN"
        outres[s]={"status":"EVALUATED","rs20":rs20,"rs60":rs60,"mixed_rs_pass":mix_pass,"A":A,"B":B,"D":D,"event_status":event}
    a=[s for s,r in outres.items() if r.get("mixed_rs_pass") and r.get("A",{}).get("pool") and r.get("event_status")=="CLEAN_DISCOVERY"]
    b=[s for s,r in outres.items() if r.get("mixed_rs_pass") and r.get("B",{}).get("breakout_confirmed") and r.get("event_status")=="CLEAN_DISCOVERY"]
    b_armed=[s for s,r in outres.items() if r.get("mixed_rs_pass") and r.get("B",{}).get("pool") and not r.get("B",{}).get("breakout_confirmed") and r.get("event_status")=="CLEAN_DISCOVERY"]
    d=[s for s,r in outres.items() if r.get("D",{}).get("dk3_pre_r1") and r.get("event_status")=="CLEAN_DISCOVERY"]
    out={
      "schema":"XRAY_DEEP_PRE_R1_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "regime":rg.get("regime"),"input_weekly_pass_count":len(syms),
      "a_geometry_rs_event_pass_count":len(a),"a_geometry_rs_event_pass":a,
      "b_breakout_rs_event_pass_count":len(b),"b_breakout_rs_event_pass":b,
      "b_armed_rs_event_pass_count":len(b_armed),"b_armed_rs_event_pass":b_armed,
      "d_dk3_pre_r1_count":len(d),"d_dk3_pre_r1":d,
      "unknown_history_count":len(unknown),"unknown_history":unknown,
      "results":outres,
      "remaining_gates":["R1_NEAREST_RESISTANCE","BASIC_SEVERE_RR","EXTENSION_CHASE","OFFICIAL_EVENT_FINALIST_REVIEW","ACCOUNT_GATE","G9","ALIGNED_60M","NON_SYNTHETIC_TARGET"],
      "event_state_fresh":event_state_fresh,
      "authority":"SHADOW_DEEP_PREFILTER_ONLY_NO_SIGNAL"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ["regime","input_weekly_pass_count","a_geometry_rs_event_pass_count","b_breakout_rs_event_pass_count","b_armed_rs_event_pass_count","d_dk3_pre_r1_count","unknown_history_count"]},sort_keys=True))

if __name__=="__main__":
    main()
