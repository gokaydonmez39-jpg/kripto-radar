#!/usr/bin/env python3
"""XRAY deep pre-R1 shadow engine for A/B/D.
Exact policy geometry where supported by shadow daily data.
No signal, no R92 registration, no G9 authority.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os, hashlib, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
import akshare as ak
import pandas as pd

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_STAGE1_STATE", str(ROOT/"stage1_shadow.json")))
REGIME=Path(os.getenv("XRAY_REGIME_STATE", str(ROOT/"regime_breadth_shadow.json")))
EVENTS=Path(os.getenv("XRAY_EVENT_STATE", str(ROOT/"event_official_state.json")))
OUT=Path(os.getenv("XRAY_DEEP_OUT", str(ROOT/"deep_pre_r1_shadow.json")))
GEOMETRY_ONLY=os.getenv("XRAY_DEEP_GEOMETRY_ONLY","0")=="1"
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_DEEP_WORKERS","8"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_DEEP_PROVIDER_MAX_INFLIGHT","3")))
RETRY_DELAYS=(0.0,1.0,2.5)
_PROVIDER_SEM=threading.Semaphore(PROVIDER_MAX_INFLIGHT)
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"

def _retryable(exc):
    s=str(exc).lower()
    return any(x in s for x in ("timed out","timeout","connection reset","remote end closed","too many requests","rate limit","429","500","502","503","504"))

def _call_with_retry(fn):
    last=None
    for delay in RETRY_DELAYS:
        if delay: time.sleep(delay)
        try:
            with _PROVIDER_SEM:
                return fn()
        except Exception as e:
            last=e
            if not _retryable(e): raise
    assert last is not None
    raise last

def _official_records():
    try:
        j=json.loads(OFFICIAL_IDENTITY_EVIDENCE.read_text())
        if j.get("schema")=="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1" and j.get("evidence_only") is True and j.get("alpha_authority") is False:
            return j.get("records") or {}
    except Exception:
        pass
    return {}

OFFICIAL_RECORDS=_official_records()

def _normalize_sina(df):
    if df is None or df.empty:return None
    cols={str(c).lower():c for c in df.columns}
    need=["date","open","high","low","close","volume"]
    if any(k not in cols for k in need):return None
    x=df[[cols[k] for k in need]].copy();x.columns=need
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    for k in need[1:]:x[k]=pd.to_numeric(x[k],errors="coerce")
    return x.dropna().drop_duplicates("date",keep="last").sort_values("date")

def _sina_history(sym):
    return _normalize_sina(_call_with_retry(lambda: ak.stock_us_daily(symbol=sym,adjust="")))

def load_history(sym,asof):
    cur=_sina_history(sym)
    rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")=="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
        pred=rec.get("predecessor_symbol"); eff=rec.get("effective_date")
        if pred and eff and cur is not None:
            p=_sina_history(pred)
            if p is not None:
                eff_ts=pd.Timestamp(eff); asof_ts=pd.Timestamp(asof)
                cur2=cur[(cur["date"]>=eff_ts)&(cur["date"]<=asof_ts)]
                pred2=p[p["date"]<eff_ts]
                if not cur2.empty and cur2["date"].dt.date.max().isoformat()==asof:
                    x=pd.concat([pred2,cur2],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last")
                    return x,"SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"
    if cur is None:return None,"SINA_EMPTY"
    return cur[cur["date"]<=pd.Timestamp(asof)],"SINA_US_DAILY"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def get_hist(sym,asof):
    try:
        x,src=load_history(sym,asof)
        if x is None or x.empty:return sym,None,"EMPTY",None
        last=x["date"].dt.date.max().isoformat()
        if last!=asof:return sym,None,f"ASOF_MISSING:{last}",None
        if len(x)<260:return sym,None,f"LT260:{len(x)}",None
        return sym,x.reset_index(drop=True),None,src
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}",None

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
    st=json.loads(STAGE1.read_text())
    asof=st["asof_et"]
    syms=sorted(set(st["weekly_pass"]))
    state_caps={s:(st.get("state_caps") or {}).get(s,"NORMAL") for s in syms}
    r92_ineligible=set(st.get("r92_ineligible") or [])
    assert st.get("task_id")==TASK_ID and st.get("execution")=="NONE" and st.get("real_money")=="NO-GO"
    rg={"regime":"DEFERRED","asof_et":asof} if GEOMETRY_ONLY else json.loads(REGIME.read_text())
    ev={"confirmed_blocks":{},"unresolved":{},"asof_et":None} if GEOMETRY_ONLY else (json.loads(EVENTS.read_text()) if EVENTS.exists() else {"confirmed_blocks":{},"unresolved":{}})
    if not GEOMETRY_ONLY:
        if rg.get("asof_et")!=asof: raise RuntimeError("ASOF_MISMATCH_STAGE1_REGIME")
        if rg.get("task_id")!=TASK_ID or rg.get("execution")!="NONE" or rg.get("real_money")!="NO-GO":
            raise RuntimeError("REGIME_SAFETY_OR_TASK")
        if ev.get("asof_et")!=asof or ev.get("task_id")!=TASK_ID or ev.get("execution")!="NONE" or ev.get("real_money")!="NO-GO":
            raise RuntimeError("EVENT_SAFETY_TASK_OR_ASOF")
    event_state_fresh=(not GEOMETRY_ONLY and ev.get("asof_et")==asof)
    data={};unknown={};history_source={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(get_hist,s,asof):s for s in syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:unknown[s]=e
            else:
                data[s]=x
                history_source[s]=src
    if "QQQ" not in data:
        raise RuntimeError("QQQ_HISTORY_UNKNOWN")
    qqq=data["QQQ"]
    outres={}
    for s in syms:
        x=data.get(s)
        if x is None:
            outres[s]={"status":"UNKNOWN","reason":unknown.get(s),"state_cap":state_caps.get(s,"NORMAL"),"r92_eligible":s not in r92_ineligible};continue
        rs20=common_rs(x,qqq,20);rs60=common_rs(x,qqq,60)
        mix_pass=True if GEOMETRY_ONLY else (bool(rs20 is not None and rs60 is not None and rs20>0 and rs60>0) if rg.get("regime")=="MIXED" else True)
        A=family_a(x) if s in st["a_trend_pool"] else {"pool":False,"reason":"NOT_A_STAGE1"}
        B=family_b(x) if s in st["b_tight_base_pool"] else {"pool":False,"reason":"NOT_B_STAGE1"}
        D=family_d(x,rs20,rs60) if s in st["d_drawdown_pool"] else {"pool":False,"reason":"NOT_D_STAGE1"}
        event="DEFERRED" if GEOMETRY_ONLY else "UNKNOWN_STALE_EVENT_STATE"
        if event_state_fresh:
            event="CLEAN_DISCOVERY"
            if s in (ev.get("confirmed_blocks") or {}): event="BLOCK_CONFIRMED_8SESSION"
            elif s in (ev.get("unresolved") or {}): event="UNKNOWN"
        outres[s]={"status":"EVALUATED","rs20":rs20,"rs60":rs60,"mixed_rs_pass":mix_pass,"A":A,"B":B,"D":D,"event_status":event,"state_cap":state_caps.get(s,"NORMAL"),"r92_eligible":s not in r92_ineligible}
    a_geom=[s for s,r in outres.items() if r.get("A",{}).get("pool")]
    b_break=[s for s,r in outres.items() if r.get("B",{}).get("breakout_confirmed")]
    b_armed=[s for s,r in outres.items() if r.get("B",{}).get("pool") and not r.get("B",{}).get("breakout_confirmed")]
    d_geom=[s for s,r in outres.items() if r.get("D",{}).get("dk3_pre_r1")]
    if GEOMETRY_ONLY:
        a=a_geom;b=b_break;d=d_geom
    else:
        a=[s for s in a_geom if outres[s].get("mixed_rs_pass") and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        b=[s for s in b_break if outres[s].get("mixed_rs_pass") and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        b_armed=[s for s in b_armed if outres[s].get("mixed_rs_pass") and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        d=[s for s in d_geom if outres[s].get("event_status")=="CLEAN_DISCOVERY"]
    out={
      "schema":"XRAY_DEEP_GEOMETRY_V1" if GEOMETRY_ONLY else "XRAY_DEEP_PRE_R1_SHADOW_V1",
      "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "mode":"GEOMETRY_ONLY_REGIME_EVENT_DEFERRED" if GEOMETRY_ONLY else "FULL_SHADOW",
      "regime":rg.get("regime"),"input_weekly_pass_count":len(syms),
      "a_geometry_count":len(a_geom),"a_geometry":sorted(a_geom),
      "b_breakout_count":len(b_break),"b_breakout":sorted(b_break),
      "b_armed_count":len(b_armed),"b_armed":sorted(b_armed),
      "d_geometry_rs_count":len(d_geom),"d_geometry_rs":sorted(d_geom),
      "a_geometry_rs_event_pass_count":len(a),"a_geometry_rs_event_pass":sorted(a),
      "b_breakout_rs_event_pass_count":len(b),"b_breakout_rs_event_pass":sorted(b),
      "b_armed_rs_event_pass_count":len(b_armed),"b_armed_rs_event_pass":sorted(b_armed),
      "d_dk3_pre_r1_count":len(d),"d_dk3_pre_r1":sorted(d),
      "unknown_history_count":len(unknown),"unknown_history":unknown,
      "history_source_by_symbol":history_source,
      "state_caps":state_caps,"r92_ineligible":sorted(r92_ineligible & set(syms)),
      "source_stage1_path":relpath(STAGE1),"source_stage1_blob_sha":blob_sha(STAGE1),
      "source_regime_path":None if GEOMETRY_ONLY else relpath(REGIME),
      "source_regime_blob_sha":None if GEOMETRY_ONLY else blob_sha(REGIME),
      "source_event_path":None if GEOMETRY_ONLY else relpath(EVENTS),
      "source_event_blob_sha":None if GEOMETRY_ONLY else blob_sha(EVENTS),
      "source_mc_policy_hash":st.get("source_mc_policy_hash"),
      "source_mc_policy_version":st.get("source_mc_policy_version"),
      "results":outres,
      "remaining_gates":["REGIME_BREADTH","R1_NEAREST_RESISTANCE","BASIC_SEVERE_RR","EXTENSION_CHASE","OFFICIAL_EVENT_FINALIST_REVIEW","ACCOUNT_GATE","G9","ALIGNED_60M","NON_SYNTHETIC_TARGET"],
      "event_state_fresh":event_state_fresh,
      "authority":"SHADOW_DEEP_PREFILTER_ONLY_NO_SIGNAL"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"mode":out["mode"],"input_weekly_pass_count":len(syms),"a_geometry_count":len(a_geom),"b_breakout_count":len(b_break),"b_armed_count":len(b_armed),"d_geometry_rs_count":len(d_geom),"unknown_history_count":len(unknown),"provider_max_inflight":PROVIDER_MAX_INFLIGHT,"retry_delays":RETRY_DELAYS},sort_keys=True))

if __name__=="__main__":
    main()
