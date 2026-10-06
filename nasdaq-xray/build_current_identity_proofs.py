#!/usr/bin/env python3
from __future__ import annotations

import csv
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
    industry=str(industries.get(sym) or "").strip()
    if not industry or industry.lower()=="blank checks":
        return None
    source=str((old or {}).get("source_url") or "")
    evidence=str((old or {}).get("evidence_date") or "")
    if not source.startswith("https://www.sec.gov/") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return None
    out=dict(old)
    out["security_name"]=names[sym]
    out["reason"]="SAME_ASOF_NASDAQ_DIRECTORY_SCREENER_PLUS_PRIOR_SEC_OPERATING_EVIDENCE"
    out["same_asof_nasdaq_screener_industry"]=industry
    out["same_asof_revalidated_without_sec_network"]=True
    return out

def prior_blank_fallback(sym,old,asof,names,industries):
    if sym not in names:
        return None
    industry=str(industries.get(sym) or "").strip()
    if industry.lower()!="blank checks":
        return None
    if int((old or {}).get("sic",-1))!=6770:
        return None
    source=str((old or {}).get("source_url") or "")
    evidence=str((old or {}).get("evidence_date") or "")
    if not source.startswith("https://www.sec.gov/") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
        return None
    out=dict(old)
    out["same_asof_nasdaq_screener_industry"]=industry
    out["same_asof_revalidated_without_sec_network"]=True
    return out

def load_json_url(url:str):
    return json.loads(request_bytes(url,SEC_UA,35).decode("utf-8"))

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

def sec_current_row(sym:str,asof:str,cik:int|None,want_blank:bool):
    if cik is None:
        return None
    sub=load_json_url(f"{SEC_SUBMISSIONS}/CIK{cik:010d}.json")
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
          and all(isinstance(j.get(k) or {},dict) for k in ("restore_to_asof","remove_from_asof","operating_overrides"))
        )
    except Exception:
        return False

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
          and all(isinstance(v,dict) and int(v.get("sic",-1))==6770 for v in proofs.values())
        )
    except Exception:
        return False

def main():
    asof=completed_asof()
    identity_path,sec_path=proof_paths(asof)
    if validate_existing_identity(identity_path,asof) and (not sec_path.exists() or validate_existing_sec(sec_path,asof)):
        print(json.dumps({"result":"NOOP_EXACT_PROOFS_ALREADY_VALID","asof_et":asof,"identity_path":identity_path.name,"sec_path":sec_path.name if sec_path.exists() else None},sort_keys=True))
        return

    names,footer=official_directory()
    footer_date=parse_footer_date(footer)
    if footer_date!=asof:
        raise RuntimeError(f"NASDAQ_DIRECTORY_NOT_EXACT_ASOF:{footer_date}!={asof}")

    prior_identity=latest_prior("master_asof_identity_proof_",asof)
    prior_sec=latest_prior("master_sec_spac_proof_",asof)
    operating_seed={}
    if prior_identity:
        operating_seed=dict(prior_identity[2].get("operating_overrides") or {})
    blank_seed={}
    if prior_sec:
        blank_seed=dict(prior_sec[2].get("proofs") or {})

    industries=official_screener_industries()
    sec_network_error=None
    operating={}
    for sym,old in sorted(operating_seed.items()):
        if sym not in names:
            continue
        cik=cik_from_prior_row(old)
        try:
            row=sec_current_row(sym,asof,cik,False)
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

    identity={
      "schema":"XRAY_MASTER_ASOF_IDENTITY_PROOF_V1",
      "asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "authority":"NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION",
      "applicability":"EXACT_ASOF_ONLY_NO_FORWARD_CARRY",
      "source_directory_footer":footer,
      "source_directory_date":footer_date,
      "same_asof_directory_is_membership_authority":True,
      "restore_to_asof":{},
      "remove_from_asof":{},
      "operating_overrides":operating,
    }
    identity_path.write_text(json.dumps(identity,ensure_ascii=False,sort_keys=False,indent=2)+"\n",encoding="utf-8")

    proofs={}
    for sym,old in sorted(blank_seed.items()):
        if sym not in names:
            continue
        cik=cik_from_prior_row(old)
        try:
            row=sec_current_row(sym,asof,cik,True)
        except Exception as e:
            row=None
            sec_network_error=sec_network_error or f"{type(e).__name__}:{str(e)[:200]}"
        if row is not None:
            row["same_asof_revalidated_without_sec_network"]=False
            proofs[sym]=row
            continue
        fallback=prior_blank_fallback(sym,old,asof,names,industries)
        if fallback is None:
            raise RuntimeError("SEC_SPAC_REVALIDATION_FAILED:"+sym)
        proofs[sym]=fallback
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
      "forward_carry":False,
      "sec_network_error":sec_network_error,
      "same_asof_nasdaq_screener_fallback_used":bool(sec_network_error),
    },sort_keys=True))

if __name__=="__main__":
    main()
