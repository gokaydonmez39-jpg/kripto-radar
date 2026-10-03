#!/usr/bin/env python3
"""Encrypted OAuth token vault for the official Longbridge hosted MCP ACCOUNT path.

Official flow:
  1) generate a one-time Agent Auth Code at https://open.longbridge.com/connect,
  2) redeem it with authenticate on https://mcp.longbridge.com/agent,
  3) use the returned Bearer on https://mcp.longbridge.com,
  4) refresh through https://mcp.longbridge.com/oauth2/token before expiry.

Only ciphertext is persisted in the repository. The Fernet key MUST come from
GitHub Actions secrets. Auth codes, access/refresh tokens and account data are
never persisted in plaintext or printed.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent
VAULT_PATH = ROOT / "account_longbridge_mcp_v2_token.enc"
FERNET_KEY_ENV = "XRAY_ACCOUNT_TOKEN_FERNET_KEY"
MAIN_MCP_URL = "https://mcp.longbridge.com/v2"
AGENT_MCP_URL = "https://mcp.longbridge.com/agent"
TOKEN_URL = "https://mcp.longbridge.com/oauth2/token"
REFRESH_SKEW_SECONDS = 300
SCHEMA = "XRAY_LONGBRIDGE_OFFICIAL_MCP_AGENT_OAUTH_V2"


class VaultError(RuntimeError):
    pass


class TokenRefreshError(RuntimeError):
    pass


def resolve_vault_key(source_env: Mapping[str, str] | None = None) -> str:
    source = os.environ if source_env is None else source_env
    explicit = str(source.get(FERNET_KEY_ENV) or "").strip()
    if not explicit:
        raise VaultError("VAULT_KEY_MISSING")
    return explicit


def _fernet(key: str) -> Fernet:
    value = (key or "").strip().encode()
    if not value:
        raise VaultError("VAULT_KEY_MISSING")
    try:
        return Fernet(value)
    except Exception as exc:
        raise VaultError("VAULT_KEY_INVALID") from exc


def encrypt_payload(payload: Mapping[str, Any], key: str) -> bytes:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
    return _fernet(key).encrypt(raw) + b"\n"


def decrypt_payload(ciphertext: bytes, key: str) -> dict[str, Any]:
    try:
        raw = _fernet(key).decrypt(ciphertext.strip())
    except InvalidToken as exc:
        raise VaultError("VAULT_DECRYPT_FAILED") from exc
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise VaultError("VAULT_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise VaultError("VAULT_PAYLOAD_NOT_OBJECT")
    return value


def validate_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != SCHEMA:
        raise VaultError("VAULT_SCHEMA_INVALID")
    for field in ("client_id", "access_token", "refresh_token"):
        value = str(payload.get(field) or "").strip()
        if len(value) < 8 or any(ch.isspace() for ch in value):
            raise VaultError(f"VAULT_{field.upper()}_INVALID")
    try:
        expires_at = int(payload.get("expires_at_epoch") or 0)
    except (TypeError, ValueError):
        raise VaultError("VAULT_EXPIRES_AT_INVALID") from None
    if expires_at <= 0:
        raise VaultError("VAULT_EXPIRES_AT_INVALID")
    scopes = {str(x) for x in payload.get("scopes") or []}
    if "account.read" not in scopes:
        raise VaultError("VAULT_ACCOUNT_READ_SCOPE_MISSING")
    if "trade.write" in scopes:
        raise VaultError("VAULT_TRADE_WRITE_SCOPE_FORBIDDEN")
    if payload.get("main_endpoint") != MAIN_MCP_URL:
        raise VaultError("VAULT_MAIN_ENDPOINT_INVALID")
    if payload.get("agent_endpoint") != AGENT_MCP_URL:
        raise VaultError("VAULT_AGENT_ENDPOINT_INVALID")
    if payload.get("account_tools_verified") is not True:
        raise VaultError("VAULT_ACCOUNT_TOOL_MANIFEST_NOT_VERIFIED")
    if payload.get("write_surface_absent") is not True:
        raise VaultError("VAULT_WRITE_SURFACE_NOT_ABSENT")


def load_vault(path: Path = VAULT_PATH, *, key: str | None = None) -> dict[str, Any]:
    if not path.exists():
        raise VaultError("VAULT_FILE_MISSING")
    secret = key if key is not None else resolve_vault_key()
    payload = decrypt_payload(path.read_bytes(), secret)
    validate_payload(payload)
    return payload


def save_vault(payload: Mapping[str, Any], path: Path = VAULT_PATH, *, key: str | None = None) -> None:
    validate_payload(payload)
    secret = key if key is not None else resolve_vault_key()
    data = encrypt_payload(payload, secret)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _http_json(
    method: str,
    url: str,
    *,
    form: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    body = urlencode(dict(form or {})).encode() if form is not None else None
    hdrs = dict(headers or {})
    if form is not None:
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = Request(url, data=body, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except HTTPError as exc:
        raise TokenRefreshError(f"HTTP_{getattr(exc, 'code', 0)}") from None
    except (URLError, TimeoutError):
        raise TokenRefreshError("NETWORK_ERROR") from None
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        raise TokenRefreshError("TOKEN_RESPONSE_INVALID_JSON") from None
    if not isinstance(value, dict):
        raise TokenRefreshError("TOKEN_RESPONSE_NOT_OBJECT")
    return value


def access_token_from_vault(
    payload: dict[str, Any],
    *,
    now_epoch: int | None = None,
    http_json: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], bool]:
    """Return usable access token, refreshing encrypted state if needed."""
    validate_payload(payload)
    now = int(time.time() if now_epoch is None else now_epoch)
    expires_at = int(payload["expires_at_epoch"])
    if expires_at - now > REFRESH_SKEW_SECONDS:
        return str(payload["access_token"]), payload, False

    call = http_json or _http_json
    form = {
        "grant_type": "refresh_token",
        "client_id": str(payload["client_id"]),
        "refresh_token": str(payload["refresh_token"]),
    }
    result = call("POST", TOKEN_URL, form=form, headers={})
    access = str(result.get("access_token") or "").strip()
    if not access:
        raise TokenRefreshError("REFRESH_ACCESS_TOKEN_MISSING")
    refresh = str(result.get("refresh_token") or "").strip() or str(payload["refresh_token"])
    try:
        expires_in = int(result.get("expires_in"))
    except (TypeError, ValueError):
        raise TokenRefreshError("REFRESH_EXPIRES_IN_MISSING") from None
    if expires_in <= REFRESH_SKEW_SECONDS:
        raise TokenRefreshError("REFRESH_EXPIRY_TOO_SHORT")

    returned_scope = [x for x in str(result.get("scope") or "").split() if x]
    scopes = returned_scope or [str(x) for x in payload.get("scopes") or []]
    scope_set = set(scopes)
    if "account.read" not in scope_set:
        raise TokenRefreshError("REFRESH_ACCOUNT_READ_SCOPE_MISSING")
    if "trade.write" in scope_set:
        raise TokenRefreshError("REFRESH_TRADE_WRITE_SCOPE_FORBIDDEN")

    updated = dict(payload)
    updated.update({
        "access_token": access,
        "refresh_token": refresh,
        "token_type": str(result.get("token_type") or payload.get("token_type") or "Bearer"),
        "scopes": sorted(scope_set),
        "issued_at_epoch": now,
        "expires_at_epoch": now + expires_in,
        "last_refresh_epoch": now,
    })
    validate_payload(updated)
    return access, updated, True


def bearer_from_vault(payload: Mapping[str, Any], *, now_epoch: int | None = None) -> str:
    """Return bearer only when comfortably valid; refresh belongs to pre-probe phase."""
    validate_payload(payload)
    now = int(time.time() if now_epoch is None else now_epoch)
    if int(payload["expires_at_epoch"]) - now <= REFRESH_SKEW_SECONDS:
        raise VaultError("VAULT_BEARER_EXPIRED_OR_EXPIRING")
    return str(payload["access_token"])


if __name__ == "__main__":
    raise SystemExit("library module")
