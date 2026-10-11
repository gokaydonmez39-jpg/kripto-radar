#!/usr/bin/env python3
"""C4.18 research-only common-feed fingerprint guard.

Only caller-supplied, privately authorized observations. Never fetch vendor
data, publish bars, infer genuine source independence, or upgrade C4.17.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

SCHEMA = "XRAY_C418_DUPLICATE_FEED_SHADOW_GUARD_V1"
FIELDS = ("open", "high", "low", "close", "volume", "vwap", "trades", "timestamp_ms")
MIN_OVERLAP = 20
MIN_FULL_MATCH = 0.95
MIN_FRACTIONAL_MATCH = 5

def _is_number(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0

def normalize(provider_rows):
    """Exact case-sensitive symbol/date join; no fuzzy identities."""
    if not isinstance(provider_rows, list):
        return None, "ROW_COLLECTION_INVALID"
    found = {}
    for row in provider_rows:
        if not isinstance(row, dict):
            return None, "ROW_OBJECT_INVALID"
        key = (row.get("ticker"), row.get("date"))
        if (not isinstance(key[0], str) or not key[0]
            or not isinstance(key[1], str) or len(key[1]) != 10):
            return None, "SYMBOL_OR_DATE_INVALID"
        if not all(_is_number(row.get(k)) for k in FIELDS):
            return None, "NON_FINITE_OR_NEGATIVE_METRIC"
        if row["volume"] <= 0 or any(row[k] <= 0 for k in ("open", "high", "low", "close")):
            return None, "NON_POSITIVE_OHLCV"
        if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"], row["low"]):
            return None, "OHLC_INVALID"
        if key in found:
            return None, "DUPLICATE_SYMBOL_DATE"
        found[key] = row
    return found, None

def audit(rows_a, rows_b, *, provider_a, provider_b, asof_et):
    report = {
        "schema": SCHEMA, "asof_et": asof_et,
        "providers": [provider_a, provider_b],
        "status": "UNKNOWN_COMMON_UPSTREAM",
        "overlap": 0, "full_value_matches": 0, "fractional_volume_matches": 0,
        "strong_duplicate_fingerprint": False,
        "independence_proven": False, "independent_source_vote_count": 0,
        "reason_codes": [], "production_authority": False,
        "can_create_PRIMARY": False, "can_create_HISTORY_PASS": False,
        "can_register_R92": False, "execution": "NONE",
        "real_money": "NO-GO", "unknown_never_pass": True,
        "vendor_raw_data_exported": False,
    }
    if (not isinstance(provider_a, str) or not isinstance(provider_b, str)
        or not provider_a or not provider_b or provider_a == provider_b
        or not isinstance(asof_et, str) or len(asof_et) != 10):
        report["reason_codes"] = ["PROVIDER_OR_ASOF_INVALID"]
        return report
    a, ea = normalize(rows_a)
    b, eb = normalize(rows_b)
    if ea or eb:
        report["reason_codes"] = [x for x in (ea, eb) if x]
        return report
    shared = a.keys() & b.keys()
    report["overlap"] = len(shared)
    for key in shared:
        x, y = a[key], b[key]
        same = all(x[k] == y[k] for k in FIELDS)
        if same:
            report["full_value_matches"] += 1
            if not float(x["volume"]).is_integer():
                report["fractional_volume_matches"] += 1
    if len(shared) < MIN_OVERLAP:
        report["reason_codes"] = ["INSUFFICIENT_OVERLAP_TO_FINGERPRINT"]
        return report
    ratio = report["full_value_matches"] / len(shared)
    if ratio >= MIN_FULL_MATCH and report["fractional_volume_matches"] >= MIN_FRACTIONAL_MATCH:
        report["status"] = "STRONG_DUPLICATE_FEED_FINGERPRINT"
        report["strong_duplicate_fingerprint"] = True
        report["reason_codes"] = [
            "SAME_OR_SHARED_UPSTREAM_PLAUSIBLE_INDEPENDENCE_NOT_ESTABLISHED",
            "SOURCE_ROOT_AND_DATA_RIGHTS_REQUIRE_INDEPENDENT_EVIDENCE",
        ]
    else:
        report["reason_codes"] = [
            "NO_STRONG_DUPLICATE_FINGERPRINT_BUT_INDEPENDENCE_STILL_UNVERIFIED"
        ]
    return report

def selftest():
    rows = []
    for i in range(28):
        rows.append({
            "ticker": f"T{i:03d}", "date": "2026-10-09",
            "open": 10.0 + i, "high": 10.2 + i, "low": 9.8 + i,
            "close": 10.1 + i, "volume": 1000.123456 + i,
            "vwap": 10.03 + i, "trades": 21 + i, "timestamp_ms": 1791576000000,
        })
    other = copy.deepcopy(rows)
    hit = audit(rows, other, provider_a="Massive", provider_b="Rallies", asof_et="2026-10-09")
    assert hit["status"] == "STRONG_DUPLICATE_FEED_FINGERPRINT"
    assert hit["overlap"] == hit["full_value_matches"] == 28
    assert hit["fractional_volume_matches"] == 28
    assert hit["independence_proven"] is False and hit["independent_source_vote_count"] == 0
    assert not hit["can_create_PRIMARY"] and not hit["can_register_R92"]
    other[0]["close"] += 0.01
    result = audit(rows, other, provider_a="Massive", provider_b="Rallies", asof_et="2026-10-09")
    assert result["strong_duplicate_fingerprint"] is True and result["full_value_matches"] == 27
    for row in other[:4]:
        row["close"] += 0.03
    result = audit(rows, other, provider_a="Massive", provider_b="Rallies", asof_et="2026-10-09")
    assert result["strong_duplicate_fingerprint"] is False
    assert result["independence_proven"] is False
    for case in (
        audit(rows[:3], rows[:3], provider_a="Massive", provider_b="Rallies", asof_et="2026-10-09"),
        audit(rows, rows, provider_a="Massive", provider_b="Massive", asof_et="2026-10-09"),
        audit(rows, None, provider_a="Massive", provider_b="Rallies", asof_et="2026-10-09"),
    ):
        assert case["status"] == "UNKNOWN_COMMON_UPSTREAM"
        assert case["independence_proven"] is False
    bad = copy.deepcopy(rows);bad.append(copy.deepcopy(rows[0]))
    assert "DUPLICATE_SYMBOL_DATE" in audit(rows,bad,provider_a="Massive",provider_b="Rallies",asof_et="2026-10-09")["reason_codes"]
    bad = copy.deepcopy(rows);bad[0]["volume"] = float("nan")
    assert "NON_FINITE_OR_NEGATIVE_METRIC" in audit(rows,bad,provider_a="Massive",provider_b="Rallies",asof_et="2026-10-09")["reason_codes"]
    print("XRAY_C418_DUPLICATE_FEED_SELFTEST=PASS_FINGERPRINT_CASE_COLLISION_DUPLICATE_NAN_INDEPENDENCE_NEVER_PROVEN")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--private-a", type=Path)
    ap.add_argument("--private-b", type=Path)
    ap.add_argument("--provider-a")
    ap.add_argument("--provider-b")
    ap.add_argument("--asof")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    repo = Path(__file__).resolve().parent.parent
    files = (args.private_a, args.private_b)
    if (None in files or not args.provider_a or not args.provider_b or not args.asof
        or any(x.resolve().is_relative_to(repo) for x in files)):
        print(json.dumps({
            "schema": SCHEMA, "status": "DATA_BLOCKED",
            "can_create_PRIMARY": False, "can_register_R92": False,
            "reason_codes": ["PRIVATE_AUTHORITATIVE_INPUT_REQUIRED"],
            "execution": "NONE", "real_money": "NO-GO"
        },sort_keys=True))
        raise SystemExit(2)
    result = audit(json.loads(files[0].read_text()), json.loads(files[1].read_text()),
                   provider_a=args.provider_a, provider_b=args.provider_b, asof_et=args.asof)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(2)

if __name__ == "__main__":
    main()
