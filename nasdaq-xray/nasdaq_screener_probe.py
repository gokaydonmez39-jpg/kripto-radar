#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent/"nasdaq_screener_probe.json"
BUILD="2026-10-01.1"
URL="https://api.nasdaq.com/api/screener/stocks"
params={
  "tableonly":"true",
  "limit":"25",
  "offset":"0",
  "exchange":"NASDAQ",
  "download":"true"
}
url=URL+"?"+urllib.parse.urlencode(params)
headers={
 "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
 "Accept":"application/json,text/plain,*/*",
 "Origin":"https://www.nasdaq.com",
 "Referer":"https://www.nasdaq.com/market-activity/stocks/screener"
}
req=urllib.request.Request(url,headers=headers)
with urllib.request.urlopen(req,timeout=45) as r:
    obj=json.loads(r.read().decode("utf-8"))
data=obj.get("data") or {}
rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
aapl=next((x for x in rows if str(x.get("symbol","")).upper()=="AAPL"),None)
out={
 "updated_at_utc":datetime.now(timezone.utc).isoformat(),
 "rows_returned":len(rows),
 "aapl":aapl,
 "sample":rows[:2],
 "status":"PASS" if len(rows)>1000 and aapl else "PARTIAL_OR_FAIL",
 "execution":"NONE",
 "real_money":"NO-GO"
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps({"rows_returned":len(rows),"aapl":aapl,"status":out["status"]},sort_keys=True))
