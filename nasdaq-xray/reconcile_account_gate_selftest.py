#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE/"reconcile_account_gate.py"

def load_mod():
    spec=importlib.util.spec_from_file_location("account_reconcile_test",SRC)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def write_json(path,obj):
    path.write_text(json.dumps(obj,sort_keys=True)+"\n")

def base_gate(status="ACCOUNT_BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED",adapter="LONGBRIDGE"):
    return {
      "schema":"XRAY_ACCOUNT_GATE_CONTRACT_V1",
      "provider":"PROVIDER_NEUTRAL",
      "current_adapter":adapter,
      "current_status":status,
      "execution":"NONE",
      "real_money":"NO-GO",
      "adapter_contract":{"path":"nasdaq-xray/account_provider_adapter_contract.json","blob_sha":"OLD"},
    }

def adapters(include_current=True):
    a={
      "schema":"XRAY_ACCOUNT_PROVIDER_ADAPTER_CONTRACT_V1",
      "execution":"NONE",
      "real_money":"NO-GO",
      "adapters":{
        "ALTERNATE":{"status":"NOT_CONNECTED"}
      }
    }
    if include_current:
        a["adapters"]["LONGBRIDGE"]={"status":"BLOCKED_SCOPE"}
    return a

def run_case(gate,adapter_obj,expect_ok,expect_error=None):
    mod=load_mod()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        gp=td/"gate.json"; ap=td/"adapter.json"
        write_json(gp,gate); write_json(ap,adapter_obj)
        mod.GATE=gp; mod.ADAPTER=ap
        try:
            mod.main()
            if not expect_ok:
                raise AssertionError("negative account reconcile case unexpectedly passed")
        except AssertionError as e:
            if expect_ok:
                raise
            if expect_error and expect_error not in str(e):
                raise AssertionError(f"wrong error: {e}")
            return
        out=json.loads(gp.read_text())
        assert out["current_status"]==gate["current_status"]
        assert out["current_status"] not in {"PASS","ACCOUNT_PASS"}
        assert out["adapter_contract"]["blob_sha"]==mod.blob_sha(ap)
        assert out["adapter_registry_sync"]=="EVIDENCE_PIN_ONLY_NEVER_PASS_AUTHORITY"
        assert out["binding_revalidation"]["status"]=="EXACT"
        assert out["binding_revalidation"]["adapter_blob_sha"]==mod.blob_sha(ap)
        if "RALLIES_ACCOUNT_READ_V1" in adapter_obj.get("adapters",{}):
            assert out["alternate_adapter_candidates"]["RALLIES_ACCOUNT_READ_V1"]==adapter_obj["adapters"]["RALLIES_ACCOUNT_READ_V1"]["status"]
        assert out["no_policy_weakening"] is True

def main():
    # 1) BLOCKED state may synchronize evidence only; status cannot change.
    run_case(base_gate(),adapters(),True)

    # 2) A persisted PASS can never be repinned into a fresh PASS by this reconciler.
    run_case(base_gate("ACCOUNT_PASS"),adapters(),False,
             "REFUSE_TO_RECONCILE_PERSISTED_PASS_WITHOUT_FRESH_SAME_RUN_PROBE")

    # 3) Current adapter disappearing from registry must fail closed.
    run_case(base_gate(),adapters(False),False,
             "CURRENT_ACCOUNT_ADAPTER_MISSING_FROM_REGISTRY")

    # 4) A new read-only alternate is surfaced without changing blocked status.
    a=adapters()
    a["adapters"]["RALLIES_ACCOUNT_READ_V1"]={"status":"BLOCKED_NO_CURRENT_PORTFOLIO_WITNESS"}
    run_case(base_gate(),a,True)

    print("XRAY_ACCOUNT_GATE_RECONCILER_SELFTEST=PASS")

if __name__=="__main__":
    main()
