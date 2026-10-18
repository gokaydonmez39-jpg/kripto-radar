#!/usr/bin/env python3
"""Research-only figure/evidence binding guard inspired by Vibe-Trading's concepts.

Independent implementation: no external code copied or imported.
This can reject unsupported numeric narratives; it CANNOT authenticate
an observation, grant source licenses, produce market-data PASS/R92/AL,
change any canonical policy, send alerts, or execute orders.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SCHEMA = "XRAY_RESEARCH_NUMERIC_CLAIM_INPUT_V1"
REPORT = "XRAY_RESEARCH_NUMERIC_PROVENANCE_SHADOW_V1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
SYM = re.compile(r"[A-Z][A-Z0-9.-]{0,9}\Z")
KEY = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
FIELDS = {
    "close_usd": "USD",
    "market_cap_usd": "USD",
    "dv30_usd": "USD",
    "volume_shares": "shares",
}
MAX_ROWS = 250


def amount(value: object) -> Decimal:
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,12})?", value):
        raise ValueError("NUMBER_MUST_BE_CANONICAL_DECIMAL_STRING")
    try:
        x = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("NUMBER_INVALID") from exc
    if not x.is_finite() or x <= 0:
        raise ValueError("NUMBER_NON_POSITIVE")
    return x


def date(value: object) -> str:
    if type(value) is not str or len(value) != 10:
        raise ValueError("DATE_INVALID")
    try:
        d = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("DATE_INVALID") from exc
    if d.isoformat() != value:
        raise ValueError("DATE_INVALID")
    return value


def _row(row: object, asof: str, *, observation: bool) -> None:
    if type(row) is not dict:
        raise ValueError("ROW_NOT_OBJECT")
    for name in ("id", "symbol", "field", "value", "unit", "asof_et", "source_blob_sha"):
        if name not in row:
            raise ValueError("ROW_MISSING_" + name.upper())
    if type(row["id"]) is not str or KEY.fullmatch(row["id"]) is None:
        raise ValueError("ROW_ID_INVALID")
    if type(row["symbol"]) is not str or SYM.fullmatch(row["symbol"]) is None:
        raise ValueError("ROW_SYMBOL_INVALID")
    if row["field"] not in FIELDS or row["unit"] != FIELDS[row["field"]]:
        raise ValueError("ROW_FIELD_UNIT_INVALID")
    date(row["asof_et"])
    if row["asof_et"] != asof:
        raise ValueError("ROW_EPOCH_MISMATCH")
    if type(row["source_blob_sha"]) is not str or HEX40.fullmatch(row["source_blob_sha"]) is None:
        raise ValueError("ROW_SOURCE_SHA_INVALID")
    amount(row["value"])
    if not observation:
        if type(row.get("observation_id")) is not str or KEY.fullmatch(row["observation_id"]) is None:
            raise ValueError("ROW_EVIDENCE_POINTER_INVALID")


def audit(doc: object) -> dict:
    if type(doc) is not dict or doc.get("schema") != SCHEMA:
        raise ValueError("SCHEMA_INVALID")
    asof = date(doc.get("asof_et"))
    if (doc.get("execution") != "NONE" or doc.get("real_money") != "NO-GO"
            or doc.get("unknown_never_pass") is not True):
        raise ValueError("NO_TRADE_POLICY_INVALID")
    observations, claims = doc.get("observations"), doc.get("claims")
    if (type(observations) is not list or type(claims) is not list
            or len(observations) > MAX_ROWS or len(claims) > MAX_ROWS):
        raise ValueError("ROW_BOUNDS")
    seen = {}
    for row in observations:
        _row(row, asof, observation=True)
        if row["id"] in seen:
            raise ValueError("DUPLICATE_OBSERVATION_ID")
        seen[row["id"]] = row
    reason_counts = {}
    bound = 0
    for row in claims:
        _row(row, asof, observation=False)
        evidence = seen.get(row["observation_id"])
        if evidence is None:
            reason = "NO_REFERENCED_OBSERVATION"
        elif any(row[k] != evidence[k] for k in
                 ("symbol", "field", "unit", "asof_et", "source_blob_sha")):
            reason = "EVIDENCE_IDENTITY_OR_FIELD_MISMATCH"
        elif amount(row["value"]) != amount(evidence["value"]):
            reason = "NUMERIC_VALUE_NOT_OBSERVED"
        else:
            reason = None
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        else:
            bound += 1
    return {
        "schema": REPORT, "asof_et": asof,
        "status": "STRUCTURALLY_BOUND_UNATTESTED" if bound == len(claims) and claims
                  else "UNSUPPORTED_NUMERIC_CLAIMS",
        "observation_count": len(observations),
        "claim_count": len(claims), "structurally_bound_count": bound,
        "rejected_count": len(claims) - bound,
        "reason_counts": dict(sorted(reason_counts.items())),
        "observation_source_bytes_verified": False,
        "vendor_entitlement_verified": False,
        "claim_market_truth_verified": False,
        "can_create_PRIMARY": False,
        "can_create_PRICE_PASS": False,
        "can_create_HISTORY_PASS": False,
        "can_create_MC_PRIMARY": False,
        "can_register_R92": False,
        "can_send_notification": False,
        "alpha_authority": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True, "raw_vendor_data_exported": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (args.private_input.resolve().is_relative_to(REPO.resolve())
            or args.out.resolve().is_relative_to(REPO.resolve())):
        parser.error("all input/output must stay private, outside the public repository")
    if (not args.private_input.is_file() or args.private_input.is_symlink()
            or args.private_input.stat().st_size > 2_000_000):
        parser.error("private input missing or oversized")
    try:
        payload = json.loads(args.private_input.read_text(encoding="utf-8"),
                             parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        result = audit(payload)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"schema": REPORT, "status": "DATA_BLOCKED",
                          "can_register_R92": False, "execution": "NONE",
                          "real_money": "NO-GO"}))
        raise SystemExit(2) from None
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("XRAY_NUMERIC_PROVENANCE_SHADOW=" + result["status"])
    if result["status"] != "STRUCTURALLY_BOUND_UNATTESTED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
