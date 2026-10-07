#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_PHASE_INPUT", str(ROOT/"canonical_full_hard_gate_20260930_state.json")))
OUT=Path(os.getenv("XRAY_PRICE_DV30_OUT", str(ROOT/"canonical_price_dv30_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF_ENV=os.getenv("XRAY_ASOF")
HARD_PRICE=5.0
HARD_DV30=50_000_000.0
WORKERS=int(os.getenv("XRAY_PHASE_WORKERS","12"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")

def num(x):
    try:
        if x is None:return None
        s=str(x).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--","-"}:return None
        v=float(s)
        return v if math.isfinite(v) else None
    except Exception:return None

def req_json(url,params=None,timeout=30):
    if params:url += ("&" if "?" in url else "?")+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,"Accept":"application/json,text/plain,*/*",
        "Accept-Language":"en-US,en;q=0.9","Referer":"https://www.nasdaq.com/"
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def expected30(asof):
    cal=mcal.get_calendar("NASDAQ")
    start=(datetime.fromisoformat(asof).date()-timedelta(days=60)).isoformat()
    sched=cal.schedule(start_date=start,end_date=asof)
    ds=[x.date().isoformat() for x in sched.index if x.date().isoformat()<=asof]
    if len(ds)<30:raise RuntimeError("CALENDAR_LT30")
    return ds[-30:]

def classify(by,asof,exp30,source):
    if asof not in by:
        return "UNKNOWN",{"reason":"ASOF_MISSING","source":source,"usable_bars":len(by)}
    price=by[asof][0]
    if price<HARD_PRICE:
        return "FAIL_PRICE",{"price":price,"source":source,"proof":"ASOF_CLOSE_LT_5"}
    vals=[by[d][0]*by[d][1] for d in exp30 if d in by]
    missing=[d for d in exp30 if d not in by]
    if not missing:
        s=sorted(vals);dv=(s[14]+s[15])/2.0
        if dv<HARD_DV30:
            return "FAIL_DV30",{"price":price,"dv30":dv,"source":source,"proof":"EXACT30_MEDIAN_LT_GATE"}
        return "PASS_PRICE_DV30",{"price":price,"dv30":dv,"source":source,"proof":"EXACT30_MEDIAN_GE_GATE","known_session_count":30,"missing_sessions":[]}
    m=len(missing)
    lo=sorted(vals+[0.0]*m); lower=(lo[14]+lo[15])/2.0
    hi=sorted(vals+[float("inf")]*m); upper=(hi[14]+hi[15])/2.0
    info={"price":price,"source":source,"known_session_count":len(vals),"missing_sessions":missing,
          "dv30_lower_bound":lower,"dv30_upper_bound":None if math.isinf(upper) else upper,
          "no_synthetic_bar":True}
    if upper<HARD_DV30:
        info["proof"]="DV30_UPPER_BOUND_LT_GATE";return "FAIL_DV30",info
    info["reason"]="EXACT30_INCOMPLETE_NEVER_PASS";return "UNKNOWN",info

def sina(sym,asof):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:return {},{"error":"SINA_EMPTY"}
        by={}
        for rec in df.to_dict(orient="records"):
            try:
                d=rec.get("date");day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                c=float(rec.get("close"));v=float(rec.get("volume"))
            except Exception:continue
            if day<=asof and c>0 and v>=0 and math.isfinite(c) and math.isfinite(v):
                by[day]=(c,v)
        return by,{"usable":len(by)}
    except Exception as e:return {},{"error":f"{type(e).__name__}:{str(e)[:160]}"}

def nasdaq(sym,asof):
    """Disabled legacy Nasdaq web historical helper.

    Canonical automation must not call api.nasdaq.com.  This compatibility
    function is intentionally nonterminal so callers fail closed and continue
    only to permitted fail-only/bridge sources.
    """
    return {},{
      "disabled":True,
      "reason":"NASDAQ_WEB_AUTOMATION_DISABLED_TOS_AND_PIT",
      "no_pass_or_fail_created":True,
    }

def yahoo(sym,asof):
    try:
        end=datetime.fromisoformat(asof).replace(tzinfo=NY)+timedelta(days=1);start=end-timedelta(days=90)
        ticker=sym.replace(".","-")
        obj=req_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}",
            {"period1":int(start.timestamp()),"period2":int(end.timestamp()),"interval":"1d","events":"history","includeAdjustedClose":"false"})
        res=((obj.get("chart") or {}).get("result") or [])
        if not res:return {},{"error":str((obj.get("chart") or {}).get("error"))}
        r=res[0];ts=r.get("timestamp") or [];q=(((r.get("indicators") or {}).get("quote") or [{}])[0])
        closes=q.get("close") or [];vols=q.get("volume") or [];by={}
        for t,c,v in zip(ts,closes,vols):
            c=num(c);v=num(v)
            if c is None or c<=0 or v is None or v<0:continue
            day=datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat()
            if day<=asof:by[day]=(c,v)
        return by,{"usable":len(by),"exchangeName":(r.get("meta") or {}).get("exchangeName")}
    except Exception as e:return {},{"error":f"{type(e).__name__}:{str(e)[:160]}"}

def eval_one(sym,exp30,asof):
    by,meta=sina(sym,asof);st,info=classify(by,asof,exp30,"SINA_US_DAILY") if by else ("UNKNOWN",{"reason":"SINA_UNAVAILABLE"})
    if st!="UNKNOWN":return sym,st,info,{"sina":meta}
    nby,nm=nasdaq(sym,asof);nst,ninfo=("UNKNOWN",{"reason":"NASDAQ_WEB_AUTOMATION_DISABLED_TOS_AND_PIT"})
    if nst!="UNKNOWN":return sym,nst,ninfo,{"sina":meta,"nasdaq":nm}
    yby,ym=yahoo(sym,asof);yst,yinfo=classify(yby,asof,exp30,"YAHOO_CHART_FREE_FAIL_ONLY") if yby else ("UNKNOWN",{"reason":"YAHOO_UNAVAILABLE"})
    if yst in {"FAIL_PRICE","FAIL_DV30"}:
        return sym,yst,yinfo,{"sina":meta,"nasdaq":nm,"yahoo":ym}
    return sym,"UNKNOWN",{
        "reason":"ALL_ZERO_DOLLAR_PHASE_SOURCES_NONTERMINAL",
        "sina_result":info,"nasdaq_result":ninfo,"yahoo_result":yinfo
    },{"sina":meta,"nasdaq":nm,"yahoo":ym}

def main():
    src=json.loads(INPUT.read_text())
    asof=ASOF_ENV or src.get("asof_et")
    assert src["task_id"]==TASK_ID and src["asof_et"]==asof
    queue=src["queue"];assert len(queue)==len(set(queue)) and len(queue)>3000
    exp30=expected30(asof)
    results={};unknowns=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(eval_one,s,exp30,asof):s for s in queue}
        for fut in as_completed(futs):
            sym,st,info,prov=fut.result()
            results[sym]={"status":st,"info":info,"provider_meta":prov}
            if st=="UNKNOWN":unknowns.append(sym)
    counts={}
    for r in results.values():counts[r["status"]]=counts.get(r["status"],0)+1
    pass_syms=sorted(s for s,r in results.items() if r["status"]=="PASS_PRICE_DV30")
    import hashlib
    obj={
        "schema":"XRAY_CANONICAL_PRICE_DV30_V1","task_id":TASK_ID,"asof_et":asof,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "source_master_queue_hash":src["queue_hash"],"source_master_count":len(queue),
        "expected30":exp30,"gate_order":["PRICE","DV30"],"thresholds":{"price":">=5","dv30":">=50000000 exact30 median"},
        "counts":dict(sorted(counts.items())),"unknown_count":len(unknowns),"unknown_symbols":sorted(unknowns),
        "pass_count":len(pass_syms),"pass_symbols":pass_syms,
        "pass_hash":hashlib.sha256("\n".join(pass_syms).encode()).hexdigest(),
        "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"counts":obj["counts"],"unknown_count":obj["unknown_count"],"pass_count":obj["pass_count"],"pass_hash":obj["pass_hash"]},sort_keys=True))

if __name__=="__main__":main()
