#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TARGET=ROOT/"select_account_live_probe.py"
spec=importlib.util.spec_from_file_location("selector",TARGET)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def state(provider,status,run_id,attempted=True,balance=True,positions=True,reason="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS"):
    schema={
      "LONGBRIDGE_HOSTED_MCP_V2":"XRAY_ACCOUNT_LONGBRIDGE_MCP_V2_PROBE_V1",
      "LONGBRIDGE_DIRECT_OPENAPI":"XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1",
    }[provider]
    return {
      "schema":schema,
      "provider":provider,
      "status":status,
      "reason_code":reason,
      "network_attempted":attempted,
      "balance_parseable":balance,
      "positions_parseable":positions,
      "private_values_persisted":False,
      "secret_values_persisted":False,
      "execution":"NONE",
      "real_money":"NO-GO",
      "workflow_run_id":run_id,
    }


def main():
    os.environ["GITHUB_RUN_ID"]="42"

    v2=state("LONGBRIDGE_HOSTED_MCP_V2","PASS","42")
    direct=state("LONGBRIDGE_DIRECT_OPENAPI","PASS","42")
    c=mod.choose([direct,v2])
    assert c["provider"]=="LONGBRIDGE_HOSTED_MCP_V2"
    assert c["status"]=="PASS"

    stale_v2=state("LONGBRIDGE_HOSTED_MCP_V2","PASS","41")
    c=mod.choose([direct,stale_v2])
    assert c["provider"]=="LONGBRIDGE_DIRECT_OPENAPI"
    assert c["status"]=="PASS"

    blocked_v2=state(
      "LONGBRIDGE_HOSTED_MCP_V2","BLOCKED_SCOPE_OR_TOKEN","42",
      attempted=True,balance=False,positions=False,
      reason="MCP_V2_ACCOUNT_READ_NOT_AUTHORIZED_OR_TOKEN_INVALID",
    )
    missing_direct=state(
      "LONGBRIDGE_DIRECT_OPENAPI","BLOCKED_MISSING_CREDENTIALS","42",
      attempted=False,balance=False,positions=False,
      reason="REQUIRED_SECRET_ENV_NOT_CONFIGURED",
    )
    c=mod.choose([missing_direct,blocked_v2])
    assert c["provider"]=="LONGBRIDGE_HOSTED_MCP_V2"
    assert c["status"]=="BLOCKED_SCOPE_OR_TOKEN"

    stale_only=mod.choose([stale_v2])
    assert stale_only["status"]=="BLOCKED_STALE_PROBE"
    assert stale_only["reason_code"]=="PASS_STATE_NOT_FROM_CURRENT_WORKFLOW_RUN"
    assert stale_only["balance_parseable"] is False
    assert stale_only["positions_parseable"] is False
    assert mod.valid_pass(stale_only) is False

    none=mod.choose([])
    assert none["status"]=="BLOCKED_MISSING_CREDENTIALS"
    assert none["provider"]=="NONE"

    print("XRAY_ACCOUNT_SELECTOR_SELFTEST=PASS")


if __name__=="__main__":
    main()
