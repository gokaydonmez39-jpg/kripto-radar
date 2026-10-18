#!/usr/bin/env python3
"""Private-export OpenBB/Qlib history adapter into XRAY's existing 260x52 SHADOW guard.

Integration scope: transform published OpenBB and Qlib tabular OHLCV formats
into the existing c418_history_exact_session_shadow_guard.audit schema.
This performs no network requests, package imports, vendor key access, order
routing, canonical writes, notifications, MC PRIMARY or R92 registration.
Framework/library data formats are NOT themselves data-feed entitlements.
Only a local operator-provided, private JSON export is supported.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

import c418_history_exact_session_shadow_guard as hist
from source_epoch_freshness_guard import last_complete_session

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MASTER = ROOT / "canonical_current_master_manifest.json"
SCHEMA = "XRAY_EXTERNAL_OHLCV_PRIVATE_EXPORT_V1"
REPORT = "XRAY_EXTERNAL_OHLCV_SHADOW_BRIDGE_V1"
FORMAT_MAP = {
    "OPENBB_EQUITY_HISTORICAL": {
        "date": "date", "open": "open", "high": "high", "low": "low",
        "close": "close", "volume": "volume",
    },
    "QLIB_FEATURES_DAILY": {
        "date": "datetime", "open": "$open", "high": "$high", "low": "$low",
        "close": "$close", "volume": "$volume",
    },
}
TICKER = re.compile(r"[A-Z][A-Z0-9.-]{0,9}\Z")
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
MAX_PRIVATE_BYTES = 2_000_000
MAX_ROWS = 600


class InvalidPrivateResearchExport(ValueError):
    """A malformed/stale/untrusted export is never a zero-result market fact."""


def require(test: bool, reason: str) -> None:
    if not test:
        raise InvalidPrivateResearchExport("XRAY_EXTERNAL_" + reason)


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _date(value: object) -> str:
    require(type(value) is str and len(value) == 10, "DATE_FORMAT")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidPrivateResearchExport("XRAY_EXTERNAL_DATE_INVALID") from exc
    require(parsed.isoformat() == value, "DATE_CANONICAL")
    return value


def _strict_numeric(value: object, field: str) -> int | float:
    require(type(value) in (int, float), "NONNUMERIC_" + field.upper())
    require(math.isfinite(value) and value > 0, "INVALID_" + field.upper())
    return value


def _rows(export: dict) -> list[dict]:
    fmt = export["format"]
    keys = FORMAT_MAP[fmt]
    raw = export["rows"]
    require(type(raw) is list and 0 < len(raw) <= MAX_ROWS, "ROW_BOUNDS")
    symbol = export["symbol"]
    transformed = []
    for value in raw:
        require(type(value) is dict, "ROW_TYPE")
        if fmt == "OPENBB_EQUITY_HISTORICAL" and "symbol" in value:
            require(value["symbol"] == symbol, "SYMBOL_MISMATCH")
        if fmt == "QLIB_FEATURES_DAILY" and "instrument" in value:
            require(value["instrument"] == symbol, "QLIB_INSTRUMENT_MISMATCH")
        d = _date(value.get(keys["date"]))
        data = {"symbol": symbol, "date": d}
        for field in ("open", "high", "low", "close", "volume"):
            data[field] = _strict_numeric(value.get(keys[field]), field)
        require(hist.exact_positive_share_count(data["volume"]),
                "VOLUME_NOT_EXACT_POSITIVE_SHARES")
        require(data["low"] <= min(data["open"], data["close"])
                and data["high"] >= max(data["open"], data["close"], data["low"]),
                "OHLC_CONTRADICTION")
        transformed.append(data)
    # No deduplication or sorting by assumption: the shared 260 guard catches
    # duplicates, unexpected future bars and missing official sessions.
    return transformed


def _master_admits(export: dict, master: dict, master_blob: bytes,
                    expected_master_blob_sha: str, now: dt.datetime) -> None:
    require(type(expected_master_blob_sha) is str
            and HEX40.fullmatch(expected_master_blob_sha) is not None
            and git_blob_sha(master_blob) == expected_master_blob_sha,
            "CURRENT_MASTER_GIT_BLOB_MISMATCH")
    require(type(master) is dict
            and master.get("execution") == "NONE"
            and master.get("real_money") == "NO-GO"
            and master.get("unknown_never_pass") is True, "MASTER_SAFETY")
    admitted = master.get("pass_symbols")
    unknown = master.get("unknown_symbols")
    require(type(admitted) is list and type(unknown) is list
            and len(admitted) == len(set(admitted)) == master.get("pass_count")
            and len(unknown) == len(set(unknown)) == master.get("unknown_count")
            and set(admitted).isdisjoint(unknown), "MASTER_IDENTITY")
    symbol = export["symbol"]
    require(symbol in admitted, "MASTER_SYMBOL_NOT_ADMITTED")
    require(export["asof_et"] == master.get("asof_et")
            and export["asof_et"] == last_complete_session(now),
            "MASTER_ASOF_NOT_LATEST_COMPLETED")
    # A complete MASTER identity is not a canonical PRICE PASS or HISTORY PASS.


def inspect(export: object, master: object, master_blob: bytes,
            expected_master_blob_sha: str, *, now: dt.datetime) -> dict:
    require(type(export) is dict and export.get("schema") == SCHEMA,
            "EXPORT_SCHEMA")
    fmt = export.get("format")
    require(fmt in FORMAT_MAP, "FORMAT_UNSUPPORTED")
    symbol, asof = export.get("symbol"), export.get("asof_et")
    require(type(symbol) is str and TICKER.fullmatch(symbol) is not None,
            "SYMBOL_FORMAT")
    _date(asof)
    require(export.get("interval") == "1d", "NOT_DAILY")
    require(export.get("adjustment") in ("RAW", "SPLIT_ADJUSTED"),
            "ADJUSTMENT_UNKNOWN")
    # The actual market venue, feed name and redistribution entitlement are
    # unproven: require explicit source identity, never infer from "OpenBB".
    require(type(export.get("upstream_vendor")) is str
            and 2 <= len(export["upstream_vendor"]) <= 80
            and export["upstream_vendor"].strip() == export["upstream_vendor"],
            "VENDOR_IDENTITY_MISSING")
    _master_admits(export, master, master_blob, expected_master_blob_sha, now)
    transformed = _rows(export)
    result = hist.audit(transformed, [symbol], asof,
                        fmt + "_UNLICENSED_SHADOW", hist.official(asof))
    return {
        "schema": REPORT,
        "status": ("RESEARCH_NUMERIC_260X52_COMPLETE_UNATTESTED"
                   if result["numeric_exact_260_count"] == 1
                   else "RESEARCH_NUMERIC_INCOMPLETE_UNATTESTED"),
        "asof_et": asof,
        "source_format": fmt,
        "upstream_vendor": export["upstream_vendor"],
        "master_git_blob_sha": expected_master_blob_sha,
        "master_symbol_admitted": True,
        "numeric_exact_260_count": result["numeric_exact_260_count"],
        "nonpassing_count": result["nonpassing_count"],
        "reason_codes": result["reason_counts"],
        "license_rights_proven": False,
        "source_feed_entitlement_proven": False,
        "exchange_and_RTH_basis_proven": False,
        "adjustments_corporate_actions_proven": False,
        "source_independence_proven": False,
        "data_quality_promotable_to_c417": False,
        "can_create_PRIMARY": False,
        "can_create_PRICE_PASS": False,
        "can_create_HISTORY_PASS": False,
        "can_create_MC_PRIMARY": False,
        "can_register_R92": False,
        "can_send_notification": False,
        "alpha_authority": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "raw_vendor_rows_exported": False,
    }


def read_private(path: Path) -> dict:
    require(not path.resolve().is_relative_to(REPO.resolve()),
            "PRIVATE_FILE_INSIDE_PUBLIC_REPO")
    require(path.is_file() and not path.is_symlink(), "PRIVATE_FILE_UNAVAILABLE")
    require(path.stat().st_size <= MAX_PRIVATE_BYTES, "PRIVATE_EXPORT_OVERSIZE")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError, UnicodeError) as exc:
        raise InvalidPrivateResearchExport("XRAY_EXTERNAL_PRIVATE_EXPORT_INVALID") from exc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-export", type=Path, required=True)
    p.add_argument("--master-blob-sha", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.resolve().is_relative_to(REPO.resolve()):
        p.error("report path must be runner-private")
    try:
        content = MASTER.read_bytes()
        result = inspect(read_private(args.private_export),
                         json.loads(content), content, args.master_blob_sha,
                         now=dt.datetime.now(dt.timezone.utc))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # No provider exception or market data leaks into log output.
        print(json.dumps({"schema": REPORT, "status": "DATA_BLOCKED",
                          "reason_codes": ["INVALID_OR_UNBOUND_PRIVATE_EXPORT"],
                          "can_register_R92": False, "can_create_PRIMARY": False,
                          "execution": "NONE", "real_money": "NO-GO"}))
        raise SystemExit(2) from None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("XRAY_EXTERNAL_OHLCV_SHADOW=" + result["status"])
    print("XRAY_EXTERNAL_OHLCV_NO_LICENSE_NO_PRIMARY_NO_R92=true")


if __name__ == "__main__":
    main()
