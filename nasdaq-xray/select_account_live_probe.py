#!/usr/bin/env python3
"""Select one public-safe same-run ACCOUNT probe state for terminal consumption.

Priority:
1. Official restricted Longbridge MCP /v2 PASS
2. Official direct Longbridge OpenAPI PASS
3. If neither passes, prefer the probe that actually attempted network
4. Otherwise preserve deterministic fail-closed state

The selector never upgrades a blocked/unknown probe to PASS and never reads or
writes private account values.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
MCP_V2 = ROOT / "account_longbridge_mcp_v2_probe_state.json"
DIRECT = ROOT / "account_longbridge_openapi_probe_state.json"
OUT = ROOT / "account_effective_probe_state.json"

ALLOWED = {
    ("XRAY_ACCOUNT_LONGBRIDGE_MCP_V2_PROBE_V1", "LONGBRIDGE_HOSTED_MCP_V2"),
    ("XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1", "LONGBRIDGE_DIRECT_OPENAPI"),
}


def load_valid(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        j = json.loads(path.read_text())
    except Exception:
        return None
    if (str(j.get("schema")), str(j.get("provider"))) not in ALLOWED:
        return None
    if j.get("execution") != "NONE" or j.get("real_money") != "NO-GO":
        return None
    if j.get("private_values_persisted") is not False:
        return None
    if j.get("secret_values_persisted") is not False:
        return None
    return j


def same_run(j: dict[str, Any]) -> bool:
    current = str(os.getenv("GITHUB_RUN_ID") or "")
    probe = str(j.get("workflow_run_id") or "")
    return bool(current and probe and current == probe)


def valid_pass(j: dict[str, Any]) -> bool:
    return (
        str(j.get("status")) == "PASS"
        and j.get("network_attempted") is True
        and j.get("balance_parseable") is True
        and j.get("positions_parseable") is True
        and str(j.get("reason_code")) == "SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS"
        and same_run(j)
    )


def choose(states: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(states)
    if not items:
        return {
            "schema": "XRAY_ACCOUNT_EFFECTIVE_PROBE_V1",
            "provider": "NONE",
            "status": "BLOCKED_MISSING_CREDENTIALS",
            "reason_code": "NO_VALID_ACCOUNT_PROBE_STATE",
            "network_attempted": False,
            "balance_parseable": False,
            "positions_parseable": False,
            "private_values_persisted": False,
            "secret_values_persisted": False,
            "execution": "NONE",
            "real_money": "NO-GO",
            "alpha_authority": False,
            "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None,
            "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT") or None,
            "selected_from": None,
        }

    by_provider = {str(j.get("provider")): j for j in items}
    for provider in ("LONGBRIDGE_HOSTED_MCP_V2", "LONGBRIDGE_DIRECT_OPENAPI"):
        j = by_provider.get(provider)
        if j is not None and valid_pass(j):
            out = dict(j)
            out["selected_from"] = provider
            return out

    # Never convert any state to PASS here. Prefer a real attempted diagnostic.
    attempted = [j for j in items if j.get("network_attempted") is True]
    if attempted:
        # Prefer restricted /v2 diagnostics when both attempted.
        attempted.sort(
            key=lambda j: 0 if j.get("provider") == "LONGBRIDGE_HOSTED_MCP_V2" else 1
        )
        out = dict(attempted[0])
        out["selected_from"] = out.get("provider")
        return out

    # Neither path attempted network. Prefer restricted /v2 if present so the
    # operator sees the least-privilege credential requirement first.
    for provider in ("LONGBRIDGE_HOSTED_MCP_V2", "LONGBRIDGE_DIRECT_OPENAPI"):
        j = by_provider.get(provider)
        if j is not None:
            out = dict(j)
            out["selected_from"] = provider
            return out

    out = dict(items[0])
    out["selected_from"] = out.get("provider")
    return out


def main() -> None:
    states = [j for j in (load_valid(MCP_V2), load_valid(DIRECT)) if j is not None]
    selected = choose(states)
    OUT.write_text(json.dumps(selected, indent=2, sort_keys=False) + "\n")
    print(
        json.dumps(
            {
                "selected_provider": selected.get("provider"),
                "status": selected.get("status"),
                "reason_code": selected.get("reason_code"),
                "pass_created": bool(selected.get("status") == "PASS"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
