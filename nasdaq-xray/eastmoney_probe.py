#!/usr/bin/env python3
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent/"eastmoney_probe.json"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BUILD="2026-10-01.4"

def get_json(url,params=None,headers=None,timeout=30):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    hdr={"User-Agent":UA,"Accept":"application/json,text/plain,*/*"}
    if headers: hdr.update(headers)
    req=urllib.request.Request(url,headers=hdr)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def em_info(symbol):
    return get_json("https://push2.eastmoney.com/api/qt/stock/get",{
        "secid":"105."+symbol,
        "fltt":"2","invt":"2",
        "fields":"f43,f57,f58,f84,f85,f116,f117,f127,f189"
    },{"Referer":"https://quote.eastmoney.com/"})

def nasdaq_summary(symbol):
    return get_json(
        "https://api.nasdaq.com/api/quote/"+symbol+"/summary",
        {"assetclass":"stocks"},
        {
            "Accept":"application/json, text/plain, */*",
            "Origin":"https://www.nasdaq.com",
            "Referer":"https://www.nasdaq.com/",
        }
    )

out={"build":BUILD,"updated_at_utc":datetime.now(timezone.utc).isoformat(),
     "execution":"NONE","real_money":"NO-GO","symbols":{}}
for sym in ["AAPL","NVDA"]:
    row={}
    try:
        e=em_info(sym)
        row["eastmoney_rc"]=e.get("rc")
        row["eastmoney_data"]=e.get("data")
    except Exception as ex:
        row["eastmoney_error"]=type(ex).__name__+":"+str(ex)[:180]
    try:
        n=nasdaq_summary(sym)
        row["nasdaq_status"]=n.get("status")
        row["nasdaq_data"]=n.get("data")
    except Exception as ex:
        row["nasdaq_error"]=type(ex).__name__+":"+str(ex)[:180]
    out["symbols"][sym]=row
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,sort_keys=True))
