#!/usr/bin/env python3
"""Independent, optimized-Python-safe SEC 514 SHADOW release gate.

Only validates provenance and operational classification metadata. Never
transforms SEC vintage witnesses into market-cap PRIMARY, HISTORY, R92 or AL.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from sec_free_mc_multisymbol_pit_audit import root_cause_class

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1"
STATUS_ALLOWED=frozenset({
    "SHADOW_SHARES_VINTAGE_ONLY","UNKNOWN",
    "UNKNOWN_OFFICIAL_CIK_ROUTE","UNKNOWN_SEC_TRANSPORT",
    "UNKNOWN_NOT_ATTEMPTED_UPSTREAM_SEC_BLOCK"})
TRANSPORT_ALLOWED=frozenset({
    "SEC_OFFICIAL_MULTI_REQUESTS_COMPLETE_WITH_UNKNOWN_ALLOWED",
    "BLOCKED_FAIR_ACCESS_STOP"})

def require(ok,reason):
    # NOT assert: safety checks still run when PYTHONOPTIMIZE=1.
    if not ok:
        raise ValueError("SEC_FULL_SCOPE_RELEASE_BLOCKED:"+reason)

def git_blob_sha(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def symbol_hash(symbols):
    return hashlib.sha256(("\n".join(sorted(symbols))+"\n").encode()).hexdigest()

def validate(report,price,master,price_raw,master_raw):
    require(all(isinstance(x,dict) for x in (report,price,master)),
            "OBJECT_SCHEMA")
    require(isinstance(price_raw,bytes) and isinstance(master_raw,bytes),
            "GIT_BLOB_BYTES")
    scope=price.get("pass_symbols")
    require(isinstance(scope,list) and bool(scope)
            and all(isinstance(x,str) and x for x in scope)
            and len(scope)==len(set(scope))
            and type(price.get("pass_count")) is int
            and price["pass_count"]==len(scope)
            and 1<=len(scope)<=650,
            "PRICE_PASS_SCOPE")
    require(price.get("asof_et")==master.get("asof_et")==report.get("asof_et"),
            "ASOF_EXACT")
    require(report.get("schema")==SCHEMA
            and report.get("source")=="SEC_EDGAR_OFFICIAL",
            "SCHEMA_SOURCE")
    require(report.get("price_git_blob_sha")==git_blob_sha(price_raw)
            and report.get("master_git_blob_sha")==git_blob_sha(master_raw),
            "SOURCE_GIT_BLOB_SHA")
    require(report.get("sample_scope_sha256")==symbol_hash(scope),
            "PRICE_SCOPE_HASH")
    require(report.get("full_current_price_pass_scope") is True
            and report.get("batch_offset")==0
            and type(report.get("batch_limit")) is int
            and report["batch_limit"]==len(scope)
            and type(report.get("sample_count")) is int
            and report["sample_count"]==len(scope),
            "FULL_SCOPE_BATCH")
    require(report.get("ticker_map_timestamp")=="CURRENT_ONLY_NOT_HISTORICAL_PIT"
            and report.get("official_exchange_current_mapping_only") is True,
            "CURRENT_MAP_NOT_PIT")
    for key,val in (("execution","NONE"),("real_money","NO-GO"),
                    ("unknown_never_pass",True),
                    ("production_alpha_authority",False),
                    ("c417_primary_mc_count",0),
                    ("market_cap_calculated",False),
                    ("price_binding_attested",False),
                    ("corporate_action_binding_attested",False),
                    ("no_real_candidate_claim",True)):
        require(report.get(key)==val and type(report.get(key)) is type(val),
                "FALSE_AUTHORITY_"+key)
    require(report.get("transport") in TRANSPORT_ALLOWED,
            "SOURCE_TRANSPORT_NOT_VALID")
    statuses=report.get("statuses")
    reasons=report.get("reason_codes")
    require(isinstance(statuses,dict) and isinstance(reasons,dict)
            and set(statuses)==set(scope) and set(reasons)==set(scope),
            "EXACT_PER_SYMBOL_PARTITION")
    require(all(v in STATUS_ALLOWED for v in statuses.values())
            and all(isinstance(v,str) and v for v in reasons.values()),
            "INVALID_STATUS_OR_REASON")
    require(all(statuses[s]=="SHADOW_SHARES_VINTAGE_ONLY"
                or statuses[s].startswith("UNKNOWN") for s in scope),
            "STATUS_ESCALATION_FORBIDDEN")
    required_statuses=dict(sorted(Counter(statuses.values()).items()))
    required_reasons=dict(sorted(Counter(reasons.values()).items()))
    require(report.get("status_counts")==required_statuses,
            "REPORTED_STATUS_COUNTS_INCONSISTENT")
    require(report.get("reason_counts")==required_reasons,
            "REPORTED_REASON_COUNTS_INCONSISTENT")
    remediation=Counter(root_cause_class(statuses[s],reasons[s],s) for s in scope)
    require(report.get("remediation_counts")==dict(sorted(remediation.items()))
            and report.get("remediation_count_exact") is True,
            "REMEDIATION_INCONSISTENT")
    if report["transport"]=="BLOCKED_FAIR_ACCESS_STOP":
        require(any(v=="UNKNOWN_NOT_ATTEMPTED_UPSTREAM_SEC_BLOCK" for v in statuses.values()),
                "UNATTESTED_TRANSPORT_STOP")
    else:
        require("UNKNOWN_NOT_ATTEMPTED_UPSTREAM_SEC_BLOCK" not in statuses.values(),
                "FALSE_COMPLETE_TRANSPORT")
    return {
        "schema":"XRAY_SEC_FULL_SCOPE_RELEASE_GUARD_V1",
        "status":"VERIFIED_SHADOW_ONLY",
        "asof_et":report["asof_et"],
        "scope_count":len(scope),
        "status_counts":required_statuses,
        "reason_counts":required_reasons,
        "remediation_counts":dict(sorted(remediation.items())),
        "primary_mc_count":0,"market_cap_calculated":False,
        "price_binding_attested":False,"corporate_action_binding_attested":False,
        "can_register_R92":False,"notification_delivered":False,
        "execution":"NONE","real_money":"NO-GO",
    }

def fixture():
    price={"asof_et":"2026-10-09","pass_symbols":["AAPL","NVDA"],"pass_count":2}
    master={"asof_et":"2026-10-09","queue_total":2}
    pb=(json.dumps(price,sort_keys=True)+"\n").encode()
    mb=(json.dumps(master,sort_keys=True)+"\n").encode()
    statuses={"AAPL":"SHADOW_SHARES_VINTAGE_ONLY","NVDA":"UNKNOWN"}
    reasons={"AAPL":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED",
             "NVDA":"NO_SEC_DEI_OR_GAAP_SHARES_FACT"}
    repairs=Counter(root_cause_class(statuses[s],reasons[s],s) for s in statuses)
    report={
        "schema":SCHEMA,"source":"SEC_EDGAR_OFFICIAL","asof_et":"2026-10-09",
        "price_git_blob_sha":git_blob_sha(pb),"master_git_blob_sha":git_blob_sha(mb),
        "sample_scope_sha256":symbol_hash(price["pass_symbols"]),
        "full_current_price_pass_scope":True,"batch_offset":0,"batch_limit":2,
        "sample_count":2,"ticker_map_timestamp":"CURRENT_ONLY_NOT_HISTORICAL_PIT",
        "official_exchange_current_mapping_only":True,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "production_alpha_authority":False,"c417_primary_mc_count":0,
        "market_cap_calculated":False,"price_binding_attested":False,
        "corporate_action_binding_attested":False,"no_real_candidate_claim":True,
        "transport":"SEC_OFFICIAL_MULTI_REQUESTS_COMPLETE_WITH_UNKNOWN_ALLOWED",
        "statuses":statuses,"reason_codes":reasons,
        "status_counts":dict(Counter(statuses.values())),
        "reason_counts":dict(Counter(reasons.values())),
        "remediation_counts":dict(sorted(repairs.items())),
        "remediation_count_exact":True}
    return report,price,master,pb,mb

def selftest():
    parts=fixture()
    passed=validate(*parts)
    require(passed["scope_count"]==2 and passed["primary_mc_count"]==0
            and passed["can_register_R92"] is False,"POSITIVE_SHADOW_ONLY")
    # Second positive: preserving the exact same authority under JSON roundtrip.
    clone=tuple(json.loads(json.dumps(x)) if isinstance(x,dict) else x for x in parts)
    require(validate(*clone)["status"]=="VERIFIED_SHADOW_ONLY","ROUNDTRIP")
    def negative(tag,change):
        a=copy.deepcopy(parts)
        change(a)
        try:validate(*a)
        except ValueError:return
        raise AssertionError("SEC_FULL_SCOPE_NEGATIVE_BYPASS:"+tag)
    checks=[
      ("ASOF",lambda a:a[0].update(asof_et="2026-10-08")),
      ("SCHEMA",lambda a:a[0].update(schema="WRONG")),
      ("PRICE_BLOB",lambda a:a[0].update(price_git_blob_sha="0"*40)),
      ("MASTER_BLOB",lambda a:a[0].update(master_git_blob_sha="0"*40)),
      ("SCOPE_HASH",lambda a:a[0].update(sample_scope_sha256="0"*64)),
      ("COUNT",lambda a:a[0].update(sample_count=1)),
      ("BATCH",lambda a:a[0].update(batch_limit=1)),
      ("ADDED_STATUS",lambda a:a[0]["statuses"].update(FAKE="UNKNOWN")),
      ("MISSING_REASON",lambda a:a[0]["reason_codes"].pop("AAPL")),
      ("WRONG_STATUS_COUNT",lambda a:a[0]["status_counts"].update(UNKNOWN=2)),
      ("WRONG_REASON_COUNT",lambda a:a[0]["reason_counts"].update(BOGUS=1)),
      ("WRONG_REMEDIATION",lambda a:a[0]["remediation_counts"].update(BOGUS=1)),
      ("FAKE_PRIMARY",lambda a:a[0].update(c417_primary_mc_count=2)),
      ("FAKE_MARKET_CAP",lambda a:a[0].update(market_cap_calculated=True)),
      ("FAKE_PRICE_RIGHT",lambda a:a[0].update(price_binding_attested=True)),
      ("FAKE_CORP_ACTION",lambda a:a[0].update(corporate_action_binding_attested=True)),
      ("FAKE_R92",lambda a:a[0].update(no_real_candidate_claim=False)),
      ("SILENT_TRANSPORT",lambda a:a[0].update(transport="BLOCKED_CONFIG")),
      ("PIT_MAP_FICTION",lambda a:a[0].update(ticker_map_timestamp="PIT_VERIFIED")),
      ("UNKNOWN_TO_PASS",lambda a:a[0]["statuses"].update(NVDA="PASS")),
      ("TAMPERED_SOURCE_SCOPE",lambda a:a[1]["pass_symbols"].append("FAKE")),
      ("DISABLE_FAIL_CLOSED",lambda a:a[0].update(unknown_never_pass=False)),
    ]
    for label,change in checks:
        negative(label,change)
    print("XRAY_SEC_FULL_SCOPE_RELEASE_SELFTEST=PASS_2_POSITIVE_22_NEGATIVE_NO_MC_NO_R92_PYTHON_O_SAFE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--artifact",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.artifact:
        p.error("--artifact required without --selftest")
    report=json.loads(args.artifact.read_text(encoding="utf-8"))
    pb=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    mb=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    result=validate(report,json.loads(pb),json.loads(mb),pb,mb)
    print("XRAY_SEC_FULL_SCOPE_RELEASE="+result["status"]+"_"+
          str(result["scope_count"]))
    print("XRAY_SEC_FULL_SCOPE_COUNTS="+json.dumps(result["status_counts"],sort_keys=True))
    print("XRAY_SEC_FULL_SCOPE_PRIMARY=0_NO_C417_AUTHORITY")

if __name__=="__main__":
    main()
