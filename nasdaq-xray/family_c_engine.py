#!/usr/bin/env python3
from __future__ import annotations
import json,math,os,hashlib,time,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal
from alpha_semantics import wilder_atr as _policy_atr, apply_split_events

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_FAMILY_C_STAGE1",str(ROOT/"canonical_current_stage1.json")))
EVENTS=Path(os.getenv("XRAY_FAMILY_C_EVENTS",str(ROOT/"canonical_current_event_state.json")))
OUT=Path(os.getenv("XRAY_FAMILY_C_OUT",str(ROOT/"canonical_current_family_c.json")))
TASK="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_FAMILY_C_WORKERS","8"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_FAMILY_C_PROVIDER_MAX_INFLIGHT","3")))
RETRY_DELAYS=(0.0,1.0,2.5)
_PROVIDER_SEM=threading.Semaphore(PROVIDER_MAX_INFLIGHT)
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"
NY=ZoneInfo("America/New_York")

def _retryable(exc):
    s=str(exc).lower()
    return any(x in s for x in ("timed out","timeout","connection reset","remote end closed","too many requests","rate limit","429","500","502","503","504"))

def _call_with_retry(fn):
    last=None
    for delay in RETRY_DELAYS:
        if delay:time.sleep(delay)
        try:
            with _PROVIDER_SEM:return fn()
        except Exception as e:
            last=e
            if not _retryable(e):raise
    assert last is not None
    raise last

def _official_records():
    try:
        j=json.loads(OFFICIAL_IDENTITY_EVIDENCE.read_text())
        if j.get("schema")=="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1" and j.get("evidence_only") is True and j.get("alpha_authority") is False:
            return j.get("records") or {}
    except Exception:pass
    return {}

OFFICIAL_RECORDS=_official_records()

def _normalize_sina(df):
    if df is None or df.empty:return None
    cols={str(c).lower():c for c in df.columns};need=["date","open","high","low","close","volume"]
    if any(k not in cols for k in need):return None
    x=df[[cols[k] for k in need]].copy();x.columns=need
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    for k in need[1:]:x[k]=pd.to_numeric(x[k],errors="coerce")
    return x.dropna().drop_duplicates("date",keep="last").sort_values("date")

def _sina_history(sym):return _normalize_sina(_call_with_retry(lambda:ak.stock_us_daily(symbol=sym,adjust="")))

def load_history(sym,asof):
    cur=_sina_history(sym);rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")=="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
        pred=rec.get("predecessor_symbol");eff=rec.get("effective_date")
        if pred and eff and cur is not None:
            p=_sina_history(pred)
            if p is not None:
                eff_ts=pd.Timestamp(eff);asof_ts=pd.Timestamp(asof)
                cur2=cur[(cur["date"]>=eff_ts)&(cur["date"]<=asof_ts)];pred2=p[p["date"]<eff_ts]
                if not cur2.empty and cur2["date"].dt.date.max().isoformat()==asof:
                    return pd.concat([pred2,cur2],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True),"SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"
    if cur is None:return None,"SINA_EMPTY"
    return cur[cur["date"]<=pd.Timestamp(asof)].reset_index(drop=True),"SINA_US_DAILY"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def hist(sym,asof):
    try:
        x,src=load_history(sym,asof)
        if x is None or x.empty:return sym,None,"EMPTY",None
        last=x["date"].dt.date.max().isoformat()
        if last!=asof:return sym,None,f"ASOF_MISSING:{last}",None
        if len(x)<260:return sym,None,f"LT260:{len(x)}",None
        return sym,x,None,src
    except Exception as e:return sym,None,f"{type(e).__name__}:{str(e)[:160]}",None

def atr_wilder(df,end_idx,n=14):
    if end_idx<1:return None
    s=_policy_atr(df.iloc[:end_idx+1].copy(),n)
    if len(s)==0 or pd.isna(s.iloc[-1]):return None
    a=float(s.iloc[-1])
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
                # First valid trigger wins. A later prettier breakout must not
                # silently replace scenario identity or frozen geometry.
                break
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
    data={};errors={};history_source={} 
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in target}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:errors[s]=e
            else:
                data[s]=x
                history_source[s]=src
    alls=sessions(asof)
    confirmed={};details={};unknown={}
    event_status_map=ev.get("event_status_by_symbol") or {}
    for s in target:
        if s not in data:
            unknown[s]={"reason":"HISTORY_"+errors.get(s,"MISSING")};continue
        strow=(st.get("results") or {}).get(s) or {}
        ca_status=strow.get("corporate_action_status")
        if not str(ca_status).startswith("PASS"):
            unknown[s]={"reason":"CORPORATE_ACTION_NOT_VERIFIED","status":ca_status};continue
        x=data[s]
        split_events=strow.get("split_events") or []
        if split_events:x=apply_split_events(x,split_events)
        x=x.reset_index(drop=True)
        best=None;dd=[]
        for e in fce.get(s) or []:
            g,d=eval_event(s,x,e,asof,alls,event_status_map.get(s,"CLEAN_DISCOVERY"))
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
      "history_source_by_symbol":history_source,
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
    print(json.dumps({"asof":asof,"weekly_scope":len(weekly),"event_symbols":len(target),"confirmed":len(confirmed),"unknown":len(unknown),"provider_max_inflight":PROVIDER_MAX_INFLIGHT,"retry_delays":RETRY_DELAYS},sort_keys=True))
if __name__=="__main__":main()
