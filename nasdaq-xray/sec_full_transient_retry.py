#!/usr/bin/env python3
"""Bounded official SEC transient-only repair on an immutable 514-scope witness.

Never reclassifies stale, missing tags, mismatched identifiers, or HTTP 404
as a transient error. Never promotes shadow SEC shares to C4.17 PRIMARY MC.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import time
from pathlib import Path
from sec_official_free_mc_transport_probe import (
    get_json,select_shares,valid_operator_contact
)
from sec_free_mc_multisymbol_pit_audit import (
    ROOT,SEC_MAP,git_blob_sha,map_ciks
)

TRANSIENT="SEC_TRANSPORT_UNAVAILABLE"
SCHEMA="XRAY_SEC_TRANSIENT_RECOVERY_SHADOW_V1"
ORIGIN_SCHEMA="XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1"

def validate_origin(origin:dict,master_sha:str,price_sha:str,scope:list[str]):
    if origin.get("schema")!=ORIGIN_SCHEMA:
        raise ValueError("BAD_ORIGIN_SCHEMA")
    if origin.get("asof_et")!="2026-10-08":
        raise ValueError("ORIGIN_ASOF_MISMATCH")
    if (origin.get("master_git_blob_sha")!=master_sha or
            origin.get("price_git_blob_sha")!=price_sha):
        raise ValueError("ORIGIN_GIT_BLOB_MISMATCH")
    if (origin.get("execution")!="NONE" or origin.get("real_money")!="NO-GO"
            or origin.get("production_alpha_authority") is not False
            or origin.get("c417_primary_mc_count")!=0):
        raise ValueError("ORIGIN_SAFETY_INVALID")
    old=origin.get("statuses") or {}
    reasons=origin.get("reason_codes") or {}
    if not isinstance(old,dict) or set(old)!=set(scope):
        raise ValueError("ORIGIN_COMPLETE_EXACT_SCOPE_INVALID")
    if int(origin.get("sample_count",-1))!=len(scope):
        raise ValueError("ORIGIN_SAMPLE_COUNT_WRONG")
    if int(origin.get("batch_limit",-1))!=len(scope) or int(origin.get("batch_offset",-1))!=0:
        raise ValueError("ORIGIN_BATCH_PARTITION_INVALID")
    expected_hash=hashlib.sha256(("\n".join(sorted(scope))+"\n").encode()).hexdigest()
    if origin.get("sample_scope_sha256")!=expected_hash:
        raise ValueError("ORIGIN_PASS_SET_HASH_MISMATCH")
    # A transient request error never proves the whole issuer is bad;
    # this is the ONLY reason code this recovery path may retry.
    selected=sorted(k for k in scope if reasons.get(k)==TRANSIENT
                    and old[k]=="UNKNOWN_SEC_TRANSPORT")
    return selected

def run(source_path:Path):
    origin=json.loads(source_path.read_text(encoding="utf-8"))
    mb=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    pb=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    master=json.loads(mb)
    price=json.loads(pb)
    price_pass=price.get("pass_symbols") or []
    if master.get("asof_et")!="2026-10-08" or price.get("asof_et")!="2026-10-08":
        raise ValueError("CURRENT_ASOF_CHANGED")
    if len(set(price_pass))!=len(price_pass)==514:
        raise ValueError("PRICE_PASS_SET_CHANGED")
    if not set(price_pass).issubset(set(master.get("pass_symbols") or [])):
        raise ValueError("MASTER_PRICE_IDENTITY_DRIFT")
    syms=validate_origin(origin,git_blob_sha(mb),git_blob_sha(pb),price_pass)
    out={"schema":SCHEMA,"origin_asof_et":"2026-10-08",
         "origin_master_blob_sha":git_blob_sha(mb),
         "origin_price_blob_sha":git_blob_sha(pb),
         "origin_source_scope_count":514,
         "eligible_retry_count":len(syms),
         "eligible_retry_symbols":syms,
         "attempted":0,
         "outcomes":{},"counts":{},
         "execution":"NONE","real_money":"NO-GO",
         "unknown_never_pass":True,
         "c417_primary_mc_count":0,"real_buy_candidates_created":0,
         "production_authority":False,
         "raw_share_counts_stored":False,
         "source_rights_unchanged":True,
         "status":"NOT_ATTEMPTED"}
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    if not valid_operator_contact(ua):
        return dict(out,status="BLOCKED_OPERATOR_CONTACT")
    if not syms:
        return dict(out,status="NO_TRANSIENT_RETRY_REQUIRED")
    try:
        mapdata=map_ciks(get_json(SEC_MAP,ua))
    except ValueError as exc:
        return dict(out,status="BLOCKED_SEC_CIK_MAP",map_error=str(exc))
    stopped=False
    for i,sym in enumerate(syms):
        cik=mapdata.get(sym)
        if not cik:
            out["outcomes"][sym]="UNKNOWN_OFFICIAL_CIK_ROUTE"
            continue
        # At most two network attempts per endpoint on transient timeouts.
        # 403/429 stop immediately, 404 is terminal, never try a guessed CIK.
        classified=None
        for retry in range(2):
            try:
                out["attempted"]+=1
                facts=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",ua)
                time.sleep(0.55)
                sub=get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",ua)
                classified=select_shares(facts,sub,"2026-10-08",expected_cik=cik)
                break
            except ValueError as exc:
                code=str(exc)
                if code in ("SEC_HTTP_403","SEC_HTTP_429"):
                    out["outcomes"][sym]="UNKNOWN_SEC_FAIR_ACCESS_STOP"
                    stopped=True
                    break
                if code!="SEC_TRANSPORT_UNAVAILABLE":
                    out["outcomes"][sym]="UNKNOWN_NONRETRYABLE_"+code
                    break
                if retry==0:
                    time.sleep(2.0)
                else:
                    out["outcomes"][sym]="UNKNOWN_TRANSIENT_EXHAUSTED"
        if classified is not None:
            out["outcomes"][sym]=classified.get("status") or "UNKNOWN"
        if stopped:
            for other in syms[i+1:]:
                out["outcomes"][other]="UNKNOWN_NOT_ATTEMPTED_FAIR_ACCESS"
            break
        if i+1<len(syms): time.sleep(0.55)
    out["counts"]=dict(sorted(collections.Counter(out["outcomes"].values()).items()))
    out["status"]="PARTIAL_SEC_FAIR_ACCESS_STOP" if stopped else "BOUNDED_TRANSIENT_RETRY_COMPLETED"
    return out

def selftest():
    scope=["A","B","C"]
    o={"schema":ORIGIN_SCHEMA,"asof_et":"2026-10-08",
       "master_git_blob_sha":"m"*40,"price_git_blob_sha":"p"*40,
       "execution":"NONE","real_money":"NO-GO",
       "production_alpha_authority":False,"c417_primary_mc_count":0,
       "statuses":{"A":"UNKNOWN_SEC_TRANSPORT",
                   "B":"UNKNOWN_SEC_TRANSPORT",
                   "C":"SHADOW_SHARES_VINTAGE_ONLY"},
       "reason_codes":{"A":TRANSIENT,"B":"SEC_HTTP_404",
                       "C":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED"},
       "batch_limit":3,"batch_offset":0,"sample_count":3,
       "sample_scope_sha256":hashlib.sha256("A\nB\nC\n".encode()).hexdigest()}
    assert validate_origin(o,"m"*40,"p"*40,scope)==["A"]
    from copy import deepcopy
    for mutation in (
        ("master_git_blob_sha","z"*40),
        ("price_git_blob_sha","z"*40),
        ("c417_primary_mc_count",1),
        ("asof_et","2026-10-07"),
        ("sample_scope_sha256","0"*64)):
        changed=deepcopy(o)
        changed[mutation[0]]=mutation[1]
        try:validate_origin(changed,"m"*40,"p"*40,scope)
        except ValueError:pass
        else:raise AssertionError("SOURCE_DRIFT_ACCEPTED:"+mutation[0])
    print("XRAY_SEC_TRANSIENT_RETRY_SELFTEST=PASS_ORIGIN_SHA_EXACT_FIVE_NEGATIVES_NO_404_RETRY")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--origin",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
    else:
        if not a.origin or not a.output:
            p.error("--origin and --output required")
        result=run(a.origin)
        a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print("XRAY_SEC_RECOVERY_STATUS="+result["status"])
        print("XRAY_SEC_RECOVERY_COUNTS="+json.dumps(result["counts"],sort_keys=True))
        print("XRAY_SEC_RECOVERY_ELIGIBLE="+str(result["eligible_retry_count"]))
        print("XRAY_SEC_RECOVERY_ATTEMPTED="+str(result["attempted"]))
        if result["status"].startswith("BLOCKED_"):raise SystemExit(2)
