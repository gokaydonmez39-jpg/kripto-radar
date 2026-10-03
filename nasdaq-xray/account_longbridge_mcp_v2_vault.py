#!/usr/bin/env python3
"""Encrypted bearer vault for the official Longbridge hosted MCP ACCOUNT path.

The documented Agent Auth flow is:
  1) generate a one-time code at https://open.longbridge.com/connect,
  2) redeem it with the `authenticate` tool on https://mcp.longbridge.com/agent,
  3) use the returned Bearer on https://mcp.longbridge.com.

Only ciphertext is persisted in the repository. The Fernet key MUST come from
GitHub Actions secrets. The one-time Agent Auth Code is never used as an
encryption key and is never persisted.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent
VAULT_PATH = ROOT / "account_longbridge_mcp_v2_token.enc"
FERNET_KEY_ENV = "XRAY_ACCOUNT_TOKEN_FERNET_KEY"
MAIN_MCP_URL = "https://mcp.longbridge.com"
AGENT_MCP_URL = "https://mcp.longbridge.com/agent"


class VaultError(RuntimeError):
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
    if payload.get("schema") != "XRAY_LONGBRIDGE_OFFICIAL_MCP_AGENT_BEARER_V1":
        raise VaultError("VAULT_SCHEMA_INVALID")
    token = str(payload.get("bearer_token") or "").strip()
    if len(token) < 16 or any(ch.isspace() for ch in token):
        raise VaultError("VAULT_BEARER_TOKEN_INVALID")
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


def bearer_from_vault(payload: Mapping[str, Any]) -> str:
    validate_payload(payload)
    return str(payload["bearer_token"])


if __name__ == "__main__":
    # Library-only module. Never print decrypted credential material.
    raise SystemExit("library module")
