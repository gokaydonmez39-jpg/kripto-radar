#!/usr/bin/env python3
"""XRAY read-only ACCOUNT probe via official Longbridge MCP /v2.

Longbridge's official /v2 MCP endpoint is a restricted surface. Upstream
source advertises account.read + trade.read but deliberately excludes
trade.write. XRAY calls only account_balance and stock_positions.

No balances, positions, account identifiers, bearer tokens, or raw provider
payloads are persisted or printed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "account_longbridge_mcp_v2_probe_state.json"
MCP_URL = "https://mcp.longbridge.com/v2"
TOKEN_ENV = "LONGBRIDGE_MCP_V2_BEARER_TOKEN"


class McpReadError(RuntimeError):
    def __init__(self, kind: str, status: int | None = None):
        super().__init__(kind)
        self.kind = kind
        self.status = status


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state(
    *,
    status: str,
    reason_code: str,
    network_attempted: bool,
    balance_parseable: bool = False,
    positions_parseable: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "XRAY_ACCOUNT_LONGBRIDGE_MCP_V2_PROBE_V1",
        "generated_at_utc": _now_utc(),
        "provider": "LONGBRIDGE_OFFICIAL_MCP_V2",
        "endpoint_class": "OFFICIAL_RESTRICTED_READ_SURFACE",
        "required_oauth_scope": "account.read",
        "trade_write_scope_required": False,
        "trade_write_surface_exposed": False,
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


def _parse_streamable_http(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" in content_type.lower() or text.lstrip().startswith("event:"):
        payloads = []
        for line in text.splitlines():
            if line.startswith("data:"):
                item = line[5:].strip()
                if not item:
                    continue
                try:
                    payloads.append(json.loads(item))
                except Exception:
                    continue
        if not payloads:
            raise McpReadError("UNPARSEABLE_MCP_RESPONSE")
        obj = payloads[-1]
    else:
        try:
            obj = json.loads(text)
        except Exception:
            raise McpReadError("UNPARSEABLE_MCP_RESPONSE") from None
    if not isinstance(obj, dict):
        raise McpReadError("UNPARSEABLE_MCP_RESPONSE")
    return obj


def _default_post_json(
    url: str,
    bearer: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    body = json.dumps(dict(payload), separators=(",", ":")).encode()
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise McpReadError("AUTH_OR_HTTP_ERROR", getattr(exc, "code", None)) from None
    except (URLError, TimeoutError):
        raise McpReadError("NETWORK_ERROR") from None
    return _parse_streamable_http(raw, content_type)


def _jsonrpc_result(obj: Mapping[str, Any]) -> Any:
    if "error" in obj:
        err = obj.get("error")
        code = err.get("code") if isinstance(err, dict) else None
        if code in (-32001, -32000):
            raise McpReadError("MCP_AUTH_OR_SCOPE_ERROR")
        raise McpReadError("MCP_TOOL_ERROR")
    if "result" not in obj:
        raise McpReadError("MCP_RESULT_MISSING")
    return obj.get("result")


def _tool_payload(result: Any) -> Any:
    if not isinstance(result, dict):
        raise McpReadError("MCP_TOOL_RESULT_UNPARSEABLE")

    structured = result.get("structuredContent")
    if structured is not None:
        return structured

    content = result.get("content")
    if not isinstance(content, list):
        raise McpReadError("MCP_TOOL_RESULT_UNPARSEABLE")
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            txt = part.get("text")
            if isinstance(txt, str):
                try:
                    return json.loads(txt)
                except Exception:
                    continue
    raise McpReadError("MCP_TOOL_RESULT_UNPARSEABLE")


def _balance_parseable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        if "balances" in value:
            balances = value.get("balances")
            return isinstance(balances, list) and len(balances) > 0
        return len(value) > 0
    return False


def _positions_parseable(value: Any) -> bool:
    # Empty positions are a valid known zero-exposure state.
    return isinstance(value, (list, dict))


def run_probe(
    env: Mapping[str, str] | None = None,
    post_json: Callable[[str, str, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_env = os.environ if env is None else env
    bearer = str(source_env.get(TOKEN_ENV) or "").strip()
    if not bearer:
        return _state(
            status="BLOCKED_MISSING_CREDENTIALS",
            reason_code="MCP_V2_BEARER_NOT_CONFIGURED",
            network_attempted=False,
        )

    send = post_json or _default_post_json
    try:
        bal_rpc = send(
            MCP_URL,
            bearer,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "account_balance", "arguments": {}},
            },
        )
        bal = _tool_payload(_jsonrpc_result(bal_rpc))

        pos_rpc = send(
            MCP_URL,
            bearer,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "stock_positions", "arguments": {}},
            },
        )
        pos = _tool_payload(_jsonrpc_result(pos_rpc))
    except McpReadError as exc:
        if exc.kind == "MCP_AUTH_OR_SCOPE_ERROR" or (
            exc.kind == "AUTH_OR_HTTP_ERROR" and exc.status in (401, 403)
        ):
            status = "BLOCKED_SCOPE_OR_TOKEN"
            reason = "MCP_V2_ACCOUNT_READ_NOT_AUTHORIZED_OR_TOKEN_INVALID"
        else:
            status = "UNKNOWN_PROVIDER_ERROR"
            reason = exc.kind
        return _state(
            status=status,
            reason_code=reason,
            network_attempted=True,
        )
    except BaseException:
        return _state(
            status="UNKNOWN_PROVIDER_ERROR",
            reason_code="UNEXPECTED_READ_ERROR",
            network_attempted=True,
        )

    balance_ok = _balance_parseable(bal)
    positions_ok = _positions_parseable(pos)
    passed = balance_ok and positions_ok
    return _state(
        status="PASS" if passed else "UNKNOWN_UNPARSEABLE_RESPONSE",
        reason_code="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS"
        if passed
        else "READ_RESPONSE_NOT_PARSEABLE",
        network_attempted=True,
        balance_parseable=balance_ok,
        positions_parseable=positions_ok,
    )


def write_state(state: Mapping[str, Any], output: Path = OUT) -> None:
    output.write_text(json.dumps(dict(state), indent=2, sort_keys=False) + "\n")


def main() -> None:
    state = run_probe()
    write_state(state)
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
