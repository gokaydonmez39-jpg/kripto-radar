#!/usr/bin/env python3
"""XRAY zero-key borderline market-cap resolver.
Sources:
- Nasdaq official screener market cap (discovery/current threshold anchor)
- SEC companyfacts DEI EntityCommonStockSharesOutstanding (official shares cross-check)
- Sina as-of close from existing PRICE/DV20/HISTORY candidate state
Research only. EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
SINA_STATE=ROOT/"sina_state.json"
CAND=ROOT/"sina_candidates.json"
OUT=ROOT/"mc_zero_key_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"
SEC_TICKERS="https://www.sec.gov/files/company_tickers_exchange.json"
SEC_UA="NASDAQ-SWING-XRAY research bot (contact: https://github.com/gokaydonmez39-jpg/kripto-radar)"

def get_json(url,timeout=30):
    req=urllib.request.Request(url,headers={
      "User-Agent":SEC_UA,
      "Accept-Encoding":"gzip, deflate",
      "Accept":"application/json",
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        enc=(r.headers.get("Content-Encoding") or "").lower()
        if enc=="gzip":
            import gzip; raw=gzip.decompress(raw)
        elif enc=="deflate":
            import zlib; raw=zlib.decompress(raw)
        return json.loads(raw.decode("utf-8"))

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except Exception:return None

def sec_map():
    obj=get_json(SEC_TICKERS)
    fields=obj.get("fields") or []
    idx={k:i for i,k in enumerate(fields)}
    out={}
    for row in obj.get("data") or []:
        try:
            t=str(row[idx["ticker"]]).upper().strip()
            ex=str(row[idx["exchange"]])
            cik=int(row[idx["cik"]])
            if t and ex=="Nasdaq": out[t]=cik
        except Exception: pass
    return out

def latest_shares(cik,asof):
    facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    concept=(((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {})
    vals=((concept.get("units") or {}).get("shares") or [])
    eligible=[]
    for x in vals:
        end=str(x.get("end") or "")[:10]
        filed=str(x.get("filed") or "")[:10]
        val=finite(x.get("val"))
        form=str(x.get("form") or "")
        if val is None or not end or not filed: continue
        if end>asof or filed>asof: continue
        if form not in {"10-K","10-Q","20-F","40-F","10-K/A","10-Q/A","20-F/A","40-F/A"}: continue
        eligible.append((end,filed,val,form))
    if not eligible:return None
    eligible.sort(key=lambda z:(z[0],z[1]))
    end,filed,val,form=eligible[-1]
    return {"shares":val,"end":end,"filed":filed,"form":form}

def main():
    ss=json.loads(SINA_STATE.read_text())
    cc=json.loads(CAND.read_text())
    asof=cc["asof_et"]
    cands=cc.get("candidates") or {}
    disc=ss.get("discovery") or {}

    direct_pass={}; unresolved={}; definitive_fail={}
    for sym,info in sorted(cands.items()):
        nmc=finite((disc.get(sym) or {}).get("screener_market_cap"))
        if nmc is None:
            unresolved[sym]={"reason":"NASDAQ_MC_MISSING"}
            continue
        if nmc>=2_600_000_000:
            direct_pass[sym]={
              "nasdaq_market_cap":nmc,
              "mode":"NASDAQ_OFFICIAL_CONSERVATIVE_GE_2_6B"
            }
        elif nmc<2_000_000_000:
            definitive_fail[sym]={
              "nasdaq_market_cap":nmc,
              "mode":"NASDAQ_OFFICIAL_LT_2B"
            }
        else:
            unresolved[sym]={
              "reason":"NASDAQ_MC_BORDERLINE_2_0_TO_2_6B",
              "nasdaq_market_cap":nmc,
              "required_resolution":"CANONICAL_BIGDATA_OR_CONSERVATIVE_RALLIES_LONGBRIDGE"
            }

    out={
      "schema":"XRAY_MC_ZERO_KEY_V2","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "direct_nasdaq_conservative_pass_count":len(direct_pass),
      "definitive_fail_count":len(definitive_fail),
      "unresolved_count":len(unresolved),
      "direct_nasdaq_conservative_pass":direct_pass,
      "definitive_fail":definitive_fail,
      "unresolved":unresolved,
      "current_core_zero_key":sorted(direct_pass),
      "policy_note":"GitHub shared runner receives SEC HTTP 403. No bypass/retry storm. Nasdaq official screener >=2.6B is conservative PASS; 2.0-2.6B remains UNKNOWN until canonical resolver."
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:out[k] for k in ["direct_nasdaq_conservative_pass_count","definitive_fail_count","unresolved_count"]},sort_keys=True))

if __name__=="__main__":
    main()
