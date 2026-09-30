#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external hard-gate shadow stage V5.

Purpose:
- Fresh NasdaqTrader identity snapshot with deterministic explicit-type exclusions.
- Recovery epoch is locked to the PASS settlement witness (currently 2026-09-29).
- Sina raw daily history is the primary zero-key shadow OHLCV accelerator.
- Eastmoney direct NASDAQ history is a bounded fallback/cross-check.
- This engine NEVER writes canonical ChatGPT Durable State and NEVER supplies G9.

Research/forward-test only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas_market_calendars as mcal
from py_mini_racer import py_mini_racer
from akshare.stock.cons import zh_js_decode

TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.7"
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
EASTMONEY_HIST_URL="https://63.push2his.eastmoney.com/api/qt/stock/kline/get"
SINA_BASE="https://finance.sina.com.cn/staticdata/us/"
ROOT=Path(__file__).resolve().parent
STATE=ROOT/"eastmoney_state.json"
CAND=ROOT/"market_candidates.json"
WITNESS=ROOT/"recovery_witness.json"

NEW_PER_RUN=int(os.getenv("XRAY_HISTORY_BATCH","60"))
MAX_ATTEMPTS=int(os.getenv("XRAY_MAX_ATTEMPTS","4"))
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
    return hashlib.sha256("\n".join(items).encode()).hexdigest()

def atomic_write(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def request_bytes(url,headers=None,timeout=20,retries=2):
    hdr={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"}
    if headers: hdr.update(headers)
    last=None
    for k in range(retries):
        try:
            req=urllib.request.Request(url,headers=hdr)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last=e
            time.sleep(0.7*(k+1)+random.uniform(0.1,0.35))
    raise last

def get_text(url,headers=None,timeout=20,retries=2):
    return request_bytes(url,headers,timeout,retries).decode("utf-8","strict")

def get_json(url,params=None,headers=None,timeout=20,retries=2):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    return json.loads(get_text(url,headers,timeout,retries))

def recovery_target():
    w=load_json(WITNESS)
    required={
      "schema":"XRAY_RECOVERY_WITNESS_V1",
      "canonical_task_id":TASK_ID,
      "source_state_revision":20,
      "source_state_hash":"709b877e39059b515c5467a6d0ef1a9b8a4fd3a05f86192f1e85539c9e64ce23",
      "settlement_result":"PASS",
      "witness_hash":"f4d083c6aff10a000b5e815fa205d3f87b54de396a3d62f4505eac99807e7f2d",
    }
    for k,v in required.items():
        if w.get(k)!=v:
            raise RuntimeError("RECOVERY_WITNESS_MISMATCH:"+k)
    target=w.get("candidate_settlement_date_et")
    if target!="2026-09-29":
        raise RuntimeError("RECOVERY_TARGET_NOT_2026_09_29")
    for sym in ("AAPL","NVDA","MSFT"):
        p=(w.get("probes") or {}).get(sym) or {}
        if p.get("pass") is not True or p.get("price_match") is not True:
            raise RuntimeError("RECOVERY_PROBE_FAIL:"+sym)
        if float(p.get("volume_relative_diff_pct",999))>0.10:
            raise RuntimeError("RECOVERY_VOLUME_GATE_FAIL:"+sym)
    return target,w

def official_nasdaq():
    text=get_text(NASDAQ_URL,timeout=30,retries=3)
    lines=[x.strip("\r") for x in text.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    included={}; excluded={}
    for row in rows:
        sym=(row.get("Symbol") or "").strip().upper()
        name=(row.get("Security Name") or "").strip()
        if not sym: continue
        reason=None
        if row.get("Test Issue")!="N": reason="TEST_ISSUE"
        elif row.get("ETF")=="Y": reason="ETF"
        elif row.get("NextShares")=="Y": reason="NEXTSHARES"
        else:
            for label,pat in TYPE_PATTERNS:
                if pat.search(name):
                    reason=label; break
        if reason: excluded[sym]={"reason":reason,"security_name":name}
        else: included[sym]=name
    if not footer or not included:
        raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return included,excluded,footer,len(rows)

def expected_sessions(target):
    cal=mcal.get_calendar("NASDAQ")
    t=datetime.fromisoformat(target).date()
    sched=cal.schedule(start_date=(t-timedelta(days=900)).isoformat(),end_date=target)
    sessions=[idx.date().isoformat() for idx,_ in sched.iterrows() if idx.date()<=t]
    if len(sessions)<260 or sessions[-1]!=target:
        raise RuntimeError("TARGET_NOT_COMPLETED_OFFICIAL_SESSION")
    return sessions[-520:],sessions[-20:]

def decode_sina(symbol,asof,expected20):
    raw=get_text(SINA_BASE+urllib.parse.quote(symbol,safe=""),timeout=14,retries=2)
    if "=" not in raw:
        raise RuntimeError("SINA_PAYLOAD_INVALID")
    token=raw.split("=",1)[1].split(";",1)[0].replace('"',"").strip()
    js=py_mini_racer.MiniRacer()
    js.eval(zh_js_decode)
    rows=js.call("d",token)
    by={}
    for row in rows or []:
        day=str(row.get("date") or "")[:10]
        try:
            close=float(row.get("close")); volume=float(row.get("volume"))
        except Exception:
            continue
        if day and day<=asof and close>0 and volume>0 and math.isfinite(close) and math.isfinite(volume):
            by[day]=(close,volume)
    return classify(by,asof,expected20,"SINA")

def decode_eastmoney(symbol,asof,expected20):
    params={
      "secid":"105."+symbol,
      "fields1":"f1,f2,f3,f4,f5,f6",
      "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
      "klt":"101","fqt":"0","beg":"20200101","end":"20500000","lmt":"2000",
    }
    data=get_json(EASTMONEY_HIST_URL,params,{"Referer":"https://quote.eastmoney.com/"},timeout=12,retries=1)
    klines=((data.get("data") or {}).get("klines") or [])
    by={}
    for line in klines:
        p=line.split(",")
        if len(p)<7: continue
        day=p[0]
        try: close=float(p[2]); volume=float(p[5])
        except Exception: continue
        if day<=asof and close>0 and volume>0 and math.isfinite(close) and math.isfinite(volume):
            by[day]=(close,volume)
    return classify(by,asof,expected20,"EASTMONEY")

def classify(by,asof,expected20,provider):
    if asof not in by:
        return "UNKNOWN_STATIC",{"reason":"ASOF_MISSING","provider":provider}
    missing=[d for d in expected20 if d not in by]
    if missing:
        return "UNKNOWN_STATIC",{"reason":"EXACT20_MISSING","dates":missing,"provider":provider}
    price=by[asof][0]
    dvs=sorted(by[d][0]*by[d][1] for d in expected20)
    dv20=(dvs[9]+dvs[10])/2.0
    bars=len(by)
    info={"price":price,"dv20":dv20,"bars":bars,"provider":provider}
    if price<=10:return "FAIL_PRICE",info
    if dv20<50_000_000:return "FAIL_DV20",info
    if bars<260:return "FAIL_HISTORY",info
    return "PASS",info

def parse_hist(symbol,asof,expected20):
    # Sina is the primary transport because GitHub shared IP repeatedly triggered
    # Eastmoney RemoteDisconnected under volume. Eastmoney is bounded fallback only.
    errors=[]
    try:
        status,info=decode_sina(symbol,asof,expected20)
        if status!="UNKNOWN_STATIC":
            return status,info
        errors.append({"provider":"SINA","info":info})
    except Exception as e:
        errors.append({"provider":"SINA","error":type(e).__name__+":"+str(e)[:140]})
    try:
        time.sleep(random.uniform(0.05,0.15))
        status,info=decode_eastmoney(symbol,asof,expected20)
        if status!="UNKNOWN_STATIC":
            return status,info
        errors.append({"provider":"EASTMONEY","info":info})
    except Exception as e:
        errors.append({"provider":"EASTMONEY","error":type(e).__name__+":"+str(e)[:140]})
    return "UNKNOWN_RETRY",errors

def exclusion_counts(excluded):
    out={}
    for v in excluded.values():out[v["reason"]]=out.get(v["reason"],0)+1
    return dict(sorted(out.items()))

def build_state(queue,names,excluded,footer,raw_count,asof,expected20,witness):
    ex_serial=[s+"|"+excluded[s]["reason"] for s in sorted(excluded)]
    return {
      "schema":"XRAY_EXTERNAL_RECOVERY_SHADOW_V5","build":BUILD,"task_id":TASK_ID,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "canonical_commit_pending":True,
      "canonical_state_source_revision":witness["source_state_revision"],
      "canonical_state_source_hash":witness["source_state_hash"],
      "recovery_witness_hash":witness["witness_hash"],
      "source":"SINA_PRIMARY_EASTMONEY_FALLBACK_SHADOW_NOT_G9",
      "identity_authority":"NASDAQTRADER_EXPLICIT_TYPE_FILTER_SHADOW",
      "official_footer":footer,"master_raw":raw_count,"asof_et":asof,"expected20":expected20,
      "queue":queue,"queue_hash":sha_lines(queue),"queue_total":len(queue),
      "security_names":{s:names[s] for s in queue},
      "explicit_excluded_count":len(excluded),"explicit_excluded_hash":sha_lines(ex_serial),
      "explicit_excluded_reason_counts":exclusion_counts(excluded),
      "cursor":0,"results":{},"status":"RECOVERY_SHADOW_PARTIAL",
    }

def count_results(results):
    out={}
    for r in results.values():
        st=r.get("status");out[st]=out.get(st,0)+1
    return dict(sorted(out.items()))

def main():
    asof,witness=recovery_target()
    names,excluded,footer,raw_count=official_nasdaq()
    _,expected20=expected_sessions(asof)
    queue=sorted(names)
    qhash=sha_lines(queue)

    state=load_json(STATE)
    if state.get("schema")!="XRAY_EXTERNAL_RECOVERY_SHADOW_V5" or state.get("queue_hash")!=qhash or state.get("asof_et")!=asof or state.get("recovery_witness_hash")!=witness["witness_hash"]:
        state=build_state(queue,names,excluded,footer,raw_count,asof,expected20,witness)

    results=state.setdefault("results",{})
    retry=[s for s in sorted(results) if results[s].get("status")=="UNKNOWN_RETRY" and int(results[s].get("attempts",0))<MAX_ATTEMPTS][:10]
    start=int(state.get("cursor",0));end=min(start+NEW_PER_RUN,len(queue))
    new=queue[start:end]
    work=[];seen=set()
    for s in retry+new:
        if s not in seen:seen.add(s);work.append(s)

    # Sequential on purpose: upstreams are more stable at low concurrency.
    for sym in work:
        status,info=parse_hist(sym,asof,expected20)
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if status=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            status="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={"status":status,"info":info,"attempts":attempts,"updated_at_utc":datetime.now(timezone.utc).isoformat()}

    state["cursor"]=end
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["counts"]=count_results(results)
    state["pending_retry"]=sum(1 for r in results.values() if r.get("status")=="UNKNOWN_RETRY" and int(r.get("attempts",0))<MAX_ATTEMPTS)
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    state["build"]=BUILD
    state["status"]="RECOVERY_SHADOW_COMPLETE" if end>=len(queue) and state["pending_retry"]==0 else "RECOVERY_SHADOW_PARTIAL"
    state["state_hash"]=hashlib.sha256(json.dumps(state,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    atomic_write(STATE,state)

    candidates={}
    for sym,r in results.items():
        if r.get("status")=="PASS":
            info=dict(r.get("info") or {});info["security_name"]=state["security_names"].get(sym);candidates[sym]=info
    atomic_write(CAND,{
      "schema":"XRAY_MARKET_CANDIDATES_SHADOW_V5","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","canonical_commit_pending":True,
      "recovery_witness_hash":witness["witness_hash"],
      "source":"NASDAQTRADER_PLUS_SINA_EASTMONEY_SHADOW",
      "candidate_count":len(candidates),"candidates":candidates,
    })

    print(json.dumps({
      "status":state["status"],"asof":asof,"queue_total":len(queue),"cursor":end,
      "processed_new":len(new),"processed_retry":len(retry),"pending_retry":state["pending_retry"],
      "counts":state["counts"],"candidate_count":len(candidates),
      "canonical_commit_pending":True,
    },sort_keys=True))

if __name__=="__main__":
    main()
