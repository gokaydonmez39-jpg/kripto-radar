#!/usr/bin/env python3
from __future__ import annotations
import json,math,os,hashlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_FAMILY_C_STAGE1",str(ROOT/"canonical_current_stage1.json")))
EVENTS=Path(os.getenv("XRAY_FAMILY_C_EVENTS",str(ROOT/"canonical_current_event_state.json")))
OUT=Path(os.getenv("XRAY_FAMILY_C_OUT",str(ROOT/"canonical_current_family_c.json")))
TASK="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_FAMILY_C_WORKERS","8"))
NY=ZoneInfo("America/New_York")

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def hist(sym,asof):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:return sym,None,"EMPTY"
        cols={c.lower():c for c in df.columns}
        need=["date","open","high","low","close","volume"]
        if any(k not in cols for k in need):return sym,None,"COLUMNS"
        x=df[[cols[k] for k in need]].copy();x.columns=need
        x["date"]=pd.to_datetime(x["date"],errors="coerce")
        for k in need[1:]:x[k]=pd.to_numeric(x[k],errors="coerce")
        x=x.dropna().drop_duplicates("date",keep="last").sort_values("date")
        x=x[x["date"]<=pd.Timestamp(asof)].reset_index(drop=True)
        if len(x)<260:return sym,None,f"LT260:{len(x)}"
        return sym,x,None
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}"

def atr_wilder(df,end_idx,n=14):
    if end_idx< n:return None
    z=df.iloc[:end_idx+1]
    h=z.high.astype(float);l=z.low.astype(float);c=z.close.astype(float)
    pc=c.shift(1)
    tr=pd.concat([(h-l).abs(),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1).to_list()
    if len(tr)<n:return None
    a=sum(tr[:n])/n
    for v in tr[n:]:a=((n-1)*a+v)/n
    return a if math.isfinite(a) and a>0 else None

def rvol20_at(df,idx):
    if idx<20:return None
    prev=[float(v) for v in df.volume.iloc[idx-20:idx] if float(v)>=0 and math.isfinite(float(v))]
    if len(prev)!=20:return None
    med=median(prev)
    if med<=0:return None
    return float(df.volume.iloc[idx])/med

def sessions(asof):
    cal=mcal.get_calendar("NASDAQ")
    sched=cal.schedule(start_date="2020-01-01",end_date=asof)
    return [x.date().isoformat() for x in sched.index]

def parse_event_dt(e):
    raw=e.get("event_datetime_et") or e.get("event_datetime_utc") or e.get("event_datetime")
    if not raw:return None
    try:
        d=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        if d.tzinfo is None:return None
        return d.astimezone(NY)
    except Exception:return None

def reaction_session(event_et,all_sessions):
    d=event_et.date().isoformat()
    hhmm=event_et.hour*60+event_et.minute
    if hhmm<9*60+30:
        for s in all_sessions:
            if s>=d:return s,"BMO"
    elif hhmm>=16*60:
        for s in all_sessions:
            if s>d:return s,"AMC"
    else:
        return None,"RTH_OR_AMBIGUOUS"
    return None,"NO_NEXT_SESSION"

def eval_event(sym,df,e,asof,all_sessions,event_status):
    edt=parse_event_dt(e)
    if edt is None:return None,{"reason":"EVENT_TIME_UNPARSEABLE"}
    rs,mode=reaction_session(edt,all_sessions)
    if rs is None:return None,{"reason":"REACTION_SESSION_AMBIGUOUS","mode":mode}
    date_to_idx={d.date().isoformat():i for i,d in enumerate(df.date)}
    if rs not in date_to_idx:return None,{"reason":"REACTION_BAR_MISSING","reaction_session":rs}
    r0=date_to_idx[rs]
    if r0<21:return None,{"reason":"PRE_EVENT_HISTORY_LT21"}
    if r0+2>=len(df):return None,{"reason":"REACTION_0_1_2_INCOMPLETE","reaction_session":rs}
    pre=r0-1
    A=atr_wilder(df,pre,14)
    if A is None:return None,{"reason":"ATR_PRE_EVENT_MISSING"}
    pre_close=float(df.close.iloc[pre]);open0=float(df.open.iloc[r0])
    gap_atr=(open0-pre_close)/A
    rv0=rvol20_at(df,r0)
    lows=[float(df.low.iloc[i]) for i in [r0,r0+1,r0+2]]
    reaction_ok=bool(gap_atr>=0.50 and rv0 is not None and rv0>=1.5 and min(lows)>pre_close)
    base_start=r0+3
    latest=min(r0+10,len(df)-1)
    confirmed=None
    if reaction_ok:
        # At least three completed consolidation bars after reaction0+1+2.
        for t in range(base_start+3,latest+1):
            base=df.iloc[base_start:t]
            if len(base)<3:continue
            P=float(base.high.max());anchor=float(base.low.min())
            width=(P-anchor)/A
            rv=rvol20_at(df,t)
            close=float(df.close.iloc[t])
            if 0.30<=width<=2.05 and close>P and rv is not None and rv>=1.5:
                confirmed={
                  "confirmed":True,"A":A,"P":P,"anchor":anchor,
                  "event_status":event_status,
                  "event_datetime_et":edt.isoformat(),"reaction_mode":mode,
                  "reaction_session":rs,"pre_event_close":pre_close,
                  "gap_atr":gap_atr,"reaction_rvol20":rv0,
                  "reaction_lows":lows,"consolidation_bars":len(base),
                  "base_width_atr":width,
                  "breakout_session":df.date.iloc[t].date().isoformat(),
                  "breakout_close":close,"breakout_rvol20":rv,
                  "sessions_from_reaction":t-r0,
                  "official_source_url":e.get("official_source_url"),
                  "event_source":e.get("source") or e.get("official_source"),
                  "authority":"C4_10_FAMILY_C_CONSERVATIVE_FAIL_CLOSED"
                }
    detail={
      "event_datetime_et":edt.isoformat(),"reaction_mode":mode,"reaction_session":rs,
      "pre_event_close":pre_close,"A":A,"gap_atr":gap_atr,"reaction_rvol20":rv0,
      "reaction_lows":lows,"reaction_ok":reaction_ok,
      "confirmed":bool(confirmed)
    }
    return confirmed,detail

def main():
    st=json.loads(STAGE1.read_text());ev=json.loads(EVENTS.read_text())
    asof=st["asof_et"]
    assert st["task_id"]==ev["task_id"]==TASK and ev["asof_et"]==asof
    assert st["execution"]==ev["execution"]=="NONE" and st["real_money"]==ev["real_money"]=="NO-GO"
    weekly=sorted(st.get("weekly_pass") or [])
    fce=ev.get("family_c_events") or {}
    target=sorted(set(weekly)&set(fce))
    data={};errors={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in target}
        for fut in as_completed(futs):
            s,x,e=fut.result()
            if x is None:errors[s]=e
            else:data[s]=x
    alls=sessions(asof)
    confirmed={};details={};unknown={}
    event_status_map=ev.get("event_status_by_symbol") or {}
    for s in target:
        if s not in data:
            unknown[s]={"reason":"HISTORY_"+errors.get(s,"MISSING")};continue
        best=None;dd=[]
        for e in fce.get(s) or []:
            g,d=eval_event(s,data[s],e,asof,alls,event_status_map.get(s,"CLEAN_DISCOVERY"))
            dd.append(d)
            if g is not None:
                if best is None or g["breakout_session"]>best["breakout_session"]:best=g
        details[s]=dd
        if best:confirmed[s]=best
    out={
      "schema":"XRAY_FAMILY_C_ENGINE_V1","task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "weekly_scope_count":len(weekly),"event_symbol_count":len(target),
      "confirmed_count":len(confirmed),"confirmed":dict(sorted(confirmed.items())),
      "unknown_count":len(unknown),"unknown":dict(sorted(unknown.items())),
      "details":dict(sorted(details.items())),
      "source_stage1_path":relpath(STAGE1),"source_stage1_blob_sha":blob_sha(STAGE1),
      "source_event_path":relpath(EVENTS),"source_event_blob_sha":blob_sha(EVENTS),
      "source_compiled_policy_hash":ev.get("compiled_policy_hash"),
      "source_compiled_policy_version":ev.get("compiled_policy_version"),
      "policy":{
        "reaction":"BMO same RTH; AMC next RTH",
        "gap_atr_min":0.50,"reaction_rvol20_min":1.5,
        "reaction_0_1_2_lows_above_pre_event_close":True,
        "min_consolidation_bars":3,"base_atr":[0.30,2.05],
        "breakout_rvol20_min":1.5,"breakout_within_sessions":10
      },
      "authority":"C4_11_POST_EARNINGS_FAIL_CLOSED_POLICY_INHERITED"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"weekly_scope":len(weekly),"event_symbols":len(target),"confirmed":len(confirmed),"unknown":len(unknown)},sort_keys=True))
if __name__=="__main__":main()
