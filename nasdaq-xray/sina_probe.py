#!/usr/bin/env python3
import json, signal, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import akshare as ak

OUT=Path(__file__).resolve().parent/"sina_probe.json"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

class Deadline(Exception):
    pass

def alarm_handler(signum, frame):
    raise Deadline("CALL_TIMEOUT")

signal.signal(signal.SIGALRM, alarm_handler)

out={"updated_at_utc":datetime.now(timezone.utc).isoformat(),"execution":"NONE","real_money":"NO-GO","results":{}}

# First prove the upstream itself is reachable without relying on AKShare decoding.
for s in ["AAPL","MSFT","NVDA"]:
    rec={}
    try:
        req=urllib.request.Request(f"https://finance.sina.com.cn/staticdata/us/{s}",headers={"User-Agent":UA})
        with urllib.request.urlopen(req,timeout=12) as r:
            raw=r.read(4096)
        rec["http_bytes_sample"]=len(raw)
        rec["http_prefix"]=raw[:80].decode("utf-8","ignore")
        rec["http_status"]="PASS"
    except Exception as e:
        rec["http_status"]="ERROR"
        rec["http_error"]=type(e).__name__+":"+str(e)[:240]

    # Decode/history through AKShare, but never allow an unbounded requests.get to hang the job.
    try:
        signal.alarm(30)
        df=ak.stock_us_daily(symbol=s,adjust="")
        signal.alarm(0)
        rows=len(df)
        rec["rows"]=rows
        if rows:
            tail=df.tail(1).iloc[0].to_dict()
            rec["last"]={k:str(v) for k,v in tail.items()}
        rec["history_status"]="PASS" if rows>=260 else "FAIL"
    except Exception as e:
        signal.alarm(0)
        rec["history_status"]="ERROR"
        rec["history_error"]=type(e).__name__+":"+str(e)[:240]
    out["results"][s]=rec

out["status"]="PASS" if all(v.get("history_status")=="PASS" for v in out["results"].values()) else "FAIL"
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,default=str)+"\n")
print(json.dumps(out,sort_keys=True,default=str))
