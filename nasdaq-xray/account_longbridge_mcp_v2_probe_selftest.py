#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROBE = ROOT / "account_longbridge_mcp_v2_probe.py"

spec = importlib.util.spec_from_file_location("xray_mcp_v2_probe", PROBE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def assert_public_only(state):
    encoded = json.dumps(state).lower()
    for forbidden in (
        "secret-bearer",
        "private-balance",
        "private-position",
        "account-id-123",
    ):
        assert forbidden not in encoded
    assert state["private_values_persisted"] is False
    assert state["secret_values_persisted"] is False
    assert state["execution"] == "NONE"
    assert state["real_money"] == "NO-GO"
    assert state["trade_write_scope_required"] is False
    assert state["trade_write_surface_exposed"] is False


def success_transport(calls):
    def post(url, bearer, payload):
        calls.append((url, bearer, payload))
        assert url == mod.MCP_URL
        assert bearer == "secret-bearer"
        name = payload["params"]["name"]
        if name == "account_balance":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                [
                                    {
                                        "account": "account-id-123",
                                        "value": "private-balance",
                                    }
                                ]
                            ),
                        }
                    ]
                },
            }
        if name == "stock_positions":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "structuredContent": {
                        "list": [
                            {
                                "stock_info": [
                                    {
                                        "symbol": "PRIVATE.US",
                                        "value": "private-position",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        raise AssertionError(name)

    return post


def main():
    called = False

    def must_not_call(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network called without bearer")

    missing = mod.run_probe(env={}, post_json=must_not_call)
    assert missing["status"] == "BLOCKED_MISSING_CREDENTIALS"
    assert missing["network_attempted"] is False
    assert called is False
    assert_public_only(missing)

    calls = []
    passed = mod.run_probe(
        env={mod.TOKEN_ENV: "secret-bearer"},
        post_json=success_transport(calls),
    )
    assert passed["status"] == "PASS"
    assert passed["balance_parseable"] is True
    assert passed["positions_parseable"] is True
    assert [x[2]["params"]["name"] for x in calls] == [
        "account_balance",
        "stock_positions",
    ]
    assert_public_only(passed)

    def denied(url, bearer, payload):
        raise mod.McpReadError("AUTH_OR_HTTP_ERROR", 403)

    blocked = mod.run_probe(
        env={mod.TOKEN_ENV: "secret-bearer"},
        post_json=denied,
    )
    assert blocked["status"] == "BLOCKED_SCOPE_OR_TOKEN"
    assert (
        blocked["reason_code"]
        == "MCP_V2_ACCOUNT_READ_NOT_AUTHORIZED_OR_TOKEN_INVALID"
    )
    assert_public_only(blocked)

    def rpc_scope_denied(url, bearer, payload):
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "error": {"code": -32001, "message": "hidden provider text"},
        }

    blocked_rpc = mod.run_probe(
        env={mod.TOKEN_ENV: "secret-bearer"},
        post_json=rpc_scope_denied,
    )
    assert blocked_rpc["status"] == "BLOCKED_SCOPE_OR_TOKEN"
    assert_public_only(blocked_rpc)

    # Empty holdings remain a valid known-zero exposure response.
    def zero_positions(url, bearer, payload):
        name = payload["params"]["name"]
        if name == "account_balance":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"structuredContent": {"balances": [{"currency": "USD"}]}},
            }
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {"structuredContent": {"list": []}},
        }

    zero = mod.run_probe(
        env={mod.TOKEN_ENV: "secret-bearer"},
        post_json=zero_positions,
    )
    assert zero["status"] == "PASS"
    assert_public_only(zero)

    source = PROBE.read_text()
    for forbidden_call in (
        "submit_order",
        "cancel_order",
        "replace_order",
        "withdrawals",
        "dca_create",
        "grid_submit",
    ):
        assert forbidden_call not in source

    print("XRAY_ACCOUNT_MCP_V2_SELFTEST=PASS")


if __name__ == "__main__":
    main()
