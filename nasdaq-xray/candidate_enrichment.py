#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
POINTER=ROOT/"chatgpt_canonical_state_v2.json"
SEC=ROOT/"canonical_sec_official_witness.json"
OUT=ROOT/"canonical_candidate_enrichment.json"
def now(): return datetime.now(timezone.utc).isoformat()
def main():
    p=json.loads(POINTER.read_text()); s=p.get("state_json") or {}
    if isinstance(s,str): s=json.loads(s)
    r92=[x for x in (s.get("r92") or []) if isinstance(x,dict) and x.get("schema")=="XRAY_RESEARCH_CANDIDATE_R92_V1"]
    sec={}
    if SEC.exists():
        try: sec=(json.loads(SEC.read_text()).get("results") or {})
        except Exception: pass
    rows=[]
    for x in r92:
        sym=x.get("symbol")
        filings=(sec.get(sym) or {}).get("filings") or []
        rows.append({"delivery_key":x.get("delivery_key"),"symbol":sym,"asof_et":x.get("asof_et"),"sec_recent_filings":filings,"enrichment_only":True})
    out={"schema":"XRAY_CANDIDATE_ENRICHMENT_V1","status":"READY" if rows else "NO_CANDIDATES","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"candidates":rows,"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"count":len(rows)},sort_keys=True))
if __name__=="__main__": main()
