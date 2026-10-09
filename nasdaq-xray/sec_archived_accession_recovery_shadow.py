#!/usr/bin/env python3
"""Official SEC submissions archive: bounded recovery of seven proven accession gaps.

Exactly seven tickers were classified SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS
by real Actions 37863746633 (artifact SHA256 636b66a99e887b2c4dd53fa254e628ca3ee409fede08e681f4806eddca28a88c).
This read-only successor never returns MC or AL PASS and never persists SEC shares.
Historical submission archives are fetched only when they cover a viable exact-ASOF
DEI filing date, using the genuine operator contact and SEC fair-access policy.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import time
from zoneinfo import ZoneInfo
from sec_official_free_mc_transport_probe import (
    get_json,select_shares,valid_operator_contact,MAX_AGE_DAYS,ACCEPTED_FORMS,
)
from sec_free_mc_multisymbol_pit_audit import map_ciks,SEC_MAP,git_blob_sha

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA="XRAY_SEC_ARCHIVED_ACCESSION_RECOVERY_SHADOW_V1"
SCOPE=("CHTR","CMCSA","CME","IBKR","REGN","VICR","WDAY")
ORIGIN_MASTER_SHA="92c37207d8dd766ab3fe8f1300e3014c6c5ab629"
ORIGIN_PRICE_SHA="42ed4a1c1a104aff94f73793194b25746d3bea59"
ALLOWED_ARCHIVE_NAME=re.compile(r"^CIK\d{10}-submissions-\d{3}\.json$")
FIELDS=("accessionNumber","form","filingDate","acceptanceDateTime")
MAX_ARCHIVES_PER_CIK=5

def exact_scope():
    mpath=ROOT/"canonical_current_master_manifest.json"
    ppath=ROOT/"canonical_current_price_dv30.json"
    m=json.loads(mpath.read_text())
    p=json.loads(ppath.read_text())
    if (git_blob_sha(mpath.read_bytes())!=ORIGIN_MASTER_SHA
        or git_blob_sha(ppath.read_bytes())!=ORIGIN_PRICE_SHA
        or m.get("asof_et")!="2026-10-08"
        or p.get("asof_et")!="2026-10-08"
        or p.get("unknown_never_pass") is not True
        or m.get("unknown_never_pass") is not True
        or not set(SCOPE).issubset(set(p.get("pass_symbols") or []))
        or not set(SCOPE).issubset(set(m.get("pass_symbols") or []))):
        raise ValueError("ORIGIN_EXACT_SCOPE_SHA_OR_ASOF_MISMATCH")
    return p["asof_et"]

def archive_filing_dates(facts,asof):
    """Only companyfacts DEI entries viable for strict PIT time-window checks."""
    raw=((((facts.get("facts") or {}).get("dei") or {})
          .get("EntityCommonStockSharesOutstanding") or {})
          .get("units") or {}).get("shares") or []
    cutoff=dt.date.fromisoformat(asof)
    dates=set()
    for row in raw:
        if not isinstance(row,dict) or row.get("form") not in ACCEPTED_FORMS:continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",str(row.get("accn") or "")):continue
        try:
            d=dt.date.fromisoformat(str(row.get("filed")))
            end=dt.date.fromisoformat(str(row.get("end")))
        except (TypeError,ValueError):continue
        if 0<=(cutoff-end).days<=MAX_AGE_DAYS and end<=d<=cutoff:
            dates.add(d)
    return dates

def archive_names(sub,facts,asof):
    dates=archive_filing_dates(facts,asof)
    if not dates:return []
    rows=((sub.get("filings") or {}).get("files") or [])
    eligible=[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict):continue
        name=str(row.get("name") or "")
        if not ALLOWED_ARCHIVE_NAME.fullmatch(name) or name in seen:
            continue
        seen.add(name)
        try:
            lo=dt.date.fromisoformat(str(row.get("filingFrom")))
            hi=dt.date.fromisoformat(str(row.get("filingTo")))
        except (TypeError,ValueError):continue
        if lo>hi:continue
        if any(lo<=d<=hi for d in dates):
            eligible.append((hi,name))
    eligible.sort(reverse=True)
    return [name for _,name in eligible[:MAX_ARCHIVES_PER_CIK]]

def filing_columns(src):
    if not isinstance(src,dict):raise ValueError("SEC_ARCHIVE_SCHEMA_INVALID")
    cols=[src.get(k) for k in FIELDS]
    if any(not isinstance(x,list) for x in cols):
        raise ValueError("SEC_ARCHIVE_COLUMNS_MISSING")
    if len({len(x) for x in cols})!=1:
        raise ValueError("SEC_ARCHIVE_COLUMNS_LENGTH_MISMATCH")
    if len(cols[0])>100000:
        raise ValueError("SEC_ARCHIVE_OVERSIZED")
    return {k:list(src[k]) for k in FIELDS}

def merge_archive(sub,archive):
    # SEC returned archived rows must not overwrite or relabel a recent record.
    recent=filing_columns(((sub.get("filings") or {}).get("recent") or {}))
    older=filing_columns(archive)
    index={}
    for source in (recent,older):
        for values in zip(*(source[k] for k in FIELDS)):
            accession,form,filed,accepted=values
            if not isinstance(accession,str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}",accession):
                continue
            if accession in index and index[accession]!=values:
                raise ValueError("SEC_DUPLICATE_ACCESSION_CONFLICT")
            index[accession]=values
    merged=dict(sub)
    filings=dict(sub.get("filings") or {})
    filings["recent"]={k:[values[idx] for values in index.values()] for idx,k in enumerate(FIELDS)}
    merged["filings"]=filings
    return merged

def classify_recent_mismatch(facts,sub,asof):
    """Counts-only evidence distinguishing missing accession / form / filed date.

    Historical filed dates are not modified or guessed. A genuinely different
    issuer/accession remains UNKNOWN, regardless of a ticker's current mapping.
    """
    raw=((((facts.get("facts") or {}).get("dei") or {})
          .get("EntityCommonStockSharesOutstanding") or {})
          .get("units") or {}).get("shares") or []
    recent=((sub.get("filings") or {}).get("recent") or {})
    cols=filing_columns(recent)
    index={row[0]:row for row in zip(*(cols[k] for k in FIELDS))
           if isinstance(row[0],str)}
    cutoff=dt.date.fromisoformat(asof)
    reasons=collections.Counter()
    for row in raw:
        if not isinstance(row,dict) or row.get("form") not in ACCEPTED_FORMS:
            continue
        try:
            filed=dt.date.fromisoformat(str(row["filed"]))
            obs=dt.date.fromisoformat(str(row["end"]))
        except (ValueError,KeyError,TypeError):
            reasons["MALFORMED_DEI_DATE"]+=1
            continue
        if not (obs<=filed<=cutoff and 0<=(cutoff-obs).days<=MAX_AGE_DAYS):
            continue
        accession=str(row.get("accn") or "")
        entry=index.get(accession)
        if entry is None:
            reasons["ACCESSION_NOT_IN_RECENT"]+=1
        elif entry[1]!=row["form"]:
            reasons["FORM_CONFLICT_SAME_ACCESSION"]+=1
        elif str(entry[2])!=str(row["filed"]):
            reasons["FILED_DATE_CONFLICT_SAME_ACCESSION"]+=1
        else:
            reasons["MATCHED_CURRENT_FILING_METADATA"]+=1
    if not reasons:reasons["NO_VIABLE_DEI_FACT_IN_ASOF_WINDOW"]=1
    return dict(sorted(reasons.items()))

def run():
    asof=exact_scope()
    result={
        "schema":SCHEMA,"asof_et":asof,
        "scope_symbols":list(SCOPE),"scope_count":len(SCOPE),
        "source_artifact_sha256":"636b66a99e887b2c4dd53fa254e628ca3ee409fede08e681f4806eddca28a88c",
        "source_master_blob_sha":ORIGIN_MASTER_SHA,"source_price_blob_sha":ORIGIN_PRICE_SHA,
        "status":"BLOCKED","reason_counts":{},"symbol_statuses":{},
        "recent_filing_metadata_diagnostics":{},
        "execution":"NONE","real_money":"NO-GO",
        "production_primary_mc_count":0,"no_vendor_raw_values_persisted":True,
        "source":"OFFICIAL_SEC_EDGAR","candidate_created":False,
        "unknown_never_pass":True}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    if not valid_operator_contact(ua):
        return dict(result,status="BLOCKED_OPERATOR_CONTACT",
                    reason_counts={"OPERATOR_CONTACT_REQUIRED":len(SCOPE)})
    statuses={}
    try:routes=map_ciks(get_json(SEC_MAP,ua))
    except ValueError:
        return dict(result,status="BLOCKED_SEC_MAP",reason_counts={"SEC_MAP_UNAVAILABLE":len(SCOPE)})
    fatal=False
    for idx,sym in enumerate(SCOPE):
        cik=routes.get(sym)
        if not cik:
            statuses[sym]="UNKNOWN_OFFICIAL_CIK_MAP_MISSING"
            continue
        try:
            facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",ua)
            time.sleep(0.55)
            sub=get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
            before=select_shares(facts,sub,asof,expected_cik=cik)
            result["recent_filing_metadata_diagnostics"][sym]=classify_recent_mismatch(facts,sub,asof)
            if before["status"]=="SHADOW_SHARES_VINTAGE_ONLY":
                statuses[sym]="SHADOW_RECENT_SOURCE_NOW_PRESENT"
            elif before.get("reason")!="SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS":
                statuses[sym]="UNKNOWN_OTHER_OFFICIAL_REASON"
            else:
                names=archive_names(sub,facts,asof)
                if not names:
                    statuses[sym]="UNKNOWN_NO_TARGETED_OFFICIAL_ARCHIVE"
                else:
                    found=False
                    for name in names:
                        time.sleep(0.55)
                        old=get_json("https://data.sec.gov/submissions/"+name,ua)
                        sub=merge_archive(sub,old)
                        recovered=select_shares(facts,sub,asof,expected_cik=cik)
                        if recovered["status"]=="SHADOW_SHARES_VINTAGE_ONLY":
                            statuses[sym]="SHADOW_ARCHIVE_ACCESSION_RECOVERED_ONLY"
                            found=True
                            break
                    if not found:statuses[sym]="UNKNOWN_ARCHIVE_ACCESSION_STILL_UNVERIFIED"
        except ValueError as exc:
            code=str(exc)
            statuses[sym]="UNKNOWN_SEC_FAIR_ACCESS_STOP" if code in ("SEC_HTTP_403","SEC_HTTP_429") else "UNKNOWN_SEC_ARCHIVE_TRANSPORT_OR_SCHEMA"
            if code in ("SEC_HTTP_403","SEC_HTTP_429"):
                fatal=True
        if fatal:
            for missing in SCOPE[idx+1:]:
                statuses[missing]="UNKNOWN_NOT_QUERIED_FAIR_ACCESS_STOP"
            break
        if idx+1<len(SCOPE):time.sleep(0.55)
    result["symbol_statuses"]=dict(sorted(statuses.items()))
    result["reason_counts"]=dict(sorted(collections.Counter(statuses.values()).items()))
    result["status"]="PARTIAL_SEC_FAIR_ACCESS_STOP" if fatal else "OFFICIAL_SEC_ARCHIVE_AUDIT_COMPLETED"
    return result

def selftest():
    facts={"facts":{"dei":{"EntityCommonStockSharesOutstanding":{"units":{"shares":[
        {"form":"10-Q","accn":"0000320193-26-000001","filed":"2026-10-07","end":"2026-09-30","val":100}
    ]}}}}}
    sub={"cik":320193,"filings":{
        "recent":{"accessionNumber":[],"form":[],"filingDate":[],"acceptanceDateTime":[]},
        "files":[{"name":"CIK0000320193-submissions-001.json","filingFrom":"2026-01-01","filingTo":"2026-10-08"}]}}
    assert archive_names(sub,facts,"2026-10-08")==["CIK0000320193-submissions-001.json"]
    assert classify_recent_mismatch({"cik":320193,**facts},sub,"2026-10-08")=={"ACCESSION_NOT_IN_RECENT":1}
    archive={"accessionNumber":["0000320193-26-000001"],"form":["10-Q"],
             "filingDate":["2026-10-07"],"acceptanceDateTime":["2026-10-07T15:45:00-04:00"]}
    old=select_shares({"cik":320193,**facts},sub,"2026-10-08")
    assert old["status"]=="UNKNOWN"
    new=select_shares({"cik":320193,**facts},merge_archive(sub,archive),"2026-10-08")
    assert new["status"]=="SHADOW_SHARES_VINTAGE_ONLY"
    mismatch={"cik":320193,"filings":{"recent":{
      "accessionNumber":["0000320193-26-000001"],
      "form":["10-Q"],"filingDate":["2026-10-06"],
      "acceptanceDateTime":["2026-10-07T15:45:00-04:00"]}}}
    assert classify_recent_mismatch({"cik":320193,**facts},mismatch,"2026-10-08")=={"FILED_DATE_CONFLICT_SAME_ACCESSION":1}
    mismatch["filings"]["recent"]["form"]=["10-K"]
    assert classify_recent_mismatch({"cik":320193,**facts},mismatch,"2026-10-08")=={"FORM_CONFLICT_SAME_ACCESSION":1}
    from copy import deepcopy
    late=deepcopy(archive);late["acceptanceDateTime"]=["2026-10-08T16:30:00-04:00"]
    assert select_shares({"cik":320193,**facts},merge_archive(sub,late),"2026-10-08")["status"]=="UNKNOWN"
    for bad in ({}, {"accessionNumber":[],"form":["10-K"],"filingDate":[],"acceptanceDateTime":[]},
                {"accessionNumber":["A"],"form":[],"filingDate":[],"acceptanceDateTime":[]}):
        try:filing_columns(bad)
        except ValueError:pass
        else:raise AssertionError("BAD_ARCHIVE_ACCEPTED")
    conflict=deepcopy(sub)
    conflict["filings"]["recent"]={k:list(v) for k,v in archive.items()}
    duplicate=deepcopy(archive);duplicate["form"]=["10-K"]
    try:merge_archive(conflict,duplicate)
    except ValueError:pass
    else:raise AssertionError("CONFLICTING_ARCHIVE_ACCEPTED")
    fake=deepcopy(sub);fake["filings"]["files"]=[{"name":"../unsafe.json","filingFrom":"2026-01-01","filingTo":"2026-10-08"}]
    assert archive_names(fake,facts,"2026-10-08")==[]
    print("XRAY_SEC_ARCHIVE_SELFTEST=PASS_ARCHIVE_PIT_7_NEGATIVE_ZERO_PRIMARY")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--output",type=pathlib.Path)
    opts=parser.parse_args()
    if opts.selftest:selftest();return
    out=run()
    if opts.output:opts.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_ARCHIVE_TRANSPORT="+out["status"])
    print("XRAY_SEC_ARCHIVE_RESULT_COUNTS="+json.dumps(out["reason_counts"],sort_keys=True))
    print("XRAY_SEC_ARCHIVE_RESULTS="+json.dumps(out["symbol_statuses"],sort_keys=True))
    print("XRAY_SEC_ARCHIVE_RECENT_METADATA_DIAG="+json.dumps(out["recent_filing_metadata_diagnostics"],sort_keys=True))
    print("XRAY_SEC_ARCHIVE_PRIMARY=ZERO_NEVER_PROMOTED")
    if out["status"].startswith("BLOCKED_"):raise SystemExit(2)

if __name__=="__main__":main()
