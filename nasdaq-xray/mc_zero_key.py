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
OVERLAY=ROOT/"mc_resolution_overlay.json"
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

def load_overlay(asof):
    meta={"status":"ABSENT"}
    if not OVERLAY.exists():
        return {},meta
    try:
        obj=json.loads(OVERLAY.read_text(encoding="utf-8"))
        if obj.get("schema")!="XRAY_MC_RESOLUTION_OVERLAY_V1":
            raise ValueError("SCHEMA")
        if obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY")
        if obj.get("base_asof_et")!=asof:
            raise ValueError("ASOF_MISMATCH")
        ts=datetime.fromisoformat(str(obj.get("generated_at_utc")).replace("Z","+00:00"))
        if ts.tzinfo is None:
            raise ValueError("TIMESTAMP_TZ")
        age_h=(datetime.now(timezone.utc)-ts.astimezone(timezone.utc)).total_seconds()/3600.0
        max_age=float(obj.get("max_age_hours",24))
        if age_h < -0.25 or age_h > max_age:
            return {},{"status":"STALE","age_hours":age_h,"max_age_hours":max_age}
        res=obj.get("resolutions") or {}
        if not isinstance(res,dict):
            raise ValueError("RESOLUTIONS")
        return res,{"status":"PASS","age_hours":age_h,"generated_at_utc":obj.get("generated_at_utc")}
    except Exception as e:
        return {},{"status":"INVALID","reason":f"{type(e).__name__}:{str(e)[:120]}"}

def main():
    ss=json.loads(SINA_STATE.read_text())
    cc=json.loads(CAND.read_text())
    asof=cc["asof_et"]
    cands=cc.get("candidates") or {}
    disc=ss.get("discovery") or {}
    overlay,overlay_meta=load_overlay(asof)

    direct_pass={}; unresolved={}; definitive_fail={}
    fallback_watch_symbols=[]
    for sym,info in sorted(cands.items()):
        ov=overlay.get(sym)
        if ov:
            mode=ov.get("mode")
            decision=ov.get("decision")
            if mode=="BIGDATA_PRIMARY":
                mc=finite(ov.get("market_cap_usd"))
                listing=ov.get("listing")
                expected="PASS" if mc is not None and mc>=2_000_000_000 else "FAIL"
                if mc is None or listing!=f"XNAS:{sym}" or decision!=expected:
                    unresolved[sym]={"reason":"MC_OVERLAY_PRIMARY_INVALID"}
                    continue
                if decision=="PASS":
                    direct_pass[sym]={
                      "market_cap":mc,
                      "mode":"BIGDATA_PRIMARY_EXACT_XNAS",
                      "bigdata_entity_id":ov.get("bigdata_entity_id"),
                    }
                else:
                    definitive_fail[sym]={
                      "market_cap":mc,
                      "mode":"BIGDATA_PRIMARY_EXACT_XNAS_LT_2B",
                      "bigdata_entity_id":ov.get("bigdata_entity_id"),
                    }
                continue
            if mode=="RALLIES_LONGBRIDGE_FALLBACK":
                rmc=finite(ov.get("rallies_market_cap_usd"))
                lmc=finite(ov.get("longbridge_market_cap_usd"))
                rel=finite(ov.get("relative_diff"))
                ok=(
                  decision=="PASS"
                  and ov.get("rallies_exchange")=="XNAS"
                  and ov.get("longbridge_exchange")=="NASD"
                  and rmc is not None and lmc is not None
                  and rmc>=2_100_000_000 and lmc>=2_100_000_000
                  and rel is not None and rel<=0.10
                  and ov.get("state_cap")=="WATCH"
                  and ov.get("r92_eligible") is False
                )
                if not ok:
                    unresolved[sym]={"reason":"MC_OVERLAY_FALLBACK_INVALID"}
                    continue
                direct_pass[sym]={
                  "market_cap_conservative_max":max(rmc,lmc),
                  "rallies_market_cap":rmc,
                  "longbridge_market_cap":lmc,
                  "relative_diff":rel,
                  "mode":"RALLIES_XNAS_LONGBRIDGE_NASD_FALLBACK",
                  "state_cap":"WATCH",
                  "r92_eligible":False,
                }
                fallback_watch_symbols.append(sym)
                continue
            unresolved[sym]={"reason":"MC_OVERLAY_MODE_UNKNOWN"}
            continue

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
      "fallback_watch_symbols":sorted(fallback_watch_symbols),
      "overlay_meta":overlay_meta,
      "policy_note":"Primary Bigdata exact XNAS COMPANY/PUBLIC finite USD market cap overrides discovery MC. Rallies XNAS + Longbridge NASD fallback requires both >=2.10B and <=10% relative difference and is capped WATCH/R92-ineligible. Freshness failure is fail-closed. Nasdaq official screener >=2.6B remains conservative PASS when no fresh overlay resolution exists; 2.0-2.6B remains UNKNOWN."
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:out[k] for k in ["direct_nasdaq_conservative_pass_count","definitive_fail_count","unresolved_count"]},sort_keys=True))

if __name__=="__main__":
    main()
