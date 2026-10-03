#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import akshare as ak

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_HISTORY_INPUT", str(ROOT/"canonical_mc_input_20260930.json")))
OUT=Path(os.getenv("XRAY_HISTORY_OUT", str(ROOT/"canonical_history_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF_ENV=os.getenv("XRAY_ASOF")
HARD_DAILY=260
HARD_WEEKLY=52
WORKERS=int(os.getenv("XRAY_HISTORY_WORKERS","10"))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def relpath(p:Path):
    try:return str(p.relative_to(ROOT.parent)).replace("\\","/")
    except Exception:return str(p)

def num(x):
    try:
        if x is None:return None
        s=str(x).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--","-"}:return None
        v=float(s);return v if math.isfinite(v) else None
    except Exception:return None

def req_json(url,params=None,timeout=30):
    if params:url += ("&" if "?" in url else "?")+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/plain,*/*","Referer":"https://www.nasdaq.com/"})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())

def week_count(by,asof):
    ad=datetime.fromisoformat(asof).date()
    monday=ad-timedelta(days=ad.weekday())
    weeks=set()
    for d in by:
        dt=datetime.fromisoformat(d).date()
        if dt<monday:
            iso=dt.isocalendar()
            weeks.add((iso.year,iso.week))
    return len(weeks)

def classify(by,asof,source):
    if not by or asof not in by:return "UNKNOWN",{"reason":"ASOF_MISSING_OR_EMPTY","source":source,"daily_bars":len(by or {})}
    daily=len(by);weekly=week_count(by,asof)
    info={"source":source,"daily_bars":daily,"completed_week_count":weekly}
    if daily>=HARD_DAILY and weekly>=HARD_WEEKLY:return "PASS_HISTORY",info
    return "POTENTIAL_FAIL_HISTORY",info

def sina(sym,asof):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        by={}
        if df is not None:
            for r in df.to_dict(orient="records"):
                try:
                    d=r.get("date");day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                    c=float(r.get("close"));v=float(r.get("volume"))
                except Exception:continue
                if day<=asof and c>0 and v>=0 and math.isfinite(c) and math.isfinite(v):by[day]=(c,v)
        return by,{"usable":len(by)}
    except Exception as e:return {},{"error":f"{type(e).__name__}:{str(e)[:160]}"}

def nasdaq(sym,asof):
    try:
        end=datetime.fromisoformat(asof).date();start=end-timedelta(days=1100)
        o=req_json(f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(sym)}/historical",
          {"assetclass":"stocks","fromdate":start.strftime("%m/%d/%Y"),"todate":end.strftime("%m/%d/%Y"),"limit":"5000"},40)
        rows=(((o.get("data") or {}).get("tradesTable") or {}).get("rows") or []);by={}
        for r in rows:
            ds=str(r.get("date") or "");day=None
            for fmt in ("%m/%d/%Y","%m/%d/%y"):
                try:day=datetime.strptime(ds,fmt).date().isoformat();break
                except Exception:pass
            if not day:continue
            c=num(r.get("close") or r.get("close/last"));v=num(r.get("volume"))
            if c is not None and c>0 and v is not None and v>=0:by[day]=(c,v)
        return by,{"rows":len(rows),"usable":len(by)}
    except Exception as e:return {},{"error":f"{type(e).__name__}:{str(e)[:160]}"}

def yahoo(sym,asof):
    try:
        end=datetime.fromisoformat(asof).replace(tzinfo=NY)+timedelta(days=1);start=end-timedelta(days=1100)
        ticker=sym.replace(".","-")
        o=req_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}",
          {"period1":int(start.timestamp()),"period2":int(end.timestamp()),"interval":"1d","events":"history","includeAdjustedClose":"false"},25)
        res=((o.get("chart") or {}).get("result") or [])
        if not res:return {},{"error":str((o.get("chart") or {}).get("error"))}
        r=res[0];q=(((r.get("indicators") or {}).get("quote") or [{}])[0]);by={}
        for t,c,v in zip(r.get("timestamp") or [],q.get("close") or [],q.get("volume") or []):
            c=num(c);v=num(v)
            if c is None or c<=0 or v is None or v<0:continue
            day=datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat()
            if day<=asof:by[day]=(c,v)
        return by,{"usable":len(by),"exchangeName":(r.get("meta") or {}).get("exchangeName")}
    except Exception as e:return {},{"error":f"{type(e).__name__}:{str(e)[:160]}"}

def eval_one(sym,asof):
    sb,sm=sina(sym,asof);ss,si=classify(sb,asof,"SINA_US_DAILY")
    if ss=="PASS_HISTORY":return sym,ss,si,{"sina":sm}
    nb,nm=nasdaq(sym,asof);ns,ni=classify(nb,asof,"NASDAQ_OFFICIAL_HISTORICAL_API")
    if ns=="PASS_HISTORY":return sym,ns,ni,{"sina":sm,"nasdaq":nm}
    yb,ym=yahoo(sym,asof);ys,yi=classify(yb,asof,"YAHOO_CHART_FREE")
    if ys=="PASS_HISTORY":return sym,ys,yi,{"sina":sm,"nasdaq":nm,"yahoo":ym}
    # Terminal FAIL requires at least two independent providers to agree below either threshold.
    fails=[x for x in [si if ss=="POTENTIAL_FAIL_HISTORY" else None,ni if ns=="POTENTIAL_FAIL_HISTORY" else None,yi if ys=="POTENTIAL_FAIL_HISTORY" else None] if x]
    if len(fails)>=2:
        return sym,"FAIL_HISTORY",{
          "proof":"TWO_PROVIDER_BELOW_HISTORY_GATE",
          "provider_results":fails,
          "daily_max":max(x["daily_bars"] for x in fails),
          "weekly_max":max(x["completed_week_count"] for x in fails)
        },{"sina":sm,"nasdaq":nm,"yahoo":ym}
    return sym,"UNKNOWN_HISTORY",{
      "reason":"INSUFFICIENT_AGREEMENT",
      "sina":si,"nasdaq":ni,"yahoo":yi
    },{"sina":sm,"nasdaq":nm,"yahoo":ym}

def main():
    src=json.loads(INPUT.read_text())
    asof=ASOF_ENV or src.get("asof_et")
    assert src["task_id"]==TASK_ID and src["asof_et"]==asof
    assert src.get("schema") in {"XRAY_CANONICAL_MC_INPUT_20260930_V1","XRAY_CANONICAL_MC_INPUT_V2","XRAY_MC_EPOCH_RESULT_V1"}
    syms=src.get("current_core_symbols") or src.get("primary_pass_symbols") or []
    assert len(syms)==len(set(syms)) and len(syms)>0
    results={};unknown=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(eval_one,s,asof):s for s in syms}
        for fut in as_completed(futs):
            s,st,info,meta=fut.result();results[s]={"status":st,"info":info,"provider_meta":meta}
            if st=="UNKNOWN_HISTORY":unknown.append(s)
    counts={}
    for r in results.values():counts[r["status"]]=counts.get(r["status"],0)+1
    passes=sorted(s for s,r in results.items() if r["status"]=="PASS_HISTORY")
    import hashlib
    obj={
      "schema":"XRAY_CANONICAL_HISTORY_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "source_mc_artifact":relpath(INPUT),
      "source_mc_blob_sha":blob_sha(INPUT),
      "source_mc_policy_hash":src.get("policy_hash"),
      "source_mc_policy_version":src.get("policy_version"),
      "input_count":len(syms),"thresholds":{"daily":HARD_DAILY,"weekly_completed":HARD_WEEKLY},
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":sorted(unknown),
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "state_caps":src.get("state_caps") or {s:"NORMAL" for s in syms},
      "r92_ineligible":src.get("r92_ineligible") or src.get("fallback_watch_symbols") or [],
      "results":dict(sorted(results.items()))
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
      "counts":obj["counts"],
      "unknown_count":obj["unknown_count"],
      "unknown_symbols":obj["unknown_symbols"],
      "unknown_diagnostics":{
        s:{
          "reason":obj["results"][s]["info"].get("reason"),
          "sina":obj["results"][s]["info"].get("sina"),
          "nasdaq":obj["results"][s]["info"].get("nasdaq"),
          "yahoo":obj["results"][s]["info"].get("yahoo"),
          "provider_meta":obj["results"][s].get("provider_meta"),
        } for s in obj["unknown_symbols"]
      },
      "pass_count":obj["pass_count"],
      "pass_hash":obj["pass_hash"]
    },sort_keys=True))
if __name__=="__main__":main()
