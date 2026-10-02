#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from resilience_runtime import fetch_json

ROOT=Path(__file__).resolve().parent
REQ=ROOT/"canonical_current_event_request.json"
OUT=ROOT/"canonical_sec_official_witness.json"
UA=os.getenv("XRAY_SEC_USER_AGENT","NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar")

def h(xs): return hashlib.sha256("\n".join(sorted(xs)).encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

def main():
    if not REQ.exists():
        OUT.write_text(json.dumps({"schema":"XRAY_SEC_OFFICIAL_WITNESS_V1","status":"NO_EVENT_REQUEST","execution":"NONE","real_money":"NO-GO","generated_at_utc":now()},sort_keys=True,indent=2)+"\n"); return
    r=json.loads(REQ.read_text())
    if r.get("schema")!="XRAY_EVENT_EPOCH_REQUEST_V1" or r.get("status")!="READY":
        raise RuntimeError("SEC_WITNESS_EVENT_REQUEST_NOT_READY")
    scope=sorted(set(r.get("weekly_scope") or []))
    ticker_map=fetch_json("SEC","https://www.sec.gov/files/company_tickers_exchange.json",{"User-Agent":UA,"Accept":"application/json"},cache_ttl=3600)
    fields=ticker_map.get("fields") or []
    rows=ticker_map.get("data") or []
    idx={name:i for i,name in enumerate(fields)}
    by={}
    for row in rows:
        try:
            t=str(row[idx["ticker"]]).upper()
            if t in scope:
                by[t]={"cik":int(row[idx["cik"]]),"name":row[idx["name"]],"exchange":row[idx["exchange"]]}
        except Exception: pass
    asof=date.fromisoformat(r["asof_et"]); floor=asof-timedelta(days=14)
    results={}
    for sym in scope:
        ident=by.get(sym)
        if not ident:
            results[sym]={"identity_status":"UNKNOWN","reason":"SEC_TICKER_MAP_MISS","filings":[]}; continue
        try:
            sub=fetch_json("SEC",f"https://data.sec.gov/submissions/CIK{ident['cik']:010d}.json",{"User-Agent":UA,"Accept":"application/json"},cache_ttl=300)
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
            results[sym]={"identity_status":"PASS","cik":ident["cik"],"name":ident["name"],"exchange":ident["exchange"],"filings":filings}
        except Exception as e:
            results[sym]={"identity_status":"UNKNOWN","cik":ident["cik"],"exchange":ident["exchange"],"reason":f"{type(e).__name__}:{str(e)[:180]}","filings":[]}
    out={"schema":"XRAY_SEC_OFFICIAL_WITNESS_V1","status":"READY","authority":"SEC_DATA_GOV_PRIMARY_WITNESS","task_id":r.get("task_id"),"asof_et":r["asof_et"],"execution":"NONE","real_money":"NO-GO","alpha_authority":False,"absence_never_clean":True,"weekly_scope":scope,"weekly_scope_count":len(scope),"weekly_scope_hash":r.get("weekly_scope_hash") or h(scope),"results":results,"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":"READY","asof":out["asof_et"],"scope":len(scope),"unknown":sum(v["identity_status"]!="PASS" for v in results.values())},sort_keys=True))
if __name__=="__main__": main()
