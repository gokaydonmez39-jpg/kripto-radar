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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY=ROOT/"chatgpt_compiled_policy_v3.json"
POLICY_BLOB="10d7af14870dfac0dc4566595d95a06f3faa854d"
POLICY_HASH="26a95745a50b65e85f6ece24b6501af0994764a84ddd886edb70d1fcd770849c"
POLICY_VERSION="C4.17"
DEEP=Path(os.getenv("XRAY_LEGAL_GUARD_DEEP",str(ROOT/"canonical_current_deep_full.json")))
FAMILY_C=Path(os.getenv("XRAY_LEGAL_GUARD_FAMILY_C",str(ROOT/"canonical_current_family_c.json")))
LIFECYCLE=Path(os.getenv("XRAY_LEGAL_GUARD_LIFECYCLE",str(ROOT/"canonical_candidate_lifecycle_registry.json")))
PREV_FINAL=Path(os.getenv("XRAY_LEGAL_GUARD_PREV_FINAL",str(ROOT/"canonical_current_final_tech.json")))
OUT=Path(os.getenv("XRAY_LEGAL_GUARD_OUT",str(ROOT/"canonical_candidate_legal_guard.json")))
CIK_CACHE=Path(os.getenv("XRAY_SEC_CIK_CACHE",str(ROOT/"sec_ticker_cik_cache.json")))
TASK_ID="6a825366222081918997094d76e6ae46"
USER_AGENT=os.getenv("XRAY_SEC_USER_AGENT","NASDAQ-SWING-XRAY research bot; xray-dataplane-bot@users.noreply.github.com")
SEC_MIN_INTERVAL_SECONDS=float(os.getenv("XRAY_SEC_MIN_INTERVAL_SECONDS","0.22"))
_SEC_LAST_REQUEST_AT=0.0
_PRIMARY_DOC_CACHE={}
_SEC_MASTER_INDEX_CACHE={}
PERIODIC={"10-K","10-Q","20-F","40-F"}
ANNUAL={"10-K","20-F","40-F"}
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
LIFECYCLE_ACTIVE_STATES={
    "WATCH_RETEST_REQUIRED","WATCH_RECONFIRMATION_REQUIRED",
    "WATCH_CHASE_RETEST_REQUIRED","WATCH_EXTENSION_RESET_REQUIRED",
    "WATCH_REGIME_REVALIDATION_REQUIRED","WATCH_REGIME_UNKNOWN",
    "PRE_G9_TECH_PASS","WATCH_EVENT_UNKNOWN_OR_BLOCKED","WATCH_MC_FALLBACK_CAP",
}
RISK_PHRASES={
    "GOING_CONCERN_REFERENCE":"going concern",
    "BANKRUPTCY_REFERENCE":"bankruptcy",
    "EVENT_OF_DEFAULT_REFERENCE":"event of default",
    "COVENANT_REFERENCE":"covenant",
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
    global _SEC_LAST_REQUEST_AT
    last=None
    for attempt in range(retries):
        try:
            now=time.monotonic()
            wait=SEC_MIN_INTERVAL_SECONDS-(now-_SEC_LAST_REQUEST_AT)
            if wait>0: time.sleep(wait)
            req=urllib.request.Request(url,headers={
                "User-Agent":USER_AGENT,
                "Accept-Encoding":"identity",
                "Accept":"application/json,application/atom+xml,text/html,*/*",
                "Accept-Language":"en-US,en;q=0.9",
                "Referer":"https://www.sec.gov/",
                "Connection":"close",
            })
            with urllib.request.urlopen(req,timeout=20) as r:
                _SEC_LAST_REQUEST_AT=time.monotonic()
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


def load_lifecycle_state(asof:str|None=None)->tuple[dict|None,str]:
    """Mirror Final lifecycle fallback and reject future-dated look-ahead state."""
    chosen=None;source="NONE"
    if PREV_FINAL.exists():
        try:
            j=json.loads(PREV_FINAL.read_text())
            cand=j.get("lifecycle_registry") or {}
            if (cand.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
                and cand.get("execution")=="NONE" and cand.get("real_money")=="NO-GO"
                and isinstance(cand.get("records"),dict)):
                src_asof=str(cand.get("asof_et") or j.get("asof_et") or "")
                if asof and src_asof and src_asof>asof:
                    raise RuntimeError("LIFECYCLE_REGISTRY_FUTURE_ASOF")
                chosen=cand;source="PREVIOUS_FINAL_EMBEDDED"
        except RuntimeError:
            raise
        except Exception:
            pass
    if LIFECYCLE.exists():
        try:
            cand=json.loads(LIFECYCLE.read_text())
            if not (cand.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
                and cand.get("execution")=="NONE" and cand.get("real_money")=="NO-GO"
                and isinstance(cand.get("records"),dict)):
                raise RuntimeError("LIFECYCLE_SIDECAR_INVALID")
            src_asof=str(cand.get("asof_et") or "")
            if asof and src_asof and src_asof>asof:
                raise RuntimeError("LIFECYCLE_REGISTRY_FUTURE_ASOF")
            for rec in (cand.get("records") or {}).values():
                if not isinstance(rec,dict): continue
                last=str(rec.get("last_asof") or "")
                if asof and last and last>asof:
                    raise RuntimeError("LIFECYCLE_RECORD_FUTURE_ASOF")
            chosen=cand;source="SIDECAR"
        except Exception as exc:
            raise RuntimeError("LIFECYCLE_SIDECAR_PARSE_SCHEMA_OR_TIME_FAIL") from exc
    return chosen,source


def candidate_scope(deep:dict,fc:dict|None,lifecycle:dict|None)->list[str]:
    """Exact finalist-local legal scope, matching Final/Terminal current-confirmed semantics.

    Fresh A/B/D names come only from Deep's event+RS confirmed aggregate sets.
    Raw per-symbol geometry can remain true after an event veto and must not
    create unrelated SEC UNKNOWNs. Prospectively recorded lifecycle symbols
    remain in scope because Final may carry them through revalidation.
    """
    syms=set()
    for field in ("a_geometry_rs_event_pass","b_breakout_rs_event_pass","d_dk3_pre_r1"):
        syms.update(str(x) for x in (deep.get(field) or []) if str(x))

    rows=deep.get("results") or {}
    for sym,g in ((fc or {}).get("confirmed") or {}).items():
        if (isinstance(g,dict) and g.get("confirmed")
            and ((rows.get(sym) or {}).get("regime_finalist_pass") is True)):
            syms.add(str(sym))

    for rec in ((lifecycle or {}).get("records") or {}).values():
        if (isinstance(rec,dict) and rec.get("symbol")
            and str(rec.get("state") or "") in LIFECYCLE_ACTIVE_STATES):
            syms.add(str(rec["symbol"]))
    return sorted(syms)

def _load_cik_cache()->tuple[dict[str,str],dict[str,str]]:
    """Load durable SEC ticker->CIK evidence; malformed cache fails closed."""
    if not CIK_CACHE.exists(): return {},{}
    j=json.loads(CIK_CACHE.read_text())
    if (j.get("schema")!="XRAY_SEC_TICKER_CIK_CACHE_V1"
        or j.get("execution")!="NONE" or j.get("real_money")!="NO-GO"
        or j.get("unknown_never_pass") is not True):
        raise RuntimeError("SEC_CIK_CACHE_SCHEMA_OR_SAFETY_FAIL")
    out={};sources={}
    for ticker,row in (j.get("records") or {}).items():
        if not isinstance(row,dict): continue
        t=str(ticker or "").upper().strip()
        cik=str(row.get("cik") or "").strip()
        if not t or not re.fullmatch(r"\d{10}",cik):
            raise RuntimeError("SEC_CIK_CACHE_RECORD_INVALID")
        out[t]=cik
        sources[t]="DURABLE_SEC_COMPANY_TICKERS_SNAPSHOT"
    return out,sources


def _merge_company_ticker_payload(j:dict,out:dict[str,str],sources:dict[str,str],label:str)->None:
    rows=[]
    if isinstance(j.get("fields"),list) and isinstance(j.get("data"),list):
        fields=[str(x) for x in j["fields"]]
        for raw in j["data"]:
            if isinstance(raw,list):
                rows.append(dict(zip(fields,raw)))
    else:
        rows=[x for x in j.values() if isinstance(x,dict)]
    for row in rows:
        t=str(row.get("ticker") or "").upper().strip()
        cik=row.get("cik_str",row.get("cik"))
        try: c=str(int(cik)).zfill(10)
        except Exception: continue
        if t:
            out[t]=c
            sources[t]=label


def _ticker_cik_map(scope:list[str]|None=None,allow_network:bool=True)->tuple[dict[str,str],dict[str,str],list[str]]:
    """Resolve ticker->CIK without turning one SEC mapping outage into a global crash.

    Durable official SEC snapshot evidence is authoritative for cached symbols.
    Missing symbols may be filled only from official SEC endpoints. If every
    official mapping endpoint is unavailable, unresolved symbols stay absent and
    are emitted as UNKNOWN by the caller; UNKNOWN never becomes PASS.
    """
    out,sources=_load_cik_cache()
    errors=[]
    need={str(x).upper() for x in (scope or []) if str(x)}
    if not allow_network or (need and need<=set(out)):
        return out,sources,errors

    for url,label in (
        ("https://www.sec.gov/files/company_tickers.json","SEC_COMPANY_TICKERS_JSON_LIVE"),
        ("https://www.sec.gov/files/company_tickers_exchange.json","SEC_COMPANY_TICKERS_EXCHANGE_JSON_LIVE"),
    ):
        try:
            _merge_company_ticker_payload(_fetch_json(url),out,sources,label)
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{str(exc)[:120]}")
        if need and need<=set(out): return out,sources,errors

    try:
        raw=_fetch("https://www.sec.gov/include/ticker.txt",limit=2_000_000).decode("utf-8","replace")
        for line in raw.splitlines():
            p=line.strip().split("\t")
            if len(p)<2: continue
            t=p[0].upper().strip()
            try: c=str(int(p[1])).zfill(10)
            except Exception: continue
            if t:
                out[t]=c
                sources[t]="SEC_TICKER_TXT_LIVE"
    except Exception as exc:
        errors.append(f"SEC_TICKER_TXT_LIVE:{type(exc).__name__}:{str(exc)[:120]}")
    return out,sources,errors


def _xml_local(tag:str)->str:
    return str(tag).rsplit("}",1)[-1]


def _atom_company_filings(cik10:str,asof:str)->tuple[dict,list[dict],str]:
    """Official SEC www.sec.gov Atom fallback when data.sec.gov submissions is unavailable.

    This remains primary-source SEC evidence. It does not create PASS from a
    secondary provider and preserves UNKNOWN on any parse/network ambiguity.
    """
    params={
      "action":"getcompany",
      "CIK":str(int(cik10)),
      "owner":"exclude",
      "count":"100",
      "output":"atom",
    }
    url="https://www.sec.gov/cgi-bin/browse-edgar?"+urllib.parse.urlencode(params)
    root=ET.fromstring(_fetch(url,limit=8_000_000))
    feed_meta={}
    filings=[]
    for el in root.iter():
        key=_xml_local(el.tag)
        txt=(el.text or "").strip()
        if key in {"company-name","cik","sic","fiscal-year-end"} and txt and key not in feed_meta:
            feed_meta[key]=txt
    for entry in [x for x in root.iter() if _xml_local(x.tag)=="entry"]:
        vals={}
        alt_href=""
        for el in entry.iter():
            key=_xml_local(el.tag)
            txt=(el.text or "").strip()
            if txt and key not in vals:
                vals[key]=txt
            if key=="link" and (el.attrib.get("rel") in (None,"alternate")):
                href=str(el.attrib.get("href") or "").strip()
                if href: alt_href=href
        form=(vals.get("filing-type") or vals.get("form-type") or vals.get("category") or "").upper().strip()
        filing_date=(vals.get("filing-date") or vals.get("filingDate") or "")[:10]
        acc=(vals.get("filing-accession-number") or vals.get("accession-number") or vals.get("accessionNumber") or "").strip()
        if not (form and filing_date and acc):
            title=str(vals.get("title") or "")
            m=re.match(r"\s*([^\s]+)\s+-",title)
            if not form and m: form=m.group(1).upper()
        if not (form and filing_date and acc):
            continue
        if filing_date>asof:
            continue
        href=(vals.get("filing-href") or alt_href or "").strip()
        filings.append({
          "accessionNumber":acc,
          "filingDate":filing_date,
          "reportDate":(vals.get("period") or vals.get("report-date") or "")[:10],
          "form":form,
          "items":vals.get("items") or "",
          "primaryDocument":"",
          "primaryDocDescription":"",
          "filingHref":href,
        })
    if not filings:
        raise RuntimeError("SEC_ATOM_NO_FILINGS")
    sub={
      "name":feed_meta.get("company-name"),
      "sic":feed_meta.get("sic"),
      "fiscalYearEnd":feed_meta.get("fiscal-year-end"),
    }
    return sub,filings,url



def _archive_quarters(asof:str,lookback_days:int=550)->list[tuple[int,int]]:
    end=datetime.fromisoformat(asof).date()
    start=end-timedelta(days=lookback_days)
    y=start.year
    q=(start.month-1)//3+1
    end_q=(end.month-1)//3+1
    out=[]
    while y<end.year or (y==end.year and q<=end_q):
        out.append((y,q))
        q+=1
        if q>4:
            y+=1
            q=1
    return out


def _sec_master_index(year:int,qtr:int)->tuple[list[dict],str]:
    key=(int(year),int(qtr))
    if key in _SEC_MASTER_INDEX_CACHE:
        return _SEC_MASTER_INDEX_CACHE[key]
    url=f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/master.idx"
    raw=_fetch(url,limit=60_000_000).decode("utf-8","replace")
    rows=[]
    for line in raw.splitlines():
        p=line.split("|",4)
        if len(p)!=5 or not p[0].strip().isdigit():
            continue
        try:
            cik=str(int(p[0].strip())).zfill(10)
        except Exception:
            continue
        form=p[2].strip().upper()
        filing_date=p[3].strip()
        filename=p[4].strip()
        if not form or not filing_date or not filename:
            continue
        rows.append({
          "cik":cik,
          "issuer_name":p[1].strip(),
          "form":form,
          "filingDate":filing_date,
          "filename":filename,
        })
    _SEC_MASTER_INDEX_CACHE[key]=(rows,url)
    return rows,url


def _sec_archives_inventory(cik10:str,asof:str)->tuple[dict,list[dict],str]:
    filings=[]
    index_urls=[]
    issuer_name=None
    for year,qtr in _archive_quarters(asof):
        rows,url=_sec_master_index(year,qtr)
        index_urls.append(url)
        for x in rows:
            if x.get("cik")!=cik10:
                continue
            if str(x.get("filingDate") or "")>asof:
                continue
            form=str(x.get("form") or "").upper()
            if not (form in REVIEW_FORMS or form in PERIODIC or form.startswith(OFFERING_PREFIX)):
                continue
            filename=str(x.get("filename") or "")
            base=Path(filename).name
            if not base.lower().endswith(".txt"):
                continue
            acc=base[:-4]
            if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",acc):
                continue
            compact=acc.replace("-","")
            issuer_name=issuer_name or x.get("issuer_name")
            filings.append({
              "accessionNumber":acc,
              "filingDate":str(x["filingDate"]),
              "reportDate":"",
              "form":form,
              "items":"",
              "primaryDocument":"",
              "primaryDocDescription":"",
              "filingHref":f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{compact}/{acc}-index.html",
              "submissionTextHref":"https://www.sec.gov/Archives/"+filename.lstrip("/"),
              "inventorySource":"SEC_ARCHIVES_FULL_INDEX",
            })
    # An accession must be unique across EDGAR master indexes. Duplicate
    # inventory is an integrity fault, never a reason to deduplicate into PASS.
    accs=[str(x["accessionNumber"]) for x in filings]
    if len(accs)!=len(set(accs)):
        raise RuntimeError("SEC_ARCHIVES_DUPLICATE_ACCESSION")
    if not filings:
        raise RuntimeError("SEC_ARCHIVES_NO_FILINGS")
    filings.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])),reverse=True)
    sub={"name":issuer_name,"sic":None,"fiscalYearEnd":None}
    return sub,filings,"SEC_ARCHIVES_FULL_INDEX_FALLBACK_V1"


def _hydrate_archive_index_row(row:dict)->dict:
    if row.get("inventorySource")!="SEC_ARCHIVES_FULL_INDEX":
        return row
    if row.get("_archiveHydrated") is True:
        return row
    index_url=str(row.get("filingHref") or "")
    if not index_url:
        raise RuntimeError("SEC_ARCHIVE_INDEX_URL_MISSING")
    raw=_fetch(index_url,limit=7_000_000)
    source=raw.decode("utf-8","replace")
    clean=_clean_html(raw)

    # Filing index pages expose "Period of Report" and 8-K item numbers.
    pm=re.search(r"\bperiod of report\s+(\d{4}-\d{2}-\d{2})\b",clean,re.I)
    if pm:
        row["reportDate"]=pm.group(1)
    items=sorted(set(re.findall(r"\bitem\s+(\d+\.\d+)\b",clean,re.I)))
    row["items"]=",".join(items)

    # Reuse the same SEC filing-index primary-document resolver already used by
    # Atom. This retains a single document-selection semantic.
    primary=_primary_doc_from_index(index_url,str(row.get("form") or ""))
    if not primary:
        raise RuntimeError("SEC_ARCHIVE_PRIMARY_DOCUMENT_NOT_FOUND")
    row["primaryDocument"]=primary.rsplit("/",1)[-1]
    row["_primaryDocumentUrl"]=primary
    row["_archiveHydrated"]=True
    return row


def _sec_submissions_or_atom(cik10:str,asof:str)->tuple[dict,list[dict],str,str|None]:
    company_url=f"https://data.sec.gov/submissions/CIK{cik10}.json"
    try:
        sub=_fetch_json(company_url)
        return sub,_recent_filings(sub),"DATA_SEC_SUBMISSIONS_JSON",None
    except Exception as primary_exc:
        primary_error=f"{type(primary_exc).__name__}:{str(primary_exc)[:160]}"
    try:
        sub,filings,atom_url=_atom_company_filings(cik10,asof)
        return sub,filings,"SEC_WWW_ATOM_FALLBACK",primary_error
    except Exception as atom_exc:
        atom_error=f"{type(atom_exc).__name__}:{str(atom_exc)[:160]}"
    sub,filings,source=_sec_archives_inventory(cik10,asof)
    return sub,filings,source,primary_error+" | ATOM:"+atom_error


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


def _normalize_sec_doc_href(href:str)->str|None:
    href=str(href or "").strip()
    if not href:return None
    full=urllib.parse.urljoin("https://www.sec.gov/",href)
    p=urllib.parse.urlparse(full)
    q=urllib.parse.parse_qs(p.query)
    if "doc" in q and q["doc"]:
        full=urllib.parse.urljoin("https://www.sec.gov/",q["doc"][0])
    return full if full.startswith("https://www.sec.gov/") else None


def _primary_doc_from_index(index_url:str,form:str)->str|None:
    key=(str(index_url),str(form).upper())
    if key in _PRIMARY_DOC_CACHE:return _PRIMARY_DOC_CACHE[key]
    raw=_fetch(str(index_url),limit=5_000_000).decode("utf-8","replace")
    rows=re.findall(r"(?is)<tr[^>]*>(.*?)</tr>",raw)
    candidates=[]
    for row_html in rows:
        text_row=re.sub(r"(?s)<[^>]+>"," ",row_html)
        text_row=html.unescape(re.sub(r"\s+"," ",text_row)).strip()
        hrefs=re.findall(r'''(?is)href=["']([^"']+)["']''',row_html)
        for href in hrefs:
            u=_normalize_sec_doc_href(href)
            if not u or "/Archives/edgar/data/" not in u:continue
            low=u.lower()
            if low.endswith(("-index.htm","-index.html")) or "/ixviewer/" in low:continue
            if not re.search(r"\.(?:htm|html|txt)(?:$|\?)",low):continue
            score=2 if re.search(rf"(?i)(?:^|\s){re.escape(str(form))}(?:\s|$)",text_row) else 0
            if "complete submission text file" in text_row.lower():score-=1
            candidates.append((score,u))
    if not candidates:
        _PRIMARY_DOC_CACHE[key]=None
        return None
    candidates.sort(key=lambda x:(-x[0],x[1]))
    _PRIMARY_DOC_CACHE[key]=candidates[0][1]
    return candidates[0][1]


def _doc_url(cik10:str,row:dict)->str|None:
    if row.get("_primaryDocumentUrl"):
        return str(row["_primaryDocumentUrl"])
    acc=str(row.get("accessionNumber") or "")
    doc=str(row.get("primaryDocument") or "")
    if acc and doc:
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc.replace('-','')}/{doc}"
    href=str(row.get("filingHref") or "")
    if href:
        return _primary_doc_from_index(href,str(row.get("form") or ""))
    return None


def _item_set(items)->set[str]:
    if isinstance(items,list): raw=",".join(str(x) for x in items)
    else: raw=str(items or "")
    return set(re.findall(r"\b\d+\.\d+\b",raw))


def _phrase_flags(text:str,phrases:dict)->list[str]:
    # SEC credit-agreement boilerplate commonly uses the plural
    # "events of default". Normalize only this grammatical variant so the
    # detailed review records the same non-blocking default-risk reference
    # without broadening it into a hard legal veto.
    scan=text.replace("events of default","event of default")
    out=[]
    for flag,p in phrases.items():
        if isinstance(p,tuple):
            if all(x in scan for x in p): out.append(flag)
        elif p in scan: out.append(flag)
    return out


def review_symbol(symbol:str,cik10:str,asof:str)->dict:
    company_url=f"https://data.sec.gov/submissions/CIK{cik10}.json"
    sub,filings,sec_listing_source,submissions_error=_sec_submissions_or_atom(cik10,asof)
    filings=[x for x in filings if str(x.get("filingDate"))<=asof]
    periodic=[x for x in filings if str(x.get("form")).upper() in PERIODIC]
    if not periodic:
        return {"status":"UNKNOWN","reason":"NO_PERIODIC_FILING_BEFORE_ASOF",
                "cik":cik10,"sec_submissions_url":company_url}
    annual=[x for x in filings if str(x.get("form")).upper() in ANNUAL]
    if not annual:
        return {"status":"UNKNOWN","reason":"NO_RECENT_ANNUAL_FILING_BEFORE_ASOF",
                "cik":cik10,"sec_submissions_url":company_url}
    annual.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])),reverse=True)
    periodic.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])),reverse=True)
    latest_annual=annual[0]
    quarterlies=[x for x in filings if str(x.get("form")).upper()=="10-Q"]
    quarterlies.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])),reverse=True)
    latest_quarterly=quarterlies[0] if quarterlies else None
    latest=periodic[0]
    # C4.17 requires recent 10-K/10-Q plus material current/offering filings.
    # Starting at the latest annual filing guarantees the annual report is read,
    # all later quarterlies are read, and intervening 8-K/6-K/offering evidence
    # cannot be skipped merely because a newer 10-Q exists.
    start=str(latest_annual["filingDate"])
    scoped=[x for x in filings if start<=str(x.get("filingDate"))<=asof]
    scoped.sort(key=lambda x:(str(x["filingDate"]),str(x["accessionNumber"])))

    hard=[];risks=[];docs=[];document_failures=[]
    for row in scoped:
        form=str(row.get("form") or "").upper()
        if row.get("inventorySource")=="SEC_ARCHIVES_FULL_INDEX":
            try:
                _hydrate_archive_index_row(row)
            except Exception as exc:
                document_failures.append({
                    "filing_date":row.get("filingDate"),"form":form,
                    "accession_number":row.get("accessionNumber"),
                    "reason":f"SEC_ARCHIVE_INDEX:{type(exc).__name__}:{str(exc)[:120]}"
                })
                continue
        items=_item_set(row.get("items"))
        # For 8-K the hard/risk item set is itself part of C4.17 evidence. If
        # the archive index does not expose an item number, do not silently PASS.
        if row.get("inventorySource")=="SEC_ARCHIVES_FULL_INDEX" and form=="8-K" and not items:
            document_failures.append({
                "filing_date":row.get("filingDate"),"form":form,
                "accession_number":row.get("accessionNumber"),
                "reason":"SEC_ARCHIVE_8K_ITEM_SET_UNPROVEN"
            })
            continue
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
      "latest_annual":{"form":latest_annual.get("form"),"filing_date":latest_annual.get("filingDate"),
                       "report_date":latest_annual.get("reportDate"),
                       "accession_number":latest_annual.get("accessionNumber"),
                       "url":_doc_url(cik10,latest_annual)},
      "latest_quarterly":({"form":latest_quarterly.get("form"),"filing_date":latest_quarterly.get("filingDate"),
                           "report_date":latest_quarterly.get("reportDate"),
                           "accession_number":latest_quarterly.get("accessionNumber"),
                           "url":_doc_url(cik10,latest_quarterly)} if latest_quarterly else None),
      "review_window":{"start_filing_date":start,"end_asof":asof,
                       "basis":"LATEST_ANNUAL_THROUGH_ASOF_INCLUDING_ALL_LATER_PERIODIC_CURRENT_AND_OFFERING_FILINGS"},
      "reviewed_filing_count":len(scoped),
      "reviewed_primary_documents":docs,
      "hard_legal_flags":hard,
      "risk_flags":risks,
      "document_failures":document_failures,
      "sec_submissions_url":company_url,
      "sec_listing_source":sec_listing_source,
      "sec_submissions_primary_error":submissions_error,
      "sec_archives_full_index_fallback":bool(sec_listing_source=="SEC_ARCHIVES_FULL_INDEX_FALLBACK_V1"),
    }


def main():
    if not POLICY.exists() or blob_sha(POLICY)!=POLICY_BLOB:
        raise RuntimeError("COMPILED_POLICY_BLOB_MISMATCH")
    policy=json.loads(POLICY.read_text())
    if (policy.get("schema")!="XRAY_GITHUB_COMPILED_POLICY_V3"
        or policy.get("policy_hash")!=POLICY_HASH
        or policy.get("execution")!="NONE" or policy.get("real_money")!="NO-GO"):
        raise RuntimeError("COMPILED_POLICY_AUTHORITY_MISMATCH")
    payload=json.loads(policy.get("payload_json") or "{}")
    if (payload.get("version")!=POLICY_VERSION
        or payload.get("unknown_never_pass") is not True
        or payload.get("execution")!="NONE" or payload.get("real_money")!="NO-GO"):
        raise RuntimeError("COMPILED_POLICY_VERSION_OR_SAFETY_MISMATCH")
    deep=json.loads(DEEP.read_text())
    asof=str(deep.get("asof_et") or "")
    if deep.get("task_id")!=TASK_ID or deep.get("execution")!="NONE" or deep.get("real_money")!="NO-GO":
        raise RuntimeError("DEEP_SAFETY_OR_TASK_MISMATCH")
    fc=json.loads(FAMILY_C.read_text()) if FAMILY_C.exists() else None
    if fc is not None and (fc.get("task_id")!=TASK_ID or fc.get("asof_et")!=asof
                           or fc.get("execution")!="NONE" or fc.get("real_money")!="NO-GO"):
        raise RuntimeError("FAMILY_C_SAFETY_OR_ASOF_MISMATCH")
    lifecycle,lifecycle_source=load_lifecycle_state(asof)
    if lifecycle is not None and (lifecycle.get("task_id") not in (None,TASK_ID)
                                  or lifecycle.get("execution")!="NONE"
                                  or lifecycle.get("real_money")!="NO-GO"):
        raise RuntimeError("LIFECYCLE_SAFETY_OR_TASK_MISMATCH")

    scope=candidate_scope(deep,fc,lifecycle)
    # No finalist/lifecycle candidate means there is nothing to query from SEC.
    # Produce an exact empty guard without making external network availability
    # a false FULL_E2E blocker for an empty candidate scope.
    cikmap,cik_sources,cik_mapping_errors=_ticker_cik_map(scope) if scope else ({},{},[])
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
        records[sym]["cik_mapping_source"]=cik_sources.get(sym.upper(),"UNKNOWN")
        time.sleep(0.12)

    out={
      "schema":"XRAY_CANDIDATE_LEGAL_GUARD_V1","task_id":TASK_ID,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "authority":"SEC_EDGAR_PRIMARY_DETAILED_FINALIST_REVIEW_V1",
      "review_scope":"LATEST_ANNUAL_THROUGH_ASOF_WITH_ALL_LATER_PERIODIC_CURRENT_AND_OFFERING_FILINGS",
      "compiled_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
      "compiled_policy_blob_sha":POLICY_BLOB,
      "compiled_policy_hash":POLICY_HASH,
      "compiled_policy_version":POLICY_VERSION,
      "source_cik_cache_path":"nasdaq-xray/sec_ticker_cik_cache.json",
      "source_cik_cache_blob_sha":blob_sha(CIK_CACHE),
      "cik_mapping_errors":cik_mapping_errors,
      "cik_mapping_sources":{s:cik_sources.get(s.upper(),"MISSING") for s in scope},
      "candidate_scope":scope,"candidate_scope_count":len(scope),"candidate_scope_hash":scope_hash(scope),
      "source_deep_path":str(DEEP.relative_to(DEEP.parent.parent)),
      "source_deep_blob_sha":blob_sha(DEEP),
      "source_family_c_path":str(FAMILY_C.relative_to(FAMILY_C.parent.parent)) if FAMILY_C.exists() else None,
      "source_family_c_blob_sha":blob_sha(FAMILY_C),
      "source_lifecycle_path":str(LIFECYCLE.relative_to(LIFECYCLE.parent.parent)) if LIFECYCLE.exists() else None,
      "source_lifecycle_blob_sha":blob_sha(LIFECYCLE),
      "source_lifecycle_fallback_path":str(PREV_FINAL.relative_to(PREV_FINAL.parent.parent)) if PREV_FINAL.exists() else None,
      "source_lifecycle_fallback_blob_sha":blob_sha(PREV_FINAL) if lifecycle_source=="PREVIOUS_FINAL_EMBEDDED" else None,
      "source_lifecycle_scope_source":lifecycle_source,
      "source_lifecycle_binding_role":"DIAGNOSTIC_PRE_FINAL_SCOPE_AUGMENTATION",
      "authoritative_binding_note":"DEEP_AND_FAMILY_C_AND_POLICY_EXACT;LIFECYCLE_BLOB_IS_NOT_AUTHORITY_BECAUSE_FINAL_MUTATES_IT_IN_RUN",
      "pass_symbols":sorted(s for s,r in records.items() if r.get("status")=="PASS"),
      "unknown_symbols":sorted(s for s,r in records.items() if r.get("status")!="PASS"),
      "records":dict(sorted(records.items())),
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"candidate_scope_count":len(scope),
                      "pass_count":len(out["pass_symbols"]),
                      "unknown_count":len(out["unknown_symbols"]),
                      "unknown_symbols":out["unknown_symbols"],
                      "unknown_reasons":{sym:(records.get(sym) or {}).get("reason") for sym in out["unknown_symbols"]},
                      "cik_mapping_errors":cik_mapping_errors},sort_keys=True))


if __name__=="__main__":
    main()
