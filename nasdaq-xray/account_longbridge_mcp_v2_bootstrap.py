#!/usr/bin/env python3
"""One-time bootstrap for the official Longbridge hosted MCP ACCOUNT OAuth vault.

Official flow:
- generate one-time Agent Auth Code at https://open.longbridge.com/connect,
- redeem it through authenticate on https://mcp.longbridge.com/agent,
- require account.read and reject trade.write,
- verify the resulting Bearer on https://mcp.longbridge.com exposes
  account_balance + stock_positions and no known execution/money-movement tools,
- persist only Fernet-encrypted access+refresh OAuth state.

No auth code, token, account id, balance or position is printed or stored plaintext.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from account_longbridge_mcp_v2_vault import (
    AGENT_MCP_URL,
    MAIN_MCP_URL,
    SCHEMA,
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
    "fund_submit_order", "fund_cancel_order", "withdrawals", "deposits", "bank_cards",
    "dca_create", "dca_update", "dca_pause", "dca_resume", "dca_stop",
    "grid_submit", "grid_replace", "grid_cancel", "grid_suspend", "grid_restart",
}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


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


def _b58decode(value: str) -> bytes:
    raw = str(value or "").strip().strip('"').strip("'").strip(chr(96))
    if not raw:
        raise BootstrapError("AUTH_CODE_MISSING")
    n = 0
    for ch in raw:
        try:
            n = n * 58 + B58.index(ch)
        except ValueError as exc:
            raise BootstrapError("AUTH_CODE_NOT_BASE58") from exc
    decoded = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(raw) - len(raw.lstrip("1"))
    return b"\x00" * pad + decoded


def packed_client_id(value: str) -> str:
    data = _b58decode(value)
    if len(data) < 3 or data[0] != 0x01:
        raise BootstrapError("AUTH_CODE_PACKED_FORMAT_INVALID")
    cid_len = int(data[1])
    if cid_len <= 0 or len(data) <= 2 + cid_len:
        raise BootstrapError("AUTH_CODE_PACKED_FORMAT_INVALID")
    try:
        client_id = data[2:2 + cid_len].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BootstrapError("AUTH_CODE_CLIENT_ID_UTF8_INVALID") from exc
    if not client_id:
        raise BootstrapError("AUTH_CODE_CLIENT_ID_MISSING")
    return client_id


def _candidate_auth_payload(value: Any) -> dict[str, Any] | None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        if value.get("access_token") and value.get("refresh_token"):
            return value
        for child in value.values():
            found = _candidate_auth_payload(child)
            if found:
                return found
        return None
    if isinstance(value, list):
        for child in value:
            found = _candidate_auth_payload(child)
            if found:
                return found
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except Exception:
            return None
        if parsed == value:
            return None
        return _candidate_auth_payload(parsed)
    return None


def _extract_auth_payload(result: Any) -> dict[str, Any]:
    found = _candidate_auth_payload(getattr(result, "structured_content", None))
    if found:
        return found
    content = getattr(result, "content", None)
    if content is not None:
        try:
            for item in list(content):
                found = _candidate_auth_payload(getattr(item, "text", None))
                if found:
                    return found
        except TypeError:
            pass
    raise BootstrapError("AUTHENTICATE_OAUTH_BUNDLE_NOT_FOUND")


async def _redeem(auth_code: str) -> tuple[str, dict[str, Any], set[str]]:
    try:
        import httpx2
        from mcp.client import Client
        from mcp.client.streamable_http import streamable_http_client
    except Exception as exc:
        raise BootstrapError("MCP_CLIENT_IMPORT_FAILED") from exc

    client_id = packed_client_id(auth_code)

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
            oauth = _extract_auth_payload(result)

    access = str(oauth.get("access_token") or "").strip()
    if not access:
        raise BootstrapError("AUTHENTICATE_ACCESS_TOKEN_MISSING")
    headers = {"Authorization": f"Bearer {access}"}
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
    return client_id, oauth, names


def build_vault_payload(
    client_id: str,
    token: Mapping[str, Any],
    manifest: set[str],
    *,
    now_epoch: int | None = None,
) -> dict[str, Any]:
    access = str(token.get("access_token") or "").strip()
    refresh = str(token.get("refresh_token") or "").strip()
    if len(access) < 8 or any(ch.isspace() for ch in access):
        raise BootstrapError("ACCESS_TOKEN_INVALID")
    if len(refresh) < 8 or any(ch.isspace() for ch in refresh):
        raise BootstrapError("REFRESH_TOKEN_INVALID")
    scopes = {x for x in str(token.get("scope") or "").split() if x}
    if "account.read" not in scopes:
        raise BootstrapError("ACCOUNT_READ_SCOPE_MISSING")
    if "trade.write" in scopes:
        raise BootstrapError("TRADE_WRITE_SCOPE_FORBIDDEN")
    try:
        expires_in = int(token.get("expires_in"))
    except (TypeError, ValueError):
        raise BootstrapError("TOKEN_EXPIRES_IN_MISSING") from None
    if expires_in <= 300:
        raise BootstrapError("TOKEN_EXPIRY_TOO_SHORT")
    if not REQUIRED_TOOLS.issubset(manifest):
        raise BootstrapError("ACCOUNT_TOOL_MANIFEST_NOT_VERIFIED")
    if FORBIDDEN_WRITE_TOOLS & set(manifest):
        raise BootstrapError("WRITE_SURFACE_PRESENT")

    now = int(time.time() if now_epoch is None else now_epoch)
    return {
        "schema": SCHEMA,
        "client_id": str(client_id),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": str(token.get("token_type") or "Bearer"),
        "scopes": sorted(scopes),
        "issued_at_epoch": now,
        "expires_at_epoch": now + expires_in,
        "main_endpoint": MAIN_MCP_URL,
        "agent_endpoint": AGENT_MCP_URL,
        "account_tools_verified": True,
        "write_surface_absent": True,
        "bootstrap_epoch": now,
        "protocol": "OFFICIAL_AGENT_AUTH_CODE_TO_MAIN_MCP_REFRESHABLE",
    }


def _public(status: str, reason_code: str) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_MCP_V2_BOOTSTRAP_STATE_V3",
        "status": status,
        "reason_code": reason_code,
        "provider": "LONGBRIDGE_HOSTED_MCP_V2",
        "protocol": "OFFICIAL_AGENT_AUTH_CODE_TO_MAIN_MCP_REFRESHABLE",
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
    try:
        if not code:
            raise BootstrapError("AUTH_CODE_MISSING")
        resolve_vault_key()  # independent Actions-only Fernet key is mandatory
        client_id, token, manifest = asyncio.run(_redeem(code))
        vault = build_vault_payload(client_id, token, manifest)
        save_vault(vault)
        state = _public("PASS", "OFFICIAL_AGENT_AUTH_REFRESHABLE_VAULT_CREATED")
    except Exception as exc:
        reason = str(exc) if str(exc) else type(exc).__name__
        state = _public("BLOCKED", reason)
    OUT.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, sort_keys=True))
    if state["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
