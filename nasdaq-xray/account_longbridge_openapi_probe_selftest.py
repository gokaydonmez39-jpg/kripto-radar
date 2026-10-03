#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROBE = ROOT / "account_longbridge_openapi_probe.py"

spec = importlib.util.spec_from_file_location("xray_account_probe", PROBE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class FakeContext:
    def __init__(self, balance, positions):
        self._balance = balance
        self._positions = positions
        self.balance_calls = 0
        self.position_calls = 0

    def account_balance(self):
        self.balance_calls += 1
        if isinstance(self._balance, BaseException):
            raise self._balance
        return self._balance

    def stock_positions(self):
        self.position_calls += 1
        if isinstance(self._positions, BaseException):
            raise self._positions
        return self._positions


class ScopeError(Exception):
    code = 403308


def legacy_creds():
    return {
        "LONGBRIDGE_APP_KEY": "test-key",
        "LONGBRIDGE_APP_SECRET": "test-secret",
        "LONGBRIDGE_ACCESS_TOKEN": "test-token",
        "XRAY_ALLOW_LEGACY_TRADE_CAPABLE_CREDENTIAL": "I_UNDERSTAND_LEGACY_TOKEN_CAN_TRADE",
    }


def assert_public_only(state):
    encoded = json.dumps(state).lower()
    for forbidden_value in (
        "private-balance-value",
        "private-position-value",
        "test-secret",
        "test-token",
        "oauth-access-secret",
        "oauth-refresh-secret",
        "oauth-refreshed-access-secret",
        "account-id-123",
    ):
        assert forbidden_value not in encoded
    assert state["private_values_persisted"] is False
    assert state["secret_values_persisted"] is False
    assert state["execution"] == "NONE"
    assert state["real_money"] == "NO-GO"
    assert "workflow_run_id" in state
    assert "workflow_run_attempt" in state


def oauth_http_factory(scope_fail=False):
    calls = []

    def http(method, url, headers=None, form=None):
        calls.append((method, url, dict(headers or {}), dict(form or {}) if form is not None else None))
        if scope_fail and url == mod.ACCOUNT_URL:
            raise mod.ProviderReadError(403308)
        if url == mod.TOKEN_URL:
            assert method == "POST"
            assert (form or {}).get("refresh_token") == "oauth-refresh-secret"
            return {
                "access_token": "oauth-refreshed-access-secret",
                "refresh_token": "rotated-refresh-hidden",
                "expires_in": 2592000,
                "token_type": "Bearer",
            }
        if url == mod.ACCOUNT_URL:
            assert (headers or {}).get("Authorization", "").startswith("Bearer ")
            return {"code": 0, "message": "success", "data": [{"account": "account-id-123", "value": "private-balance-value"}]}
        if url == mod.POSITIONS_URL:
            assert (headers or {}).get("Authorization", "").startswith("Bearer ")
            return {"code": 0, "message": "success", "data": {"list": [{"symbol": "PRIVATE", "value": "private-position-value"}]}}
        raise AssertionError(url)

    return http, calls


def main():
    factory_called = False

    def must_not_call():
        nonlocal factory_called
        factory_called = True
        raise AssertionError("context factory called without credentials")

    missing = mod.run_probe(env={}, context_factory=must_not_call)
    assert missing["status"] == "BLOCKED_MISSING_CREDENTIALS"
    assert missing["network_attempted"] is False
    assert missing["auth_mode"] == "NONE"
    assert factory_called is False
    assert_public_only(missing)

    partial_oauth_http, partial_calls = oauth_http_factory()
    partial_oauth = mod.run_probe(
        env={"LONGBRIDGE_OAUTH_CLIENT_ID": "client-only"},
        context_factory=must_not_call,
        http_json=partial_oauth_http,
    )
    assert partial_oauth["status"] == "BLOCKED_MISSING_CREDENTIALS"
    assert partial_oauth["reason_code"] == "OAUTH_ACCOUNT_SCOPE_SECRET_ENV_INCOMPLETE"
    assert partial_oauth["network_attempted"] is False
    assert partial_calls == []
    assert_public_only(partial_oauth)

    bearer_http, bearer_calls = oauth_http_factory()
    bearer = mod.run_probe(
        env={"LONGBRIDGE_OAUTH_ACCESS_TOKEN": "oauth-access-secret"},
        http_json=bearer_http,
    )
    assert bearer["status"] == "PASS"
    assert bearer["auth_mode"] == "OAUTH_BEARER_ENV"
    assert bearer["balance_parseable"] is True
    assert bearer["positions_parseable"] is True
    assert not any(url == mod.TOKEN_URL for _, url, _, _ in bearer_calls)
    assert_public_only(bearer)

    refresh_http, refresh_calls = oauth_http_factory()
    refreshed = mod.run_probe(
        env={
            "LONGBRIDGE_OAUTH_CLIENT_ID": "oauth-client",
            "LONGBRIDGE_OAUTH_REFRESH_TOKEN": "oauth-refresh-secret",
        },
        http_json=refresh_http,
    )
    assert refreshed["status"] == "PASS"
    assert refreshed["auth_mode"] == "OAUTH_REFRESH_ENV"
    assert refresh_calls[0][1] == mod.TOKEN_URL
    assert_public_only(refreshed)

    denied_http, _ = oauth_http_factory(scope_fail=True)
    denied = mod.run_probe(
        env={"LONGBRIDGE_OAUTH_ACCESS_TOKEN": "oauth-access-secret"},
        http_json=denied_http,
    )
    assert denied["status"] == "BLOCKED_SCOPE"
    assert denied["reason_code"] == "PROVIDER_PERMISSION_SCOPE_DENIED"
    assert_public_only(denied)

    no_opt_in_env = legacy_creds()
    no_opt_in_env.pop("XRAY_ALLOW_LEGACY_TRADE_CAPABLE_CREDENTIAL")
    factory_called = False
    blocked_high_privilege = mod.run_probe(env=no_opt_in_env, context_factory=must_not_call)
    assert blocked_high_privilege["status"] == "BLOCKED_HIGH_PRIVILEGE_CREDENTIAL_NOT_OPTED_IN"
    assert blocked_high_privilege["reason_code"] == "LEGACY_TRADE_CAPABLE_CREDENTIAL_REQUIRES_EXPLICIT_OPT_IN"
    assert blocked_high_privilege["network_attempted"] is False
    assert factory_called is False
    assert_public_only(blocked_high_privilege)

    ctx = FakeContext(
        balance=[{"value": "private-balance-value", "account": "account-id-123"}],
        positions=[{"symbol": "PRIVATE", "value": "private-position-value"}],
    )
    passed = mod.run_probe(env=legacy_creds(), context_factory=lambda: ctx)
    assert passed["status"] == "PASS"
    assert passed["auth_mode"] == "LEGACY_API_KEY_ENV"
    assert passed["balance_parseable"] is True
    assert passed["positions_parseable"] is True
    assert ctx.balance_calls == 1 and ctx.position_calls == 1
    assert_public_only(passed)

    empty_ctx = FakeContext(balance=[object()], positions=[])
    empty_positions = mod.run_probe(env=legacy_creds(), context_factory=lambda: empty_ctx)
    assert empty_positions["status"] == "PASS"
    assert empty_positions["positions_parseable"] is True
    assert_public_only(empty_positions)

    scope_fail = mod.run_probe(
        env=legacy_creds(),
        context_factory=lambda: FakeContext(ScopeError("hidden scope text"), []),
    )
    assert scope_fail["status"] == "BLOCKED_SCOPE"
    assert scope_fail["reason_code"] == "PROVIDER_PERMISSION_SCOPE_DENIED"
    assert_public_only(scope_fail)

    source = PROBE.read_text()
    for forbidden_call in (
        ".place_order(",
        ".replace_order(",
        ".cancel_order(",
        ".submit_order(",
        ".withdraw(",
    ):
        assert forbidden_call not in source

    print("XRAY_ACCOUNT_OPENAPI_SELFTEST=PASS")


if __name__ == "__main__":
    main()
