#!/usr/bin/env python3
"""NASDAQ SWING X-RAY Sina resumable hard-gate accelerator V1.
Identity authority: fresh NasdaqTrader directory + deterministic explicit exclusions.
Discovery accelerator: Sina US spot sorted by market cap.
OHLCV accelerator: Sina US daily history.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
This external engine is shadow/recovery data-plane evidence; it never supplies G9.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median

import akshare as ak
import pandas_market_calendars as mcal

TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.1"
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
ROOT=Path(__file__).resolve().parent
STATE=ROOT/"sina_state.json"
CAND=ROOT/"sina_candidates.json"

NEW_PER_RUN=int(os.getenv("XRAY_SINA_HISTORY_BATCH","500"))
RETRY_PER_RUN=int(os.getenv("XRAY_SINA_RETRY_BATCH","50"))
WORKERS=int(os.getenv("XRAY_SINA_HISTORY_WORKERS","8"))
MAX_ATTEMPTS=int(os.getenv("XRAY_SINA_MAX_ATTEMPTS","4"))
DISCOVERY_PRICE_FLOOR=9.0
DISCOVERY_MC_FLOOR=1_800_000_000.0
HARD_PRICE=10.0
HARD_DV20=50_000_000.0
HARD_HISTORY=260
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

TYPE_PATTERNS=[
 ("WARRANT",re.compile(r"\bwarrants?\b",re.I)),
 ("RIGHT",re.compile(r"\brights?\b",re.I)),
 ("UNIT",re.compile(r"\bunits?\b",re.I)),
 ("PREFERRED",re.compile(r"\bpreferred\b|\bpreference\b",re.I)),
 ("DEBT",re.compile(r"\bsenior notes?\b|\bsubordinated notes?\b|\bnotes? due\b|\bdebentures?\b|\bbonds?\b",re.I)),
 ("ETN",re.compile(r"\betn\b|exchange[- ]traded notes?",re.I)),
 ("FUND",re.compile(r"\bfund\b",re.I)),
]

def sha_lines(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def get_text(url,timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def official_nasdaq():
    text=get_text(NASDAQ_URL)
    lines=[line.strip("\r") for line in text.splitlines() if line.strip()]
    footer=next((line for line in reversed(lines) if line.startswith("File Creation Time:")),None)
    body="\n".join(line for line in lines if not line.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    included={}; excluded={}
    for row in rows:
        symbol=(row.get("Symbol") or "").strip().upper()
        name=(row.get("Security Name") or "").strip()
        if not symbol: continue
        reason=None
        if row.get("Test Issue")!="N": reason="TEST_ISSUE"
        elif row.get("ETF")=="Y": reason="ETF"
        elif row.get("NextShares")=="Y": reason="NEXTSHARES"
        else:
            for label,pat in TYPE_PATTERNS:
                if pat.search(name):
                    reason=label; break
        if reason: excluded[symbol]={"reason":reason,"security_name":name}
        else: included[symbol]=name
    if not footer or not included: raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return included,excluded,footer

def completed_sessions():
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    sched=cal.schedule(
      start_date=(now.date()-timedelta(days=900)).isoformat(),
      end_date=(now.date()+timedelta(days=1)).isoformat()
    )
    sessions=[]
    for idx,row in sched.iterrows():
        if row["market_close"].to_pydatetime()<=now:
            sessions.append(idx.date().isoformat())
    if len(sessions)<260: raise RuntimeError("CALENDAR_TOO_SHORT")
    return sessions[-520:],sessions[-1],sessions[-20:]

def urshift(x,n):
    return (x & 0xffffffff) >> (n & 31)

def r64(s,b):
    return urshift((s | (s << 6)),b%6)&63

def sina_hash(s):
    alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$'
    a=[]; c=[]
    bs=s.encode("utf-8")
    for i,c0 in enumerate(bs):
        c.append(c0)
        if len(c)==3 or i==len(bs)-1:
            while len(c)<3:c.append(0)
            a.extend([
              (c[0]>>2)&63,
              ((c[1]>>4)|(c[0]<<6))&63,
              ((c[1]<<4)|(c[2]>>2))&63,
              c[2]&63
            ])
            c=[]
    while len(a)<16:a.append(0)
    rr=0
    for i in range(len(a)):
        rr ^= (r64(a[i]^(rr|i),i)^r64(i,rr))&63
    for i in range(len(a)):
        a[i]=(r64((rr|(i&a[i])),rr)^a[i])&63
        rr+=a[i]
    for i in range(16,len(a)):
        a[i%16]^=(a[i]+(i>>4))&63
    return ''.join(alphabet[a[i]] for i in range(16))

def sina_spot_page(page,num=20):
    decoded=f"US_CategoryService.getList?page={page}&num={num}&sort=mktcap&asc=0&market=&id="
    token=sina_hash(decoded)
    base=f"http://stock.finance.sina.com.cn/usstock/api/jsonp.php/IO.XSRV2.CallbackList[{token}]/US_CategoryService.getList"
    params={"page":str(page),"num":str(num),"sort":"mktcap","asc":"0","market":"","id":""}
    url=base+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Referer":"https://finance.sina.com.cn/stock/usstock/sector.shtml"})
    with urllib.request.urlopen(req,timeout=30) as r:
        txt=r.read().decode("utf-8","replace")
    start=txt.find("({"); end=txt.rfind(");")
    if start<0 or end<0: raise RuntimeError("SINA_SPOT_JSONP_PARSE_FAIL")
    return json.loads(txt[start+1:end])

def fnum(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None

def build_spot_queue(official):
    rows_seen=0; pages=0; kept={}
    reported_total=None
    for page in range(1,1200):
        obj=sina_spot_page(page)
        pages=page
        if reported_total is None:
            try: reported_total=int(obj.get("count"))
            except Exception: reported_total=None
        rows=obj.get("data") or []
        if not rows: break
        rows_seen+=len(rows)
        page_mc=[]
        for r in rows:
            mc=fnum(r.get("mktcap"))
            if mc is not None: page_mc.append(mc)
            sym=str(r.get("symbol") or "").strip().upper()
            market=str(r.get("market") or "").strip().upper()
            px=fnum(r.get("price"))
            if sym not in official or market!="NASDAQ": continue
            if px is None or mc is None: continue
            if px>=DISCOVERY_PRICE_FLOOR and mc>=DISCOVERY_MC_FLOOR:
                kept[sym]={
                  "spot_price":px,
                  "spot_market_cap":mc,
                  "spot_volume":fnum(r.get("volume")),
                  "name":r.get("name"),
                  "market":market
                }
        # Sorted descending by market cap across all US rows. Once entire page
        # is below the conservative floor, later pages cannot contain candidates.
        if page_mc and max(page_mc)<DISCOVERY_MC_FLOOR:
            break
        time.sleep(0.04)
    queue=sorted(kept)
    return queue,kept,{
      "pages":pages,
      "rows_seen":rows_seen,
      "reported_total":reported_total,
      "discovery_price_floor":DISCOVERY_PRICE_FLOOR,
      "discovery_mc_floor":DISCOVERY_MC_FLOOR,
    }

def parse_hist(symbol,asof,expected20):
    try:
        df=ak.stock_us_daily(symbol=symbol,adjust="")
        if df is None or df.empty:
            return "UNKNOWN_STATIC","SINA_HISTORY_EMPTY"
        by={}
        for rec in df.to_dict(orient="records"):
            dt=rec.get("date")
            try:
                day=dt.date().isoformat() if hasattr(dt,"date") else str(dt)[:10]
                close=float(rec.get("close")); volume=float(rec.get("volume"))
            except Exception:
                continue
            if day<=asof and close>0 and volume>0 and math.isfinite(close) and math.isfinite(volume):
                by[day]=(close,volume)
        if asof not in by:
            return "UNKNOWN_STATIC","ASOF_MISSING"
        missing=[d for d in expected20 if d not in by]
        if missing:
            return "UNKNOWN_STATIC",{"reason":"EXACT20_MISSING","dates":missing}
        price=by[asof][0]
        dvs=sorted(by[d][0]*by[d][1] for d in expected20)
        dv20=(dvs[9]+dvs[10])/2.0
        bars=len(by)
        info={"price":price,"dv20":dv20,"bars":bars}
        if price<=HARD_PRICE:return "FAIL_PRICE",info
        if dv20<HARD_DV20:return "FAIL_DV20",info
        if bars<HARD_HISTORY:return "FAIL_HISTORY",info
        return "PASS",info
    except Exception as exc:
        return "UNKNOWN_RETRY",f"{type(exc).__name__}:{str(exc)[:180]}"

def load_json(path):
    if path.exists():
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:pass
    return {}

def atomic_write(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def exclusion_counts(excluded):
    out={}
    for v in excluded.values():out[v["reason"]]=out.get(v["reason"],0)+1
    return dict(sorted(out.items()))

def count_results(results):
    out={}
    for r in results.values():out[r.get("status")]=out.get(r.get("status"),0)+1
    return dict(sorted(out.items()))

def build_state(queue,spot,names,excluded,footer,asof,expected20,spot_meta):
    ex_serial=[s+"|"+excluded[s]["reason"] for s in sorted(excluded)]
    return {
      "schema":"XRAY_SINA_RESUMABLE_V1","build":BUILD,"task_id":TASK_ID,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "identity_authority":"NASDAQTRADER_EXPLICIT_TYPE_FILTER_V1",
      "source":"SINA_SPOT_AND_HISTORY_ACCELERATOR_NOT_G9",
      "official_footer":footer,"asof_et":asof,"expected20":expected20,
      "queue":queue,"queue_hash":sha_lines(queue),"queue_total":len(queue),
      "security_names":{s:names[s] for s in queue},
      "spot":{s:spot[s] for s in queue},
      "spot_meta":spot_meta,
      "explicit_excluded_count":len(excluded),
      "explicit_excluded_hash":sha_lines(ex_serial),
      "explicit_excluded_reason_counts":exclusion_counts(excluded),
      "cursor":0,"results":{},"status":"HISTORY_PARTIAL"
    }

def main():
    names,excluded,footer=official_nasdaq()
    _,asof,expected20=completed_sessions()
    state=load_json(STATE)

    # Rebuild discovery only when official snapshot / ASOF changes.
    needs_rebuild=(
      state.get("schema")!="XRAY_SINA_RESUMABLE_V1"
      or state.get("asof_et")!=asof
      or state.get("official_footer")!=footer
    )
    if needs_rebuild:
        queue,spot,spot_meta=build_spot_queue(set(names))
        state=build_state(queue,spot,names,excluded,footer,asof,expected20,spot_meta)

    queue=state["queue"]; results=state.setdefault("results",{})
    retry=[s for s in sorted(results)
           if results[s].get("status")=="UNKNOWN_RETRY"
           and int(results[s].get("attempts",0))<MAX_ATTEMPTS][:RETRY_PER_RUN]
    start=int(state.get("cursor",0)); end=min(start+NEW_PER_RUN,len(queue))
    new=queue[start:end]
    work=[]; seen=set()
    for s in retry+new:
        if s not in seen:
            seen.add(s); work.append(s)

    run_results=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(parse_hist,s,asof,expected20):s for s in work}
        for fut in as_completed(futs):
            s=futs[fut]
            status,info=fut.result()
            run_results.append((s,status,info))

    for sym,status,info in run_results:
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if status=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            status="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={
          "status":status,"info":info,"attempts":attempts,
          "updated_at_utc":datetime.now(timezone.utc).isoformat()
        }

    state["cursor"]=end
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["counts"]=count_results(results)
    state["pending_retry"]=sum(
      1 for r in results.values()
      if r.get("status")=="UNKNOWN_RETRY" and int(r.get("attempts",0))<MAX_ATTEMPTS
    )
    state["build"]=BUILD
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    state["status"]="HISTORY_COMPLETE" if end>=len(queue) and state["pending_retry"]==0 else "HISTORY_PARTIAL"
    state["state_hash"]=hashlib.sha256(json.dumps(state,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    atomic_write(STATE,state)

    candidates={}
    for sym,r in results.items():
        if r.get("status")!="PASS":continue
        info=dict(r.get("info") or {})
        info["security_name"]=state["security_names"].get(sym)
        info["spot_market_cap"]=state["spot"][sym].get("spot_market_cap")
        info["spot_price"]=state["spot"][sym].get("spot_price")
        candidates[sym]=info
    cand={
      "schema":"XRAY_SINA_CANDIDATES_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO",
      "source":"NASDAQTRADER_PLUS_SINA_PRICE_DV20_HISTORY_SHADOW",
      "candidate_count":len(candidates),"candidates":candidates
    }
    atomic_write(CAND,cand)

    print(json.dumps({
      "status":state["status"],"asof":asof,"queue_total":len(queue),
      "spot_pages":state["spot_meta"]["pages"],"spot_rows_seen":state["spot_meta"]["rows_seen"],
      "cursor":end,"processed_new":len(new),"processed_retry":len(retry),
      "pending_retry":state["pending_retry"],"counts":state["counts"],
      "candidate_count":len(candidates)
    },sort_keys=True))

if __name__=="__main__":
    main()
