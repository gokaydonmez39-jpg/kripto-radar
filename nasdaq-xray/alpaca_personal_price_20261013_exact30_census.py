#!/usr/bin/env python3
"""Oct 13 PERSONAL historical SIP exact-30 30Min DV30 bounded census.

Uses actual 2026-10-13 canonical MASTER/PRICE sha and official Nasdaq
calendar, never Oct 12 volume or price. HTTP-only licensed-credential scope
(Alpaca historical SIP). Closing auction/corrections not verified; 30Min is
a lower bound and cannot authorize C4.17 PRIMARY, MC or R92.
No OHLCV persisted.
"""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, json, os, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
import alpaca_sip_4symbol_30min_rth_shadow as pilot
from alpaca_sip_30min_rth_lower_bound_pilot import stamp
from alpaca_sip_request_pacer import PACER

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
SCHEMA="XRAY_ALPACA_20261013_FULL_UNKNOWN_SCOPE_30MIN_SHADOW_V1"
BATCH=8
CALL_BUDGET=1200
MAX_PAGE_BYTES=2500000
FULL_RUN=38481474945
FULL_SHA256="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e"
STATES={"LOWER_BOUND_GE_50M_SHADOW","UPPER_BOUND_LT_50M_SHADOW",
        "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
        "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"}

def demand(value,code):
    if not value:raise ValueError("XRAY_PRICE_20261013_"+code)

def blobsha(p):
    b=p.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def dates30():
    import pandas_market_calendars as mcal
    all_dates=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2026-08-25",end_date=ASOF)]
    d=all_dates[-30:]
    demand(len(d)==30 and d[-1]==ASOF and len(set(d))==30,"OFFICIAL_30_CALENDAR")
    return d

def scope(now=None):
    # Fail closed on a stale session: an old frozen census is never evidence
    # for the latest market date, even when the vendor endpoint still serves it.
    from source_epoch_freshness_guard import last_complete_session
    now=now or dt.datetime.now(dt.timezone.utc)
    demand(now.tzinfo is not None and
           last_complete_session(now)==ASOF,"NOT_LATEST_COMPLETED_ASOF")
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text())
    demand(master.get("asof_et")==price.get("asof_et")==ASOF,"EXACT_SOURCE_ASOF")
    symbols=price.get("unknown_symbols")
    demand(type(symbols) is list and symbols==sorted(set(symbols))
           and len(symbols)==price.get("unknown_count")
           and len(symbols)>0 and len(symbols)<=650,"C4_PRICE_UNKNOWN_SCOPE")
    demand(set(symbols).issubset(set(master["pass_symbols"]))
           and master.get("unknown_never_pass") is True
           and price.get("unknown_never_pass") is True
           and price.get("execution")==master.get("execution")=="NONE"
           and price.get("real_money")==master.get("real_money")=="NO-GO",
           "MASTER_AND_PRICE_SAFETY")
    return symbols,dates30(),blobsha(ROOT/"canonical_current_master_manifest.json"),blobsha(ROOT/"canonical_current_price_dv30.json")

def fetch(batch,dates,creds,calls,asof=ASOF):
    base="https://data.alpaca.markets/v2/stocks/bars"
    out=[]
    # Start at the first session's ET midnight, finish after the exact target.
    from zoneinfo import ZoneInfo
    ny=ZoneInfo("America/New_York")
    first=dt.datetime.combine(dt.date.fromisoformat(dates[0]),dt.time(0),tzinfo=ny)
    last=dt.datetime.combine(dt.date.fromisoformat(asof)+dt.timedelta(days=1),
                             dt.time(0),tzinfo=ny)
    for tf in ("1Day","30Min"):
        token=None
        seen=set()
        merged={}
        for _ in range(150):
            demand(calls[0]<CALL_BUDGET,"GLOBAL_HTTP_BUDGET")
            params={"symbols":",".join(batch),"timeframe":tf,
                    "feed":"sip","adjustment":"raw","sort":"asc",
                    "limit":"10000","start":first.isoformat(),
                    "end":last.isoformat()}
            if token:params["page_token"]=token
            req=urllib.request.Request(base+"?"+urllib.parse.urlencode(params),
                headers={"APCA-API-KEY-ID":creds[0],
                         "APCA-API-SECRET-KEY":creds[1],
                         "Accept":"application/json"})
            PACER.pace()  # Count page tokens against account-level RPM.
            calls[0]+=1
            with urllib.request.urlopen(req,timeout=32) as rsp:
                raw=rsp.read(MAX_PAGE_BYTES+1)
            demand(len(raw)<=MAX_PAGE_BYTES,"RESPONSE_BODY_LIMIT")
            data=json.loads(raw)
            demand(type(data) is dict and type(data.get("bars")) is dict,"BAR_RESPONSE")
            for symbol,rows in data["bars"].items():
                demand(symbol in batch and type(rows) is list,"FOREIGN_OR_MALFORMED_SYMBOL")
                merged.setdefault(symbol,[]).extend(rows)
            nxt=data.get("next_page_token")
            if not nxt:break
            demand(isinstance(nxt,str) and nxt not in seen,"PAGE_TOKEN_LOOP")
            seen.add(nxt);token=nxt
        else:
            raise ValueError("XRAY_PRICE_20261013_PAGES_OVER_150")
        out.append(merged)
    return out

def history_join(hist_path,symbols,status):
    if hist_path is None:return None
    raw=hist_path.read_bytes()
    demand(hashlib.sha256(raw).hexdigest()==FULL_SHA256,"ROOT_HISTORY_IMMUTABLE_SHA")
    doc=json.loads(raw)
    demand(doc.get("asof_et")==ASOF and doc.get("total_scope")==3185
           and doc.get("source_root_git_blob_sha")==
             "dd6d3e6574dc318017d46f412b69e2a5f1331df5","HISTORY_PROVENANCE")
    hs=doc.get("symbol_statuses") or {}
    demand(len(hs)==3185 and set(symbols).issubset(set(hs)),"PRICE_HISTORY_MEMBERSHIP")
    ok={"OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY",
        "PRIOR_VERIFIED_260_52_SIP_SHADOW_NOT_PRIMARY"}
    positive=[s for s in symbols if status.get(s)=="LOWER_BOUND_GE_50M_SHADOW"]
    joint=sorted(s for s in positive if hs.get(s) in ok)
    return {"history_run_id":FULL_RUN,"history_json_sha256":FULL_SHA256,
            "history_asof_et":ASOF,"history_positive_raw_count":2679,
            "price_positive_lower_bound_count":len(positive),
            "same_asof_price_lower_bound_and_history_raw_shadow_count":len(joint),
            "same_asof_shadow_intersection_symbols":joint,
            "claim_primary":False}

def analyze(batch,daily,halfhour,dates):
    demand(type(daily) is dict and type(halfhour) is dict,"CENSUS_RESPONSE")
    demand(set(daily).issubset(set(batch)) and
           set(halfhour).issubset(set(batch)),"CENSUS_FOREIGN_KEY")
    found={}
    for sym in batch:
        try:
            found[sym]=pilot.classify_one(daily.get(sym,[]),halfhour.get(sym,[]),dates)
        except (KeyError,ValueError,TypeError,OverflowError):
            found[sym]="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
    demand(set(found)==set(batch) and set(found.values()).issubset(STATES),
           "CENSUS_ALL_SYMBOLS_EXACT")
    return found

def selftest():
    d=dates30()
    demand(d[-1]==ASOF and len(d)==30,"TEST_30")
    # Current 3184/545 source partition, not the earlier 3185-issuer
    # independent HISTORY cohort. Never infer PRICE primary from their join.
    now=dt.datetime(2026,10,14,18,0,tzinfo=dt.timezone.utc)
    symbols,days,master_sha,price_sha=scope(now)
    demand(len(symbols)==545 and days==d and
           len(master_sha)==len(price_sha)==40,"CURRENT_545_SHA_SCOPE")
    try:scope(dt.datetime(2026,10,15,21,0,tzinfo=dt.timezone.utc))
    except ValueError as exc:
        demand("NOT_LATEST_COMPLETED_ASOF" in str(exc),"STALE_REASON")
    else:raise AssertionError("OLD_13OCT_SCOPE_ACCEPTED_ON_15OCT")
    b=["AAPL","MSFT"]
    demand(analyze(b,{}, {},d)==dict.fromkeys(b,"UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"),
           "MISSING_PRICE_NEVER_PASS")
    try:analyze(["AAPL"],{"OTHER":[]},{},d)
    except ValueError:pass
    else:raise AssertionError("FOREIGN_NOT_BLOCKED")
    print("XRAY_PRICE13_OFFLINE_SELFTEST=PASS_REAL_545_SCOPE_FRESHNESS_SHA_30_SESSIONS_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--oct13-census",action="store_true")
    p.add_argument("--history-artifact",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:
        demand(not a.oct13_census,"SELFTEST_ARGS")
        selftest();return
    demand(a.oct13_census and a.out and a.history_artifact,"ONE_SHOT")
    demand(not a.out.resolve().is_relative_to(ROOT.parent.resolve()),"NO_RAW_REPO_EXPORT")
    syms,dates,master_sha,price_sha=scope()
    statuses={s:"UNKNOWN_NOT_ATTEMPTED" for s in syms}
    r={"schema":SCHEMA,"asof_et":ASOF,"canonical_master_git_blob_sha":master_sha,
       "canonical_price_git_blob_sha":price_sha,"source_price_unknown_count":len(syms),
       "exact30_dates":dates,
       "exact30_calendar_sha256":hashlib.sha256(("\n".join(dates)+"\n").encode()).hexdigest(),
       "provider":"ALPACA_HISTORICAL_SIP_PERSONAL",
       "symbol_statuses":statuses,"api_calls":0,"call_budget":CALL_BUDGET,
       "official_close_auction_price_independently_verified":False,
       "trade_cancel_correction_lineage_reconciled":False,
       "rth_exact_total_volume_independently_verified":False,
       "multisource_vendor_independence_verified":False,
       "automated_provider_entitlement_attested":False,
       "primary_price_count":0,"primary_mc_count":0,"r92_created":False,
       "canonical_files_mutated":False,"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "vendor_raw_ohlcv_persisted":False}
    def save():
        r["counts"]=dict(sorted(collections.Counter(statuses.values()).items()))
        r["classified_count"]=sum(s!="UNKNOWN_NOT_ATTEMPTED" for s in statuses.values())
        r["all_scope_attempted"]=r["classified_count"]==len(syms)
        r["same_asof_history"]=history_join(a.history_artifact,syms,statuses)
        a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    save()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    demand(bool(key and secret),"PERSONAL_PROVIDER_CREDENTIALS_ABSENT")
    calls=[0]
    for i in range(0,len(syms),BATCH):
        b=syms[i:i+BATCH]
        try:
            day,half=fetch(b,dates,(key,secret),calls)
            statuses.update(analyze(b,day,half,dates))
        except (urllib.error.HTTPError,urllib.error.URLError,ValueError,TimeoutError) as err:
            reason=("HTTP_"+str(err.code)) if isinstance(err,urllib.error.HTTPError) else "BATCH_RETRIEVAL_ERROR"
            r["provider_stop_reason"]=reason
            for sym in b:statuses[sym]="UNKNOWN_"+reason
            if reason in ("HTTP_403","HTTP_429") or calls[0]>=CALL_BUDGET:
                break
        r["api_calls"]=calls[0]
        save()
        if i+BATCH<len(syms):time.sleep(0.7)
    r["api_calls"]=calls[0]
    save()
    print("XRAY_PRICE13_COUNTS="+json.dumps(r["counts"],sort_keys=True))
    print("XRAY_PRICE13_SCOPE="+str(r["classified_count"])+"/"+str(len(syms)))
    print("XRAY_PRICE13_HTTP="+str(calls[0]))
    print("XRAY_PRICE13_SAME_ASOF_HISTORY_LOWER_BOUND="+str(
      r["same_asof_history"]["same_asof_price_lower_bound_and_history_raw_shadow_count"]))
    print("XRAY_PRICE13_PRIMARY=0_SEC_MC=0_R92=0")

if __name__=="__main__":main()
