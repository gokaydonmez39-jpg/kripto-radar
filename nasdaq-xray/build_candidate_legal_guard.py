#!/usr/bin/env python3
"""Build the C4.17 finalist-local detailed legal guard from official SEC EDGAR.

This is a zero-alpha evidence gate. It never creates a trading signal, never
changes thresholds, and never treats a provider/network failure as PASS.

Review scope is deterministic: for each current candidate-scope symbol, inspect
the latest periodic filing available on/before ASOF (10-K/10-Q/20-F/40-F) and
all SEC filings from that filing date through ASOF. Explicit high-severity
bankruptcy/default/delisting/non-reliance items remain UNKNOWN pending review.
Financing/offering, merger/control and split/ADR evidence is recorded as risk
flags but is not silently converted into a hard alpha rule.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DEEP=Path(os.getenv("XRAY_LEGAL_GUARD_DEEP",str(ROOT/"canonical_current_deep_full.json")))
FAMILY_C=Path(os.getenv("XRAY_LEGAL_GUARD_FAMILY_C",str(ROOT/"canonical_current_family_c.json")))
LIFECYCLE=Path(os.getenv("XRAY_LEGAL_GUARD_LIFECYCLE",str(ROOT/"canonical_candidate_lifecycle_registry.json")))
OUT=Path(os.getenv("XRAY_LEGAL_GUARD_OUT",str(ROOT/"canonical_candidate_legal_guard.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
USER_AGENT=os.getenv("XRAY_SEC_USER_AGENT","XRAY research compliance contact: xray-noreply@example.invalid")
PERIODIC={"10-K","10-Q","20-F","40-F"}
OFFERING_PREFIX=("S-3","F-3","424B")
REVIEW_FORMS={"8-K","6-K","10-K","10-Q","20-F","40-F"}
HARD_ITEMS={"1.03":"BANKRUPTCY_OR_RECEIVERSHIP",
            "2.04":"TRIGGERING_EVENT_DIRECT_FINANCIAL_OBLIGATION",
            "3.01":"DELISTING_OR_LISTING_RULE_NOTICE",
            "4.02":"NON_RELIANCE_ON_PREVIOUS_FINANCIALS"}
RISK_ITEMS={"1.01":"MATERIAL_DEFINITIVE_AGREEMENT",
            "2.01":"ACQUISITION_OR_DISPOSITION",
            "3.02":"UNREGISTERED_SALE_OF_EQUITY",
            "5.01":"CHANGE_IN_CONTROL"}
HARD_PHRASES={
    "SUBSTANTIAL_DOUBT_GOING_CONCERN":"substantial doubt about our ability to continue as a going concern",
    "FILED_CHAPTER_11":"filed a voluntary petition under chapter 11",
}
RISK_PHRASES={
    "GOING_CONCERN_REFERENCE":"going concern",
    "BANKRUPTCY_REFERENCE":"bankruptcy",
    "EVENT_OF_DEFAULT_REFERENCE":"event of default",
    "DELISTING_REFERENCE":"delisting",
    "ATM_OR_AT_THE_MARKET":"at-the-market",
    "SECONDARY_OFFERING":"secondary offering",
    "CONVERTIBLE_SECURITY":"convertible",
    "MERGER_AGREEMENT":"merger agreement",
    "REVERSE_SPLIT":"reverse stock split",
    "STOCK_SPLIT":"stock split",
    "ADR_OR_ADS":"american depositary",
}


def blob_sha(path:Path)->str|None:
    if not path.exists(): return None
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()


def scope_hash(symbols:list[str])->str:
    return hashlib.sha256(("\n".join(symbols)+"\n").encode()).hexdigest()


def _fetch(url:str,limit:int=15_000_000,retries:int=3)->bytes:
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={
                "User-Agent":USER_AGENT,
                "Accept-Encoding":"identity",
                "Accept":"application/json,text/html,*/*",
            })
            with urllib.request.urlopen(req,timeout=20) as r:
                data=r.read(limit+1)
                if len(data)>limit: raise RuntimeError("SEC_RESPONSE_TOO_LARGE")
                return data
        except Exception as exc:
            last=exc
            if attempt+1<retries: time.sleep(0.7*(attempt+1))
    raise RuntimeError(f"SEC_FETCH_FAILED:{type(last).__name__}:{str(last)[:160]}")


def _fetch_json(url:str)->dict:
    x=json.loads(_fetch(url).decode("utf-8","replace"))
    if not isinstance(x,dict): raise RuntimeError("SEC_JSON_NOT_OBJECT")
    return x


def _clean_html(raw:bytes)->str:
    s=raw.decode("utf-8","replace")
    s=re.sub(r"(?is)<script.*?</script>|<style.*?</style>"," ",s)
    s=re.sub(r"(?s)<[^>]+>"," ",s)
    s=html.unescape(s)
    return re.sub(r"\s+"," ",s).lower()


def candidate_scope(deep:dict,fc:dict|None,lifecycle:dict|None)->list[str]:
    syms=set()
    for sym,row in (deep.get("results") or {}).items():
        if not isinstance(row,dict): continue
        if ((row.get("A") or {}).get("pool")
            or (row.get("B") or {}).get("breakout_confirmed")
            or (row.get("D") or {}).get("dk3_pre_r1")):
            syms.add(str(sym))
    for sym,g in ((fc or {}).get("confirmed") or {}).items():
        if isinstance(g,dict) and g.get("confirmed"): syms.add(str(sym))
    for rec in ((lifecycle or {}).get("records") or {}).values():
        if isinstance(rec,dict) and rec.get("symbol"): syms.add(str(rec["symbol"]))
    return sorted(syms)


def _ticker_cik_map()->dict[str,str]:
    j=_fetch_json("https://www.sec.gov/files/company_tickers.json")
    out={}
    for row in j.values():
        if not isinstance(row,dict): continue
        t=str(row.get("ticker") or "").upper()
        cik=row.get("cik_str")
        if t and cik is not None: out[t]=str(int(cik)).zfill(10)
    return out


def _recent_filings(sub:dict)->list[dict]:
    r=((sub.get("filings") or {}).get("recent") or {})
    keys=("accessionNumber","filingDate","reportDate","form","items","primaryDocument","primaryDocDescription")
    n=max((len(r.get(k) or []) for k in keys),default=0)
    out=[]
    for i in range(n):
        row={}
        for k in keys:
            a=r.get(k) or []
            row[k]=a[i] if i<len(a) else ""
        if row.get("accessionNumber") and row.get("filingDate") and row.get("form"):
            out.append(row)
    return out


def _doc_url(cik10:str,row:dict)->str|None:
    acc=str(row.get("accessionNumber") or "")
    doc=str(row.get("primaryDocument") or "")
    if not acc or not doc:return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc.replace('-','')}/{doc}"


def _item_set(items)->set[str]:
    if isinstance(items,list): raw=",".join(str(x) for x in items)
    else: raw=str(items or "")
    return set(re.findall(r"\b\d+\.\d+\b",raw))


def _phrase_flags(text:str,phrases:dict)->list[str]:
    out=[]
    for flag,p in phrases.items():
        if isinstance(p,tuple):
            if all(x in text for x in p): out.append(flag)
        elif p in text: out.append(flag)
    return out


def review_symbol(symbol:str,cik10:str,asof:str)->dict:
    company_url=f"https://data.sec.gov/submissions/CIK{cik10}.json"
    sub=_fetch_json(company_url)
    filings=[x for x in _recent_filings(sub) if str(x.get("filingDate"))<=asof]
    periodic=[x for x in filings if str(x.get("form")).upper() in PERIODIC]
    if not periodic:
        return {"status":"UNKNOWN","reason":"NO_PERIODIC_FILING_BEFORE_ASOF",
                "cik":cik10,"sec_submissions_url":company_url}
    periodic.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])),reverse=True)
    latest=periodic[0]
    start=str(latest["filingDate"])
    scoped=[x for x in filings if start<=str(x.get("filingDate"))<=asof]
    scoped.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])))

    hard=[];risks=[];docs=[];document_failures=[]
    for row in scoped:
        form=str(row.get("form") or "").upper()
        items=_item_set(row.get("items"))
        for it,label in HARD_ITEMS.items():
            if it in items: hard.append(f"{label}:{row['filingDate']}:{form}")
        for it,label in RISK_ITEMS.items():
            if it in items: risks.append(f"{label}:{row['filingDate']}:{form}")
        if form.startswith(OFFERING_PREFIX):
            risks.append(f"FINANCING_OR_OFFERING_FILING:{row['filingDate']}:{form}")

        # Read the latest periodic plus current-report / offering primary documents.
        if form in REVIEW_FORMS or form.startswith(OFFERING_PREFIX):
            url=_doc_url(cik10,row)
            if url:
                try:
                    txt=_clean_html(_fetch(url))
                    for f in _phrase_flags(txt,HARD_PHRASES):
                        hard.append(f"{f}:{row['filingDate']}:{form}")
                    for f in _phrase_flags(txt,RISK_PHRASES):
                        risks.append(f"{f}:{row['filingDate']}:{form}")
                    docs.append({"filing_date":row["filingDate"],"form":form,
                                 "accession_number":row["accessionNumber"],"url":url,
                                 "items":sorted(items)})
                except Exception as exc:
                    document_failures.append({
                        "filing_date":row["filingDate"],"form":form,
                        "accession_number":row["accessionNumber"],
                        "reason":f"{type(exc).__name__}:{str(exc)[:120]}"
                    })
            else:
                document_failures.append({"filing_date":row["filingDate"],"form":form,
                                          "reason":"PRIMARY_DOCUMENT_URL_MISSING"})

    hard=sorted(set(hard));risks=sorted(set(risks))
    if document_failures:
        status="UNKNOWN";reason="SEC_PRIMARY_DOCUMENT_REVIEW_INCOMPLETE"
    elif hard:
        status="UNKNOWN";reason="HIGH_SEVERITY_LEGAL_FLAG_REQUIRES_EXPLICIT_RESOLUTION"
    else:
        status="PASS";reason="DETAILED_SEC_REVIEW_COMPLETE_NO_UNRESOLVED_HARD_LEGAL_FLAG"

    return {
      "status":status,"reason":reason,"cik":cik10,
      "issuer_name":sub.get("name"),"sic":sub.get("sic"),"fiscal_year_end":sub.get("fiscalYearEnd"),
      "latest_periodic":{"form":latest.get("form"),"filing_date":latest.get("filingDate"),
                         "report_date":latest.get("reportDate"),
                         "accession_number":latest.get("accessionNumber"),
                         "url":_doc_url(cik10,latest)},
      "review_window":{"start_filing_date":start,"end_asof":asof},
      "reviewed_filing_count":len(scoped),
      "reviewed_primary_documents":docs,
      "hard_legal_flags":hard,
      "risk_flags":risks,
      "document_failures":document_failures,
      "sec_submissions_url":company_url,
    }


def main():
    deep=json.loads(DEEP.read_text())
    asof=str(deep.get("asof_et") or "")
    if deep.get("task_id")!=TASK_ID or deep.get("execution")!="NONE" or deep.get("real_money")!="NO-GO":
        raise RuntimeError("DEEP_SAFETY_OR_TASK_MISMATCH")
    fc=json.loads(FAMILY_C.read_text()) if FAMILY_C.exists() else None
    if fc is not None and (fc.get("task_id")!=TASK_ID or fc.get("asof_et")!=asof
                           or fc.get("execution")!="NONE" or fc.get("real_money")!="NO-GO"):
        raise RuntimeError("FAMILY_C_SAFETY_OR_ASOF_MISMATCH")
    lifecycle=json.loads(LIFECYCLE.read_text()) if LIFECYCLE.exists() else None
    if lifecycle is not None and (lifecycle.get("task_id")!=TASK_ID
                                  or lifecycle.get("execution")!="NONE"
                                  or lifecycle.get("real_money")!="NO-GO"):
        raise RuntimeError("LIFECYCLE_SAFETY_OR_TASK_MISMATCH")

    scope=candidate_scope(deep,fc,lifecycle)
    cikmap=_ticker_cik_map()
    records={}
    for sym in scope:
        cik=cikmap.get(sym.upper())
        if not cik:
            records[sym]={"status":"UNKNOWN","reason":"SEC_TICKER_CIK_NOT_FOUND"}
            continue
        try:
            records[sym]=review_symbol(sym,cik,asof)
        except Exception as exc:
            records[sym]={"status":"UNKNOWN",
                          "reason":f"SEC_REVIEW_ERROR:{type(exc).__name__}:{str(exc)[:180]}",
                          "cik":cik}
        time.sleep(0.12)

    out={
      "schema":"XRAY_CANDIDATE_LEGAL_GUARD_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "authority":"SEC_EDGAR_PRIMARY_DETAILED_FINALIST_REVIEW_V1",
      "review_scope":"LATEST_PERIODIC_FILING_THROUGH_ASOF",
      "candidate_scope":scope,"candidate_scope_count":len(scope),"candidate_scope_hash":scope_hash(scope),
      "source_deep_path":str(DEEP.relative_to(DEEP.parent.parent)),
      "source_deep_blob_sha":blob_sha(DEEP),
      "source_family_c_path":str(FAMILY_C.relative_to(FAMILY_C.parent.parent)) if FAMILY_C.exists() else None,
      "source_family_c_blob_sha":blob_sha(FAMILY_C),
      "source_lifecycle_path":str(LIFECYCLE.relative_to(LIFECYCLE.parent.parent)) if LIFECYCLE.exists() else None,
      "source_lifecycle_blob_sha":blob_sha(LIFECYCLE),
      "pass_symbols":sorted(s for s,r in records.items() if r.get("status")=="PASS"),
      "unknown_symbols":sorted(s for s,r in records.items() if r.get("status")!="PASS"),
      "records":dict(sorted(records.items())),
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"candidate_scope_count":len(scope),
                      "pass_count":len(out["pass_symbols"]),
                      "unknown_count":len(out["unknown_symbols"]),
                      "unknown_symbols":out["unknown_symbols"]},sort_keys=True))


if __name__=="__main__":
    main()
