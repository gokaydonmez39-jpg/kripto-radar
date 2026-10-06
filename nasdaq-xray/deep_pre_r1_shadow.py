#!/usr/bin/env python3
"""XRAY deep pre-R1 shadow engine for A/B/D.
Exact policy geometry where supported by shadow daily data.
No signal, no R92 registration, no G9 authority.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os, hashlib, time, threading, socket
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
import akshare as ak
import pandas as pd
from alpha_semantics import (
    wilder_atr as _policy_atr,
    ema_seeded,
    strict_swings as _policy_swings,
    drawdown_metrics,
    tight_base_at,
    find_recent_b_trigger,
    NEW_TRIGGER_DISCOVERY_MAX_AGE,
    mechanical_scale_breaks,
    mechanical_split_suspects,
    split_consistent_history,
    apply_split_events,
    family_a_pretrigger_low,
    trend_pullback_stage1_at,
    history_fingerprint,
)

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
HTTP_TIMEOUT_SECONDS=max(5.0,float(os.getenv("XRAY_DEEP_HTTP_TIMEOUT_SECONDS","20")))
socket.setdefaulttimeout(HTTP_TIMEOUT_SECONDS)
if not getattr(requests.sessions.Session.request,"_xray_deep_bounded_timeout",False):
    _XRAY_DEEP_ORIGINAL_SESSION_REQUEST=requests.sessions.Session.request
    def _xray_deep_bounded_session_request(self,*args,**kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"]=HTTP_TIMEOUT_SECONDS
        return _XRAY_DEEP_ORIGINAL_SESSION_REQUEST(self,*args,**kwargs)
    _xray_deep_bounded_session_request._xray_deep_bounded_timeout=True
    requests.sessions.Session.request=_xray_deep_bounded_session_request
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"
HISTORY_CACHE_DIR=os.getenv("XRAY_DEEP_HISTORY_CACHE_DIR")
HISTORY_CACHE_REQUIRED=os.getenv("XRAY_DEEP_CACHE_REQUIRED","0")=="1"
HISTORY_BINDING_ENV=os.getenv("XRAY_DEEP_HISTORY_BINDING_STATE")
HISTORY_BINDING=Path(HISTORY_BINDING_ENV) if HISTORY_BINDING_ENV else None
HISTORY_BINDING_REQUIRED=os.getenv("XRAY_DEEP_HISTORY_BINDING_REQUIRED","0")=="1"
PREV_FINAL=Path(os.getenv("XRAY_DEEP_PREV_FINAL",str(ROOT/"canonical_current_final_tech.json")))
LIFECYCLE=Path(os.getenv("XRAY_DEEP_LIFECYCLE_REGISTRY",str(ROOT/"canonical_candidate_lifecycle_registry.json")))
LIFECYCLE_ACTIVE_STATES={
    "WATCH_RETEST_REQUIRED","WATCH_RECONFIRMATION_REQUIRED",
    "WATCH_CHASE_RETEST_REQUIRED","WATCH_EXTENSION_RESET_REQUIRED",
    "WATCH_REGIME_REVALIDATION_REQUIRED","WATCH_REGIME_UNKNOWN",
    "PRE_G9_TECH_PASS","WATCH_EVENT_UNKNOWN_OR_BLOCKED","WATCH_MC_FALLBACK_CAP",
}

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

def _history_cache_path(sym):
    if not HISTORY_CACHE_DIR:return None
    return Path(HISTORY_CACHE_DIR)/(hashlib.sha256(sym.encode()).hexdigest()+".csv.gz")

def _cached_sina_history(sym,asof,require_asof=True):
    p=_history_cache_path(sym)
    if p is None or not p.exists():return None
    try:
        x=_normalize_sina(pd.read_csv(p,compression="gzip"))
        if x is None or x.empty:return None
        x=x[x["date"]<=pd.Timestamp(asof)].reset_index(drop=True)
        if x.empty:return None
        if require_asof and x["date"].dt.date.max().isoformat()!=asof:return None
        return x
    except Exception:return None

def _sina_history(sym):
    return _normalize_sina(_call_with_retry(lambda: ak.stock_us_daily(symbol=sym,adjust="")))

def load_history(sym,asof):
    cur=_cached_sina_history(sym,asof)
    if cur is None and HISTORY_CACHE_REQUIRED:
        return None,"SINA_SAME_RUN_CACHE_MISSING"
    if cur is None:cur=_sina_history(sym)
    rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")=="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
        pred=rec.get("predecessor_symbol"); eff=rec.get("effective_date")
        if pred and eff and cur is not None:
            p=_cached_sina_history(pred,asof,require_asof=False)
            if p is None and HISTORY_CACHE_REQUIRED:
                return None,"SINA_PREDECESSOR_SAME_RUN_CACHE_MISSING"
            if p is None:p=_sina_history(pred)
            if p is not None:
                eff_ts=pd.Timestamp(eff); asof_ts=pd.Timestamp(asof)
                cur2=cur[(cur["date"]>=eff_ts)&(cur["date"]<=asof_ts)]
                pred2=p[p["date"]<eff_ts]
                if not cur2.empty and cur2["date"].dt.date.max().isoformat()==asof:
                    x=pd.concat([pred2,cur2],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last")
                    return x.reset_index(drop=True),"SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"
    if cur is None:return None,"SINA_EMPTY"
    return cur[cur["date"]<=pd.Timestamp(asof)].reset_index(drop=True),"SINA_US_DAILY"

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
    return _policy_atr(df,14)

def strict_swings(df):
    return _policy_swings(df)

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

def family_b(df,eligible_trigger_dates=None):
    # New triggers are discovered only in the current/prior three completed sessions.
    # The five-session retest window applies only after durable discovery/registration.
    # Weekly-at-trigger eligibility participates in trigger selection so an earlier
    # weekly-fail breakout cannot mask a later weekly-pass breakout.
    recent=find_recent_b_trigger(df,NEW_TRIGGER_DISCOVERY_MAX_AGE,eligible_trigger_dates)
    if recent:
        return {"pool":True,**recent}
    # No recent trigger: current completed bar may still define an ARMED base.
    t=len(df)-1
    g=tight_base_at(df,t)
    if not g:return {"pool":False}
    return {"pool":True,**g,"breakout_confirmed":False,"trigger_date":None}

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
    prior_h=[i for i in hs if i<hl]
    later_h=[i for i in hs if i>hl]
    return {"hl":hl,"prior_hs":prior_h,"later_hs":later_h,"hs":hs,"ls":ls}

def family_d(df,qqq,eligible_trigger_dates=None):
    # Evaluate the earliest valid reclaim in today/prior three completed sessions.
    # The five-session retest lifecycle is reserved for already-recorded setups.
    # Every structural/RS/ATR input is sliced at the candidate trigger, preventing
    # current-day look-ahead from manufacturing or replacing a historical trigger.
    allowed=None if eligible_trigger_dates is None else set(str(x) for x in eligible_trigger_dates)
    last_idx=len(df)-1
    diagnostic=None
    for t in range(max(0,last_idx-NEW_TRIGGER_DISCOVERY_MAX_AGE),last_idx+1):
        td=df.date.iloc[t].date().isoformat()
        if allowed is not None and td not in allowed:continue
        x=df.iloc[:t+1].reset_index(drop=True)
        q=qqq[qqq.date<=x.date.iloc[-1]].reset_index(drop=True)
        st=active_hl_and_sh(x)
        if not st:continue
        hl=st["hl"];prior=st["prior_hs"]
        if not prior:continue
        # A strict 5-bar swing low centered at hl is only confirmed at hl+2
        # close. The reclaim trigger must occur AFTER that availability point;
        # the confirmation bar itself cannot retroactively use the new HL.
        if t<hl+3:continue
        sh=prior[-1];P=float(x.high.iloc[sh]);anchor=float(x.low.iloc[hl])
        Aser=atr14(x)
        if Aser is None or t<1 or pd.isna(Aser.iloc[-2]):continue
        A=float(Aser.iloc[-2]);d=(P-anchor)/A if A>0 else None
        cc=x.close.astype(float);close=float(cc.iloc[-1])
        ema50s=ema_seeded(cc,50)
        if pd.isna(ema50s.iloc[-1]):continue
        ema50=float(ema50s.iloc[-1]);rv=rvol20(x)
        rs20=common_rs(x,q,20);rs60=common_rs(x,q,60)
        dd=drawdown_metrics(x);dd252=dd["current_drawdown_252"];dd120=dd["max_drawdown_close_120"]
        pool=bool(dd252<=-0.15 or dd120<=-0.20)
        g={"pool":pool,"hl_date":x.date.iloc[hl].strftime("%Y-%m-%d"),"P":P,"anchor":anchor,
           "A":A,"d":d,"close":close,"ema50":ema50,"rs20":rs20,"rs60":rs60,"rvol20":rv,
           "dd252":dd252,"dd120":dd120,"dd252_definition":"CURRENT_CLOSE_VS_MAX_HIGH_252",
           "dd120_definition":"MAX_DRAWDOWN_CLOSE_120","trigger_date":td,
           "trigger_age_sessions":last_idx-t}
        diagnostic=g
        reclaim=bool(pool and d is not None and 0.30<=d<=2.05 and close>P and close>ema50
                     and rs20 is not None and rs60 is not None and rs20>0 and rs60>0
                     and rv is not None and rv>=1.2)
        if reclaim:
            g["dk3_pre_r1"]=True
            return g
    if diagnostic is not None:
        diagnostic["dk3_pre_r1"]=False
        diagnostic["trigger_date"]=None
        return diagnostic
    return {"pool":False,"reason":"NO_RECENT_VALID_D_STRUCTURE","dk3_pre_r1":False,"trigger_date":None}

def _family_a_at_trigger(df,t):
    """Evaluate A using only information available through candidate trigger t."""
    if t<=0 or t>=len(df):return {"pool":False,"reason":"A_TRIGGER_INDEX"}
    x=df.iloc[:t+1].reset_index(drop=True)
    st=active_hl_and_sh(x)
    if not st:return {"pool":False,"reason":"NO_ACTIVE_HL"}
    hl=st["hl"];prev_h=[i for i in st["hs"] if i<hl]
    if not prev_h:return {"pool":False,"reason":"NO_SH"}
    sh=prev_h[-1]
    sessions_since_confirm=t-(sh+2)
    if sessions_since_confirm<2 or sessions_since_confirm>8:
        return {"pool":False,"reason":"SH_AGE","sessions_since_confirm":sessions_since_confirm}
    if t<hl+3:
        return {"pool":False,"reason":"HL_NOT_CONFIRMED_BEFORE_REVERSAL","sessions_since_confirm":sessions_since_confirm}
    if float(x.close.iloc[t])<=float(x.high.iloc[t-1]):
        return {"pool":False,"reason":"NO_REVERSAL","sessions_since_confirm":sessions_since_confirm}
    if not trend_pullback_stage1_at(x,t):
        return {"pool":False,"reason":"A_STAGE1_AT_TRIGGER_FAIL",
                "trigger_date":x.date.iloc[t].strftime("%Y-%m-%d"),
                "sessions_since_confirm":sessions_since_confirm}
    Aser=atr14(x)
    if Aser is None or pd.isna(Aser.iloc[t-1]):return {"pool":False,"reason":"ATR"}
    A=float(Aser.iloc[t-1]);anchor=float(x.low.iloc[hl]);SH=float(x.high.iloc[sh])
    P=float(x.high.iloc[t-1]);prelow=family_a_pretrigger_low(x,t)
    near_hl=abs(prelow-anchor)<=0.5*A
    d=(P-anchor)/A if A>0 else None;depth=(SH-anchor)/A if A>0 else None
    geom=bool(near_hl and d is not None and depth is not None
              and 0.30<=d<=1.07 and 2.15<=depth<=4.00)
    return {"pool":geom,"sh_date":x.date.iloc[sh].strftime("%Y-%m-%d"),
            "hl_date":x.date.iloc[hl].strftime("%Y-%m-%d"),
            "trigger_date":x.date.iloc[t].strftime("%Y-%m-%d"),
            "sessions_since_confirm":sessions_since_confirm,
            "P":P,"anchor":anchor,"A":A,"d":d,"depth":depth,"prelow_near_hl":near_hl}

def family_a(df,eligible_trigger_dates=None):
    # Reconstruct missed A triggers inside the five-session retest window using
    # trigger-time structure. A newer HL formed after an old trigger must not
    # erase a still-valid frozen setup that was not recorded because of an outage.
    if df.empty:return {"pool":False,"reason":"EMPTY"}
    allowed=None if eligible_trigger_dates is None else set(str(x) for x in eligible_trigger_dates)
    last=len(df)-1;diagnostic=None
    for t in range(max(1,last-5),last+1):
        td=df.date.iloc[t].date().isoformat()
        if allowed is not None and td not in allowed:continue
        g=_family_a_at_trigger(df,t);diagnostic=g
        if g.get("pool"):
            g["trigger_age_sessions"]=last-t
            return g
    return diagnostic or {"pool":False,"reason":"NO_RECENT_VALID_A_STRUCTURE"}

def evaluate_recent_families(df,qqq,eligible_trigger_dates=None):
    """Exact A/B/D evaluation in the five-session retest horizon, weekly-at-trigger aware."""
    return (family_a(df,eligible_trigger_dates),
            family_b(df,eligible_trigger_dates),
            family_d(df,qqq,eligible_trigger_dates))

def _lifecycle_scope(asof):
    """Carry active prospective setups across later official sessions.

    Same-ASOF equality is intentionally NOT required: lifecycle horizon is 2-8
    sessions and must survive into later ASOFs. A future-dated registry is never
    accepted. Valid sidecar state overrides the embedded prior-Final copy.
    """
    chosen=None
    try:
        if PREV_FINAL.exists():
            f=json.loads(PREV_FINAL.read_text())
            lr=f.get("lifecycle_registry") or {}
            fa=str(f.get("asof_et") or "")
            if (fa and fa<=asof
                and lr.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
                and lr.get("execution")=="NONE" and lr.get("real_money")=="NO-GO"
                and isinstance(lr.get("records"),dict)):
                chosen=lr
        if LIFECYCLE.exists():
            lr=json.loads(LIFECYCLE.read_text())
            la=str(lr.get("asof_et") or "")
            if (la and la<=asof
                and lr.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
                and lr.get("execution")=="NONE" and lr.get("real_money")=="NO-GO"
                and isinstance(lr.get("records"),dict)):
                chosen=lr
            else:
                return []
        if not chosen:return []
        return sorted(set(
            str(rec.get("symbol")) for rec in (chosen.get("records") or {}).values()
            if rec.get("symbol") and str(rec.get("state") or "") in LIFECYCLE_ACTIVE_STATES
            and str(rec.get("last_asof") or chosen.get("asof_et") or "")<=asof
        ))
    except Exception:
        return []

def _regime_finalist_metrics(x,qqq,regime_name):
    rs20=common_rs(x,qqq,20);rs60=common_rs(x,qqq,60)
    regime_name=str(regime_name or "UNKNOWN")
    if regime_name not in {"STRONG","MIXED","WEAK"}:
        status="UNKNOWN"
    elif regime_name=="MIXED":
        if rs20 is None or rs60 is None:
            status="UNKNOWN"
        else:
            status="PASS" if rs20>0 and rs60>0 else "FAIL"
    else:
        status="PASS"
    return rs20,rs60,status

def main():
    st=json.loads(STAGE1.read_text())
    asof=st["asof_et"]
    history_binding={}
    if HISTORY_BINDING is not None:
        if not HISTORY_BINDING.exists():
            if HISTORY_BINDING_REQUIRED:raise RuntimeError("DEEP_HISTORY_BINDING_MISSING")
        else:
            hb=json.loads(HISTORY_BINDING.read_text())
            if hb.get("asof_et")!=asof or hb.get("execution")!="NONE" or hb.get("real_money")!="NO-GO":
                raise RuntimeError("DEEP_HISTORY_BINDING_SAFETY_OR_ASOF_MISMATCH")
            history_binding=hb.get("history_fingerprint_by_symbol") or {}
    current_weekly=sorted(set(st["weekly_pass"]))
    syms=sorted(set(st.get("recent_weekly_scope") or current_weekly))
    lifecycle_scope=_lifecycle_scope(asof)
    history_syms=sorted(set(syms)|set(lifecycle_scope))
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
    data={};unknown={};history_source={};history_fps={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(get_hist,s,asof):s for s in history_syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:unknown[s]=e
            else:
                fp=history_fingerprint(x,asof)
                exp=history_binding.get(s)
                if exp is not None and fp!=exp:
                    unknown[s]="HISTORY_FINGERPRINT_MISMATCH"
                    continue
                if HISTORY_BINDING_REQUIRED and s!="QQQ" and exp is None:
                    unknown[s]="HISTORY_FINGERPRINT_BINDING_MISSING"
                    continue
                data[s]=x
                history_source[s]=src
                history_fps[s]=fp
    if "QQQ" not in data:
        raise RuntimeError("QQQ_HISTORY_UNKNOWN:"+str(unknown.get("QQQ")))
    if HISTORY_BINDING_REQUIRED:
        qexp=(json.loads(HISTORY_BINDING.read_text()).get("qqq_history_fingerprint") if HISTORY_BINDING is not None and HISTORY_BINDING.exists() else None)
        if qexp is None or history_fps.get("QQQ")!=qexp:
            raise RuntimeError("QQQ_HISTORY_FINGERPRINT_BINDING_MISMATCH")
    qqq=data["QQQ"].reset_index(drop=True)
    qqq_scale_breaks=mechanical_scale_breaks(qqq,260)
    qqq_split_suspects=mechanical_split_suspects(qqq,260)
    qqq_ca_status="PASS_NO_LOCAL_SPLIT_DISCONTINUITY"
    qqq_split_events=[]
    if qqq_scale_breaks or qqq_split_suspects:
        qqq,qqq_ca_status,qqq_split_events=split_consistent_history("QQQ",qqq)
        if not str(qqq_ca_status).startswith("PASS"):
            raise RuntimeError("QQQ_CORPORATE_ACTION_UNKNOWN:"+str(qqq_ca_status))
        qqq=qqq.reset_index(drop=True)
    outres={}
    for s in syms:
        x=data.get(s)
        if x is None:
            outres[s]={"status":"UNKNOWN","reason":unknown.get(s),"state_cap":state_caps.get(s,"NORMAL"),"r92_eligible":s not in r92_ineligible};continue
        strow=(st.get("results") or {}).get(s) or {}
        ca_status=strow.get("corporate_action_status")
        split_events=strow.get("split_events") or []
        if not str(ca_status).startswith("PASS"):
            outres[s]={"status":"UNKNOWN","reason":"CORPORATE_ACTION_NOT_VERIFIED",
                       "corporate_action_status":ca_status,"state_cap":state_caps.get(s,"NORMAL"),
                       "r92_eligible":s not in r92_ineligible};continue
        if split_events:
            x=apply_split_events(x,split_events)
        x=x.reset_index(drop=True)
        regime_name=str(rg.get("regime") or "UNKNOWN")
        if GEOMETRY_ONLY:
            rs20=common_rs(x,qqq,20);rs60=common_rs(x,qqq,60)
            mix_pass=True
            regime_finalist_status="DEFERRED"
            regime_finalist_pass=None
        else:
            rs20,rs60,regime_finalist_status=_regime_finalist_metrics(x,qqq,regime_name)
            mix_pass=(regime_finalist_status=="PASS")
            regime_finalist_pass=(regime_finalist_status=="PASS")
        # Exact recent-trigger evaluation must not depend on today's cheap Stage1
        # snapshot pool. A/B/D re-check their mandatory conditions at the actual
        # candidate trigger; this preserves valid triggers from the prior 3 sessions.
        weekly_dates=set(strow.get("recent_weekly_pass_dates") or [])
        A,B,D=evaluate_recent_families(x,qqq,weekly_dates)
        def bind_weekly(g,flag):
            if not isinstance(g,dict): return
            td=str(g.get("trigger_date") or "")
            if flag and td and td not in weekly_dates:
                g[flag]=False
                g["reason"]="WEEKLY_AT_TRIGGER_FAIL"
                g["weekly_pass_at_trigger"]=False
            elif flag and td:
                g["weekly_pass_at_trigger"]=True
        bind_weekly(A,"pool")
        bind_weekly(B,"breakout_confirmed")
        bind_weekly(D,"dk3_pre_r1")
        # An ARMED B has no trigger yet; it exists only if the current ASOF itself
        # has weekly support. A historical weekly-pass day cannot manufacture a
        # new current ARMED state.
        if isinstance(B,dict) and B.get("pool") and not B.get("breakout_confirmed") and asof not in weekly_dates:
            B["pool"]=False; B["reason"]="CURRENT_WEEKLY_FAIL_FOR_ARMED"
        event="DEFERRED" if GEOMETRY_ONLY else "UNKNOWN_STALE_EVENT_STATE"
        if event_state_fresh:
            event="CLEAN_DISCOVERY"
            if s in (ev.get("confirmed_blocks") or {}): event="BLOCK_CONFIRMED_8SESSION"
            elif s in (ev.get("unresolved") or {}): event="UNKNOWN"
        outres[s]={"status":"EVALUATED","rs20":rs20,"rs60":rs60,"mixed_rs_pass":mix_pass,
                   "regime_finalist_status":regime_finalist_status,
                   "regime_finalist_pass":regime_finalist_pass,
                   "A":A,"B":B,"D":D,"event_status":event,
                   "mechanical_scale_breaks":mechanical_scale_breaks(x,260),
                   "corporate_action_status":ca_status,"split_events":split_events,
                   "state_cap":state_caps.get(s,"NORMAL"),"r92_eligible":s not in r92_ineligible}
    lifecycle_revalidation={}
    if not GEOMETRY_ONLY:
        event_map=ev.get("event_status_by_symbol") or {}
        for s in lifecycle_scope:
            if s in outres:
                rr=outres[s]
                lifecycle_revalidation[s]={
                  "status":"PASS" if rr.get("regime_finalist_status")=="PASS" else rr.get("regime_finalist_status","UNKNOWN"),
                  "regime_finalist_status":rr.get("regime_finalist_status","UNKNOWN"),
                  "regime_finalist_pass":rr.get("regime_finalist_pass") is True,
                  "rs20":rr.get("rs20"),"rs60":rr.get("rs60"),"event_status":rr.get("event_status"),
                }
                continue
            x=data.get(s)
            strow=(st.get("results") or {}).get(s) or {}
            ca_status=strow.get("corporate_action_status")
            if x is None:
                lifecycle_revalidation[s]={"status":"UNKNOWN","reason":"HISTORY_"+str(unknown.get(s,"MISSING")),
                                           "regime_finalist_status":"UNKNOWN","regime_finalist_pass":False}
                continue
            if not str(ca_status).startswith("PASS"):
                lifecycle_revalidation[s]={"status":"UNKNOWN","reason":"CORPORATE_ACTION_NOT_VERIFIED",
                                           "corporate_action_status":ca_status,
                                           "regime_finalist_status":"UNKNOWN","regime_finalist_pass":False}
                continue
            split_events=strow.get("split_events") or []
            if split_events:x=apply_split_events(x,split_events)
            x=x.reset_index(drop=True)
            rs20,rs60,rf_status=_regime_finalist_metrics(x,qqq,rg.get("regime"))
            lifecycle_revalidation[s]={
              "status":rf_status,"regime_finalist_status":rf_status,
              "regime_finalist_pass":rf_status=="PASS","rs20":rs20,"rs60":rs60,
              "event_status":event_map.get(s,"UNKNOWN"),
            }

    a_geom=[s for s,r in outres.items() if r.get("A",{}).get("pool")]
    b_break=[s for s,r in outres.items() if r.get("B",{}).get("breakout_confirmed")]
    b_armed=[s for s,r in outres.items() if r.get("B",{}).get("pool") and not r.get("B",{}).get("breakout_confirmed")]
    d_geom=[s for s,r in outres.items() if r.get("D",{}).get("dk3_pre_r1")]
    if GEOMETRY_ONLY:
        a=a_geom;b=b_break;d=d_geom
    else:
        a=[s for s in a_geom if outres[s].get("regime_finalist_pass") is True and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        b=[s for s in b_break if outres[s].get("regime_finalist_pass") is True and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        b_armed=[s for s in b_armed if outres[s].get("regime_finalist_pass") is True and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
        d=[s for s in d_geom if outres[s].get("regime_finalist_pass") is True and outres[s].get("event_status")=="CLEAN_DISCOVERY"]
    out={
      "schema":"XRAY_DEEP_GEOMETRY_V1" if GEOMETRY_ONLY else "XRAY_DEEP_PRE_R1_SHADOW_V1",
      "task_id":TASK_ID,"asof_et":asof,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "mode":"GEOMETRY_ONLY_REGIME_EVENT_DEFERRED" if GEOMETRY_ONLY else "FULL_SHADOW",
      "regime":rg.get("regime"),
      "input_weekly_pass_count":len(current_weekly),
      "input_weekly_trigger_scope_count":len(syms),
      "weekly_trigger_scope":syms,
      "a_geometry_count":len(a_geom),"a_geometry":sorted(a_geom),
      "b_breakout_count":len(b_break),"b_breakout":sorted(b_break),
      "b_armed_count":len(b_armed),"b_armed":sorted(b_armed),
      "d_geometry_rs_count":len(d_geom),"d_geometry_rs":sorted(d_geom),
      "a_geometry_rs_event_pass_count":len(a),"a_geometry_rs_event_pass":sorted(a),
      "b_breakout_rs_event_pass_count":len(b),"b_breakout_rs_event_pass":sorted(b),
      "b_armed_rs_event_pass_count":len(b_armed),"b_armed_rs_event_pass":sorted(b_armed),
      "d_dk3_pre_r1_count":len(d),"d_dk3_pre_r1":sorted(d),
      "lifecycle_revalidation_scope":lifecycle_scope,
      "lifecycle_revalidation_scope_count":len(lifecycle_scope),
      "lifecycle_revalidation":dict(sorted(lifecycle_revalidation.items())),
      "unknown_history_count":len(unknown),"unknown_history":unknown,
      "history_source_by_symbol":history_source,
      "history_fingerprint_by_symbol":{k:v for k,v in history_fps.items() if k!="QQQ"},
      "qqq_history_fingerprint":history_fps.get("QQQ"),
      "history_fingerprint_semantics":"RAW_OR_OFFICIAL_COMPOSITE_ASOF_TAIL320_V1",
      "qqq_corporate_action_status":qqq_ca_status,"qqq_split_events":qqq_split_events,
      "state_caps":state_caps,"r92_ineligible":sorted(r92_ineligible & set(syms)),
      "source_stage1_path":relpath(STAGE1),"source_stage1_blob_sha":blob_sha(STAGE1),
      "source_regime_path":None if GEOMETRY_ONLY else relpath(REGIME),
      "source_regime_blob_sha":None if GEOMETRY_ONLY else blob_sha(REGIME),
      "source_event_path":None if GEOMETRY_ONLY else relpath(EVENTS),
      "source_event_blob_sha":None if GEOMETRY_ONLY else blob_sha(EVENTS),
      "source_mc_policy_hash":st.get("source_mc_policy_hash"),
      "source_mc_policy_version":st.get("source_mc_policy_version"),
      "results":outres,
      "remaining_gates":["REGIME_BREADTH","R1_NEAREST_RESISTANCE","BASIC_SEVERE_RR","EXTENSION_CHASE","OFFICIAL_EVENT_FINALIST_REVIEW","ACCOUNT_GATE","G9","NON_SYNTHETIC_TARGET"],
      "event_state_fresh":event_state_fresh,
      "authority":"SHADOW_DEEP_PREFILTER_ONLY_NO_SIGNAL"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"mode":out["mode"],"input_weekly_pass_count":len(current_weekly),"input_weekly_trigger_scope_count":len(syms),"a_geometry_count":len(a_geom),"b_breakout_count":len(b_break),"b_armed_count":len(b_armed),"d_geometry_rs_count":len(d_geom),"unknown_history_count":len(unknown),"provider_max_inflight":PROVIDER_MAX_INFLIGHT,"retry_delays":RETRY_DELAYS},sort_keys=True))

if __name__=="__main__":
    main()
