#!/usr/bin/env python3
"""Re-check seven legacy SEC accession suspects from CURRENT 2026-10-09 sources.

Do not relabel the immutable 2026-10-08 origin audit: this performs new
same-ASOF live SEC reads on seven independently requalified current symbols.
Public SEC archive evidence only. No share prices or share counts persisted,
no derived market cap, no PRIMARY authority or live/trading R92.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
from sec_archived_accession_recovery_shadow import (
    SCOPE, archive_names, merge_archive, classify_recent_mismatch,
    MAX_ARCHIVES_PER_CIK,
)
from sec_official_free_mc_transport_probe import get_json, select_shares, valid_operator_contact
from sec_free_mc_multisymbol_pit_audit import map_ciks, SEC_MAP, git_blob_sha

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-09"
PRICE_SHA="6f3f68fff0897d68f200ad3621c51a5071494714"
MASTER_SHA="828c21436a836b69fe5084387e1c54446c7b5075"
SCHEMA="XRAY_SEC_CURRENT_20261009_SEVEN_ACCESSION_RECHECK_SHADOW_V1"
POLICY="C4.17"

def hash_lines(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def scope_contract(price,master,price_sha,master_sha):
    """Require immutable exact 9-Oct canonical source identity; no stale rollover."""
    if price_sha!=PRICE_SHA or master_sha!=MASTER_SHA:
        raise ValueError("CURRENT_20261009_SOURCE_GIT_BLOB_SHA_MISMATCH")
    if price.get("asof_et")!=ASOF or master.get("asof_et")!=ASOF:
        raise ValueError("CURRENT_20261009_ASOF_MISMATCH")
    for obj in (price,master):
        if (obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO"
            or obj.get("unknown_never_pass") is not True):
            raise ValueError("CANONICAL_SAFETY_CONTRACT_DRIFT")
    p=price.get("pass_symbols")
    m=master.get("pass_symbols")
    if not isinstance(p,list) or not isinstance(m,list):
        raise ValueError("CANONICAL_PASS_SYMBOLS_MISSING")
    if (p!=sorted(set(p)) or len(p)!=514 or price.get("pass_count")!=514
        or price.get("pass_hash")!=hash_lines(p)):
        raise ValueError("CANONICAL_514_PRICE_SCOPE_INVALID")
    if len(m)!=len(set(m)) or not set(p).issubset(set(m)):
        raise ValueError("MASTER_PRICE_PARTITION_INVALID")
    if not set(SCOPE).issubset(set(p)):
        raise ValueError("SEVEN_RECHECK_SYMBOLS_NOT_IN_CURRENT_PRICE_PASS")
    return {"asof_et":ASOF,"price_blob_sha":price_sha,
            "master_blob_sha":master_sha,"price_pass_count":len(p),
            "price_pass_hash":price["pass_hash"],
            "seven_scope":list(SCOPE),
            "seven_scope_hash":hash_lines(list(SCOPE))}

def load_source():
    pb=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    mb=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    return scope_contract(json.loads(pb),json.loads(mb),
                          git_blob_sha(pb),git_blob_sha(mb))

def recheck(fetch=get_json, sleep=time.sleep):
    authority=load_source()
    out={"schema":SCHEMA,**authority,
         "legacy_cohort_20261008_only_rechecked_not_reused":True,
         "origin": "CURRENT_20261009_SEC_LIVE_REREAD",
         "authority":"SHADOW_ONLY", "status":"NOT_RUN",
         "reason_counts":{},"symbol_statuses":{},
         "metadata_reason_counts":{},
         "raw_shares_persisted":False,"market_cap_derived":False,
         "primary_mc_count":0,"history_pass_count":0,"r92_created":False,
         "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    ua=os.environ.get("XRAY_SEC_USER_AGENT","")
    if not valid_operator_contact(ua):
        return dict(out,status="BLOCKED_OPERATOR_CONTACT")
    try:
        cik_map=map_ciks(fetch(SEC_MAP,ua))
    except ValueError as exc:
        return dict(out,status="BLOCKED_SEC_CIK_MAP",reason_counts={"SEC_MAP_UNAVAILABLE":7})
    status={}
    meta=Counter()
    stopped=False
    for idx,sym in enumerate(SCOPE):
        cik=cik_map.get(sym)
        if not cik:
            status[sym]="UNKNOWN_SEC_CIK_ROUTE_MISSING"
            continue
        try:
            facts=fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",ua)
            sleep(0.55)
            submissions=fetch(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
            old=select_shares(facts,submissions,ASOF,expected_cik=cik)
            for name,count in classify_recent_mismatch(facts,submissions,ASOF).items():
                meta[name]+=count
            if old["status"]=="SHADOW_SHARES_VINTAGE_ONLY":
                status[sym]="SHADOW_CURRENT_RECENT_SHARES_VINTAGE_ONLY"
            elif old.get("reason")=="SEC_FACT_ACCESSION_NOT_VERIFIED_IN_RECENT_SUBMISSIONS":
                candidates=archive_names(submissions,facts,ASOF)
                if len(candidates)>MAX_ARCHIVES_PER_CIK:
                    raise ValueError("SEC_ARCHIVE_UNBOUNDED")
                if not candidates:
                    status[sym]="UNKNOWN_NO_APPLICABLE_CURRENT_ARCHIVE"
                else:
                    recovered=False
                    for name in candidates:
                        sleep(0.55)
                        archive=fetch("https://data.sec.gov/submissions/"+name,ua)
                        submissions=merge_archive(submissions,archive)
                        row=select_shares(facts,submissions,ASOF,expected_cik=cik)
                        if row["status"]=="SHADOW_SHARES_VINTAGE_ONLY":
                            recovered=True
                            break
                    status[sym]=("SHADOW_CURRENT_ARCHIVE_SHARES_VINTAGE_ONLY"
                                  if recovered else "UNKNOWN_ARCHIVE_STILL_UNVERIFIED")
            elif old.get("reason")=="SEC_CONFLICTING_SAME_VINTAGE_SHARES":
                status[sym]="UNKNOWN_SEC_CONFLICTING_SAME_VINTAGE_SHARES"
            else:
                status[sym]="UNKNOWN_CURRENT_"+str(old.get("reason") or "SEC_SHARE_REASON")
        except ValueError as exc:
            if str(exc) in ("SEC_HTTP_403","SEC_HTTP_429"):
                status[sym]="UNKNOWN_SEC_FAIR_ACCESS_STOP"
                for rest in SCOPE[idx+1:]:
                    status[rest]="UNKNOWN_NOT_ATTEMPTED_SEC_FAIR_ACCESS_STOP"
                stopped=True
                break
            status[sym]="UNKNOWN_SEC_TRANSPORT_OR_SCHEMA"
        if idx+1<len(SCOPE):sleep(0.55)
    out["symbol_statuses"]=dict(sorted(status.items()))
    out["reason_counts"]=dict(sorted(Counter(status.values()).items()))
    out["metadata_reason_counts"]=dict(sorted(meta.items()))
    out["status"]=("PARTIAL_SEC_FAIR_ACCESS_STOP" if stopped
                    else "CURRENT_SEVEN_OFFICIAL_RECHECK_COMPLETED_SHADOW")
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    opts=ap.parse_args()
    if opts.out.resolve().is_relative_to(ROOT.parent.resolve()):
        ap.error("--out must be private runner path outside repo")
    r=recheck()
    opts.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_CURRENT_SEVEN_RECHECK="+r["status"])
    print("XRAY_SEC_CURRENT_SEVEN_COUNTS="+json.dumps(r["reason_counts"],sort_keys=True))
    print("XRAY_SEC_CURRENT_SEVEN_SHADOW=NO_PRIMARY_NO_MC_NO_ALPHA")
    if r["status"].startswith("BLOCKED_"):
        raise SystemExit(2)

if __name__=="__main__":
    main()
