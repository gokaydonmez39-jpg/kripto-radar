#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from resilience_runtime import fetch_json
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_macro_context.json"
def now(): return datetime.now(timezone.utc).isoformat()
def main():
    key=os.getenv("FRED_API_KEY","").strip()
    out={"schema":"XRAY_MACRO_CONTEXT_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"generated_at_utc":now(),"series":{}}
    if not key:
        out["status"]="NOT_CONFIGURED_OPTIONAL"; out["reason"]="FRED_API_KEY_MISSING"
    else:
        for sid in ["DGS2","DGS10","DFEDTARU"]:
            q=urllib.parse.urlencode({"series_id":sid,"api_key":key,"file_type":"json","sort_order":"desc","limit":5})
            try:
                j=fetch_json("FRED",f"https://api.stlouisfed.org/fred/series/observations?{q}",{"Accept":"application/json"},cache_ttl=900)
                obs=[x for x in (j.get("observations") or []) if x.get("value") not in {None,"."}]
                out["series"][sid]=obs[0] if obs else None
            except Exception as e: out["series"][sid]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:160]}"}
        out["status"]="READY"
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"]},sort_keys=True))
if __name__=="__main__": main()
