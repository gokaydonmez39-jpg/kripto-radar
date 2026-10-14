#!/usr/bin/env python3
"""Re-probe all 168 Oct13 source-date gaps with 3 separate source families.

(1) Alpaca historical SIP observed bars: FIRST OBSERVED IN EXACT-260
    WINDOW only, never asserted as a security's original first trade.
(2) SEC submissions: exact current ticker->CIK and SEC filing acceptances
    are distinct from exchange listing dates.
(3) Nasdaq quote/IPO metadata: official FIRST LISTING date only if an
    explicit verified listing date is present. HTTP blocked -> UNKNOWN.
No automatic master or history PRIMARY, NO R92. SEC and Nasdaq have source
fair-use stop guards; cannot infer dates from SIC or the SEC first filing.
"""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, json, os, time, urllib.error
import urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import alpaca_root260_missing168_date_gaps as gap
from alpaca_root260_full_cohort_personal import request_one
import sec_official_free_mc_transport_probe as sec
from sec_free_mc_multisymbol_pit_audit import map_ciks

ASOF="2026-10-13"
SCHEMA="XRAY_168_ASOF13_THREE_SOURCE_DATE_CENSUS_V1"
FROZEN_SHA="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e"
ROOT_GIT="dd6d3e6574dc318017d46f412b69e2a5f1331df5"
START_RUN=38481474945
RECHECK_RUN=38484091581
SEC_URL="https://www.sec.gov/files/company_tickers_exchange.json"
SEC_MAX=168
ALPACA_MAX_CALLS=14
BATCH=12
NASDAQ_MAX=168
MIN_SOURCE_INTERVAL=0.57

def require(ok,code):
    if not ok:raise ValueError("XRAY_168_MULTISOURCE_"+code)

def official260():
    import pandas_market_calendars as mcal
    d=[x.date().isoformat() for x in mcal.get_calendar("NASDAQ").valid_days(
        start_date="2025-08-01",end_date=ASOF)]
    d=d[-260:]
    require(len(d)==260 and d[-1]==ASOF,"CALENDAR_260")
    return d

def read_frozen(path):
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==FROZEN_SHA,"SOURCE_SHA256")
    o=json.loads(raw)
    require(o.get("schema")=="XRAY_FULL_ROOT_260_52_PERSONAL_SIP_COHORT_V1"
        and o.get("asof_et")==ASOF and o.get("total_scope")==3185
        and o.get("source_root_git_blob_sha")==ROOT_GIT
        and o.get("full_scope_reached") is True,"FROZEN_ROOT_SCOPE")
    states=o["symbol_statuses"]
    targets=sorted(x for x,v in states.items()
      if v=="UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE")
    require(len(targets)==168 and len(set(targets))==168,
       "EXACT168_MEMBERSHIP")
    return targets

def first_seen(rows,dates):
    if type(rows) is not list:return None
    seen=set()
    for x in rows:
        if type(x) is not dict:return None
        t=x.get("t")
        if not isinstance(t,str):return None
        try:
            moment=dt.datetime.fromisoformat(t.replace("Z","+00:00"))
            if moment.tzinfo is None:return None
            day=moment.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        except (ValueError,TypeError,OverflowError):return None
        if day in seen:return None
        seen.add(day)
    return min(seen.intersection(dates)) if seen.intersection(dates) else None

def sec_vintage(doc,asof=ASOF):
    # SEC forms filed before the public listing are not the first Nasdaq trade.
    require(type(doc) is dict,"SUBMISSIONS_SHAPE")
    fil=(doc.get("filings") or {})
    recent=fil.get("recent") or {}
    dates=recent.get("filingDate") or []
    forms=recent.get("form") or []
    accepted=recent.get("acceptanceDateTime") or []
    early=[d for d in dates if isinstance(d,str) and d<=asof]
    old=[x.get("filingFrom") for x in (fil.get("files") or [])
         if isinstance(x,dict) and isinstance(x.get("filingFrom"),str)
         and x.get("filingFrom")<=asof]
    reg_dates=sorted(set(d for d,f in zip(dates,forms)
      if isinstance(d,str) and d<=asof and f in ("8-A12B","8-A12G","S-1","F-1","424B4")))
    return {"earliest_visible_sec_filing_date":min(early+old) if early+old else None,
      "first_visible_registration_or_prospectus_date":reg_dates[0] if reg_dates else None,
      "nasdaq_listing_date_inferred_from_sec":False,
      "latest_accepted_before_asof":max((str(x) for x in accepted
           if isinstance(x,str) and x[:10]<=asof),default=None),
      "reported_sic":doc.get("sic"),"sec_name":doc.get("name")}

def accept_listing_date(doc,symbol,first260):
    # Never confuse IPO announcement/calendar estimated pricing with actual
    # exchange listing. Only exact key-value evidence under same ticker.
    if not isinstance(doc,dict) or doc.get("status") not in (None,200):
        return None
    data=doc.get("data")
    if not isinstance(data,dict):return None
    actual=data.get("symbol")
    if actual is not None and actual!=symbol:return None
    # API fields are untrusted until checked against a separate Nasdaq source.
    # The official exchange listing-date observation remains REVIEW_REQUIRED.
    fields=[]
    for key in ("listingDate","firstTradeDate","listedDate"):
        value=data.get(key)
        if isinstance(value,str):
            try:
                d=dt.date.fromisoformat(value[:10]).isoformat()
                if d>=first260 and d<=ASOF:
                    fields.append((key,d))
            except ValueError:pass
    return fields[0] if len(fields)==1 else None

def nasdaq_quote(symbol):
    url="https://api.nasdaq.com/api/quote/"+urllib.parse.quote(symbol,safe="")+"/info?assetclass=stocks"
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0 (compatible; XRAY-Research/1.0)",
        "Accept":"application/json","Origin":"https://www.nasdaq.com"})
    with urllib.request.urlopen(req,timeout=13) as response:
        raw=response.read(900001)
    require(len(raw)<900001,"NASDAQ_RESPONSE_TOO_LARGE")
    return json.loads(raw)

def selftest():
    ds=official260()
    require(len(ds)==260 and ds[-1]==ASOF,"SELFTEST_CALENDAR")
    require(accept_listing_date({"data":{"symbol":"ABC","listingDate":ds[12]}},
                                "ABC",ds[0])==("listingDate",ds[12]),
                                "NASDAQ_DATE")
    require(accept_listing_date({"data":{"symbol":"OTHER","listingDate":ds[12]}},
                                "ABC",ds[0]) is None,"WRONG_TICKER_VETO")
    require(accept_listing_date({"data":{"symbol":"ABC","ipoDate":ds[12]}},
                                "ABC",ds[0]) is None,"IPO_ANNOUNCEMENT_VETO")
    require(sec_vintage({"filings":{"recent":{"filingDate":[ds[15]],
      "form":["8-A12B"]}}})["nasdaq_listing_date_inferred_from_sec"] is False,
      "SEC_IS_NOT_EXCHANGE")
    require(first_seen([{"t":ds[20]+"T04:00:00Z"}],ds)==ds[20],
      "ALPACA_FIRST_OBSERVED")
    print("XRAY_MISSING168_THREESOURCE_SELFTEST=PASS_PIT_IPO_LISTING_GUARDS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--frozen-root",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    require(a.frozen_root and a.out,"ONE_SHOT_ARGS")
    require(not a.out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),
            "NO_REPO_RAW_SOURCE_PERSISTENCE")
    syms=read_frozen(a.frozen_root)
    dates=official260()
    result={"schema":SCHEMA,"asof_et":ASOF,"asof_260_first_session":dates[0],
       "asof_260_last_session":dates[-1],
       "source_frozen_root_run":START_RUN,"frozen_root_sha256":FROZEN_SHA,
       "source_old_gap_diagnostic_run":RECHECK_RUN,
       "total_symbols":len(syms),"symbols":syms,
       "status":{s:"UNKNOWN_NOT_YET_CROSSCHECKED" for s in syms},
       "sources":{s:{} for s in syms},
       "alpaca_calls":0,"sec_requests":0,"nasdaq_requests":0,
       "sec_transport":"NOT_ATTEMPTED","nasdaq_transport":"NOT_ATTEMPTED",
       "proven_lt260_listing":0,
       "same_asof_history_primary_created":False,
       "canonical_history_written":False,"canonical_master_written":False,
       "r92_created":False,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True,"raw_provider_ohlcv_exported":False}
    def save():
        result["counts"]=dict(sorted(collections.Counter(result["status"].values()).items()))
        result["classified"]=sum(v!="UNKNOWN_NOT_YET_CROSSCHECKED" for v in result["status"].values())
        a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    save()
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    if key and secret:
        for i in range(0,168,BATCH):
            batch=syms[i:i+BATCH]
            require(result["alpaca_calls"]<ALPACA_MAX_CALLS,"ALPACA_CALL_CAP")
            result["alpaca_calls"]+=1
            try:
                data=request_one(batch,dates[0],key,secret)
                for sym in batch:
                    bars=data.get(sym,[])
                    first=first_seen(bars,dates)
                    result["sources"][sym]["alpaca_first_observed_in_260"]=first
                    result["sources"][sym]["alpaca_observed_rows_in_260"]=len(bars)
                    result["sources"][sym]["alpaca_first_trading_day_authoritative"]=False
            except (RuntimeError,ValueError) as e:
                for sym in batch:result["sources"][sym]["alpaca_error"]="SOURCE_STOP_OR_SHAPE"
                if "HTTP_403" in str(e) or "HTTP_429" in str(e):break
            save()
            time.sleep(.5)
    else:
        result["alpaca_transport"]="CREDENTIALS_UNAVAILABLE"

    ua=(os.getenv("XRAY_SEC_USER_AGENT") or "").strip()
    routes={}
    if sec.valid_operator_contact(ua):
        try:
            index=sec.get_json(SEC_URL,ua)
            result["sec_requests"]+=1
            routes=map_ciks(index)
            result["sec_transport"]="SEC_OFFICIAL_TICKER_INDEX_OK"
        except ValueError:
            result["sec_transport"]="SEC_INDEX_UNAVAILABLE"
    else:result["sec_transport"]="SEC_USER_AGENT_NOT_CONFIGURED"
    blocked=False
    for sym in syms:
        cik=routes.get(sym)
        result["sources"][sym]["sec_cik_current_map"]=cik
        result["sources"][sym]["sec_ticker_map_is_asof_pit"]=False
        if blocked or not cik:continue
        try:
            doc=sec.get_json("https://data.sec.gov/submissions/CIK"+cik+".json",ua)
            result["sec_requests"]+=1
            require(str(doc.get("cik","")).zfill(10)==cik,"SEC_CIK_RESPONSE_IDENTITY")
            result["sources"][sym]["sec_filing_vintage"]=sec_vintage(doc)
            result["sources"][sym]["sec_submission_source_url"]=
              "https://data.sec.gov/submissions/CIK"+cik+".json"
        except ValueError as err:
            msg=str(err)
            result["sources"][sym]["sec_filing_error"]="HTTP_OR_IDENTITY"
            if any(x in msg for x in ("SEC_HTTP_403","SEC_HTTP_429")):
                blocked=True
                result["sec_transport"]="FAIR_ACCESS_STOP"
        save()
        time.sleep(MIN_SOURCE_INTERVAL)
    if not blocked and routes:result["sec_transport"]="SUBMISSIONS_SCOPED_COMPLETE_WITH_UNKNOWN_ALLOWED"

    nasdaq_blocked=False
    for sym in syms:
        if nasdaq_blocked:break
        result["nasdaq_requests"]+=1
        try:
            obj=nasdaq_quote(sym)
            candidate=accept_listing_date(obj,sym,dates[0])
            if candidate:
                result["sources"][sym]["nasdaq_candidate_listing_date"]=candidate[1]
                result["sources"][sym]["nasdaq_candidate_date_field"]=candidate[0]
                result["sources"][sym]["nasdaq_date_secondary_validation"]="REQUIRED"
            else:
                result["sources"][sym]["nasdaq_listing_date"]="NOT_PRESENT_OR_UNCONFIRMED"
        except (urllib.error.HTTPError,urllib.error.URLError,ValueError,TimeoutError) as err:
            result["sources"][sym]["nasdaq_error"]="HTTP_OR_SCHEMA"
            if isinstance(err,urllib.error.HTTPError) and err.code in (403,429):
                nasdaq_blocked=True
                result["nasdaq_transport"]="HTTP_403_OR_429_STOP"
        save()
        time.sleep(.2)
    if not nasdaq_blocked:
        result["nasdaq_transport"]="API_SCOPE_VISITED_LISTING_DATE_MAY_BE_ABSENT"

    for sym in syms:
        prov=result["sources"][sym]
        # A single Nasdaq API tentative listing date is NOT yet strong enough
        # for irreversible canonical FAIL. Requires second official listing
        # witness as well as matching effective trade date and PIT identity.
        if prov.get("nasdaq_candidate_listing_date"):
            state="UNKNOWN_LISTING_DATE_NEEDS_INDEPENDENT_EXCHANGE_CONFIRMATION"
        elif prov.get("alpaca_first_observed_in_260"):
            state="UNKNOWN_EARLY_BAR_GAP_FIRST_LISTING_UNVERIFIED"
        else:
            state="UNKNOWN_SOURCE_INCOMPLETE_OR_NO_OFFICIAL_LISTING_DATE"
        result["status"][sym]=state
    result["proven_lt260_listing"]=0
    save()
    print("XRAY_168_SEC_CALLS="+str(result["sec_requests"]))
    print("XRAY_168_ALPACA_CALLS="+str(result["alpaca_calls"]))
    print("XRAY_168_NASDAQ_CALLS="+str(result["nasdaq_requests"]))
    print("XRAY_168_COUNTS="+json.dumps(result["counts"],sort_keys=True))
    print("XRAY_168_NO_FABRICATED_IPO_OR_PRIMARY=PASS")

if __name__=="__main__":main()
