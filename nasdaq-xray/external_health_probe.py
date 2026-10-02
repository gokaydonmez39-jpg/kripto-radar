#!/usr/bin/env python3
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from resilience_runtime import fetch_json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"external_health_state.json"

def now(): return datetime.now(timezone.utc).isoformat()

def statuspage(provider,url):
    j=fetch_json(provider,url,{"Accept":"application/json","User-Agent":"NASDAQ-SWING-XRAY/1.0"},cache_ttl=60)
    s=j.get("status") or {}
    ind=str(s.get("indicator") or "unknown")
    return {
        "status":"PASS" if ind=="none" else ("DEGRADED" if ind in {"minor","major","critical"} else "UNKNOWN"),
        "indicator":ind,
        "description":s.get("description"),
    }

def main():
    out={"schema":"XRAY_EXTERNAL_HEALTH_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"sources":{},"generated_at_utc":now()}
    try:
        out["sources"]["github_status"]=statuspage("GITHUB_STATUS","https://www.githubstatus.com/api/v2/status.json")
    except Exception as e:
        out["sources"]["github_status"]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"}

    # Zero-key public Cloudflare Statuspage is always attempted. Radar API is
    # optional enrichment only when the user has explicitly configured a token.
    try:
        out["sources"]["cloudflare_status"]=statuspage("CLOUDFLARE_STATUS","https://www.cloudflarestatus.com/api/v2/status.json")
    except Exception as e:
        out["sources"]["cloudflare_status"]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"}

    token=os.getenv("CLOUDFLARE_RADAR_TOKEN","").strip()
    if token:
        try:
            j=fetch_json("CLOUDFLARE_RADAR","https://api.cloudflare.com/client/v4/radar/annotations/outages?limit=10&offset=0&dateRange=1d&format=json",{"Authorization":f"Bearer {token}","Accept":"application/json"},cache_ttl=300)
            anns=((j.get("result") or {}).get("annotations") or [])
            out["sources"]["cloudflare_radar"]={"status":"PASS" if j.get("success") is True else "UNKNOWN","outage_count_1d":len(anns),"recent":anns[:10]}
        except Exception as e:
            out["sources"]["cloudflare_radar"]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"}
    else:
        out["sources"]["cloudflare_radar"]={"status":"NOT_CONFIGURED_OPTIONAL","reason":"CLOUDFLARE_RADAR_TOKEN_MISSING"}

    core=[out["sources"]["github_status"]["status"],out["sources"]["cloudflare_status"]["status"]]
    out["status"]="DEGRADED" if "DEGRADED" in core else ("UNKNOWN" if "UNKNOWN" in core else "PASS")
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"github":out["sources"]["github_status"]["status"],"cloudflare_status":out["sources"]["cloudflare_status"]["status"],"cloudflare_radar":out["sources"]["cloudflare_radar"]["status"]},sort_keys=True))
if __name__=="__main__": main()
