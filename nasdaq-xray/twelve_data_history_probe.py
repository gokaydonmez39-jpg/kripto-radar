#!/usr/bin/env python3
"""Twelve Data Basic EOD research sample; never source/AL authority.

One AAPL 320-bar query if XRAY_TWELVE_DATA_API_KEY is configured.
Request unadjusted as-traded bars, not default split-adjusted bars that may
retroactively encode future splits. Corporate-action/PIT rights remain UNPROVEN.
Only aggregates emitted; vendor data and credentials are never stored.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path
from current_history_source_request import expected_dates

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_TWELVE_EOD_SINGLE_SAMPLE_V1"
SYMBOL="AAPL"


def eod_query(asof:str)->str:
    """Unadjusted historical EOD request; credential stays in HTTP header.

    Twelve Data documents default adjustment 'splits'; for an as-of research
    sample this must NOT silently incorporate a future split. Unadjusted source
    bars alone do not prove a lawful complete PIT-adjustment chain or DV30.
    """
    return urllib.parse.urlencode({"symbol":SYMBOL,"interval":"1day",
                                   "outputsize":320,"end_date":asof,
                                   "adjust":"none"})


def classify(data:dict,asof:str)->dict:
    meta=data.get("meta") or {}
    bars=data.get("values")
    if data.get("status")!="ok" or not isinstance(bars,list):
        raise ValueError("NOT_EOD_SERIES")
    if (meta.get("symbol")!=SYMBOL or meta.get("interval")!="1day"
        or meta.get("currency")!="USD" or meta.get("mic_code")!="XNAS"):
        raise ValueError("EOD_IDENTITY_MISMATCH")
    if not (1<=len(bars)<=320):
        raise ValueError("UNEXPECTED_BAR_COUNT")
    dates=set()
    for item in bars:
        day=str(item.get("datetime",""))
        if len(day)!=10 or day>asof or day in dates:
            raise ValueError("LOOKAHEAD_OR_DUPLICATE_DATE")
        dates.add(day)
        values=[]
        for k in ("open","high","low","close","volume"):
            v=float(item[k])
            if not math.isfinite(v) or v<=0:raise ValueError("INVALID_OHLCV")
            values.append(v)
        o,h,l,c,v=values
        if h<max(o,l,c) or l>min(o,c):raise ValueError("INVALID_PRICE_RANGE")
    daily,weekly=expected_dates(asof)
    return {"bars_valid":len(bars),"260_dates_present":set(daily)<=dates,
            "52_completed_weeks_present":set(weekly)<=dates}


def probe(key:str,asof:str,fetch=None)->dict:
    out={"schema":SCHEMA,"asof_et":asof,"status":"BLOCKED_NO_KEY",
         "api_calls":0,"bars_valid":0,"260_dates_present":False,
         "52_completed_weeks_present":False,"can_register_R92":False,
         "history_authority":False,"mc_authority":False,
         "vendor_data_persisted":False,"execution":"NONE","real_money":"NO-GO"}
    if not key:return out
    out["api_calls"]=1
    try:
        if fetch is None:
            params=eod_query(asof)
            req=urllib.request.Request("https://api.twelvedata.com/time_series?"+params,
                   headers={"Authorization":"apikey "+key,"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=14) as resp:
                body=resp.read(100001)
            if len(body)>100000:raise ValueError("TOO_MUCH_VENDOR_DATA")
            obj=json.loads(body)
        else:obj=fetch()
        result=classify(obj,asof)
        out.update(result)
        out["status"]="SHADOW_SAMPLE_COMPLETE" if (
            result["260_dates_present"] and result["52_completed_weeks_present"]
        ) else "BLOCKED_HISTORY_SAMPLE_INCOMPLETE"
    except Exception:
        # Never log vendor bodies, request URL or credentials.
        out["status"]="BLOCKED_VENDOR_RESPONSE_OR_ACCESS"
    return out


def selftest()->None:
    asof="2026-10-08"
    daily,weekly=expected_dates(asof)
    q=urllib.parse.parse_qs(eod_query(asof),strict_parsing=True)
    assert q=={"symbol":[SYMBOL],"interval":["1day"],"outputsize":["320"],
               "end_date":[asof],"adjust":["none"]}, "PIT_SPLIT_LOOKAHEAD_REQUEST"
    assert "apikey" not in eod_query(asof).lower(), "KEY_IN_VENDOR_QUERY"
    fixture={"status":"ok","meta":{"symbol":"AAPL","interval":"1day",
             "currency":"USD","mic_code":"XNAS"},
             "values":[{"datetime":d,"open":"10","high":"11",
                        "low":"9","close":"10","volume":"100.5"} for d in daily]}
    assert probe("",asof)["api_calls"]==0
    p=probe("test-key",asof,lambda:fixture)
    assert p["status"]=="SHADOW_SAMPLE_COMPLETE"
    assert p["history_authority"] is False and p["can_register_R92"] is False
    for change in (
        lambda x:x["meta"].update(mic_code="XNYS"),
        lambda x:x["values"][0].update(volume="0"),
        lambda x:x["values"][0].update(datetime="2026-10-09"),
        lambda x:x["values"][0].update(close="nan"),
        lambda x:x["values"][0].update(high="1"),
        lambda x:x["values"].append(x["values"][0]),
    ):
        import copy
        d=copy.deepcopy(fixture)
        change(d)
        assert probe("test",asof,lambda d=d:d)["status"]=="BLOCKED_VENDOR_RESPONSE_OR_ACCESS"
    truncated=dict(fixture,values=fixture["values"][:259])
    assert probe("test",asof,lambda:truncated)["status"]=="BLOCKED_HISTORY_SAMPLE_INCOMPLETE"
    print("XRAY_TWELVE_UNADJUSTED_PIT_REQUEST_SELFTEST=PASS_260_52_AND_7_NEGATIVES_NO_ALPHA")


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    if not args.output or args.output.resolve().is_relative_to(ROOT.parent.resolve()):
        ap.error("output must be ephemeral, outside GitHub repository")
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    out=probe(os.environ.get("XRAY_TWELVE_DATA_API_KEY",""),price["asof_et"])
    args.output.write_text(json.dumps(out,sort_keys=True)+"\n")
    print("XRAY_TWELVE_EOD_PROBE="+out["status"])
    print("XRAY_TWELVE_EOD_CALLS="+str(out["api_calls"]))


if __name__=="__main__":main()
