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
    mp=sec_map()

    direct_pass={}; borderline={}; unresolved={}; sec_fail={}
    # Conservative direct pass: official Nasdaq MC >= 2.6B.
    for sym,info in sorted(cands.items()):
        nmc=finite((disc.get(sym) or {}).get("screener_market_cap"))
        if nmc is None:
            unresolved[sym]={"reason":"NASDAQ_MC_MISSING"}; continue
        if nmc>=2_600_000_000:
            direct_pass[sym]={"nasdaq_market_cap":nmc,"mode":"NASDAQ_CONSERVATIVE_GE_2_6B"}
        else:
            borderline[sym]={"nasdaq_market_cap":nmc,"price":finite(info.get("price"))}

    sec_pass={}
    for sym,rec in sorted(borderline.items()):
        cik=mp.get(sym)
        if cik is None:
            unresolved[sym]={"reason":"SEC_CIK_MISSING","nasdaq_market_cap":rec["nasdaq_market_cap"]};continue
        if rec["price"] is None:
            unresolved[sym]={"reason":"PRICE_MISSING"};continue
        try:
            sh=latest_shares(cik,asof)
            if sh is None:
                unresolved[sym]={"reason":"SEC_SHARES_FACT_MISSING","cik":cik,"nasdaq_market_cap":rec["nasdaq_market_cap"]};continue
            sec_mc=rec["price"]*sh["shares"]
            nmc=rec["nasdaq_market_cap"]
            rel=abs(sec_mc-nmc)/max(sec_mc,nmc)
            evidence={"cik":cik,"price":rec["price"],"shares":sh["shares"],"shares_end":sh["end"],"shares_filed":sh["filed"],"shares_form":sh["form"],"sec_market_cap":sec_mc,"nasdaq_market_cap":nmc,"relative_diff":rel}
            if sec_mc>=2_100_000_000 and nmc>=2_100_000_000 and rel<=0.10:
                sec_pass[sym]=evidence
            elif sec_mc<2_000_000_000 and nmc<2_000_000_000:
                sec_fail[sym]=evidence
            else:
                unresolved[sym]={"reason":"SEC_NASDAQ_MC_NOT_CONCORDANT","evidence":evidence}
        except Exception as e:
            unresolved[sym]={"reason":f"SEC_ERROR:{type(e).__name__}:{str(e)[:140]}"}
        time.sleep(0.25)

    out={
      "schema":"XRAY_MC_ZERO_KEY_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "direct_nasdaq_conservative_pass_count":len(direct_pass),
      "sec_crosscheck_pass_count":len(sec_pass),
      "sec_definitive_fail_count":len(sec_fail),
      "unresolved_count":len(unresolved),
      "direct_nasdaq_conservative_pass":direct_pass,
      "sec_crosscheck_pass":sec_pass,
      "sec_definitive_fail":sec_fail,
      "unresolved":unresolved,
      "current_core_zero_key":sorted(set(direct_pass)|set(sec_pass)),
      "policy_note":"This zero-key path is deliberately stricter than the canonical $2B threshold. Borderline disagreements stay UNKNOWN."
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:out[k] for k in ["direct_nasdaq_conservative_pass_count","sec_crosscheck_pass_count","sec_definitive_fail_count","unresolved_count"]},sort_keys=True))

if __name__=="__main__":
    main()
