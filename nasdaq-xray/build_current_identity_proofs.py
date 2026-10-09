#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta, time as clocktime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from master_spac_operating_guard import nonblank_requires_completion

ROOT=Path(__file__).resolve().parent
MANUAL_IDENTITY_SEED=ROOT/"master_sec_identity_manual_seed_registry.json"
NASDAQ_DIR="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER="https://api.nasdaq.com/api/screener/stocks"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_TICKERS_EXCHANGE="https://www.sec.gov/files/company_tickers_exchange.json"
SEC_CIK_DISCOVERY_DIAGNOSTICS={}
SEC_SUBMISSIONS="https://data.sec.gov/submissions"
SEC_UA=os.getenv("XRAY_SEC_USER_AGENT","")
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TASK="6a825366222081918997094d76e6ae46"
IDENTITY_DISCOVERY_VERSION="SEC_CURRENT_SUSPECT_DISCOVERY_V9"
SPAC_SUSPECT_RE=re.compile(r"\bacquisition\b|\bspac\b|\bblank[ -]?check\b|\bcapital\s+corp(?:oration)?\.?\s+(?:[IVXLCDM]+|\d+)\s*-\s*class\s+a\s+ordinary\s+shares?\b",re.I)

def current_spac_suspects(names:dict,industries:dict)->list[str]:
    """Return every exact-ASOF Nasdaq name that requires SPAC classification.

    Nasdaq screener industry="Blank Checks" is supporting identity evidence,
    not a substitute for the SEC/manual SIC-6770 proof consumed by MASTER.
    Excluding such rows here created a discovery blind spot: the symbol was
    neither proven/excluded nor left in the SEC discovery queue.
    """
    return sorted(
      sym for sym,name in names.items()
      if bool(SPAC_SUSPECT_RE.search(str(name or "")))
    )

def sec_source_binds_cik(source:str,cik:str)->bool:
    """Require manual SEC evidence URL to bind the exact issuer CIK."""
    try:
        target=str(int(str(cik).strip()))
    except Exception:
        return False
    try:
        u=urllib.parse.urlparse(str(source or ""))
    except Exception:
        return False
    if u.scheme!="https" or u.netloc.lower()!="www.sec.gov":
        return False
    q=urllib.parse.parse_qs(u.query)
    for key,vals in q.items():
        if str(key).upper()=="CIK":
            for val in vals:
                try:
                    if str(int(str(val).strip()))==target:
                        return True
                except Exception:
                    pass
    m=re.search(r"/Archives/edgar/data/(\d+)/",u.path,re.I)
    if m:
        try:
            return str(int(m.group(1)))==target
        except Exception:
            return False
    return False

DIRECTORY_SNAPSHOT_SCHEMA="XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1"
STAMP_RE=re.compile(r"^(master_(?:asof_identity|sec_spac)_proof_)(\d{8})\.json$")
FOOTER_RE=re.compile(r"^File Creation Time:\s*(\d{2})(\d{2})(\d{4})")

def proof_paths(asof:str):
    stamp=asof.replace("-","")
    return (
      ROOT/f"master_asof_identity_proof_{stamp}.json",
      ROOT/f"master_sec_spac_proof_{stamp}.json",
    )

def parse_footer_date(footer:str)->str:
    m=FOOTER_RE.match(str(footer or "").strip())
    if not m:
        raise RuntimeError("NASDAQ_DIRECTORY_FOOTER_DATE_UNPARSEABLE")
    mm,dd,yyyy=m.groups()
    return f"{yyyy}-{mm}-{dd}"

def completed_asof()->str:
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    sched=cal.schedule(
      start_date=(now.date()-timedelta(days=15)).isoformat(),
      end_date=(now.date()+timedelta(days=1)).isoformat(),
    )
    done=[idx.date().isoformat() for idx,row in sched.iterrows() if row["market_close"].to_pydatetime()<=now]
    if not done:
        raise RuntimeError("NO_COMPLETED_NASDAQ_SESSION")
    return done[-1]

def request_bytes(url:str, user_agent:str, timeout:int=45)->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":user_agent,"Accept":"application/json,text/plain,*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()

def official_directory():
    raw=request_bytes(NASDAQ_DIR,UA,35).decode("utf-8")
    lines=[x.strip("\r") for x in raw.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    if not footer:
        raise RuntimeError("NASDAQ_DIRECTORY_FOOTER_MISSING")
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    names={}
    for row in rows:
        sym=str(row.get("Symbol") or "").strip().upper()
        name=str(row.get("Security Name") or "").strip()
        if sym:
            names[sym]=name
    if not names:
        raise RuntimeError("NASDAQ_DIRECTORY_EMPTY")
    return names,footer

def official_screener_industries():
    params=urllib.parse.urlencode({
      "tableonly":"true","limit":"25","offset":"0","exchange":"NASDAQ","download":"true"
    })
    req=urllib.request.Request(
      NASDAQ_SCREENER+"?"+params,
      headers={
        "User-Agent":UA,
        "Accept":"application/json,text/plain,*/*",
        "Origin":"https://www.nasdaq.com",
        "Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
      },
    )
    with urllib.request.urlopen(req,timeout=60) as r:
        obj=json.loads(r.read().decode("utf-8"))
    data=obj.get("data") or {}
    rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
    if len(rows)<1000:
        raise RuntimeError("NASDAQ_SCREENER_TOO_FEW_ROWS")
    out={}
    for row in rows:
        sym=str(row.get("symbol") or "").strip().upper()
        if sym:
            out[sym]=str(row.get("industry") or "").strip()
    return out

def prior_operating_fallback(sym,old,asof,names,industries):
    if sym not in names:
        return None
    current_name=str(names.get(sym) or "").strip()
    prior_name=str((old or {}).get("security_name") or "").strip()
    industry=str(industries.get(sym) or "").strip()
    source=str((old or {}).get("source_url") or "")
    evidence=str((old or {}).get("evidence_date") or "")
    if not current_name or current_name!=prior_name:
        return None
    if not source.startswith("https://www.sec.gov/") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return None
    out=dict(old)
    out["security_name"]=current_name
    out["reason"]="SAME_ASOF_NASDAQ_DIRECTORY_EXACT_NAME_PLUS_PRIOR_SEC_OPERATING_EVIDENCE"
    out["same_asof_nasdaq_screener_industry"]=industry
    out["same_asof_revalidated_without_sec_network"]=True
    out["revalidation_semantics"]="FAIL_CLOSED_PREVENT_FALSE_SPAC_EXCLUSION_ONLY;NO_ALPHA_PASS"
    return out

def prior_blank_fallback(sym,old,asof,names,industries):
    if sym not in names:
        return None
    current_name=str(names.get(sym) or "").strip()
    industry=str(industries.get(sym) or "").strip()
    if int((old or {}).get("sic",-1))!=6770:
        return None
    source=str((old or {}).get("source_url") or "")
    evidence=str((old or {}).get("evidence_date") or "")
    if not source.startswith("https://www.sec.gov/") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return None
    try:
        age=(datetime.fromisoformat(asof)-datetime.fromisoformat(evidence)).days
    except Exception:
        return None
    if age<0 or age>120:
        return None
    name_spac=bool(SPAC_SUSPECT_RE.search(current_name))
    industry_spac=(industry.lower()=="blank checks")
    if not (industry_spac or name_spac):
        return None
    out=dict(old)
    out["same_asof_nasdaq_security_name"]=current_name
    out["same_asof_nasdaq_screener_industry"]=industry
    out["same_asof_revalidated_without_sec_network"]=True
    out["revalidation_semantics"]="PRIOR_SEC_SIC6770_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS"
    return out

def load_json_url(url:str):
    return json.loads(request_bytes(url,SEC_UA,35).decode("utf-8"))

def _nasdaq_exchange_cik_map(raw):
    """Secondary SEC routing is discovery-only, not issuer classification."""
    if not isinstance(raw,dict):
        raise ValueError("SEC_EXCHANGE_HEADER_INVALID")
    fields=raw.get("fields")
    rows=raw.get("data")
    if not isinstance(fields,list) or not isinstance(rows,list):
        raise ValueError("SEC_EXCHANGE_SCHEMA_INVALID")
    if not {"cik","ticker","exchange"}.issubset(set(fields)):
        raise ValueError("SEC_EXCHANGE_FIELDS_INVALID")
    pos={k:fields.index(k) for k in ("cik","ticker","exchange")}
    required=max(pos.values())
    out={}; conflicts=set()
    for row in rows:
        if not isinstance(row,list) or len(row)<=required:
            continue
        if str(row[pos["exchange"]] or "").strip().lower()!="nasdaq":
            continue
        sym=str(row[pos["ticker"]] or "").strip().upper()
        try:cik=int(row[pos["cik"]])
        except (ValueError,TypeError):continue
        if not sym or cik<=0:continue
        if sym in out and out[sym]!=cik:
            conflicts.add(sym)
        else:
            out[sym]=cik
    for sym in conflicts:
        out.pop(sym,None)
    return out,conflicts


def pinned_github_sec_cik_mirror(asof,symbols):
    """Exact-ASOF SHA256 reference-list routing ONLY: SEC submissions remain mandatory.

    GitHub mirror never determines issuer SIC/operating classification. The
    immutable GitHub commit plus manifest and file digest must all verify;
    failure never creates a PASS, override, or legacy carry-forward.
    """
    import sec_mirror_cik_shadow as mirror
    if not asof or not symbols:
        raise ValueError("MIRROR_SCOPE_AND_ASOF_REQUIRED")
    base="https://api.github.com/repos/TylerJForstrom/Stock-Data/git/ref/heads/main"
    ref=json.loads(request_bytes(base,SEC_UA,30).decode("utf-8"))
    sha=str((ref.get("object") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise ValueError("MIRROR_REF_NOT_PINNED")
    prefix="https://raw.githubusercontent.com/TylerJForstrom/Stock-Data/"+sha+"/data/symbols/current/"
    meta=json.loads(request_bytes(prefix+"manifest.json",SEC_UA,30).decode("utf-8"))
    payload=request_bytes(prefix+"sec_company_tickers_exchange.jsonl",SEC_UA,50)
    if len(payload)>3_000_000:
        raise ValueError("MIRROR_DATA_OVERSIZED")
    shadow=mirror.classify(asof,list(symbols),meta,payload)
    # Sole use of mirror: look up CIK to attempt actual official SEC SIC read.
    # Conflict or partial coverage remains UNKNOWN.
    return {sym:int(cik) for sym,cik in shadow["ciK_discovery_only"].items()},{
        "mirror_commit":sha,
        "mirror_source_sha256":shadow["source_sha256"],
        "mirror_exact_asof":asof,
        "mirror_discovered":shadow["ciK_discovered_count"],
        "mirror_scope":len(set(symbols)),
        "mirror_authority":"CIK_ROUTING_ONLY_OFFICIAL_SEC_SIC_REQUIRED",
    }

def sec_ticker_cik_map(asof=None,subjects=None):
    """Try both independent official SEC CIK-route endpoints, fail closed.

    The mappings authorize only CIK discovery. Same-ticker submissions,
    SIC and filed-on-or-before-ASOF remain mandatory for classification.
    If sources disagree, never choose a CIK or promote a security.
    """
    global SEC_CIK_DISCOVERY_DIAGNOSTICS
    out={}; ambiguous=set()
    diag={
      "source":"SEC_TICKERS_PLUS_NASDAQ_EXCHANGE_CIK_ROUTING_ONLY",
      "legacy_valid_count":0,"exchange_added_count":0,
      "conflict_count":0,"classification_authority":False,
      "exact_asof_proof_required":True,
    }
    primary_ok=False; secondary_ok=False
    try:
        raw=load_json_url(SEC_TICKERS)
        if not isinstance(raw,dict):
            raise ValueError("SEC_PRIMARY_TICKERS_SCHEMA_INVALID")
        primary_ok=True
        for row in raw.values():
            if not isinstance(row,dict):continue
            sym=str(row.get("ticker") or "").strip().upper()
            try:cik=int(row.get("cik_str"))
            except (TypeError,ValueError):continue
            if sym and cik>0:
                if sym in out and out[sym]!=cik:
                    ambiguous.add(sym)
                else:
                    out[sym]=cik
        for sym in ambiguous:
            out.pop(sym,None)
        diag["legacy_valid_count"]=len(out)
    except Exception as exc:
        diag["primary_error"]=type(exc).__name__
    try:
        extra,extra_conflicts=_nasdaq_exchange_cik_map(load_json_url(SEC_TICKERS_EXCHANGE))
        secondary_ok=True
        conflicts=ambiguous|extra_conflicts
        for sym,cik in extra.items():
            if sym in out and out[sym]!=cik:
                conflicts.add(sym)
        for sym in conflicts:
            out.pop(sym,None)
        for sym,cik in extra.items():
            if sym not in conflicts and sym not in out:
                out[sym]=cik
                diag["exchange_added_count"]+=1
        diag["exchange_valid_count"]=len(extra)
        diag["conflict_count"]=len(conflicts)
    except Exception as exc:
        diag["secondary_error"]=type(exc).__name__
        diag["conflict_count"]=len(ambiguous)
    if primary_ok and secondary_ok:
        diag["status"]="PASS_DUAL_SEC_CIK_DISCOVERY"
    elif secondary_ok:
        diag["status"]="PASS_EXCHANGE_ONLY_CIK_ROUTING"
    elif primary_ok:
        diag["status"]="SECONDARY_UNAVAILABLE_LEGACY_FALLBACK_ONLY"
    else:
        diag["status"]="BOTH_SEC_TICKER_LISTS_UNAVAILABLE"
    # On dual SEC index transport failure, consult only an independently
    # SHA256-proven and commit-pinned reference snapshot. It supplies CIK
    # routing to official SEC submissions, NEVER SIC or a classification.
    if not primary_ok and not secondary_ok and asof and subjects:
        try:
            mirror_routes,mirror_diag=pinned_github_sec_cik_mirror(asof,subjects)
            out.update(mirror_routes)
            diag.update(mirror_diag)
            diag["status"]="PASS_PINNED_MIRROR_CIK_ONLY_SEC_SIC_REQUIRED"
        except Exception as exc:
            diag["mirror_error"]=type(exc).__name__+":"+str(exc)[:120]
    diag["total_resolved_cik_routes"]=len(out)
    SEC_CIK_DISCOVERY_DIAGNOSTICS=diag
    if not primary_ok and not secondary_ok and not out:
        raise RuntimeError("SEC_CIK_ROUTING_UNAVAILABLE_PRIMARY_AND_SECONDARY")
    return out

def sec_submissions_transport_is_blocked(exc):
    """Only explicit access-policy HTTP failures stop a same-run SEC fan-out.

    A single 403/429 means the remaining CIK issuers stay UNKNOWN this run.
    Other transient errors are symbol-local; no synthetic classifications.
    """
    return getattr(exc,"code",None) in (403,429)

def official_sec_sic(sub:dict):
    """Never infer operating issuer status from absent or contradictory SEC SIC."""
    code=str(sub.get("sic") or "").strip()
    if not re.fullmatch(r"\d{3,4}",code):
        return None
    sic=int(code)
    if sic<=0:
        return None
    desc=str(sub.get("sicDescription") or "").strip()
    # A contradictory description is not affirmative SIC-6770 evidence.
    if desc and (desc.casefold().startswith("blank checks") != (sic==6770)):
        return None
    return sic,desc

def sec_current_classification(sym:str,asof:str,cik:int|None):
    """One same-run SEC submissions read returning blank/nonblank classification."""
    if cik is None:return None
    sub=load_json_url(f"{SEC_SUBMISSIONS}/CIK{int(cik):010d}.json")
    tickers=[str(x).strip().upper() for x in (sub.get("tickers") or [])]
    if str(sym).upper() not in tickers:return None
    official=official_sec_sic(sub)
    if official is None:return None
    sic,desc=official
    evidence=latest_filing_date(sub,asof)
    if not evidence:return None
    is_blank=(sic==6770)
    return {
      "cik":f"{int(cik):010d}",
      "sic":sic,
      "classification":"Blank Checks" if is_blank else desc,
      "source_url":f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}",
      "evidence_date":evidence,
      "is_blank_check":bool(is_blank),
      "same_asof_revalidated_without_sec_network":False,
      "discovery_version":IDENTITY_DISCOVERY_VERSION,
    }

def latest_prior(prefix:str,asof:str):
    best=None
    for p in ROOT.glob(prefix+"*.json"):
        try:
            j=json.loads(p.read_text(encoding="utf-8"))
            d=str(j.get("asof_et") or "")
            if d and d<asof and (best is None or d>best[0]):
                best=(d,p,j)
        except Exception:
            continue
    return best

def cik_from_prior_row(row:dict):
    row=row or {}
    raw=row.get("cik")
    if raw is not None:
        try:
            return int(str(raw).strip())
        except Exception:
            pass
    url=str(row.get("source_url") or "")
    for pat in (r"/data/(\d+)/",r"[?&]CIK=(\d+)",r"cik=(\d+)"):
        m=re.search(pat,url,re.I)
        if m:
            return int(m.group(1))
    return None

def file_blob_sha(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def manual_identity_seed_registry(asof:str,names:dict)->tuple[dict,dict]:
    """Read bounded official-SEC seed evidence; seed data never creates alpha PASS."""
    if not MANUAL_IDENTITY_SEED.exists():
        return {},{
          "path":str(MANUAL_IDENTITY_SEED.relative_to(ROOT.parent)).replace("\\","/"),
          "blob_sha":None,"record_count":0,
        }
    j=json.loads(MANUAL_IDENTITY_SEED.read_text(encoding="utf-8"))
    assert j.get("schema")=="XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1"
    assert j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
    assert j.get("unknown_never_pass") is True
    assert j.get("authority")=="OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY"
    rows={}
    for sym,row in sorted((j.get("records") or {}).items()):
        sym=str(sym).upper().strip()
        if sym not in names or not isinstance(row,dict):
            continue
        current_name=str(names.get(sym) or "").strip()
        if not current_name or not SPAC_SUSPECT_RE.search(current_name):
            continue
        source=str(row.get("source_url") or "")
        evidence=str(row.get("evidence_date") or "")
        cik=str(row.get("cik") or "").strip()
        try:sic=int(row.get("sic"))
        except Exception:continue
        is_blank=row.get("is_blank_check")
        if (
          not source.startswith("https://www.sec.gov/")
          or not sec_source_binds_cik(source,cik)
          or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence)
          or evidence>asof
          or not re.fullmatch(r"\d{10}",cik)
          or not isinstance(is_blank,bool)
          or (is_blank and sic!=6770)
          or ((not is_blank) and sic==6770)
        ):
            continue
        try:
            age=(datetime.fromisoformat(asof)-datetime.fromisoformat(evidence)).days
        except Exception:
            continue
        if age<0 or age>120:
            continue
        out=dict(row)
        out["cik"]=cik
        out["sic"]=sic
        out["is_blank_check"]=is_blank
        out["same_asof_nasdaq_security_name"]=current_name
        out["manual_seed_registry_path"]=str(MANUAL_IDENTITY_SEED.relative_to(ROOT.parent)).replace("\\","/")
        out["manual_seed_registry_blob_sha"]=file_blob_sha(MANUAL_IDENTITY_SEED)
        out["seed_semantics"]="OFFICIAL_SEC_STATIC_EVIDENCE_PLUS_EXACT_ASOF_NASDAQ_IDENTITY;NO_ALPHA_PASS"
        rows[sym]=out
    meta={
      "path":str(MANUAL_IDENTITY_SEED.relative_to(ROOT.parent)).replace("\\","/"),
      "blob_sha":file_blob_sha(MANUAL_IDENTITY_SEED),
      "record_count":len(rows),
    }
    return rows,meta

def latest_filing_date(sub:dict,asof:str):
    """Return a SEC filing date only if accepted by same-ASOF RTH close."""
    from datetime import date
    recent=((sub.get("filings") or {}).get("recent") or {})
    days=recent.get("filingDate") or []
    accepted=recent.get("acceptanceDateTime") or []
    if not days or len(days)!=len(accepted):
        return None
    try:
        asof_day=date.fromisoformat(asof)
        cutoff=datetime.combine(asof_day,clocktime(16,0),
                 tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    except (ValueError,TypeError):
        return None
    valid=[]
    for day,stamp in zip(days,accepted):
        try:
            d=date.fromisoformat(str(day))
            t=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
            if t.tzinfo is None:continue
            if d<=asof_day and t.astimezone(timezone.utc)<=cutoff:
                valid.append(d.isoformat())
        except (ValueError,TypeError):continue
    return max(valid) if valid else None


def sec_entity_landing_row(sym:str,asof:str,cik:int|None,want_blank:bool,prior_evidence_date:str|None):
    if cik is None:
        return None
    evidence=str(prior_evidence_date or "")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return None
    url=f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}&owner=exclude"
    raw=request_bytes(url,SEC_UA,35).decode("utf-8","ignore")
    text=html.unescape(re.sub(r"<[^>]+>"," ",raw))
    text=re.sub(r"\s+"," ",text)
    upper=text.upper()
    if f"{int(cik):010d}" not in text and str(int(cik)) not in text:
        return None
    if re.search(rf"(?<![A-Z0-9]){re.escape(str(sym).upper())}(?![A-Z0-9])",upper) is None:
        return None
    m=re.search(r"SIC\s*:\s*(?:\([^)]*\)\s*)?(\d{4})\s*[-–]?\s*([^<]{0,80})",text,re.I)
    if m:
        sic=int(m.group(1))
        desc=m.group(2).strip()
    else:
        sic=6770 if re.search(r"6770\s*[-–]\s*Blank Checks",text,re.I) else -1
        desc="Blank Checks" if sic==6770 else ""
    if sic<=0 or (desc and (desc.casefold().startswith("blank checks") != (sic==6770))):
        return None
    is_blank=(sic==6770)
    if bool(want_blank)!=bool(is_blank):
        return None
    return {
      "cik":f"{int(cik):010d}",
      "sic":sic,
      "classification":"Blank Checks" if want_blank else desc,
      "source_url":url,
      "evidence_date":evidence,
      "same_asof_revalidated_without_sec_network":False,
      "same_asof_sec_entity_landing_revalidated":True,
      "revalidation_transport":"SEC_EDGAR_ENTITY_LANDING",
      "revalidation_asof_et":asof,
    }

def sec_current_row(sym:str,asof:str,cik:int|None,want_blank:bool,prior_evidence_date:str|None=None):
    if cik is None:
        return None
    try:
        sub=load_json_url(f"{SEC_SUBMISSIONS}/CIK{cik:010d}.json")
    except Exception:
        return sec_entity_landing_row(sym,asof,cik,want_blank,prior_evidence_date)
    tickers=[str(x).strip().upper() for x in (sub.get("tickers") or [])]
    if sym not in tickers:
        return None
    official=official_sec_sic(sub)
    if official is None:
        return None
    sic,desc=official
    is_blank=(sic==6770)
    if bool(want_blank)!=bool(is_blank):
        return None
    evidence=latest_filing_date(sub,asof)
    if not evidence:
        return None
    return {
      "cik":f"{cik:010d}",
      "sic":sic,
      "classification":"Blank Checks" if want_blank else desc,
      "source_url":f"https://www.sec.gov/edgar/browse/?CIK={cik}",
      "evidence_date":evidence,
    }

def validate_existing_identity(path:Path,asof:str)->bool:
    try:
        j=json.loads(path.read_text(encoding="utf-8"))
        return bool(
          j.get("schema")=="XRAY_MASTER_ASOF_IDENTITY_PROOF_V1"
          and j.get("asof_et")==asof
          and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
          and j.get("unknown_never_pass") is True
          and j.get("authority")=="NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION"
          and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
          and j.get("discovery_version")==IDENTITY_DISCOVERY_VERSION
          and all(isinstance(j.get(k) or {},dict) for k in ("restore_to_asof","remove_from_asof","operating_overrides"))
        )
    except Exception:
        return False

def valid_sec_spac_proof_row(v:dict,asof:str)->bool:
    if not isinstance(v,dict) or int(v.get("sic",-1))!=6770:
        return False
    if v.get("same_asof_revalidated_without_sec_network") is not True:
        return True
    semantics=str(v.get("revalidation_semantics") or "")
    allowed={
      "PRIOR_SEC_SIC6770_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS",
      "MANUAL_OFFICIAL_SEC_EVIDENCE_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS",
    }
    if semantics not in allowed:
        return False
    if semantics.startswith("MANUAL_OFFICIAL_SEC_"):
        expected_path=str(MANUAL_IDENTITY_SEED.relative_to(ROOT.parent)).replace("\\","/")
        if (
          v.get("manual_seed_registry_path")!=expected_path
          or not MANUAL_IDENTITY_SEED.exists()
          or v.get("manual_seed_registry_blob_sha")!=file_blob_sha(MANUAL_IDENTITY_SEED)
        ):
            return False
    source=str(v.get("source_url") or "")
    evidence=str(v.get("evidence_date") or "")
    footer=str(v.get("same_asof_nasdaq_directory_footer") or "")
    if not source.startswith("https://www.sec.gov/"):
        return False
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return False
    try:
        age=(datetime.fromisoformat(asof)-datetime.fromisoformat(evidence)).days
        if age<0 or age>120 or parse_footer_date(footer)!=asof:
            return False
    except Exception:
        return False
    current_name=str(v.get("same_asof_nasdaq_security_name") or "")
    industry=str(v.get("same_asof_nasdaq_screener_industry") or "")
    same_asof_spac=bool(SPAC_SUSPECT_RE.search(current_name))
    same_asof_blank=(industry.strip().lower()=="blank checks")
    return bool(same_asof_spac or same_asof_blank)

def validate_existing_sec(path:Path,asof:str)->bool:
    try:
        j=json.loads(path.read_text(encoding="utf-8"))
        proofs=j.get("proofs") or {}
        return bool(
          j.get("schema")=="XRAY_MASTER_SEC_SPAC_PROOF_V1"
          and j.get("asof_et")==asof
          and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
          and j.get("unknown_never_pass") is True
          and j.get("authority")=="SEC_EDGAR_SIC_6770_EXACT_ASOF"
          and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
          and isinstance(proofs,dict)
          and all(valid_sec_spac_proof_row(v,asof) for v in proofs.values())
        )
    except Exception:
        return False

def sec_discovery_coverage_complete(sec_path:Path,asof:str)->bool:
    """Structural proof validity is not the same as current-suspect coverage."""
    try:
        j=json.loads(sec_path.read_text(encoding="utf-8"))
        cov=j.get("discovery_coverage") or {}
        unresolved=sorted(set(cov.get("unresolved_current_suspects") or []))
        _,seed_meta=manual_identity_seed_registry(asof,{})
        # With names={} the loader intentionally returns no usable rows, but the
        # blob/path binding remains exact-current and invalidates stale NOOP state.
        current_seed_blob=(file_blob_sha(MANUAL_IDENTITY_SEED) if MANUAL_IDENTITY_SEED.exists() else None)
        current_seed_path=str(MANUAL_IDENTITY_SEED.relative_to(ROOT.parent)).replace("\\","/")
        return bool(
          j.get("asof_et")==asof
          and j.get("discovery_version")==IDENTITY_DISCOVERY_VERSION
          and cov.get("manual_seed_registry_path")==current_seed_path
          and cov.get("manual_seed_registry_blob_sha")==current_seed_blob
          and cov.get("coverage_complete") is True
          and int(cov.get("unresolved_current_suspect_count",-1))==0
          and not unresolved
        )
    except Exception:
        return False

def exact_proofs_complete(identity_path,sec_path,asof):
    """NOOP requires valid artifacts AND complete current-suspect discovery coverage."""
    return bool(
        validate_existing_identity(identity_path,asof)
        and sec_path.exists()
        and validate_existing_sec(sec_path,asof)
        and sec_discovery_coverage_complete(sec_path,asof)
    )

def frozen_exact_asof_directory(asof,root=ROOT):
    """Rehydrate an already-committed exact-ASOF Nasdaq identity snapshot.

    Prefer an immutable membership-only snapshot when present. It is sourced
    from an exact historical Nasdaq directory and carries no PASS/UNKNOWN
    classification decisions. Then fall back to canonical/support-plane state
    only when those artifacts are independently exact for the requested ASOF.
    Never use a later live directory as historical membership authority.
    """
    stamp=asof.replace("-","")
    snapshot_path=root/f"master_nasdaq_directory_snapshot_{stamp}.json"
    if snapshot_path.exists():
        try:
            snap=json.loads(snapshot_path.read_text(encoding="utf-8"))
            footer=str(snap.get("source_directory_footer") or "")
            names={str(k).upper():str(v) for k,v in (snap.get("security_names") or {}).items() if str(k).strip() and str(v).strip()}
            industries={str(k).upper():str(v).strip() for k,v in (snap.get("industries") or {}).items() if str(k).strip() and str(v).strip()}
            if (
              snap.get("schema")==DIRECTORY_SNAPSHOT_SCHEMA
              and snap.get("asof_et")==asof
              and snap.get("source_directory_date")==asof
              and parse_footer_date(footer)==asof
              and snap.get("membership_only") is True
              and snap.get("identity_decisions_reused") is False
              and snap.get("source_queue_classification_ignored") is True
              and int(snap.get("membership_count",-1))==len(names)
              and len(names)>0
              and set(industries)<=set(names)
            ):
                return names,industries,footer
        except Exception:
            pass

    candidates=[
      (root/"canonical_current_full_state.json",root/"canonical_current_master_manifest.json"),
      (root/"sina_state.json",None),
    ]
    for full_path,manifest_path in candidates:
        if not full_path.exists():
            continue
        try:
            full=json.loads(full_path.read_text(encoding="utf-8"))
            manifest=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path and manifest_path.exists() else {}
            if full.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2" or full.get("asof_et")!=asof:
                continue
            if manifest and manifest.get("asof_et")!=asof:
                continue
            footer=str((manifest or {}).get("official_footer") or full.get("official_footer") or "")
            if parse_footer_date(footer)!=asof:
                continue
            q=list(full.get("queue") or [])
            unknown=sorted(set(full.get("identity_unknown_symbols") or []))
            detail=(manifest or {}).get("unknown_detail") or full.get("identity_unknown_detail") or {}
            raw=int(full.get("raw_identity_total",-1))
            qhash=hashlib.sha256("\n".join(q).encode()).hexdigest()
            dm=full.get("discovery_meta") or {}
            if (
              full.get("identity_ruleset")!="V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER"
              or full.get("identity_partition_policy")!="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"
              or dm.get("identity_partition_policy")!="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"
              or int(full.get("queue_total",-1))!=len(q)
              or len(q)!=len(set(q))
              or full.get("queue_hash")!=qhash
              or raw!=len(q)+len(unknown)
              or set(detail)!=set(unknown)
              or bool(set(q)&set(unknown))
            ):
                continue
            names={str(k).upper():str(v) for k,v in (full.get("security_names") or {}).items() if str(k).strip() and str(v).strip()}
            industries={}
            for sym,row in detail.items():
                sym=str(sym).upper()
                name=str((row or {}).get("security_name") or "").strip()
                if name:
                    names[sym]=name
                industry=str((row or {}).get("same_asof_nasdaq_industry") or (row or {}).get("same_asof_nasdaq_screener_industry") or "").strip()
                if industry:
                    industries[sym]=industry
            if not names:
                continue
            return names,industries,footer
        except Exception:
            continue
    return None

def main():
    asof=completed_asof()
    identity_path,sec_path=proof_paths(asof)
    if exact_proofs_complete(identity_path,sec_path,asof):
        print(json.dumps({"result":"NOOP_EXACT_PROOFS_ALREADY_VALID","asof_et":asof,"identity_path":identity_path.name,"sec_path":sec_path.name},sort_keys=True))
        return

    live_names,live_footer=official_directory()
    live_footer_date=parse_footer_date(live_footer)
    directory_replay_mode=False
    if live_footer_date==asof:
        names=live_names
        footer=live_footer
        footer_date=live_footer_date
        industries=official_screener_industries()
    else:
        frozen=frozen_exact_asof_directory(asof)
        if frozen is None:
            raise RuntimeError(f"NASDAQ_DIRECTORY_NOT_EXACT_ASOF:{live_footer_date}!={asof}")
        names,industries,footer=frozen
        footer_date=asof
        directory_replay_mode=True

    prior_identity=latest_prior("master_asof_identity_proof_",asof)
    prior_sec=latest_prior("master_sec_spac_proof_",asof)
    operating_seed={}
    if prior_identity:
        operating_seed=dict(prior_identity[2].get("operating_overrides") or {})
    blank_seed={}
    if prior_sec:
        blank_seed=dict(prior_sec[2].get("proofs") or {})

    sec_network_error=None
    sec_discovery_errors={}
    operating={}
    current_suspect_set=set(current_spac_suspects(names,industries))
    nonblank_pending_completion=set()
    for sym,old in sorted(operating_seed.items()):
        if sym not in names:
            continue
        # SEC SIC may be changed to target sector before the SPAC closes.
        # Same-ASOF issuer-name suspicion + nonblank SIC != consummation.
        if sym in current_suspect_set and nonblank_requires_completion(True, (old or {}).get('sic')):
            nonblank_pending_completion.add(sym)
            continue
        cik=cik_from_prior_row(old)
        try:
            row=sec_current_row(sym,asof,cik,False,str((old or {}).get("evidence_date") or ""))
        except Exception as e:
            row=None
            sec_network_error=f"{type(e).__name__}:{str(e)[:200]}"
        if row is not None:
            operating[sym]={
              "security_name":names[sym],
              "evidence_date":row["evidence_date"],
              "reason":"SAME_RUN_SEC_CURRENT_NON_BLANK_CHECK_REVALIDATION",
              "source_url":row["source_url"],
              "cik":row["cik"],
              "sic":row["sic"],
              "same_asof_revalidated_without_sec_network":False,
            }
            continue
        fallback=prior_operating_fallback(sym,old,asof,names,industries)
        if fallback is None:
            raise RuntimeError("OPERATING_OVERRIDE_REVALIDATION_FAILED:"+sym)
        operating[sym]=fallback

    # V4 coverage repair: an exact-ASOF proof artifact can be structurally valid
    # while covering only a subset of current SPAC suspects.  V4 deliberately
    # re-enters current suspects through SEC discovery instead of treating the
    # mere existence of a valid proof file as complete coverage. UNKNOWN remains
    # UNKNOWN on transport/evidence failure; this can never create alpha PASS.
    # Discover CURRENT same-ASOF SPAC suspects, not only prior-day proof seeds.
    # This closes the seed=0 deadlock while remaining fail-closed: only SEC
    # submissions with the same ticker and a filing date <= ASOF can classify.
    discovered_blank={}
    unresolved_current_suspects=[]
    try:
        # Exact-ASOF suspect scope; the mirror is never a whole-market
        # membership source or a path that can generate classification PASS.
        current_cik_map=sec_ticker_cik_map(asof,current_spac_suspects(names,industries))
    except Exception as e:
        current_cik_map={}
        sec_network_error=sec_network_error or f"{type(e).__name__}:{str(e)[:200]}"
    current_suspects=current_spac_suspects(names,industries)
    manual_seeds,manual_seed_meta=manual_identity_seed_registry(asof,names)
    sec_submissions_blocked_code=None
    sec_submissions_blocked_at=None
    sec_submissions_skipped=0
    for sym in current_suspects:
        if sym in operating:
            continue
        manual=manual_seeds.get(sym)
        if manual is not None:
            if manual.get("is_blank_check") is True:
                discovered_blank[sym]={
                  "cik":manual["cik"],
                  "sic":manual["sic"],
                  "classification":str(manual.get("classification") or "Blank Checks"),
                  "source_url":manual["source_url"],
                  "evidence_date":manual["evidence_date"],
                  "same_asof_revalidated_without_sec_network":True,
                  "revalidation_semantics":"MANUAL_OFFICIAL_SEC_EVIDENCE_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS",
                  "same_asof_nasdaq_security_name":manual["same_asof_nasdaq_security_name"],
                  "same_asof_nasdaq_screener_industry":str(industries.get(sym) or ""),
                  "same_asof_nasdaq_directory_footer":footer,
                  "manual_seed_registry_path":manual["manual_seed_registry_path"],
                  "manual_seed_registry_blob_sha":manual["manual_seed_registry_blob_sha"],
                }
            else:
                if nonblank_requires_completion(True, manual.get('sic')):
                    unresolved_current_suspects.append(sym)
                    nonblank_pending_completion.add(sym)
                    continue
                operating[sym]={
                  "security_name":names[sym],
                  "evidence_date":manual["evidence_date"],
                  "reason":"SAME_ASOF_OFFICIAL_SEC_MANUAL_SEED_NON_BLANK_CHECK",
                  "source_url":manual["source_url"],
                  "cik":manual["cik"],
                  "sic":manual["sic"],
                  "classification":manual.get("classification"),
                  "same_asof_revalidated_without_sec_network":True,
                  "revalidation_semantics":"MANUAL_OFFICIAL_SEC_NONBLANK_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_IDENTITY;NO_ALPHA_PASS",
                  "manual_seed_registry_path":manual["manual_seed_registry_path"],
                  "manual_seed_registry_blob_sha":manual["manual_seed_registry_blob_sha"],
                  "discovery_version":IDENTITY_DISCOVERY_VERSION,
                }
            continue
        if sec_submissions_blocked_code is not None:
            # One SEC HTTP 403/429 must not trigger hundreds of duplicate
            # requests or cross-symbol guessed SIC conclusions.
            unresolved_current_suspects.append(sym)
            sec_submissions_skipped+=1
            continue
        cik=current_cik_map.get(sym)
        if cik is None:
            unresolved_current_suspects.append(sym)
            continue
        try:
            row=sec_current_classification(sym,asof,cik)
        except Exception as e:
            if sec_submissions_transport_is_blocked(e):
                sec_submissions_blocked_code=int(e.code)
                sec_submissions_blocked_at=sym
            row=None
            sec_discovery_errors[sym]=f"{type(e).__name__}:{str(e)[:160]}"
            sec_network_error=sec_network_error or sec_discovery_errors[sym]
        if row is None:
            unresolved_current_suspects.append(sym)
            continue
        if row.get("is_blank_check") is True:
            discovered_blank[sym]={k:v for k,v in row.items() if k!="is_blank_check"}
        else:
            if nonblank_requires_completion(True, row.get('sic')):
                unresolved_current_suspects.append(sym)
                nonblank_pending_completion.add(sym)
                continue
            operating[sym]={
              "security_name":names[sym],
              "evidence_date":row["evidence_date"],
              "reason":"SAME_RUN_SEC_CURRENT_NON_BLANK_CHECK_DISCOVERY",
              "source_url":row["source_url"],
              "cik":row["cik"],
              "sic":row["sic"],
              "classification":row.get("classification"),
              "same_asof_revalidated_without_sec_network":False,
              "discovery_version":IDENTITY_DISCOVERY_VERSION,
            }

    SEC_CIK_DISCOVERY_DIAGNOSTICS["sec_submissions_blocked_http_code"]=sec_submissions_blocked_code
    SEC_CIK_DISCOVERY_DIAGNOSTICS["sec_submissions_blocked_at"]=sec_submissions_blocked_at
    SEC_CIK_DISCOVERY_DIAGNOSTICS["sec_submissions_skip_count"]=sec_submissions_skipped
    SEC_CIK_DISCOVERY_DIAGNOSTICS["sec_submissions_classification_authority"]=False

    identity={
      "schema":"XRAY_MASTER_ASOF_IDENTITY_PROOF_V1",
      "asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "authority":"NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION",
      "applicability":"EXACT_ASOF_ONLY_NO_FORWARD_CARRY",
      "discovery_version":IDENTITY_DISCOVERY_VERSION,
      "source_directory_footer":footer,
      "source_directory_date":footer_date,
      "same_asof_directory_is_membership_authority":True,
      "directory_replay_mode":"FROZEN_EXACT_ASOF_COMMITTED_SNAPSHOT" if directory_replay_mode else "LIVE_EXACT_ASOF_OFFICIAL_DIRECTORY",
      "live_directory_footer_observed":live_footer if directory_replay_mode else None,
      "restore_to_asof":{},
      "remove_from_asof":{},
      "operating_overrides":operating,
      "manual_seed_registry":manual_seed_meta,
    }
    identity_path.write_text(json.dumps(identity,ensure_ascii=False,sort_keys=False,indent=2)+"\n",encoding="utf-8")

    proofs=dict(discovered_blank)
    unresolved_sec_spac=list(unresolved_current_suspects)
    for sym,old in sorted(blank_seed.items()):
        if sym in proofs or sym in operating:
            continue
        if sym not in names:
            continue
        cik=cik_from_prior_row(old)
        try:
            row=sec_current_row(sym,asof,cik,True,str((old or {}).get("evidence_date") or ""))
        except Exception as e:
            row=None
            sec_network_error=sec_network_error or f"{type(e).__name__}:{str(e)[:200]}"
        if row is not None:
            row["same_asof_revalidated_without_sec_network"]=False
            proofs[sym]=row
            continue
        # SEC transport may be unavailable on shared CI IPs. Reuse only the
        # prior SEC SIC 6770 evidence (<=120d) when the exact-ASOF Nasdaq
        # directory still independently identifies the same ticker as a SPAC.
        # This is exclusion-only evidence; it can never create alpha PASS.
        fallback=prior_blank_fallback(sym,old,asof,names,industries)
        if fallback is not None:
            fallback["same_asof_nasdaq_directory_footer"]=footer
            proofs[sym]=fallback
            continue
        unresolved_sec_spac.append(sym)
    unresolved_sec_spac=sorted(set(unresolved_sec_spac)-set(proofs))
    if proofs:
        sec={
          "schema":"XRAY_MASTER_SEC_SPAC_PROOF_V1",
          "asof_et":asof,
          "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
          "authority":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
          "applicability":"EXACT_ASOF_ONLY_NO_FORWARD_CARRY",
          "discovery_version":IDENTITY_DISCOVERY_VERSION,
          "discovery_coverage":{
            "manual_seed_registry_path":manual_seed_meta["path"],
            "manual_seed_registry_blob_sha":manual_seed_meta["blob_sha"],
            "manual_seed_registry_record_count":manual_seed_meta["record_count"],
            "sec_cik_routing":dict(SEC_CIK_DISCOVERY_DIAGNOSTICS),
            "current_suspect_count":len(current_suspects),
            "resolved_current_suspect_count":len(current_suspects)-len(unresolved_sec_spac),
            "unresolved_current_suspect_count":len(unresolved_sec_spac),
            "unresolved_current_suspects":unresolved_sec_spac,
            "nonblank_sic_without_completed_merger_proof":sorted(nonblank_pending_completion),
            "nonblank_sic_is_not_merger_completion":True,
            "coverage_complete":len(unresolved_sec_spac)==0,
            "sec_transport_error":sec_network_error,
            "fail_closed":True,
          },
          "proofs":proofs,
        }
        sec_path.write_text(json.dumps(sec,ensure_ascii=False,sort_keys=False,indent=2)+"\n",encoding="utf-8")
    elif sec_path.exists():
        sec_path.unlink()

    assert validate_existing_identity(identity_path,asof)
    if proofs:
        assert validate_existing_sec(sec_path,asof)
    print(json.dumps({
      "result":"PASS",
      "asof_et":asof,
      "directory_footer":footer,
      "identity_path":identity_path.name,
      "operating_override_count":len(operating),
      "manual_seed_registry_record_count":manual_seed_meta["record_count"],
      "manual_seed_registry_blob_sha":manual_seed_meta["blob_sha"],
      "sec_path":sec_path.name if proofs else None,
      "sec_spac_count":len(proofs),
      "sec_spac_discovered_current_count":len(discovered_blank),
      "operating_discovered_current_count":sum(1 for v in operating.values() if (v or {}).get("reason")=="SAME_RUN_SEC_CURRENT_NON_BLANK_CHECK_DISCOVERY"),
      "current_suspect_count":len(current_suspects),
      "sec_spac_unresolved_reentered_queue":sorted(set(unresolved_sec_spac)),
      "sec_discovery_coverage_complete":len(unresolved_sec_spac)==0,
      "sec_discovery_error_count":len(sec_discovery_errors),
      "forward_carry":False,
      "sec_network_error":sec_network_error,
      "same_asof_nasdaq_screener_fallback_used":bool(sec_network_error),
    },sort_keys=True))

if __name__=="__main__":
    main()
