#!/usr/bin/env python3
"""One-time bootstrap for the encrypted Longbridge MCP /v2 ACCOUNT token vault.

Inputs are GitHub Actions secrets:
- LONGBRIDGE_AGENT_AUTH_CODE: one-time packed Longbridge Agent Auth Code
- XRAY_ACCOUNT_TOKEN_FERNET_KEY: Fernet key used only to encrypt/decrypt the vault

The auth code and tokens are never printed or persisted in plaintext.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from account_longbridge_mcp_v2_vault import VAULT_PATH, save_vault

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_mcp_v2_bootstrap_state.json"
AUTH_CODE_ENV = "LONGBRIDGE_AGENT_AUTH_CODE"
TOKEN_URL = "https://openapi.longbridge.com/oauth2/token"
REDIRECT_URI = "https://open.longbridge.com/connect/done"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class BootstrapError(RuntimeError):
    pass


def _b58decode(value: str) -> bytes:
    raw = (value or "").strip().strip('"').strip("'").strip(chr(96))
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


def unpack_agent_code(value: str) -> tuple[str, str]:
    data = _b58decode(value)
    if len(data) < 3 or data[0] != 0x01:
        raise BootstrapError("AUTH_CODE_PACKED_FORMAT_INVALID")
    cid_len = data[1]
    if cid_len <= 0 or len(data) <= 2 + cid_len:
        raise BootstrapError("AUTH_CODE_PACKED_FORMAT_INVALID")
    try:
        client_id = data[2:2 + cid_len].decode("utf-8")
        code = data[2 + cid_len:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BootstrapError("AUTH_CODE_UTF8_INVALID") from exc
    if not client_id or not code:
        raise BootstrapError("AUTH_CODE_PACKED_FORMAT_INVALID")
    return client_id, code


def _exchange(client_id: str, code: str) -> dict[str, Any]:
    form = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
    }).encode()
    req = Request(
        TOKEN_URL,
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except HTTPError as exc:
        raise BootstrapError(f"TOKEN_EXCHANGE_HTTP_{getattr(exc,'code',0)}") from None
    except (URLError, TimeoutError):
        raise BootstrapError("TOKEN_EXCHANGE_NETWORK_ERROR") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise BootstrapError("TOKEN_EXCHANGE_INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise BootstrapError("TOKEN_EXCHANGE_NOT_OBJECT")
    return payload


def build_vault_payload(client_id: str, token: Mapping[str, Any], *, now_epoch: int | None = None) -> dict[str, Any]:
    access = str(token.get("access_token") or "").strip()
    refresh = str(token.get("refresh_token") or "").strip()
    scopes = {x for x in str(token.get("scope") or "").split() if x}
    try:
        expires_in = int(token.get("expires_in"))
    except (TypeError, ValueError):
        raise BootstrapError("TOKEN_EXPIRES_IN_MISSING") from None

    if not access or not refresh:
        raise BootstrapError("TOKEN_ACCESS_OR_REFRESH_MISSING")
    if expires_in <= 300:
        raise BootstrapError("TOKEN_EXPIRY_TOO_SHORT")
    if "account.read" not in scopes:
        raise BootstrapError("ACCOUNT_READ_SCOPE_MISSING")
    if "trade.write" in scopes:
        raise BootstrapError("TRADE_WRITE_SCOPE_FORBIDDEN")

    now = int(time.time() if now_epoch is None else now_epoch)
    return {
        "schema": "XRAY_LONGBRIDGE_MCP_V2_ENCRYPTED_TOKEN_V1",
        "client_id": client_id,
        "access_token": access,
        "refresh_token": refresh,
        "token_type": str(token.get("token_type") or "Bearer"),
        "scopes": sorted(scopes),
        "issued_at_epoch": now,
        "expires_at_epoch": now + expires_in,
        "bootstrap_epoch": now,
    }


def _public(status: str, reason_code: str, *, scopes: list[str] | None = None, expires_in: int | None = None) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_MCP_V2_BOOTSTRAP_STATE_V1",
        "status": status,
        "reason_code": reason_code,
        "provider": "LONGBRIDGE_HOSTED_MCP_V2",
        "required_scope": "account.read",
        "trade_write_scope_allowed": False,
        "scopes": scopes or [],
        "expires_in": expires_in,
        "encrypted_vault_path": str(VAULT_PATH.relative_to(ROOT.parent)),
        "private_values_persisted": False,
        "secret_values_persisted": False,
        "execution": "NONE",
        "real_money": "NO-GO",
    }


def main() -> None:
    code = os.getenv(AUTH_CODE_ENV, "")
    try:
        client_id, raw_code = unpack_agent_code(code)
        token = _exchange(client_id, raw_code)
        vault = build_vault_payload(client_id, token)
        save_vault(vault)
        state = _public(
            "PASS",
            "ENCRYPTED_ACCOUNT_READ_VAULT_CREATED",
            scopes=vault["scopes"],
            expires_in=int(vault["expires_at_epoch"]) - int(vault["issued_at_epoch"]),
        )
    except Exception as exc:
        reason = str(exc) if str(exc) else type(exc).__name__
        state = _public("BLOCKED", reason)
    OUT.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, sort_keys=True))
    if state["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
