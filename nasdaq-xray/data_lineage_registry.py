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

CATALOG={
 "universe":{
   "artifact":"canonical_current_master_manifest.json",
   "endpoint":"NASDAQTRADER_SYMBOL_DIRECTORY",
   "feed":"NASDAQ_LISTED_DIRECTORY",
   "entitlement_class":"OFFICIAL_PUBLIC_CURRENT_DAY_DATA",
   "license_class":"NASDAQ_SOURCE_SPECIFIC_PUBLIC_TERMS",
   "actual":"NASDAQTRADER",
   "authority":"T0_EXCHANGE_IDENTITY",
 },
 "price_dv20":{
   "artifact":"canonical_current_price_dv20.json",
   "endpoint":"RALLIES_CONNECTED_CHATGPT_MARKET_DATA",
   "feed":"COMPLETED_SESSION_DAILY_AGGREGATES",
   "entitlement_class":"CURRENT_CONNECTED_PLATFORM_ACCESS_ZERO_COST_SURFACE",
   "license_class":"SURFACE_SPECIFIC_TERMS_NO_TRANSFER_TO_B2B_API",
   "actual":"RALLIES",
   "authority":"COMPILED_DV20_PRIMARY",
 },
 "market_cap":{
   "artifact":"canonical_mc_bridge_20261002_c417.json",
   "endpoint":"BIGDATA_CONNECTED_MARKET_CAP_WITH_COMPILED_FALLBACKS",
   "feed":"FINITE_USD_MARKET_CAP",
   "entitlement_class":"USAGE_METERED_CREDIT_SURFACE",
   "license_class":"NOT_PERMANENT_ZERO_CORE_MIGRATION_REQUIRED",
   "actual":"BIGDATA_PRIMARY_WITH_FALLBACKS",
   "authority":"COMPILED_C4_17_MC_AUTHORITY",
 },
 "events":{
   "artifact":"canonical_current_event_state.json",
   "endpoint":"SEC_ISSUER_IR_NASDAQ_OFFICIAL_RESOLUTION_CHAIN",
   "feed":"OFFICIAL_FILINGS_ISSUER_EVENTS_LISTING_HALTS",
   "entitlement_class":"PUBLIC_OFFICIAL_WITH_FAIR_ACCESS_OR_SOURCE_CADENCE",
   "license_class":"SOURCE_SPECIFIC_OFFICIAL_TERMS",
   "actual":"SEC_ISSUER_IR_NASDAQ",
   "authority":"T0_EVENT_CHAIN",
 },
 "settlement":{
   "artifact":"canonical_resolver_bridge_20261002_c417.json",
   "endpoint":"ALPACA_CONNECTED_HISTORICAL_SIP_WITH_RALLIES_LONGBRIDGE_FAILOVER",
   "feed":"COMPLETED_SESSION_HISTORICAL_OR_DELAYED_SIP_NON_G9",
   "entitlement_class":"ZERO_DOLLAR_DELAYED_HISTORICAL_WITH_PROVIDER_LIMITS",
   "license_class":"NON_G9_TEMPORARY_CORE_MIGRATION_REQUIRED",
   "actual":"ALPACA_HISTORICAL_SIP_WITH_COMPILED_FAILOVER",
   "authority":"C4_17_SETTLEMENT",
 },
 "g9":{
   "artifact":"strict_g9_runtime_state.json",
   "endpoint":"STRICT_G9_MULTI_PROVIDER_GATE",
   "feed":"NATIONAL_NBBO_PLUS_LAST_TRADE_REQUIRED",
   "entitlement_class":"UNPROVEN_PERMANENT_ZERO_AUTOMATED_NONDISPLAY",
   "license_class":"BLOCKED_UNTIL_PRIMARY_SOURCE_ENTITLEMENT_PROOF",
   "actual":"NONE_CURRENTLY_QUALIFYING",
   "authority":"STRICT_G9_GATE",
 },
 "account":{
   "artifact":"account_gate_contract.json",
   "endpoint":"PROVIDER_NEUTRAL_READ_ONLY_ACCOUNT_ADAPTER_GATE",
   "feed":"SAME_RUN_BALANCE_PLUS_POSITIONS",
   "entitlement_class":"CURRENT_ADAPTER_UNRESOLVED",
   "license_class":"PROVIDER_SPECIFIC_ACCOUNT_TERMS",
   "actual":"PROVIDER_NEUTRAL",
   "authority":"ACCOUNT_ADAPTER_GATE",
 },
}

def main():
    top=load(POL); payload=json.loads(top.get("payload_json") or "{}")
    requested={
      "universe":payload.get("universe",{}).get("primary"),
      "price_dv20":payload.get("dv20",{}).get("primary"),
      "market_cap":payload.get("mc",{}).get("primary"),
      "events":payload.get("events_account",{}).get("events"),
      "settlement":payload.get("settlement",{}).get("primary"),
      "g9":payload.get("g9",{}).get("A"),
      "account":payload.get("events_account",{}).get("account"),
    }
    rows=[]
    unresolved=0
    for field,cfg in CATALOG.items():
        p=ROOT/cfg["artifact"]; j=load(p)
        actual=j.get("provider_actual") or j.get("provider") or cfg["actual"]
        fallback_used=j.get("fallback_used") if "fallback_used" in j else "NOT_DECLARED_BY_ARTIFACT"
        fallback_reason=j.get("fallback_reason") or "NOT_DECLARED_BY_ARTIFACT"
        receipt={
          "field":field,"artifact":cfg["artifact"],"artifact_sha256":sha(p),
          "provider_requested":requested.get(field) or "UNSPECIFIED_IN_POLICY",
          "provider_actual":actual,
          "endpoint":cfg["endpoint"],"feed":cfg["feed"],
          "authority_class":j.get("authority") or cfg["authority"],
          "entitlement_class":cfg["entitlement_class"],
          "source_timestamp":j.get("source_timestamp") or j.get("market_timestamp") or j.get("asof_et") or j.get("ASOF_ET"),
          "received_at":j.get("generated_at_utc") or j.get("updated_at_utc") or "ARTIFACT_TIMESTAMP_NOT_EMBEDDED",
          "fallback_used":fallback_used,"fallback_reason":fallback_reason,
          "schema_version":j.get("schema") or "MISSING",
          "license_class":cfg["license_class"],
          "health":"PASS_ARTIFACT_PRESENT" if p.exists() else "UNKNOWN_ARTIFACT_MISSING",
          "freshness":"ASOF_BOUND" if (j.get("asof_et") or j.get("ASOF_ET")) else "GATE_OR_CONTRACT_STATE",
          "receipt_complete":bool(p.exists() and cfg["endpoint"] and cfg["feed"] and cfg["entitlement_class"] and cfg["license_class"])
        }
        if not receipt["receipt_complete"]: unresolved+=1
        rows.append(receipt)
    out={"schema":"XRAY_DATA_LINEAGE_REGISTRY_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "configured_provider_not_actual_provider":True,"unknown_never_pass":True,
         "status":"COMPLETE_LINEAGE_SCHEMA" if unresolved==0 else "PARTIAL_LINEAGE",
         "incomplete_receipt_count":unresolved,
         "gate_unknowns_are_preserved":True,
         "note":"COMPLETE_LINEAGE_SCHEMA means every tracked field has an explicit provenance/entitlement/license classification; it does not convert blocked G9 or ACCOUNT into PASS.",
         "records":rows,"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"records":len(rows),"incomplete":unresolved},sort_keys=True))
if __name__=="__main__": main()
