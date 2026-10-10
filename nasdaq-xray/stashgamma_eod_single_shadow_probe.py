#!/usr/bin/env python3
"""StashGamma Free EOD one-symbol C4.18 SHADOW source probe, not a data grant.

Vendor's official contract: https://www.stashgamma.com/developer-docs
X-Api-Key header, GET /api/dataapi/v1/eod/{symbol}, from/to ISO dates.
API credentials, raw bars and private source values never enter GitHub artifacts.
One request maximum; no background scan, notification, alpha or trading.
The operator-provided entitlement flags are claims, never independent proof.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date,timedelta
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from current_history_source_request import expected_dates
from history_transport_cache_guard import official_completed_sessions

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_STASHGAMMA_ONE_SYMBOL_EOD_SHADOW_PROBE_V1"
SYMBOL="QQQ"
BASE="https://www.stashgamma.com/api/dataapi/v1/eod/"
MAX_BYTES=350000
MAX_BARS=650

def configured(env:dict)->bool:
    key=env.get("XRAY_STASHGAMMA_API_KEY","")
    digest=env.get("XRAY_STASHGAMMA_LICENSE_EVIDENCE_SHA256","")
    return (isinstance(key,str) and len(key)>=16 and key.startswith("sg_live_")
            and env.get("XRAY_STASHGAMMA_PERSONAL_UNATTENDED_OK")=="true"
            and env.get("XRAY_STASHGAMMA_PRIVATE_CACHE_RIGHTS_OK")=="true"
            and isinstance(digest,str) and bool(re.fullmatch(r"[a-fA-F0-9]{64}",digest)))

def query_window(asof:str)->tuple[str,str]:
    daily,weekly=expected_dates(asof)
    start=(date.fromisoformat(min(daily[0],weekly[0]))-timedelta(days=5)).isoformat()
    return start,asof

def checked_response(payload:dict,asof:str)->dict:
    if not isinstance(payload,dict) or str(payload.get("symbol","")).upper()!=SYMBOL:
        raise ValueError("VENDOR_SYMBOL_MISMATCH")
    bars=payload.get("bars")
    count=payload.get("count")
    if (not isinstance(bars,list) or type(count) is not int or count!=len(bars)
            or not 260<=len(bars)<=MAX_BARS):
        raise ValueError("EOD_BAR_COUNT_INVALID")
    start,_=query_window(asof)
    known=set(official_completed_sessions(asof))
    seen=set()
    for entry in bars:
        if not isinstance(entry,dict):
            raise ValueError("BAR_ROW_INVALID")
        day=entry.get("date")
        if (not isinstance(day,str) or len(day)!=10 or day<start or day>asof
                or day not in known or day in seen):
            raise ValueError("FUTURE_DUPLICATE_OR_NONEXCHANGE_BAR")
        seen.add(day)
        values=[]
        for k in ("open","high","low","close","volume"):
            v=entry.get(k)
            if isinstance(v,bool) or not isinstance(v,(int,float)):
                raise ValueError("BAR_VALUE_NOT_NUMERIC")
            x=float(v)
            if not math.isfinite(x) or x<=0:
                raise ValueError("BAR_VALUE_INVALID")
            values.append(x)
        o,h,l,c,v=values
        if h<max(o,c,l) or l>min(o,c) or v!=math.floor(v):
            raise ValueError("OHLCV_RANGE_OR_SHARE_VOLUME_INVALID")
    daily,weekly=expected_dates(asof)
    return {"bars_valid":len(bars),
            "daily_260_dates_present":set(daily).issubset(seen),
            "weekly_52_dates_present":set(weekly).issubset(seen),
            "max_bar_date_at_or_before_asof":max(seen)==asof}

def probe(env:dict,asof:str,fetch=None)->dict:
    doc={"schema":SCHEMA,"asof_et":asof,"symbol":SYMBOL,
         "status":"BLOCKED_NO_INDEPENDENT_KEY_OR_RIGHTS_CLAIM",
         "api_calls":0,"bars_valid":0,"daily_260_dates_present":False,
         "weekly_52_dates_present":False,
         "max_bar_date_at_or_before_asof":False,
         "vendor_access_scope_granted_independently":False,
         "vendor_entitlement_proven":False,
         "market_consolidated_volume_proven":False,
         "issuer_share_class_figi_proven":False,
         "unadjusted_pit_bar_semantics_proven":False,
         "private_cache_reuse_rights_independently_proven":False,
         "primary_mc_created":False,"canonical_history_pass_created":0,
         "can_register_R92":False,"alpha_authority":False,
         "raw_bar_persisted":False,"secret_logged":False,
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    if not configured(env):
        return doc
    doc["api_calls"]=1
    try:
        if fetch is None:
            start,end=query_window(asof)
            path=BASE+urllib.parse.quote(SYMBOL,safe="")
            params=urllib.parse.urlencode({"from":start,"to":end})
            req=urllib.request.Request(path+"?"+params,
                headers={"X-Api-Key":env["XRAY_STASHGAMMA_API_KEY"],
                         "Accept":"application/json"},method="GET")
            with urllib.request.urlopen(req,timeout=15) as response:
                body=response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:
                raise ValueError("EOD_RESPONSE_TOO_LARGE")
            payload=json.loads(body)
        else:
            payload=fetch()
        values=checked_response(payload,asof)
        doc.update(values)
        doc["status"]=("SHADOW_COMPLETE_260D_52W_STRUCTURE_NOT_AUTHORITY"
                       if (values["daily_260_dates_present"]
                       and values["weekly_52_dates_present"]
                       and values["max_bar_date_at_or_before_asof"])
                       else "BLOCKED_INCOMPLETE_SOURCE_SAMPLE")
    except urllib.error.HTTPError as exc:
        # No token, URL, response body, or raw market data in public diagnostics.
        doc["status"]="BLOCKED_PROVIDER_RATE_LIMIT" if exc.code==429 else "BLOCKED_VENDOR_AUTH_OR_HTTP"
    except (urllib.error.URLError,ValueError,TypeError,KeyError,OverflowError,
            json.JSONDecodeError):
        doc["status"]="BLOCKED_VENDOR_RESPONSE_INVALID"
    return doc

def selftest()->None:
    asof="2026-10-09"
    daily,weekly=expected_dates(asof)
    start,end=query_window(asof)
    assert start<min(daily[0],weekly[0]) and end==asof
    assert SYMBOL not in urllib.parse.urlencode({"from":start,"to":end})
    env={"XRAY_STASHGAMMA_API_KEY":"sg_live_"+"x"*30,
         "XRAY_STASHGAMMA_PERSONAL_UNATTENDED_OK":"true",
         "XRAY_STASHGAMMA_PRIVATE_CACHE_RIGHTS_OK":"true",
         "XRAY_STASHGAMMA_LICENSE_EVIDENCE_SHA256":"a"*64}
    sample_days=sorted(set(daily+weekly))
    fixture={"symbol":SYMBOL,"count":len(sample_days),
             "bars":[{"date":d,"open":10.0,"high":11.0,"low":9.0,
                      "close":10.0,"volume":10000} for d in sample_days]}
    assert probe({},asof)["api_calls"]==0
    for k in tuple(env):
        incomplete=dict(env)
        incomplete.pop(k)
        assert probe(incomplete,asof)["api_calls"]==0,k
    good=probe(env,asof,lambda:fixture)
    assert good["status"]=="SHADOW_COMPLETE_260D_52W_STRUCTURE_NOT_AUTHORITY"
    assert good["bars_valid"]==len(sample_days)
    assert all(good[k] is False for k in (
        "vendor_entitlement_proven","market_consolidated_volume_proven",
        "issuer_share_class_figi_proven","unadjusted_pit_bar_semantics_proven",
        "private_cache_reuse_rights_independently_proven",
        "can_register_R92","alpha_authority","raw_bar_persisted"))
    assert good["canonical_history_pass_created"]==0
    cases=[
        ("SYMBOL",lambda z:z.update(symbol="AAPL")),
        ("COUNT",lambda z:z.update(count=len(sample_days)-1)),
        ("DUPLICATE",lambda z:z["bars"].append(copy.deepcopy(z["bars"][-1]))),
        ("LOOKAHEAD",lambda z:z["bars"][-1].update(date="2026-10-12")),
        ("NEG_VOLUME",lambda z:z["bars"][-1].update(volume=-5)),
        ("FLOAT_SHARES",lambda z:z["bars"][-1].update(volume=1.5)),
        ("NAN_PRICE",lambda z:z["bars"][-1].update(open=float("nan"))),
        ("BAD_RANGE",lambda z:z["bars"][-1].update(high=1)),
        ("NONSESSION",lambda z:z["bars"][-1].update(date="2026-10-10")),
        ("STRING_PRICE",lambda z:z["bars"][-1].update(open="10")),
    ]
    for name,edit in cases:
        broken=copy.deepcopy(fixture)
        edit(broken)
        result=probe(env,asof,lambda x=broken:x)
        assert result["status"]=="BLOCKED_VENDOR_RESPONSE_INVALID",name
        assert result["can_register_R92"] is False,name
    incomplete=copy.deepcopy(fixture)
    incomplete["bars"]=incomplete["bars"][:-1]
    incomplete["count"]=len(incomplete["bars"])
    x=probe(env,asof,lambda:incomplete)
    assert x["status"] in ("BLOCKED_INCOMPLETE_SOURCE_SAMPLE","BLOCKED_VENDOR_RESPONSE_INVALID")
    assert probe(env,asof,lambda:(_ for _ in ()).throw(ValueError("fake")))[
        "status"]=="BLOCKED_VENDOR_RESPONSE_INVALID"
    print("XRAY_STASHGAMMA_SOURCE_SCHEMA_SELFTEST=PASS_ONE_POSITIVE_TEN_CORRUPT_FOUR_RIGHTS_NEGATIVES_NO_MC_NO_R92")

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.out is None or args.out.resolve().is_relative_to(REPO.resolve()):
        parser.error("public repository output forbidden; use private temporary path")
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    result=probe(os.environ,price["asof_et"])
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("XRAY_STASHGAMMA_EOD="+result["status"])
    print("XRAY_STASHGAMMA_SOURCE_CALLS="+str(result["api_calls"]))
    print("XRAY_STASHGAMMA_PRIMARY_OR_R92=NOT_AUTHORIZED")

if __name__=="__main__":
    main()
