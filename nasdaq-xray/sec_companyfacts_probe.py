#!/usr/bin/env python3
import json, urllib.request
from pathlib import Path
OUT=Path(__file__).resolve().parent/"sec_companyfacts_probe.json"
urls={
 "aapl_companyfacts":"https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
 "ticker_map":"https://www.sec.gov/files/company_tickers_exchange.json"
}
uas=[
 "NASDAQ-SWING-XRAY/1.0 contact=https://github.com/gokaydonmez39-jpg/kripto-radar",
 "Mozilla/5.0 (compatible; NASDAQ-SWING-XRAY/1.0; +https://github.com/gokaydonmez39-jpg/kripto-radar)"
]
out={}
for name,url in urls.items():
    out[name]={}
    for i,ua in enumerate(uas,1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":ua,"Accept":"application/json","Accept-Encoding":"identity"})
            with urllib.request.urlopen(req,timeout=25) as r:
                b=r.read(1024)
                out[name][f"ua{i}"]={"status":r.status,"bytes_sample":len(b),"prefix":b[:80].decode("utf-8","ignore")}
        except Exception as e:
            out[name][f"ua{i}"]={"error":type(e).__name__+":"+str(e)[:180]}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,sort_keys=True))
