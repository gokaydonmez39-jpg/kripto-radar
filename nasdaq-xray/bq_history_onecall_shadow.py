#!/usr/bin/env python3
"""Single limited BQ /quotes?mode=eod research probe, never PRIMARY.

Uses existing XRAY_BQ_API_KEY if provided. One 12-row AAPL-only completed EOD
query, bounded to the exact current PRICE ASOF; no vendor data persisted, no
secrets or URL/error body logged, no third-party dataset construction.
R92 / MC / canonical HISTORY changes expressly prohibited.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
PRICE=ROOT/"canonical_current_price_dv30.json"
SCHEMA="XRAY_BQ_ONECALL_EOD_RESEARCH_SHADOW_V1"
HOST="data.businessquant.com"
REQUEST_CAP=1
BAR_CAP=12
TICKER="AAPL"


def validate(obj:object, asof:str, symbol:str=TICKER)->dict:
    if isinstance(obj,dict) and symbol in obj:
        body=obj.get(symbol)
    else:
        body=obj
    if not isinstance(body,dict):
        raise ValueError("BQ_RESPONSE_NOT_OBJECT")
    meta=body.get("metadata")
    rows=body.get("data")
    if not isinstance(meta,dict) or not isinstance(rows,list) or len(rows)>BAR_CAP:
        raise ValueError("BQ_EOD_RESPONSE_BAD_SHAPE_OR_EXCESS_BARS")
    if str(meta.get("ticker","")).upper()!=symbol or meta.get("mode")!="eod":
        raise ValueError("BQ_EOD_IDENTITY_OR_MODE_UNVERIFIED")
    pages=meta.get("pagination")
    if not isinstance(pages,dict) or type(pages.get("current_page")) is not int or pages["current_page"]!=1:
        raise ValueError("BQ_PAGINATION_UNVERIFIED")
    seen=set()
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("BQ_ROW_NOT_OBJECT")
        raw=str(row.get("date") or "")[:10]
        try:
            d=date.fromisoformat(raw)
        except (TypeError,ValueError) as e:
            raise ValueError("BQ_DATE_INVALID") from e
        if raw>asof or raw in seen or d.weekday()>4:
            raise ValueError("BQ_FUTURE_DUPLICATE_OR_NONSESSION")
        seen.add(raw)
        vals=[]
        for k in ("open","high","low","close","volume"):
            rawv=row.get(k)
            if isinstance(rawv,bool):
                raise ValueError("BQ_BOOL_AS_BAR")
            try:v=float(rawv)
            except (ValueError,TypeError) as e:
                raise ValueError("BQ_BAR_NOT_NUMERIC") from e
            if not math.isfinite(v) or v<=0:
                raise ValueError("BQ_BAR_NONPOSITIVE_OR_NONFINITE")
            vals.append(v)
        o,h,l,c,v=vals
        if h<max(o,c,l) or l>min(o,c):
            raise ValueError("BQ_OHLC_RANGE_INCONSISTENT")
    return {"bar_rows_validated":len(rows),
            "bar_dates_unique":len(seen)==len(rows),
            "asof_bound_respected":True,
            "cik_in_response":str(meta.get("cik") or "").strip().isdigit()}


def limited_get(key:str,asof:str)->object:
    # Exact vendor endpoint; URL may contain API key: NEVER log it, errors,
    # exception repr or fetched JSON. Network is called once only.
    start=(date.fromisoformat(asof)-timedelta(days=21)).isoformat()
    q=urllib.parse.urlencode({
        "ticker":TICKER,"mode":"eod","from_date":start,"till_date":asof,
        "limit":BAR_CAP,"page":1,"api_key":key})
    req=urllib.request.Request("https://"+HOST+"/quotes?"+q,
        headers={"Accept":"application/json","User-Agent":"XRAY-NonTrading-Research/1.0"},
        method="GET")
    with urllib.request.urlopen(req,timeout=14) as fh:
        # up to one bounded page, not a bulk dataset.
        raw=fh.read(65537)
        if len(raw)>65536:
            raise ValueError("BQ_RESPONSE_TOO_LARGE")
    return json.loads(raw)


def run(asof:str,key:str,http_get=limited_get)->dict:
    report={
        "schema":SCHEMA,"status":"BLOCKED_NO_API_KEY",
        "asof_et":asof,"provider":"BUSINESS_QUANT_EOD_ONE_CALL",
        "symbol_count_requested":0,"api_call_count":0,"bar_rows_validated":0,
        "response_metadata_only":True,"current_scope_514_backfilled":False,
        "data_storage_license_verified":False,"unattended_redistribution_rights_verified":False,
        "production_history_authority":False,"primary_mc_authority":False,
        "can_register_R92":False,"raw_prices_or_volumes_persisted":False,
        "api_key_or_request_url_reported":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }
    if not key:
        return report
    report["symbol_count_requested"]=1
    report["api_call_count"]=1
    try:
        obj=http_get(key,asof)
        verdict=validate(obj,asof)
        report.update(verdict)
        report["status"]="SHADOW_EOD_SAMPLE_STRUCTURAL_ONLY"
    except urllib.error.HTTPError as e:
        report["status"]=("BLOCKED_API_QUOTA_429" if e.code==429 else
            "BLOCKED_UNAUTHORIZED_401_403" if e.code in (401,403) else
            "BLOCKED_VENDOR_HTTP_ERROR")
    except (urllib.error.URLError, TimeoutError):
        report["status"]="BLOCKED_TRANSPORT_ERROR"
    except Exception:
        # Query may hold secret even inside nested exceptions: never reveal it.
        report["status"]="BLOCKED_INVALID_RESPONSE"
    return report


def selftest()->None:
    asof="2026-10-08"
    row={"date":"2026-10-07 16:00:00","open":10.,"high":11.,
         "low":9.,"close":10.5,"volume":150.25}
    sample={"metadata":{"ticker":TICKER,"mode":"eod","cik":320193,
                        "pagination":{"current_page":1,"total_pages":1}},
            "data":[row]}
    assert validate(sample,asof)["bar_rows_validated"]==1
    assert validate({TICKER:sample},asof)["cik_in_response"]
    assert run(asof,"",lambda *a: (_ for _ in ()).throw(AssertionError("CALL_WITH_NO_KEY")))["api_call_count"]==0
    good=run(asof,"fake-not-real-key",lambda *a:{TICKER:sample})
    assert good["status"]=="SHADOW_EOD_SAMPLE_STRUCTURAL_ONLY"
    assert good["production_history_authority"] is False and good["can_register_R92"] is False
    assert good["api_key_or_request_url_reported"] is False
    from copy import deepcopy
    cases=[]
    for bad in [
        {"metadata":{**sample["metadata"],"mode":"daily"},"data":[row]},
        {"metadata":{**sample["metadata"],"ticker":"TSLA"},"data":[row]},
        {"metadata":sample["metadata"],"data":[dict(row,date="2026-10-09")]},
        {"metadata":sample["metadata"],"data":[dict(row,volume=0)]},
        {"metadata":sample["metadata"],"data":[dict(row,close="nan")]},
        {"metadata":sample["metadata"],"data":[dict(row,high=2)]},
        {"metadata":sample["metadata"],"data":[row,row]},
        {"metadata":sample["metadata"],"data":[dict(row,date="2026-10-10")]},
        {"metadata":sample["metadata"],"data":[dict(row,date="not-a-date")]},
    ]:
        try:validate(bad,asof)
        except ValueError:cases.append(1)
        else:raise AssertionError("BQ_INVALID_EOD_ACCEPTED")
    assert len(cases)==9
    import urllib.error
    for code in (401,403,429,500):
        r=run(asof,"mock-token",lambda *a,c=code:(_ for _ in ()).throw(urllib.error.HTTPError("https://secret.invalid?api_key=SECRET",c,"none",None,None)))
        assert r["status"].startswith("BLOCKED_")
        assert "SECRET" not in json.dumps(r)
    print("XRAY_BQ_SHADOW_EOD_SELFTEST=PASS_2_POSITIVE_9_NEGATIVE_4_HTTP_AND_NO_KEY_NO_DATA_LEAK")


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    if not args.out:
        ap.error("--out in ephemeral runner temp required")
    if args.out.resolve().is_relative_to(REPO.resolve()):
        ap.error("PUBLIC_REPO_OUTPUT_FORBIDDEN")
    p=json.loads(PRICE.read_text(encoding="utf-8"))
    if p.get("execution")!="NONE" or p.get("real_money")!="NO-GO":
        raise SystemExit("PRICE_SAFETY_INVALID")
    out=run(p["asof_et"],os.environ.get("XRAY_BQ_API_KEY","").strip())
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_BQ_EOD_SHADOW_STATUS="+out["status"])
    print("XRAY_BQ_EOD_SHADOW_REQUESTS="+str(out["api_call_count"]))
    print("XRAY_BQ_EOD_SHADOW_VALID_ROWS="+str(out["bar_rows_validated"]))
    print("XRAY_BQ_EOD_NO_HISTORY_MC_AL_AUTHORITY=PASS")


if __name__=="__main__":
    main()
