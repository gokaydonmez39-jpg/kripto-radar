#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

import account_longbridge_mcp_v2_bootstrap as boot
import account_longbridge_mcp_v2_vault as vault


PACKED_DISPLAY = "F4ep4yfKvDgpZnFUR6T8vm5bCjG65XZKgaTiNWbwTCVPqGw3HCrpDvYuxLUu6uNtn73ht5BKtKS7Fk9WG9MV9V2PYkwSGWoZfoEtFbfCL2f45c8"
PACKED_CLIENT_ID = "c91cd252-2f89-4024-9c5d-7b1340fc3bd1"


class Obj:
    def __init__(self, *, input_schema=None, structured_content=None, content=None, is_error=False):
        self.inputSchema = input_schema
        self.structured_content = structured_content
        self.content = [] if content is None else content
        self.is_error = is_error


class Text:
    def __init__(self, text): self.text = text


def expect_error(fn, text: str):
    try:
        fn()
    except Exception as exc:
        assert text in str(exc), (text, repr(exc))
        return
    raise AssertionError(f"expected {text}")


def token_bundle(scope="account.read watchlist", *, refresh="private-refresh-token-value-456"):
    return {
        "access_token": "private-access-token-value-123",
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": scope,
    }


def main():
    expect_error(lambda: vault.resolve_vault_key({}), "VAULT_KEY_MISSING")
    key = Fernet.generate_key().decode()
    assert vault.resolve_vault_key({vault.FERNET_KEY_ENV: key}) == key

    assert boot.packed_client_id(PACKED_DISPLAY) == PACKED_CLIENT_ID

    tool = Obj(input_schema={
        "type": "object",
        "properties": {"auth_code": {"type": "string"}},
        "required": ["auth_code"],
    })
    assert boot._auth_arg_name(tool) == "auth_code"

    structured = {"access_token": "A"*32, "refresh_token": "R"*32, "expires_in": 3600, "scope": "account.read"}
    result = Obj(structured_content=structured)
    assert boot._extract_auth_payload(result)["refresh_token"] == "R"*32
    text_result = Obj(content=[Text(json.dumps(structured))])
    assert boot._extract_auth_payload(text_result)["access_token"] == "A"*32

    manifest = {"account_balance", "stock_positions", "quote", "watchlist"}
    payload = boot.build_vault_payload(
        PACKED_CLIENT_ID, token_bundle(), manifest, now_epoch=1_000_000
    )
    assert payload["schema"] == vault.SCHEMA
    assert payload["client_id"] == PACKED_CLIENT_ID
    assert payload["scopes"] == ["account.read", "watchlist"]
    assert payload["expires_at_epoch"] == 1_003_600
    assert payload["main_endpoint"] == "https://mcp.longbridge.com"
    assert payload["agent_endpoint"] == "https://mcp.longbridge.com/agent"
    assert payload["account_tools_verified"] is True
    assert payload["write_surface_absent"] is True

    expect_error(
        lambda: boot.build_vault_payload(
            PACKED_CLIENT_ID, token_bundle(scope="watchlist"), manifest
        ),
        "ACCOUNT_READ_SCOPE_MISSING",
    )
    expect_error(
        lambda: boot.build_vault_payload(
            PACKED_CLIENT_ID, token_bundle(scope="account.read trade.write"), manifest
        ),
        "TRADE_WRITE_SCOPE_FORBIDDEN",
    )
    expect_error(
        lambda: boot.build_vault_payload(
            PACKED_CLIENT_ID, token_bundle(), {"account_balance"}
        ),
        "ACCOUNT_TOOL_MANIFEST_NOT_VERIFIED",
    )
    expect_error(
        lambda: boot.build_vault_payload(
            PACKED_CLIENT_ID, token_bundle(),
            {"account_balance", "stock_positions", "submit_order"}
        ),
        "WRITE_SURFACE_PRESENT",
    )

    encoded = vault.encrypt_payload(payload, key)
    for secret in (
        b"private-access-token-value-123",
        b"private-refresh-token-value-456",
        PACKED_CLIENT_ID.encode(),
    ):
        assert secret not in encoded
    decoded = vault.decrypt_payload(encoded, key)
    assert decoded == payload

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "token.enc"
        vault.save_vault(payload, p, key=key)
        raw = p.read_bytes()
        assert b"private-access-token-value-123" not in raw
        assert b"private-refresh-token-value-456" not in raw
        loaded = vault.load_vault(p, key=key)
        assert loaded == payload
        assert vault.bearer_from_vault(loaded, now_epoch=1_000_100) == "private-access-token-value-123"
        expect_error(
            lambda: vault.bearer_from_vault(loaded, now_epoch=1_003_400),
            "VAULT_BEARER_EXPIRED_OR_EXPIRING",
        )

    access, unchanged, refreshed = vault.access_token_from_vault(
        dict(payload),
        now_epoch=1_000_100,
        http_json=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not refresh")),
    )
    assert access == "private-access-token-value-123"
    assert unchanged == payload
    assert refreshed is False

    calls = []
    def refresh_http(method, url, *, form=None, headers=None):
        calls.append((method, url, dict(form or {})))
        return {
            "access_token": "new-private-access-token",
            "refresh_token": "rotated-private-refresh-token",
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": "account.read watchlist",
        }

    access2, updated, refreshed2 = vault.access_token_from_vault(
        dict(payload), now_epoch=1_003_400, http_json=refresh_http
    )
    assert refreshed2 is True
    assert access2 == "new-private-access-token"
    assert updated["refresh_token"] == "rotated-private-refresh-token"
    assert updated["expires_at_epoch"] == 1_010_600
    assert calls[0][1] == "https://mcp.longbridge.com/oauth2/token"
    assert calls[0][2]["client_id"] == PACKED_CLIENT_ID

    expect_error(
        lambda: vault.access_token_from_vault(
            dict(payload),
            now_epoch=1_003_400,
            http_json=lambda *a, **k: {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 7200,
                "scope": "account.read trade.write",
            },
        ),
        "REFRESH_TRADE_WRITE_SCOPE_FORBIDDEN",
    )

    bad = dict(payload)
    bad["write_surface_absent"] = False
    expect_error(lambda: vault.validate_payload(bad), "VAULT_WRITE_SURFACE_NOT_ABSENT")

    public = boot._public("PASS", "TEST")
    encoded_public = json.dumps(public).lower()
    for forbidden in (
        "private-access-token-value-123",
        "private-refresh-token-value-456",
        "rotated-private-refresh-token",
        PACKED_DISPLAY.lower(),
    ):
        assert forbidden not in encoded_public
    assert public["private_values_persisted"] is False
    assert public["secret_values_persisted"] is False
    assert public["execution"] == "NONE"
    assert public["real_money"] == "NO-GO"

    print("XRAY_ACCOUNT_MCP_V2_VAULT_SELFTEST=PASS")


if __name__ == "__main__":
    main()
