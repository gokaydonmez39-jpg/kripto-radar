#!/usr/bin/env python3
"""XRAY Stage1 shadow technical engine.
Input: canonical-Bigdata MC pass list.
History: Sina raw daily accelerator (shadow only, never G9/canonical fill authority).
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os, time, hashlib, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal
from alpha_semantics import (
    wilder_atr as _policy_atr, ema_seeded, drawdown_metrics,
    find_recent_b_trigger, mechanical_scale_breaks, mechanical_split_suspects,
    split_consistent_history,
)

ROOT=Path(__file__).resolve().parent
MC=Path(os.getenv("XRAY_MC_STATE", str(ROOT/"mc_final_state.json")))
OUT=Path(os.getenv("XRAY_STAGE1_OUT", str(ROOT/"stage1_shadow.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_STAGE1_WORKERS","8"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_STAGE1_PROVIDER_MAX_INFLIGHT","3")))
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
    for k in ["open","high","low","close","volume"]:x[k]=pd.to_numeric(x[k],errors="coerce")
    return x.dropna().sort_values("date")

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

def wilder_atr(df, n=14):
    return _policy_atr(df,n)

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
    ema10=ema_seeded(closes,10)
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

def recent_weekly_context(df,week_last,max_age=3):
    """Weekly gate as knowable on current/prior completed trigger sessions."""
    passed=[]; ctx={}
    if df is None or df.empty:return passed,ctx
    for idx in range(max(0,len(df)-1-max_age),len(df)):
        td=df["date"].iloc[idx].date().isoformat()
        wi=weekly_gate(df.iloc[:idx+1].copy(),td,week_last)
        ctx[td]=wi
        if wi.get("pass"):passed.append(td)
    return passed,ctx

def process(sym,asof,week_last):
    try:
        x,history_source=load_history(sym,asof)
        if x is None or x.empty:return sym,{"status":"UNKNOWN","reason":"SINA_EMPTY"}
        x=x.reset_index(drop=True)
        if len(x)<260:return sym,{"status":"HISTORY_FAIL","reason":"DAILY_LT260","bars":len(x),"history_source":history_source}

        raw_wg=weekly_gate(x,asof,week_last)
        scale_breaks=mechanical_scale_breaks(x,260)
        split_suspects=mechanical_split_suspects(x)
        ca_status="PASS_NO_LOCAL_SPLIT_DISCONTINUITY"
        split_events=[]
        # External split lookup is anomaly-driven, not gap-driven. Ordinary
        # earnings/news gaps are common and must not turn the universe UNKNOWN.
        # Only a recent close-to-close mechanical scale discontinuity can require
        # split verification; open-gap suspects remain diagnostic evidence.
        if scale_breaks:
            x2,ca_status,split_events=split_consistent_history(sym,x)
            if not str(ca_status).startswith("PASS"):
                return sym,{"status":"UNKNOWN","reason":"CORPORATE_ACTION_SOURCE_UNKNOWN",
                            "corporate_action_status":ca_status,"mechanical_scale_breaks":scale_breaks,
                            "mechanical_split_suspects":split_suspects,"history_source":history_source}
            x=x2.reset_index(drop=True)

        wg=weekly_gate(x,asof,week_last)
        # New-candidate discovery is allowed on the current or prior three
        # completed sessions. Preserve the weekly context that was actually
        # knowable on each candidate trigger date; today's weekly status must
        # never erase a valid recent trigger.
        recent_weekly_pass_dates,recent_weekly_context_map=recent_weekly_context(x,week_last,3)
        if not wg.get("pass"):
            return sym,{"status":"WEEKLY_FAIL","weekly":wg,"raw_weekly":raw_wg,
                        "recent_weekly_pass_dates":recent_weekly_pass_dates,
                        "recent_weekly_context":recent_weekly_context_map,
                        "corporate_action_status":ca_status,"split_events":split_events,
                        "mechanical_scale_breaks":scale_breaks,"mechanical_split_suspects":split_suspects,
                        "history_source":history_source}

        close=x["close"].astype(float)
        sma50=close.rolling(50).mean()
        recent20_high=x["high"].astype(float).rolling(20).max()
        a_pool=False
        if len(x)>=70 and pd.notna(sma50.iloc[-1]) and pd.notna(sma50.iloc[-21]) and pd.notna(recent20_high.iloc[-1]):
            rh=float(recent20_high.iloc[-1]); last=float(close.iloc[-1])
            a_pool=bool(last>float(sma50.iloc[-1]) and float(sma50.iloc[-1])>float(sma50.iloc[-21]) and rh>0 and 0.88*rh<=last<=rh)
        b=base_pool(x)
        b_recent=find_recent_b_trigger(x,3)
        last=float(close.iloc[-1])
        dd=drawdown_metrics(x)
        dd252=dd["current_drawdown_252"]; dd120=dd["max_drawdown_close_120"]
        d_pool=bool((math.isfinite(dd252) and dd252<=-0.15) or (math.isfinite(dd120) and dd120<=-0.20))
        return sym,{
          "status":"WEEKLY_PASS","weekly":wg,"raw_weekly":raw_wg,"history_source":history_source,
          "recent_weekly_pass_dates":recent_weekly_pass_dates,
          "recent_weekly_context":recent_weekly_context,
          "corporate_action_status":ca_status,"split_events":split_events,
          "mechanical_scale_breaks":scale_breaks,"mechanical_split_suspects":split_suspects,
          "a_trend_pool":a_pool,"b_tight_base_pool":b,"b_recent_trigger":b_recent,
          "d_drawdown_pool":d_pool,"dd252":dd252,"dd120":dd120,
          "dd252_definition":"CURRENT_CLOSE_VS_MAX_HIGH_252",
          "dd120_definition":"MAX_DRAWDOWN_CLOSE_120","last_close":last
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
    recent_weekly=[s for s,r in results.items() if r.get("recent_weekly_pass_dates")]
    a=[s for s in weekly if results[s].get("a_trend_pool")]
    b=[s for s in weekly if results[s].get("b_tight_base_pool") or results[s].get("b_recent_trigger")]
    d=[s for s in weekly if results[s].get("d_drawdown_pool")]
    unknown=[s for s,r in results.items() if r.get("status")=="UNKNOWN"]
    out={
      "schema":"XRAY_STAGE1_SHADOW_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "input_current_core_count":len(syms),
      "weekly_pass_count":len(weekly),"weekly_pass":sorted(weekly),
      "recent_weekly_scope_count":len(recent_weekly),"recent_weekly_scope":sorted(recent_weekly),
      "a_trend_pool_count":len(a),"a_trend_pool":sorted(a),
      "b_tight_base_pool_count":len(b),"b_tight_base_pool":sorted(b),
      "d_drawdown_pool_count":len(d),"d_drawdown_pool":sorted(d),
      "unknown_count":len(unknown),"unknown":sorted(unknown),
      "state_caps":state_caps,
      "r92_ineligible":sorted(r92_ineligible & set(syms)),
      "source_input_path":relpath(MC),"source_input_blob_sha":blob_sha(MC),
      "source_legal_pass_hash":mc.get("source_legal_pass_hash"),
      "source_mc_policy_hash":mc.get("source_mc_policy_hash"),
      "source_mc_policy_version":mc.get("source_mc_policy_version"),
      "results":results,
      "source_authority":"SHADOW_TECHNICAL_ACCELERATOR_ONLY",
      "notes":["C post-earnings family is evaluated later from official earnings/event evidence.","No setup signal or R92 registration is created here."]
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps(dict({k:out[k] for k in ["input_current_core_count","weekly_pass_count","a_trend_pool_count","b_tight_base_pool_count","d_drawdown_pool_count","unknown_count"]},provider_max_inflight=PROVIDER_MAX_INFLIGHT,retry_delays=RETRY_DELAYS),sort_keys=True))

if __name__=="__main__":
    main()
