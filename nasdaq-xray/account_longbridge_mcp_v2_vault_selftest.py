#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet

import account_longbridge_mcp_v2_bootstrap as boot
import account_longbridge_mcp_v2_vault as vault


PACKED_DISPLAY = "F4ep4yfKvDgpZnFUR6T8vm5bCjG65XZKgaTiNWbwTCVPqGw3HCrpDvYuxLUu6uNtn73ht5BKtKS7Fk9WG9MV9V2PYkwSGWoZfoEtFbfCL2f45c8"
PACKED_CLIENT_ID = "c91cd252-2f89-4024-9c5d-7b1340fc3bd1"
ORIGINAL_CODE = "RKBXES26iL0CdQL85vXz+tSNeoHeqyUuLEz3nVWgqVU="


def expect_error(fn, text: str):
    try:
        fn()
    except Exception as exc:
        assert text in str(exc), (text, repr(exc))
        return
    raise AssertionError(f"expected {text}")


def main():
    cid, code = boot.unpack_agent_code(PACKED_DISPLAY)
    assert cid == PACKED_CLIENT_ID
    assert code == ORIGINAL_CODE

    token = {
        "access_token": "private-access-token",
        "refresh_token": "private-refresh-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "account.read watchlist",
    }
    payload = boot.build_vault_payload("client-1", token, now_epoch=1_000_000)
    assert payload["scopes"] == ["account.read", "watchlist"]
    assert payload["expires_at_epoch"] == 1_003_600

    expect_error(
        lambda: boot.build_vault_payload(
            "client-1",
            {**token, "scope": "watchlist"},
            now_epoch=1_000_000,
        ),
        "ACCOUNT_READ_SCOPE_MISSING",
    )
    expect_error(
        lambda: boot.build_vault_payload(
            "client-1",
            {**token, "scope": "account.read trade.write"},
            now_epoch=1_000_000,
        ),
        "TRADE_WRITE_SCOPE_FORBIDDEN",
    )

    derived_seed = "A" * 96
    derived1 = vault.resolve_vault_key({vault.AUTH_CODE_KEY_ENV: derived_seed})
    derived2 = vault.resolve_vault_key({vault.AUTH_CODE_KEY_ENV: derived_seed})
    assert derived1 == derived2
    assert derived_seed not in derived1

    explicit = Fernet.generate_key().decode()
    assert vault.resolve_vault_key({
        vault.FERNET_KEY_ENV: explicit,
        vault.AUTH_CODE_KEY_ENV: derived_seed,
    }) == explicit

    key = Fernet.generate_key().decode()
    encoded = vault.encrypt_payload(payload, key)
    assert b"private-access-token" not in encoded
    assert b"private-refresh-token" not in encoded
    decoded = vault.decrypt_payload(encoded, key)
    assert decoded == payload

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "token.enc"
        vault.save_vault(payload, p, key=key)
        assert p.exists()
        raw = p.read_bytes()
        assert b"private-access-token" not in raw
        assert vault.load_vault(p, key=key) == payload

    access, unchanged, refreshed = vault.access_token_from_vault(
        dict(payload),
        now_epoch=1_000_100,
        http_json=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not refresh")),
    )
    assert access == "private-access-token"
    assert unchanged == payload
    assert refreshed is False

    calls = []
    def refresh_http(method, url, *, form=None, headers=None):
        calls.append((method, url, dict(form or {})))
        return {
            "access_token": "new-private-access",
            "refresh_token": "rotated-private-refresh",
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": "account.read watchlist",
        }

    access2, updated, refreshed2 = vault.access_token_from_vault(
        dict(payload),
        now_epoch=1_003_400,
        http_json=refresh_http,
    )
    assert refreshed2 is True
    assert access2 == "new-private-access"
    assert updated["refresh_token"] == "rotated-private-refresh"
    assert updated["expires_at_epoch"] == 1_010_600
    assert len(calls) == 1
    assert calls[0][1] == vault.TOKEN_URL

    expect_error(
        lambda: vault.access_token_from_vault(
            dict(payload),
            now_epoch=1_003_400,
            http_json=lambda *a, **k: {
                "access_token": "x",
                "refresh_token": "y",
                "expires_in": 7200,
                "scope": "account.read trade.write",
            },
        ),
        "REFRESH_TRADE_WRITE_SCOPE_FORBIDDEN",
    )

    public = boot._public("PASS", "TEST", scopes=["account.read"], expires_in=3600)
    serialized = json.dumps(public).lower()
    for forbidden in ("private-access-token", "private-refresh-token", "rotated-private-refresh"):
        assert forbidden not in serialized
    assert public["private_values_persisted"] is False
    assert public["secret_values_persisted"] is False
    assert public["execution"] == "NONE"
    assert public["real_money"] == "NO-GO"

    print("XRAY_ACCOUNT_MCP_V2_VAULT_SELFTEST=PASS")


if __name__ == "__main__":
    main()
