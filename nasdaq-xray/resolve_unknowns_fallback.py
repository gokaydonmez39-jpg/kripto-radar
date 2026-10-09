#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal
from functools import lru_cache
from history_transport_cache_guard import exact_recent_sessions

ROOT=Path(__file__).resolve().parent
MANIFEST=Path(os.getenv("XRAY_UNKNOWN_MANIFEST", str(ROOT/"canonical_full_hard_gate_20260930_unknowns.json")))
OUT=Path(os.getenv("XRAY_RESOLUTION_OUT", str(ROOT/"history_resolution_overlay.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
HARD_PRICE=5.0
HARD_DV30=50_000_000.0
HARD_HISTORY=260
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")
RESOLVE_WORKERS=max(1,int(os.getenv("XRAY_RESOLVER_WORKERS","8")))

def req_json(url, params=None, timeout=30):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,
        "Accept":"application/json,text/plain,*/*",
        "Accept-Language":"en-US,en;q=0.9",
        "Referer":"https://www.nasdaq.com/",
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def num(x):
    try:
        if x is None:return None
        s=str(x).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--","-"}:return None
        v=float(s)
        return v if math.isfinite(v) else None
    except Exception:return None

def expected30(asof):
    cal=mcal.get_calendar("NASDAQ")
    start=(datetime.fromisoformat(asof).date()-timedelta(days=60)).isoformat()
    sched=cal.schedule(start_date=start,end_date=asof)
    ds=[x.date().isoformat() for x in sched.index if x.date().isoformat()<=asof]
    if len(ds)<30: raise RuntimeError("CALENDAR_LT30")
    return ds[-30:]

def nasdaq_hist(sym,asof):
    end=datetime.fromisoformat(asof).date()
    start=end-timedelta(days=1000)
    obj=req_json(
        f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(sym)}/historical",
        {
            "assetclass":"stocks",
            "fromdate":start.strftime("%m/%d/%Y"),
            "todate":end.strftime("%m/%d/%Y"),
            "limit":"5000",
        },
        timeout=35,
    )
    rows=(((obj.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    by={}
    for r in rows:
        ds=str(r.get("date") or "").strip()
        day=None
        for fmt in ("%m/%d/%Y","%m/%d/%y"):
            try:
                day=datetime.strptime(ds,fmt).date().isoformat();break
            except Exception:pass
        if not day:continue
        close=num(r.get("close") or r.get("close/last"))
        vol=num(r.get("volume"))
        if day<=asof and close is not None and close>0 and vol is not None and vol>=0:
            by[day]=(close,vol)
    return by,{"rows":len(rows),"usable":len(by)}

def yahoo_hist(sym,asof):
    end=datetime.fromisoformat(asof).replace(tzinfo=NY)+timedelta(days=1)
    start=end-timedelta(days=1000)
    ticker=sym.replace(".","-")
    obj=req_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}",
        {
            "period1":int(start.timestamp()),
            "period2":int(end.timestamp()),
            "interval":"1d",
            "events":"history",
            "includeAdjustedClose":"false",
        },
        timeout=25,
    )
    res=((obj.get("chart") or {}).get("result") or [])
    if not res:return {},{"error":((obj.get("chart") or {}).get("error"))}
    r=res[0]
    ts=r.get("timestamp") or []
    q=(((r.get("indicators") or {}).get("quote") or [{}])[0])
    closes=q.get("close") or []
    vols=q.get("volume") or []
    by={}
    for t,c,v in zip(ts,closes,vols):
        close=num(c); vol=num(v)
        if close is None or close<=0 or vol is None or vol<0:continue
        day=datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat()
        if day<=asof:by[day]=(close,vol)
    meta=r.get("meta") or {}
    return by,{"usable":len(by),"firstTradeDate":meta.get("firstTradeDate"),"exchangeName":meta.get("exchangeName")}

@lru_cache(maxsize=16)
def _completed_weekly_close_days(asof):
    asof_date=datetime.fromisoformat(asof).date()
    start=(asof_date-timedelta(days=800)).isoformat()
    end=(asof_date+timedelta(days=7)).isoformat()
    schedule=mcal.get_calendar("NASDAQ").schedule(start_date=start,end_date=end)
    week_last={}
    for idx in schedule.index:
        d=idx.date()
        iso=d.isocalendar()
        week_last[(iso.year,iso.week)]=d.isoformat()
    return frozenset(d for d in week_last.values() if d<=asof)

def week_count(by,asof):
    """Observed official completed weekly closes, not arbitrary calendar weeks."""
    return len(set(by).intersection(_completed_weekly_close_days(asof)))

def classify(by,asof,exp30,source):
    bars=len(by)
    if asof not in by:
        return None,{"reason":"ASOF_MISSING","bars":bars,"source":source}
    price=by[asof][0]
    if price<HARD_PRICE:
        return "FAIL_PRICE",{"price":price,"bars":bars,"source":source,"proof":"EXACT_ASOF_DAILY_CLOSE"}
    if bars<HARD_HISTORY:
        return "POTENTIAL_FAIL_HISTORY",{"price":price,"bars":bars,"source":source,
                                         "reason":"FEWER_THAN_260_OBSERVED_BARS_NOT_IPO_PROOF"}
    if not exact_recent_sessions(set(by),asof):
        return "POTENTIAL_FAIL_HISTORY",{"price":price,"bars":bars,"source":source,
                                         "reason":"LATEST_260_OFFICIAL_SESSIONS_INCOMPLETE"}
    completed_weeks=week_count(by,asof)
    if completed_weeks<52:
        return "POTENTIAL_FAIL_HISTORY",{"price":price,"bars":bars,"source":source,
                                         "reason":"FEWER_THAN_52_COMPLETED_WEEKLY_CLOSES",
                                         "completed_weeks":completed_weeks}
    vals=[by[d][0]*by[d][1] for d in exp30 if d in by]
    miss=[d for d in exp30 if d not in by]
    if not miss:
        s=sorted(vals); dv=(s[14]+s[15])/2.0
        if dv<HARD_DV30:
            return "FAIL_DV30",{"price":price,"dv30":dv,"bars":bars,"source":source,"proof":"EXACT30_MEDIAN"}
        return "PASS_HARD_GATES",{
            "price":price,"bars":bars,"dv30_lower_bound":dv,"dv30_upper_bound":dv,
            "known_session_count":30,"missing_sessions":[],"no_synthetic_bar":True,
            "source":source,"proof":"EXACT30_MEDIAN",
        }
    m=len(miss)
    low=sorted(vals+[0.0]*m)
    lower=(low[14]+low[15])/2.0
    high=sorted(vals+[float("inf")]*m)
    upper=(high[14]+high[15])/2.0
    if upper<HARD_DV30:
        return "FAIL_DV30",{
            "price":price,"dv30":upper,"bars":bars,"source":source,
            "proof":"DV30_UPPER_BOUND_LT_GATE","missing_sessions":miss,
            "known_session_count":len(vals),"no_synthetic_bar":True,
        }
    return None,{
        "price":price,"bars":bars,"source":source,"reason":"EXACT30_INCOMPLETE_NEVER_PASS",
        "missing_sessions":miss,"known_session_count":len(vals),
        "dv30_lower_bound":lower,"dv30_upper_bound":None if math.isinf(upper) else upper,
    }


def resolve_symbol(sym,old,asof,exp30):
    nd={}; yd={}
    nmeta={}; ymeta={}
    try: nd,nmeta=nasdaq_hist(sym,asof)
    except Exception as e: nmeta={"error":f"{type(e).__name__}:{str(e)[:160]}"}
    try: yd,ymeta=yahoo_hist(sym,asof)
    except Exception as e: ymeta={"error":f"{type(e).__name__}:{str(e)[:160]}"}
    ndc,ndi=classify(nd,asof,exp30,"NASDAQ_OFFICIAL_HISTORICAL_API") if nd else (None,{"reason":"NO_NASDAQ_DATA"})
    ydc,ydi=classify(yd,asof,exp30,"YAHOO_CHART_FREE_FALLBACK") if yd else (None,{"reason":"NO_YAHOO_DATA"})
    decision=None; info=None
    if ndc in {"FAIL_PRICE","FAIL_DV30","PASS_HARD_GATES"}:
        decision,info=ndc,ndi
    elif ydc in {"FAIL_PRICE","FAIL_DV30"}:
        decision,info=ydc,ydi
    # Two incomplete providers (even matching counts) do not prove a genuine
    # post-IPO history shortfall. Shared truncation must remain UNKNOWN until
    # a verified independent official listing-date upper bound is available.
    if decision:
        out={"decision":decision}
        if decision=="FAIL_HISTORY":
            out.update({"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
        elif decision=="FAIL_PRICE":
            out.update({"price":info["price"],"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
        elif decision=="FAIL_DV30":
            out.update({"price":info["price"],"dv30":info["dv30"],"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
        elif decision=="PASS_HARD_GATES":
            out.update({
                "price":info["price"],"bars":info["bars"],
                "dv30_lower_bound":info["dv30_lower_bound"],"dv30_upper_bound":info["dv30_upper_bound"],
                "known_session_count":info["known_session_count"],"missing_sessions":info["missing_sessions"],
                "no_synthetic_bar":True,"source":info["source"],"proof":info["proof"],
            })
        return sym,out,None
    unresolved={
        "prior_status":old.get("status"),"prior_info":old.get("info"),
        "nasdaq_meta":nmeta,"nasdaq_class":ndc,"nasdaq_info":ndi,
        "yahoo_meta":ymeta,"yahoo_class":ydc,"yahoo_info":ydi,
    }
    return sym,None,unresolved

def load_exception_bridge(asof,queue_hash):
    path=ROOT/f"canonical_resolver_bridge_{asof.replace('-','')}.json"
    if not path.exists():
        return {},{"status":"ABSENT","path":str(path)}
    try:
        obj=json.loads(path.read_text())
        if obj.get("schema")!="XRAY_RESOLVER_EPOCH_RESULT_V1" or obj.get("status")!="COMMITTED":
            raise ValueError("SCHEMA_OR_STATUS")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
        if obj.get("asof_et")!=asof or obj.get("queue_hash")!=queue_hash:
            raise ValueError("BINDING")
        if (
          obj.get("compiled_policy_hash")!="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
          or obj.get("compiled_policy_version")!="C4.11"
          or obj.get("compiled_policy_blob_sha")!="738402b627abaca89a5b9fdfea51ff6c468d752b"
        ):
            raise ValueError("POLICY_BINDING")
        if obj.get("settlement_required") is True and obj.get("settlement_status")!="PASS":
            raise ValueError("SETTLEMENT_BINDING")
        hrs=obj.get("history_resolutions") or {}
        if not isinstance(hrs,dict): raise ValueError("HISTORY_RESOLUTIONS")
        return hrs,{"status":"PASS","path":str(path),"symbol_hash":obj.get("symbol_hash"),"source_result_task_id":obj.get("source_result_task_id")}
    except Exception as e:
        return {},{"status":"INVALID","path":str(path),"reason":f"{type(e).__name__}:{str(e)[:160]}"}

def valid_bridge_history_resolution(x):
    if not isinstance(x,dict): return False
    d=x.get("decision")
    if d=="FAIL_HISTORY":
        b=x.get("bars")
        return isinstance(b,int) and 0<=b<HARD_HISTORY and bool(x.get("source")) and bool(x.get("proof"))
    if d=="FAIL_PRICE":
        p=num(x.get("price"))
        return p is not None and p<HARD_PRICE and bool(x.get("source")) and bool(x.get("proof"))
    if d=="BLOCK_CURRENT_RUN":
        return x.get("trade_status")=="Halted" and bool(x.get("last_bar")) and bool(x.get("source"))
    return False

def main():
    m=json.loads(MANIFEST.read_text())
    asof=m["asof_et"]; exp30=expected30(asof)
    existing_resolutions={}
    if OUT.exists():
        try:
            old=json.loads(OUT.read_text())
            if (
                old.get("schema")=="XRAY_HISTORY_IDENTITY_RESOLUTION_OVERLAY_V1"
                and old.get("task_id")==TASK_ID
                and old.get("execution")=="NONE"
                and old.get("real_money")=="NO-GO"
                and old.get("base_asof_et")==asof
                and isinstance(old.get("resolutions"),dict)
            ):
                existing_resolutions=dict(old["resolutions"])
        except Exception:
            existing_resolutions={}
    resolutions={}; unresolved={}
    items=sorted(m["unknowns"].items())
    if items:
        with ThreadPoolExecutor(max_workers=min(RESOLVE_WORKERS,len(items))) as ex:
            futs={ex.submit(resolve_symbol,sym,old,asof,exp30):sym for sym,old in items}
            for fut in as_completed(futs):
                sym,out,unres=fut.result()
                if out is not None: resolutions[sym]=out
                else: unresolved[sym]=unres
    bridge_history,exception_bridge_meta=load_exception_bridge(asof,m.get("source_queue_hash"))
    for sym,br in sorted(bridge_history.items()):
        if sym not in unresolved:
            continue
        if not valid_bridge_history_resolution(br):
            continue
        resolutions[sym]=dict(br)
        unresolved.pop(sym,None)

    # Preserve prior same-epoch proven resolutions, but never retain a prior
    # resolution for a symbol that is currently UNKNOWN unless this run re-proves it.
    merged=dict(existing_resolutions)
    for sym in m.get("unknowns",{}):
        merged.pop(sym,None)
    merged.update(resolutions)
    obj={
        "schema":"XRAY_HISTORY_IDENTITY_RESOLUTION_OVERLAY_V1",
        "task_id":TASK_ID,
        "execution":"NONE","real_money":"NO-GO",
        "base_asof_et":asof,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "max_age_hours":24,
        "resolver":"NASDAQ_OFFICIAL_HISTORICAL_PRIMARY_YAHOO_FAIL_ONLY_FALLBACK_MERGE_V2",
        "exception_bridge_meta":exception_bridge_meta,
        "expected30":exp30,
        "manifest_unknown_count":len(m.get("unknowns",{})),
        "current_resolution_count":len(resolutions),
        "current_unresolved_count":len(unresolved),
        "resolution_count":len(merged),
        "unresolved_count":len(unresolved),
        "resolutions":merged,
        "unresolved":unresolved,
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "manifest_unknown_count":len(m.get("unknowns",{})),
        "current_resolution_count":len(resolutions),
        "resolution_count":len(merged),"unresolved_count":len(unresolved),
        "decisions":{d:sum(1 for v in resolutions.values() if v["decision"]==d) for d in sorted(set(v["decision"] for v in resolutions.values()))}
    },sort_keys=True))

if __name__=="__main__":
    main()
