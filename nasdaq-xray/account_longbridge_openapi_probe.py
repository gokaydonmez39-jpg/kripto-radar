#!/usr/bin/env python3
"""XRAY read-only Longbridge OpenAPI ACCOUNT probe.

Public output is status/provenance only. No balances, positions, account ids,
buying power, tokens, or other private account values are serialized.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_openapi_probe_state.json"

REQUIRED_ENV = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_state(
    *,
    status: str,
    balance_parseable: bool,
    positions_parseable: bool,
    network_attempted: bool,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1",
        "generated_at_utc": _now_utc(),
        "provider": "LONGBRIDGE_DIRECT_OPENAPI",
        "auth_mode": "LEGACY_API_KEY_ENV",
        "status": status,
        "reason_code": reason_code,
        "balance_parseable": bool(balance_parseable),
        "positions_parseable": bool(positions_parseable),
        "empty_positions_are_known_exposure": True,
        "same_run_required_calls": ["account_balance", "stock_positions"],
        "network_attempted": bool(network_attempted),
        "private_values_persisted": False,
        "secret_values_persisted": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "alpha_authority": False,
    }


def _safe_error_code(exc: BaseException) -> int | None:
    for attr in ("code", "error_code", "status_code"):
        value = getattr(exc, attr, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def _balance_is_parseable(value: Any) -> bool:
    if value is None:
        return False
    try:
        return len(value) > 0
    except TypeError:
        return True


def _positions_are_parseable(value: Any) -> bool:
    # Empty positions are a valid known zero-exposure state.
    return value is not None


def run_probe(
    env: Mapping[str, str] | None = None,
    context_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    source_env = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not source_env.get(name)]
    if missing:
        return _public_state(
            status="BLOCKED_MISSING_CREDENTIALS",
            balance_parseable=False,
            positions_parseable=False,
            network_attempted=False,
            reason_code="REQUIRED_SECRET_ENV_NOT_CONFIGURED",
        )

    if context_factory is None:
        # Import only after credentials are confirmed so a no-secret run is
        # guaranteed to remain network-free.
        from longbridge.openapi import Config, TradeContext

        def context_factory() -> Any:
            config = Config.from_apikey_env()
            return TradeContext(config)

    try:
        ctx = context_factory()
        balance = ctx.account_balance()
        balance_ok = _balance_is_parseable(balance)
        positions = ctx.stock_positions()
        positions_ok = _positions_are_parseable(positions)
    except BaseException as exc:
        code = _safe_error_code(exc)
        reason = "PROVIDER_PERMISSION_SCOPE_DENIED" if code == 403308 else "PROVIDER_READ_ERROR"
        return _public_state(
            status="BLOCKED_SCOPE" if code == 403308 else "UNKNOWN_PROVIDER_ERROR",
            balance_parseable=False,
            positions_parseable=False,
            network_attempted=True,
            reason_code=reason,
        )

    passed = balance_ok and positions_ok
    return _public_state(
        status="PASS" if passed else "UNKNOWN_UNPARSEABLE_RESPONSE",
        balance_parseable=balance_ok,
        positions_parseable=positions_ok,
        network_attempted=True,
        reason_code="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS" if passed else "READ_RESPONSE_NOT_PARSEABLE",
    )


def write_state(state: Mapping[str, Any], output: Path = OUT) -> None:
    output.write_text(json.dumps(dict(state), indent=2, sort_keys=False) + "\n")


def main() -> None:
    state = run_probe()
    write_state(state)
    # Print only public-safe fields. Never print provider response objects.
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
