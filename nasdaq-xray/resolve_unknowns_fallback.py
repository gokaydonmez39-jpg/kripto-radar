#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
MANIFEST=Path(os.getenv("XRAY_UNKNOWN_MANIFEST", str(ROOT/"canonical_full_hard_gate_20260930_unknowns.json")))
OUT=Path(os.getenv("XRAY_RESOLUTION_OUT", str(ROOT/"history_resolution_overlay.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
HARD_PRICE=10.0
HARD_DV20=50_000_000.0
HARD_HISTORY=260
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")

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

def expected20(asof):
    cal=mcal.get_calendar("NASDAQ")
    start=(datetime.fromisoformat(asof).date()-timedelta(days=60)).isoformat()
    sched=cal.schedule(start_date=start,end_date=asof)
    ds=[x.date().isoformat() for x in sched.index if x.date().isoformat()<=asof]
    if len(ds)<20: raise RuntimeError("CALENDAR_LT20")
    return ds[-20:]

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
        if close is not None and close>0 and vol is not None and vol>=0:
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

def classify(by,asof,exp20,source):
    bars=len(by)
    if asof not in by:
        return None,{"reason":"ASOF_MISSING","bars":bars,"source":source}
    price=by[asof][0]
    if price<=HARD_PRICE:
        return "FAIL_PRICE",{"price":price,"bars":bars,"source":source,"proof":"EXACT_ASOF_DAILY_CLOSE"}
    if bars<HARD_HISTORY:
        return "POTENTIAL_FAIL_HISTORY",{"price":price,"bars":bars,"source":source}
    vals=[by[d][0]*by[d][1] for d in exp20 if d in by]
    miss=[d for d in exp20 if d not in by]
    if not miss:
        s=sorted(vals); dv=(s[9]+s[10])/2.0
        if dv<HARD_DV20:
            return "FAIL_DV20",{"price":price,"dv20":dv,"bars":bars,"source":source,"proof":"EXACT20_MEDIAN"}
        return "PASS_HARD_GATES",{
            "price":price,"bars":bars,"dv20_lower_bound":dv,"dv20_upper_bound":dv,
            "known_session_count":20,"missing_sessions":[],"no_synthetic_bar":True,
            "source":source,"proof":"EXACT20_MEDIAN",
        }
    m=len(miss)
    low=sorted(vals+[0.0]*m)
    lower=(low[9]+low[10])/2.0
    high=sorted(vals+[float("inf")]*m)
    upper=(high[9]+high[10])/2.0
    if upper<HARD_DV20:
        return "FAIL_DV20",{
            "price":price,"dv20":upper,"bars":bars,"source":source,
            "proof":"DV20_UPPER_BOUND_LT_GATE","missing_sessions":miss,
            "known_session_count":len(vals),"no_synthetic_bar":True,
        }
    if lower>=HARD_DV20 and not math.isinf(upper):
        return "PASS_HARD_GATES",{
            "price":price,"bars":bars,"dv20_lower_bound":lower,"dv20_upper_bound":upper,
            "known_session_count":len(vals),"missing_sessions":miss,"no_synthetic_bar":True,
            "source":source,"proof":"DV20_LOWER_BOUND_GE_GATE",
        }
    return None,{
        "price":price,"bars":bars,"source":source,"reason":"EXACT20_STILL_AMBIGUOUS",
        "missing_sessions":miss,"known_session_count":len(vals),
        "dv20_lower_bound":lower,"dv20_upper_bound":None if math.isinf(upper) else upper,
    }


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
        return p is not None and p<=HARD_PRICE and bool(x.get("source")) and bool(x.get("proof"))
    if d=="BLOCK_CURRENT_RUN":
        return x.get("trade_status")=="Halted" and bool(x.get("last_bar")) and bool(x.get("source"))
    return False

def main():
    m=json.loads(MANIFEST.read_text())
    asof=m["asof_et"]; exp20=expected20(asof)
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
    for sym,old in sorted(m["unknowns"].items()):
        nd={}; yd={}
        nmeta={}; ymeta={}
        try: nd,nmeta=nasdaq_hist(sym,asof)
        except Exception as e: nmeta={"error":f"{type(e).__name__}:{str(e)[:160]}"}
        try: yd,ymeta=yahoo_hist(sym,asof)
        except Exception as e: ymeta={"error":f"{type(e).__name__}:{str(e)[:160]}"}
        ndc,ndi=classify(nd,asof,exp20,"NASDAQ_OFFICIAL_HISTORICAL_API") if nd else (None,{"reason":"NO_NASDAQ_DATA"})
        ydc,ydi=classify(yd,asof,exp20,"YAHOO_CHART_FREE_FALLBACK") if yd else (None,{"reason":"NO_YAHOO_DATA"})

        decision=None; info=None
        # Nasdaq official is primary. Its exact terminal/pass classification may resolve directly.
        if ndc in {"FAIL_PRICE","FAIL_DV20","PASS_HARD_GATES"}:
            decision,info=ndc,ndi
        # Yahoo fallback may prove only terminal PRICE/DV20 failures; never create PASS alone.
        elif ydc in {"FAIL_PRICE","FAIL_DV20"}:
            decision,info=ydc,ydi
        # FAIL_HISTORY requires two-provider agreement on exact as-of bar presence and <260 usable bars.
        elif ndc=="POTENTIAL_FAIL_HISTORY" and ydc=="POTENTIAL_FAIL_HISTORY":
            if abs(int(ndi["bars"])-int(ydi["bars"]))<=5:
                decision="FAIL_HISTORY"
                info={"bars":min(int(ndi["bars"]),int(ydi["bars"])),
                      "source":"NASDAQ_OFFICIAL_HISTORICAL_API+YAHOO_CHART_FREE_FALLBACK",
                      "proof":"TWO_PROVIDER_LT260_AGREEMENT"}
        if decision:
            out={"decision":decision}
            if decision=="FAIL_HISTORY":
                out.update({"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
            elif decision=="FAIL_PRICE":
                out.update({"price":info["price"],"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
            elif decision=="FAIL_DV20":
                out.update({"price":info["price"],"dv20":info["dv20"],"bars":info["bars"],"source":info["source"],"proof":info["proof"]})
            elif decision=="PASS_HARD_GATES":
                out.update({
                    "price":info["price"],"bars":info["bars"],
                    "dv20_lower_bound":info["dv20_lower_bound"],"dv20_upper_bound":info["dv20_upper_bound"],
                    "known_session_count":info["known_session_count"],"missing_sessions":info["missing_sessions"],
                    "no_synthetic_bar":True,"source":info["source"],"proof":info["proof"],
                })
            resolutions[sym]=out
        else:
            unresolved[sym]={
                "prior_status":old.get("status"),"prior_info":old.get("info"),
                "nasdaq_meta":nmeta,"nasdaq_class":ndc,"nasdaq_info":ndi,
                "yahoo_meta":ymeta,"yahoo_class":ydc,"yahoo_info":ydi,
            }
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
        "expected20":exp20,
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
