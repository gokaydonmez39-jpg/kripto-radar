#!/usr/bin/env python3
"""Private source-byte attestation for XRAY research numeric claims.

Independent research-only extension of research_numeric_provenance_shadow.
An operator-supplied externally pinned Git blob SHA is checked against exact
private source bytes. Each observation and claimed figure must match a source
record. A matching hash never proves independent publisher authenticity, legal
data entitlement, fresh RTH, issuer identity, or investment advice.

No vendor network, no external package, no broker, no public data file, no AL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import research_numeric_provenance_shadow as base

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "XRAY_PRIVATE_NUMERIC_SOURCE_RECORDS_V1"
REPORT = "XRAY_RESEARCH_NUMERIC_SOURCE_BYTES_SHADOW_V1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 1_000_000
FIELDS = frozenset(("id", "symbol", "field", "value", "unit", "asof_et"))


def git_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\x00" + content).hexdigest()


def require(check: bool, reason: str) -> None:
    if not check:
        raise ValueError("XRAY_SOURCE_BYTES_" + reason)


def strict_json(content: bytes) -> object:
    require(type(content) is bytes and 0 < len(content) <= MAX_BYTES,
            "INVALID_SOURCE_SIZE")
    def reject_duplicate_keys(pairs):
        d = {}
        for key, value in pairs:
            if key in d:
                raise ValueError("XRAY_SOURCE_BYTES_DUPLICATE_JSON_KEY")
            d[key] = value
        return d
    try:
        return json.loads(content.decode("utf-8"),
                          object_pairs_hook=reject_duplicate_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("XRAY_SOURCE_BYTES_INVALID_SOURCE_JSON") from exc


def inspect(claims: object, source_bytes: bytes, expected_source_git_sha: str) -> dict:
    require(type(expected_source_git_sha) is str
            and SHA40.fullmatch(expected_source_git_sha) is not None,
            "PIN_UNFORMED")
    require(git_sha(source_bytes) == expected_source_git_sha,
            "BYTE_HASH_MISMATCH")
    source = strict_json(source_bytes)
    require(type(source) is dict and set(source) == {"schema", "asof_et", "observations"}
            and source.get("schema") == SCHEMA, "SOURCE_SCHEMA")
    bound_report = base.audit(claims)
    require(source["asof_et"] == claims["asof_et"], "SOURCE_ASOF_MISMATCH")
    src_rows = source["observations"]
    claimed_rows = claims["observations"]
    require(type(src_rows) is list and type(claimed_rows) is list
            and 0 < len(src_rows) <= base.MAX_ROWS
            and len(src_rows) == len(claimed_rows), "SOURCE_SCOPE_COUNT")
    by_id = {}
    for row in src_rows:
        require(type(row) is dict and set(row) == FIELDS,
                "SOURCE_ROW_SCHEMA")
        # Reuse base numeric/symbol/epoch validation; SHA key is NOT source-controlled.
        checked = dict(row, source_blob_sha=expected_source_git_sha)
        base._row(checked, source["asof_et"], observation=True)
        require(row["id"] not in by_id, "SOURCE_DUPLICATE_OBSERVATION")
        by_id[row["id"]] = row
    require(len({r["id"] for r in claimed_rows}) == len(claimed_rows),
            "CLAIMED_DUPLICATE_OBSERVATION")
    for row in claimed_rows:
        require(row["source_blob_sha"] == expected_source_git_sha,
                "CLAIMED_SOURCE_HASH_MISMATCH")
        source_row = by_id.get(row["id"])
        require(source_row is not None, "OBSERVATION_ID_NOT_IN_SOURCE")
        require({k: row[k] for k in FIELDS} == source_row,
                "OBSERVATION_BYTES_NOT_EQUAL_SOURCE")
    structural_ok = bound_report["status"] == "STRUCTURALLY_BOUND_UNATTESTED"
    return {
        "schema": REPORT,
        "asof_et": source["asof_et"],
        "status": ("SOURCE_FILE_BYTES_AND_CLAIMS_MATCH_UNATTESTED"
                   if structural_ok else "DATA_BLOCKED_UNSUPPORTED_NUMERIC_CLAIMS"),
        "source_git_blob_sha": expected_source_git_sha,
        "source_bytes_match_independent_operator_pin": True,
        "record_count": len(src_rows),
        "claim_count": bound_report["claim_count"],
        "bound_count": bound_report["structurally_bound_count"],
        "rejected_count": bound_report["rejected_count"],
        "reason_counts": bound_report["reason_counts"],
        "operator_pin_origin_independently_authenticated": False,
        "publisher_signed_data_verified": False,
        "market_truth_verified": False,
        "vendor_entitlement_verified": False,
        "exchange_rth_complete_verified": False,
        "can_create_PRIMARY": False,
        "can_create_PRICE_PASS": False,
        "can_create_HISTORY_PASS": False,
        "can_create_MC_PRIMARY": False,
        "can_register_R92": False,
        "can_send_notification": False,
        "alpha_authority": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True, "vendor_raw_data_exported": False,
    }


def private_bytes(path: Path) -> bytes:
    require(not path.resolve().is_relative_to(ROOT.resolve()),
            "PUBLIC_REPOSITORY_PATH_FORBIDDEN")
    require(path.is_file() and not path.is_symlink()
            and 0 < path.stat().st_size <= MAX_BYTES, "PRIVATE_INPUT_UNAVAILABLE")
    return path.read_bytes()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-claims", type=Path, required=True)
    p.add_argument("--private-source", type=Path, required=True)
    p.add_argument("--expected-source-git-blob-sha", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if (args.out.resolve().is_relative_to(ROOT.resolve())
            or args.out.resolve() in
                (args.private_claims.resolve(), args.private_source.resolve())
            or args.out.is_symlink()):
        p.error("output must be distinct and private")
    try:
        claims = strict_json(private_bytes(args.private_claims))
        src = private_bytes(args.private_source)
        result = inspect(claims, src, args.expected_source_git_blob_sha)
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"schema": REPORT, "status": "DATA_BLOCKED",
                          "execution": "NONE", "real_money": "NO-GO",
                          "can_register_R92": False, "can_create_PRIMARY": False}))
        raise SystemExit(2) from None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("XRAY_SOURCE_BYTES_SHADOW=" + result["status"])
    if result["status"] != "SOURCE_FILE_BYTES_AND_CLAIMS_MATCH_UNATTESTED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
