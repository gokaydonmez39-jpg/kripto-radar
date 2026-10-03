#!/usr/bin/env python3
"""Refresh/validate the encrypted Longbridge MCP /v2 ACCOUNT vault only.

This step intentionally performs no account reads. If token state is refreshed,
ciphertext is written atomically to the repository vault file so the workflow
can persist it *before* any downstream research/final-gate work.

No plaintext token, auth code, account id, balance or position is printed.
"""
from __future__ import annotations

import json
from pathlib import Path

from account_longbridge_mcp_v2_vault import (
    VAULT_PATH,
    TokenRefreshError,
    VaultError,
    access_token_from_vault,
    load_vault,
    resolve_vault_key,
    save_vault,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_mcp_v2_refresh_state.json"


def public_state(status: str, reason_code: str, *, refreshed: bool = False) -> dict:
    return {
        "schema": "XRAY_ACCOUNT_MCP_V2_REFRESH_STATE_V1",
        "provider": "LONGBRIDGE_HOSTED_MCP_V2",
        "status": status,
        "reason_code": reason_code,
        "vault_present": VAULT_PATH.exists(),
        "token_refresh_performed": bool(refreshed),
        "encrypted_vault_updated": bool(refreshed),
        "account_read_performed": False,
        "private_values_persisted": False,
        "secret_values_persisted": False,
        "execution": "NONE",
        "real_money": "NO-GO",
    }


def run() -> dict:
    if not VAULT_PATH.exists():
        return public_state("BLOCKED_MISSING_VAULT", "ENCRYPTED_VAULT_FILE_NOT_CONFIGURED")
    try:
        key = resolve_vault_key()
        payload = load_vault(key=key)
        _token, updated, refreshed = access_token_from_vault(payload)
        if refreshed:
            save_vault(updated, key=key)
        return public_state(
            "PASS",
            "ENCRYPTED_VAULT_REFRESHED" if refreshed else "ENCRYPTED_VAULT_TOKEN_STILL_VALID",
            refreshed=refreshed,
        )
    except (VaultError, TokenRefreshError) as exc:
        return public_state("BLOCKED_TOKEN_VAULT", str(exc) or type(exc).__name__)


def main() -> None:
    state = run()
    OUT.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")
    print(json.dumps(state, sort_keys=True))
    if state["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
