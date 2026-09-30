#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OUT=Path(__file__).resolve().parent/"eastmoney_probe.json"
BUILD="2026-10-01.2"

def get(url,params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(url+"?"+q,headers={"User-Agent":UA,"Referer":"https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

spot=get("https://72.push2.eastmoney.com/api/qt/clist/get",{
 "pn":"1","pz":"10000","po":"1","np":"1",
 "ut":"bd1d9ddb04089700cf9c27f6f7426281","fltt":"2","invt":"2","fid":"f12",
 "fs":"m:105,m:106,m:107","fields":"f2,f5,f12,f13,f14,f20,f21"
})
diff=((spot.get("data") or {}).get("diff") or [])
if isinstance(diff,dict): diff=list(diff.values())
aapl=next((x for x in diff if str(x.get("f12","")).upper()=="AAPL"),None)
if not aapl:
    raise RuntimeError("AAPL_NOT_FOUND")
secid=f"{aapl.get('f13')}.{aapl.get('f12')}"
hist=get("https://63.push2his.eastmoney.com/api/qt/stock/kline/get",{
 "secid":secid,
 "fields1":"f1,f2,f3,f4,f5,f6",
 "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
 "klt":"101","fqt":"0","end":"20500000","lmt":"400"
})
klines=((hist.get("data") or {}).get("klines") or [])
out={
 "updated_at_utc":datetime.now(timezone.utc).isoformat(),
 "spot_count":len(diff),
 "aapl_raw":aapl,
 "aapl_secid":secid,
 "aapl_history_count":len(klines),
 "aapl_history_first":klines[:2],
 "aapl_history_last":klines[-2:],
 "status":"PASS" if len(diff)>1000 and len(klines)>=260 else "FAIL",
 "execution":"NONE","real_money":"NO-GO"
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,sort_keys=True))
