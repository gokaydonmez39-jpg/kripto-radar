#!/usr/bin/env python3
"""Four-source XRAY NASDAQ research admission: fail closed, stdlib only."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SCHEMA = "XRAY_NASDAQ_STRONG4_KRONOS_STYLE_V1"
EXPECTED = {
 "pydantic": ("pydantic/pydantic","2.14.3","MIT","P0"),
 "quantstats": ("ranaroussi/quantstats","0.0.86","Apache-2.0","P1"),
 "vectorbt": ("polakowo/vectorbt","1.2.0","Apache-2.0 WITH Commons Clause v1.0; restricted resale of software","P2"),
 "duckdb": ("duckdb/duckdb","2.0.0","MIT","P2"),
}
DENIED = (
 "can_issue_al","can_change_stop_target","can_place_order","can_write_private_sheet",
 "can_call_broker","can_call_external_vendor","can_emit_alert",
 "can_create_schedule","can_access_secrets","can_change_crypto",
 "can_modify_main","can_pay_vendor",
)
BASELINE_SHA = "b6dc10a0cdbb9774adb76f9720066b665fdeff56"
REGISTRY_SHA = "6547f095bae9c6ed7b5b43d55ba0fc11b0042d92"

def ensure(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)

def validate(doc: object) -> dict:
    ensure(type(doc) is dict and doc.get("schema") == SCHEMA, "SCHEMA_INVALID")
    ensure(doc.get("scope")=="personal-swing/research_lab; PR-ONLY; research only", "SCOPE_DRIFT")
    ensure(doc.get("main_baseline_sha")==BASELINE_SHA and
           doc.get("original_88_registry_sha")==REGISTRY_SHA, "BASELINE_DRIFT")
    core=doc.get("protected_contract")
    ensure(type(core) is dict and set(core)=={
      "universe","provider","timeframe","basis","stop_atr","target_atr",
      "tracking_xnas_sessions","execution","orders","new_paid_service","new_schedule",
      "crypto_change","canonical_change"}, "CORE_KEYS_INVALID")
    required={"universe":477,"provider":"Alpaca IEX","timeframe":"1Day",
              "basis":"RAW","stop_atr":2,"target_atr":4,"tracking_xnas_sessions":15,
              "execution":"NONE","orders":"NO_ORDER",
              "new_paid_service":False,"new_schedule":False,
              "crypto_change":False,"canonical_change":False}
    for k,v in required.items():
        ensure(type(core.get(k)) is type(v) and core[k]==v, "CORE_DRIFT_"+k)
    src=doc.get("sources")
    ensure(type(src) is list and len(src)==4,"REQUIRES_FOUR_CANDIDATES")
    seen=set()
    for item in src:
        ensure(type(item) is dict,"INVALID_CANDIDATE")
        id_=item.get("id")
        ensure(type(id_) is str and id_ in EXPECTED and id_ not in seen,"UNKNOWN_OR_DUPLICATE_CANDIDATE")
        seen.add(id_)
        repo,version,license_,priority=EXPECTED[id_]
        ensure(item.get("repo")==repo and item.get("reference_version")==version and
               item.get("distribution")==id_ and item.get("license")==license_ and
               item.get("priority")==priority,"SOURCE_IDENTITY_DRIFT")
        ensure(type(item.get("review_commit")) is str and
               re.fullmatch(r"[0-9a-f]{40}",item["review_commit"]) is not None,
               "SOURCE_REVIEW_SHA_INVALID")
        ensure(item.get("review_sha_not_installed_wheel_hash") is True,"SOURCE_ATTESTATION_DRIFT")
        ensure(item.get("admission")=="RESEARCH_PR_ONLY","ADMISSION_ESCALATED")
        for flag in ("actual_sdk_runtime_verified","actual_pit_verified","independent_oos_verified",
                     "production_authorized"):
            ensure(item.get(flag) is False, "UNPROVEN_"+flag)
        flags=item.get("permissions")
        ensure(type(flags) is dict and set(flags)==set(DENIED),"CAPABILITY_SET_CHANGED")
        for cap in DENIED:
            ensure(flags[cap] is False,"FORBIDDEN_"+cap)
        ensure(type(item.get("function")) is str and bool(item["function"].strip()),"EMPTY_PURPOSE")
    ensure(seen==set(EXPECTED),"CANDIDATE_COVERAGE_DRIFT")
    return {"schema":"XRAY_NASDAQ_STRONG4_ADMISSION_REPORT_V1",
            "status":"OFFLINE_CONTRACT_PASS_NO_SDK_OR_PRODUCTION_CLAIM",
            "candidates":sorted(seen),"sdk_runtime_pass_claims":0,
            "verified_alpha":False,"production_authorized":False,"orders":0,
            "new_schedules":0,"new_paid_services":0}

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--manifest", default=str(Path(__file__).with_name("strong4_manifest.json")))
    p.add_argument("--require-production", action="store_true")
    args=p.parse_args()
    try:
        result=validate(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
        print(json.dumps(result,sort_keys=True))
        return 3 if args.require_production else 0
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc)},sort_keys=True))
        return 3
if __name__=="__main__":
    raise SystemExit(main())
