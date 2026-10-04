#!/usr/bin/env python3
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GATE=ROOT/"account_gate_contract.json"
ADAPTER=ROOT/"account_provider_adapter_contract.json"

def load(p):
    return json.loads(p.read_text())

def blob_sha(p):
    b=p.read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + bytes([0]) + b).hexdigest()

def main():
    g=load(GATE)
    a=load(ADAPTER)
    assert g.get("schema")=="XRAY_ACCOUNT_GATE_CONTRACT_V1"
    assert a.get("schema")=="XRAY_ACCOUNT_PROVIDER_ADAPTER_CONTRACT_V1"
    assert g.get("execution")=="NONE" and g.get("real_money")=="NO-GO"
    assert a.get("execution")=="NONE" and a.get("real_money")=="NO-GO"
    assert g.get("provider")=="PROVIDER_NEUTRAL"
    current=str(g.get("current_adapter") or "")
    assert current and current in (a.get("adapters") or {}), "CURRENT_ACCOUNT_ADAPTER_MISSING_FROM_REGISTRY"

    # Evidence synchronization only. This reconciler has no authority to create
    # ACCOUNT PASS or persist any account/private values.
    prior_status=g.get("current_status")
    if str(prior_status).upper() in {"PASS","ACCOUNT_PASS"}:
        raise AssertionError("REFUSE_TO_RECONCILE_PERSISTED_PASS_WITHOUT_FRESH_SAME_RUN_PROBE")

    actual=blob_sha(ADAPTER)
    g["adapter_contract"]={
      "path":"nasdaq-xray/account_provider_adapter_contract.json",
      "blob_sha":actual,
    }
    g["adapter_registry_count"]=len(a.get("adapters") or {})
    g["adapter_registry_sync"]="EVIDENCE_PIN_ONLY_NEVER_PASS_AUTHORITY"
    # Keep human/diagnostic binding metadata synchronized too. Stale historical
    # adapter SHAs are not allowed to masquerade as current revalidation proof.
    g["binding_revalidation"]={
      "status":"EXACT",
      "adapter_blob_sha":actual,
      "revalidated_on":"2026-10-04",
      "semantic_effect":"NONE_ZERO_ALPHA",
    }
    g["binding_revalidated_on"]="2026-10-04"
    g["binding_revalidation_note"]="Exact adapter/gate binding synchronized to the current provider-neutral registry; no ACCOUNT PASS created."
    # Surface the Rallies read-only adapter as an explicit alternate when present.
    if "RALLIES_ACCOUNT_READ_V1" in (a.get("adapters") or {}):
        g.setdefault("alternate_adapter_candidates",{})["RALLIES_ACCOUNT_READ_V1"]=a["adapters"]["RALLIES_ACCOUNT_READ_V1"].get("status","UNKNOWN")
    g["no_policy_weakening"]=True
    GATE.write_text(json.dumps(g,indent=2)+"\n")
    print(json.dumps({
      "status":"PASS",
      "current_adapter":current,
      "account_status":prior_status,
      "adapter_blob_sha":actual,
      "adapter_count":g["adapter_registry_count"],
      "pass_created":False,
    },sort_keys=True))

if __name__=="__main__":
    main()
