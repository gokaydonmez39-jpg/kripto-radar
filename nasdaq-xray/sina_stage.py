#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external hard-gate accelerator V2.
Identity: fresh NasdaqTrader directory.
Canonical FULL_IDENTITY mode does not call Nasdaq web screener endpoints and
defers all market gates to PRICE/DV30. Legacy non-full discovery mode may retain
the old screener helper but is not used by the canonical pre-MC workflow.
History accelerator: Sina US daily history.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
No external source here is G9 authority or a substitute for canonical MC authority.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import pandas_market_calendars as mcal

TASK_ID="6a825366222081918997094d76e6ae46"
BUILD="2026-10-02.1"
IDENTITY_RULESET="V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER"
IDENTITY_PARTITION_POLICY="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD"
DIRECTORY_SNAPSHOT_SCHEMA="XRAY_NASDAQ_DIRECTORY_SNAPSHOT_V1"
NASDAQ_DIR="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER="https://api.nasdaq.com/api/screener/stocks"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS="https://data.sec.gov/submissions"
SEC_UA=os.getenv("XRAY_SEC_USER_AGENT","NASDAQ-SWING-XRAY research bot; xray-dataplane-bot@users.noreply.github.com")
SPAC_SUSPECT=re.compile(r"\bacquisition\b|\bspac\b|\bblank[ -]?check\b|\bcapital\s+corp(?:oration)?\.?\s+(?:[IVXLCDM]+|\d+)\s*-\s*class\s+a\s+ordinary\s+shares?\b",re.I)
FOOTER_RE=re.compile(r"^File Creation Time:\s*(\d{2})(\d{2})(\d{4})")
_SEC_TICKER_CACHE=None
_SEC_SPAC_CACHE={}
ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("XRAY_SINA_STATE", str(ROOT/"sina_state.json")))
CAND=Path(os.getenv("XRAY_SINA_CAND", str(ROOT/"sina_candidates.json")))
RESOLUTION_OVERLAY=Path(os.getenv("XRAY_HISTORY_RESOLUTION_OVERLAY", str(ROOT/"history_resolution_overlay.json")))
FULL_IDENTITY=os.getenv("XRAY_FULL_IDENTITY","0")=="1"
IDENTITY_ONLY=os.getenv("XRAY_IDENTITY_ONLY","0")=="1"

BATCH=int(os.getenv("XRAY_SINA_HISTORY_BATCH","100"))
RETRY_BATCH=int(os.getenv("XRAY_SINA_RETRY_BATCH","20"))
WORKERS=int(os.getenv("XRAY_SINA_HISTORY_WORKERS","8"))
MAX_ATTEMPTS=int(os.getenv("XRAY_SINA_MAX_ATTEMPTS","4"))

# Discovery may be equal to or wider than canonical gates, never stricter.
# Current canonical price floor is >=$5; recovery/discovery must not pre-drop eligible names.
DISCOVERY_PRICE_FLOOR=5.0
DISCOVERY_MC_FLOOR=1_800_000_000.0
HARD_PRICE=5.0
HARD_DV30=50_000_000.0
HARD_HISTORY=260

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

TYPE_PATTERNS=[
 ("WARRANT",re.compile(r"\bwarrants?\b",re.I)),
 ("RIGHT",re.compile(r"\brights?\b",re.I)),
 ("UNIT",re.compile(r"\bunits?\b",re.I)),
 ("PREFERRED",re.compile(r"\bpreferred\b|\bpreference\b",re.I)),
 ("DEBT",re.compile(r"\bsenior notes?\b|\bsubordinated notes?\b|\bnotes? due\b|\bdebentures?\b|\bbonds?\b",re.I)),
 ("ETN",re.compile(r"\betn\b|exchange[- ]traded notes?",re.I)),
 ("FUND",re.compile(r"\bfund\b",re.I)),
 ("WHEN_ISSUED",re.compile(r"\bwhen[- ]issued\b",re.I)),
]

def sha_lines(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()

def git_blob_sha(path):
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def sec_spac_proof_path(asof):
    return ROOT/f"master_sec_spac_proof_{str(asof).replace('-','')}.json"

def asof_identity_proof_path(asof):
    return ROOT/f"master_asof_identity_proof_{str(asof).replace('-','')}.json"

def load_sec_spac_proof(asof):
    proof_path=sec_spac_proof_path(asof)
    if not proof_path.exists():
        return {},None
    j=json.loads(proof_path.read_text(encoding="utf-8"))
    if str(j.get("asof_et") or "")!=asof:
        return {},None
    if not (
      j.get("schema")=="XRAY_MASTER_SEC_SPAC_PROOF_V1"
      and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
      and j.get("unknown_never_pass") is True
      and j.get("authority")=="SEC_EDGAR_SIC_6770_EXACT_ASOF"
      and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
    ):
        raise RuntimeError("SEC_SPAC_PROOF_HEADER_INVALID")
    proofs=j.get("proofs") or {}
    if not isinstance(proofs,dict):
        raise RuntimeError("SEC_SPAC_PROOF_BODY_INVALID")
    out={}
    for sym,row in proofs.items():
        sym=str(sym or "").strip().upper()
        if not sym or not isinstance(row,dict):
            raise RuntimeError("SEC_SPAC_PROOF_ROW_INVALID")
        if (
          int(row.get("sic",-1))!=6770
          or str(row.get("classification") or "")!="Blank Checks"
          or not re.fullmatch(r"0[0-9]{9}",str(row.get("cik") or ""))
          or not str(row.get("source_url") or "").startswith("https://www.sec.gov/")
          or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",str(row.get("evidence_date") or ""))
          or str(row.get("evidence_date"))>asof
        ):
            raise RuntimeError("SEC_SPAC_PROOF_ROW_INVALID:"+sym)
        if row.get("same_asof_revalidated_without_sec_network") is True:
            if row.get("revalidation_semantics")!="PRIOR_SEC_SIC6770_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS":
                raise RuntimeError("SEC_SPAC_PROOF_FALLBACK_SEMANTICS_INVALID:"+sym)
            try:
                age=(datetime.fromisoformat(asof)-datetime.fromisoformat(str(row.get("evidence_date")))).days
            except Exception:
                raise RuntimeError("SEC_SPAC_PROOF_FALLBACK_EVIDENCE_DATE_INVALID:"+sym)
            if age<0 or age>120:
                raise RuntimeError("SEC_SPAC_PROOF_FALLBACK_STALE:"+sym)
            footer=str(row.get("same_asof_nasdaq_directory_footer") or "")
            fm=re.match(r"^File Creation Time:\s*(\d{2})(\d{2})(\d{4})",footer)
            if not fm or f"{fm.group(3)}-{fm.group(1)}-{fm.group(2)}"!=asof:
                raise RuntimeError("SEC_SPAC_PROOF_FALLBACK_DIRECTORY_ASOF_INVALID:"+sym)
            current_name=str(row.get("same_asof_nasdaq_security_name") or "")
            industry=str(row.get("same_asof_nasdaq_screener_industry") or "")
            if not (
              SPAC_SUSPECT.search(current_name)
              or industry.strip().lower()=="blank checks"
            ):
                raise RuntimeError("SEC_SPAC_PROOF_FALLBACK_NASDAQ_IDENTITY_INVALID:"+sym)
        out[sym]=row
    return out,git_blob_sha(proof_path)


def load_asof_identity_proof(asof):
    proof_path=asof_identity_proof_path(asof)
    if not proof_path.exists():
        return {},None
    j=json.loads(proof_path.read_text(encoding="utf-8"))
    if str(j.get("asof_et") or "")!=asof:
        return {},None
    if not (
      j.get("schema")=="XRAY_MASTER_ASOF_IDENTITY_PROOF_V1"
      and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
      and j.get("unknown_never_pass") is True
      and j.get("authority")=="NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION"
      and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
    ):
        raise RuntimeError("ASOF_IDENTITY_PROOF_HEADER_INVALID")
    restore=j.get("restore_to_asof") or {}
    remove=j.get("remove_from_asof") or {}
    operating=j.get("operating_overrides") or {}
    if not all(isinstance(x,dict) for x in (restore,remove,operating)):
        raise RuntimeError("ASOF_IDENTITY_PROOF_BODY_INVALID")
    groups=[set(restore),set(remove),set(operating)]
    if any(groups[a]&groups[b] for a in range(len(groups)) for b in range(a+1,len(groups))):
        raise RuntimeError("ASOF_IDENTITY_PROOF_OVERLAP")
    for sym,row in restore.items():
        if not isinstance(row,dict) or not row.get("security_name") or str(row.get("effective_date") or "")<=asof:
            raise RuntimeError("ASOF_IDENTITY_RESTORE_INVALID:"+sym)
        if not str(row.get("source_url") or "").startswith("https://www.nasdaqtrader.com/"):
            raise RuntimeError("ASOF_IDENTITY_RESTORE_SOURCE_INVALID:"+sym)
    for sym,row in remove.items():
        if not isinstance(row,dict) or not row.get("security_name") or str(row.get("effective_date") or "")<=asof:
            raise RuntimeError("ASOF_IDENTITY_REMOVE_INVALID:"+sym)
        if not str(row.get("source_url") or "").startswith("https://www.nasdaqtrader.com/"):
            raise RuntimeError("ASOF_IDENTITY_REMOVE_SOURCE_INVALID:"+sym)
    for sym,row in operating.items():
        if not isinstance(row,dict) or not row.get("security_name") or str(row.get("evidence_date") or "")>asof:
            raise RuntimeError("ASOF_IDENTITY_OPERATING_INVALID:"+sym)
        if not str(row.get("source_url") or "").startswith("https://www.sec.gov/"):
            raise RuntimeError("ASOF_IDENTITY_OPERATING_SOURCE_INVALID:"+sym)
    return j,git_blob_sha(proof_path)

def apply_asof_identity_proof(names,excluded,proof):
    names=dict(names);excluded=dict(excluded)
    for sym,row in (proof.get("remove_from_asof") or {}).items():
        names.pop(sym,None)
        excluded[sym]={
          "reason":"POST_ASOF_LISTING","security_name":row["security_name"],
          "source":"NASDAQTRADER_EXACT_EFFECTIVE_DATE","effective_date":row["effective_date"],
          "source_url":row["source_url"],
        }
    for sym,row in (proof.get("restore_to_asof") or {}).items():
        excluded.pop(sym,None)
        names[sym]=row["security_name"]
    return names,excluded

def request_json(url,params=None,headers=None,timeout=45):
    if params:
        url=url+"?"+urllib.parse.urlencode(params)
    h={
      "User-Agent":UA,
      "Accept":"application/json,text/plain,*/*",
    }
    if headers:h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def request_text(url,timeout=35):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def official_footer_date(footer):
    m=FOOTER_RE.match(str(footer or "").strip())
    if not m:
        return None
    mm,dd,yyyy=m.groups()
    return f"{yyyy}-{mm}-{dd}"

def exact_asof_membership_snapshot(asof):
    """Load immutable membership-only Nasdaq snapshot for historical replay.

    This source carries no PASS/UNKNOWN decisions. It may rebuild the identity
    partition under current exact-ASOF proof artifacts without consulting a
    later live Nasdaq directory.
    """
    p=ROOT/f"master_nasdaq_directory_snapshot_{str(asof).replace('-','')}.json"
    if not p.exists():
        return None
    try:
        j=json.loads(p.read_text(encoding="utf-8"))
        names={str(k).strip().upper():str(v).strip() for k,v in (j.get("security_names") or {}).items() if str(k).strip() and str(v).strip()}
        industries={str(k).strip().upper():str(v).strip() for k,v in (j.get("industries") or {}).items() if str(k).strip()}
        footer=str(j.get("source_directory_footer") or "")
        if (
          j.get("schema")!=DIRECTORY_SNAPSHOT_SCHEMA
          or j.get("asof_et")!=asof
          or j.get("execution")!="NONE" or j.get("real_money")!="NO-GO"
          or j.get("unknown_never_pass") is not True
          or j.get("membership_only") is not True
          or j.get("identity_decisions_reused") is not False
          or j.get("source_queue_classification_ignored") is not True
          or j.get("source_directory_date")!=asof
          or official_footer_date(footer)!=asof
          or int(j.get("membership_count",-1))!=len(names)
          or int(j.get("industry_count",-1))!=len(industries)
          or not set(industries)<=set(names)
          or not names
        ):
            return None
        return {
          "security_names":names,
          "industries":industries,
          "official_footer":footer,
          "path":"nasdaq-xray/"+p.name,
          "blob_sha":git_blob_sha(p),
        }
    except Exception:
        return None

def official_nasdaq():
    text=request_text(NASDAQ_DIR)
    lines=[x.strip("\r") for x in text.splitlines() if x.strip()]
    footer=next((x for x in reversed(lines) if x.startswith("File Creation Time:")),None)
    body="\n".join(x for x in lines if not x.startswith("File Creation Time:"))
    rows=list(csv.DictReader(io.StringIO(body),delimiter="|"))
    included={}; excluded={}
    for row in rows:
        sym=(row.get("Symbol") or "").strip().upper()
        name=(row.get("Security Name") or "").strip()
        if not sym:continue
        reason=None
        if row.get("Test Issue")!="N":reason="TEST_ISSUE"
        elif row.get("ETF")=="Y":reason="ETF"
        elif row.get("NextShares")=="Y":reason="NEXTSHARES"
        else:
            for label,pat in TYPE_PATTERNS:
                if pat.search(name):
                    reason=label
                    break
        if reason:excluded[sym]={"reason":reason,"security_name":name}
        else:included[sym]=name
    if not footer or not included:
        raise RuntimeError("NASDAQ_DIRECTORY_INVALID")
    return included,excluded,footer

def sec_blank_check_proof(symbol):
    """Official SEC exclusion-only proof for a suspect blank-check/SPAC name.

    Only SIC 6770 / Blank Checks for the exact ticker can exclude a symbol.
    Any SEC/network/schema ambiguity returns None and therefore remains queued.
    """
    global _SEC_TICKER_CACHE
    sym=str(symbol or "").strip().upper()
    if sym in _SEC_SPAC_CACHE:
        return _SEC_SPAC_CACHE[sym]
    try:
        if _SEC_TICKER_CACHE is None:
            raw=request_json(
              SEC_TICKERS,
              headers={"User-Agent":SEC_UA,"Accept":"application/json"},
              timeout=30,
            )
            idx={}
            for row in (raw or {}).values():
                if not isinstance(row,dict):
                    continue
                ticker=str(row.get("ticker") or "").strip().upper()
                cik=row.get("cik_str")
                if ticker and cik is not None:
                    idx[ticker]=int(cik)
            _SEC_TICKER_CACHE=idx
        cik=(_SEC_TICKER_CACHE or {}).get(sym)
        if cik is None:
            _SEC_SPAC_CACHE[sym]=None
            return None
        sub=request_json(
          f"{SEC_SUBMISSIONS}/CIK{int(cik):010d}.json",
          headers={"User-Agent":SEC_UA,"Accept":"application/json"},
          timeout=30,
        )
        sic=str(sub.get("sic") or "").strip()
        sic_desc=str(sub.get("sicDescription") or "").strip()
        tickers=[str(x).strip().upper() for x in (sub.get("tickers") or [])]
        exchanges=[str(x) for x in (sub.get("exchanges") or [])]
        if sym in tickers and (sic=="6770" or sic_desc.lower()=="blank checks"):
            proof={
              "authority":"SEC_SUBMISSIONS",
              "cik":f"{int(cik):010d}",
              "sic":sic,
              "sic_description":sic_desc,
              "tickers":tickers,
              "exchanges":exchanges,
              "source":f"{SEC_SUBMISSIONS}/CIK{int(cik):010d}.json",
            }
            _SEC_SPAC_CACHE[sym]=proof
            return proof
    except Exception:
        pass
    _SEC_SPAC_CACHE[sym]=None
    return None

def screener_rows():
    obj=request_json(
      NASDAQ_SCREENER,
      {
        "tableonly":"true",
        "limit":"25",
        "offset":"0",
        "exchange":"NASDAQ",
        "download":"true",
      },
      headers={
        "Origin":"https://www.nasdaq.com",
        "Referer":"https://www.nasdaq.com/market-activity/stocks/screener",
      },
      timeout=60,
    )
    data=obj.get("data") or {}
    rows=data.get("rows") or ((data.get("table") or {}).get("rows") or [])
    if len(rows)<1000:
        raise RuntimeError("NASDAQ_SCREENER_TOO_FEW_ROWS")
    return rows

def num(x):
    try:
        if x is None:return None
        s=str(x).replace("$","").replace(",","").strip()
        if not s or s in {"N/A","--"}:return None
        v=float(s)
        return v if math.isfinite(v) else None
    except Exception:
        return None

def build_discovery(official,force_all=False,sec_spac_proof=None,operating_overrides=None):
    rows=screener_rows()
    off=set(official)
    prefilter={}
    screener_excluded={}
    sec_spac_proof=sec_spac_proof or {}
    operating_overrides=operating_overrides or {}
    missing=set(off)
    exact_hard_mc_price_count=0
    for r in rows:
        sym=str(r.get("symbol") or "").strip().upper()
        if sym not in off:continue
        missing.discard(sym)
        if sym in sec_spac_proof and sym not in operating_overrides:
            pr=sec_spac_proof[sym]
            screener_excluded[sym]={
              "reason":"SPAC_BLANK_CHECK",
              "security_name":official.get(sym) or str(r.get("name") or "").strip(),
              "industry":"Blank Checks",
              "source":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
              "cik":pr.get("cik"),
              "source_url":pr.get("source_url"),
            }
            continue
        industry=str(r.get("industry") or "").strip()
        # Nasdaq screener blank-check classification is diagnostic only.
        # Exclusion authority is the exact-ASOF SEC proof artifact above.
        # Suspect names without exact-ASOF proof remain queued fail-closed.
        px=num(r.get("lastsale"))
        mc=num(r.get("marketCap"))
        vol=num(r.get("volume"))
        if px is not None and mc is not None and px>=HARD_PRICE and mc>=2_000_000_000:
            exact_hard_mc_price_count+=1
        if force_all:
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
              "discovery_reason":"FULL_IDENTITY_NO_PREFILTER",
            }
            continue
        if px is None or mc is None:
            # Fail-closed discovery: an official Nasdaq-listed symbol must never
            # disappear merely because the screener omitted a gating field.
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
              "discovery_reason":"SCREENER_FIELD_MISSING_FORCE_QUEUE",
            }
            continue
        if px>=DISCOVERY_PRICE_FLOOR and mc>=DISCOVERY_MC_FLOOR:
            prefilter[sym]={
              "screener_price":px,
              "screener_market_cap":mc,
              "screener_volume":vol,
              "sector":r.get("sector"),
              "industry":r.get("industry"),
              "country":r.get("country"),
            }
    for sym in sorted(missing):
        if sym in sec_spac_proof and sym not in operating_overrides:
            pr=sec_spac_proof[sym]
            screener_excluded[sym]={
              "reason":"SPAC_BLANK_CHECK",
              "security_name":official.get(sym),
              "industry":"Blank Checks",
              "source":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
              "cik":pr.get("cik"),
              "source_url":pr.get("source_url"),
            }
            continue
        # Official-directory identity exists but the web screener omitted it.
        # For a SPAC-suspect name, SEC SIC 6770 is exclusion-only proof.
        # If SEC is unavailable/ambiguous, fail closed by keeping it queued.
        # Suspect names without exact-ASOF proof remain queued fail-closed.
        # Otherwise force it into downstream PRICE/DV30/HISTORY; MC remains
        # UNKNOWN unless a later authoritative resolver proves it.
        prefilter[sym]={
          "screener_price":None,
          "screener_market_cap":None,
          "screener_volume":None,
          "sector":None,
          "industry":None,
          "country":None,
          "discovery_reason":"OFFICIAL_SCREENER_MISSING_FORCE_QUEUE",
        }
    applied_sec=sorted(set(screener_excluded)&set(sec_spac_proof))
    queue=sorted(prefilter)
    return queue,prefilter,{
      "rows_returned":len(rows),
      "official_matched":len(off)-len(missing),
      "official_missing":len(missing),
      "official_missing_hash":sha_lines(sorted(missing)),
      "discovery_queue_total":len(queue),
      "hard_price_mc_snapshot_count":exact_hard_mc_price_count,
      "discovery_price_floor":DISCOVERY_PRICE_FLOOR,
      "discovery_mc_floor":DISCOVERY_MC_FLOOR,
      "authority":"FULL_IDENTITY_NO_PREFILTER" if force_all else "DISCOVERY_PREFILTER_ONLY_NOT_CANONICAL_MC",
      "full_identity":bool(force_all),
      "screener_spac_excluded_count":len(screener_excluded),
      "screener_spac_excluded_hash":sha_lines(sorted(screener_excluded)),
      "sec_spac_proof_count":len(applied_sec),
      "sec_spac_proof_hash":sha_lines(applied_sec),
    },screener_excluded

def build_full_identity_from_directory(official,sec_spac_proof=None,operating_overrides=None):
    """Build canonical full-identity scope without Nasdaq web market metadata.

    The official NasdaqTrader directory supplies membership/name only. Price,
    volume, market-cap, sector and industry are deliberately absent here.
    Exact SEC SPAC proof may exclude; otherwise name-suspect shells remain
    fail-closed UNKNOWN in the later identity partition.
    """
    sec_spac_proof=sec_spac_proof or {}
    operating_overrides=operating_overrides or {}
    prefilter={}
    excluded={}
    for sym in sorted(official):
        if sym in sec_spac_proof and sym not in operating_overrides:
            pr=sec_spac_proof[sym]
            excluded[sym]={
              "reason":"SPAC_BLANK_CHECK",
              "security_name":official.get(sym),
              "industry":None,
              "source":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
              "cik":pr.get("cik"),
              "source_url":pr.get("source_url"),
            }
            continue
        prefilter[sym]={
          "screener_price":None,
          "screener_market_cap":None,
          "screener_volume":None,
          "sector":None,
          "industry":None,
          "country":None,
          "discovery_reason":"NASDAQTRADER_FULL_IDENTITY_MARKET_GATES_DEFERRED_NO_WEB_SCREENER",
        }
    applied_sec=sorted(set(excluded)&set(sec_spac_proof))
    queue=sorted(prefilter)
    return queue,prefilter,{
      "rows_returned":len(official),
      "official_matched":len(official),
      "official_missing":0,
      "official_missing_hash":sha_lines([]),
      "discovery_queue_total":len(queue),
      "hard_price_mc_snapshot_count":0,
      "discovery_price_floor":DISCOVERY_PRICE_FLOOR,
      "discovery_mc_floor":DISCOVERY_MC_FLOOR,
      "authority":"NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA",
      "full_identity":True,
      "nasdaq_web_screener_used":False,
      "screener_spac_excluded_count":0,
      "screener_spac_excluded_hash":sha_lines([]),
      "sec_spac_proof_count":len(applied_sec),
      "sec_spac_proof_hash":sha_lines(applied_sec),
    },excluded

def official_blank_checks_exclusion_authorized(industry,full_identity,membership_snapshot):
    """Allow Nasdaq Blank Checks exclusion only from safe identity evidence.

    Legacy non-full discovery may use its same-run Nasdaq screener metadata.
    Canonical FULL_IDENTITY may use only a validated immutable exact-ASOF
    membership snapshot carrying preserved industry metadata. Live/current web
    screener metadata remains non-authoritative in canonical mode.
    """
    if str(industry or "").strip().lower()!="blank checks":
        return False
    if not full_identity:
        return True
    if not isinstance(membership_snapshot,dict):
        return False
    return bool(membership_snapshot.get("path") and membership_snapshot.get("blob_sha"))


def build_discovery_from_snapshot(official,industries,sec_spac_proof=None,operating_overrides=None):
    """Identity-only replay from exact-ASOF immutable membership metadata.

    No live price/MC fields are synthesized. Market gates remain deferred to
    PRICE/DV30. Exact SEC SPAC proofs may exclude; exact-ASOF Nasdaq industry
    metadata is preserved for the later blank-check/name fail-closed partition.
    """
    sec_spac_proof=sec_spac_proof or {}
    operating_overrides=operating_overrides or {}
    prefilter={}
    excluded={}
    for sym in sorted(official):
        if sym in sec_spac_proof and sym not in operating_overrides:
            pr=sec_spac_proof[sym]
            excluded[sym]={
              "reason":"SPAC_BLANK_CHECK",
              "security_name":official.get(sym),
              "industry":"Blank Checks",
              "source":"SEC_EDGAR_SIC_6770_EXACT_ASOF",
              "cik":pr.get("cik"),
              "source_url":pr.get("source_url"),
            }
            continue
        prefilter[sym]={
          "screener_price":None,
          "screener_market_cap":None,
          "screener_volume":None,
          "sector":None,
          "industry":industries.get(sym),
          "country":None,
          "discovery_reason":"IMMUTABLE_EXACT_ASOF_MEMBERSHIP_REPLAY_MARKET_GATES_DEFERRED",
        }
    applied_sec=sorted(set(excluded)&set(sec_spac_proof))
    queue=sorted(prefilter)
    return queue,prefilter,{
      "rows_returned":len(official),
      "official_matched":len(official),
      "official_missing":0,
      "official_missing_hash":sha_lines([]),
      "discovery_queue_total":len(queue),
      "hard_price_mc_snapshot_count":0,
      "discovery_price_floor":DISCOVERY_PRICE_FLOOR,
      "discovery_mc_floor":DISCOVERY_MC_FLOOR,
      "authority":"IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS",
      "full_identity":True,
      "screener_spac_excluded_count":len(excluded),
      "screener_spac_excluded_hash":sha_lines(sorted(excluded)),
      "sec_spac_proof_count":len(applied_sec),
      "sec_spac_proof_hash":sha_lines(applied_sec),
    },excluded

def completed_sessions():
    cal=mcal.get_calendar("NASDAQ")
    now=datetime.now(timezone.utc)
    sched=cal.schedule(
      start_date=(now.date()-timedelta(days=900)).isoformat(),
      end_date=(now.date()+timedelta(days=1)).isoformat(),
    )
    sessions=[]
    for idx,row in sched.iterrows():
        if row["market_close"].to_pydatetime()<=now:
            sessions.append(idx.date().isoformat())
    if len(sessions)<260:
        raise RuntimeError("CALENDAR_TOO_SHORT")
    return sessions[-1],sessions[-30:]

def parse_hist(sym,asof,expected30):
    try:
        df=ak.stock_us_daily(symbol=sym,adjust="")
        if df is None or df.empty:
            return "UNKNOWN_STATIC","SINA_HISTORY_EMPTY"
        by={}
        for rec in df.to_dict(orient="records"):
            d=rec.get("date")
            try:
                day=d.date().isoformat() if hasattr(d,"date") else str(d)[:10]
                close=float(rec.get("close"))
                volume=float(rec.get("volume"))
            except Exception:
                continue
            if day<=asof and close>0 and volume>0 and math.isfinite(close) and math.isfinite(volume):
                by[day]=(close,volume)
        bars=len(by)
        # PRICE may short-circuit from an exact same-ASOF close. A short Sina
        # history alone is not enough to terminally FAIL HISTORY because provider
        # incompleteness can mimic a young listing. Route it to the independent resolver.
        if asof in by:
            price=by[asof][0]
            if price<HARD_PRICE:
                return "FAIL_PRICE",{"price":price,"bars":bars,"proof":"ASOF_CLOSE"}
        else:
            return "UNKNOWN_STATIC",{
              "reason":"ASOF_MISSING_REQUIRES_RESOLUTION",
              "bars":bars,
              "history_short":bars<HARD_HISTORY,
            }

        if bars<HARD_HISTORY:
            return "UNKNOWN_STATIC",{
              "price":price,"bars":bars,
              "reason":"SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION"
            }

        missing=[d for d in expected30 if d not in by]
        known_dv=[by[d][0]*by[d][1] for d in expected30 if d in by]
        if missing:
            # Median interval proof with unknown session dollar-volume constrained
            # only to nonnegative values. No synthetic bar is inserted.
            m=len(missing)
            low=sorted(known_dv+[0.0]*m)
            lower=(low[14]+low[15])/2.0
            high=sorted(known_dv+[float("inf")]*m)
            upper=(high[14]+high[15])/2.0
            info={
              "price":price,"bars":bars,"reason":"EXACT30_MISSING",
              "dates":missing,"known_session_count":len(known_dv),
              "dv30_lower_bound":lower,
              "dv30_upper_bound":None if math.isinf(upper) else upper,
              "no_synthetic_bar":True,
            }
            if upper < HARD_DV30:
                info["proof"]="DV30_UPPER_BOUND_LT_GATE"
                return "FAIL_DV30",info
            info["reason"]="EXACT30_INCOMPLETE_NEVER_PASS"
            return "UNKNOWN_STATIC",info

        dvs=sorted(known_dv)
        dv30=(dvs[14]+dvs[15])/2.0
        info={
          "price":price,"dv30":dv30,"bars":bars,
          "known_session_count":30,"missing_sessions":[],
          "no_synthetic_bar":True,"proof":"EXACT30_MEDIAN"
        }
        if dv30<HARD_DV30:return "FAIL_DV30",info
        return "PASS",info
    except Exception as e:
        return "UNKNOWN_RETRY",f"{type(e).__name__}:{str(e)[:200]}"

def load_resolution_overlay(asof):
    meta={"status":"ABSENT"}
    if not RESOLUTION_OVERLAY.exists():
        return {},meta
    try:
        obj=json.loads(RESOLUTION_OVERLAY.read_text(encoding="utf-8"))
        if obj.get("schema")!="XRAY_HISTORY_IDENTITY_RESOLUTION_OVERLAY_V1":
            raise ValueError("SCHEMA")
        if obj.get("task_id")!=TASK_ID or obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SAFETY_OR_TASK")
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
        return {},{"status":"INVALID","reason":f"{type(e).__name__}:{str(e)[:160]}"}

def resolution_result(sym,ov,expected30):
    if not isinstance(ov,dict):
        return "UNKNOWN_STATIC",{"reason":"RESOLUTION_OVERLAY_INVALID","symbol":sym}
    d=ov.get("decision")
    if d=="FAIL_HISTORY":
        bars=ov.get("bars")
        if not isinstance(bars,int) or bars>=HARD_HISTORY:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_HISTORY_INVALID","symbol":sym}
        return "FAIL_HISTORY",{"bars":bars,"resolution_source":ov.get("source"),"reason":"DAILY_LT260"}
    if d=="FAIL_DV30":
        px=num(ov.get("price")); dv=num(ov.get("dv30")); bars=ov.get("bars")
        if px is None or dv is None or not isinstance(bars,int) or dv>=HARD_DV30:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_DV30_INVALID","symbol":sym}
        return "FAIL_DV30",{"price":px,"dv30":dv,"bars":bars,"resolution_source":ov.get("source"),"proof":ov.get("proof")}
    if d=="FAIL_PRICE":
        px=num(ov.get("price")); bars=ov.get("bars")
        if px is None or px>=HARD_PRICE:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_FAIL_PRICE_INVALID","symbol":sym}
        return "FAIL_PRICE",{"price":px,"bars":bars,"resolution_source":ov.get("source")}
    if d=="EXCLUDE":
        reason=str(ov.get("reason") or "")
        if reason not in {"SPAC_BLANK_CHECK","PREFERRED","WHEN_ISSUED"}:
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_EXCLUDE_INVALID","symbol":sym}
        return "FAIL_IDENTITY_TYPE",{"reason":reason,"proof":ov.get("proof"),"resolution_source":ov.get("source")}
    if d=="BLOCK_CURRENT_RUN":
        if ov.get("trade_status")!="Halted" or not ov.get("last_bar"):
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_BLOCK_INVALID","symbol":sym}
        return "BLOCK_CURRENT_RUN",{"reason":ov.get("reason"),"trade_status":"Halted","last_bar":ov.get("last_bar"),"resolution_source":ov.get("source")}
    if d=="PASS_HARD_GATES":
        px=num(ov.get("price")); bars=ov.get("bars")
        lo=num(ov.get("dv30_lower_bound")); hi=num(ov.get("dv30_upper_bound"))
        missing=ov.get("missing_sessions") or []; known=ov.get("known_session_count")
        if (
          px is None or px<HARD_PRICE or not isinstance(bars,int) or bars<HARD_HISTORY
          or lo is None or hi is None or lo<HARD_DV30 or hi<lo
          or ov.get("no_synthetic_bar") is not True
          or not isinstance(known,int) or known!=30 or missing!=[]
          or lo!=hi
        ):
            return "UNKNOWN_STATIC",{"reason":"RESOLUTION_PASS_BOUND_INVALID","symbol":sym}
        return "PASS",{
          "price":px,"bars":bars,
          "dv30_gate_pass_by_bound":True,
          "dv30_lower_bound":lo,"dv30_upper_bound":hi,
          "known_session_count":known,"missing_sessions":missing,
          "no_synthetic_bar":True,
          "resolution_source":ov.get("source"),
          "proof":ov.get("proof"),
        }
    return "UNKNOWN_STATIC",{"reason":"RESOLUTION_DECISION_UNKNOWN","symbol":sym,"decision":d}

def load(path):
    if path.exists():
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:pass
    return {}

def write(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def exclusion_counts(excluded):
    out={}
    for x in excluded.values():out[x["reason"]]=out.get(x["reason"],0)+1
    return dict(sorted(out.items()))

def result_counts(results):
    out={}
    for x in results.values():
        k=x.get("status")
        out[k]=out.get(k,0)+1
    return dict(sorted(out.items()))

def canonical_frozen_identity(asof):
    """Reuse only an exact same-ASOF canonical identity partition.

    Frozen reuse is support-plane binding only. It may preserve a proven
    PASS+UNKNOWN identity partition, but it must never promote an unproven
    SPAC/blank-check name into the PRICE queue.
    """
    if not FULL_IDENTITY:
        return None
    sp=ROOT/"canonical_current_full_state.json"
    mp=ROOT/"canonical_current_master_manifest.json"
    if not sp.exists() or not mp.exists():
        return None
    try:
        st=json.loads(sp.read_text(encoding="utf-8"))
        mf=json.loads(mp.read_text(encoding="utf-8"))
        q=list(st.get("queue") or [])
        identity_unknown=sorted(set(st.get("identity_unknown_symbols") or []))
        identity_unknown_detail=st.get("identity_unknown_detail") or {}
        raw_identity_total=int(st.get("raw_identity_total",-1))
        sec_proof,sec_blob=load_sec_spac_proof(asof)
        sec_count=len(sec_proof)
        asof_proof,asof_blob=load_asof_identity_proof(asof)
        operating_overrides=asof_proof.get("operating_overrides") or {}
        asof_counts={k:len(asof_proof.get(k) or {}) for k in ("restore_to_asof","remove_from_asof","operating_overrides")}
        dm=st.get("discovery_meta") or {}
        mf_sec=mf.get("sec_spac_proof") or {}
        mf_cp=mf.get("completion_proof") or {}
        disc=st.get("discovery") or {}
        names=st.get("security_names") or {}
        unproven_spac=[]
        for sym in q:
            row=disc.get(sym) or {}
            industry=str(row.get("industry") or "").strip()
            security_name=str(names.get(sym) or "").strip()
            suspect=(industry.lower()=="blank checks" or bool(SPAC_SUSPECT.search(security_name)))
            if suspect and sym not in operating_overrides and sym not in sec_proof:
                unproven_spac.append(sym)
        frozen_partition_exact=bool(
          len(identity_unknown)==len(set(identity_unknown))
          and set(identity_unknown_detail)==set(identity_unknown)
          and not (set(identity_unknown)&set(q))
          and int(dm.get("identity_unknown_count",-1))==len(identity_unknown)
          and dm.get("identity_unknown_hash")==sha_lines(identity_unknown)
          and raw_identity_total==len(q)+len(identity_unknown)
          and int(dm.get("raw_identity_total",-1))==raw_identity_total
          and int(mf.get("unknown_count",-1))==len(identity_unknown)
          and sorted(mf.get("unknown_symbols") or [])==identity_unknown
          and int(mf.get("pass_count",-1))==len(q)
          and sorted(mf.get("pass_symbols") or [])==sorted(q)
          and all((identity_unknown_detail.get(sym) or {}).get("unknown_never_pass") is True for sym in identity_unknown)
        )
        if (
          st.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2"
          or st.get("identity_ruleset")!=IDENTITY_RULESET
          or mf.get("identity_ruleset")!=IDENTITY_RULESET
          or st.get("identity_partition_policy")!=IDENTITY_PARTITION_POLICY
          or mf.get("identity_partition_policy")!=IDENTITY_PARTITION_POLICY
          or dm.get("identity_partition_policy")!=IDENTITY_PARTITION_POLICY
          or mf_cp.get("identity_partition_policy_exact") is not True
          or mf_cp.get("identity_unknown_partition_exact") is not True
          or str(st.get("asof_et") or "")!=asof
          or str(mf.get("asof_et") or "")!=asof
          or official_footer_date(st.get("official_footer"))!=asof
          or official_footer_date(mf.get("official_footer"))!=asof
          or not frozen_partition_exact
          or unproven_spac
          or int(st.get("queue_total",-1))!=len(q)
          or int(mf.get("queue_total",-1))!=len(q)
          or len(q)!=len(set(q))
          or st.get("queue_hash")!=sha_lines(q)
          or mf.get("queue_hash")!=st.get("queue_hash")
          or mf_cp.get("sec_spac_proof_binding") is not True
          or dm.get("sec_spac_proof_blob_sha")!=sec_blob
          or int(dm.get("sec_spac_proof_count",-1))!=sec_count
          or mf_sec.get("blob_sha")!=sec_blob
          or int(mf_sec.get("count",-1))!=sec_count
          or dm.get("asof_identity_proof_blob_sha")!=asof_blob
          or (mf.get("asof_identity_proof") or {}).get("blob_sha")!=asof_blob
          or (mf.get("asof_identity_proof") or {}).get("counts")!=asof_counts
        ):
            return None
        return {
          "queue":q,
          "queue_hash":st["queue_hash"],
          "security_names":dict(st.get("security_names") or {}),
          "discovery":dict(st.get("discovery") or {}),
          "discovery_meta":dict(st.get("discovery_meta") or {}),
          "identity_unknown_symbols":identity_unknown,
          "identity_unknown_detail":dict(identity_unknown_detail),
          "raw_identity_total":raw_identity_total,
          "official_footer":st.get("official_footer"),
          "identity_authority":st.get("identity_authority"),
          "explicit_excluded_count":int(st.get("explicit_excluded_count",0) or 0),
          "explicit_excluded_hash":st.get("explicit_excluded_hash"),
          "explicit_excluded_reason_counts":dict(st.get("explicit_excluded_reason_counts") or {}),
          "source_state_hash":st.get("state_hash"),
          "source_state_path":"nasdaq-xray/canonical_current_full_state.json",
          "source_manifest_path":"nasdaq-xray/canonical_current_master_manifest.json",
        }
    except Exception:
        return None

def support_frozen_identity(asof):
    """Exact-ASOF membership fallback for historical identity-only replay.

    Use durable support-plane sina_state.json only when it proves the same
    ASOF/footer/queue/UNKNOWN partition. Only metadata-neutral proof rebinds
    are allowed: no restore/remove delta, no newly proven SEC blank-check
    exclusion, and every current operating override must already be in the
    proven PASS queue with the same security name.
    """
    if not FULL_IDENTITY:
        return None
    p=ROOT/"sina_state.json"
    if not p.exists():
        return None
    try:
        st=json.loads(p.read_text(encoding="utf-8"))
        if (
          st.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2"
          or st.get("asof_et")!=asof
          or st.get("identity_ruleset")!=IDENTITY_RULESET
          or st.get("identity_partition_policy")!=IDENTITY_PARTITION_POLICY
          or official_footer_date(st.get("official_footer"))!=asof
        ):
            return None
        q=list(st.get("queue") or [])
        names=dict(st.get("security_names") or {})
        disc=dict(st.get("discovery") or {})
        unknown=sorted(set(st.get("identity_unknown_symbols") or []))
        detail=st.get("identity_unknown_detail") or {}
        dm=st.get("discovery_meta") or {}
        raw=int(st.get("raw_identity_total",-1))
        if not (
          int(st.get("queue_total",-1))==len(q)==len(set(q))
          and st.get("queue_hash")==sha_lines(q)
          and set(names)==set(q)
          and set(disc)==set(q)
          and set(detail)==set(unknown)
          and not (set(q)&set(unknown))
          and raw==len(q)+len(unknown)
          and int(dm.get("identity_unknown_count",-1))==len(unknown)
          and dm.get("identity_unknown_hash")==sha_lines(unknown)
          and int(dm.get("raw_identity_total",-1))==raw
          and dm.get("identity_partition_policy")==IDENTITY_PARTITION_POLICY
          and dm.get("full_identity") is True
        ):
            return None
        sec_proof,sec_blob=load_sec_spac_proof(asof)
        if sec_proof:
            return None
        asof_proof,asof_blob=load_asof_identity_proof(asof)
        if (asof_proof.get("restore_to_asof") or {}) or (asof_proof.get("remove_from_asof") or {}):
            return None
        operating=asof_proof.get("operating_overrides") or {}
        for sym,row in operating.items():
            if sym not in names or str((row or {}).get("security_name") or "")!=str(names.get(sym) or ""):
                return None
        unproven=[]
        for sym in q:
            row=disc.get(sym) or {}
            industry=str(row.get("industry") or "").strip()
            security_name=str(names.get(sym) or "").strip()
            if (industry.lower()=="blank checks" or bool(SPAC_SUSPECT.search(security_name))) and sym not in operating:
                unproven.append(sym)
        if unproven:
            return None
        return {
          "queue":q,
          "queue_hash":st["queue_hash"],
          "security_names":names,
          "discovery":disc,
          "discovery_meta":dm,
          "identity_unknown_symbols":unknown,
          "identity_unknown_detail":detail,
          "raw_identity_total":raw,
          "official_footer":st.get("official_footer"),
          "identity_authority":st.get("identity_authority"),
          "explicit_excluded_count":int(st.get("explicit_excluded_count",0) or 0),
          "explicit_excluded_hash":st.get("explicit_excluded_hash"),
          "explicit_excluded_reason_counts":dict(st.get("explicit_excluded_reason_counts") or {}),
          "source_state_hash":st.get("state_hash"),
          "source_state_path":"nasdaq-xray/sina_state.json",
          "source_manifest_path":"nasdaq-xray/sina_state.json",
          "support_rebind":True,
        }
    except Exception:
        return None

def main():
    asof,expected30=completed_sessions()
    sec_proof_path=sec_spac_proof_path(asof)
    identity_proof_path=asof_identity_proof_path(asof)
    sec_spac_proof,sec_spac_blob=load_sec_spac_proof(asof)
    asof_identity_proof,asof_identity_blob=load_asof_identity_proof(asof)
    operating_overrides=asof_identity_proof.get("operating_overrides") or {}
    sec_identity_token="SEC_SPAC_PROOF:"+str(sec_spac_blob or "NONE")
    asof_identity_token="ASOF_IDENTITY_PROOF:"+str(asof_identity_blob or "NONE")
    frozen=canonical_frozen_identity(asof)
    if frozen is None:
        frozen=support_frozen_identity(asof)
    membership_snapshot=None
    if frozen is None:
        membership_snapshot=exact_asof_membership_snapshot(asof)
    if frozen is not None:
        names=dict(frozen["security_names"])
        excluded={}
        footer=str(frozen.get("official_footer") or "CANONICAL_FROZEN_IDENTITY")
        if official_footer_date(footer)!=asof:
            raise RuntimeError("FROZEN_IDENTITY_FOOTER_NOT_EXACT_ASOF")
        identity_token="CANONICAL_FROZEN:"+str(frozen.get("source_state_hash") or frozen["queue_hash"])+"|"+sec_identity_token+"|"+asof_identity_token
    elif membership_snapshot is not None:
        names=dict(membership_snapshot["security_names"])
        excluded={}
        footer=str(membership_snapshot["official_footer"])
        identity_token="IMMUTABLE_EXACT_ASOF_MEMBERSHIP:"+membership_snapshot["blob_sha"]+"|"+sec_identity_token+"|"+asof_identity_token
    else:
        names,excluded,footer=official_nasdaq()
        live_footer_date=official_footer_date(footer)
        if live_footer_date!=asof:
            raise RuntimeError(f"NASDAQ_DIRECTORY_NOT_EXACT_ASOF:{live_footer_date}!={asof}")
        names,excluded=apply_asof_identity_proof(names,excluded,asof_identity_proof)
        identity_token=footer+"|"+sec_identity_token+"|"+asof_identity_token
    state=load(STATE)
    epoch_key=IDENTITY_RULESET+"|"+IDENTITY_PARTITION_POLICY+"|"+("FULL_IDENTITY" if FULL_IDENTITY else "DISCOVERY_PREFILTER")+"|"+identity_token+"|"+asof

    if state.get("schema")!="XRAY_NASDAQ_SCREENER_SINA_V2" or state.get("epoch_key")!=epoch_key:
        if frozen is not None:
            queue=list(frozen["queue"])
            discovery=dict(frozen["discovery"])
            meta=dict(frozen["discovery_meta"])
            identity_unknown_symbols=list(frozen["identity_unknown_symbols"])
            identity_unknown_detail=dict(frozen["identity_unknown_detail"])
            meta.update({
              "authority":"CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF",
              "full_identity":True,
              "frozen_identity_path":frozen["source_state_path"],
              "frozen_manifest_path":frozen["source_manifest_path"],
              "frozen_queue_hash":frozen["queue_hash"],
              "identity_partition_policy":IDENTITY_PARTITION_POLICY,
              "identity_unknown_count":len(identity_unknown_symbols),
              "identity_unknown_hash":sha_lines(identity_unknown_symbols),
              "raw_identity_total":int(frozen["raw_identity_total"]),
              "sec_spac_proof_path":("nasdaq-xray/"+sec_proof_path.name) if sec_spac_blob else None,
              "sec_spac_proof_blob_sha":sec_spac_blob,
              "sec_spac_proof_count":len(sec_spac_proof),
              "sec_spac_proof_hash":sha_lines(sorted(sec_spac_proof)),
              "asof_identity_proof_path":("nasdaq-xray/"+identity_proof_path.name) if asof_identity_blob else None,
              "asof_identity_proof_blob_sha":asof_identity_blob,
              "asof_identity_proof_counts":{k:len(asof_identity_proof.get(k) or {}) for k in ("restore_to_asof","remove_from_asof","operating_overrides")},
              "support_membership_rebind":bool(frozen.get("support_rebind")),
            })
            ex_serial=[]
        else:
            if membership_snapshot is not None:
                queue,discovery,meta,screener_excluded=build_discovery_from_snapshot(
                    names,membership_snapshot["industries"],sec_spac_proof,operating_overrides
                )
                meta.update({
                  "membership_snapshot_path":membership_snapshot["path"],
                  "membership_snapshot_blob_sha":membership_snapshot["blob_sha"],
                  "identity_decisions_reused_from_snapshot":False,
                })
            else:
                if FULL_IDENTITY:
                    queue,discovery,meta,screener_excluded=build_full_identity_from_directory(
                        names,sec_spac_proof,operating_overrides
                    )
                else:
                    queue,discovery,meta,screener_excluded=build_discovery(
                        names,False,sec_spac_proof,operating_overrides
                    )
            # C4.17 accepts official/issuer/SEC proof for SPAC-shell handling.
            # Exact same-ASOF Nasdaq screener industry "Blank Checks" is official
            # exclusion evidence and may deterministically EXCLUDE the shell.
            # A name-only SPAC suspicion remains UNKNOWN unless SEC/issuer proof
            # exists; this prevents false exclusion of an operating de-SPAC.
            identity_unknown_detail={}
            official_blank_excluded=[]
            for sym in list(queue):
                disc=discovery.get(sym) or {}
                industry=str(disc.get("industry") or "").strip()
                security_name=str(names.get(sym) or "").strip()
                if sym in operating_overrides:
                    continue
                # Canonical FULL_IDENTITY never uses live/current Nasdaq web
                # screener metadata as decision authority. It may use only the
                # validated immutable exact-ASOF membership snapshot preserved
                # for this research epoch.
                if official_blank_checks_exclusion_authorized(
                    industry,FULL_IDENTITY,membership_snapshot
                ):
                    screener_excluded[sym]={
                      "reason":"SPAC_BLANK_CHECK",
                      "proof":{
                        "authority":(
                          "NASDAQ_EXACT_ASOF_FROZEN_SCREENER_INDUSTRY"
                          if FULL_IDENTITY else
                          "NASDAQ_SAME_ASOF_SCREENER_INDUSTRY"
                        ),
                        "industry":industry,
                        "security_name":security_name,
                        "asof_et":asof,
                        "snapshot_path":(
                          (membership_snapshot or {}).get("path")
                          if FULL_IDENTITY else None
                        ),
                        "snapshot_blob_sha":(
                          (membership_snapshot or {}).get("blob_sha")
                          if FULL_IDENTITY else None
                        ),
                        "unknown_never_pass":True,
                      },
                    }
                    official_blank_excluded.append(sym)
                    continue
                if bool(SPAC_SUSPECT.search(security_name)) and sym not in sec_spac_proof:
                    identity_unknown_detail[sym]={
                      "reason":"SPAC_NAME_SUSPECT_OFFICIAL_CLASSIFICATION_UNRESOLVED",
                      "source":"NASDAQ_SAME_ASOF_DIRECTORY_NAME_FAIL_CLOSED",
                      "security_name":security_name,
                      "same_asof_nasdaq_industry":industry,
                      "exact_sec_spac_proof":False,
                      "official_blank_checks_proof":False,
                      "unknown_never_pass":True,
                    }
            identity_unknown_symbols=sorted(identity_unknown_detail)
            remove_set=set(identity_unknown_symbols)|set(official_blank_excluded)
            if remove_set:
                queue=[sym for sym in queue if sym not in remove_set]
                discovery={sym:row for sym,row in discovery.items() if sym not in remove_set}
            meta.update({
              "sec_spac_proof_path":("nasdaq-xray/"+sec_proof_path.name) if sec_spac_blob else None,
              "sec_spac_proof_blob_sha":sec_spac_blob,
              "asof_identity_proof_path":("nasdaq-xray/"+identity_proof_path.name) if asof_identity_blob else None,
              "asof_identity_proof_blob_sha":asof_identity_blob,
              "asof_identity_proof_counts":{k:len(asof_identity_proof.get(k) or {}) for k in ("restore_to_asof","remove_from_asof","operating_overrides")},
              "identity_partition_policy":IDENTITY_PARTITION_POLICY,
              "identity_unknown_count":len(identity_unknown_symbols),
              "identity_unknown_hash":sha_lines(identity_unknown_symbols),
              "official_blank_checks_excluded_count":len(official_blank_excluded),
              "official_blank_checks_excluded_hash":sha_lines(sorted(official_blank_excluded)),
              "raw_identity_total":len(queue)+len(identity_unknown_symbols),
            })
            excluded.update(screener_excluded)
            ex_serial=[s+"|"+excluded[s]["reason"] for s in sorted(excluded)]
        state={
          "schema":"XRAY_NASDAQ_SCREENER_SINA_V2",
          "build":BUILD,
          "task_id":TASK_ID,
          "execution":"NONE",
          "real_money":"NO-GO",
          "unknown_never_pass":True,
          "epoch_key":epoch_key,
          "asof_et":asof,
          "expected30":expected30,
          "official_footer":footer,
          "identity_authority":(frozen.get("identity_authority") if frozen is not None else "NASDAQTRADER_EXPLICIT_TYPE_FILTER_V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER"),
          "identity_ruleset":IDENTITY_RULESET,
          "identity_partition_policy":IDENTITY_PARTITION_POLICY,
          "discovery_source":(
              "CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF" if frozen is not None else
              "IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_REPLAY" if membership_snapshot is not None else
              ("NASDAQTRADER_FULL_IDENTITY_NO_NASDAQ_WEB_MARKET_METADATA" if FULL_IDENTITY else "NASDAQ_OFFICIAL_WEB_SCREENER_PREFILTER_ONLY")
          ),
          "history_source":"SINA_US_DAILY_ACCELERATOR_NOT_G9",
          "identity_unknown_symbols":identity_unknown_symbols,
          "identity_unknown_detail":identity_unknown_detail,
          "raw_identity_total":len(queue)+len(identity_unknown_symbols),
          "queue":queue,
          "queue_hash":sha_lines(queue),
          "queue_total":len(queue),
          "discovery":discovery,
          "discovery_meta":meta,
          "security_names":{s:names[s] for s in queue},
          "explicit_excluded_count":(frozen["explicit_excluded_count"] if frozen is not None else len(excluded)),
          "explicit_excluded_hash":(frozen["explicit_excluded_hash"] if frozen is not None else sha_lines(ex_serial)),
          "explicit_excluded_reason_counts":(frozen["explicit_excluded_reason_counts"] if frozen is not None else exclusion_counts(excluded)),
          "cursor":0,
          "results":{},
          "status":"HISTORY_PARTIAL",
        }

    queue=state["queue"]
    if IDENTITY_ONLY:
        now=datetime.now(timezone.utc).isoformat()
        results={
          sym:{
            "status":"UNKNOWN_STATIC",
            "info":{
              "reason":"MARKET_GATES_DEFERRED_TO_PRICE_DV30_HISTORY",
              "source":"MASTER_IDENTITY_ONLY_MODE",
            },
            "attempts":0,
            "updated_at_utc":now,
          }
          for sym in queue
        }
        state["results"]=results
        state["cursor"]=len(queue)
        state["processed_new_this_run"]=0
        state["processed_retry_this_run"]=0
        state["counts"]=result_counts(results)
        state["pending_retry"]=0
        state["unknown_count"]=len(queue)
        state["status"]="IDENTITY_READY_MARKET_GATES_DEFERRED"
        state["history_source"]="DEFERRED_TO_PRICE_DV30_HISTORY_PHASE"
        state["updated_at_utc"]=now
        state["state_hash"]=hashlib.sha256(
          json.dumps(state,sort_keys=True,separators=(",",":")).encode("utf-8")
        ).hexdigest()
        write(STATE,state)
        cand={
          "schema":"XRAY_SINA_CANDIDATES_V2",
          "task_id":TASK_ID,"asof_et":asof,
          "execution":"NONE","real_money":"NO-GO",
          "candidate_count":0,
          "source":"MASTER_IDENTITY_ONLY_MARKET_GATES_DEFERRED",
          "market_cap_authority":"UNRESOLVED_UNTIL_CANONICAL_MC_POLICY",
          "candidates":{},
        }
        write(CAND,cand)
        print(json.dumps({
          "status":state["status"],"asof":asof,"queue_total":len(queue),
          "identity_only":True,"market_gate_unknown":len(queue),
          "discovery_meta":state["discovery_meta"],
        },sort_keys=True))
        return

    results=state.setdefault("results",{})
    retry=[
      s for s in sorted(results)
      if results[s].get("status")=="UNKNOWN_RETRY"
      and int(results[s].get("attempts",0))<MAX_ATTEMPTS
    ][:RETRY_BATCH]

    start=int(state.get("cursor",0))
    end=min(start+BATCH,len(queue))
    new=queue[start:end]
    work=[];seen=set()
    for s in retry+new:
        if s not in seen:
            seen.add(s);work.append(s)

    done=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(parse_hist,s,asof,expected30):s for s in work}
        for fut in as_completed(futs):
            sym=futs[fut]
            status,info=fut.result()
            done.append((sym,status,info))

    for sym,status,info in done:
        prev=results.get(sym) or {}
        attempts=int(prev.get("attempts",0))+1
        if status=="UNKNOWN_RETRY" and attempts>=MAX_ATTEMPTS:
            status="UNKNOWN_RETRY_EXHAUSTED"
        results[sym]={
          "status":status,
          "info":info,
          "attempts":attempts,
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
        }

    resolution_overlay,resolution_overlay_meta=load_resolution_overlay(asof)
    for sym,ov in sorted(resolution_overlay.items()):
        if sym not in queue:
            continue
        status,info=resolution_result(sym,ov,expected30)
        prev=results.get(sym) or {}
        results[sym]={
          "status":status,
          "info":info,
          "attempts":int(prev.get("attempts",0)),
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "resolution_overlay":True,
        }
    state["resolution_overlay_meta"]=resolution_overlay_meta

    # Explicit Nasdaq screener industry classification as Blank Checks is a
    # legal/shell blocker, not a history-provider UNKNOWN. This does not
    # declare an operating de-SPAC a shell; it only blocks symbols that the
    # same-run Nasdaq metadata explicitly classifies as Blank Checks.
    for sym in queue:
        disc=(state.get("discovery") or {}).get(sym) or {}
        if str(disc.get("industry") or "").strip().lower()=="blank checks":
            prev=results.get(sym) or {}
            results[sym]={
              "status":"BLOCK_LEGAL_SHELL",
              "info":{
                "reason":"NASDAQ_SCREENER_INDUSTRY_BLANK_CHECKS",
                "source":"NASDAQ_SAME_RUN_SCREENER_METADATA",
                "security_name":(state.get("security_names") or {}).get(sym),
              },
              "attempts":int(prev.get("attempts",0)),
              "updated_at_utc":datetime.now(timezone.utc).isoformat(),
            }

    state["cursor"]=end
    state["processed_new_this_run"]=len(new)
    state["processed_retry_this_run"]=len(retry)
    state["counts"]=result_counts(results)
    state["pending_retry"]=sum(
      1 for x in results.values()
      if x.get("status")=="UNKNOWN_RETRY" and int(x.get("attempts",0))<MAX_ATTEMPTS
    )
    state["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    unknown_count=sum(1 for x in results.values() if str(x.get("status","")).startswith("UNKNOWN"))
    state["unknown_count"]=unknown_count
    state["status"]="HISTORY_COMPLETE" if end>=len(queue) and state["pending_retry"]==0 and unknown_count==0 else "HISTORY_PARTIAL"
    state["state_hash"]=hashlib.sha256(
      json.dumps(state,sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()
    write(STATE,state)

    candidates={}
    for sym,r in results.items():
        if r.get("status")!="PASS":continue
        info=dict(r.get("info") or {})
        info["security_name"]=state["security_names"].get(sym)
        info["screener_market_cap_shadow"]=state["discovery"][sym].get("screener_market_cap")
        info["screener_price_shadow"]=state["discovery"][sym].get("screener_price")
        candidates[sym]=info

    cand={
      "schema":"XRAY_SINA_CANDIDATES_V2",
      "task_id":TASK_ID,
      "asof_et":asof,
      "execution":"NONE",
      "real_money":"NO-GO",
      "candidate_count":len(candidates),
      "source":"NASDAQTRADER_FULL_IDENTITY_PLUS_SINA_WITH_TTL_FAIL_CLOSED_RESOLUTION_OVERLAY" if FULL_IDENTITY else "NASDAQTRADER_IDENTITY_PLUS_NASDAQ_SCREENER_DISCOVERY_PLUS_SINA_WITH_TTL_FAIL_CLOSED_RESOLUTION_OVERLAY",
      "market_cap_authority":"UNRESOLVED_UNTIL_CANONICAL_MC_POLICY",
      "candidates":candidates,
    }
    write(CAND,cand)

    print(json.dumps({
      "status":state["status"],
      "asof":asof,
      "queue_total":len(queue),
      "cursor":end,
      "processed_new":len(new),
      "processed_retry":len(retry),
      "pending_retry":state["pending_retry"],
      "counts":state["counts"],
      "candidate_count":len(candidates),
      "discovery_meta":state["discovery_meta"],
    },sort_keys=True))

if __name__=="__main__":
    main()
