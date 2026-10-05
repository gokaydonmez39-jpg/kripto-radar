#!/usr/bin/env python3
"""Deterministic C4.17 alpha semantics shared by XRAY technical stages.

No execution. No account access. No signal delivery. Pure calculations only.
"""
from __future__ import annotations
import hashlib, math, time, json
from typing import Any
from datetime import timedelta
import pandas as pd
import pandas_market_calendars as mcal

def wilder_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR with the first TR undefined and the first n valid TRs as seed."""
    h=df["high"].astype(float); l=df["low"].astype(float); c=df["close"].astype(float)
    tr=pd.Series(float("nan"),index=df.index,dtype="float64")
    if len(df)>1:
        pc=c.shift(1)
        vals=pd.concat([(h-l).abs(),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
        tr.iloc[1:]=vals.iloc[1:]
    out=pd.Series(float("nan"),index=df.index,dtype="float64")
    valid=tr.dropna()
    if len(valid)<n:return out
    seed_pos=valid.index[n-1]
    seed=float(valid.iloc[:n].mean())
    out.loc[seed_pos]=seed
    started=False; prev=seed
    for idx in df.index:
        if idx==seed_pos:
            started=True; continue
        if not started: continue
        x=tr.loc[idx]
        if pd.isna(x): continue
        prev=((n-1)*prev+float(x))/n
        out.loc[idx]=prev
    return out

def ema_seeded(series: pd.Series, n: int) -> pd.Series:
    """EMA seeded by the first n values' SMA, matching the canonical contract."""
    s=series.astype(float)
    out=pd.Series(float("nan"),index=s.index,dtype="float64")
    if len(s)<n:return out
    seed=float(s.iloc[:n].mean())
    out.iloc[n-1]=seed
    alpha=2.0/(n+1.0); prev=seed
    for i in range(n,len(s)):
        prev=alpha*float(s.iloc[i])+(1-alpha)*prev
        out.iloc[i]=prev
    return out

def strict_swings(df: pd.DataFrame) -> tuple[list[int],list[int]]:
    hs=[]; ls=[]; H=df["high"].astype(float).tolist(); L=df["low"].astype(float).tolist()
    for i in range(2,len(df)-2):
        if all(H[i]>H[j] for j in (i-2,i-1,i+1,i+2)): hs.append(i)
        if all(L[i]<L[j] for j in (i-2,i-1,i+1,i+2)): ls.append(i)
    return hs,ls

def drawdown_metrics(df: pd.DataFrame) -> dict[str,float]:
    """Canonical D-pool metrics: current close vs 252 high; worst close DD inside 120."""
    c=df["close"].astype(float); h=df["high"].astype(float)
    cur=float(c.iloc[-1])
    hi252=float(h.iloc[-252:].max())
    current_dd252=cur/hi252-1 if hi252>0 else float("nan")
    w=c.iloc[-120:].reset_index(drop=True)
    running=w.cummax()
    dd=w/running-1.0
    max_dd120=float(dd.min()) if len(dd) else float("nan")
    return {"current_drawdown_252":current_dd252,"max_drawdown_close_120":max_dd120}

def trigger_index(df: pd.DataFrame, trigger_date: str) -> int | None:
    ds=df["date"].dt.date.astype(str).tolist()
    try:return ds.index(str(trigger_date))
    except ValueError:return None

def setup_id(symbol:str,family:str,trigger_date:str,P:float,anchor:float,A:float)->str:
    raw=f"{symbol}|{family}|{trigger_date}|{P:.8f}|{anchor:.8f}|{A:.8f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def session_age(df:pd.DataFrame,trigger_date:str,asof:str)->int|None:
    dates=[d.date().isoformat() for d in df["date"]]
    if trigger_date not in dates or asof not in dates:return None
    a=dates.index(trigger_date); b=dates.index(asof)
    return b-a if b>=a else None

def history_fingerprint(df:pd.DataFrame,asof:str|None=None,lookback:int=320)->dict[str,Any]:
    """Deterministic OHLCV binding for cross-phase exact-history verification."""
    if df is None or df.empty:raise ValueError("EMPTY_HISTORY_FINGERPRINT")
    need=("date","open","high","low","close","volume")
    if any(c not in df.columns for c in need):raise ValueError("HISTORY_FINGERPRINT_COLUMNS_MISSING")
    x=df[list(need)].copy()
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    for c in need[1:]:x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.dropna().drop_duplicates("date",keep="last").sort_values("date")
    if asof is not None:x=x[x["date"]<=pd.Timestamp(asof)]
    if x.empty:raise ValueError("EMPTY_HISTORY_FINGERPRINT_ASOF")
    if lookback>0:x=x.tail(int(lookback))
    rows=[]
    for _,r in x.iterrows():
        rows.append([
          r["date"].date().isoformat(),
          *[format(float(r[c]),".12g") for c in need[1:]]
        ])
    raw=json.dumps(rows,separators=(",",":"),ensure_ascii=True).encode()
    return {
      "schema":"XRAY_ALPHA_HISTORY_FINGERPRINT_V1",
      "sha256":hashlib.sha256(raw).hexdigest(),
      "rows":len(rows),
      "first_date":rows[0][0],
      "last_date":rows[-1][0],
      "lookback":int(lookback),
    }

def _base_high_points(prior:pd.DataFrame, atr:pd.Series)->list[dict[str,Any]]:
    pts=[]
    # t is a hypothetical trigger index; base excludes t.
    for t in range(26,len(prior)):
        A=atr.iloc[t-1]
        if pd.isna(A) or not math.isfinite(float(A)) or float(A)<=0: continue
        tr=pd.concat([
          (prior["high"]-prior["low"]).abs(),
          (prior["high"]-prior["close"].shift(1)).abs(),
          (prior["low"]-prior["close"].shift(1)).abs()
        ],axis=1).max(axis=1)
        passing=[]
        for n in (5,10,15,20):
            if t<n+20: continue
            base=prior.iloc[t-n:t]
            bh=float(base["high"].max()); bl=float(base["low"].min())
            width=(bh-bl)/float(A)
            last5=float(tr.iloc[t-5:t].mean())
            prev20=float(tr.iloc[t-25:t-5].mean())
            if 0.30<=width<=2.05 and prev20>0 and last5<=0.8*prev20:
                passing.append((n,bh))
        if passing:
            n,bh=max(passing,key=lambda z:z[0])
            pts.append({"price":bh,"kind":"BASE_HIGH","occurrence_idx":t-1,
                        "confirmed_idx":t-1,"date":prior["date"].iloc[t-1].date().isoformat(),
                        "window":n})
    return pts

def _weekly_swing_points(prior:pd.DataFrame)->list[dict[str,Any]]:
    """Completed weekly swing highs using the official Nasdaq session calendar."""
    if prior.empty:return []
    x=prior.copy()
    x["week"]=x["date"].dt.to_period("W-FRI")
    cal=mcal.get_calendar("NASDAQ")
    start=(x["date"].min()-pd.Timedelta(days=10)).date().isoformat()
    end=(x["date"].max()+pd.Timedelta(days=2)).date().isoformat()
    sched=cal.schedule(start_date=start,end_date=end)
    week_last={}
    for idx,_ in sched.iterrows():
        d=idx.date()
        k=pd.Timestamp(d).to_period("W-FRI")
        week_last[k]=d.isoformat()
    rows=[]
    for k,g in x.groupby("week"):
        expected=week_last.get(k)
        if not expected: continue
        got=g["date"].dt.date.max().isoformat()
        if got!=expected: continue
        rows.append({"date":g["date"].iloc[-1],"high":float(g["high"].max()),
                     "low":float(g["low"].min()),"close":float(g["close"].iloc[-1])})
    if len(rows)<5:return []
    w=pd.DataFrame(rows).reset_index(drop=True)
    hs,_=strict_swings(w);pts=[]
    daily_dates=prior["date"].dt.date.astype(str).tolist()
    for i in hs[-52:]:
        if i+2>=len(w): continue
        d=w["date"].iloc[i].date().isoformat()
        cd=w["date"].iloc[i+2].date().isoformat()
        eligible=[j for j,z in enumerate(daily_dates) if z<=cd]
        if not eligible:continue
        daily_idx=max(eligible)
        pts.append({"price":float(w["high"].iloc[i]),"kind":"WEEKLY_SWING_HIGH",
                    "occurrence_idx":i,"confirmed_idx":daily_idx,"date":d})
    return pts

def _gap_down_zones(prior:pd.DataFrame)->list[dict[str,Any]]:
    zones=[]
    for i in range(1,len(prior)):
        prev_low=float(prior["low"].iloc[i-1]); cur_high=float(prior["high"].iloc[i])
        if cur_high < prev_low:
            lower,upper=cur_high,prev_low
            filled=False
            for j in range(i+1,len(prior)):
                if float(prior["high"].iloc[j])>=upper:
                    filled=True; break
            if not filled:
                zones.append({"lower":lower,"upper":upper,"kind":"UNFILLED_GAP_DOWN",
                              "active":True,"points":[],"active_from_idx":i,
                              "occurrence_dates":[prior["date"].iloc[i].date().isoformat()]})
    return zones

def _cluster_points(points:list[dict[str,Any]],A:float)->list[dict[str,Any]]:
    if not points:return []
    points=sorted(points,key=lambda x:(float(x["price"]),x["date"],x["kind"]))
    clusters=[]
    cur=[]
    for p in points:
        trial=cur+[p]
        vals=[float(x["price"]) for x in trial]
        ref=sum(vals)/len(vals)
        tol=max(0.35*A,ref*0.005)
        if cur and max(vals)-min(vals)>tol:
            clusters.append(cur);cur=[p]
        else:cur=trial
    if cur:clusters.append(cur)
    zones=[]
    for cl in clusters:
        vals=[float(x["price"]) for x in cl]
        zones.append({"lower":min(vals),"upper":max(vals),"kind":"STRUCTURAL_CLUSTER",
                      "points":cl,"active_from_idx":max(int(x["confirmed_idx"]) for x in cl),
                      "occurrence_dates":sorted(set(x["date"] for x in cl)),"active":True})
    return zones

_SPLIT_CACHE:dict[str,tuple[str,list[dict[str,Any]]]]={}

def mechanical_split_suspects(df:pd.DataFrame,lookback:int=260)->list[dict[str,Any]]:
    """Discovery-only split suspect detector, bounded to the active technical horizon."""
    if df is None or len(df)<2:return []
    common=(1.25,1.5,2.0,3.0,4.0,5.0,10.0,20.0,25.0,50.0,100.0)
    out=[]; start=max(1,len(df)-lookback)
    for i in range(start,len(df)):
        prev=float(df["close"].iloc[i-1]);op=float(df["open"].iloc[i])
        if prev<=0 or op<=0:continue
        q=op/prev
        if 0.82<=q<=1.22:continue
        best=None
        for r in common:
            for target in (r,1.0/r):
                err=abs(q/target-1.0)
                if best is None or err<best[0]:best=(err,r,target)
        if best and best[0]<=0.12:
            out.append({"date":df["date"].iloc[i].date().isoformat(),"open_prev_close_ratio":q,
                        "matched_split_ratio":best[1],"directional_target":best[2],"relative_error":best[0]})
    return out

def fetch_yahoo_split_events(symbol:str,start_date:str,end_date:str,retries:int=3)->tuple[str,list[dict[str,Any]]]:
    """Fetch split-only events. PASS with [] means the provider explicitly returned no splits."""
    key=f"{symbol}|{start_date}|{end_date}"
    if key in _SPLIT_CACHE:return _SPLIT_CACHE[key]
    try:
        from curl_cffi import requests as crequests
    except Exception:
        return "UNKNOWN_TRANSPORT_MISSING",[]
    p1=int(pd.Timestamp(start_date,tz="UTC").timestamp())
    p2=int((pd.Timestamp(end_date,tz="UTC")+pd.Timedelta(days=2)).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params={"period1":p1,"period2":p2,"interval":"1d","events":"splits","includeAdjustedClose":"false"}
    last=None
    for attempt in range(retries):
        try:
            resp=crequests.get(url,params=params,impersonate="chrome",timeout=12)
            if int(resp.status_code)!=200:
                raise RuntimeError(f"HTTP_{resp.status_code}")
            data=resp.json();result=(data.get("chart") or {}).get("result") or []
            if not result:raise RuntimeError("NO_CHART_RESULT")
            events=((result[0].get("events") or {}).get("splits") or {})
            out=[]
            for _,e in events.items():
                num=float(e.get("numerator"));den=float(e.get("denominator"))
                ts=e.get("date")
                if not (math.isfinite(num) and math.isfinite(den) and num>0 and den>0 and ts is not None):
                    raise RuntimeError("INVALID_SPLIT_EVENT")
                day=pd.Timestamp(int(ts),unit="s",tz="UTC").date().isoformat()
                if start_date<=day<=end_date:
                    out.append({"date":day,"numerator":num,"denominator":den,
                                "ratio":num/den,"splitRatio":e.get("splitRatio")})
            out=sorted(out,key=lambda z:z["date"])
            ans=("PASS",out);_SPLIT_CACHE[key]=ans;return ans
        except Exception as exc:
            last=exc
            if attempt+1<retries:time.sleep(0.6*(attempt+1))
    ans=(f"UNKNOWN:{type(last).__name__}:{str(last)[:100]}",[])
    _SPLIT_CACHE[key]=ans;return ans

def apply_split_events(df:pd.DataFrame,events:list[dict[str,Any]])->pd.DataFrame:
    """Convert pre-split raw OHLCV to the latest share scale using split-only ratios."""
    x=df.copy().sort_values("date").reset_index(drop=True)
    for e in sorted(events,key=lambda z:z["date"]):
        ratio=float(e["ratio"])
        if not math.isfinite(ratio) or ratio<=0:raise ValueError("INVALID_SPLIT_RATIO")
        event_day=pd.Timestamp(e["date"])
        mask=x["date"]<event_day
        for col in ("open","high","low","close"):
            if col in x.columns:x.loc[mask,col]=x.loc[mask,col].astype(float)/ratio
        if "volume" in x.columns:x.loc[mask,"volume"]=x.loc[mask,"volume"].astype(float)*ratio
    return x

def _verify_split_events_against_raw(df:pd.DataFrame,events:list[dict[str,Any]])->tuple[bool,str]:
    """Cross-check provider-declared split events against raw OHLC.

    A mechanical 2x/3x-like price move is a discovery trigger, not proof of a
    corporate action. Large earnings/clinical/news gaps can legitimately resemble
    common split factors. Therefore only provider-declared split events are
    ratio/date-validated here. A successful split lookup with no event leaves the
    move as ordinary market price discovery at Stage1/breadth; finalist-level
    primary corporate-action review remains separately fail-closed.
    """
    x=df.copy().sort_values("date").reset_index(drop=True)
    dates=x["date"].dt.date.astype(str).tolist()
    for e in events:
        day=str(e["date"])
        if day not in dates:return False,"SPLIT_EVENT_DATE_NOT_IN_RAW_HISTORY:"+day
        i=dates.index(day)
        if i<1:return False,"SPLIT_EVENT_HAS_NO_PRIOR_BAR:"+day
        pc=float(x["close"].iloc[i-1]);op=float(x["open"].iloc[i]);ratio=float(e["ratio"])
        if pc<=0 or op<=0 or ratio<=0:return False,"INVALID_SPLIT_CROSSCHECK_VALUES:"+day
        observed=pc/op
        rel=abs(observed/ratio-1.0)
        # Independent raw Sina scale break should approximately agree with the
        # provider split ratio. 35% leaves room for a large overnight move while
        # rejecting an unrelated or mis-dated declared split.
        if rel>0.35:return False,f"SPLIT_RATIO_RAW_CONFLICT:{day}:{observed:.6f}:{ratio:.6f}"
    return True,"PASS"

def split_consistent_history(symbol:str,df:pd.DataFrame,lookback:int=260)->tuple[pd.DataFrame,str,list[dict[str,Any]]]:
    """Reconcile split events only inside the active technical horizon.

    Stage1/Final call this function only after a recent mechanical split-like
    discontinuity is detected. Ancient provider split events outside that same
    horizon are irrelevant to current technical geometry and must not poison
    the current decision merely because an old vendor/raw scale disagrees.
    """
    if df is None or df.empty:return df,"UNKNOWN_EMPTY_HISTORY",[]
    x=df.copy().sort_values("date").reset_index(drop=True)
    if len(x)<2:return x,"UNKNOWN_INSUFFICIENT_HISTORY",[]
    horizon=max(2,int(lookback or 260))
    start_idx=max(1,len(x)-horizon)
    start=x["date"].iloc[start_idx].date().isoformat()
    end=x["date"].iloc[-1].date().isoformat()
    status,events=fetch_yahoo_split_events(symbol,start,end)
    if status!="PASS":return x,status,events
    # Defensive range filter: even if a provider returns an out-of-window event,
    # current technical decisions are bound only to the active horizon.
    events=[e for e in events if start<=str(e.get("date") or "")<=end]
    ok,reason=_verify_split_events_against_raw(x,events)
    if not ok:return x,"UNKNOWN:"+reason,events
    if not events:return x,"PASS_NO_SPLIT_EVENTS_CROSSCHECKED",[]
    return apply_split_events(x,events),"PASS_SPLIT_RECONCILED_CROSSCHECKED",events

def resistance_zones(df:pd.DataFrame,trigger_idx:int,A:float)->list[dict[str,Any]]:
    """Structural resistance set known by trigger-1; no trigger/current look-ahead."""
    if trigger_idx<=2:return []
    prior=df.iloc[:trigger_idx].copy().reset_index(drop=True)
    cutoff=len(prior)-1
    hs,_=strict_swings(prior)
    pts=[]
    for i in hs:
        if i+2>cutoff or i<max(0,cutoff-120): continue
        pts.append({"price":float(prior["high"].iloc[i]),"kind":"DAILY_SWING_HIGH",
                    "occurrence_idx":i,"confirmed_idx":i+2,
                    "date":prior["date"].iloc[i].date().isoformat()})
    atr=wilder_atr(prior,14)
    pts.extend(_base_high_points(prior,atr))
    pts.extend(_weekly_swing_points(prior))
    zones=_cluster_points(pts,A)+_gap_down_zones(prior)
    # A resistance remains active after a close above it until a later successful
    # role-change retest closes back above the zone. A single close never erases supply.
    for z in zones:
        lo=float(z["lower"]); hi=float(z["upper"]); af=int(z["active_from_idx"])
        breakout=None; role_change=None
        for i in range(af+1,len(prior)):
            if breakout is None and float(prior["close"].iloc[i])>hi:
                breakout=i; continue
            if breakout is not None and i>breakout:
                touched=float(prior["low"].iloc[i])<=hi and float(prior["high"].iloc[i])>=lo
                if touched and float(prior["close"].iloc[i])>hi:
                    role_change=i; break
        if role_change is not None:
            z["active"]=False; z["broken_at"]=prior["date"].iloc[role_change].date().isoformat()
        elif breakout is not None:
            z["breakout_unconfirmed_role_change"]=prior["date"].iloc[breakout].date().isoformat()
    return sorted(zones,key=lambda z:(float(z["lower"]),float(z["upper"]),z["kind"]))

def nearest_active_resistance(df:pd.DataFrame,trigger_idx:int,A:float,entry_low:float,entry_high:float,entry_model:float)->dict[str,Any]:
    zones=resistance_zones(df,trigger_idx,A)
    # Any active zone that reaches into the entry band is the first obstacle
    # and may not be skipped merely because its upper bound is below E_MODEL.
    # Zones wholly below ENTRY_LOW are support/context, not overhead resistance.
    eligible=[z for z in zones if z.get("active") and float(z["upper"])>=entry_low]
    if not eligible:
        prior=df.iloc[:trigger_idx]
        prior_max=float(prior["high"].max()) if len(prior) else float("nan")
        return {"status":"NONE_OBSERVED","zones":zones,"prior_max_high":prior_max}
    z=min(eligible,key=lambda q:(float(q["lower"]),float(q["upper"])))
    overlap=not (float(z["upper"])<entry_low or float(z["lower"])>entry_high)
    return {"status":"PASS","T1":float(z["lower"]),"zone":z,"target_overlap":overlap,"zones":zones}

def rvol20_at(df:pd.DataFrame,idx:int)->float|None:
    """Exact trigger-volume ratio versus the prior 20 completed rows; trigger excluded."""
    if idx<20:return None
    vals=[float(v) for v in df["volume"].iloc[idx-20:idx] if math.isfinite(float(v)) and float(v)>=0]
    if len(vals)!=20:return None
    med=float(pd.Series(vals,dtype="float64").median())
    if not math.isfinite(med) or med<=0:return None
    v=float(df["volume"].iloc[idx])
    return v/med if math.isfinite(v) and v>=0 else None

def tight_base_at(df:pd.DataFrame,t:int)->dict[str,Any]|None:
    """C4.17 B geometry at trigger t; trigger is excluded from base and contraction windows."""
    if t<26 or t>=len(df):return None
    atr=wilder_atr(df,14)
    if t-1>=len(atr) or pd.isna(atr.iloc[t-1]):return None
    A=float(atr.iloc[t-1])
    if not math.isfinite(A) or A<=0:return None
    tr=pd.concat([(df["high"]-df["low"]).abs(),(df["high"]-df["close"].shift(1)).abs(),
                  (df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    passing=[]
    for n in (5,10,15,20):
        if t<n+20:continue
        base=df.iloc[t-n:t]
        bh=float(base["high"].max());bl=float(base["low"].min());width=(bh-bl)/A
        last5=float(tr.iloc[t-5:t].mean());prev20=float(tr.iloc[t-25:t-5].mean())
        if 0.30<=width<=2.05 and prev20>0 and last5<=0.8*prev20:
            passing.append((n,bh,bl,width))
    if not passing:return None
    n,P,anchor,width=max(passing,key=lambda z:z[0])
    rv=rvol20_at(df,t);close=float(df["close"].iloc[t])
    return {"window":n,"P":P,"anchor":anchor,"b":width,"A":A,"rvol20":rv,"close":close,
            "breakout_confirmed":bool(close>P and rv is not None and rv>=1.5),
            "trigger_date":df["date"].iloc[t].date().isoformat()}

def find_recent_b_trigger(df:pd.DataFrame,max_age:int=5,eligible_dates=None)->dict[str,Any]|None:
    """Earliest valid B trigger inside the retest horizon and optional weekly-eligible dates."""
    if df.empty:return None
    allowed=None if eligible_dates is None else set(str(x) for x in eligible_dates)
    last=len(df)-1
    for t in range(max(0,last-max_age),last+1):
        td=df["date"].iloc[t].date().isoformat()
        if allowed is not None and td not in allowed:continue
        g=tight_base_at(df,t)
        if g and g.get("breakout_confirmed"):
            g["trigger_age_sessions"]=last-t
            return g
    return None

def mechanical_scale_breaks(df:pd.DataFrame,lookback:int=260)->list[dict[str,Any]]:
    """Detect likely split/ADR-ratio scale breaks in unadjusted OHLC; diagnostic/fail-closed only."""
    out=[]; start=max(1,len(df)-lookback); common=(2.0,3.0,4.0,5.0,10.0,20.0)
    for i in range(start,len(df)):
        pc=float(df["close"].iloc[i-1]);cc=float(df["close"].iloc[i])
        if pc<=0 or cc<=0:continue
        ratio=max(pc/cc,cc/pc)
        nearest=min(common,key=lambda x:abs(ratio-x));rel=abs(ratio-nearest)/nearest
        if ratio>=1.8 and rel<=0.08:
            out.append({"date":df["date"].iloc[i].date().isoformat(),"ratio":ratio,
                        "nearest_common_factor":nearest,"relative_error":rel})
    return out

def trend_pullback_stage1_at(df:pd.DataFrame,idx:int)->bool:
    """C4.17 A Stage1 gate evaluated as-of the candidate trigger, never today's snapshot."""
    if idx<69 or idx>=len(df):
        return False
    close=df["close"].astype(float)
    sma50=close.rolling(50).mean()
    recent20=df["high"].astype(float).rolling(20).max()
    if pd.isna(sma50.iloc[idx]) or pd.isna(sma50.iloc[idx-20]) or pd.isna(recent20.iloc[idx]):
        return False
    last=float(close.iloc[idx]); rh=float(recent20.iloc[idx])
    return bool(
        rh>0 and last>float(sma50.iloc[idx])
        and float(sma50.iloc[idx])>float(sma50.iloc[idx-20])
        and 0.88*rh<=last<=rh
    )

def family_a_pretrigger_low(df:pd.DataFrame,trigger_idx:int)->float:
    """C4.17 A-family HL proximity uses only the bar immediately before reversal."""
    if trigger_idx<=0 or trigger_idx>=len(df):
        raise IndexError("INVALID_FAMILY_A_TRIGGER_INDEX")
    v=float(df["low"].iloc[trigger_idx-1])
    if not math.isfinite(v):
        raise ValueError("INVALID_FAMILY_A_PRETRIGGER_LOW")
    return v

def retest_bar(row:pd.Series,P:float,entry_high:float)->bool:
    return float(row["low"])<=entry_high and float(row["close"])>P and float(row["close"])<=entry_high

def extension_diagnostics(df:pd.DataFrame,A:float,P:float,entry_high:float)->dict[str,Any]:
    t=len(df)-1; close=float(df["close"].iloc[t])
    pivot_extension=(close/P)-1 if P>0 else float("inf")
    move3=None; reset=False; reset_kind=None
    if t>=3:
        move3=(close-float(df["close"].iloc[t-3]))/A
        # Canonical reset may be either a valid retest inside the frozen entry
        # band or a newly completed tight base known before the current close.
        for i in range(t-2,t):
            if retest_bar(df.iloc[i],P,entry_high):
                reset=True; reset_kind="RETEST"; break
        if not reset:
            for candidate_t in (t-1,t):
                if candidate_t>=0 and tight_base_at(df,candidate_t) is not None:
                    reset=True; reset_kind="TIGHT_BASE"; break
    veto=bool(pivot_extension>=0.08 or (move3 is not None and move3>2.0 and not reset))
    return {"pivot_extension":pivot_extension,"move3_atr":move3,
            "reset_between_tminus3_and_t":reset,"reset_kind":reset_kind,
            "extension_veto":veto}
