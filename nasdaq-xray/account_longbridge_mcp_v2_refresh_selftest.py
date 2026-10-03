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

            payload = {
                "schema": "XRAY_LONGBRIDGE_MCP_V2_ENCRYPTED_TOKEN_V1",
                "client_id": "client-1",
                "access_token": "private-access",
                "refresh_token": "private-refresh",
                "token_type": "Bearer",
                "scopes": ["account.read"],
                "issued_at_epoch": 100,
                "expires_at_epoch": 9999999999,
                "bootstrap_epoch": 100,
            }
            mod.save_vault(payload, p, key=key)
            valid = mod.run()
            assert valid["status"] == "PASS"
            assert valid["reason_code"] == "ENCRYPTED_VAULT_TOKEN_STILL_VALID"
            assert valid["token_refresh_performed"] is False
            assert valid["account_read_performed"] is False

            original = mod.access_token_from_vault
            def fake_refresh(current):
                updated = dict(current)
                updated["access_token"] = "new-private-access"
                updated["refresh_token"] = "new-private-refresh"
                updated["expires_at_epoch"] = 9999999999
                return "new-private-access", updated, True
            mod.access_token_from_vault = fake_refresh
            refreshed = mod.run()
            assert refreshed["status"] == "PASS"
            assert refreshed["reason_code"] == "ENCRYPTED_VAULT_REFRESHED"
            assert refreshed["token_refresh_performed"] is True
            restored = mod.load_vault(p, key=key)
            assert restored["refresh_token"] == "new-private-refresh"
            mod.access_token_from_vault = original

            raw = p.read_bytes()
            assert b"private-access" not in raw
            assert b"private-refresh" not in raw
            assert b"new-private-access" not in raw
            assert b"new-private-refresh" not in raw

        print("XRAY_ACCOUNT_MCP_V2_REFRESH_SELFTEST=PASS")
    finally:
        if old_key is None:
            os.environ.pop("XRAY_ACCOUNT_TOKEN_FERNET_KEY", None)
        else:
            os.environ["XRAY_ACCOUNT_TOKEN_FERNET_KEY"] = old_key


if __name__ == "__main__":
    main()
