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


def creds():
    return {
        "LONGBRIDGE_APP_KEY": "test-key",
        "LONGBRIDGE_APP_SECRET": "test-secret",
        "LONGBRIDGE_ACCESS_TOKEN": "test-token",
    }


def assert_public_only(state):
    encoded = json.dumps(state).lower()
    for forbidden_value in (
        "private-balance-value",
        "private-position-value",
        "test-secret",
        "test-token",
        "account-id-123",
    ):
        assert forbidden_value not in encoded
    assert state["private_values_persisted"] is False
    assert state["secret_values_persisted"] is False
    assert state["execution"] == "NONE"
    assert state["real_money"] == "NO-GO"
    assert "workflow_run_id" in state
    assert "workflow_run_attempt" in state


def main():
    factory_called = False

    def must_not_call():
        nonlocal factory_called
        factory_called = True
        raise AssertionError("context factory called without credentials")

    missing = mod.run_probe(env={}, context_factory=must_not_call)
    assert missing["status"] == "BLOCKED_MISSING_CREDENTIALS"
    assert missing["network_attempted"] is False
    assert factory_called is False
    assert_public_only(missing)

    ctx = FakeContext(
        balance=[{"value": "private-balance-value", "account": "account-id-123"}],
        positions=[{"symbol": "PRIVATE", "value": "private-position-value"}],
    )
    passed = mod.run_probe(env=creds(), context_factory=lambda: ctx)
    assert passed["status"] == "PASS"
    assert passed["balance_parseable"] is True
    assert passed["positions_parseable"] is True
    assert ctx.balance_calls == 1 and ctx.position_calls == 1
    assert_public_only(passed)

    empty_ctx = FakeContext(balance=[object()], positions=[])
    empty_positions = mod.run_probe(env=creds(), context_factory=lambda: empty_ctx)
    assert empty_positions["status"] == "PASS"
    assert empty_positions["positions_parseable"] is True
    assert_public_only(empty_positions)

    balance_fail = mod.run_probe(
        env=creds(),
        context_factory=lambda: FakeContext(RuntimeError("hidden provider text"), []),
    )
    assert balance_fail["status"] != "PASS"
    assert_public_only(balance_fail)

    position_fail = mod.run_probe(
        env=creds(),
        context_factory=lambda: FakeContext([object()], RuntimeError("hidden provider text")),
    )
    assert position_fail["status"] != "PASS"
    assert_public_only(position_fail)

    scope_fail = mod.run_probe(
        env=creds(),
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
