#!/usr/bin/env python3
"""XRAY NASDAQ - offline-only candidate catalogue contract.

No imports of candidate frameworks, no network/SDK calls, no credentials,
no GitHub/SHEETS mutation, no schedule and no order.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SCHEMA = "XRAY_NASDAQ_RESEARCH_CANDIDATES_V1"
STRONG = {"pydantic-ai", "mcp-use", "qlib", "openbb-v5"}
HELPER = {"timesfm", "openbb-mcp", "alpaca-mcp", "tradingview-charts"}
FORBIDDEN = {
    "may_issue_al", "may_change_stop_or_target", "may_write_private_sheet",
    "may_emit_alert", "may_place_order", "may_access_broker", "may_read_secrets",
    "may_fetch_external_data", "may_install_packages", "may_create_schedule",
    "may_change_crypto_or_canonical"
}
PINS = {
    "pydantic-ai": "58b007e6c33b48b739035a56dc0f1f3849debb50",
    "mcp-use": "ac0b6a5390c98adc1dd0804c796bfc21b37f800c",
    "qlib": "54355232463878d2eebb91fe0ee5fa7fa1f5976c",
    "openbb-v5": "8c69d8d7632a965f765218162667b32074003fea",
    "timesfm": "e51928e27119cb17bebc005be2696b75e0a9e688",
    "openbb-mcp": "8c69d8d7632a965f765218162667b32074003fea",
    "alpaca-mcp": "63cc4278d87b31f3ed4efcfaa55624095c6d7be8",
    "tradingview-charts": "2e1d5ce9fa0cf2a1fc8d70e0df66237e622e52c8",
}
STATES = {
    "pydantic-ai": "YENI_ADAY", "mcp-use": "YENI_ADAY",
    "qlib": "MEVCUT_SENTETIK_SHADOW", "openbb-v5": "MEVCUT_88_KATALOG",
    "timesfm": "YENI_ADAY", "openbb-mcp": "MEVCUT_OPENBB_YETENEGI",
    "alpaca-mcp": "MEVCUT_88_KATALOG_BLOCKED",
    "tradingview-charts": "YENI_ADAY",
}
EXISTING_KEYS = {
    "openbb-v5": "code:openbq-org/openbb",
    "openbb-mcp": "code:openbq-org/openbb",
    "alpaca-mcp": "code:alpacahq/alpaca-mcp-server"
}
EXPECTED_URLS = {
    "pydantic-ai": "https://github.com/pydantic/pydantic-ai",
    "mcp-use": "https://github.com/mcp-use/mcp-use",
    "qlib": "https://github.com/microsoft/qlib",
    "openbb-v5": "https://github.com/openbq-org/OpenBB",
    "timesfm": "https://github.com/google-research/timesfm",
    "openbb-mcp": "https://github.com/openbq-org/OpenBB",
    "alpaca-mcp": "https://github.com/alpacahq/alpaca-mcp-server",
    "tradingview-charts": "https://github.com/tradingview/lightweight-charts"
}

def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)

def validate(document: dict) -> dict:
    require(type(document) is dict and document.get("schema") == SCHEMA,
            "SCHEMA_INVALID")
    require(document.get("scope") ==
            "personal-swing/research_lab offline ONLY; not a production install",
            "SCOPE_INVALID")
    core = document.get("core_policy")
    require(type(core) is dict and core.get("universe") == 477 and
            core.get("source") == "Alpaca IEX" and
            core.get("bar") == "1Day RTH raw" and
            core.get("execution") == "NONE" and core.get("orders") == "NO_ORDER",
            "CORE_CONTRACT_DRIFT")
    for field in ("technical_al_policy_change", "paid_new_services",
                  "new_schedules", "crypto_or_canonical_change"):
        require(core.get(field) is False, "CORE_SIDE_EFFECT_" + field)
    require(document.get("baseline_repo_main_sha") ==
            "f32765f3848e5984b084a96646151db422e12d7d",
            "BASELINE_REPOSITORY_PROVENANCE_DRIFT")
    require(document.get("recorded_repo_manifest_blob_sha") ==
            "6547f095bae9c6ed7b5b43d55ba0fc11b0042d92",
            "BASELINE_REGISTRY_PROVENANCE_DRIFT")
    entries = document.get("candidates")
    require(type(entries) is list and len(entries) == 8, "CANDIDATE_COUNT")
    ids = set()
    for e in entries:
        require(type(e) is dict, "ENTRY_NOT_OBJECT")
        key = e.get("id")
        require(type(key) is str and key not in ids, "DUPLICATE_OR_MISSING_ID")
        ids.add(key)
        require(key in EXPECTED_URLS and e.get("url") == EXPECTED_URLS[key],
                "UNRECOGNIZED_SOURCE")
        require(e.get("upstream_snapshot_sha") == PINS[key] and
                re.fullmatch(r"[0-9a-f]{40}", PINS[key]) is not None,
                "UPSTREAM_SHA_MISMATCH")
        require(e.get("pin_role") ==
                "DOCUMENTATION_REVIEW_REFERENCE_ONLY_NOT_EXECUTED",
                "UNAUTHORIZED_PIN_ROLE")
        require(e.get("current_state") == STATES[key],
                "UNVERIFIED_STATE_PROMOTION")
        expected_group = "STRONG" if key in STRONG else "HELPER"
        require(e.get("group") == expected_group, "INVALID_GROUP")
        require(e.get("existing_registry_key") == EXISTING_KEYS.get(key),
                "REGISTRY_ALIAS_DRIFT")
        require(e.get("admission") == "CATALOGUE_SHADOW_ONLY",
                "UNAUTHORIZED_ADMISSION")
        for f in ("external_dependencies_installed", "real_provider_pit_verified",
                  "production_authorized"):
            require(e.get(f) is False, "UNPROVEN_SUCCESS_" + f)
        p = e.get("policy")
        require(type(p) is dict and set(p) == FORBIDDEN, "CAPABILITY_POLICY_DRIFT")
        for cap in FORBIDDEN:
            require(p[cap] is False, "FORBIDDEN_" + cap)
        for f in ("purpose", "pilot", "acceptance", "current_state", "label"):
            require(type(e.get(f)) is str and len(e[f].strip()) > 0,
                    "UNSPECIFIED_" + f)
    require(ids == STRONG | HELPER, "MISSING_CANDIDATE")
    return {
        "status": "CATALOGUE_CONTRACT_PASS_NO_INTEGRATION_CLAIM",
        "strong": len(STRONG), "helper": len(HELPER),
        "distinct_projects_or_capabilities": len(ids),
        "already_recorded_registry_keys": sorted(set(EXISTING_KEYS.values())),
        "production_approved": 0, "vendor_calls": 0, "orders": 0,
        "new_schedules": 0, "model_imports": 0
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(
        Path(__file__).with_name("candidate_manifest.json")))
    args = parser.parse_args()
    try:
        document = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        report = validate(document)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}, sort_keys=True))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
