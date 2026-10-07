#!/usr/bin/env python3
"""Fail-closed SEC transport matrix probe for GitHub-hosted runners.

Purpose: determine which official SEC endpoint families are reachable from the
production runner before any zero-dollar SEC migration is attempted.

NON-CANONICAL. No alpha authority. No Event/MC/Legal classification changes.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"sec_transport_matrix_probe_state.json"
UA="NASDAQ-SWING-XRAY/1.0 research contact=https://github.com/gokaydonmez39-jpg/kripto-radar"

ENDPOINTS={
    "SEC_TICKER_MAP_EXCHANGE":"https://www.sec.gov/files/company_tickers_exchange.json",
    "SEC_TICKER_MAP":"https://www.sec.gov/files/company_tickers.json",
    "SEC_SUBMISSIONS_AAPL":"https://data.sec.gov/submissions/CIK0000320193.json",
    "SEC_COMPANYFACTS_AAPL":"https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
    "SEC_DAILY_INDEX_QTR4":"https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/index.json",
    "SEC_DAILY_MASTER_20261006":"https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261006.idx",
    "SEC_FULL_INDEX_QTR4":"https://www.sec.gov/Archives/edgar/full-index/2026/QTR4/index.json",
}

def fetch(url:str,timeout:int=20)->dict:
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,
        "Accept":"application/json,text/plain,text/html,*/*",
        "Accept-Encoding":"identity",
        "Connection":"close",
    })
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            body=r.read(256_000)
            return {
                "reachable":True,
                "http_status":int(getattr(r,"status",200)),
                "content_type":str(r.headers.get("Content-Type") or ""),
                "final_url":str(r.geturl()),
                "bytes_sampled":len(body),
                "sha256_sample":hashlib.sha256(body).hexdigest(),
            }
    except urllib.error.HTTPError as e:
        return {
            "reachable":False,
            "http_status":int(e.code),
            "error":f"HTTPError:{e.code}",
            "final_url":url,
        }
    except Exception as e:
        return {
            "reachable":False,
            "http_status":None,
            "error":f"{type(e).__name__}:{str(e)[:180]}",
            "final_url":url,
        }

def selftest()->None:
    assert len(ENDPOINTS)==7
    assert all(u.startswith("https://") and ".sec.gov/" in u for u in ENDPOINTS.values())
    assert "Archives/edgar/daily-index" in ENDPOINTS["SEC_DAILY_INDEX_QTR4"]
    print("SEC_TRANSPORT_MATRIX_SELFTEST=PASS")

def main()->None:
    selftest()
    results={}
    for name,url in ENDPOINTS.items():
        results[name]=fetch(url)
        time.sleep(1.10)
    reachable=sorted(k for k,v in results.items() if v.get("reachable") is True)
    blocked=sorted(k for k,v in results.items() if v.get("reachable") is not True)
    families={
        "files": any(results[k].get("reachable") for k in ("SEC_TICKER_MAP_EXCHANGE","SEC_TICKER_MAP")),
        "data": any(results[k].get("reachable") for k in ("SEC_SUBMISSIONS_AAPL","SEC_COMPANYFACTS_AAPL")),
        "archives": any(results[k].get("reachable") for k in ("SEC_DAILY_INDEX_QTR4","SEC_DAILY_MASTER_20261006","SEC_FULL_INDEX_QTR4")),
    }
    out={
        "schema":"XRAY_SEC_TRANSPORT_MATRIX_PROBE_V1",
        "authority":"NON_CANONICAL_TRANSPORT_DIAGNOSTIC_ONLY",
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
        "classification_applied":False,
        "sec_fair_access_target_rps_lt_1":True,
        "endpoint_count":len(ENDPOINTS),
        "reachable_count":len(reachable),
        "blocked_count":len(blocked),
        "reachable_endpoints":reachable,
        "blocked_endpoints":blocked,
        "families":families,
        "results":results,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "reachable":len(reachable),
        "blocked":len(blocked),
        "families":families,
        "out":str(OUT),
    },sort_keys=True))

if __name__=="__main__":
    main()
