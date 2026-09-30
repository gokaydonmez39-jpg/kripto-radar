#!/usr/bin/env python3
"""NASDAQ SWING X-RAY Eastmoney resumable hard-gate stage.
Official universe: NasdaqTrader. Market discovery/history accelerator: Eastmoney.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
Eastmoney never supplies G9 authority.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, random, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal
import akshare as ak

TASK_ID="6a825366222081918997094d76e6ae46"
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
SPOT_URL="https://72.push2.eastmoney.com/api/qt/clist/get"
HIST_URL="https://63.push2his.eastmoney.com/api/qt/stock/kline/get"
ROOT=Path(__file__).resolve().parent
STATE=ROOT/"eastmoney_state.json"
CAND=ROOT/"market_candidates.json"
BATCH=int(os.getenv("XRAY_EM_HISTORY_BATCH","120"))
WORKERS=int(os.getenv("XRAY_EM_HISTORY_WORKERS","8"))
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
UT="bd1d9ddb04089700cf9c27f6f7426281"

def h(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def get_json(url,params,timeout=35,retries=3):
    q=urllib.parse.urlencode(params)
    last=None
    for k in range(retries):
        try:
            req=urllib.request.Request(url+"?"+q,headers={"User-Agent":UA,"Referer":"https://quote.eastmoney.com/","Accept":"application/json,text/plain,*/*"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e
            time.sleep(0.4*(k+1))
    raise last

def get_text(url,timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def official_universe():
    text=get_text(NASDAQ_URL)
    lines=[x.strip("\r") for x in text.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    symbols=[]
    for row in rows:
        s=(row.get("Symbol") or "").strip().upper()
        if not s: continue
        if row.get("Test Issue")!="N": continue
        if row.get("ETF")=="Y": continue
        if row.get("NextShares")=="Y": continue
        symbols.append(s)
    symbols=sorted(set(symbols))
    if not footer or not symbols: raise RuntimeError("OFFICIAL_UNIVERSE_INVALID")
    return symbols,footer

def completed_sessions():
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    from datetime import timedelta
    start=(now.date()-timedelta(days=800)).isoformat()
    end=(now.date()+timedelta(days=1)).isoformat()
    sched=cal.schedule(start_date=start,end_date=end)
    out=[]
    for idx,row in sched.iterrows():
        if row["market_close"].to_pydatetime()<=now:
            out.append(idx.date().isoformat())
    if len(out)<260: raise RuntimeError("CALENDAR_TOO_SHORT")
    return out[-520:],out[-1],out[-20:]

def fnum(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except:return None

def spot_all():
    # Use AKShare's maintained Eastmoney pagination/retry implementation.
    df=ak.stock_us_spot_em()
    if df is None or df.empty:
        raise RuntimeError("EASTMONEY_SPOT_EMPTY")
    rows=[]
    for rec in df.to_dict(orient="records"):
        code=str(rec.get("代码") or "").strip().upper()
        if "." not in code:
            continue
        market,sym=code.split(".",1)
        rows.append({
          "f12":sym,"f13":market,"f14":rec.get("名称"),
          "f2":rec.get("最新价"),"f5":rec.get("成交量"),
          "f20":rec.get("总市值")
        })
    if not rows:
        raise RuntimeError("EASTMONEY_SPOT_PARSE_EMPTY")
    return rows,len(rows),None

def parse_hist(secid,asof,expected20):
    params={
      "secid":secid,"fields1":"f1,f2,f3,f4,f5,f6",
      "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
      "klt":"101","fqt":"0","beg":"20200101","end":"20500000","lmt":"2000"
    }
    try:
        d=get_json(HIST_URL,params,timeout=45,retries=2)
        kl=((d.get("data") or {}).get("klines") or [])
        by={}
        for line in kl:
            a=line.split(",")
            if len(a)<7: continue
            dt=a[0]
            try: close=float(a[2]); vol=float(a[5])
            except: continue
            if dt<=asof and close>0 and vol>0 and math.isfinite(close) and math.isfinite(vol):
                by[dt]=(close,vol)
        if asof not in by:return "UNKNOWN","ASOF_MISSING"
        if any(x not in by for x in expected20):return "UNKNOWN","EXACT20_MISSING"
        px=by[asof][0]
        dvs=sorted(by[x][0]*by[x][1] for x in expected20)
        dv20=(dvs[9]+dvs[10])/2.0
        bars=len(by)
        if px<=10:return "FAIL_PRICE",{"price":px,"dv20":dv20,"bars":bars}
        if dv20<50_000_000:return "FAIL_DV20",{"price":px,"dv20":dv20,"bars":bars}
        if bars<260:return "FAIL_HISTORY",{"price":px,"dv20":dv20,"bars":bars}
        return "PASS",{"price":px,"dv20":dv20,"bars":bars}
    except Exception as e:
        return "UNKNOWN",f"{type(e).__name__}:{str(e)[:120]}"

def load():
    if STATE.exists():
        try:return json.loads(STATE.read_text())
        except:pass
    return {}

def save(obj,path=STATE):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
    tmp.replace(path)

def main():
    official,footer=official_universe()
    _,asof,expected20=completed_sessions()
    uh=h(official)
    s=load()

    # Rebuild spot discovery once per official-universe/asof epoch.
    if s.get("universe_hash")!=uh or s.get("asof_et")!=asof:
        rows,total,pages=spot_all()
        off=set(official)
        spot={}
        missing=set(off)
        for r in rows:
            sym=str(r.get("f12") or "").upper().strip()
            if sym not in off: continue
            market=str(r.get("f13") or "").strip()
            px=fnum(r.get("f2")); mc=fnum(r.get("f20"))
            if not market: continue
            spot[sym]={"secid":f"{market}.{sym}","spot_price":px,"market_cap":mc,"name":r.get("f14")}
            missing.discard(sym)

        # Wide conservative discovery envelope only; no canonical PASS from spot values.
        # Price >=9 and MC >=1.8B prevents borderline 10/2B names from being dropped.
        queue=sorted(sym for sym,v in spot.items()
                     if v.get("spot_price") is not None and v["spot_price"]>=9
                     and v.get("market_cap") is not None and v["market_cap"]>=1_800_000_000)
        s={
          "schema":"XRAY_EASTMONEY_RESUMABLE_V1","task_id":TASK_ID,"execution":"NONE","real_money":"NO-GO",
          "unknown_never_pass":True,"source":"EASTMONEY_ACCELERATOR_NOT_G9",
          "official_footer":footer,"universe_hash":uh,"asof_et":asof,"expected20":expected20,
          "official_count":len(official),"spot_provider_total":total,"spot_pages":pages,
          "spot_matched":len(spot),"spot_missing":sorted(missing),"spot_missing_count":len(missing),
          "queue":queue,"queue_hash":h(queue),"cursor":0,"queue_total":len(queue),
          "spot":{k:spot[k] for k in queue},
          "pass":{},"unknown":{},"fail_price":0,"fail_dv20":0,"fail_history":0,
          "status":"HISTORY_PARTIAL"
        }

    start=int(s.get("cursor",0)); end=min(start+BATCH,len(s.get("queue") or []))
    batch=(s.get("queue") or [])[start:end]

    from concurrent.futures import ThreadPoolExecutor,as_completed
    results=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        fs={ex.submit(parse_hist,s["spot"][sym]["secid"],s["asof_et"],s["expected20"]):sym for sym in batch}
        for fut in as_completed(fs):
            sym=fs[fut]
            status,info=fut.result()
            results.append((sym,status,info))

    for sym,status,info in results:
        if status=="PASS":
            rec=dict(info)
            rec["eastmoney_market_cap"]=s["spot"][sym]["market_cap"]
            rec["secid"]=s["spot"][sym]["secid"]
            s["pass"][sym]=rec
            s["unknown"].pop(sym,None)
        elif status=="UNKNOWN":s["unknown"][sym]=info
        elif status=="FAIL_PRICE":s["fail_price"]+=1
        elif status=="FAIL_DV20":s["fail_dv20"]+=1
        elif status=="FAIL_HISTORY":s["fail_history"]+=1

    s["cursor"]=end
    s["processed_this_run"]=len(batch)
    s["pass_count"]=len(s["pass"]);s["unknown_count"]=len(s["unknown"])
    s["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    s["status"]="HISTORY_COMPLETE" if end>=len(s["queue"]) else "HISTORY_PARTIAL"
    s["state_hash"]=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    save(s)

    # SEC stage input: only exact PRICE/DV20/HISTORY passes; MC remains to be independently confirmed.
    cand={"schema":"XRAY_MARKET_CANDIDATES_V1","task_id":TASK_ID,"asof_et":s["asof_et"],
          "execution":"NONE","real_money":"NO-GO","source":"EASTMONEY_PRICE_DV20_HISTORY_PASS",
          "candidates":s["pass"],"candidate_count":len(s["pass"])}
    save(cand,CAND)

    print(json.dumps({"status":s["status"],"asof":s["asof_et"],"spot_matched":s["spot_matched"],
      "queue_total":s["queue_total"],"cursor":s["cursor"],"pass":s["pass_count"],
      "unknown":s["unknown_count"],"fail_price":s["fail_price"],"fail_dv20":s["fail_dv20"],
      "fail_history":s["fail_history"]},sort_keys=True))

if __name__=="__main__":
    main()
