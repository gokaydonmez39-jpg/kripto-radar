#!/usr/bin/env python3
"""Independent, local-only readback for the optional 477 EOD risk shadow.

No network, broker, Sheets, alert, AL or position authority. A missing
completed EOD snapshot is an explicit SKIP; an invalid shadow is REFUSED.
Neither outcome is a market clearance or historical PIT certification.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "XRAY_NASDAQ_477_OFFICIAL_SHADOW_V1"
STATUS = "RESEARCH_SHADOW_ONLY_NO_AUTHORITY"
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,14}\Z")
ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
ROW_FLAGS = ("market_cleared", "may_change_al", "may_change_stop_or_target",
             "may_notify", "may_place_order", "may_write_sheet")
TOP_FLAGS = ("market_clearance_proven", "historical_pit_proven",
             "first_public_availability_proven", "may_modify_al",
             "may_write_sheet", "may_notify", "may_place_order")
CURRENT = "OBSERVED_CURRENT_SAFETY_WITNESS_REVIEW_ONLY"
AFTER = "UNKNOWN_SOURCE_AFTER_EOD_CUTOFF"
STALE = "UNKNOWN_SOURCE_TOO_OLD"


class ReceiptRefused(ValueError):
    """Stable refusal code; never include private payloads in public logs."""


def require(condition, code):
    if not condition:
        raise ReceiptRefused(code)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def no_constant(_value):
    raise ReceiptRefused("NONFINITE_JSON")


def read_private(path):
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= 8_000_000, "PRIVATE_EVIDENCE_SIZE_INVALID")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=no_constant)


def digest(value):
    blob = json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(blob).hexdigest()


def instant(value):
    require(type(value) is str and 1 <= len(value) <= 40, "TIME_INVALID")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptRefused("TIME_INVALID") from exc
    require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0),
            "TIME_MUST_BE_UTC")
    return stamp.astimezone(timezone.utc)


def verify(snapshot, receipt, guard):
    """Require 477 exact ordered rows, source binding and no risk promotion."""
    require(all(type(x) is dict for x in (snapshot, receipt, guard)),
            "EVIDENCE_OBJECT_INVALID")
    require(receipt.get("schema") == SCHEMA and receipt.get("status") == STATUS,
            "SHADOW_SCHEMA_OR_STATUS_INVALID")
    require(type(receipt.get("rows_count")) is int
            and receipt["rows_count"] == 477, "SHADOW_ROW_COUNT_INVALID")
    rows = receipt.get("rows")
    source_rows = snapshot.get("rows")
    require(type(rows) is list and type(source_rows) is list
            and len(rows) == len(source_rows) == 477
            and all(type(x) is dict for x in rows + source_rows),
            "SHADOW_ROWS_INVALID")
    names = [item.get("symbol") for item in rows]
    source_names = [item.get("symbol") for item in source_rows]
    require(all(type(s) is str and SYMBOL.fullmatch(s) is not None
                for s in names)
            and len(set(names)) == 477 and names == source_names,
            "SHADOW_SYMBOL_ORDER_OR_SCOPE_DRIFT")
    asof = receipt.get("asof_et")
    require(asof == snapshot.get("asof_et") and type(asof) is str,
            "SHADOW_EOD_DATE_MISMATCH")
    require(ISO_DAY.fullmatch(asof) is not None, "SHADOW_EOD_DATE_INVALID")
    try:
        parsed_day = date.fromisoformat(asof)
    except ValueError as exc:
        raise ReceiptRefused("SHADOW_EOD_DATE_INVALID") from exc
    require(parsed_day.isoformat() == asof, "SHADOW_EOD_DATE_INVALID")
    require(all(type(snapshot.get(k)) is str
                and HEX_SHA.fullmatch(snapshot[k]) for k in
                ("scope_sha256", "analysis_fingerprint_sha256")),
            "SOURCE_SHA_INVALID")
    require(receipt.get("scope_sha256") == snapshot["scope_sha256"]
            and receipt.get("analysis_fingerprint_sha256")
            == snapshot["analysis_fingerprint_sha256"]
            and receipt.get("private_eod_snapshot_sha256") == digest(snapshot),
            "SHADOW_SOURCE_DIGEST_MISMATCH")
    require(receipt.get("nasdaq_witness_sha256") == digest(guard),
            "SHADOW_GUARD_DIGEST_MISMATCH")
    require(all(receipt.get(k) is False for k in TOP_FLAGS)
            and receipt.get("no_network_calls") is True,
            "UNAUTHORIZED_SHADOW_AUTHORITY")
    require(type(receipt.get("sec_unknown")) is int
            and receipt["sec_unknown"] == 477
            and type(receipt.get("corporate_actions_unknown")) is int
            and receipt["corporate_actions_unknown"] == 477,
            "UNPROVEN_SOURCE_INCORRECTLY_CLEARED")
    require(all(all(item.get(flag) is False for flag in ROW_FLAGS)
                and item.get("sec") == "UNKNOWN_NOT_477_PIT_PROVEN"
                and item.get("alpaca_corporate_actions")
                == "UNKNOWN_NO_PER_SYMBOL_TIMELY_LEDGER"
                and item.get("nasdaq") in (
                    "OBSERVED_VETO_REQUIRES_REVIEW",
                    "UNKNOWN_NOT_A_MARKET_CLEARANCE") for item in rows),
            "ROW_RISK_OR_AUTHORITY_DRIFT")
    cutoff = instant(receipt.get("decision_cutoff_utc"))
    seen = instant(receipt.get("source_observed_at_utc"))
    state = AFTER if seen > cutoff else (
        STALE if cutoff - seen > timedelta(hours=24) else CURRENT)
    require(receipt.get("nasdaq_source_state") == state,
            "SOURCE_TIME_CLASSIFICATION_DRIFT")
    flagged = sum(x["nasdaq"] == "OBSERVED_VETO_REQUIRES_REVIEW" for x in rows)
    require(type(receipt.get("nasdaq_veto_events_observed")) is int
            and receipt["nasdaq_veto_events_observed"] == flagged
            and type(receipt.get("nasdaq_unknown")) is int
            and receipt["nasdaq_unknown"] == 477 - flagged
            and (state == CURRENT or flagged == 0),
            "NASDAQ_REVIEW_COUNT_OR_ASOF_DRIFT")
    return "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE"


def evaluate(snapshot_path, receipt_path, guard_path):
    snap = Path(snapshot_path)
    out = Path(receipt_path)
    if not snap.is_file():
        require(not out.exists(), "ORPHAN_SHADOW_WITHOUT_COMPLETED_EOD")
        return "SKIPPED_NO_COMPLETED_SCAN"
    require(out.is_file(), "MISSING_SHADOW_OUTPUT")
    return verify(read_private(snap), read_private(out),
                  read_private(guard_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--guard", required=True)
    args = parser.parse_args(argv)
    try:
        status = evaluate(args.snapshot, args.receipt, args.guard)
        print(json.dumps({"official_shadow_receipt": status,
                          "market_clearance_proven": False},
                         sort_keys=True))
        return 0
    except (ReceiptRefused, ValueError, OSError, TypeError, KeyError,
            UnicodeError, OverflowError) as exc:
        code = str(exc) if isinstance(exc, ReceiptRefused) else "READBACK_INVALID"
        print(json.dumps({"official_shadow_receipt": "REFUSED",
                          "reason_code": code,
                          "market_clearance_proven": False}, sort_keys=True))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
