#!/usr/bin/env python3
"""One-time bootstrap for the official Longbridge hosted MCP ACCOUNT bearer vault.

Official flow:
- generate a one-time Agent Auth Code at https://open.longbridge.com/connect,
- connect unauthenticated to https://mcp.longbridge.com/agent,
- redeem the code via the exposed `authenticate` tool,
- verify the returned Bearer against https://mcp.longbridge.com,
- require account_balance + stock_positions and require write tools to be absent,
- persist only Fernet-encrypted bearer ciphertext.

The auth code and bearer token are never printed or persisted in plaintext.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from account_longbridge_mcp_v2_vault import (
    AGENT_MCP_URL,
    MAIN_MCP_URL,
    VAULT_PATH,
    resolve_vault_key,
    save_vault,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_mcp_v2_bootstrap_state.json"
AUTH_CODE_ENV = "LONGBRIDGE_AGENT_AUTH_CODE"
REQUIRED_TOOLS = {"account_balance", "stock_positions"}
FORBIDDEN_WRITE_TOOLS = {
    "submit_order", "cancel_order", "replace_order", "submit_multileg_order",
    "fund_submit_order", "fund_cancel_order", "withdrawals",
    "dca_create", "dca_update", "dca_pause", "dca_resume", "dca_stop",
    "grid_submit", "grid_replace", "grid_cancel",
}


class BootstrapError(RuntimeError):
    pass


def _tool_schema(tool: Any) -> dict[str, Any]:
    for attr in ("inputSchema", "input_schema"):
        value = getattr(tool, attr, None)
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, dict):
            return value
    if hasattr(tool, "model_dump"):
        data = tool.model_dump()
        for key in ("inputSchema", "input_schema"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _auth_arg_name(tool: Any) -> str:
    schema = _tool_schema(tool)
    props = schema.get("properties") if isinstance(schema, dict) else None
    props = props if isinstance(props, dict) else {}
    for key in ("auth_code", "code", "authorization_code"):
        if key in props:
            return key
    required = schema.get("required") if isinstance(schema, dict) else None
    required = [str(x) for x in required] if isinstance(required, list) else []
    if len(required) == 1 and required[0] in props:
        return required[0]
    string_props = [
        str(k) for k, v in props.items()
        if isinstance(v, dict) and str(v.get("type") or "") == "string"
    ]
    if len(string_props) == 1:
        return string_props[0]
    raise BootstrapError("AUTHENTICATE_INPUT_SCHEMA_AMBIGUOUS")


def _candidate_token(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("bearer_token", "access_token", "token", "authorization"):
            if key in value:
                found = _candidate_token(value[key])
                if found:
                    return found
        for child in value.values():
            found = _candidate_token(child)
            if found:
                return found
        return None
    if isinstance(value, list):
        for child in value:
            found = _candidate_token(child)
            if found:
                return found
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        parsed = json.loads(s)
    except Exception:
        parsed = None
    if parsed is not None and parsed != s:
        found = _candidate_token(parsed)
        if found:
            return found
    m = re.search(r"Authorization\s*:\s*Bearer\s+([^\s\"'<>]+)", s, flags=re.I)
    if m:
        return m.group(1).strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    # Avoid treating arbitrary prose as a credential.
    if len(s) >= 16 and not any(ch.isspace() for ch in s):
        return s
    return None


def _extract_token(result: Any) -> str:
    structured = getattr(result, "structured_content", None)
    found = _candidate_token(structured)
    if found:
        return found
    content = getattr(result, "content", None)
    if content is not None:
        try:
            for item in list(content):
                found = _candidate_token(getattr(item, "text", None))
                if found:
                    return found
        except TypeError:
            pass
    raise BootstrapError("AUTHENTICATE_BEARER_TOKEN_NOT_FOUND")


async def _redeem(auth_code: str) -> tuple[str, set[str]]:
    try:
        import httpx2
        from mcp.client import Client
        from mcp.client.streamable_http import streamable_http_client
    except Exception as exc:
        raise BootstrapError("MCP_CLIENT_IMPORT_FAILED") from exc

    async with httpx2.AsyncClient(timeout=httpx2.Timeout(30.0, read=120.0)) as http_client:
        transport = streamable_http_client(AGENT_MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            listed = await client.list_tools()
            names = {str(t.name) for t in listed.tools}
            if names != {"authenticate"}:
                raise BootstrapError("AGENT_UNAUTHORIZED_TOOL_SURFACE_NOT_AUTHENTICATE_ONLY")
            tool = next(t for t in listed.tools if str(t.name) == "authenticate")
            arg_name = _auth_arg_name(tool)
            result = await client.call_tool("authenticate", {arg_name: auth_code})
            if bool(getattr(result, "is_error", False)):
                raise BootstrapError("AGENT_AUTHENTICATE_TOOL_ERROR")
            token = _extract_token(result)

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(
        headers=headers,
        timeout=httpx2.Timeout(30.0, read=120.0),
    ) as http_client:
        transport = streamable_http_client(MAIN_MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            listed = await client.list_tools()
            names = {str(t.name) for t in listed.tools}
    if not REQUIRED_TOOLS.issubset(names):
        raise BootstrapError("MAIN_MCP_ACCOUNT_TOOLS_MISSING")
    if FORBIDDEN_WRITE_TOOLS & names:
        raise BootstrapError("MAIN_MCP_WRITE_SURFACE_PRESENT")
    return token, names


def build_vault_payload(token: str, manifest: set[str], *, now_epoch: int | None = None) -> dict[str, Any]:
    token = str(token or "").strip()
    if len(token) < 16 or any(ch.isspace() for ch in token):
        raise BootstrapError("BEARER_TOKEN_INVALID")
    if not REQUIRED_TOOLS.issubset(manifest):
        raise BootstrapError("ACCOUNT_TOOL_MANIFEST_NOT_VERIFIED")
    if FORBIDDEN_WRITE_TOOLS & set(manifest):
        raise BootstrapError("WRITE_SURFACE_PRESENT")
    now = int(time.time() if now_epoch is None else now_epoch)
    return {
        "schema": "XRAY_LONGBRIDGE_OFFICIAL_MCP_AGENT_BEARER_V1",
        "bearer_token": token,
        "main_endpoint": MAIN_MCP_URL,
        "agent_endpoint": AGENT_MCP_URL,
        "account_tools_verified": True,
        "write_surface_absent": True,
        "created_at_epoch": now,
        "protocol": "OFFICIAL_AGENT_AUTH_CODE_TO_MAIN_MCP",
    }


def _public(status: str, reason_code: str) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_MCP_V2_BOOTSTRAP_STATE_V2",
        "status": status,
        "reason_code": reason_code,
        "provider": "LONGBRIDGE_HOSTED_MCP_V2",
        "protocol": "OFFICIAL_AGENT_AUTH_CODE_TO_MAIN_MCP",
        "agent_endpoint": AGENT_MCP_URL,
        "main_endpoint": MAIN_MCP_URL,
        "required_permission": "ACCOUNT",
        "write_surface_allowed": False,
        "encrypted_vault_path": str(VAULT_PATH.relative_to(ROOT.parent)),
        "private_values_persisted": False,
        "secret_values_persisted": False,
        "execution": "NONE",
        "real_money": "NO-GO",
    }


def main() -> None:
    code = str(os.getenv(AUTH_CODE_ENV) or "").strip()
    state: dict[str, Any]
    try:
        if not code:
            raise BootstrapError("AUTH_CODE_MISSING")
        # Explicit independent Fernet key is mandatory; never derive it from
        # the short one-time Agent Auth Code.
        resolve_vault_key()
        token, manifest = asyncio.run(_redeem(code))
        vault = build_vault_payload(token, manifest)
        save_vault(vault)
        state = _public("PASS", "OFFICIAL_AGENT_AUTH_BEARER_VAULT_CREATED")
    except Exception as exc:
        reason = str(exc) if str(exc) else type(exc).__name__
        state = _public("BLOCKED", reason)
    OUT.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, sort_keys=True))
    if state["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
