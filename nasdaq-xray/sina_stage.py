#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external hard-gate accelerator V2.
Identity: fresh NasdaqTrader directory.
Discovery prefilter: official Nasdaq web screener (wide conservative floor only).
History accelerator: Sina US daily history.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
No external source here is G9 authority or a substitute for canonical MC authority.
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

import akshare as ak
import pandas_market_calendars as mcal

TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.5"
IDENTITY_RULESET="V2_WHEN_ISSUED"
NASDAQ_DIR="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER="https://api.nasdaq.com/api/screener/stocks"
ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("XRAY_SINA_STATE", str(ROOT/"sina_state.json")))
CAND=Path(os.getenv("XRAY_SINA_CAND", str(ROOT/"sina_candidates.json")))
RESOLUTION_OVERLAY=Path(os.getenv("XRAY_HISTORY_RESOLUTION_OVERLAY", str(ROOT/"history_resolution_overlay.json")))
FULL_IDENTITY=os.getenv("XRAY_FULL_IDENTITY","0")=="1"

BATCH=int(os.getenv("XRAY_SINA_HISTORY_BATCH","100"))
RETRY_BATCH=int(os.getenv("XRAY_SINA_RETRY_BATCH","20"))
WORKERS=int(os.getenv("XRAY_SINA_HISTORY_WORKERS","8"))
MAX_ATTEMPTS=int(os.getenv("XRAY_SINA_MAX_ATTEMPTS","4"))

# Wide discovery floors only. Canonical thresholds remain $10 / $2B / $50M / 260 bars.
DISCOVERY_PRICE_FLOOR=9.0
DISCOVERY_MC_FLOOR=1_800_000_000.0
HARD_PRICE=10.0
HARD_DV20=50_000_000.0
HARD_HISTORY=260

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

TYPE_PATTERNS=[
 ("WARRANT",re.compile(r"\bwarrants?\b",re.I)),
 ("RIGHT",re.compile(r"\brights?\b",re.I)),
 ("UNIT",re.compile(r"\bunits?\b",re.I)),
 ("PREFERRED",re.compile(r"\bpreferred\b|\bpreference\b",re.I)),
 ("DEBT",re.compile(r"\bsenior notes?\b|\bsubordinated notes?\b|\bnotes? due\b|\bdebentures?\b|\bbonds?\b",re.I)),
 ("ETN",re.compile(r"\betn\b|exchange[- ]traded notes?",re.I)),
 ("FUND",re.compile(r"\bfund\b",re.I)),
 ("WHEN_ISSUED",re.compile(r"\bwhen[- ]issued\b",re.I)),
 ("SPAC",re.compile(r"\bspac\b|\bblank check\b",re.I)),
]

def sha_lines(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def request_json(url,params=None,headers=None,timeout=45):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    h={
      "User-Agent":UA,
      "Accept":"application/json,text/plain,*/*",
    }
    if headers:h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def request_text(url,timeout=35):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def official_nasdaq():
    text=request_text(NASDAQ_DIR)
    lines=[x.strip("\r") for x in text.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    included={}; excluded={}
    for row in rows:
        sym=(row.get("Symbol") or "").strip().upper()
        name=(row.get("Security Name") or "").strip()
        if not sym:continue
        reason=None
        if row.get("Test Issue")!="N":reason="TEST_ISSUE"
        elif row.get("ETF")=="Y":reason="ETF"
        elif row.get("NextShares")=="Y":reason="NEXTSHARES"
        else:
            for label,pat in TYPE_PATTERNS:
                if pat.search(name):
                    reason=label
                    break
        if reason:excluded[sym]={"reason":reason,"security_name":name}
        else:included[sym]=name
    if not footer or not included:
        raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return included,excluded,footer

def screener_rows():
    obj=request_json(
      NASDAQ_SCREENER,
      {
        "tableonly":"true",
        "limit":"25",
        "offset":"0",
        "exchange":"NASDAQ",
        "download":"true",
      },
      headers={
        "Origin":"https://www.nasdaq.com",
        "Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
      },
      timeout=60,
    )
    data=obj.get("data") or {}
    rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
    if len(rows)<1000:
        raise RuntimeError("NASDAQ_SCREENER_TOO_FEW_ROWS")
    return rows

def num(x):
    try:
        if x is None:return None
        s=str(x).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--"}:return None
        v=float(s)
        return v if math.isfinite(v) else None
    except Exception:
        return None

def build_discovery(official,force_all=False):
    rows=screener_rows()
    off=set(official)
    prefilter={}
    missing=set(off)
    exact_hard_mc_price_count=0
    for r in rows:
        sym=str(r.get("symbol") or "").strip().upper()
        if sym not in off:continue
        missing.discard(sym)
        px=num(r.get("lastsale"))
        mc=num(r.get("marketCap"))
        vol=num(r.get("volume"))
        if px is not None and mc is not None and px>HARD_PRICE and mc>=2_000_000_000:
            exact_hard_mc_price_count+=1
        if force_all:
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
              "discovery_reason":"FULL_IDENTITY_NO_PREFILTER",
            }
            continue
        if px is None or mc is None:
            # Fail-closed discovery: an official Nasdaq-listed symbol must never
            # disappear merely because the screener omitted a gating field.
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
              "discovery_reason":"SCREENER_FIELD_MISSING_FORCE_QUEUE",
            }
            continue
        if px>=DISCOVERY_PRICE_FLOOR and mc>=DISCOVERY_MC_FLOOR:
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
            }
    for sym in sorted(missing):
        # Official-directory identity exists but the web screener omitted it.
        # Force it into downstream PRICE/DV20/HISTORY; MC remains UNKNOWN
        # unless a later authoritative resolver proves it.
        prefilter[sym]={
          "screener_price":None,
          "screener_market_cap":None,
          "screener_volume":None,
          "sector":None,
          "industry":None,
          "country":None,
          "discovery_reason":"OFFICIAL_SCREENER_MISSING_FORCE_QUEUE",
        }
    queue=sorted(prefilter)
    return queue,prefilter,{
      "rows_returned":len(rows),
      "official_matched":len(off)-len(missing),
      "official_missing":len(missing),
      "official_missing_hash":sha_lines(sorted(missing)),
      "discovery_queue_total":len(queue),
      "hard_price_mc_snapshot_count":exact_hard_mc_price_count,
      "discovery_price_floor":DISCOVERY_PRICE_FLOOR,
      "discovery_mc_floor":DISCOVERY_MC_FLOOR,
      "authority":"FULL_IDENTITY_NO_PREFILTER" if force_all else "DISCOVERY_PREFILTER_ONLY_NOT_CANONICAL_MC",
      "full_identity":bool(force_all),
    }

def completed_sessions():
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    sched=cal.schedule(
      start_date=(now.date()-timedelta(days=900)).isoformat(),
      end_date=(now.date()+timedelta(days=1)).isoformat(),
    )
    sessions=[]
    for idx,row in sched.iterrows():
        if row["market_close"].to_pydatetime()<=now:
            sessions.append(idx.date().isoformat())
    if len(sessions)<260:
        raise RuntimeError("CALENDAR_TOO_SHORT")
    return sessions[-1],sessions[-20:]

def parse_hist(sym,asof,expected20):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:
            return "UNKNOWN_STATIC","SINA_HISTORY_EMPTY"
        by={}
        for rec in df.to_dict(orient="records"):
            d=rec.get("date")
            try:
                day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                close=float(rec.get("close"))
                volume=float(rec.get("volume"))
            except Exception:
                continue
            if day<=asof and close>0 and volume>0 and math.isfinite(close) and math.isfinite(volume):
                by[day]=(close,volume)
        bars=len(by)
        # Hard-gate short circuits are safe: a proven failure at any mandatory
        # gate is terminal non-PASS even when a later/earlier provider field is missing.
        if asof in by:
            price=by[asof][0]
            if price<=HARD_PRICE:
                return "FAIL_PRICE",{"price":price,"bars":bars,"proof":"ASOF_CLOSE"}
        else:
            if bars<HARD_HISTORY:
                return "FAIL_HISTORY",{"bars":bars,"reason":"DAILY_LT260","proof":"KNOWN_HISTORY_COUNT"}
            return "UNKNOWN_STATIC",{"reason":"ASOF_MISSING","bars":bars}

        if bars<HARD_HISTORY:
            return "FAIL_HISTORY",{"price":price,"bars":bars,"reason":"DAILY_LT260","proof":"KNOWN_HISTORY_COUNT"}

        missing=[d for d in expected20 if d not in by]
        known_dv=[by[d][0]*by[d][1] for d in expected20 if d in by]
        if missing:
            # Median interval proof with unknown session dollar-volume constrained
            # only to nonnegative values. No synthetic bar is inserted.
            m=len(missing)
            low=sorted(known_dv+[0.0]*m)
            lower=(low[9]+low[10])/2.0
            high=sorted(known_dv+[float("inf")]*m)
            upper=(high[9]+high[10])/2.0
            info={
              "price":price,"bars":bars,"reason":"EXACT20_MISSING",
              "dates":missing,"known_session_count":len(known_dv),
              "dv20_lower_bound":lower,
              "dv20_upper_bound":None if math.isinf(upper) else upper,
              "no_synthetic_bar":True,
            }
            if upper < HARD_DV20:
                info["proof"]="DV20_UPPER_BOUND_LT_GATE"
                return "FAIL_DV20",info
            info["reason"]="EXACT20_INCOMPLETE_NEVER_PASS"
            return "UNKNOWN_STATIC",info

        dvs=sorted(known_dv)
        dv20=(dvs[9]+dvs[10])/2.0
        info={"price":price,"dv20":dv20,"bars":bars}
        if dv20<HARD_DV20:return "FAIL_DV20",info
        return "PASS",info
    except Exception as e:
        return "UNKNOWN_RETRY",f"{type(e).__name__}:{str(e)[:200]}"

def load_resolution_overlay(asof):
    meta={"status":"ABSENT"}
    if not RESOLUTION_OVERLAY.exists():
        return {},meta
    try:
        obj=json.loads(RESOLUTION_OVERLAY.read_text(encoding="utf-8"))
        if obj.get("schema")!="XRAY_HISTORY_IDENTITY_RESOLUTION_OVERLAY_V1":
            raise ValueError("SCHEMA")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
        if obj.get("base_asof_et")!=asof:
            raise ValueError("ASOF_MISMATCH")
        ts=datetime.fromisoformat(str(obj.get("generated_at_utc")).replace("Z","+00:00"))
        if ts.tzinfo is None:
            raise ValueError("TIMESTAMP_TZ")
        age_h=(datetime.now(timezone.utc)-ts.astimezone(timezone.utc)).total_seconds()/3600.0
        max_age=float(obj.get("max_age_hours",24))
        if age_h < -0.25 or age_h > max_age:
            return {},{"status":"STALE","age_hours":age_h,"max_age_hours":max_age}
        res=obj.get("resolutions") or {}
        if not isinstance(res,dict):
            raise ValueError("RESOLUTIONS")
        return res,{"status":"PASS","age_hours":age_h,"generated_at_utc":obj.get("generated_at_utc")}
    except Exception as e:
        return {},{"status":"INVALID","reason":f"{type(e).__name__}:{str(e)[:160]}"}

def resolution_result(sym,ov,expected20):
    if not isinstance(ov,dict):
        return "UNKNOWN_STATIC",{"reason":"RESOLUTION_OVERLAY_INVALID","symbol":sym}
    d=ov.get("decision")
    if d=="FAIL_HISTORY":
        bars=ov.get("bars")
        if not isinstance(bars,int) or bars>=HARD_HISTORY:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_HISTORY_INVALID","symbol":sym}
        return "FAIL_HISTORY",{"bars":bars,"resolution_source":ov.get("source"),"reason":"DAILY_LT260"}
    if d=="FAIL_DV20":
        px=num(ov.get("price")); dv=num(ov.get("dv20")); bars=ov.get("bars")
        if px is None or dv is None or not isinstance(bars,int) or dv>=HARD_DV20:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_DV20_INVALID","symbol":sym}
        return "FAIL_DV20",{"price":px,"dv20":dv,"bars":bars,"resolution_source":ov.get("source"),"proof":ov.get("proof")}
    if d=="FAIL_PRICE":
        px=num(ov.get("price")); bars=ov.get("bars")
        if px is None or px>HARD_PRICE:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_PRICE_INVALID","symbol":sym}
        return "FAIL_PRICE",{"price":px,"bars":bars,"resolution_source":ov.get("source")}
    if d=="EXCLUDE":
        reason=str(ov.get("reason") or "")
        if reason not in {"SPAC_BLANK_CHECK","PREFERRED","WHEN_ISSUED"}:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_EXCLUDE_INVALID","symbol":sym}
        return "FAIL_IDENTITY_TYPE",{"reason":reason,"proof":ov.get("proof"),"resolution_source":ov.get("source")}
    if d=="BLOCK_CURRENT_RUN":
        if ov.get("trade_status")!="Halted" or not ov.get("last_bar"):
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_BLOCK_INVALID","symbol":sym}
        return "BLOCK_CURRENT_RUN",{"reason":ov.get("reason"),"trade_status":"Halted","last_bar":ov.get("last_bar"),"resolution_source":ov.get("source")}
    if d=="PASS_HARD_GATES":
        px=num(ov.get("price")); bars=ov.get("bars")
        lo=num(ov.get("dv20_lower_bound")); hi=num(ov.get("dv20_upper_bound"))
        missing=ov.get("missing_sessions") or []; known=ov.get("known_session_count")
        if (
          px is None or px<=HARD_PRICE or not isinstance(bars,int) or bars<HARD_HISTORY
          or lo is None or hi is None or lo<HARD_DV20 or hi<lo
          or ov.get("no_synthetic_bar") is not True
          or not isinstance(known,int) or known!=20 or missing!=[]
          or lo!=hi
        ):
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_PASS_BOUND_INVALID","symbol":sym}
        return "PASS",{
          "price":px,"bars":bars,
          "dv20_gate_pass_by_bound":True,
          "dv20_lower_bound":lo,"dv20_upper_bound":hi,
          "known_session_count":known,"missing_sessions":missing,
          "no_synthetic_bar":True,
          "resolution_source":ov.get("source"),
          "proof":ov.get("proof"),
        }
    return "UNKNOWN_STATIC",{"reason":"RESOLUTION_DECISION_UNKNOWN","symbol":sym,"decision":d}

def load(path):
    if path.exists():
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:pass
    return {}

def write(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def exclusion_counts(excluded):
    out={}
    for x in excluded.values():out[x["reason"]]=out.get(x["reason"],0)+1
    return dict(sorted(out.items()))

def result_counts(results):
    out={}
    for x in results.values():
        k=x.get("status")
        out[k]=out.get(k,0)+1
    return dict(sorted(out.items()))

def main():
    names,excluded,footer=official_nasdaq()
    asof,expected20=completed_sessions()
    state=load(STATE)
    epoch_key=IDENTITY_RULESET+"|"+footer+"|"+asof

    if state.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2" or state.get("epoch_key")!=epoch_key:
        queue,discovery,meta=build_discovery(names,FULL_IDENTITY)
        ex_serial=[s+"|"+excluded[s]["reason"] for s in sorted(excluded)]
        state={
          "schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
          "build":BUILD,
          "task_id":TASK_ID,
          "execution":"NONE",
          "real_money":"NO-GO",
          "unknown_never_pass":True,
          "epoch_key":epoch_key,
          "asof_et":asof,
          "expected20":expected20,
          "official_footer":footer,
          "identity_authority":"NASDAQTRADER_EXPLICIT_TYPE_FILTER_V2_WHEN_ISSUED",
          "identity_ruleset":IDENTITY_RULESET,
          "discovery_source":"NASDAQTRADER_FULL_IDENTITY_PLUS_NASDAQ_SCREENER_METADATA_ONLY" if FULL_IDENTITY else "NASDAQ_OFFICIAL_WEB_SCREENER_PREFILTER_ONLY",
          "history_source":"SINA_US_DAILY_ACCELERATOR_NOT_G9",
          "queue":queue,
          "queue_hash":sha_lines(queue),
          "queue_total":len(queue),
          "discovery":discovery,
          "discovery_meta":meta,
          "security_names":{s:names[s] for s in queue},
          "explicit_excluded_count":len(excluded),
          "explicit_excluded_hash":sha_lines(ex_serial),
          "explicit_excluded_reason_counts":exclusion_counts(excluded),
          "cursor":0,
          "results":{},
          "status":"HISTORY_PARTIAL",
        }

    queue=state["queue"]
    results=state.setdefault("results",{})
    retry=[
      s for s in sorted(results)
      if results[s].get("status")=="UNKNOWN_RETRY"
      and int(results[s].get("attempts",0))<MAX_ATTEMPTS
    ][:RETRY_BATCH]

    start=int(state.get("cursor",0))
    end=min(start+BATCH,len(queue))
    new=queue[start:end]
    work=[];seen=set()
    for s in retry+new:
        if s not in seen:
            seen.add(s);work.append(s)

    done=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(parse_hist,s,asof,expected20):s for s in work}
        for fut in as_completed(futs):
            sym=futs[fut]
            status,info=fut.result()
            done.append((sym,status,info))

    for sym,status,info in done:
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if status=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            status="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={
          "status":status,
          "info":info,
          "attempts":attempts,
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
        }

    resolution_overlay,resolution_overlay_meta=load_resolution_overlay(asof)
    for sym,ov in sorted(resolution_overlay.items()):
        if sym not in queue:
            continue
        status,info=resolution_result(sym,ov,expected20)
        prev=results.get(sym) or {}
        results[sym]={
          "status":status,
          "info":info,
          "attempts":int(prev.get("attempts",0)),
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "resolution_overlay":True,
        }
    state["resolution_overlay_meta"]=resolution_overlay_meta

    # Explicit Nasdaq screener industry classification as Blank Checks is a
    # legal/shell blocker, not a history-provider UNKNOWN. This does not
    # declare an operating de-SPAC a shell; it only blocks symbols that the
    # same-run Nasdaq metadata explicitly classifies as Blank Checks.
    for sym in queue:
        disc=(state.get("discovery") or {}).get(sym) or {}
        if str(disc.get("industry") or "").strip().lower()=="blank checks":
            prev=results.get(sym) or {}
            results[sym]={
              "status":"BLOCK_LEGAL_SHELL",
              "info":{
                "reason":"NASDAQ_SCREENER_INDUSTRY_BLANK_CHECKS",
                "source":"NASDAQ_SAME_RUN_SCREENER_METADATA",
                "security_name":(state.get("security_names") or {}).get(sym),
              },
              "attempts":int(prev.get("attempts",0)),
              "updated_at_utc":datetime.now(timezone.utc).isoformat(),
            }

    state["cursor"]=end
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["counts"]=result_counts(results)
    state["pending_retry"]=sum(
      1 for x in results.values()
      if x.get("status")=="UNKNOWN_RETRY" and int(x.get("attempts",0))<MAX_ATTEMPTS
    )
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    unknown_count=sum(1 for x in results.values() if str(x.get("status","")).startswith("UNKNOWN"))
    state["unknown_count"]=unknown_count
    state["status"]="HISTORY_COMPLETE" if end>=len(queue) and state["pending_retry"]==0 and unknown_count==0 else "HISTORY_PARTIAL"
    state["state_hash"]=hashlib.sha256(
      json.dumps(state,sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()
    write(STATE,state)

    candidates={}
    for sym,r in results.items():
        if r.get("status")!="PASS":continue
        info=dict(r.get("info") or {})
        info["security_name"]=state["security_names"].get(sym)
        info["screener_market_cap_shadow"]=state["discovery"][sym].get("screener_market_cap")
        info["screener_price_shadow"]=state["discovery"][sym].get("screener_price")
        candidates[sym]=info

    cand={
      "schema":"XRAY_SINA_CANDIDATES_V2",
      "task_id":TASK_ID,
      "asof_et":asof,
      "execution":"NONE",
      "real_money":"NO-GO",
      "candidate_count":len(candidates),
      "source":"NASDAQTRADER_FULL_IDENTITY_PLUS_SINA_WITH_TTL_FAIL_CLOSED_RESOLUTION_OVERLAY" if FULL_IDENTITY else "NASDAQTRADER_IDENTITY_PLUS_NASDAQ_SCREENER_DISCOVERY_PLUS_SINA_WITH_TTL_FAIL_CLOSED_RESOLUTION_OVERLAY",
      "market_cap_authority":"UNRESOLVED_UNTIL_CANONICAL_MC_POLICY",
      "candidates":candidates,
    }
    write(CAND,cand)

    print(json.dumps({
      "status":state["status"],
      "asof":asof,
      "queue_total":len(queue),
      "cursor":end,
      "processed_new":len(new),
      "processed_retry":len(retry),
      "pending_retry":state["pending_retry"],
      "counts":state["counts"],
      "candidate_count":len(candidates),
      "discovery_meta":state["discovery_meta"],
    },sort_keys=True))

if __name__=="__main__":
    main()
