#!/usr/bin/env python3
from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_data_lineage_registry.json"
POL=ROOT/"chatgpt_compiled_policy_v3.json"
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def load(p):
    try:return json.loads(p.read_text())
    except Exception:return {}
def main():
    top=load(POL); payload=json.loads(top.get("payload_json") or "{}")
    roles=[
      ("universe","canonical_current_master_manifest.json",payload.get("universe",{}).get("primary"),"NASDAQTRADER"),
      ("price_dv20","canonical_current_price_dv20.json",payload.get("dv20",{}).get("primary"),"RALLIES"),
      ("market_cap","canonical_mc_bridge_20261002_c417.json",payload.get("mc",{}).get("primary"),"BIGDATA_PRIMARY_WITH_FALLBACKS"),
      ("events","canonical_current_event_state.json",payload.get("events_account",{}).get("events"),"SEC_ISSUER_IR_NASDAQ"),
      ("settlement","canonical_resolver_bridge_20261002_c417.json",payload.get("settlement",{}).get("primary"),"ALPACA_HISTORICAL_SIP_WITH_COMPILED_FAILOVER"),
      ("g9","strict_g9_runtime_state.json",payload.get("g9",{}).get("A"),"STRICT_G9_GATE"),
      ("account","account_gate_contract.json",payload.get("events_account",{}).get("account"),"ACCOUNT_ADAPTER_GATE"),
    ]
    rows=[]
    for field,fn,requested,actual_class in roles:
        p=ROOT/fn; j=load(p)
        rows.append({
          "field":field,"artifact":fn,"artifact_sha256":sha(p),
          "provider_requested":requested or "UNSPECIFIED_IN_POLICY",
          "provider_actual":j.get("provider_actual") or j.get("provider") or actual_class,
          "endpoint":j.get("endpoint") or "NOT_EMBEDDED",
          "feed":j.get("feed") or "NOT_EMBEDDED",
          "authority_class":j.get("authority") or actual_class,
          "entitlement_class":j.get("entitlement_class") or "NOT_EMBEDDED",
          "source_timestamp":j.get("source_timestamp") or j.get("market_timestamp") or j.get("asof_et") or j.get("ASOF_ET"),
          "received_at":j.get("generated_at_utc") or j.get("updated_at_utc") or "NOT_EMBEDDED",
          "fallback_used":j.get("fallback_used") if "fallback_used" in j else "NOT_EMBEDDED",
          "fallback_reason":j.get("fallback_reason") or "NOT_EMBEDDED",
          "schema_version":j.get("schema") or "MISSING",
          "license_class":j.get("license_class") or "NOT_EMBEDDED",
          "health":"PASS_ARTIFACT_PRESENT" if p.exists() else "UNKNOWN_ARTIFACT_MISSING",
          "freshness":"ASOF_BOUND" if (j.get("asof_et") or j.get("ASOF_ET")) else "NOT_EMBEDDED"
        })
    missing=sum(1 for r in rows if "NOT_EMBEDDED" in {str(r["endpoint"]),str(r["feed"]),str(r["entitlement_class"]),str(r["license_class"])})
    out={"schema":"XRAY_DATA_LINEAGE_REGISTRY_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "configured_provider_not_actual_provider":True,"unknown_never_pass":True,
         "status":"PARTIAL_LINEAGE" if missing else "COMPLETE_LINEAGE","missing_field_level_receipt_count":missing,
         "records":rows,"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"records":len(rows),"partial":missing},sort_keys=True))
if __name__=="__main__": main()
