#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
NASDAQ_DIR="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER="https://api.nasdaq.com/api/screener/stocks"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS="https://data.sec.gov/submissions"
SEC_UA=os.getenv("XRAY_SEC_USER_AGENT","NASDAQ-SWING-XRAY research bot; xray-dataplane-bot@users.noreply.github.com")
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TASK="6a825366222081918997094d76e6ae46"
IDENTITY_DISCOVERY_VERSION="SEC_CURRENT_SUSPECT_DISCOVERY_V3"
SPAC_SUSPECT_RE=re.compile(r"\bacquisition\b|\bspac\b|\bblank[ -]?check\b|\bcapital\s+corp(?:oration)?\.?\s+(?:[IVXLCDM]+|\d+)\s*-\s*class\s+a\s+ordinary\s+shares?\b",re.I)
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

def sec_ticker_cik_map():
    """Current SEC ticker->CIK discovery; evidence routing only, never alpha authority."""
    raw=load_json_url(SEC_TICKERS)
    rows=raw.values() if isinstance(raw,dict) else raw
    out={}
    for row in rows or []:
        if not isinstance(row,dict):continue
        sym=str(row.get("ticker") or "").strip().upper()
        try:cik=int(row.get("cik_str"))
        except Exception:continue
        if sym and cik>0:out[sym]=cik
    return out

def sec_current_classification(sym:str,asof:str,cik:int|None):
    """One same-run SEC submissions read returning blank/nonblank classification."""
    if cik is None:return None
    sub=load_json_url(f"{SEC_SUBMISSIONS}/CIK{int(cik):010d}.json")
    tickers=[str(x).strip().upper() for x in (sub.get("tickers") or [])]
    if str(sym).upper() not in tickers:return None
    try:sic=int(str(sub.get("sic") or "-1").strip())
    except Exception:sic=-1
    desc=str(sub.get("sicDescription") or "").strip()
    evidence=latest_filing_date(sub,asof)
    if not evidence:return None
    is_blank=(sic==6770 or desc.lower()=="blank checks")
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

def latest_filing_date(sub:dict,asof:str):
    recent=((sub.get("filings") or {}).get("recent") or {})
    dates=[str(x) for x in (recent.get("filingDate") or []) if str(x)<=asof and re.fullmatch(r"20\d{2}-\d{2}-\d{2}",str(x))]
    return max(dates) if dates else None

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
    is_blank=(sic==6770 or desc.lower().startswith("blank checks"))
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
    try:
        sic=int(str(sub.get("sic") or "-1").strip())
    except Exception:
        sic=-1
    desc=str(sub.get("sicDescription") or "").strip()
    is_blank=(sic==6770 or desc.lower()=="blank checks")
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
    if v.get("revalidation_semantics")!="PRIOR_SEC_SIC6770_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS":
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

def exact_proofs_complete(identity_path,sec_path,asof):
    """NOOP is legal only when BOTH exact-ASOF proof artifacts exist and validate."""
    return bool(
        validate_existing_identity(identity_path,asof)
        and sec_path.exists()
        and validate_existing_sec(sec_path,asof)
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
    for sym,old in sorted(operating_seed.items()):
        if sym not in names:
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

    # Discover CURRENT same-ASOF SPAC suspects, not only prior-day proof seeds.
    # This closes the seed=0 deadlock while remaining fail-closed: only SEC
    # submissions with the same ticker and a filing date <= ASOF can classify.
    discovered_blank={}
    unresolved_current_suspects=[]
    try:
        current_cik_map=sec_ticker_cik_map()
    except Exception as e:
        current_cik_map={}
        sec_network_error=sec_network_error or f"{type(e).__name__}:{str(e)[:200]}"
    current_suspects=sorted(
      sym for sym,name in names.items()
      if str(industries.get(sym) or "").strip().lower()!="blank checks"
      and bool(SPAC_SUSPECT_RE.search(str(name or "")))
    )
    for sym in current_suspects:
        if sym in operating:
            continue
        cik=current_cik_map.get(sym)
        if cik is None:
            unresolved_current_suspects.append(sym)
            continue
        try:
            row=sec_current_classification(sym,asof,cik)
        except Exception as e:
            row=None
            sec_discovery_errors[sym]=f"{type(e).__name__}:{str(e)[:160]}"
            sec_network_error=sec_network_error or sec_discovery_errors[sym]
        if row is None:
            unresolved_current_suspects.append(sym)
            continue
        if row.get("is_blank_check") is True:
            discovered_blank[sym]={k:v for k,v in row.items() if k!="is_blank_check"}
        else:
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
      "sec_path":sec_path.name if proofs else None,
      "sec_spac_count":len(proofs),
      "sec_spac_discovered_current_count":len(discovered_blank),
      "operating_discovered_current_count":sum(1 for v in operating.values() if (v or {}).get("reason")=="SAME_RUN_SEC_CURRENT_NON_BLANK_CHECK_DISCOVERY"),
      "current_suspect_count":len(current_suspects),
      "sec_spac_unresolved_reentered_queue":sorted(set(unresolved_sec_spac)),
      "sec_discovery_error_count":len(sec_discovery_errors),
      "forward_carry":False,
      "sec_network_error":sec_network_error,
      "same_asof_nasdaq_screener_fallback_used":bool(sec_network_error),
    },sort_keys=True))

if __name__=="__main__":
    main()
