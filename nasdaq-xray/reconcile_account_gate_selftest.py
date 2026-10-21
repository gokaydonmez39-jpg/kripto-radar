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

def check(ok):
    if not ok:
        raise AssertionError("ACCOUNT_OUTPUT_INVARIANT_FAILED")

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
        check(out["current_status"]==gate["current_status"])
        check(out["current_status"] not in {"PASS","ACCOUNT_PASS"})
        check(out["adapter_contract"]["blob_sha"]==mod.blob_sha(ap))
        check(out["adapter_registry_sync"]=="EVIDENCE_PIN_ONLY_NEVER_PASS_AUTHORITY")
        check(out["binding_revalidation"]["status"]=="EXACT")
        check(out["binding_revalidation"]["adapter_blob_sha"]==mod.blob_sha(ap))
        if "RALLIES_ACCOUNT_READ_V1" in adapter_obj.get("adapters",{}):
            check(out["alternate_adapter_candidates"]["RALLIES_ACCOUNT_READ_V1"]==adapter_obj["adapters"]["RALLIES_ACCOUNT_READ_V1"]["status"])
        check(out["no_policy_weakening"] is True)

def watchdog_account_heartbeat_contract(account_workflow: str, watchdog_workflow: str) -> None:
    """Brokerless contract: NO hourly account writer and NO watchdog account wake.

    The 15-minute official-session root watchdog remains independently active
    via its Live Truth and E2E completions. Offline historical account
    verification can only run manually or as a read-only PR test.
    """
    def triggers(doc):
        parts=doc.split("\non:\n",1)
        if len(parts)!=2:raise ValueError("WORKFLOW_TRIGGER_MISSING")
        return parts[1].split("\npermissions:\n",1)[0]

    a=triggers(account_workflow)
    w=triggers(watchdog_workflow)
    if not account_workflow.startswith("name: XRAY Account Gate Reconciler\n"):
        raise ValueError("ACCOUNT_WORKFLOW_NAME_DRIFT")
    if ('  schedule:\n' in a or '  push:\n' in a
        or '  workflow_dispatch:\n' not in a
        or '\npermissions:\n  contents: read\n' not in account_workflow
        or 'git push origin' in account_workflow
        or 'secrets.' in account_workflow):
        raise ValueError("BROKERLESS_ACCOUNT_OFFLINE_ONLY_CONTRACT")
    if ('  workflow_run:\n' not in w
        or '    types: [completed]\n    branches: [main]' not in w
        or '  workflow_dispatch:\n' not in w
        or w.count('  schedule:\n') != 1
        or w.count('    - cron: "*/15 * * * 1-5"') != 1
        or '"XRAY Account Gate Reconciler"' in w):
        raise ValueError("WATCHDOG_BROKERLESS_INDEPENDENT_WAKE_INVALID")
    for required in ('"XRAY Live Truth Attestation"',
                     '"XRAY E2E Production Readiness (Fail-Closed)"',
                     "python nasdaq-xray/github_native_root_watchdog.py --out",
                     'cancel-in-progress: false',
                     'contents: read', 'actions: write'):
        if required not in watchdog_workflow:
            raise ValueError("WATCHDOG_REQUIRED_INDEPENDENT_GUARD_MISSING")

def selftest_account_watchdog_topology():
    account_path=HERE.parent/".github/workflows/xray-account-gate-reconcile.yml"
    watchdog_path=HERE.parent/".github/workflows/xray-github-native-root-watchdog.yml"
    a=account_path.read_text()
    w=watchdog_path.read_text()
    watchdog_account_heartbeat_contract(a,w)
    mutations=(
        (a.replace("name: XRAY Account Gate Reconciler\n",
                   "name: XRAY Account Gate Reconciler Drift\n"),w),
        (a.replace("  workflow_dispatch:\n",
                   '  schedule:\n    - cron: "12 * * * *"\n  workflow_dispatch:\n'),w),
        (a.replace("  workflow_dispatch:\n",
                   "  push:\n    branches: [main]\n  workflow_dispatch:\n"),w),
        (a.replace("contents: read","contents: write"),w),
        (a.replace("  workflow_dispatch:\n",""),w),
        (a+"\n# git push origin main\n",w),
        (a+"\n# secrets.ACCOUNT_FORBIDDEN\n",w),
        (a,w.replace('cron: "*/15 * * * 1-5"',
                     'cron: "*/1 * * * 1-5"')),
        (a,w.replace('      - "XRAY E2E Production Readiness (Fail-Closed)"',
                     '      - "XRAY E2E Production Readiness (Fail-Closed)"\n      - "XRAY Account Gate Reconciler"')),
        (a,w.replace('      - "XRAY Live Truth Attestation"','')),
        (a,w.replace('      - "XRAY E2E Production Readiness (Fail-Closed)"','')),
        (a,w.replace('cancel-in-progress: false','cancel-in-progress: true')),
    )
    for bad_account,bad_watchdog in mutations:
        try:
            watchdog_account_heartbeat_contract(bad_account,bad_watchdog)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_ACCOUNT_WATCHDOG_TOPOLOGY_ACCEPTED")
    print("XRAY_ACCOUNT_TO_ROOT_WATCHDOG_TOPOLOGY=PASS_12_BROKERLESS_NEGATIVES")

def main():
    selftest_account_watchdog_topology()
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

    # Fail-closed under both python and python -O.
    bad=base_gate();bad["schema"]="INVALID";run_case(bad,adapters(),False,"ACCOUNT_GATE_SCHEMA_INVALID")
    bad=adapters();bad["schema"]="INVALID";run_case(base_gate(),bad,False,"ACCOUNT_ADAPTER_SCHEMA_INVALID")
    bad=base_gate();bad["execution"]="TRADE";run_case(bad,adapters(),False,"ACCOUNT_GATE_EXECUTION_UNSAFE")
    bad=adapters();bad["real_money"]="GO";run_case(base_gate(),bad,False,"ACCOUNT_ADAPTER_EXECUTION_UNSAFE")
    bad=base_gate();bad["provider"]="BAD";run_case(bad,adapters(),False,"ACCOUNT_GATE_PROVIDER_INVALID")
    print("XRAY_ACCOUNT_GATE_RECONCILER_SELFTEST=PASS_2_POSITIVE_7_NEGATIVE_OPTIMIZED_SAFE")

if __name__=="__main__":
    main()
