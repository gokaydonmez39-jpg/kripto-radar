#!/usr/bin/env python3
import csv, io, json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent/"stooq_symbol_probe.json"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
res={"updated_at_utc":datetime.now(timezone.utc).isoformat(),"execution":"NONE","real_money":"NO-GO","results":{}}
for s in ["aapl.us","msft.us","nvda.us"]:
    try:
        url="https://stooq.com/q/d/l/?"+urllib.parse.urlencode({"s":s,"d1":"20240101","d2":"20260930","i":"d"})
        req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/csv,*/*"})
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read().decode("utf-8","replace")
        rows=list(csv.DictReader(io.StringIO(raw)))
        valid=[x for x in rows if x.get("Date") and x.get("Close") and x.get("Volume")]
        res["results"][s]={"status":"PASS" if len(valid)>=260 else "FAIL","rows":len(valid),"first":valid[:1],"last":valid[-1:]}
    except Exception as e:
        res["results"][s]={"status":"ERROR","error":type(e).__name__+":"+str(e)[:240]}
res["status"]="PASS" if all(x.get("status")=="PASS" for x in res["results"].values()) else "FAIL"
OUT.write_text(json.dumps(res,indent=2,sort_keys=True)+"\n")
print(json.dumps(res,sort_keys=True))
