#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent/"eastmoney_probe.json"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BUILD="2026-10-01.6"

def get_json(url,params=None,headers=None,timeout=35):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    hdr={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"}
    if headers: hdr.update(headers)
    req=urllib.request.Request(url,headers=hdr)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

NASDAQ_HEADERS={
    "Accept":"application/json, text/plain, */*",
    "Origin":"https://www.nasdaq.com",
    "Referer":"https://www.nasdaq.com/",
}

def em_info(symbol):
    return get_json("https://push2.eastmoney.com/api/qt/stock/get",{
        "secid":"105."+symbol,"fltt":"2","invt":"2",
        "fields":"f43,f57,f58,f84,f85,f116,f117,f127,f189"
    },{"Referer":"https://quote.eastmoney.com/"})

def em_hist(symbol):
    return get_json("https://63.push2his.eastmoney.com/api/qt/stock/kline/get",{
        "secid":"105."+symbol,
        "fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt":"101","fqt":"0","beg":"20260901","end":"20260930","lmt":"100"
    },{"Referer":"https://quote.eastmoney.com/"})

def nasdaq_summary(symbol):
    return get_json("https://api.nasdaq.com/api/quote/"+symbol+"/summary",
                    {"assetclass":"stocks"},NASDAQ_HEADERS)

def nasdaq_hist(symbol):
    return get_json("https://api.nasdaq.com/api/quote/"+symbol+"/historical",{
        "assetclass":"stocks",
        "fromdate":"09/01/2026",
        "todate":"09/30/2026",
        "limit":"100"
    },NASDAQ_HEADERS)

out={"build":BUILD,"updated_at_utc":datetime.now(timezone.utc).isoformat(),
     "execution":"NONE","real_money":"NO-GO","symbols":{}}
for sym in ["AAPL","NVDA"]:
    row={}
    for label,fn in [
        ("eastmoney_info",lambda:em_info(sym)),
        ("eastmoney_hist",lambda:em_hist(sym)),
        ("nasdaq_summary",lambda:nasdaq_summary(sym)),
        ("nasdaq_hist",lambda:nasdaq_hist(sym)),
    ]:
        try: row[label]=fn()
        except Exception as ex: row[label+"_error"]=type(ex).__name__+":"+str(ex)[:180]
    out["symbols"][sym]=row
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps({"build":BUILD,"symbols":list(out["symbols"]),"execution":"NONE","real_money":"NO-GO"},sort_keys=True))
