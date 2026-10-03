#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request, urllib.error, hashlib, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import akshare as ak
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
OFFICIAL_IDENTITY_EVIDENCE=ROOT/"history_official_identity_evidence.json"
INPUT=Path(os.getenv("XRAY_HISTORY_INPUT", str(ROOT/"canonical_mc_input_20260930.json")))
OUT=Path(os.getenv("XRAY_HISTORY_OUT", str(ROOT/"canonical_history_20260930.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF_ENV=os.getenv("XRAY_ASOF")
HARD_DAILY=260
HARD_WEEKLY=52
WORKERS=int(os.getenv("XRAY_HISTORY_WORKERS","10"))
PROVIDER_MAX_INFLIGHT=max(1,int(os.getenv("XRAY_HISTORY_PROVIDER_MAX_INFLIGHT","3")))
RETRY_DELAYS=(0.0,1.0,2.5)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NY=ZoneInfo("America/New_York")
_PROVIDER_SEM=threading.Semaphore(PROVIDER_MAX_INFLIGHT)
HISTORY_BRIDGE={}
HISTORY_BRIDGE_PATH=None

def load_history_bridge(src,asof):
    global HISTORY_BRIDGE_PATH
    raw=os.getenv("XRAY_HISTORY_EVIDENCE_BRIDGE")
    p=Path(raw) if raw else ROOT/f"canonical_history_evidence_bridge_{asof.replace('-','')}_v1.json"
    if not p.exists():
        HISTORY_BRIDGE_PATH=None
        return {}
    j=json.loads(p.read_text())
    assert j.get("schema")=="XRAY_HISTORY_EVIDENCE_BRIDGE_V1"
    assert j.get("status")=="READY"
    assert j.get("task_id")==TASK_ID
    assert j.get("asof_et")==asof
    assert j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
    assert j.get("unknown_never_pass") is True
    assert j.get("no_threshold_change") is True and j.get("no_synthetic_bars") is True
    assert (j.get("thresholds") or {}).get("daily")==HARD_DAILY
    assert (j.get("thresholds") or {}).get("weekly_completed")==HARD_WEEKLY
    assert j.get("source_mc_path")==relpath(INPUT)
    assert j.get("source_mc_blob_sha")==blob_sha(INPUT)
    assert j.get("source_mc_policy_hash")==src.get("policy_hash")
    assert j.get("source_mc_policy_version")==src.get("policy_version")
    entries=j.get("entries") or {}
    assert isinstance(entries,dict)
    assert set(entries)==set(j.get("scope_symbols") or [])
    assert int((j.get("counts") or {}).get("TOTAL",-1))==len(entries)
    HISTORY_BRIDGE_PATH=relpath(p)
    return entries

def bridge_resolution(sym,asof):
    e=HISTORY_BRIDGE.get(sym)
    if not e:
        return None
    mode=e.get("mode"); outcome=e.get("outcome")
    if mode=="LISTING_AGE_TERMINAL_FAIL_V1" and outcome=="FAIL_HISTORY":
        ld=datetime.fromisoformat(e["listing_date"]).date()
        ad=datetime.fromisoformat(asof).date()
        age=(ad-ld).days
        assert 0<=age<364
        assert int(e.get("calendar_days_since_listing",-1))==age
        assert e.get("proof")=="LISTING_AGE_LT_364_DAYS__52_COMPLETED_WEEKS_IMPOSSIBLE"
        auth=e.get("listing_authority")
        assert auth in {"BIGDATA_CORPORATE_CALENDAR","NASDAQ_OFFICIAL"}
        if auth=="NASDAQ_OFFICIAL":
            assert str(e.get("listing_source_url") or "").startswith("https://www.nasdaq.com/")
        return "FAIL_HISTORY",{
          "proof":"LISTING_AGE_TERMINAL_FAIL_V1",
          "listing_date":e["listing_date"],
          "calendar_days_since_listing":age,
          "reason":"52_COMPLETED_WEEKS_IMPOSSIBLE_FROM_CURRENT_SECURITY_LISTING_DATE",
          "authority":auth,
          "bridge_path":HISTORY_BRIDGE_PATH,
          "thresholds":{"daily":HARD_DAILY,"weekly_completed":HARD_WEEKLY}
        }
    if mode=="TICKER_LINEAGE_HISTORY_PASS_V1" and outcome=="PASS_HISTORY":
        # PASS authority intentionally removed from the legacy bridge. Ticker
        # continuity must pass continuity_composite_pass(), which requires the
        # official unchanged-CUSIP registry plus live cross-source overlap and
        # an exact current-ASOF bar. A manually prepared bridge must never
        # bypass that check.
        return None
    raise AssertionError(f"invalid history bridge entry for {sym}")

def _is_transient(exc):
    if isinstance(exc,urllib.error.HTTPError):
        return exc.code in {408,425,429,500,502,503,504}
    if isinstance(exc,(urllib.error.URLError,TimeoutError,ConnectionError,ConnectionResetError)):
        return True
    s=str(exc).lower()
    return any(x in s for x in (
      "timed out","timeout","temporarily unavailable","connection reset",
      "remote end closed","too many requests","rate limit","429","502","503","504"
    ))

def _call_with_retry(fn):
    last=None
    for attempt,delay in enumerate(RETRY_DELAYS,1):
        if delay:
            time.sleep(delay)
        try:
            with _PROVIDER_SEM:
                return fn(),attempt
        except Exception as e:
            last=e
            if not _is_transient(e):
                raise
    assert last is not None
    raise last

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
    def _once():
        req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/plain,*/*","Referer":"https://www.nasdaq.com/"})
        with urllib.request.urlopen(req,timeout=timeout) as r:
            return json.loads(r.read().decode())
    out,_attempts=_call_with_retry(_once)
    return out

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
    dates=sorted(by or {})
    base={
      "source":source,
      "daily_bars":len(dates),
      "first_date":dates[0] if dates else None,
      "last_date":dates[-1] if dates else None,
      "asof_present":bool(asof in (by or {})),
    }
    if not by or asof not in by:
        return "UNKNOWN",dict(base,reason="ASOF_MISSING_OR_EMPTY")
    daily=len(by);weekly=week_count(by,asof)
    info=dict(base,completed_week_count=weekly)
    if daily>=HARD_DAILY and weekly>=HARD_WEEKLY:return "PASS_HISTORY",info
    return "POTENTIAL_FAIL_HISTORY",info

def load_official_identity_evidence():
    try:
        j=json.loads(OFFICIAL_IDENTITY_EVIDENCE.read_text())
        if (
          j.get("schema")=="XRAY_HISTORY_OFFICIAL_IDENTITY_EVIDENCE_V1"
          and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
          and j.get("alpha_authority") is False and j.get("evidence_only") is True
        ):
            return j.get("records") or {}
    except Exception:
        pass
    return {}

OFFICIAL_RECORDS=load_official_identity_evidence()

def official_listing_upper_bound_fail(sym,asof):
    rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")!="OFFICIAL_LISTING_UPPER_BOUND_FAIL_ONLY":
        return None
    start=rec.get("earliest_public_trading_date")
    if not start:
        return None
    try:
        cal=mcal.get_calendar("NYSE")
        sched=cal.schedule(start_date=start,end_date=asof)
        sessions=[x.date().isoformat() for x in sched.index]
        max_daily=len(sessions)
        max_weekly=week_count({d:(1,1) for d in sessions},asof)
    except Exception:
        return None
    if max_daily<HARD_DAILY or max_weekly<HARD_WEEKLY:
        return {
          "proof":"OFFICIAL_LISTING_DATE_HISTORY_UPPER_BOUND",
          "source_registry":"nasdaq-xray/history_official_identity_evidence.json",
          "mode":rec.get("mode"),
          "earliest_public_trading_date":start,
          "regular_way_trading_date":rec.get("regular_way_trading_date"),
          "max_possible_daily_bars":max_daily,
          "max_possible_completed_weeks":max_weekly,
          "thresholds":{"daily":HARD_DAILY,"weekly_completed":HARD_WEEKLY},
          "official_sources":rec.get("sources") or [],
          "note":rec.get("note"),
        }
    return None

def continuity_composite_pass(sym,asof,sb,si,yb,yi):
    rec=OFFICIAL_RECORDS.get(sym) or {}
    if rec.get("mode")!="OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY":
        return None
    if rec.get("cusip_unchanged") is not True:
        return None
    effective=rec.get("effective_date")
    predecessor=rec.get("predecessor_symbol")
    if not effective or not predecessor:
        return None
    # Current symbol must be observed exactly on ASOF from one source.
    if asof not in sb:
        return None
    # Long-history source may lag by one completed session, but must itself
    # satisfy the 260-day/52-week history depth before composition.
    if len(yb)<HARD_DAILY or week_count(yb,asof)<HARD_WEEKLY:
        return None
    # Verify that the two independent feeds represent the same post-change
    # security over a meaningful overlap; no identity-only PASS.
    common=sorted(d for d in set(sb)&set(yb) if effective<=d<=asof)
    if len(common)<20:
        return None
    rel=[]
    for d in common:
        a=num(sb[d][0]); b=num(yb[d][0])
        if a is None or b is None or a<=0 or b<=0:
            continue
        rel.append(abs(a-b)/max(a,b))
    if len(rel)<20:
        return None
    rel_sorted=sorted(rel)
    p95=rel_sorted[min(len(rel_sorted)-1,max(0,math.ceil(0.95*len(rel_sorted))-1))]
    if p95>0.001:
        return None
    merged=dict(yb)
    merged.update(sb)
    daily=len(merged); weekly=week_count(merged,asof)
    if daily<HARD_DAILY or weekly<HARD_WEEKLY or asof not in merged:
        return None
    return {
      "source":"OFFICIAL_TICKER_CONTINUITY_COMPOSITE_HISTORY",
      "proof":"UNCHANGED_CUSIP_PLUS_CROSS_SOURCE_OVERLAP",
      "source_registry":"nasdaq-xray/history_official_identity_evidence.json",
      "predecessor_symbol":predecessor,
      "effective_date":effective,
      "cusip_unchanged":True,
      "daily_bars":daily,
      "completed_week_count":weekly,
      "asof_present":True,
      "overlap_sessions":len(common),
      "overlap_compared":len(rel),
      "overlap_p95_relative_close_diff":p95,
      "official_sources":rec.get("sources") or [],
      "note":rec.get("note"),
    }

def aligned_first_bar_upper_bound_fail(a,b,asof):
    """Evidence-only terminal fail for young listings.

    If two independent providers begin on the exact same first trading date,
    the official US-equity session calendar gives a hard upper bound on the
    number of completed sessions/weeks available to the current symbol. This
    may only create FAIL, never PASS.
    """
    fa=(a or {}).get("first_date"); fb=(b or {}).get("first_date")
    if not fa or fa!=fb:
        return None
    try:
        cal=mcal.get_calendar("NYSE")
        sched=cal.schedule(start_date=fa,end_date=asof)
        sessions=[x.date().isoformat() for x in sched.index]
        max_daily=len(sessions)
        max_weekly=week_count({d:(1,1) for d in sessions},asof)
    except Exception:
        return None
    if max_daily<HARD_DAILY or max_weekly<HARD_WEEKLY:
        return {
          "proof":"TWO_PROVIDER_ALIGNED_FIRST_BAR_UPPER_BOUND",
          "providers":[a.get("source"),b.get("source")],
          "first_date":fa,
          "asof_et":asof,
          "max_possible_daily_bars":max_daily,
          "max_possible_completed_weeks":max_weekly,
          "thresholds":{"daily":HARD_DAILY,"weekly_completed":HARD_WEEKLY},
        }
    return None

def sina(sym,asof):
    try:
        df,attempts=_call_with_retry(lambda: ak.stock_us_daily(symbol=sym,adjust=""))
        by={}
        if df is not None:
            for r in df.to_dict(orient="records"):
                try:
                    d=r.get("date");day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                    c=float(r.get("close"));v=float(r.get("volume"))
                except Exception:continue
                if day<=asof and c>0 and v>=0 and math.isfinite(c) and math.isfinite(v):by[day]=(c,v)
        return by,{"usable":len(by),"attempts":attempts}
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

def eastmoney(sym,asof):
    """Fourth-source recovery for Nasdaq-only symbols.

    Eastmoney secid market 105 is Nasdaq. This source is consulted only after
    Sina, official Nasdaq historical, and Yahoo did not produce a terminal
    PASS. It never weakens the 260-daily/52-completed-week hard gates and still
    requires an exact ASOF bar.
    """
    try:
        end=datetime.fromisoformat(asof).date()
        start=end-timedelta(days=1100)
        secid=f"105.{sym}"
        df,attempts=_call_with_retry(lambda: ak.stock_us_hist(
          symbol=secid,period="daily",
          start_date=start.strftime("%Y%m%d"),end_date=end.strftime("%Y%m%d"),
          adjust=""
        ))
        by={}
        if df is not None:
            for r in df.to_dict(orient="records"):
                try:
                    d=r.get("日期",r.get("date"))
                    day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                    close_v=r.get("收盘",r.get("close"))
                    vol_v=r.get("成交量",r.get("volume"))
                    cv=num(close_v);vv=num(vol_v)
                except Exception:
                    continue
                if day<=asof and cv is not None and cv>0 and vv is not None and vv>=0:
                    by[day]=(cv,vv)
        return by,{"usable":len(by),"attempts":attempts,"secid":secid,"market":"NASDAQ_105"}
    except Exception as e:
        return {},{"error":f"{type(e).__name__}:{str(e)[:160]}","secid":f"105.{sym}"}

def eval_one(sym,asof):
    official_fail=official_listing_upper_bound_fail(sym,asof)
    if official_fail:
        return sym,"FAIL_HISTORY",official_fail,{"official_identity_registry":True}
    sb,sm=sina(sym,asof);ss,si=classify(sb,asof,"SINA_US_DAILY")
    if ss=="PASS_HISTORY":return sym,ss,si,{"sina":sm}
    nb,nm=nasdaq(sym,asof);ns,ni=classify(nb,asof,"NASDAQ_OFFICIAL_HISTORICAL_API")
    if ns=="PASS_HISTORY":return sym,ns,ni,{"sina":sm,"nasdaq":nm}
    yb,ym=yahoo(sym,asof);ys,yi=classify(yb,asof,"YAHOO_CHART_FREE")
    if ys=="PASS_HISTORY":return sym,ys,yi,{"sina":sm,"nasdaq":nm,"yahoo":ym}
    comp=continuity_composite_pass(sym,asof,sb,si,yb,yi)
    if comp:
        return sym,"PASS_HISTORY",comp,{"sina":sm,"nasdaq":nm,"yahoo":ym,"official_identity_registry":True}
    eb,em=eastmoney(sym,asof);es,ei=classify(eb,asof,"EASTMONEY_US_DAILY_NASDAQ_105")
    if es=="PASS_HISTORY":return sym,es,ei,{"sina":sm,"nasdaq":nm,"yahoo":ym,"eastmoney":em}

    br=bridge_resolution(sym,asof)
    if br is not None:
        bst,binfo=br
        return sym,bst,binfo,{"sina":sm,"nasdaq":nm,"yahoo":ym,"eastmoney":em,"history_bridge":HISTORY_BRIDGE_PATH}

    # Recent-listing proof: two independent providers with the exact same
    # first bar can establish a hard maximum number of sessions even when a
    # latest provider bar is missing. Evidence-only: this can never create PASS.
    for aa,bb in ((si,yi),(si,ei),(yi,ei),(ni,yi),(ni,ei)):
        proof=aligned_first_bar_upper_bound_fail(aa,bb,asof)
        if proof:
            return sym,"FAIL_HISTORY",proof,{"sina":sm,"nasdaq":nm,"yahoo":ym,"eastmoney":em}

    # Terminal FAIL requires at least two independent providers to agree below either threshold.
    fails=[x for x in [
      si if ss=="POTENTIAL_FAIL_HISTORY" else None,
      ni if ns=="POTENTIAL_FAIL_HISTORY" else None,
      yi if ys=="POTENTIAL_FAIL_HISTORY" else None,
      ei if es=="POTENTIAL_FAIL_HISTORY" else None
    ] if x]
    if len(fails)>=2:
        return sym,"FAIL_HISTORY",{
          "proof":"TWO_PROVIDER_BELOW_HISTORY_GATE",
          "provider_results":fails,
          "daily_max":max(x["daily_bars"] for x in fails),
          "weekly_max":max(x["completed_week_count"] for x in fails)
        },{"sina":sm,"nasdaq":nm,"yahoo":ym,"eastmoney":em}
    return sym,"UNKNOWN_HISTORY",{
      "reason":"INSUFFICIENT_AGREEMENT",
      "sina":si,"nasdaq":ni,"yahoo":yi,"eastmoney":ei
    },{"sina":sm,"nasdaq":nm,"yahoo":ym,"eastmoney":em}

def main():
    global HISTORY_BRIDGE
    src=json.loads(INPUT.read_text())
    asof=ASOF_ENV or src.get("asof_et")
    assert src["task_id"]==TASK_ID and src["asof_et"]==asof
    HISTORY_BRIDGE=load_history_bridge(src,asof)
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
      "official_identity_evidence_path":"nasdaq-xray/history_official_identity_evidence.json",
      "official_identity_evidence_blob_sha":blob_sha(OFFICIAL_IDENTITY_EVIDENCE) if OFFICIAL_IDENTITY_EVIDENCE.exists() else None,
      "input_count":len(syms),"thresholds":{"daily":HARD_DAILY,"weekly_completed":HARD_WEEKLY},
      "counts":dict(sorted(counts.items())),"unknown_count":len(unknown),"unknown_symbols":sorted(unknown),
      "pass_count":len(passes),"pass_symbols":passes,
      "pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "state_caps":src.get("state_caps") or {s:"NORMAL" for s in syms},
      "r92_ineligible":src.get("r92_ineligible") or src.get("fallback_watch_symbols") or [],
      "history_evidence_bridge_path":HISTORY_BRIDGE_PATH,
      "history_evidence_bridge_count":len(HISTORY_BRIDGE),
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
          "eastmoney":obj["results"][s]["info"].get("eastmoney"),
          "provider_meta":obj["results"][s].get("provider_meta"),
        } for s in obj["unknown_symbols"]
      },
      "pass_count":obj["pass_count"],
      "pass_hash":obj["pass_hash"],
      "provider_max_inflight":PROVIDER_MAX_INFLIGHT,
      "retry_delays":RETRY_DELAYS
    },sort_keys=True))
if __name__=="__main__":main()
