#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROBE=ROOT/"account_longbridge_mcp_v2_probe.py"

spec=importlib.util.spec_from_file_location("xray_account_mcp_v2_probe",PROBE)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class Obj:
    def __init__(self, *, is_error=False, structured_content=None, content=None):
        self.is_error=is_error
        self.structured_content=structured_content
        self.content=[] if content is None else content


class Text:
    def __init__(self,text): self.text=text


def main():
    missing=mod.run_probe(env={})
    assert missing["status"]=="BLOCKED_MISSING_CREDENTIALS"
    assert missing["network_attempted"] is False
    assert missing["reason_code"]=="MCP_V2_BEARER_OR_VAULT_NOT_CONFIGURED"
    assert missing["provider"]=="LONGBRIDGE_HOSTED_MCP_V2"
    assert missing["endpoint"]=="https://mcp.longbridge.com/v2"
    assert missing["required_oauth_scope"]=="account.read"
    assert missing["trade_write_scope_required"] is False
    assert missing["tool_manifest_verified"] is False
    assert missing["credential_source"]=="NONE"
    assert isinstance(missing["encrypted_vault_present"], bool)
    assert missing["token_refresh_performed"] is False
    assert missing["encrypted_vault_updated"] is False
    assert missing["trade_write_surface_exposed"] is None

    for key in ("private_values_persisted","secret_values_persisted"):
        assert missing[key] is False

    assert mod._result_parseable(Obj(structured_content={"balances":[{"currency":"USD"}]}),allow_empty=False)
    assert mod._result_parseable(Obj(structured_content=[]),allow_empty=True)
    assert not mod._result_parseable(Obj(structured_content=[]),allow_empty=False)
    assert mod._result_parseable(Obj(content=[Text("{}")]),allow_empty=True)
    assert not mod._result_parseable(Obj(is_error=True,structured_content={"x":1}),allow_empty=True)

    assert set(mod.REQUIRED_TOOLS)=={"account_balance","stock_positions"}
    forbidden=set(mod.FORBIDDEN_WRITE_TOOLS)
    for name in (
        "submit_order","cancel_order","replace_order","submit_multileg_order",
        "fund_submit_order","fund_cancel_order","withdrawals",
        "dca_create","grid_submit",
    ):
        assert name in forbidden

    source=PROBE.read_text()
    for required in (
        'client.call_tool("account_balance"',
        'client.call_tool("stock_positions"',
        'MCP_URL = "https://mcp.longbridge.com/v2"',
    ):
        assert required in source
    for forbidden_call in (
        'client.call_tool("submit_order"',
        'client.call_tool("cancel_order"',
        'client.call_tool("replace_order"',
        'client.call_tool("withdrawals"',
        'client.call_tool("dca_create"',
        'client.call_tool("grid_submit"',
    ):
        assert forbidden_call not in source

    encoded=json.dumps(missing).lower()
    assert "bearer " not in encoded
    print("XRAY_ACCOUNT_MCP_V2_SELFTEST=PASS")


if __name__=="__main__":
    main()
