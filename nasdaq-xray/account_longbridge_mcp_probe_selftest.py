#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROBE=ROOT/"account_longbridge_mcp_probe.py"

spec=importlib.util.spec_from_file_location("xray_account_mcp_probe",PROBE)
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
    assert missing["reason_code"]=="HOSTED_MCP_BEARER_SECRET_NOT_CONFIGURED"

    for key in ("private_values_persisted","secret_values_persisted"):
        assert missing[key] is False

    assert mod._result_parseable(Obj(structured_content={"ok":True}),allow_empty=False)
    assert mod._result_parseable(Obj(structured_content=[]),allow_empty=True)
    assert not mod._result_parseable(Obj(structured_content=[]),allow_empty=False)
    assert mod._result_parseable(Obj(content=[Text("{}")]),allow_empty=True)
    assert not mod._result_parseable(Obj(is_error=True,structured_content={"x":1}),allow_empty=True)

    source=PROBE.read_text()
    for required in ('call_tool("account_balance"', 'call_tool("stock_positions"'):
        assert required in source
    for forbidden in (
        'call_tool("place_order"',
        'call_tool("submit_order"',
        'call_tool("replace_order"',
        'call_tool("cancel_order"',
        'call_tool("today_orders"',
        'call_tool("history_orders"',
        'call_tool("fund_positions"',
    ):
        assert forbidden not in source

    encoded=json.dumps(missing).lower()
    assert "bearer " not in encoded
    print("XRAY_ACCOUNT_HOSTED_MCP_SELFTEST=PASS")

if __name__=="__main__":
    main()
