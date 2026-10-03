#!/usr/bin/env python3
"""XRAY read-only Longbridge OpenAPI ACCOUNT probe.

Supports least-privilege OAuth bearer/refresh credentials first, with the
legacy API-key path retained only as an explicit compatibility fallback.

Public output is status/provenance only. No balances, positions, account ids,
buying power, tokens, refresh tokens, or other private values are serialized.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_openapi_probe_state.json"

LEGACY_REQUIRED_ENV = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)
LEGACY_RISK_OPT_IN_ENV = "XRAY_ALLOW_LEGACY_TRADE_CAPABLE_CREDENTIAL"
LEGACY_RISK_OPT_IN_VALUE = "I_UNDERSTAND_LEGACY_TOKEN_CAN_TRADE"

OAUTH_ACCESS_TOKEN_ENV = "LONGBRIDGE_OAUTH_ACCESS_TOKEN"
OAUTH_CLIENT_ID_ENV = "LONGBRIDGE_OAUTH_CLIENT_ID"
OAUTH_REFRESH_TOKEN_ENV = "LONGBRIDGE_OAUTH_REFRESH_TOKEN"
OAUTH_CLIENT_SECRET_ENV = "LONGBRIDGE_OAUTH_CLIENT_SECRET"

TOKEN_URL = "https://openapi.longbridge.com/oauth2/token"
ACCOUNT_URL = "https://openapi.longbridge.com/v1/asset/account"
POSITIONS_URL = "https://openapi.longbridge.com/v1/asset/stock"


class ProviderReadError(RuntimeError):
    def __init__(self, code: int | None = None):
        super().__init__("provider read failed")
        self.code = code


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_state(
    *,
    status: str,
    balance_parseable: bool,
    positions_parseable: bool,
    network_attempted: bool,
    reason_code: str,
    auth_mode: str,
    refresh_token_rotation_observed: bool = False,
    refresh_persistence_required: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1",
        "generated_at_utc": _now_utc(),
        "provider": "LONGBRIDGE_DIRECT_OPENAPI",
        "auth_mode": auth_mode,
        "refresh_token_rotation_observed": bool(refresh_token_rotation_observed),
        "refresh_persistence_required": bool(refresh_persistence_required),
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
        "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None,
        "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT") or None,
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


def _default_http_json(
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    form: Mapping[str, str] | None = None,
) -> Any:
    body = urlencode(dict(form or {})).encode() if form is not None else None
    h = dict(headers or {})
    if form is not None:
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = Request(url, data=body, headers=h, method=method)
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except HTTPError as exc:
        code: int | None = None
        try:
            raw = exc.read()
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(parsed, dict) and parsed.get("code") is not None:
                code = int(parsed.get("code"))
        except Exception:
            pass
        raise ProviderReadError(code or getattr(exc, "code", None)) from None
    except (URLError, TimeoutError):
        raise ProviderReadError(None) from None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise ProviderReadError(None) from None


def _api_data(payload: Any) -> Any:
    if not isinstance(payload, dict):
        raise ProviderReadError(None)
    try:
        code = int(payload.get("code", -1))
    except (TypeError, ValueError):
        code = -1
    if code != 0 or "data" not in payload:
        raise ProviderReadError(code if code >= 0 else None)
    return payload.get("data")


def _run_oauth(
    source_env: Mapping[str, str],
    http_json: Callable[..., Any],
) -> dict[str, Any]:
    access_token = str(source_env.get(OAUTH_ACCESS_TOKEN_ENV) or "").strip()
    client_id = str(source_env.get(OAUTH_CLIENT_ID_ENV) or "").strip()
    refresh_token = str(source_env.get(OAUTH_REFRESH_TOKEN_ENV) or "").strip()
    client_secret = str(source_env.get(OAUTH_CLIENT_SECRET_ENV) or "").strip()

    auth_mode = "OAUTH_BEARER_ENV" if access_token else "OAUTH_REFRESH_ENV"

    if not access_token:
        if not client_id or not refresh_token:
            return _public_state(
                status="BLOCKED_MISSING_CREDENTIALS",
                balance_parseable=False,
                positions_parseable=False,
                network_attempted=False,
                reason_code="OAUTH_ACCOUNT_SCOPE_SECRET_ENV_INCOMPLETE",
                auth_mode=auth_mode,
            )
        form = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
        if client_secret:
            form["client_secret"] = client_secret
        try:
            token_payload = http_json("POST", TOKEN_URL, headers={}, form=form)
            if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
                raise ProviderReadError(None)
            returned_refresh = str(token_payload.get("refresh_token") or "").strip()
            if returned_refresh and returned_refresh != refresh_token:
                # Official Longbridge SDK persists a newly returned refresh token
                # after refresh. GitHub Actions runners are ephemeral and this
                # probe has no authorized secret-write channel, so accepting a
                # rotated token would create a one-run PASS that cannot be
                # guaranteed on the next scheduler run. Fail closed before
                # reading account data; never serialize either token value.
                return _public_state(
                    status="BLOCKED_ROTATING_REFRESH_TOKEN_PERSISTENCE_REQUIRED",
                    balance_parseable=False,
                    positions_parseable=False,
                    network_attempted=True,
                    reason_code="OAUTH_REFRESH_TOKEN_ROTATED_BUT_SECURE_PERSISTENCE_UNAVAILABLE",
                    auth_mode=auth_mode,
                    refresh_token_rotation_observed=True,
                    refresh_persistence_required=True,
                )
            access_token = str(token_payload["access_token"])
        except BaseException as exc:
            code = _safe_error_code(exc)
            return _public_state(
                status="BLOCKED_SCOPE" if code == 403308 else "UNKNOWN_PROVIDER_ERROR",
                balance_parseable=False,
                positions_parseable=False,
                network_attempted=True,
                reason_code="PROVIDER_PERMISSION_SCOPE_DENIED" if code == 403308 else "OAUTH_REFRESH_OR_TOKEN_ERROR",
                auth_mode=auth_mode,
            )

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        balance = _api_data(http_json("GET", ACCOUNT_URL, headers=headers, form=None))
        positions = _api_data(http_json("GET", POSITIONS_URL, headers=headers, form=None))
        balance_ok = _balance_is_parseable(balance)
        positions_ok = _positions_are_parseable(positions)
    except BaseException as exc:
        code = _safe_error_code(exc)
        return _public_state(
            status="BLOCKED_SCOPE" if code == 403308 else "UNKNOWN_PROVIDER_ERROR",
            balance_parseable=False,
            positions_parseable=False,
            network_attempted=True,
            reason_code="PROVIDER_PERMISSION_SCOPE_DENIED" if code == 403308 else "PROVIDER_READ_ERROR",
            auth_mode=auth_mode,
        )

    passed = balance_ok and positions_ok
    return _public_state(
        status="PASS" if passed else "UNKNOWN_UNPARSEABLE_RESPONSE",
        balance_parseable=balance_ok,
        positions_parseable=positions_ok,
        network_attempted=True,
        reason_code="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS" if passed else "READ_RESPONSE_NOT_PARSEABLE",
        auth_mode=auth_mode,
    )


def run_probe(
    env: Mapping[str, str] | None = None,
    context_factory: Callable[[], Any] | None = None,
    http_json: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    source_env = os.environ if env is None else env
    oauth_present = any(
        source_env.get(name)
        for name in (
            OAUTH_ACCESS_TOKEN_ENV,
            OAUTH_CLIENT_ID_ENV,
            OAUTH_REFRESH_TOKEN_ENV,
            OAUTH_CLIENT_SECRET_ENV,
        )
    )
    if oauth_present:
        return _run_oauth(source_env, http_json or _default_http_json)

    missing = [name for name in LEGACY_REQUIRED_ENV if not source_env.get(name)]
    if missing:
        return _public_state(
            status="BLOCKED_MISSING_CREDENTIALS",
            balance_parseable=False,
            positions_parseable=False,
            network_attempted=False,
            reason_code="REQUIRED_SECRET_ENV_NOT_CONFIGURED",
            auth_mode="NONE",
        )

    # Legacy Longbridge API credentials are broader than XRAY needs: official
    # documentation warns that possession of the Legacy Access Token can allow
    # trading through OpenAPI. The probe itself remains read-only, but it must
    # never consume such a credential accidentally. A separate explicit secret
    # opt-in is required before any network/context construction occurs.
    if source_env.get(LEGACY_RISK_OPT_IN_ENV) != LEGACY_RISK_OPT_IN_VALUE:
        return _public_state(
            status="BLOCKED_HIGH_PRIVILEGE_CREDENTIAL_NOT_OPTED_IN",
            balance_parseable=False,
            positions_parseable=False,
            network_attempted=False,
            reason_code="LEGACY_TRADE_CAPABLE_CREDENTIAL_REQUIRES_EXPLICIT_OPT_IN",
            auth_mode="LEGACY_API_KEY_ENV",
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
            auth_mode="LEGACY_API_KEY_ENV",
        )

    passed = balance_ok and positions_ok
    return _public_state(
        status="PASS" if passed else "UNKNOWN_UNPARSEABLE_RESPONSE",
        balance_parseable=balance_ok,
        positions_parseable=positions_ok,
        network_attempted=True,
        reason_code="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS" if passed else "READ_RESPONSE_NOT_PARSEABLE",
        auth_mode="LEGACY_API_KEY_ENV",
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
