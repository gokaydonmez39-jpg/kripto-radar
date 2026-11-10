#!/usr/bin/env python3
"""Real third-party SDK runtime smoke: requires external no-network/no-secrets Docker.

Does not fetch prices, call an LLM API, connect a server, or authorize production.
A successful import is never evidence of live PIT, OOS or source usage rights.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os

CANDIDATES = {
    "pydantic-ai": ("pydantic-ai-slim", "2.66.0"),
    "mcp-use": ("mcp-use", "1.7.1"),
    "qlib": ("pyqlib", "0.9.7"),
    "openbb-v5": ("openbb", "5.0.0"),
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def smoke(candidate: str) -> dict:
    require(candidate in CANDIDATES, "UNKNOWN_CANDIDATE")
    # The runner's Docker --network none is the real control; env vars alone
    # DO NOT prove isolation.
    require(os.environ.get("XRAY_CONTAINER_NO_NETWORK") == "1",
            "NETWORK_ISOLATION_NOT_ASSERTED")
    require(os.environ.get("XRAY_NO_SECRETS") == "1",
            "SECRETLESS_RUNTIME_NOT_ASSERTED")
    sensitive = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ALPACA_API_KEY",
                 "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "GOOGLE_API_KEY",
                 "GITHUB_TOKEN", "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON",
                 "XRAY_ALPACA_DATA_KEY_ID", "XRAY_ALPACA_DATA_SECRET_KEY")
    require(all(not os.environ.get(key) for key in sensitive),
            "SENSITIVE_ENV_PRESENT")
    distribution, expected = CANDIDATES[candidate]
    installed = importlib.metadata.version(distribution)
    require(installed == expected, "DISTRIBUTION_VERSION_MISMATCH")

    if candidate == "pydantic-ai":
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel
        result = Agent(TestModel(custom_output_text="XRAY_OFFLINE_SDK_SMOKE"),
                       output_type=str).run_sync("Offline SDK verification")
        require(result.output == "XRAY_OFFLINE_SDK_SMOKE",
                "PYDANTIC_TESTMODEL_FAILED")
        scope = "REAL_SDK_TESTMODEL_OFFLINE_PASS_ONLY"
    elif candidate == "mcp-use":
        from mcp_use import MCPClient
        client = MCPClient.from_dict({"mcpServers": {}})
        require(client is not None, "MCP_CLIENT_CONSTRUCTION_FAILED")
        scope = "REAL_SDK_EMPTY_CLIENT_OFFLINE_PASS_NO_SERVER"
    elif candidate == "qlib":
        import qlib
        require(callable(getattr(qlib, "init", None)), "QLIB_MISSING_INIT")
        scope = "REAL_QLIB_IMPORT_ONLY_NO_PIT_OR_DATA"
    else:
        # OpenBB 5.0 attempts to write .build.lock inside its installed package.
        # Keep the image read-only: copy only this package to an isolated /tmp
        # directory and import the unchanged SDK from there. No provider access.
        from importlib.util import find_spec
        import shutil
        import sys
        import tempfile
        from pathlib import Path

        spec = find_spec("openbb")
        require(spec is not None and spec.submodule_search_locations,
                "OPENBB_PACKAGE_SPEC_MISSING")
        package_root = Path(next(iter(spec.submodule_search_locations)))
        require(package_root.is_dir(), "OPENBB_PACKAGE_DIR_MISSING")
        temporary_parent = Path(tempfile.mkdtemp(prefix="xray-openbb-cow-"))
        shutil.copytree(package_root, temporary_parent / "openbb")
        sys.path.insert(0, str(temporary_parent))
        from openbb import obb
        require(obb is not None, "OPENBB_IMPORT_MISSING")
        scope = "REAL_OPENBB_IMPORT_TEMP_COW_ONLY_NO_PROVIDER"

    return {
        "schema": "XRAY_NASDAQ_REAL_SDK_SMOKE_V1",
        "candidate": candidate,
        "distribution": distribution,
        "installed_version": installed,
        "scope": scope,
        "sdk_code_executed": True,
        "model_api_called": False,
        "mcp_server_connected": False,
        "market_data_requested": False,
        "vendor_licence_verified": False,
        "pit_477x500_verified": False,
        "oos_alpha_verified": False,
        "production_authorized": False,
        "may_issue_al": False,
        "may_place_order": False,
        "may_change_stop_target": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    args = parser.parse_args()
    try:
        print(json.dumps(smoke(args.candidate), sort_keys=True))
        return 0
    except Exception as exc:
        # Avoid dumping credentials, environment or full tracebacks into public logs.
        print(json.dumps({
            "schema": "XRAY_NASDAQ_REAL_SDK_SMOKE_V1",
            "candidate": args.candidate,
            "status": "HOLD",
            "error_type": type(exc).__name__,
            "error": str(exc)[:220],
            "production_authorized": False,
        }, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
