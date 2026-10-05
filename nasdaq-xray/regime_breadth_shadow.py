#!/usr/bin/env python3
"""XRAY REGIME/BREADTH shadow engine.
Universe = canonical Bigdata-MC CURRENT_CORE names only.
History accelerator = Sina. UNKNOWN!=PASS. Never G9.
"""
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request, hashlib, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import akshare as ak
import pandas as pd
import pandas_market_calendars as mcal
from alpha_semantics import apply_split_events, mechanical_split_suspects, mechanical_scale_breaks

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_REGIME_STAGE1", str(ROOT/"canonical_current_stage1.json")))
MC=Path(os.getenv("XRAY_MC_STATE", str(ROOT/"mc_final_state.json")))
OUT=Path(os.getenv("XRAY_REGIME_OUT", str(ROOT/"regime_breadth_shadow.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
WORKERS=int(os.getenv("XRAY_BREADTH_WORKERS","8"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_BREADTH_PROVIDER_MAX_INFLIGHT","3")))
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

def _normalize_sina_close(df):
    if df is None or df.empty:return None
    cols={str(c).lower():c for c in df.columns}
    if "date" not in cols or "close" not in cols:return None
    x=df[[cols["date"],cols["close"]]].copy();x.columns=["date","close"]
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    x["close"]=pd.to_numeric(x["close"],errors="coerce")
    return x.dropna().drop_duplicates("date",keep="last").sort_values("date")

def _sina_close(sym):
    return _normalize_sina_close(_call_with_retry(lambda: ak.stock_us_daily(symbol=sym,adjust="")))

def sina_close_history(sym,asof):
    cur=_sina_close(sym)
    rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")=="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY" and rec.get("cusip_unchanged") is True:
        pred=rec.get("predecessor_symbol"); eff=rec.get("effective_date")
        if pred and eff and cur is not None:
            p=_sina_close(pred)
            if p is not None:
                eff_ts=pd.Timestamp(eff); asof_ts=pd.Timestamp(asof)
                cur2=cur[(cur["date"]>=eff_ts)&(cur["date"]<=asof_ts)]
                pred2=p[p["date"]<eff_ts]
                if not cur2.empty and cur2["date"].dt.date.max().isoformat()==asof:
                    x=pd.concat([pred2,cur2],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last")
                    return x,"SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"
    if cur is None:return None,"SINA_EMPTY"
    x=cur[cur["date"]<=pd.Timestamp(asof)]
    return x,"SINA_US_DAILY"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

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
    def _once():
        req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"})
        with urllib.request.urlopen(req,timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    obj=_call_with_retry(_once)
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
    if x.empty or x["date"].dt.date.max().isoformat()!=asof:return None,f"YAHOO_ASOF_MISSING:{x['date'].dt.date.max().isoformat() if not x.empty else 'EMPTY'}"
    if len(x)<200:return None,f"YAHOO_LT200:{len(x)}"
    return x,None

def hist(sym,asof):
    primary_error=None
    try:
        x,src=sina_close_history(sym,asof)
        if x is not None and not x.empty:
            last=x["date"].dt.date.max().isoformat()
            if last==asof and len(x)>=200:return sym,x,None,src
            primary_error=f"{src}_LT200_OR_ASOF:{len(x)}:{last}"
        else:primary_error=str(src)
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
    st={}
    if STAGE1.exists():
        try:
            qst=json.loads(STAGE1.read_text())
            if qst.get("asof_et")==asof and qst.get("task_id")==TASK_ID:st=qst
        except Exception:st={}
    data={};missing={};history_source={}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(hist,s,asof):s for s in syms+["QQQ"]}
        for fut in as_completed(futs):
            s,x,e,src=fut.result()
            if x is None:missing[s]=e
            else:
                data[s]=x
                history_source[s]=src

    qqq_ca_status=None;qqq_split_events=[]
    if "QQQ" not in data:
        regime="UNKNOWN";q={}
    else:
        # Regime history is close-only (Sina or Yahoo fallback). Do not pass it
        # through the OHLC split reconciler, which requires an open column.
        # For regime math we need only the last 200 sessions; a severe recent
        # scale break is fail-closed, while ancient artifacts are irrelevant.
        qdf=data["QQQ"].reset_index(drop=True)
        qqq_breaks=mechanical_scale_breaks(qdf,260)
        if qqq_breaks:
            qqq_ca_status="UNKNOWN_RECENT_QQQ_SCALE_BREAK"
            missing["QQQ"]="CORPORATE_ACTION_UNKNOWN:"+qqq_ca_status
            regime="UNKNOWN";q={}
        else:
            qqq_ca_status="PASS_NO_RECENT_QQQ_SCALE_BREAK"
            c=qdf["close"]
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
    corporate_action_status_by_symbol={}
    for s in syms:
        x=data.get(s)
        if x is None:
            breadth_missing.append(s);continue
        strow=(st.get("results") or {}).get(s) or {}
        ca_status=strow.get("corporate_action_status")
        split_events=strow.get("split_events") or []
        breaks=mechanical_split_suspects(x)
        if split_events:
            x=apply_split_events(x,split_events).reset_index(drop=True)
        elif breaks and not str(ca_status).startswith("PASS"):
            breadth_missing.append(s)
            corporate_action_status_by_symbol[s]=ca_status or "UNKNOWN_SCALE_BREAK"
            continue
        corporate_action_status_by_symbol[s]=ca_status or ("PASS_NO_MECHANICAL_SCALE_BREAK" if not breaks else "PASS_VERIFIED")
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
      "qqq_corporate_action_status":qqq_ca_status,"qqq_split_events":qqq_split_events,
      "corporate_action_status_by_symbol":corporate_action_status_by_symbol,
      "history_source_by_symbol":history_source,
      "history_source_counts":{
        "SINA_US_DAILY":sum(1 for v in history_source.values() if v=="SINA_US_DAILY"),
        "SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE":sum(1 for v in history_source.values() if v=="SINA_OFFICIAL_TICKER_CONTINUITY_COMPOSITE"),
        "YAHOO_CHART_FREE_FALLBACK":sum(1 for v in history_source.values() if v=="YAHOO_CHART_FREE_FALLBACK")
      },
      "source_input_path":relpath(MC),"source_input_blob_sha":blob_sha(MC),
      "source_legal_pass_hash":mc.get("source_legal_pass_hash"),
      "source_mc_policy_hash":mc.get("source_mc_policy_hash"),
      "source_mc_policy_version":mc.get("source_mc_policy_version"),
      "source_authority":"SHADOW_REGIME_ACCELERATOR_ONLY_SINA_PRIMARY_YAHOO_FALLBACK"
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps(dict({k:out[k] for k in ["current_core_count","history_ok_count","breadth_missing_count","breadth_above_sma50_pct","nh20","nl20","regime"]},provider_max_inflight=PROVIDER_MAX_INFLIGHT,retry_delays=RETRY_DELAYS),sort_keys=True))

if __name__=="__main__":
    main()
