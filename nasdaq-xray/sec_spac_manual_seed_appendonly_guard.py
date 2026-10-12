#!/usr/bin/env python3
"""Source-exact SEC SPAC manual-seed append-only resolver.

A 2026-10-09 frozen proof references the original manual seed registry
Git blob. Later *additions* to that registry must not invalidate already
proved identical issuer records. Neither changed record values nor changed
original proof references are accepted. No unknown is promoted to PASS:
this validates only existing official SIC6770 SPAC exclusions.

C4.17/C4.27, execution NONE, REAL_MONEY NO-GO.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/"master_sec_spac_proof_20261009.json"
SEEDS=ROOT/"master_sec_identity_manual_seed_registry.json"
ORIGINAL_REGISTRY_PATH="nasdaq-xray/master_sec_identity_manual_seed_registry.json"
PROOF_SCHEMA="XRAY_MASTER_SEC_SPAC_PROOF_V1"
SEED_SCHEMA="XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1"
FIELDS=("cik","sic","classification","source_url","evidence_date")
NO_RELEASE={"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def git_blob_bytes(buf):
    return hashlib.sha1(b"blob "+str(len(buf)).encode("ascii")+b"\0"+buf).hexdigest()

def date_valid(text):
    if not isinstance(text,str):
        return False
    try:
        return dt.date.fromisoformat(text).isoformat()==text
    except (ValueError,TypeError):
        return False

def reject(label):
    raise ValueError("SEC_MANUAL_SEED_APPEND_ONLY_GUARD:"+label)

def prove(proof,seed,asof,symbol,original_sha,current_sha):
    if not isinstance(proof,dict) or not isinstance(seed,dict):
        reject("SOURCE_DOCUMENT_MISSING")
    if not all(proof.get(k)==v and seed.get(k)==v for k,v in NO_RELEASE.items()):
        reject("FAIL_CLOSED_POLICY")
    if (proof.get("schema")!=PROOF_SCHEMA or seed.get("schema")!=SEED_SCHEMA
        or proof.get("authority")!="SEC_EDGAR_SIC_6770_EXACT_ASOF"
        or proof.get("applicability")!="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
        or seed.get("authority")!="OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY"):
        reject("SOURCE_AUTHORITY_CHANGED")
    if not date_valid(asof) or proof.get("asof_et")!=asof:
        reject("SOURCE_EPOCH_NOT_EXACT")
    if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}",symbol):
        reject("SYMBOL_INVALID")
    coverage=proof.get("discovery_coverage")
    if not isinstance(coverage,dict):
        reject("COVERAGE_MISSING")
    if (coverage.get("manual_seed_registry_path")!=ORIGINAL_REGISTRY_PATH
        or not re.fullmatch(r"[0-9a-f]{40}",original_sha or "")
        or coverage.get("manual_seed_registry_blob_sha")!=original_sha
        or not re.fullmatch(r"[0-9a-f]{40}",current_sha or "")):
        reject("HISTORIC_BLOB_BINDING_CHANGED")
    proofs=proof.get("proofs")
    records=seed.get("records")
    if not isinstance(proofs,dict) or not isinstance(records,dict):
        reject("SOURCE_RECORDS_MISSING")
    if (len(records)<coverage.get("manual_seed_registry_record_count",0)
        or type(coverage.get("manual_seed_registry_record_count")) is not int):
        reject("APPEND_ONLY_RECORD_COUNT_SHRANK")
    row=proofs.get(symbol)
    manual=records.get(symbol)
    if not isinstance(row,dict) or not isinstance(manual,dict):
        reject("PROOF_OR_SEED_SYMBOL_MISSING")
    if (row.get("revalidation_semantics")!=
        "MANUAL_OFFICIAL_SEC_EVIDENCE_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS"
        or row.get("manual_seed_registry_path")!=ORIGINAL_REGISTRY_PATH
        or row.get("manual_seed_registry_blob_sha")!=original_sha):
        reject("PROOF_REQUIRES_DIFFERENT_FROZEN_SEED")
    for k in FIELDS:
        if row.get(k)!=manual.get(k):
            reject("PREEXISTING_RECORD_CHANGED:"+k)
    if (row.get("sic")!=6770 or row.get("classification")!="Blank Checks"
        or manual.get("is_blank_check") is not True
        or manual.get("evidence_authority")!="SEC_EDGAR_OFFICIAL"
        or not re.fullmatch(r"0[0-9]{9}",str(manual.get("cik") or ""))
        or not str(manual.get("source_url") or "").startswith("https://www.sec.gov/Archives/edgar/")
        or not date_valid(manual.get("evidence_date"))
        or not date_valid(manual.get("verified_asof_et"))
        or not (manual["evidence_date"]<=manual["verified_asof_et"]<=asof)):
        reject("MANUAL_SEC_ORIGINAL_IDENTITY_INVALID")
    days=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(manual["evidence_date"])).days
    if days<0 or days>120:
        reject("MANUAL_SEED_STALE_OR_FUTURE")
    return "UNCHANGED_OFFICIAL_SEC_RECORD_APPEND_ONLY_REGISTRY_ACCEPTED_NO_ALPHA"

def test():
    proof=json.loads(MASTER.read_text(encoding="utf-8"))
    manual=json.loads(SEEDS.read_text(encoding="utf-8"))
    original=proof["discovery_coverage"]["manual_seed_registry_blob_sha"]
    current=git_blob_bytes(SEEDS.read_bytes())
    require_count=0
    for symbol,row in proof["proofs"].items():
        if row.get("revalidation_semantics","").startswith("MANUAL_OFFICIAL_SEC_"):
            got=prove(proof,manual,proof["asof_et"],symbol,original,current)
            if got!="UNCHANGED_OFFICIAL_SEC_RECORD_APPEND_ONLY_REGISTRY_ACCEPTED_NO_ALPHA":
                reject("WRONG_POSITIVE")
            require_count+=1
    if require_count!=135 or original==current:
        reject("UNEXPECTED_REAL_MANUAL_SEED_COHORT")
    symbol="AACI"
    if symbol not in proof["proofs"]:
        reject("NO_REAL_CANARY")
    cases=[
        ("CIK_MUTATION",lambda p,s:s["records"][symbol].update(cik="0000000001")),
        ("SIC_MUTATION",lambda p,s:s["records"][symbol].update(sic=3333)),
        ("CLASSIFICATION_MUTATION",lambda p,s:s["records"][symbol].update(classification="Operating")),
        ("EVIDENCE_DATE_MUTATION",lambda p,s:s["records"][symbol].update(evidence_date="2026-08-13")),
        ("SOURCE_URL_MUTATION",lambda p,s:s["records"][symbol].update(source_url="https://www.sec.gov/Archives/edgar/changed")),
        ("BLANK_CHECK_MUTATION",lambda p,s:s["records"][symbol].update(is_blank_check=False)),
        ("AUTHORITY_MUTATION",lambda p,s:s["records"][symbol].update(evidence_authority="UNKNOWN")),
        ("AFTER_ASOF_VERIFICATION",lambda p,s:s["records"][symbol].update(verified_asof_et="2026-10-10")),
        ("RECORD_DELETE",lambda p,s:s["records"].pop(symbol)),
        ("PROOF_CIK_MUTATION",lambda p,s:p["proofs"][symbol].update(cik="0000000001")),
        ("PROOF_ORIGINAL_BLOB_MUTATION",lambda p,s:p["proofs"][symbol].update(manual_seed_registry_blob_sha="f"*40)),
        ("ROOT_ORIGINAL_BLOB_MUTATION",lambda p,s:p["discovery_coverage"].update(manual_seed_registry_blob_sha="f"*40)),
        ("SEED_SCHEMA_MUTATION",lambda p,s:s.update(schema="OTHER")),
        ("SEED_RIGHTS_MUTATION",lambda p,s:s.update(real_money="GO")),
        ("PROOF_RIGHTS_MUTATION",lambda p,s:p.update(real_money="GO")),
        ("PROOF_ASOF_MUTATION",lambda p,s:p.update(asof_et="2026-10-10")),
        ("PROOF_AUTHORITY_MUTATION",lambda p,s:p.update(authority="UNKNOWN")),
        ("SEED_COUNT_SHRINK",lambda p,s:s.update(records={symbol:s["records"][symbol]})),
        ("APPROVE_FALSE_PROOF",lambda p,s:p["proofs"][symbol].update(revalidation_semantics="DIRECT_ALPHA_PASS")),
        ("SOURCE_TAMPER",lambda p,s:s["records"][symbol].update(source_url="https://evil.invalid/")),
    ]
    accepted=[]
    for label,mutate in cases:
        p=copy.deepcopy(proof);s=copy.deepcopy(manual)
        mutate(p,s)
        try:prove(p,s,proof["asof_et"],symbol,original,current)
        except ValueError:
            accepted.append(label)
        else:reject("BAD_MUTANT_ACCEPTED:"+label)
    if len(accepted)!=len(cases):
        reject("NEGATIVE_COUNT")
    print("XRAY_SEC_SPAC_APPEND_ONLY=PASS_REAL_135_UNCHANGED_20_NEGATIVE_NO_ALPHA")
    print("XRAY_SEC_SPAC_SOURCE_OLD_SHA="+original)
    print("XRAY_SEC_SPAC_SOURCE_CURRENT_SHA="+current)

if __name__=="__main__":
    test()
