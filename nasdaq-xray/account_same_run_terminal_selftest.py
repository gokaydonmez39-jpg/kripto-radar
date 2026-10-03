#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE/"build_current_terminal.py"

spec=importlib.util.spec_from_file_location("xray_terminal_account_test",SRC)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

def write(path:Path,obj):
    path.write_text(json.dumps(obj)+"\n")

def base_adapter():
    return {
      "schema":"XRAY_ACCOUNT_PROVIDER_ADAPTER_CONTRACT_V1",
      "execution":"NONE","real_money":"NO-GO",
      "adapters":{
        "LONGBRIDGE":{"status":"BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED"},
        "LONGBRIDGE_DIRECT_OPENAPI":{"status":"ELIGIBLE_FRESH_SAME_RUN_ONLY"},
        "LONGBRIDGE_HOSTED_MCP":{"status":"SUPERSEDED_BY_RESTRICTED_V2"},
        "LONGBRIDGE_HOSTED_MCP_V2":{"status":"ELIGIBLE_FRESH_SAME_RUN_ONLY"},
      },
    }

def blob(path:Path):
    return mod.blob_sha(path)

def base_gate(adapter_sha):
    return {
      "schema":"XRAY_ACCOUNT_GATE_CONTRACT_V1",
      "provider":"PROVIDER_NEUTRAL",
      "execution":"NONE","real_money":"NO-GO",
      "current_status":"ACCOUNT_BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED",
      "current_adapter":"LONGBRIDGE",
      "adapter_contract":{"path":"nasdaq-xray/account_provider_adapter_contract.json","blob_sha":adapter_sha},
    }

def g9():
    return {
      "schema":"XRAY_STRICT_G9_RUNTIME_V1",
      "execution":"NONE","real_money":"NO-GO",
      "g9_pass":False,"status":"BLOCKED_ENTITLEMENT_AUTHORITY_UNPROVEN",
      "adapter_status":"BLOCKED_NO_PROVIDER_SELECTED",
    }

def live(run_id,status="PASS",provider="LONGBRIDGE_DIRECT_OPENAPI"):
    passed=status=="PASS"
    schemas={
      "LONGBRIDGE_DIRECT_OPENAPI":"XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1",
      "LONGBRIDGE_HOSTED_MCP":"XRAY_ACCOUNT_LONGBRIDGE_HOSTED_MCP_PROBE_V1",
      "LONGBRIDGE_HOSTED_MCP_V2":"XRAY_ACCOUNT_LONGBRIDGE_MCP_V2_PROBE_V1",
    }
    schema=schemas[provider]
    return {
      "schema":schema,
      "provider":provider,
      "execution":"NONE","real_money":"NO-GO",
      "status":status,
      "reason_code":"SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS" if passed else "REQUIRED_SECRET_ENV_NOT_CONFIGURED",
      "network_attempted":passed,
      "balance_parseable":passed,
      "positions_parseable":passed,
      "private_values_persisted":False,
      "secret_values_persisted":False,
      "workflow_run_id":run_id,
      "workflow_run_attempt":"1",
    }

def evaluate(td:Path,live_obj=None,current_run="run-1"):
    ap=td/"adapter.json"; gp=td/"gate.json"; g9p=td/"g9.json"; lp=td/"live.json"
    write(ap,base_adapter())
    write(gp,base_gate(blob(ap)))
    write(g9p,g9())
    mod.GATE_FILES={"g9_runtime":g9p,"account_gate":gp,"account_adapter":ap}
    prior_live=os.environ.get("XRAY_ACCOUNT_LIVE_PROBE_STATE")
    prior_run=os.environ.get("GITHUB_RUN_ID")
    try:
        os.environ["GITHUB_RUN_ID"]=current_run
        if live_obj is None:
            os.environ.pop("XRAY_ACCOUNT_LIVE_PROBE_STATE",None)
        else:
            write(lp,live_obj)
            os.environ["XRAY_ACCOUNT_LIVE_PROBE_STATE"]=str(lp)
        return mod.load_gate_reporting()
    finally:
        if prior_live is None: os.environ.pop("XRAY_ACCOUNT_LIVE_PROBE_STATE",None)
        else: os.environ["XRAY_ACCOUNT_LIVE_PROBE_STATE"]=prior_live
        if prior_run is None: os.environ.pop("GITHUB_RUN_ID",None)
        else: os.environ["GITHUB_RUN_ID"]=prior_run

def main():
    with tempfile.TemporaryDirectory() as d:
        td=Path(d)
        blocked=evaluate(td)
        assert blocked["account_status"]=="ACCOUNT_BLOCKED_SCOPE_NOT_GRANTED_OR_ACCOUNT_UNSUPPORTED"
        assert "account_live_probe" not in blocked["evidence"]

        passed=evaluate(td,live("run-1"),"run-1")
        assert passed["account_status"]=="ACCOUNT_PASS"
        ev=passed["evidence"]["account_live_probe"]
        assert ev["same_run_attested"] is True
        assert ev["provider"]=="LONGBRIDGE_DIRECT_OPENAPI"
        assert ev["private_values_persisted"] is False
        assert ev["secret_values_persisted"] is False
        assert passed["evidence"]["account_gate"]["current_adapter"]=="LONGBRIDGE_DIRECT_OPENAPI"

        hosted_v2=evaluate(td,live("run-hosted-v2","PASS","LONGBRIDGE_HOSTED_MCP_V2"),"run-hosted-v2")
        assert hosted_v2["account_status"]=="ACCOUNT_PASS"
        hev=hosted_v2["evidence"]["account_live_probe"]
        assert hev["provider"]=="LONGBRIDGE_HOSTED_MCP_V2"
        assert hev["same_run_attested"] is True
        assert hosted_v2["evidence"]["account_gate"]["current_adapter"]=="LONGBRIDGE_HOSTED_MCP_V2"

        stale=evaluate(td,live("old-run"),"run-2")
        assert stale["account_status"]!="ACCOUNT_PASS"

        missing=evaluate(td,live("run-3","BLOCKED_MISSING_CREDENTIALS"),"run-3")
        assert missing["account_status"]!="ACCOUNT_PASS"
        assert missing["evidence"]["account_live_probe"]["network_attempted"] is False

    print("XRAY_ACCOUNT_SAME_RUN_TERMINAL_SELFTEST=PASS")

if __name__=="__main__":
    main()
