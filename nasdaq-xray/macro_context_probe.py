#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from resilience_runtime import fetch_json, fetch_text

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_macro_context.json"

def now(): return datetime.now(timezone.utc).isoformat()

def local(tag): return tag.rsplit("}",1)[-1]

def treasury_fallback():
    year=datetime.now(timezone.utc).year
    url=f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    xml=fetch_text("US_TREASURY_YIELD_CURVE",url,{
        "Accept":"application/xml,text/xml;q=0.9,*/*;q=0.8",
        "User-Agent":"NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar",
    },cache_ttl=900)
    root=ET.fromstring(xml)
    rows=[]
    for entry in root.iter():
        if local(entry.tag)!="entry": continue
        vals={}
        for el in entry.iter():
            name=local(el.tag)
            txt=(el.text or "").strip()
            if txt: vals[name]=txt
        dt=vals.get("NEW_DATE") or vals.get("Date") or vals.get("date")
        y2=vals.get("BC_2YEAR") or vals.get("BC_2_YEAR")
        y10=vals.get("BC_10YEAR") or vals.get("BC_10_YEAR")
        if dt and y2 and y10:
            try: rows.append({"date":dt,"dgs2":float(y2),"dgs10":float(y10)})
            except Exception: pass
    if not rows: raise RuntimeError("TREASURY_XML_NO_2Y_10Y_ROWS")
    rows.sort(key=lambda x:x["date"])
    x=rows[-1]
    x["spread_2s10s_pct_points"]=round(x["dgs10"]-x["dgs2"],4)
    x["source"]="US_TREASURY_DAILY_PAR_YIELD_CURVE_XML"
    return x

def main():
    key=os.getenv("FRED_API_KEY","").strip()
    out={"schema":"XRAY_MACRO_CONTEXT_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,"generated_at_utc":now(),"series":{},"source_priority":["FRED_OPTIONAL","US_TREASURY_ZERO_KEY_FALLBACK"]}
    fred_ok=False
    if key:
        for sid in ["DGS2","DGS10","DFEDTARU"]:
            q=urllib.parse.urlencode({"series_id":sid,"api_key":key,"file_type":"json","sort_order":"desc","limit":5})
            try:
                j=fetch_json("FRED",f"https://api.stlouisfed.org/fred/series/observations?{q}",{"Accept":"application/json"},cache_ttl=900)
                obs=[x for x in (j.get("observations") or []) if x.get("value") not in {None,"."}]
                out["series"][sid]=obs[0] if obs else None
            except Exception as e:
                out["series"][sid]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:160]}"}
        fred_ok=bool(out["series"].get("DGS2")) and bool(out["series"].get("DGS10"))
    try:
        out["treasury_zero_key"]=treasury_fallback()
        treasury_ok=True
    except Exception as e:
        out["treasury_zero_key"]={"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"}
        treasury_ok=False
    if fred_ok:
        out["status"]="READY"
        out["authority"]="FRED_WITH_TREASURY_CROSSCHECK" if treasury_ok else "FRED_ONLY"
    elif treasury_ok:
        out["status"]="READY"
        out["authority"]="US_TREASURY_ZERO_KEY_FALLBACK"
        out["reason"]="FRED_API_KEY_MISSING_OR_UNAVAILABLE"
    else:
        out["status"]="UNKNOWN"
        out["authority"]="NO_MACRO_WITNESS"
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"authority":out["authority"]},sort_keys=True))
if __name__=="__main__": main()
