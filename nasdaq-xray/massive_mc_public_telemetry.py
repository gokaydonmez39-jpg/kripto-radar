#!/usr/bin/env python3
"""Publish only license-safe operational telemetry from Massive MC shadow runs.

This file must never emit ticker-level or derived vendor market data to public
GitHub Actions artifacts. The raw input stays only in the ephemeral runner temp.
NO MC promotion, R92 creation, execution, or external data acquisition.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

INPUT_SCHEMA = "XRAY_MASSIVE_MC_SHADOW_V1"
OUTPUT_SCHEMA = "XRAY_MASSIVE_MC_PUBLIC_TELEMETRY_V1"
ALLOWED_STATUS = {"BLOCKED_NO_RUNTIME_KEY", "SHADOW_PROBED_NON_ALPHA"}


def sanitize(obj: dict) -> dict:
    if not isinstance(obj, dict) or obj.get("schema") != INPUT_SCHEMA:
        raise ValueError("INPUT_SCHEMA_INVALID")
    asof = obj.get("asof_et")
    if not isinstance(asof, str) or dt.date.fromisoformat(asof).isoformat() != asof:
        raise ValueError("ASOF_INVALID")
    n = obj.get("requested_count")
    records = obj.get("records")
    if type(n) is not int or not (1 <= n <= 5):
        raise ValueError("FREE_TIER_BOUND_INVALID")
    if not isinstance(records, dict) or len(records) != n:
        raise ValueError("RECORD_COUNT_MISMATCH")
    if obj.get("status") not in ALLOWED_STATUS:
        raise ValueError("RUN_STATUS_INVALID")
    if obj.get("execution") != "NONE" or obj.get("real_money") != "NO-GO":
        raise ValueError("EXECUTION_SAFETY_INVALID")
    if obj.get("unknown_never_pass") is not True or obj.get("policy_unchanged") != "C4.17":
        raise ValueError("POLICY_SAFETY_INVALID")
    for k in ("mc_primary_pass_created", "candidate_created", "r92_created"):
        if obj.get(k) is not False:
            raise ValueError("SHADOW_NON_PROMOTION_INVALID:" + k)
    if obj["status"] == "BLOCKED_NO_RUNTIME_KEY" and any(
        not isinstance(v, dict) or v.get("reason") != "NO_RUNTIME_KEY" or v.get("state") != "UNKNOWN"
        for v in records.values()
    ):
        raise ValueError("MISSING_KEY_STATE_INCONSISTENT")
    # Deliberately do not copy ticker, CIK, market cap, price, state counts,
    # classification outcomes, symbol lists, per-ticker errors, or raw data.
    return {
        "schema": OUTPUT_SCHEMA,
        "asof_et": asof,
        "status": obj["status"],
        "requested_count": n,
        "execution": "NONE",
        "real_money": "NO-GO",
        "policy_unchanged": "C4.17",
        "unknown_never_pass": True,
        "mc_primary_pass_created": False,
        "candidate_created": False,
        "r92_created": False,
        "public_artifact_vendor_data": False,
        "source_role": "OPERATIONAL_HEALTH_ONLY_NOT_MARKET_EVIDENCE",
    }


def selftest() -> None:
    raw = {
        "schema": INPUT_SCHEMA, "asof_et": "2026-10-07",
        "status": "SHADOW_PROBED_NON_ALPHA", "requested_count": 1,
        "records": {"SECRET_TICKER": {"market_cap_usd": 2456789012, "cik": "0001234567",
                                      "state": "SHADOW_OBSERVED_ABOVE_2B"}},
        "execution": "NONE", "real_money": "NO-GO", "policy_unchanged": "C4.17",
        "unknown_never_pass": True, "mc_primary_pass_created": False,
        "candidate_created": False, "r92_created": False,
    }
    clean = sanitize(raw)
    payload = json.dumps(clean)
    assert "SECRET_TICKER" not in payload and "2456789012" not in payload
    assert "0001234567" not in payload and "SHADOW_OBSERVED" not in payload
    assert clean["public_artifact_vendor_data"] is False
    blocked = dict(raw, status="BLOCKED_NO_RUNTIME_KEY",
                   records={"SECRET_TICKER": {"state": "UNKNOWN", "reason": "NO_RUNTIME_KEY"}})
    assert sanitize(blocked)["status"] == "BLOCKED_NO_RUNTIME_KEY"
    for change in (
        {"schema": "WRONG"}, {"requested_count": 6}, {"requested_count": True},
        {"records": {}}, {"candidate_created": True}, {"r92_created": True},
        {"mc_primary_pass_created": True}, {"unknown_never_pass": False},
        {"execution": "REAL"}, {"status": "PRIMARY_PASS"},
        {"asof_et": "bad"},
    ):
        test = dict(raw, **change)
        try:
            sanitize(test)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("INVALID_INPUT_ACCEPTED:" + repr(change))
    print("XRAY_MASSIVE_PUBLIC_TELEMETRY_SELFTEST=PASS (ZERO_VENDOR_DATA)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--input", type=pathlib.Path)
    p.add_argument("--out", type=pathlib.Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.input or not args.out:
        p.error("--input and --out required")
    # No stale telemetry may survive a failed sanitation attempt.
    args.out.unlink(missing_ok=True)
    obj = json.loads(args.input.read_text(encoding="utf-8"))
    telemetry = sanitize(obj)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("XRAY_MASSIVE_PUBLIC_TELEMETRY=SAFE status=" + telemetry["status"])


if __name__ == "__main__":
    main()
