#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, re, urllib.parse, xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from resilience_runtime import fetch_json, fetch_text

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_macro_context.json"
# Context only: seven calendar days is an upper age bound, not a same-session
# quote or trading authority. Weekends/holidays need no fabricated observations.
MAX_AGE_DAYS=7
CROSSCHECK_TOLERANCE_PCT_POINTS=0.01

def now(): return datetime.now(timezone.utc).isoformat()
def local(tag): return tag.rsplit("}",1)[-1]

def safe_error(exc):
    # Do not persist exception messages: a request URL may contain a key.
    status=getattr(exc,"code",None)
    if type(status) is int and 100<=status<=599:
        return "HTTP_"+str(status)
    return "PROVIDER_OR_PARSE_ERROR"

def observation_day(value):
    if not isinstance(value,str):
        raise ValueError("INVALID_OBSERVATION_DATE")
    d=date.fromisoformat(value)
    if d.isoformat()!=value:
        raise ValueError("NONCANONICAL_OBSERVATION_DATE")
    return d

def numeric(value):
    if type(value) not in (str,int,float):
        raise ValueError("INVALID_OBSERVATION_VALUE")
    x=float(value)
    if not math.isfinite(x):
        raise ValueError("NONFINITE_OBSERVATION_VALUE")
    return x

def usable_day(value,today):
    d=observation_day(value)
    age=(today-d).days
    if not 0<=age<=MAX_AGE_DAYS:
        raise ValueError("OBSERVATION_NOT_WITHIN_AGE_BOUND")
    return d

def latest_fred(payload,today):
    observations=payload.get("observations")
    if not isinstance(observations,list):
        raise ValueError("OBSERVATIONS_MISSING")
    rows={}
    for x in observations:
        if not isinstance(x,dict):
            raise ValueError("OBSERVATION_SCHEMA")
        if x.get("value") in (None,"."):
            continue
        d=observation_day(x.get("date"))
        if d>today:
            raise ValueError("FUTURE_OBSERVATION")
        v=numeric(x["value"])
        if d in rows and numeric(rows[d]["value"])!=v:
            raise ValueError("CONFLICTING_OBSERVATION")
        rows[d]={"date":d.isoformat(),"value":str(v)}
    if not rows:
        raise ValueError("NO_NUMERIC_OBSERVATION")
    row=rows[max(rows)]
    usable_day(row["date"],today)
    return row

def treasury_fallback(today):
    year=today.year
    url=f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    xml=fetch_text("US_TREASURY_YIELD_CURVE",url,{
        "Accept":"application/xml,text/xml;q=0.9,*/*;q=0.8",
        "User-Agent":"NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar",
    },cache_ttl=900)
    root=ET.fromstring(xml)
    rows={}
    for entry in root.iter():
        if local(entry.tag)!="entry": continue
        vals={}
        for el in entry.iter():
            name=local(el.tag)
            txt=(el.text or "").strip()
            if txt: vals[name]=txt
        stamp=vals.get("NEW_DATE") or vals.get("Date") or vals.get("date")
        y2=vals.get("BC_2YEAR") or vals.get("BC_2_YEAR")
        y10=vals.get("BC_10YEAR") or vals.get("BC_10_YEAR")
        if not (stamp and y2 and y10):
            continue
        d=observation_day(stamp[:10])
        if d>today:
            raise ValueError("FUTURE_TREASURY_OBSERVATION")
        pair=(numeric(y2),numeric(y10))
        if d in rows and rows[d]!=pair:
            raise ValueError("CONFLICTING_TREASURY_OBSERVATION")
        rows[d]=pair
    if not rows: raise RuntimeError("TREASURY_XML_NO_2Y_10Y_ROWS")
    d=max(rows)
    usable_day(d.isoformat(),today)
    y2,y10=rows[d]
    return {"date":d.isoformat(),"dgs2":y2,"dgs10":y10,
        "spread_2s10s_pct_points":round(y10-y2,4),
        "source":"US_TREASURY_DAILY_PAR_YIELD_CURVE_XML"}

def pair_from_series(series,today):
    try:
        a,b=series["DGS2"],series["DGS10"]
        if not isinstance(a,dict) or not isinstance(b,dict):
            return None
        if "status" in a or "status" in b:
            return None
        d=usable_day(a["date"],today)
        if usable_day(b["date"],today)!=d:
            return None
        return (d,numeric(a["value"]),numeric(b["value"]))
    except (KeyError,TypeError,ValueError,OverflowError):
        return None

def pair_from_treasury(treasury,today):
    try:
        if not isinstance(treasury,dict) or "status" in treasury:
            return None
        return (usable_day(treasury["date"],today),numeric(treasury["dgs2"]),numeric(treasury["dgs10"]))
    except (KeyError,TypeError,ValueError,OverflowError):
        return None

def select_context(series,treasury,today):
    f=pair_from_series(series,today)
    t=pair_from_treasury(treasury,today)
    out={"status":"UNKNOWN","authority":"NO_MACRO_WITNESS",
         "observation_date":None,"same_date_crosscheck":False,
         "reason":"NO_VALID_FRESH_SAME_DATE_PAIR"}
    if f and t and f[0]==t[0]:
        if any(abs(x-y)>CROSSCHECK_TOLERANCE_PCT_POINTS+1e-12 for x,y in zip(f[1:],t[1:])):
            out["reason"]="SAME_DATE_SOURCE_DISAGREEMENT"
            return out
        out.update(status="READY",authority="FRED_WITH_TREASURY_CROSSCHECK",
                   observation_date=f[0].isoformat(),same_date_crosscheck=True,reason="VALID_SAME_DATE_PAIR")
    elif f and (not t or f[0]>t[0]):
        out.update(status="READY",authority="FRED_ONLY",
                   observation_date=f[0].isoformat(),reason="TREASURY_UNAVAILABLE_OR_OLDER")
    elif t:
        out.update(status="READY",authority="US_TREASURY_ZERO_KEY_FALLBACK",
                   observation_date=t[0].isoformat(),reason="FRED_PAIR_UNAVAILABLE_OR_OLDER")
    return out

def validate_artifact(out,at):
    """Publication schema + recency guard. No market/trading authority."""
    def require(ok,label):
        if not ok: raise ValueError(label)
    required={"schema","execution","real_money","alpha_authority","generated_at_utc",
              "series","source_priority","context_only","max_age_calendar_days",
              "crosscheck_tolerance_pct_points","treasury_zero_key","status","authority",
              "observation_date","same_date_crosscheck","reason"}
    require(type(out) is dict and set(out)==required,"MACRO_SCHEMA")
    require(out["schema"]=="XRAY_MACRO_CONTEXT_V1" and out["execution"]=="NONE"
            and out["real_money"]=="NO-GO" and out["alpha_authority"] is False
            and out["context_only"] is True,"MACRO_AUTHORITY")
    require(out["source_priority"]==["FRED_OPTIONAL","US_TREASURY_ZERO_KEY_FALLBACK"]
            and out["max_age_calendar_days"]==MAX_AGE_DAYS
            and out["crosscheck_tolerance_pct_points"]==CROSSCHECK_TOLERANCE_PCT_POINTS,"MACRO_POLICY")
    stamp=datetime.fromisoformat(out["generated_at_utc"])
    require(stamp.tzinfo is not None and at.tzinfo is not None
            and 0<=(at-stamp).total_seconds()<=900,"MACRO_GENERATION_AGE")
    today=stamp.astimezone(ZoneInfo("America/New_York")).date()
    def error_row(x):
        return (type(x) is dict and set(x)=={"status","reason"} and x["status"]=="UNKNOWN"
                and isinstance(x["reason"],str)
                and re.fullmatch(r"(?:HTTP_[1-5][0-9]{2}|PROVIDER_OR_PARSE_ERROR)",x["reason"]) is not None)
    series=out["series"]
    require(type(series) is dict and set(series)<={"DGS2","DGS10","DFEDTARU"},"MACRO_SERIES_IDS")
    for row in series.values():
        if error_row(row): continue
        require(type(row) is dict and set(row)=={"date","value"} and isinstance(row["value"],str),"MACRO_FRED_ROW")
        usable_day(row["date"],today)
        require(str(numeric(row["value"]))==row["value"],"MACRO_FRED_VALUE")
    t=out["treasury_zero_key"]
    if not error_row(t):
        require(type(t) is dict and set(t)=={"date","dgs2","dgs10","spread_2s10s_pct_points","source"}
                and t["source"]=="US_TREASURY_DAILY_PAR_YIELD_CURVE_XML","MACRO_TREASURY_ROW")
        usable_day(t["date"],today)
        require(type(t["dgs2"]) in (int,float) and type(t["dgs10"]) in (int,float)
                and type(t["spread_2s10s_pct_points"]) in (int,float)
                and round(numeric(t["dgs10"])-numeric(t["dgs2"]),4)==numeric(t["spread_2s10s_pct_points"]),"MACRO_TREASURY_SPREAD")
    expected=select_context(series,t,today)
    require(all(type(out[k]) is type(v) and out[k]==v for k,v in expected.items()),"MACRO_SELECTION_CONTRADICTION")
    return True

def selftest():
    # Explicit guards remain effective with python -O.
    def require(ok,label):
        if not ok: raise AssertionError(label)
    day=date(2026,11,24)
    valid={"DGS2":{"date":"2026-11-24","value":"4.00"},
           "DGS10":{"date":"2026-11-24","value":"4.20"}}
    errors={"DGS2":{"status":"UNKNOWN","reason":"HTTP_403"},
            "DGS10":{"status":"UNKNOWN","reason":"HTTP_429"}}
    t={"date":"2026-11-24","dgs2":4.0,"dgs10":4.2}
    unknown={"status":"UNKNOWN"}
    require(select_context(errors,unknown,day)["status"]=="UNKNOWN","ERROR_DICT_FALSE_READY")
    require(select_context(errors,t,day)["authority"]=="US_TREASURY_ZERO_KEY_FALLBACK","FALLBACK")
    require(select_context(valid,t,day)["same_date_crosscheck"] is True,"CROSSCHECK")
    require(select_context(valid,dict(t,dgs10=4.22),day)["status"]=="UNKNOWN","SOURCE_DISAGREEMENT")
    require(select_context(valid,dict(t,dgs10=4.21),day)["status"]=="READY","TOLERANCE_EDGE")
    require(select_context(valid,dict(t,date="2026-11-23"),day)["authority"]=="FRED_ONLY","OLDER_TREASURY")
    require(select_context(valid,dict(t,date="2026-11-25"),day)["same_date_crosscheck"] is False,"FUTURE_CROSSCHECK")
    mismatch=dict(valid,DGS10={"date":"2026-11-23","value":"4.20"})
    require(select_context(mismatch,unknown,day)["status"]=="UNKNOWN","MIXED_DATES")
    for when,expected in (("2026-11-17","READY"),("2026-11-16","UNKNOWN"),("2026-11-25","UNKNOWN")):
        require(select_context({},dict(t,date=when),day)["status"]==expected,"AGE_BOUND_"+when)
    for value in ("NaN","inf",True,None):
        require(select_context({},dict(t,dgs10=value),day)["status"]=="UNKNOWN","NONFINITE_OR_INVALID")
    require(select_context({},dict(t,dgs2=0),day)["status"]=="READY","ZERO_IS_NUMERIC")
    require(latest_fred({"observations":[{"date":"2026-11-24","value":"."},{"date":"2026-11-23","value":"4.0"}]},day)["date"]=="2026-11-23","FRED_MISSING_LATEST")
    for rows in ([{"date":"2026-11-25","value":"1"}],[{"date":"2026-11-16","value":"1"}],[{"date":"2026-11-24","value":"1"},{"date":"2026-11-24","value":"2"}]):
        try: latest_fred({"observations":rows},day)
        except ValueError: pass
        else: raise AssertionError("INVALID_FRED_ACCEPTED")
    require("SECRET" not in safe_error(RuntimeError("https://example.invalid?api_key=SECRET")),"ERROR_PRIVACY")
    from resilience_runtime import classify_exception, failure_message
    err=RuntimeError("https://example.invalid?api_key=SECRET")
    require(failure_message("FRED",err,classify_exception(err))=="FRED:PROVIDER_ERROR","LEDGER_ERROR_PRIVACY")
    import urllib.error
    err=urllib.error.HTTPError("https://example.invalid?api_key=SECRET",403,"SECRET",None,None)
    require(failure_message("FRED",err,classify_exception(err))=="FRED:HTTP_403","LEDGER_HTTP_PRIVACY")
    at=datetime(2026,11,24,21,0,tzinfo=timezone.utc)
    record={"schema":"XRAY_MACRO_CONTEXT_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
            "generated_at_utc":at.isoformat(),"series":{},
            "source_priority":["FRED_OPTIONAL","US_TREASURY_ZERO_KEY_FALLBACK"],"context_only":True,
            "max_age_calendar_days":MAX_AGE_DAYS,"crosscheck_tolerance_pct_points":CROSSCHECK_TOLERANCE_PCT_POINTS,
            "treasury_zero_key":dict(t,source="US_TREASURY_DAILY_PAR_YIELD_CURVE_XML",spread_2s10s_pct_points=0.2)}
    record.update(select_context(record["series"],record["treasury_zero_key"],day))
    require(validate_artifact(record,at),"VALID_PUBLICATION")
    for modified in (dict(record,alpha_authority=True),dict(record,status="UNKNOWN"),
                     dict(record,generated_at_utc="2026-11-24T20:44:59+00:00"),
                     dict(record,generated_at_utc="2026-11-24T21:00:01+00:00"),
                     dict(record,series={"DGS2":{"status":"UNKNOWN","reason":"SECRET"}}),
                     dict(record,treasury_zero_key=dict(record["treasury_zero_key"],spread_2s10s_pct_points=0.3))):
        try: validate_artifact(modified,at)
        except ValueError: pass
        else: raise AssertionError("INVALID_PUBLICATION_ACCEPTED")
    print("XRAY_MACRO_CONTEXT_SELFTEST=PASS_NO_FALSE_READY_FRESHNESS_CROSSCHECK_PRIVACY_PUBLICATION")

def main():
    ap=argparse.ArgumentParser()
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument("--selftest",action="store_true")
    mode.add_argument("--validate-file",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.validate_file is not None:
        validate_artifact(json.loads(args.validate_file.read_text()),datetime.now(timezone.utc))
        print("XRAY_MACRO_PUBLICATION_VALIDATED=NO_ALPHA")
        return
    today=datetime.now(ZoneInfo("America/New_York")).date()
    key=os.getenv("FRED_API_KEY","").strip()
    out={"schema":"XRAY_MACRO_CONTEXT_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "generated_at_utc":now(),"series":{},"source_priority":["FRED_OPTIONAL","US_TREASURY_ZERO_KEY_FALLBACK"],
         "context_only":True,"max_age_calendar_days":MAX_AGE_DAYS,
         "crosscheck_tolerance_pct_points":CROSSCHECK_TOLERANCE_PCT_POINTS}
    if key:
        for sid in ["DGS2","DGS10","DFEDTARU"]:
            q=urllib.parse.urlencode({"series_id":sid,"api_key":key,"file_type":"json","sort_order":"desc","limit":5})
            try:
                j=fetch_json("FRED",f"https://api.stlouisfed.org/fred/series/observations?{q}",{"Accept":"application/json"},cache_ttl=900)
                out["series"][sid]=latest_fred(j,today)
            except Exception as e:
                out["series"][sid]={"status":"UNKNOWN","reason":safe_error(e)}
    try:
        out["treasury_zero_key"]=treasury_fallback(today)
    except Exception as e:
        out["treasury_zero_key"]={"status":"UNKNOWN","reason":safe_error(e)}
    out.update(select_context(out["series"],out["treasury_zero_key"],today))
    validate_artifact(out,datetime.now(timezone.utc))
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"authority":out["authority"],"observation_date":out["observation_date"]},sort_keys=True))
if __name__=="__main__": main()
