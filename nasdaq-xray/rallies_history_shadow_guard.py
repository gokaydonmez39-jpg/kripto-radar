#!/usr/bin/env python3
"""Rallies 260x52 exact-session research diagnostic. NO collection or alpha.

Use only private locally authorized market-data inputs. A successful connector
read does NOT grant unattended non-display, internal retention, or distribution
rights. Results contain counts/reason codes only; raw bars never leave caller.
C4.17 and current source precedence are immutable. Synthetic tests are TESTS.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path

from current_history_source_request import expected_dates
from history_transport_cache_guard import official_completed_sessions

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "XRAY_RALLIES_260_52_HISTORY_SHADOW_GUARD_V1"
NON_PROMOTION = {
    "schema": SCHEMA,
    "source": "RALLIES_GET_PRICE_FROM_DATE_RANGE",
    "production_authority": False,
    "c417_history_pass": False,
    "c417_dv30_pass": False,
    "c417_mc_primary": False,
    "r92_eligible": False,
    "licensed_cache_created": False,
    "vendor_raw_data_exported": False,
    "execution": "NONE",
    "real_money": "NO-GO",
    "unknown_never_pass": True,
}

def safe_day(value):
    if not isinstance(value, str):
        return None
    try:
        day = dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return day if day.isoformat() == value else None

def inspect(rows, *, asof, symbol, expected260, completed52, official):
    if (not safe_day(asof)
        or not isinstance(symbol, str) or not symbol
        or len(expected260) != 260 or len(set(expected260)) != 260
        or len(completed52) != 52 or len(set(completed52)) != 52
        or not all(safe_day(d) for d in expected260 + completed52)
        or not set(expected260).issubset(set(official))
        or not set(completed52).issubset(set(official))
        or expected260[-1] != asof):
        raise ValueError("INVALID_PINNED_NASDAQ_HISTORY_CALENDAR")
    reasons = {
        "PROVIDER_AUTOMATION_RIGHTS_UNVERIFIED",
        "PROVIDER_NONDISPLAY_AND_RETAIN_RIGHTS_UNVERIFIED",
        "RTH_AND_UPSTREAM_AGGREGATION_UNVERIFIED",
        "ADJUSTMENT_AND_CORPORATE_ACTION_BASIS_UNVERIFIED",
        "TICKER_IDENTITY_NOT_ECHOED_BY_SOURCE",
        "INDEPENDENT_RAW_CLOSE_AND_VOLUME_NOT_ATTESTED",
    }
    unique = {}
    duplicates = 0
    invalid = 0
    off_calendar = 0
    if not isinstance(rows, list):
        rows = []
        reasons.add("SOURCE_RESPONSE_NOT_LIST")
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        day = safe_day(row.get("date"))
        if day is None or day.isoformat() > asof or day.isoformat() not in official:
            off_calendar += 1
            continue
        if day.isoformat() in unique:
            duplicates += 1
            continue
        fields = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
        if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in fields):
            invalid += 1
            continue
        op, hi, lo, cl, vol = fields
        if hi < max(op, lo, cl) or lo > min(op, hi, cl):
            invalid += 1
            continue
        unique[day.isoformat()] = row
    required = set(expected260)
    covered = required.intersection(unique)
    week_ends = set(completed52).intersection(unique)
    fractional = sum(not float(unique[d]["volume"]).is_integer() for d in covered)
    if len(covered) != 260:
        reasons.add("EXACT_260_COMPLETED_SESSIONS_NOT_PROVEN")
    if len(week_ends) != 52:
        reasons.add("EXACT_52_COMPLETED_WEEK_ENDS_NOT_PROVEN")
    if duplicates:
        reasons.add("DUPLICATE_DATE_REJECTED")
    if invalid:
        reasons.add("INVALID_OHLCV_REJECTED")
    if off_calendar:
        reasons.add("AFTER_ASOF_OR_NONTRADING_DATE_REJECTED")
    if fractional:
        reasons.add("FRACTIONAL_SHARE_VOLUME_WITHOUT_SOURCE_ADJUSTMENT_PROOF")
    if not rows:
        reasons.add("NO_REAL_SOURCE_ROWS")
    structure = (len(covered) == 260 and len(week_ends) == 52
                 and not duplicates and not invalid and not off_calendar)
    return dict(
        NON_PROMOTION,
        status="SHADOW_STRUCTURAL_COVERAGE_OBSERVED_NO_ALPHA" if structure
               else "BLOCKED_HISTORY_COVERAGE_OR_SHAPE",
        symbol=symbol,
        asof_et=asof,
        source_row_count=len(rows),
        accepted_unique_official_sessions=len(unique),
        required_260_sessions_observed=len(covered),
        completed_52_week_ends_observed=len(week_ends),
        missing_required_sessions=260 - len(covered),
        fractional_volume_required_sessions=fractional,
        duplicated_date_count=duplicates,
        invalid_ohlcv_count=invalid,
        outside_official_calendar_count=off_calendar,
        structure_only=structure,
        reason_codes=sorted(reasons),
    )

def selftest():
    asof = "2026-10-09"
    days, weeks = expected_dates(asof)
    official = official_completed_sessions(asof)
    def row(d):
        return dict(date=d, open=10.0, high=12.0, low=9.0,
                    close=11.0, volume=1000)
    base = [row(d) for d in days]
    def check(rows):
        return inspect(rows, asof=asof, symbol="TEST_FIXTURE",
                       expected260=days, completed52=weeks, official=official)
    x = check(base)
    assert x["structure_only"] and x["required_260_sessions_observed"] == 260
    assert x["completed_52_week_ends_observed"] == 52
    assert x["production_authority"] is False and x["r92_eligible"] is False
    assert x["c417_history_pass"] is False and x["c417_dv30_pass"] is False
    assert x["c417_mc_primary"] is False and x["vendor_raw_data_exported"] is False
    assert "PROVIDER_AUTOMATION_RIGHTS_UNVERIFIED" in x["reason_codes"]
    assert "ADJUSTMENT_AND_CORPORATE_ACTION_BASIS_UNVERIFIED" in x["reason_codes"]
    assert "INDEPENDENT_RAW_CLOSE_AND_VOLUME_NOT_ATTESTED" in x["reason_codes"]
    assert not check(base[:-1])["structure_only"]
    assert "EXACT_260_COMPLETED_SESSIONS_NOT_PROVEN" in check(base[:-1])["reason_codes"]
    assert "DUPLICATE_DATE_REJECTED" in check(base + [base[0]])["reason_codes"]
    assert not check(base + [base[0]])["structure_only"]
    fraction = [dict(r) for r in base]
    fraction[0]["volume"] = 1000.41
    y = check(fraction)
    assert y["structure_only"] and y["fractional_volume_required_sessions"] == 1
    assert "FRACTIONAL_SHARE_VOLUME_WITHOUT_SOURCE_ADJUSTMENT_PROOF" in y["reason_codes"]
    assert y["c417_history_pass"] is False
    future = [dict(r) for r in base]
    future[0]["date"] = "2026-10-12"
    assert "AFTER_ASOF_OR_NONTRADING_DATE_REJECTED" in check(future)["reason_codes"]
    weekend = [dict(r) for r in base]
    weekend[0]["date"] = "2026-10-10"
    assert not check(weekend)["structure_only"]
    broken = [dict(r) for r in base]
    broken[0]["high"] = 3.0
    assert "INVALID_OHLCV_REJECTED" in check(broken)["reason_codes"]
    for bad in ([], None, ["nondict"]):
        assert not check(bad)["structure_only"]
    try:
        inspect(base, asof=asof, symbol="TEST", expected260=days[:-1],
                completed52=weeks, official=official)
    except ValueError:
        pass
    else:
        raise AssertionError("BROKEN_EXPECTED_SESSION_LIST_ACCEPTED")
    print("XRAY_RALLIES_HISTORY_SHADOW_SELFTEST=PASS_260_52_ALL_NEGATIVES_NO_ALPHA")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--symbol")
    ap.add_argument("--private-json", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.symbol or not args.private_json:
        raise SystemExit("PRIVATE_INPUT_REQUIRED_NO_VENDOR_FETCH")
    src = args.private_json.resolve()
    if (not src.is_file() or src.is_relative_to(ROOT.resolve())):
        raise SystemExit("DATA_MUST_BE_PRIVATE_OUTSIDE_PUBLIC_REPOSITORY")
    price = json.loads((ROOT / "nasdaq-xray/canonical_current_price_dv30.json").read_text())
    symbols = price.get("pass_symbols") or []
    if args.symbol != "QQQ" and args.symbol not in symbols:
        raise SystemExit("SYMBOL_OUTSIDE_EXACT_CURRENT_PRICE_PASS_SCOPE")
    asof = price["asof_et"]
    days, weeks = expected_dates(asof)
    doc = json.loads(src.read_text())
    result = inspect(doc.get("result") if isinstance(doc, dict) else None,
                     asof=asof, symbol=args.symbol, expected260=days,
                     completed52=weeks, official=official_completed_sessions(asof))
    print(json.dumps(result, sort_keys=True))
    # A real source can never be admitted to C4.17 by this diagnostic.
    raise SystemExit(2)

if __name__ == "__main__":
    main()
