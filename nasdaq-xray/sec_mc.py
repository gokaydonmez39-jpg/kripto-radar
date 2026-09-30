#!/usr/bin/env python3
"""XRAY SEC market-cap cross-check stage.
Official SEC facts only. Never G9. EXECUTION=NONE. REAL_MONEY=NO-GO.
Uses candidate prices from upstream state; ambiguous shares outstanding => UNKNOWN.
"""
from __future__ import annotations
import csv, io, json, math, os, time, urllib.request
from datetime import datetime, timezone, date
from pathlib import Path

ROOT=Path(__file__).resolve().parent
IN=ROOT/"market_candidates.json"
OUT=ROOT/"sec_mc_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"
UA=os.getenv("SEC_USER_AGENT","NASDAQ-SWING-XRAY research contact xray@example.invalid")
TICKERS_URL="https://www.sec.gov/files/company_tickers_exchange.json"

def get_json(url,timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Encoding":"gzip, deflate","Host":urllib.parse.urlparse(url).netloc})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

# urllib.parse is used in get_json Host resolution.
import urllib.parse

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except Exception:return None

def latest_shares(facts,asof):
    usgaap=((facts.get("facts") or {}).get("dei") or {})
    concept=usgaap.get("EntityCommonStockSharesOutstanding")
    if not concept:
        # Some issuers expose it under us-gaap instead.
        concept=((facts.get("facts") or {}).get("us-gaap") or {}).get("CommonStocksIncludingAdditionalPaidInCapital")
        return None,"SHARES_CONCEPT_MISSING"
    units=concept.get("units") or {}
    vals=units.get("shares") or []
    eligible=[]
    for x in vals:
        end=str(x.get("end") or "")
        filed=str(x.get("filed") or "")
        val=finite(x.get("val"))
        if val is None or not end or end>asof: continue
        eligible.append((end,filed,val,x.get("form")))
    if not eligible:return None,"SHARES_FACT_MISSING"
    eligible.sort(key=lambda z:(z[0],z[1]))
    end,filed,val,form=eligible[-1]
    return {"shares":val,"end":end,"filed":filed,"form":form},None

def main():
    if not IN.exists():
        raise RuntimeError("MARKET_CANDIDATES_MISSING")
    src=json.loads(IN.read_text())
    candidates=src.get("candidates") or {}
    asof=src.get("asof_et")
    if not asof: raise RuntimeError("ASOF_MISSING")

    tick=get_json(TICKERS_URL)
    fields=tick.get("fields") or []
    rows=tick.get("data") or []
    idx={n:i for i,n in enumerate(fields)}
    mp={}
    for r in rows:
        try:
            ticker=str(r[idx["ticker"]]).upper()
            exch=str(r[idx["exchange"]])
            cik=int(r[idx["cik"]])
            if exch=="Nasdaq":
                mp[ticker]=cik
        except Exception:continue

    out={"schema":"XRAY_SEC_MC_V1","task_id":TASK_ID,"execution":"NONE","real_money":"NO-GO",
         "asof_et":asof,"updated_at_utc":datetime.now(timezone.utc).isoformat(),
         "source":"SEC_COMPANYFACTS_OFFICIAL_CROSSCHECK","pass":{},"unknown":{},"fail":{},
         "threshold":2000000000,"conservative_pass_floor":2100000000}

    for i,(sym,info) in enumerate(sorted(candidates.items())):
        px=finite((info or {}).get("price"))
        if px is None:
            out["unknown"][sym]="PRICE_MISSING"; continue
        cik=mp.get(sym)
        if cik is None:
            out["unknown"][sym]="SEC_NASDAQ_CIK_MISSING"; continue
        try:
            facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
            sh,err=latest_shares(facts,asof)
            if err:
                out["unknown"][sym]=err; continue
            mc=px*sh["shares"]
            rec={"price":px,"shares":sh["shares"],"shares_end":sh["end"],"filed":sh["filed"],"form":sh["form"],"market_cap_est":mc}
            if mc>=2100000000: out["pass"][sym]=rec
            elif mc<2000000000: out["fail"][sym]=rec
            else: out["unknown"][sym]="MC_BORDERLINE_2_0_TO_2_1B"
        except Exception as e:
            out["unknown"][sym]=f"{type(e).__name__}:{str(e)[:100]}"
        time.sleep(0.12)  # < 10 req/s SEC fair-access envelope

    out["pass_count"]=len(out["pass"]); out["fail_count"]=len(out["fail"]); out["unknown_count"]=len(out["unknown"])
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"pass":out["pass_count"],"fail":out["fail_count"],"unknown":out["unknown_count"]},sort_keys=True))

if __name__=="__main__":
    main()
