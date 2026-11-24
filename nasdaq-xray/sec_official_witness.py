#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, re, time, urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from resilience_runtime import fetch_json

ROOT=Path(__file__).resolve().parent
REQ=ROOT/"canonical_current_event_request.json"
OUT=ROOT/"canonical_sec_official_witness.json"
UA=os.getenv("XRAY_SEC_USER_AGENT","NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar")

def h(xs): return hashlib.sha256("\n".join(sorted(xs)).encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

def write(obj):
    OUT.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def error_label(exc):
    status=getattr(exc,"code",None)
    if status is not None:
        return f"{type(exc).__name__}:HTTP_{status}"
    return f"{type(exc).__name__}:{str(exc)[:180]}"

# Process-local pacing. Other processes are not covered by this limiter.
_SEC_LAST_REQUEST = None

def sec_fetch_json(provider, url, headers, **kwargs):
    """One attempt per official endpoint observation; never retry a 429."""
    global _SEC_LAST_REQUEST
    current = time.monotonic()
    if _SEC_LAST_REQUEST is not None:
        delay = 1.05 - (current - _SEC_LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
    _SEC_LAST_REQUEST = time.monotonic()
    return fetch_json(provider, url, headers, retry_delays=(), **kwargs)

def access_stop(exc):
    return getattr(exc, "code", None) in (401, 403, 429) or str(exc).startswith("CIRCUIT_OPEN:")

def resolve_from_map(scope):
    try:
        ticker_map=sec_fetch_json("SEC_TICKER_MAP","https://www.sec.gov/files/company_tickers_exchange.json",{"User-Agent":UA,"Accept":"application/json"},cache_ttl=3600)
    except Exception as e:
        return {}, error_label(e)
    fields=ticker_map.get("fields") or []; rows=ticker_map.get("data") or []
    idx={name:i for i,name in enumerate(fields)}
    out={}
    for row in rows:
        try:
            t=str(row[idx["ticker"]]).upper()
            if t in scope:
                out[t]={"cik":int(row[idx["cik"]]),"name":row[idx["name"]],"exchange":row[idx["exchange"]],"resolver":"SEC_TICKER_MAP"}
        except Exception: pass
    return out, None
def resolve_from_efts(sym,asof):
    start=(asof-timedelta(days=550)).isoformat()
    q=urllib.parse.urlencode({
        "q":sym,
        "forms":"10-K,10-Q,8-K,20-F,6-K",
        "dateRange":"custom",
        "startdt":start,
        "enddt":asof.isoformat(),
        "from":0,
    })
    j=sec_fetch_json("SEC_EFTS",f"https://efts.sec.gov/LATEST/search-index?{q}",{"User-Agent":UA,"Accept":"application/json"},cache_ttl=900)
    hits=(((j.get("hits") or {}).get("hits")) or [])
    cands=[]
    for hit in hits:
        src=hit.get("_source") or {}
        ciks=src.get("ciks") or []
        tickers=[str(x).upper() for x in (src.get("tickers") or [])]
        display=" ".join(str(x) for x in (src.get("display_names") or []))
        exact=(sym in tickers) or bool(re.search(rf"\({re.escape(sym)}\)",display.upper()))
        if not exact or not ciks: continue
        for cik in ciks:
            try: cands.append(int(str(cik).lstrip("0") or "0"))
            except Exception: pass
    cands=sorted(set(x for x in cands if x>0))
    if len(cands)!=1: return None, f"EFTS_EXACT_CIK_MATCHES_{len(cands)}"
    return {"cik":cands[0],"name":None,"exchange":None,"resolver":"SEC_EFTS_EXACT_TICKER"},None

def bounded_identity_resolution(scope,asof):
    """Avoid N-symbol SEC fan-out when hosted-runner SEC transport is blocked.

    One official ticker-map request is attempted first. If it fails, exactly one
    EFTS symbol probe is allowed to distinguish endpoint-specific failure from a
    broader transport block. A dual failure leaves the complete scope UNKNOWN;
    it can never create CLEAN/PASS evidence.
    """
    by,map_error=resolve_from_map(scope)
    prefetch={}
    transport={
        "status":"AVAILABLE",
        "map_error":map_error,
        "efts_probe_symbol":None,
        "efts_probe_error":None,
    }
    # A rate-limit or authentication failure is not a reason to try another
    # endpoint. Preserve the existing single official diagnostic on map 403.
    if map_error and (map_error.endswith(":HTTP_429") or map_error.endswith(":HTTP_401") or "CIRCUIT_OPEN:" in map_error):
        transport["status"]="BLOCKED_BOUNDED_PROBE"
        return by,prefetch,transport
    if map_error and scope:
        probe=sorted(scope)[0]
        transport["efts_probe_symbol"]=probe
        try:
            ident,reason=resolve_from_efts(probe,asof)
            prefetch[probe]=(ident,reason)
            transport["status"]="DEGRADED_MAP_FALLBACK"
        except Exception as e:
            transport["status"]="BLOCKED_BOUNDED_PROBE"
            transport["efts_probe_error"]=error_label(e)
    return by,prefetch,transport

def main():
    if not REQ.exists():
        write({"schema":"XRAY_SEC_OFFICIAL_WITNESS_V1","status":"NO_EVENT_REQUEST","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"generated_at_utc":now()}); return
    r=json.loads(REQ.read_text())
    if r.get("schema")!="XRAY_EVENT_EPOCH_REQUEST_V1" or r.get("status")!="READY":
        write({"schema":"XRAY_SEC_OFFICIAL_WITNESS_V1","status":"NOT_READY","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"generated_at_utc":now()})
        print(json.dumps({"status":"NOT_READY"})); return

    # SEC witness is only an enrichment/confirmation layer. Restrict to geometry
    # scope to avoid unnecessary public-endpoint load. Absence can never imply CLEAN.
    scope=sorted(set(r.get("geometry_scope") or r.get("weekly_scope") or []))
    asof=date.fromisoformat(r["asof_et"])
    results,transport=build_witness_results(scope,asof)
    unknown=sum(v["identity_status"]!="PASS" for v in results.values())
    out={"schema":"XRAY_SEC_OFFICIAL_WITNESS_V1","status":"READY" if unknown==0 else "READY_WITH_UNKNOWNS","authority":"SEC_PRIMARY_WITNESS_OPTIONAL","task_id":r.get("task_id"),"asof_et":r["asof_et"],"execution":"NONE","real_money":"NO-GO","alpha_authority":False,"absence_never_clean":True,"scope_kind":"GEOMETRY_ONLY","geometry_scope":scope,"geometry_scope_count":len(scope),"geometry_scope_hash":r.get("geometry_scope_hash") or h(scope),"weekly_scope_hash":r.get("weekly_scope_hash"),"sec_transport":transport,"results":results,"unknown_count":unknown,"generated_at_utc":now()}
    write(out)
    print(json.dumps({"status":out["status"],"asof":out["asof_et"],"scope":len(scope),"unknown":unknown},sort_keys=True))

def build_witness_results(scope,asof):
    floor=asof-timedelta(days=14)
    by,prefetch,transport=bounded_identity_resolution(scope,asof)
    results={}
    for sym in scope:
        if transport.get("status") in ("BLOCKED_BOUNDED_PROBE","BLOCKED_DURING_SCOPE"):
            results[sym]={
                "identity_status":"UNKNOWN",
                "reason":"SEC_TRANSPORT_" + transport["status"],
                "transport":transport,
                "filings":[],
            }
            continue
        ident=by.get(sym)
        resolve_reason=None
        if not ident:
            if sym in prefetch:
                ident,resolve_reason=prefetch[sym]
            else:
                try:
                    ident,resolve_reason=resolve_from_efts(sym,asof)
                except Exception as e:
                    resolve_reason=error_label(e)
                    if access_stop(e):
                        transport.update(status="BLOCKED_DURING_SCOPE", blocked_provider="SEC_EFTS", blocked_reason=resolve_reason)
        if not ident:
            results[sym]={"identity_status":"UNKNOWN","reason":resolve_reason or "SEC_IDENTITY_UNRESOLVED","filings":[]}; continue
        try:
            sub=sec_fetch_json("SEC_SUBMISSIONS",f"https://data.sec.gov/submissions/CIK{ident['cik']:010d}.json",{"User-Agent":UA,"Accept":"application/json"},cache_ttl=300)
            # A requested URL or prior routing hint is not an issuer witness.
            # Require an explicit positive CIK and exact symbol in the response.
            raw_cik=sub.get("cik")
            response_cik=None
            if type(raw_cik) is int and raw_cik>0:
                response_cik=raw_cik
            elif isinstance(raw_cik,str) and re.fullmatch(r"[0-9]{1,10}",raw_cik):
                response_cik=int(raw_cik)
            if response_cik!=ident["cik"] or not response_cik:
                results[sym]={"identity_status":"UNKNOWN","cik":ident["cik"],"reason":"SEC_SUBMISSIONS_CIK_MISSING_OR_MISMATCH","filings":[]}; continue
            st=sub.get("tickers")
            if not isinstance(st,list) or not st or any(not isinstance(x,str) or not x for x in st):
                results[sym]={"identity_status":"UNKNOWN","cik":ident["cik"],"reason":"SEC_SUBMISSIONS_TICKERS_MISSING_OR_INVALID","filings":[]}; continue
            if sym not in [x.upper() for x in st]:
                results[sym]={"identity_status":"UNKNOWN","cik":ident["cik"],"reason":"SEC_SUBMISSIONS_TICKER_MISMATCH","filings":[]}; continue
            recent=((sub.get("filings") or {}).get("recent") or {})
            forms=recent.get("form") or []; dates=recent.get("filingDate") or []
            acc=recent.get("accessionNumber") or []; docs=recent.get("primaryDocument") or []
            report=recent.get("reportDate") or []
            filings=[]
            for i,form in enumerate(forms):
                try: fd=date.fromisoformat(dates[i])
                except Exception: continue
                if fd<floor or fd>asof: continue
                if form not in {"8-K","10-Q","10-K","6-K","20-F","4","SC 13D","SC 13D/A","SC 13G","SC 13G/A"}: continue
                filings.append({"form":form,"filing_date":dates[i],"report_date":report[i] if i<len(report) else None,"accession_number":acc[i] if i<len(acc) else None,"primary_document":docs[i] if i<len(docs) else None})
            results[sym]={"identity_status":"PASS","cik":ident["cik"],"name":sub.get("name") or ident.get("name"),"exchange":ident.get("exchange"),"resolver":ident.get("resolver"),"filings":filings}
        except Exception as e:
            reason=error_label(e)
            results[sym]={"identity_status":"UNKNOWN","cik":ident["cik"],"reason":reason,"filings":[]}
            if access_stop(e):
                transport.update(status="BLOCKED_DURING_SCOPE", blocked_provider="SEC_SUBMISSIONS", blocked_reason=reason)

    return results,transport
if __name__=="__main__": main()
