#!/usr/bin/env python3
"""XRAY read-only Longbridge hosted-MCP ACCOUNT probe.

Uses a pre-authorized least-privilege Bearer token from Longbridge Agent Auth /
standard MCP authorization. The token should carry ACCOUNT permission only.

The probe calls exactly two read-only tools:
- account_balance
- stock_positions

No private account values, positions, identifiers, or bearer tokens are ever
serialized to the public state file or stdout.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_mcp_probe_state.json"
TOKEN_ENV = "LONGBRIDGE_MCP_BEARER_TOKEN"
MCP_URL = "https://mcp.longbridge.com"
REQUIRED_TOOLS = ("account_balance", "stock_positions")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state(
    *,
    status: str,
    reason_code: str,
    network_attempted: bool,
    balance_parseable: bool = False,
    positions_parseable: bool = False,
    manifest_verified: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_LONGBRIDGE_HOSTED_MCP_PROBE_V1",
        "generated_at_utc": _now_utc(),
        "provider": "LONGBRIDGE_HOSTED_MCP",
        "status": status,
        "reason_code": reason_code,
        "network_attempted": bool(network_attempted),
        "tool_manifest_verified": bool(manifest_verified),
        "balance_parseable": bool(balance_parseable),
        "positions_parseable": bool(positions_parseable),
        "empty_positions_are_known_exposure": True,
        "same_run_required_calls": list(REQUIRED_TOOLS),
        "private_values_persisted": False,
        "secret_values_persisted": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "alpha_authority": False,
        "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None,
        "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT") or None,
    }


def _result_parseable(result: Any, *, allow_empty: bool) -> bool:
    if result is None or bool(getattr(result, "is_error", False)):
        return False
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        if allow_empty:
            return isinstance(structured, (dict, list))
        try:
            return len(structured) > 0
        except TypeError:
            return True
    content = getattr(result, "content", None)
    if content is None:
        return False
    try:
        items = list(content)
    except TypeError:
        return False
    if allow_empty and not items:
        return True
    for item in items:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            if allow_empty:
                return True
            if text.strip():
                return True
    return False


async def _live_probe(token: str) -> dict[str, Any]:
    try:
        import httpx2
        from mcp.client import Client
        from mcp.client.streamable_http import streamable_http_client
    except Exception:
        return _state(
            status="UNKNOWN_RUNTIME_DEPENDENCY_ERROR",
            reason_code="MCP_CLIENT_IMPORT_FAILED",
            network_attempted=False,
        )

    try:
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx2.Timeout(30.0, read=120.0),
        ) as http_client:
            transport = streamable_http_client(MCP_URL, http_client=http_client)
            async with Client(transport) as client:
                listed = await client.list_tools()
                names = {str(t.name) for t in listed.tools}
                if not set(REQUIRED_TOOLS).issubset(names):
                    return _state(
                        status="BLOCKED_REQUIRED_TOOLS_NOT_EXPOSED",
                        reason_code="HOSTED_MCP_ACCOUNT_TOOLS_MISSING",
                        network_attempted=True,
                        manifest_verified=False,
                    )
                balance = await client.call_tool("account_balance", {})
                balance_ok = _result_parseable(balance, allow_empty=False)
                positions = await client.call_tool("stock_positions", {})
                positions_ok = _result_parseable(positions, allow_empty=True)
                passed = balance_ok and positions_ok
                return _state(
                    status="PASS" if passed else "UNKNOWN_UNPARSEABLE_RESPONSE",
                    reason_code="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS" if passed else "READ_RESPONSE_NOT_PARSEABLE",
                    network_attempted=True,
                    balance_parseable=balance_ok,
                    positions_parseable=positions_ok,
                    manifest_verified=True,
                )
    except Exception as exc:
        name = type(exc).__name__.upper()
        reason = "HOSTED_MCP_AUTH_OR_SCOPE_ERROR" if any(x in name for x in ("AUTH", "HTTP", "MCP")) else "HOSTED_MCP_PROVIDER_ERROR"
        return _state(
            status="BLOCKED_AUTH_OR_SCOPE" if reason == "HOSTED_MCP_AUTH_OR_SCOPE_ERROR" else "UNKNOWN_PROVIDER_ERROR",
            reason_code=reason,
            network_attempted=True,
        )


def run_probe(env: dict[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    token = str(source.get(TOKEN_ENV) or "").strip()
    if not token:
        return _state(
            status="BLOCKED_MISSING_CREDENTIALS",
            reason_code="HOSTED_MCP_BEARER_SECRET_NOT_CONFIGURED",
            network_attempted=False,
        )
    return asyncio.run(_live_probe(token))


def write_state(state: dict[str, Any], output: Path = OUT) -> None:
    output.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")


def main() -> None:
    state = run_probe()
    write_state(state)
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
