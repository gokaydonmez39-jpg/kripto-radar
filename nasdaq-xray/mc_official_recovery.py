#!/usr/bin/env python3
"""XRAY 2026-09-29 zero-dollar official MC audit.

Input authority already proven for PRICE/DV20:
- Rallies exact20 summary at ASOF 2026-09-29.
Cross-check MC sources:
- Nasdaq official stock screener marketCap.
- SEC Company Facts shares outstanding x exact 2026-09-29 Rallies close.
- Existing Rallies + Longbridge conservative MC evidence.

This is ZERO-ALPHA AUDIT EVIDENCE ONLY until canonical policy explicitly accepts it.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
"""
from __future__ import annotations
import json, math, os, random, time, urllib.parse, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUMMARY=ROOT/"rallies_recovery_summary.json"
FALLBACK=ROOT/"mc_fallback_20260929.json"
STATE=ROOT/"mc_official_recovery_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-01.1"
ASOF="2026-09-29"
BATCH=int(os.getenv("XRAY_OFFICIAL_MC_BATCH","35"))
MAX_ATTEMPTS=int(os.getenv("XRAY_OFFICIAL_MC_MAX_ATTEMPTS","3"))
UA="NASDAQ-SWING-XRAY/1.0 research github.com/gokaydonmez39-jpg/kripto-radar"
NASDAQ_SCREENER="https://api.nasdaq.com/api/screener/stocks"
SEC_TICKERS="https://www.sec.gov/files/company_tickers_exchange.json"
PASS_FLOOR=2_100_000_000.0
FAIL_CEILING=2_000_000_000.0
MAX_REL_DIFF=0.10
MAX_FACT_AGE_DAYS=150
ALLOWED_FORMS={"10-K","10-Q","10-K/A","10-Q/A","20-F","20-F/A","40-F","40-F/A"}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def atomic(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except Exception:return None

def get_json(url,params=None,headers=None,timeout=45,retries=3):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    hdr={"User-Agent":UA,"Accept":"application/json,text/plain,*/*","Accept-Encoding":"identity"}
    if headers:hdr.update(headers)
    last=None
    for k in range(retries):
        try:
            req=urllib.request.Request(url,headers=hdr)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e
            time.sleep(0.8*(k+1)+random.uniform(0.1,0.4))
    raise last

def nasdaq_map():
    obj=get_json(
      NASDAQ_SCREENER,
      {"tableonly":"true","limit":"25","offset":"0","exchange":"NASDAQ","download":"true"},
      {"Origin":"https://www.nasdaq.com","Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
       "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"},
      timeout=60
    )
    data=obj.get("data") or {}
    rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
    if len(rows)<3000:
        raise RuntimeError("NASDAQ_SCREENER_TOO_FEW_ROWS")
    out={}
    for r in rows:
        s=str(r.get("symbol") or "").upper().strip()
        mc=finite(r.get("marketCap"))
        px=None
        try:px=finite(str(r.get("lastsale") or "").replace("$","").replace(",",""))
        except Exception:pass
        if s:
            out[s]={"market_cap":mc,"lastsale":px,"name":r.get("name")}
    return out,len(rows)

def sec_map():
    obj=get_json(SEC_TICKERS,timeout=45)
    fields=obj.get("fields") or []
    rows=obj.get("data") or []
    idx={n:i for i,n in enumerate(fields)}
    by_ticker={}
    by_cik={}
    for r in rows:
        try:
            ticker=str(r[idx["ticker"]]).upper().strip()
            exch=str(r[idx["exchange"]]).strip()
            cik=int(r[idx["cik"]])
            name=str(r[idx["name"]])
        except Exception:
            continue
        if exch.lower()!="nasdaq":continue
        by_ticker[ticker]={"cik":cik,"name":name,"exchange":exch}
        by_cik.setdefault(cik,[]).append(ticker)
    return by_ticker,{k:sorted(set(v)) for k,v in by_cik.items()}

def latest_dei_shares(facts,asof):
    concept=(((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding"))
    if not concept:return None,"DEI_SHARES_CONCEPT_MISSING"
    vals=((concept.get("units") or {}).get("shares") or [])
    cand=[]
    for x in vals:
        filed=str(x.get("filed") or "")
        end=str(x.get("end") or "")
        form=str(x.get("form") or "")
        val=finite(x.get("val"))
        if not filed or not end or val is None:continue
        if filed>asof or end>asof or form not in ALLOWED_FORMS:continue
        try:age=(date.fromisoformat(asof)-date.fromisoformat(end)).days
        except Exception:continue
        if age<0 or age>MAX_FACT_AGE_DAYS:continue
        cand.append((filed,end,val,form,age,x.get("accn")))
    if not cand:return None,"NO_FRESH_DEI_SHARES"
    cand.sort(key=lambda z:(z[0],z[1]))
    filed,end,val,form,age,accn=cand[-1]
    return {"shares":val,"filed":filed,"end":end,"form":form,"age_days":age,"accn":accn},None

def latest_usgaap_shares(facts,asof):
    concept=(((facts.get("facts") or {}).get("us-gaap") or {}).get("CommonStockSharesOutstanding"))
    if not concept:return None
    vals=((concept.get("units") or {}).get("shares") or [])
    cand=[]
    for x in vals:
        filed=str(x.get("filed") or "")
        end=str(x.get("end") or "")
        val=finite(x.get("val"))
        if not filed or not end or val is None or filed>asof or end>asof:continue
        try:age=(date.fromisoformat(asof)-date.fromisoformat(end)).days
        except Exception:continue
        if age<0 or age>MAX_FACT_AGE_DAYS:continue
        cand.append((filed,end,val,age,x.get("form"),x.get("accn")))
    if not cand:return None
    cand.sort(key=lambda z:(z[0],z[1]))
    filed,end,val,age,form,accn=cand[-1]
    return {"shares":val,"filed":filed,"end":end,"age_days":age,"form":form,"accn":accn}

def classify(sym,price,fb,nq,sec_ticker,sec_ciks):
    if not nq or finite(nq.get("market_cap")) is None:
        return "UNKNOWN_STATIC",{"reason":"NASDAQ_MC_MISSING"}
    if not sec_ticker:
        return "UNKNOWN_STATIC",{"reason":"SEC_TICKER_CIK_MISSING"}
    cik=sec_ticker["cik"]
    cik_tickers=sec_ciks.get(cik) or []
    if len(cik_tickers)!=1:
        return "UNKNOWN_STATIC",{"reason":"MULTI_TICKER_CIK","cik":cik,"tickers":cik_tickers}
    try:
        facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",timeout=35,retries=2)
    except Exception as e:
        return "UNKNOWN_RETRY",{"reason":type(e).__name__+":"+str(e)[:140]}
    dei,err=latest_dei_shares(facts,ASOF)
    if err:
        return "UNKNOWN_STATIC",{"reason":err,"cik":cik}
    sec_mc=price*dei["shares"]
    nq_mc=float(nq["market_cap"])
    r_mc=finite((fb or {}).get("rallies_market_cap"))
    l_mc=finite((fb or {}).get("longbridge_market_cap"))
    usg=latest_usgaap_shares(facts,ASOF)
    sec_vs_nq=abs(sec_mc-nq_mc)/max(sec_mc,nq_mc)
    detail={
      "cik":cik,"price_20260929":price,"dei":dei,"usgaap":usg,
      "sec_derived_market_cap":sec_mc,"nasdaq_market_cap":nq_mc,
      "rallies_market_cap":r_mc,"longbridge_market_cap":l_mc,
      "sec_vs_nasdaq_rel_diff":sec_vs_nq,
    }
    # SEC explicitly warns share tags can be wrong; if both tags exist, demand internal agreement.
    if usg is not None:
        share_rel=abs(dei["shares"]-usg["shares"])/max(dei["shares"],usg["shares"])
        detail["dei_vs_usgaap_shares_rel_diff"]=share_rel
        if share_rel>0.05:
            return "UNKNOWN_CONFLICT",dict(detail,reason="SEC_SHARE_TAG_CONFLICT_GT_5PCT")
    # Require all four market-cap views when Rallies/Longbridge evidence exists.
    vals=[sec_mc,nq_mc]
    if r_mc is not None:vals.append(r_mc)
    if l_mc is not None:vals.append(l_mc)
    if r_mc is None or l_mc is None:
        return "UNKNOWN_STATIC",dict(detail,reason="RALLIES_OR_LONGBRIDGE_MC_MISSING")
    maxrel=(max(vals)-min(vals))/max(vals)
    detail["four_source_max_relative_spread"]=maxrel
    if maxrel>MAX_REL_DIFF:
        return "UNKNOWN_CONFLICT",dict(detail,reason="FOUR_SOURCE_MC_SPREAD_GT_10PCT")
    if all(v>=PASS_FLOOR for v in vals):
        return "PASS_OFFICIAL_CONSERVATIVE_CANDIDATE",detail
    if all(v<FAIL_CEILING for v in vals):
        return "FAIL_MC",detail
    return "UNKNOWN_BORDERLINE",dict(detail,reason="MC_2_0_TO_2_1B_OR_MIXED")

def status_counts(results):
    o={}
    for v in results.values():o[v["status"]]=o.get(v["status"],0)+1
    return dict(sorted(o.items()))

def main():
    summary=load(SUMMARY); fbroot=load(FALLBACK)
    if summary.get("asof_et")!=ASOF or len(summary.get("pass_symbols") or [])!=498:
        raise RuntimeError("RALLIES_SUMMARY_PREIMAGE_MISMATCH")
    pass_syms=summary["pass_symbols"]
    metrics=summary.get("pass_metrics") or {}
    fb=fbroot.get("results") or {}
    nq,nq_rows=nasdaq_map()
    st,sc=sec_map()

    state={}
    if STATE.exists():
        try:state=load(STATE)
        except Exception:state={}
    if state.get("schema")!="XRAY_OFFICIAL_MC_AUDIT_V1" or state.get("asof_et")!=ASOF:
        state={"schema":"XRAY_OFFICIAL_MC_AUDIT_V1","build":BUILD,"task_id":TASK_ID,
               "asof_et":ASOF,"execution":"NONE","real_money":"NO-GO",
               "unknown_never_pass":True,"canonical_authority":"ZERO_UNTIL_POLICY_ACCEPTANCE",
               "input_count":len(pass_syms),"results":{},"status":"MC_AUDIT_PARTIAL"}
    results=state.setdefault("results",{})
    retry=[s for s,v in sorted(results.items())
           if v.get("status")=="UNKNOWN_RETRY" and int(v.get("attempts",0))<MAX_ATTEMPTS][:10]
    new=[s for s in pass_syms if s not in results][:BATCH]
    work=[];seen=set()
    for s in retry+new:
        if s not in seen:seen.add(s);work.append(s)
    for sym in work:
        price=finite((metrics.get(sym) or {}).get("price"))
        if price is None:
            stt,info="UNKNOWN_STATIC",{"reason":"ASOF_PRICE_MISSING"}
        else:
            stt,info=classify(sym,price,fb.get(sym),nq.get(sym),st.get(sym),sc)
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if stt=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            stt="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={"status":stt,"info":info,"attempts":attempts,
                      "updated_at_utc":datetime.now(timezone.utc).isoformat()}
        time.sleep(0.14)
    pending_new=sum(1 for s in pass_syms if s not in results)
    pending_retry=sum(1 for s,v in results.items()
                      if v.get("status")=="UNKNOWN_RETRY" and int(v.get("attempts",0))<MAX_ATTEMPTS)
    state.update({
      "build":BUILD,"nasdaq_rows":nq_rows,"processed_new_this_run":len(new),
      "processed_retry_this_run":len(retry),"pending_new":pending_new,
      "pending_retry":pending_retry,"counts":status_counts(results),
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":"MC_AUDIT_COMPLETE" if pending_new==0 and pending_retry==0 else "MC_AUDIT_PARTIAL"
    })
    atomic(STATE,state)
    print(json.dumps({"status":state["status"],"counts":state["counts"],
      "processed_new":len(new),"processed_retry":len(retry),
      "pending_new":pending_new,"pending_retry":pending_retry},sort_keys=True))

if __name__=="__main__":
    main()
