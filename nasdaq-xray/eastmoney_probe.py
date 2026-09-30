#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OUT=Path(__file__).resolve().parent/"eastmoney_probe.json"
BUILD="2026-10-01.3"

def get(url,params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(url+"?"+q,headers={"User-Agent":UA,"Referer":"https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

# NASDAQ is market 105 in AKShare's current US-stock examples.
secid="105.AAPL"
hist=get("https://63.push2his.eastmoney.com/api/qt/stock/kline/get",{
 "secid":secid,
 "fields1":"f1,f2,f3,f4,f5,f6",
 "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
 "klt":"101","fqt":"0","beg":"20240101","end":"20500000","lmt":"1000"
})
klines=((hist.get("data") or {}).get("klines") or [])

quote=get("https://push2.eastmoney.com/api/qt/stock/get",{
 "secid":secid,
 "ut":"bd1d9ddb04089700cf9c27f6f7426281",
 "fltt":"2","invt":"2",
 "fields":"f2,f5,f12,f13,f14,f20,f21,f124"
})
qd=quote.get("data") or {}

out={
 "build":BUILD,
 "updated_at_utc":datetime.now(timezone.utc).isoformat(),
 "aapl_secid":secid,
 "aapl_quote":qd,
 "aapl_history_count":len(klines),
 "aapl_history_first":klines[:2],
 "aapl_history_last":klines[-2:],
 "status":"PASS" if len(klines)>=260 and str(qd.get("f12","")).upper()=="AAPL" else "FAIL",
 "execution":"NONE","real_money":"NO-GO"
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,sort_keys=True))
