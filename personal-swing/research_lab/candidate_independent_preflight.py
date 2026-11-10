#!/usr/bin/env python3
"""XRAY 477 candidate *preflight*, not model/provider admission.

Offline only. Does not import third-party candidate SDKs, access a market feed,
read credentials, create timers, write to a Sheet or send trading instructions.
External source identities and Git blob hashes were read separately; a manifest
is not independent proof of licence, package integrity, or market provenance.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
from datetime import date
from pathlib import Path

from candidate_guard import PINS, validate

SCHEMA = "XRAY_CANDIDATE_INDEPENDENT_PREFLIGHT_V1"
PACKAGES = {
    "pydantic-ai": "pydantic-ai-slim",
    "mcp-use": "mcp-use",
    "qlib": "pyqlib",
    "openbb-v5": "openbb",
    "timesfm": "timesfm",
    "openbb-mcp": "openbb-mcp-server",
    "alpaca-mcp": "alpaca-mcp-server",
    "tradingview-charts": None,  # JS package: not a Python import
}
DIRECT_SOURCE_FILES = {
    "pydantic-ai": ("pydantic_ai_slim/pyproject.toml", "93c40fc5bb3979d0900fa2ac5555e462afb01820"),
    "mcp-use": ("libraries/python/pyproject.toml", "20243758ad0294bf4f468eea04564c813c19ab36"),
    "qlib": ("pyproject.toml", "54a44ab5fc28043796da48fc58a8c808c5922aca"),
    "openbb-v5": ("openbb_platform/pyproject.toml", "b28f7273b57324857fed9041a0aa4f7158c65d19"),
    "timesfm": ("README.md", "804951ffd5755267c96a1ef2867e0be895fae385"),
    "openbb-mcp": ("openbb_platform/pyproject.toml", "b28f7273b57324857fed9041a0aa4f7158c65d19"),
    "alpaca-mcp": ("README.md", "fe3f7e37192a2c3e5c76ed0f7523fb9a16871e78"),
    "tradingview-charts": ("README.md", None),
}


def _strict_string(s: object) -> bool:
    return type(s) is str and 0 < len(s) <= 200 and not any(c in s for c in "\r\n\0")


def assess(manifest: dict, *, distribution_versions: dict[str, str] | None = None) -> dict:
    """Reports what exists, **never** marks an SDK runtime test PASS."""
    validate(manifest)
    if distribution_versions is None:
        distribution_versions = {}
        for name in set(v for v in PACKAGES.values() if v):
            try:
                distribution_versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
    if not isinstance(distribution_versions, dict):
        raise ValueError("DISTRIBUTION_INPUT_INVALID")
    if not all(_strict_string(k) and _strict_string(v) for k, v in distribution_versions.items()):
        raise ValueError("DISTRIBUTION_INPUT_INVALID")
    rows = []
    for candidate in manifest["candidates"]:
        key = candidate["id"]
        distro = PACKAGES[key]
        observed_version = distribution_versions.get(distro) if distro else None
        source_path, source_blob = DIRECT_SOURCE_FILES[key]
        rows.append({
            "candidate": key,
            "group": candidate["group"],
            "upstream_commit_sha": PINS[key],
            "reviewed_source_path": source_path,
            "reviewed_source_blob_sha": source_blob,
            "python_distribution": distro,
            "distribution_installed": observed_version is not None,
            "observed_package_version": observed_version,
            "installed_version_matched_to_reviewed_commit": False,
            "source_licence_and_transitive_sbom_verified": False,
            "sdk_executed": False,
            "network_sandbox_attested": False,
            "vendor_data_accessed": False,
            "production_authorized": False,
            "status": "DISTRIBUTION_METADATA_ONLY_NO_SDK_PASS" if observed_version
                      else ("JS_ARTIFACT_NOT_TESTED" if distro is None else "SDK_NOT_INSTALLED"),
        })
    return {
        "schema": SCHEMA,
        "candidate_count": 8,
        "sdk_runtime_pass": 0,
        "licence_pass": 0,
        "independent_real_pit_pass": 0,
        "production_approved": 0,
        "sdk_imports_executed": 0,
        "network_calls": 0,
        "orders": 0,
        "new_schedules": 0,
        "candidates": rows,
    }


def check_xnas_sessions(candidate_dates: list[str], *, expected_min: int = 500) -> dict:
    """Checks only exchange calendar shape, NOT issuer lineage or PIT/source rights.

    Input is supplied by caller and untrusted. All candidate dates must be
    consecutive *XNAS sessions*. No inference from consecutive calendar days.
    """
    if type(expected_min) is not int or expected_min != 500:
        raise ValueError("FROZEN_XNAS_MIN_HISTORY_500")
    if not isinstance(candidate_dates, list) or len(candidate_dates) < 500:
        raise ValueError("XNAS_INSUFFICIENT_SESSIONS")
    if len(candidate_dates) > 15000:
        raise ValueError("XNAS_INPUT_TOO_LARGE")
    if not all(type(v) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}",v) for v in candidate_dates):
        raise ValueError("INVALID_XNAS_DATE_FORMAT")
    try:
        parsed = [date.fromisoformat(v) for v in candidate_dates]
    except ValueError as exc:
        raise ValueError("INVALID_XNAS_DATE") from exc
    if any(d.isoformat() != s for d,s in zip(parsed, candidate_dates)):
        raise ValueError("NONCANONICAL_XNAS_DATE")
    if not all(a < b for a,b in zip(parsed,parsed[1:])):
        raise ValueError("DUPLICATE_OR_UNORDERED_XNAS_DATE")
    try:
        import exchange_calendars as xc  # only the existing official-calendar dependency
        cal = xc.get_calendar("XNAS")
        observed = [v.strftime("%Y-%m-%d") for v in cal.sessions_in_range(parsed[0],parsed[-1])]
    except (ImportError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("XNAS_CALENDAR_UNAVAILABLE_OR_RANGE_INVALID") from exc
    if observed != candidate_dates:
        raise ValueError("NON_XNAS_OR_MISSING_SESSION")
    return {
        "schema": "XRAY_XNAS_CALENDAR_SHAPE_ONLY_V1",
        "status": "CALENDAR_SHAPE_PASS_PROVENANCE_UNVERIFIED",
        "session_count": len(candidate_dates),
        "first_session": candidate_dates[0],
        "last_session": candidate_dates[-1],
        "historical_issuer_membership_verified": False,
        "per_symbol_477_pit_verified": False,
        "external_data_rights_verified": False,
        "corporate_action_basis_verified": False,
        "oos_alpha_verified": False,
        "production_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("candidate_manifest.json")))
    parser.add_argument("--xnas-dates-file", help="Private local JSON list: reads dates ONLY, never prices or metadata")
    parser.add_argument("--require-production", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = assess(manifest)
        if args.xnas_dates_file:
            values = json.loads(Path(args.xnas_dates_file).read_text(encoding="utf-8"))
            result["xnas_calendar_shape"] = check_xnas_sessions(values)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 3 if args.require_production else 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status":"HOLD", "reason":str(exc)}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())