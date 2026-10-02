#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from resilience_runtime import fetch_json
ROOT=Path(__file__).resolve().parent
IN=ROOT/"free_solution_candidates.json"; OUT=ROOT/"free_solution_verification.json"
def now(): return datetime.now(timezone.utc).isoformat()
def main():
    src=json.loads(IN.read_text()); rows=[]
    for x in src.get("candidates") or []:
        repo=x["repo"]
        try:
            j=fetch_json("GITHUB_REPO_VERIFY",f"https://api.github.com/repos/{repo}",{"Accept":"application/vnd.github+json","User-Agent":"NASDAQ-SWING-XRAY"},cache_ttl=1800)
            lic=(j.get("license") or {}).get("spdx_id")
            rows.append({"repo":repo,"purpose":x.get("purpose"),"exists":True,"archived":bool(j.get("archived")),"disabled":bool(j.get("disabled")),"fork":bool(j.get("fork")),"license":lic,"pushed_at":j.get("pushed_at"),"default_branch":j.get("default_branch"),"integration_verdict":"REFERENCE_ONLY" if lic in {"GPL-2.0","GPL-2.0-only","AGPL-3.0","AGPL-3.0-only"} else "REVIEW"})
        except Exception as e:
            rows.append({"repo":repo,"purpose":x.get("purpose"),"exists":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:160]}","integration_verdict":"FAIL_CLOSED"})
    out={"schema":"XRAY_FREE_SOLUTION_VERIFICATION_V1","status":"READY","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"results":rows,"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":"READY","count":len(rows)},sort_keys=True))
if __name__=="__main__": main()
