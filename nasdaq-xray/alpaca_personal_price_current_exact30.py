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
    analyze as archived_analyze,fetch,BATCH,CALL_BUDGET,STATES,
)
from decimal import Decimal
from alpaca_rth_minute_integrity_shadow import official_window
from alpaca_sip_30min_rth_lower_bound_pilot import stamp,data_check,NY
from alpaca_sip_4symbol_30min_rth_shadow import LIMIT
from functools import lru_cache

@lru_cache(maxsize=128)
def cached_official_window(day):
    return official_window(day)
ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_CURRENT_EXACT30_SIP_PRICE_RECHECK_V1"
MAX_INTEGRITY_RECHECKS=8
INTEGRITY_UNKNOWN="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
RESEARCH_BOUNDS={
    "LOWER_BOUND_GE_50M_SHADOW",
    "UPPER_BOUND_LT_50M_SHADOW",
    "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
}

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
            ("\n".join(names)+"\n").encode()).hexdigest(),
        "exact30_dates":dates,"source":"ALPACA_HISTORICAL_SIP_PERSONAL",
        "source_minute_granularity":"30Min_RTH_09_30_TO_16_00",
        "classifications":dict.fromkeys(names,"UNKNOWN_NOT_ATTEMPTED"),
        "scope_truncated":False,"scope_total":len(names),"classified_count":0,
        "attempted_count":0,"api_calls":0,"call_budget":CALL_BUDGET,
        "integrity_recheck_limit":MAX_INTEGRITY_RECHECKS,
        "integrity_recheck_candidate_count":0,
        "integrity_recheck_attempted":0,
        "integrity_recheck_recovered":0,
        "integrity_recheck_unresolved":0,
        "integrity_recheck_status":"NOT_STARTED",
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

def classify_mixed_full_and_early(daily,halfhour,days):
    """True NASDAQ 13:00 early-close support, never force 390-minute assumptions."""
    expected={}
    windows={}
    for day in days:
        start,close,minutes=cached_official_window(day)
        require(minutes in (210,390) and minutes%30==0,
                "OFFICIAL_SESSION_LENGTH")
        windows[day]=(start,minutes)
        for i in range(minutes//30):
            t=start+dt.timedelta(minutes=i*30)
            require(t not in expected and t<close,"BAR_SLOT_INTEGRITY")
            expected[t]=day
    daybars={}
    for bar in daily:
        at=stamp(bar).astimezone(NY).date().isoformat()
        if at in windows:
            require(at not in daybars,"DUPLICATE_DAILY")
            data_check(bar)
            daybars[at]=bar
    require(set(daybars)==set(days),"EXACT_30_DAILY_SET")
    half={}
    for bar in halfhour:
        at=stamp(bar)
        if at in expected:
            require(at not in half,"DUPLICATE_30MIN")
            half[at]=data_check(bar)
    require(set(half)==set(expected),"EARLY_AND_FULL_BAR_COUNTS_EXACT")
    lower=[];upper=[]
    for day in days:
        start,n=windows[day]
        rth=sum(half[start+dt.timedelta(minutes=i*30)]
                for i in range(n//30))
        daily_volume=data_check(daybars[day])
        require(rth<=daily_volume,"DAILY_VOLUME_BOUND")
        close=Decimal(str(daybars[day]["c"]))
        require(close.is_finite() and close>0,"CLOSE_PRICE")
        lower.append(close*rth)
        upper.append(close*daily_volume)
    lower.sort();upper.sort()
    lo=(lower[14]+lower[15])/Decimal(2)
    hi=(upper[14]+upper[15])/Decimal(2)
    require(lo<=hi,"BOUNDS_INVERSION")
    if lo>=LIMIT:return "LOWER_BOUND_GE_50M_SHADOW"
    if hi<LIMIT:return "UPPER_BOUND_LT_50M_SHADOW"
    return "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW"

def dynamic_analyze(batch,daily,halfhour,days):
    require(set(daily)<=set(batch) and set(halfhour)<=set(batch),
            "FOREIGN_BATCH_KEY")
    if all(cached_official_window(d)[2]==390 for d in days):
        return archived_analyze(batch,daily,halfhour,days)
    found={}
    for sym in batch:
        try:
            found[sym]=classify_mixed_full_and_early(
                daily.get(sym,[]),halfhour.get(sym,[]),days)
        except (ValueError,TypeError,KeyError,OverflowError):
            found[sym]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    require(set(found)==set(batch) and set(found.values())<=STATES,
            "COMPLETE_MIXED_CLASSIFICATION")
    return found

def isolated_integrity_recheck(report,dates,credentials,counters,fetcher,
                               analyzer=dynamic_analyze,checkpoint=None,
                               *,max_rechecks=MAX_INTEGRITY_RECHECKS):
    """One bounded, single-symbol retry for malformed/missing 30-day SIP bars.

    A retry is purely research-level. It cannot repair an auction/rights/
    corporate-action authority gap, create PRICE PASS, or rewrite canonical.
    """
    require(type(max_rechecks) is int and 0<=max_rechecks<=MAX_INTEGRITY_RECHECKS,
            "ISOLATED_RECHECK_CAP")
    statuses=report["classifications"]
    candidates=sorted(s for s,v in statuses.items() if v==INTEGRITY_UNKNOWN)
    report["integrity_recheck_candidate_count"]=len(candidates)
    report["integrity_recheck_unresolved"]=len(candidates)
    report["integrity_recheck_status"]="NO_GAPS" if not candidates else "BOUNDED_RESEARCH_RECHECK"
    for sym in candidates[:max_rechecks]:
        if counters[0]>=CALL_BUDGET:
            report["integrity_recheck_status"]="GLOBAL_BUDGET_EXHAUSTED"
            break
        before=counters[0]
        report["integrity_recheck_attempted"]+=1
        try:
            daily,half=fetcher([sym],dates,credentials,counters,asof=report["asof_et"])
            result=analyzer([sym],daily,half,dates)
            require(type(result) is dict and set(result)=={sym},
                    "ISOLATED_RESULT_SCOPE")
            observed=result[sym]
            require(observed in RESEARCH_BOUNDS | {INTEGRITY_UNKNOWN},
                    "ISOLATED_INVALID_CLASSIFICATION")
            if observed in RESEARCH_BOUNDS:
                require(statuses[sym]==INTEGRITY_UNKNOWN,
                        "ISOLATED_ONLY_PREVIOUS_UNKNOWN")
                statuses[sym]=observed
                report["integrity_recheck_recovered"]+=1
        except (urllib.error.HTTPError,urllib.error.URLError,ValueError,
                TimeoutError,OSError) as exc:
            if isinstance(exc,urllib.error.HTTPError) and exc.code in (401,403,429):
                report["integrity_recheck_status"]="PROVIDER_AUTH_OR_RATE_LIMIT_STOP"
                break
            report["integrity_recheck_status"]="SOME_SOURCE_GAPS_UNRESOLVED"
        finally:
            require(before<=counters[0]<=CALL_BUDGET,
                    "ISOLATED_BUDGET_OVERRUN")
            report["integrity_recheck_unresolved"]=sum(
                x==INTEGRITY_UNKNOWN for x in statuses.values())
            report["api_calls"]=counters[0]
            finalize(report)
            if checkpoint is not None:
                checkpoint()
    require(report["integrity_recheck_recovered"]+
            report["integrity_recheck_unresolved"]==
            report["integrity_recheck_candidate_count"],
            "ISOLATED_GAP_ACCOUNTING")
    if report["integrity_recheck_status"]=="BOUNDED_RESEARCH_RECHECK":
        report["integrity_recheck_status"]=(
            "ALL_ISOLATED_GAPS_REMEASURED_SHADOW"
            if report["integrity_recheck_unresolved"]==0 else
            "SOME_SOURCE_GAPS_UNRESOLVED")
    require(report.get("price_primary_pass_count")==0 and
            report.get("registered_R92_created") is False,
            "ISOLATED_NEVER_PRIMARY")
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
            output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    checkpoint()
    for i in range(0,len(symbols),BATCH):
        block=symbols[i:i+BATCH]
        try:
            one,two=fetcher(block,dates,credentials,counters,asof=asof)
            measured=dynamic_analyze(block,one,two,dates)
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
    if not result.get("provider_cliff"):
        isolated_integrity_recheck(result,dates,credentials,counters,fetcher,
                                   checkpoint=checkpoint)
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
    # A future early close must not make every symbol UNKNOWN for 30 days.
    early_dates=dates30("2026-11-27")
    require("2026-11-27" in early_dates and
            cached_official_window("2026-11-27")[2]==210,
            "OFFICIAL_13ET_EARLY_CLOSE")
    synth_day=[];synth_half=[]
    for day in early_dates:
        start,close,minutes=cached_official_window(day)
        midnight=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(),
                                      NY).astimezone(dt.timezone.utc)
        synth_day.append({"t":midnight.isoformat(),"o":100.0,"h":101.0,
            "l":99.0,"c":100.0,"v":600000})
        for i in range(minutes//30):
            t=start+dt.timedelta(minutes=i*30)
            synth_half.append({"t":t.isoformat(),"o":100.0,"h":101.0,
                "l":99.0,"c":100.0,"v":1000})
    observed=classify_mixed_full_and_early(synth_day,synth_half,early_dates)
    require(observed=="AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
            "EARLY_CLOSE_COVERAGE_NOT_FALSE_UNKNOWN")
    broken=synth_half[:-1]
    try:classify_mixed_full_and_early(synth_day,broken,early_dates)
    except ValueError:pass
    else:raise AssertionError("MISSING_13ET_HALF_HOUR_NOT_REJECTED")
    # Offline single-symbol recovery test: exactly one recheck, not a second
    # universe-wide request; no vendor credentials or real price observations.
    recovered=empty_report(asof,syms,d,"a"*40,"b"*40)
    recovered["classifications"]={"AAPL":INTEGRITY_UNKNOWN,
                                  "MSFT":INTEGRITY_UNKNOWN}
    finalize(recovered)
    calls=[0]
    queries=[]
    def fake_fetch(block,dates,creds,counter,asof):
        queries.append((tuple(block),asof))
        counter[0]+=2
        return {},{}
    def fake_analyzer(block,daily,halfhour,dates):
        return {block[0]:("LOWER_BOUND_GE_50M_SHADOW"
                          if block[0]=="AAPL" else INTEGRITY_UNKNOWN)}
    isolated_integrity_recheck(recovered,d,("NOT_USED","NOT_USED"),calls,
                               fake_fetch,analyzer=fake_analyzer)
    require(queries==[(("AAPL",),asof),(("MSFT",),asof)]
            and calls[0]==4
            and recovered["integrity_recheck_recovered"]==1
            and recovered["integrity_recheck_unresolved"]==1
            and recovered["classifications"]["MSFT"]==INTEGRITY_UNKNOWN
            and recovered["price_primary_pass_count"]==0
            and not recovered["registered_R92_created"],
            "ISOLATED_RECHECK_ONE_RECOVERED_ONE_UNRESOLVED")
    # No provider probing when the global HTTP call budget is exhausted.
    exhausted=empty_report(asof,syms,d,"a"*40,"b"*40)
    exhausted["classifications"]["AAPL"]=INTEGRITY_UNKNOWN
    finalize(exhausted)
    stop=[CALL_BUDGET]
    isolated_integrity_recheck(exhausted,d,(),stop,
                               lambda *args,**kwargs:
                               (_ for _ in ()).throw(AssertionError("HTTP_CALLED")))
    require(exhausted["integrity_recheck_status"]=="GLOBAL_BUDGET_EXHAUSTED"
            and exhausted["integrity_recheck_attempted"]==0
            and exhausted["integrity_recheck_unresolved"]==1,
            "RECHECK_BUDGET_FATAL")
    # Authentication/rate-limit failures never become a plausible PASS.
    auth=empty_report(asof,syms,d,"a"*40,"b"*40)
    auth["classifications"]={"AAPL":INTEGRITY_UNKNOWN,
                             "MSFT":INTEGRITY_UNKNOWN}
    finalize(auth)
    def denied(block,dates,creds,counter,asof):
        counter[0]+=1
        raise urllib.error.HTTPError("https://data.alpaca.markets",
                                     403,"Denied",{},None)
    isolated_integrity_recheck(auth,d,(),[0],denied)
    require(auth["integrity_recheck_status"]=="PROVIDER_AUTH_OR_RATE_LIMIT_STOP"
            and auth["integrity_recheck_attempted"]==1
            and auth["integrity_recheck_unresolved"]==2
            and auth["price_primary_pass_count"]==0,
            "RECHECK_PROVIDER_CLIFF_NEVER_PASS")
    print("XRAY_PERSONAL_CURRENT_PRICE_SELFTEST=PASS_DYNAMIC_ASOF_EARLY_CLOSE_ISOLATED_RECOVERY_BUDGET_AUTH_NEGATIVES_NO_PRIMARY")

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
