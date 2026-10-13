#!/usr/bin/env python3
"""PRICE-independent, bounded five-symbol Alpaca historical SIP research canary.

No canonical PRICE/DV30, HISTORY, MC, R92, G9, ACCOUNT or broker writes.
Existing external-account access in ChatGPT is NOT GitHub-runner entitlement.
Vendor request requires BOTH runner credentials and an explicit dated operator
research-license attestation. No raw OHLCV, credentials or URLs are persisted.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PRICE = ROOT / "canonical_current_price_dv30.json"
MASTER = ROOT / "canonical_current_master_manifest.json"
NY = ZoneInfo("America/New_York")
SAMPLE = ("AAPL", "AAON", "AAL", "AAOI", "NVDA")
SCHEMA = "XRAY_ALPACA_HISTORICAL_SIP_EXACT30_BACKUP_PROBE_V1"
ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
MAX_BARS = 200
MAX_BYTES = 180000

def required(ok, label):
    if not ok:
        raise ValueError(label)

def parse_date(x):
    required(isinstance(x,str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}",x), "INVALID_DATE")
    required(dt.date.fromisoformat(x).isoformat()==x, "INVALID_DATE")
    return x

def expected_sessions(price,master,latest):
    required(price.get("execution")=="NONE" and price.get("real_money")=="NO-GO", "PRICE_SAFETY")
    required(master.get("execution")=="NONE" and master.get("real_money")=="NO-GO", "MASTER_SAFETY")
    required(price.get("asof_et")==master.get("asof_et")==latest, "SOURCE_ASOF_NOT_LATEST")
    required(price.get("unknown_never_pass") is True and master.get("unknown_never_pass") is True, "UNKNOWN_POLICY")
    dates=price.get("expected30")
    required(isinstance(dates,list) and len(dates)==30 and len(set(dates))==30, "NOT_EXACT30")
    for d in dates:parse_date(d)
    required(dates==sorted(dates) and dates[-1]==latest, "DATES_NOT_COMPLETE_ASOF")
    import pandas_market_calendars as mcal
    official=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(start_date=dates[0],end_date=latest)]
    required(dates==official, "NOT_OFFICIAL_NASDAQ_EXACT30")
    unknown=price.get("unknown_symbols")
    mp=master.get("pass_symbols")
    required(isinstance(unknown,list) and len(unknown)==price.get("unknown_count") and
             len(unknown)==len(set(unknown)) and set(SAMPLE).issubset(set(unknown)), "SAMPLE_NOT_PRICE_UNKNOWN")
    required(isinstance(mp,list) and set(SAMPLE).issubset(set(mp)),"SAMPLE_NOT_MASTER_PASS")
    required(price.get("pass_count")==len(price.get("pass_symbols",[])), "PRICE_PASS_COUNT")
    return dates

def request_params(dates):
    start=dates[0]+"T00:00:00Z"
    end=(dt.date.fromisoformat(dates[-1])+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    return {"symbols":",".join(SAMPLE),"timeframe":"1Day","start":start,"end":end,
            "limit":str(MAX_BARS),"feed":"sip","adjustment":"raw","sort":"asc"}

def grant(env):
    return (env.get("XRAY_ALPACA_SIP_HISTORY_RESEARCH_LICENSE_OK","").strip().lower()=="true"
            and re.fullmatch(r"[0-9a-f]{64}",env.get("XRAY_ALPACA_SIP_HISTORY_LICENSE_EVIDENCE_SHA256","")) is not None)

def fetch(keys,dates):
    kid,secret=keys
    query=urllib.parse.urlencode(request_params(dates))
    req=urllib.request.Request(ENDPOINT+"?"+query,headers={
        "APCA-API-KEY-ID":kid, "APCA-API-SECRET-KEY":secret,
        "Accept":"application/json", "User-Agent":"XRAY-Research-NoOrders/1.0"})
    with urllib.request.urlopen(req,timeout=18) as resp:
        data=resp.read(MAX_BYTES+1)
    required(len(data)<=MAX_BYTES, "OVERSIZED_VENDOR_BODY")
    return json.loads(data)

def validate(doc,dates):
    required(isinstance(doc,dict) and isinstance(doc.get("bars"),dict), "NO_BARS_MAPPING")
    required(not doc.get("next_page_token"), "PAGINATION_NOT_COMPLETE")
    data=doc["bars"]
    required(set(data)==set(SAMPLE), "MISSING_OR_EXTRA_SYMBOL")
    expected=set(dates)
    out={}
    for sym in SAMPLE:
        rows=data[sym]
        required(isinstance(rows,list) and len(rows)==30,"NOT_30_BARS")
        seen=set()
        for bar in rows:
            required(isinstance(bar,dict), "BAD_BAR")
            raw_ts=bar.get("t")
            required(isinstance(raw_ts,str), "BAD_TIMESTAMP")
            instant=dt.datetime.fromisoformat(raw_ts.replace("Z","+00:00"))
            required(instant.tzinfo is not None, "NAIVE_TIMESTAMP")
            day=instant.astimezone(NY).date().isoformat()
            required(day in expected and day not in seen, "DATE_MISSING_DUPLICATE_OR_FOREIGN")
            seen.add(day)
            vals=[]
            for key in ("o","h","l","c"):
                val=bar.get(key)
                required(isinstance(val,(float,int)) and not isinstance(val,bool) and
                         math.isfinite(val) and val>0, "OHLC_INVALID")
                vals.append(float(val))
            o,h,l,c=vals
            required(h>=max(o,l,c) and l<=min(o,h,c), "OHLC_ORDER")
            v=bar.get("v")
            required(type(v) is int and v>0, "OFFICIAL_INTEGER_VOLUME_UNVERIFIED")
        required(seen==expected, "DATE_SET_MISMATCH")
        out[sym]={"completed_daily_bars":30,"date_set_exact":True,
                  "positive_integer_volume":True}
    return out

def report_base(asof=None):
    return {"schema":SCHEMA,"asof_et":asof,"policy":"C4.17","control":"C4.27",
        "status":"BLOCKED_INPUT_UNVERIFIED","requested_symbols":list(SAMPLE),
        "requested_symbol_count":len(SAMPLE),"valid_symbols":0,"valid_bars":0,
        "api_calls":0,"provider":"ALPACA_SIP_HISTORICAL","feed":"sip",
        "interactive_access_not_runner_authority":True,
        "runner_credentials_present":False,"operator_research_grant_claimed":False,
        "license_independently_verified":False,"official_rth_only_lineage_attested":False,
        "full_540_symbol_coverage":False,"primary_price_authority":False,
        "primary_mc_authority":False,"history_pass":False,
        "r92_created":False,"strict_g9_pass":False,"account_pass":False,
        "can_create_primary":False,"alpha_authority":False,
        "vendor_raw_data_persisted":False,"secrets_or_request_urls_persisted":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def run(price,master,latest,env,getter=fetch):
    out=report_base(price.get("asof_et"))
    try:
        dates=expected_sessions(price,master,latest)
    except Exception:
        out["status"]="BLOCKED_STALE_OR_INVALID_CURRENT_PRICE_SCOPE"
        return out
    kid=env.get("XRAY_ALPACA_API_KEY_ID","").strip()
    sec=env.get("XRAY_ALPACA_API_SECRET_KEY","").strip()
    out["runner_credentials_present"]=bool(kid and sec)
    out["operator_research_grant_claimed"]=grant(env)
    if not kid or not sec:
        out["status"]="BLOCKED_RUNNER_CREDENTIALS_NOT_CONFIGURED"
        return out
    if not grant(env):
        out["status"]="BLOCKED_UNATTESTED_UNATTENDED_RESEARCH_RIGHTS"
        return out
    out["api_calls"]=1
    try:
        doc=getter((kid,sec),dates)
        rows=validate(doc,dates)
        out["valid_symbols"]=len(rows)
        out["valid_bars"]=sum(v["completed_daily_bars"] for v in rows.values())
        out["status"]="SHADOW_EXACT30_TRANSPORT_CONFIRMED_NO_PRIMARY"
    except urllib.error.HTTPError as e:
        out["status"]=("BLOCKED_HTTP_401_403" if e.code in (401,403) else
                       "BLOCKED_HTTP_429" if e.code==429 else "BLOCKED_VENDOR_HTTP")
    except (urllib.error.URLError,OSError,TimeoutError):
        out["status"]="BLOCKED_VENDOR_TRANSPORT"
    except Exception:
        # Never serialize vendor body, URL or nested exceptions (may contain secrets).
        out["status"]="BLOCKED_VENDOR_SCHEMA_OR_INTEGRITY"
    return out

def selftest():
    from unittest.mock import patch
    # Pin an OFFLINE historical fixture; live current PRICE is allowed to
    # advance tomorrow, or eventually resolve all 540 UNKNOWN, without
    # making a valid negative regression selftest suddenly fail.
    import pandas_market_calendars as mcal
    dates=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-31",end_date="2026-10-12")]
    assert len(dates)==30
    source={"asof_et":"2026-10-12","execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"expected30":dates,"pass_symbols":[],
            "pass_count":0,"unknown_symbols":list(SAMPLE),"unknown_count":5}
    master={"asof_et":"2026-10-12","execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"pass_symbols":list(SAMPLE),"pass_count":5}
    assert expected_sessions(source,master,source["asof_et"])==dates
    def bars():
        def tick(day):
            et=dt.datetime.combine(dt.date.fromisoformat(day),dt.time.min,NY)
            return et.astimezone(dt.timezone.utc).isoformat().replace("+00:00","Z")
        return {"bars":{s:[{"t":tick(d),"o":10.0,"h":12.0,"l":9.0,"c":11.0,"v":100000}
                           for d in dates] for s in SAMPLE},"next_page_token":None}
    good=validate(bars(),dates)
    assert len(good)==5 and all(x["positive_integer_volume"] for x in good.values())
    import copy
    for bad in (
        lambda x:x["bars"]["AAPL"].pop(),
        lambda x:x["bars"]["AAPL"][0].update(v=100000.25),
        lambda x:x["bars"]["AAPL"][0].update(v="100000"),
        lambda x:x["bars"]["AAPL"][0].update(h=8.0),
        lambda x:x["bars"]["AAPL"][0].update(t="2026-11-02T04:00:00Z"),
        lambda x:x["bars"]["AAPL"][0].update(t=x["bars"]["AAPL"][1]["t"]),
        lambda x:x.update(next_page_token="MORE"),
        lambda x:x["bars"].pop("AAPL"),
        lambda x:x["bars"].update(ZZZZ=[]),
    ):
        target=copy.deepcopy(bars());bad(target)
        try:validate(target,dates)
        except (ValueError,TypeError):pass
        else:raise AssertionError("UNSAFE_SIP_BAR_ACCEPTED")
    assert request_params(dates)["feed"]=="sip" and request_params(dates)["adjustment"]=="raw"
    assert request_params(dates)["end"]==(
        dt.date.fromisoformat(dates[-1])+dt.timedelta(days=1)).isoformat()+"T00:00:00Z"
    assert grant({}) is False
    assert grant({"XRAY_ALPACA_SIP_HISTORY_RESEARCH_LICENSE_OK":"true",
                  "XRAY_ALPACA_SIP_HISTORY_LICENSE_EVIDENCE_SHA256":"NONSENSE"}) is False
    calls=[]
    def fake(keys,ds):
        calls.append((keys,ds))
        return bars()
    o=run(source,master,source["asof_et"],{},fake)
    assert o["api_calls"]==0 and not calls
    o=run(source,master,source["asof_et"],{
        "XRAY_ALPACA_API_KEY_ID":"fake","XRAY_ALPACA_API_SECRET_KEY":"fake"},fake)
    assert o["api_calls"]==0 and not calls and o["status"]=="BLOCKED_UNATTESTED_UNATTENDED_RESEARCH_RIGHTS"
    env={"XRAY_ALPACA_API_KEY_ID":"fake","XRAY_ALPACA_API_SECRET_KEY":"fake",
         "XRAY_ALPACA_SIP_HISTORY_RESEARCH_LICENSE_OK":"true",
         "XRAY_ALPACA_SIP_HISTORY_LICENSE_EVIDENCE_SHA256":"a"*64}
    o=run(source,master,source["asof_et"],env,fake)
    assert o["api_calls"]==1 and len(calls)==1 and o["valid_bars"]==150
    assert o["status"]=="SHADOW_EXACT30_TRANSPORT_CONFIRMED_NO_PRIMARY"
    assert all(o[k] is False for k in ("primary_price_authority","primary_mc_authority",
                "r92_created","history_pass","strict_g9_pass","account_pass",
                "vendor_raw_data_persisted","license_independently_verified"))
    o=run(source,master,"2026-10-09",env,fake)
    assert o["api_calls"]==0 and len(calls)==1
    with patch.dict(os.environ,{"TEST_SENTINEL":"NO_NETWORK"}):
        assert "fake" not in json.dumps(o)
    # REGRESSION: consolidated 1Day volume is not exclusive RTH volume.
    # Must be explicit, not inferred from 30 bars / integer volume.
    claim=report_base(source["asof_et"])
    assert claim["daily_sip_1day_volume_is_rth"] is False
    assert claim["rth_volume_requires_official_session_minutes"] is True
    assert claim["close_auction_allocation_verified"] is False
    print("XRAY_ALPACA_SIP_EXACT30_BACKUP_SELFTEST=PASS_5_SYMBOLS_9_NEGATIVES_NO_KEY_RIGHTS_STALE_ZERO_ALPHA")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest();return
    if args.out is None:
        p.error("--out required")
    if args.out.resolve().is_relative_to(REPO.resolve()):
        p.error("PUBLIC_REPO_OUTPUT_FORBIDDEN")
    from source_epoch_freshness_guard import last_complete_session
    try:
        master=json.loads(MASTER.read_text())
        price=json.loads(PRICE.read_text())
        latest=last_complete_session(dt.datetime.now(dt.timezone.utc))
        out=run(price,master,latest,os.environ)
    except Exception:
        out=report_base()
        out["status"]="BLOCKED_CANONICAL_OR_CALENDAR_UNREADABLE"
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_ALPACA_SIP_EXACT30_BACKUP="+out["status"])
    print("XRAY_ALPACA_SIP_CALLS="+str(out["api_calls"]))
    print("XRAY_ALPACA_SIP_NO_PRICE_PRIMARY_NO_MC_R92_G9_ACCOUNT=PASS")

if __name__=="__main__":
    main()
