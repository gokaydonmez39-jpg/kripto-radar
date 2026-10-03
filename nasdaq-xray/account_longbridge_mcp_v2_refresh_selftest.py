#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "account_longbridge_mcp_v2_refresh.py"

spec = importlib.util.spec_from_file_location("xray_account_mcp_v2_refresh", TARGET)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def payload():
    return {
        "schema": "XRAY_LONGBRIDGE_OFFICIAL_MCP_AGENT_OAUTH_V2",
        "client_id": "client-id-123456",
        "access_token": "private-access-token",
        "refresh_token": "private-refresh-token",
        "token_type": "Bearer",
        "scopes": ["account.read"],
        "issued_at_epoch": 100,
        "expires_at_epoch": 9_999_999_999,
        "main_endpoint": "https://mcp.longbridge.com/v2",
        "agent_endpoint": "https://mcp.longbridge.com/agent",
        "account_tools_verified": True,
        "write_surface_absent": True,
        "bootstrap_epoch": 100,
        "protocol": "OFFICIAL_AGENT_AUTH_CODE_TO_MAIN_MCP_REFRESHABLE",
    }


def main():
    old_key = os.environ.get("XRAY_ACCOUNT_TOKEN_FERNET_KEY")
    try:
        key = Fernet.generate_key().decode()
        os.environ["XRAY_ACCOUNT_TOKEN_FERNET_KEY"] = key

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "token.enc"
            mod.VAULT_PATH = p

            missing = mod.run()
            assert missing["status"] == "BLOCKED_MISSING_VAULT"
            assert missing["account_read_performed"] is False
            assert missing["secret_values_persisted"] is False

            initial = payload()
            mod.save_vault(initial, p, key=key)
            valid = mod.run()
            assert valid["status"] == "PASS"
            assert valid["reason_code"] == "ENCRYPTED_VAULT_TOKEN_STILL_VALID"
            assert valid["token_refresh_performed"] is False
            assert valid["account_read_performed"] is False

            original = mod.access_token_from_vault
            def fake_refresh(current):
                updated = dict(current)
                updated["access_token"] = "new-private-access-token"
                updated["refresh_token"] = "new-private-refresh-token"
                updated["expires_at_epoch"] = 9_999_999_999
                updated["last_refresh_epoch"] = 123
                return "new-private-access-token", updated, True

            mod.access_token_from_vault = fake_refresh
            refreshed = mod.run()
            assert refreshed["status"] == "PASS"
            assert refreshed["reason_code"] == "ENCRYPTED_VAULT_REFRESHED"
            assert refreshed["token_refresh_performed"] is True
            assert refreshed["encrypted_vault_updated"] is True
            assert refreshed["account_read_performed"] is False
            restored = mod.load_vault(p, key=key)
            assert restored["refresh_token"] == "new-private-refresh-token"
            assert restored["access_token"] == "new-private-access-token"
            mod.access_token_from_vault = original

            raw = p.read_bytes()
            for secret in (
                b"private-access-token",
                b"private-refresh-token",
                b"new-private-access-token",
                b"new-private-refresh-token",
                b"client-id-123456",
            ):
                assert secret not in raw

        print("XRAY_ACCOUNT_MCP_V2_REFRESH_SELFTEST=PASS")
    finally:
        if old_key is None:
            os.environ.pop("XRAY_ACCOUNT_TOKEN_FERNET_KEY", None)
        else:
            os.environ["XRAY_ACCOUNT_TOKEN_FERNET_KEY"] = old_key


if __name__ == "__main__":
    main()
