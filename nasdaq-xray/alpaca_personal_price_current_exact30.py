#!/usr/bin/env python3
"""Automatic latest-session personal historical-SIP exact30 RTH lower-bound census.

No broker interaction. Does not require an enterprise redistribution license to
compute local historical research, but grants no extra API/data-feed permission.
30-minute 09:30-16:00 bars omit the closing auction. Results NEVER authorize
canonical C4.17 DV30/MC/AL/R92 without separate evidence. No OHLCV export.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,hashlib,json,os,time,urllib.error
from pathlib import Path
import pandas_market_calendars as mcal
from source_epoch_freshness_guard import last_complete_session
from alpaca_personal_price_20261013_exact30_census import (
    analyze,fetch,BATCH,CALL_BUDGET,STATES,
)
ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_CURRENT_EXACT30_SIP_PRICE_RECHECK_V1"

def require(ok,reason):
    if not ok:raise ValueError("XRAY_PERSONAL_CURRENT_PRICE_"+reason)

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+bytes([0])+data).hexdigest()

def dates30(asof):
    start=(dt.date.fromisoformat(asof)-dt.timedelta(days=85)).isoformat()
    dates=[str(x.date()) for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date=start,end_date=asof)]
    out=dates[-30:]
    require(len(out)==30 and len(set(out))==30 and out[-1]==asof,
            "EXACT_OFFICIAL_30")
    return out

def scope(master,price,now):
    require(now.tzinfo is not None and now.utcoffset()==dt.timedelta(),
            "AWARE_UTC_CLOCK")
    asof=last_complete_session(now)
    require(master.get("asof_et")==price.get("asof_et")==asof,
            "LATEST_MASTER_PRICE_ASOF")
    require(master.get("execution")==price.get("execution")=="NONE" and
            master.get("real_money")==price.get("real_money")=="NO-GO" and
            master.get("unknown_never_pass") is True and
            price.get("unknown_never_pass") is True,
            "SOURCE_SAFETY")
    full=master.get("pass_symbols")
    names=price.get("unknown_symbols")
    require(type(full) is list and full==sorted(set(full))
            and type(names) is list and names==sorted(set(names))
            and len(names)==price.get("unknown_count")
            and set(names).issubset(set(full))
            and len(full)==master.get("pass_count"),
            "EXACT_PRICE_RESIDUAL_WITHIN_MASTER")
    dates=dates30(asof)
    require(price.get("expected30")==dates,"CURRENT_CANONICAL_30_DATES")
    return asof,names,dates

def empty_report(asof,names,dates,master_blob,price_blob):
    return {"schema":SCHEMA,"asof_et":asof,
        "source_master_git_blob_sha":master_blob,
        "source_price_git_blob_sha":price_blob,
        "source_price_unknown_total":len(names),
        "source_price_unknown_symbols_sha256":hashlib.sha256(
            ("\\n".join(names)+"\\n").encode()).hexdigest(),
        "exact30_dates":dates,"source":"ALPACA_HISTORICAL_SIP_PERSONAL",
        "source_minute_granularity":"30Min_RTH_09_30_TO_16_00",
        "classifications":dict.fromkeys(names,"UNKNOWN_NOT_ATTEMPTED"),
        "scope_truncated":False,"scope_total":len(names),"classified_count":0,
        "attempted_count":0,"api_calls":0,"call_budget":CALL_BUDGET,
        "canonical_price_promoted":False,"canonical_mc_promoted":False,
        "canonical_files_mutated":False,"strict_live_G9_satisfied":False,
        "registered_R92_created":False,"personal_research_only":True,
        "auction_and_trade_correction_independently_verified":False,
        "official_rth_exact_volume_attested":False,
        "vendor_raw_OHLCV_written":False,"execution":"NONE",
        "real_money":"NO-GO","unknown_never_pass":True}

def finalize(report):
    x=report["classifications"]
    total=report["scope_total"]
    require(type(x) is dict and len(x)==total,"FULL_SYMBOL_PARTITION")
    report["counts"]=dict(sorted(collections.Counter(x.values()).items()))
    report["classified_count"]=sum(v!="UNKNOWN_NOT_ATTEMPTED" for v in x.values())
    report["all_symbols_classified"]=report["classified_count"]==total
    report["research_lower_bound_ge_50m_count"]=report["counts"].get(
        "LOWER_BOUND_GE_50M_SHADOW",0)
    report["price_primary_pass_count"]=0
    require(sum(report["counts"].values())==total and
            report["research_lower_bound_ge_50m_count"]<=report["classified_count"],
            "NO_PARTIAL_SCOPE_PASS")
    return report

def census(now,credentials,output,fetcher=fetch):
    master_raw=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    price_raw=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    master=json.loads(master_raw);price=json.loads(price_raw)
    asof,symbols,dates=scope(master,price,now)
    result=empty_report(asof,symbols,dates,blob(master_raw),blob(price_raw))
    result["source_sha_exact"]=True
    counters=[0]
    if output is not None:
        require(not output.resolve().is_relative_to(ROOT.parent.resolve()),
                "NO_VENDOR_DERIVED_REPO_WRITE")
    def checkpoint():
        result["api_calls"]=counters[0]
        finalize(result)
        if output is not None:
            output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\\n")
    checkpoint()
    for i in range(0,len(symbols),BATCH):
        block=symbols[i:i+BATCH]
        try:
            one,two=fetcher(block,dates,credentials,counters,asof=asof)
            measured=analyze(block,one,two,dates)
            require(set(measured)==set(block),"FULL_BATCH_PARTITION")
            result["classifications"].update(measured)
        except (urllib.error.HTTPError,urllib.error.URLError,
                ValueError,TimeoutError,OSError) as e:
            response_code=e.code if isinstance(e,urllib.error.HTTPError) else None
            result["classifications"].update({
                sym:("UNKNOWN_HTTP_"+str(response_code) if response_code else
                     "UNKNOWN_BATCH_TRANSPORT_OR_INTEGRITY") for sym in block
            })
            result["last_error_class"]=type(e).__name__
            if response_code in (401,403,429) or counters[0]>=CALL_BUDGET:
                result["provider_cliff"]=(
                    "AUTH_OR_ENTITLEMENT" if response_code in (401,403)
                    else "RATE_LIMIT_OR_BUDGET")
                checkpoint()
                break
        result["attempted_count"]+=len(block)
        checkpoint()
        if i+BATCH<len(symbols):time.sleep(0.7)
    finalize(result)
    checkpoint()
    return result

def selftest():
    asof="2026-10-13"
    d=dates30(asof)
    require(len(d)==30 and d[-1]==asof,"OFFICIAL_30")
    master={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True,"pass_count":3,
      "pass_symbols":["AAPL","MSFT","NVDA"]}
    price={"asof_et":asof,"execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True,"unknown_count":2,
      "unknown_symbols":["AAPL","MSFT"],"expected30":d}
    now=dt.datetime(2026,10,14,18,0,tzinfo=dt.timezone.utc)
    given,syms,dates=scope(master,price,now)
    require(given==asof and syms==["AAPL","MSFT"],"POSITIVE_LIVE_COHORT")
    bad=dict(price,unknown_symbols=["AAPL","OUTSIDE"])
    try:scope(master,bad,now)
    except ValueError:pass
    else:raise AssertionError("FOREIGN_SYMBOL_ACCEPTED")
    try:scope(master,price,dt.datetime(2026,10,15,21,0,
                                      tzinfo=dt.timezone.utc))
    except ValueError:pass
    else:raise AssertionError("STALE_COHORT_ACCEPTED")
    bad=dict(price,expected30=list(reversed(d)))
    try:scope(master,bad,now)
    except ValueError:pass
    else:raise AssertionError("BAD_CALENDAR_ACCEPTED")
    obj=empty_report(asof,syms,d,"a"*40,"b"*40)
    finalize(obj)
    require(obj["classified_count"]==0 and
            obj["price_primary_pass_count"]==0 and
            not obj["all_symbols_classified"],"FALSE_EMPTY_PASS")
    obj["classifications"]["AAPL"]="LOWER_BOUND_GE_50M_SHADOW"
    finalize(obj)
    require(obj["research_lower_bound_ge_50m_count"]==1 and
            obj["price_primary_pass_count"]==0,"FALSE_PRIMARY")
    print("XRAY_PERSONAL_CURRENT_PRICE_SELFTEST=PASS_DYNAMIC_ASOF_FULL_SCOPE_FIVE_NEGATIVES_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:return selftest()
    require(args.out is not None,"OUTPUT_REQUIRED")
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
         os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
         os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    require(bool(key and secret),"ACTUAL_PROVIDER_KEYS_REQUIRED")
    out=census(dt.datetime.now(dt.timezone.utc),(key,secret),args.out)
    print("XRAY_PERSONAL_CURRENT_PRICE_SCOPE="+str(
        out["classified_count"])+"/"+str(out["scope_total"]))
    print("XRAY_PERSONAL_CURRENT_PRICE_COUNTS="+json.dumps(out["counts"],sort_keys=True))
    print("XRAY_PERSONAL_CURRENT_PRICE_ASOF="+out["asof_et"])
    print("XRAY_PERSONAL_CURRENT_PRICE_NO_PRIMARY_R92=PASS")
if __name__=="__main__":main()
