#!/usr/bin/env python3
"""Fail-closed social-tip identity-only research screen.

Untrusted social tickers cannot create PASS_PRICE, DV30, HISTORY, MC, R92,
an AL, a user notification, an order or an accepted primary market source.
The NASDAQ master is a dated identity-only source, not evidence of a quote.
No API, network, third-party dependencies or import of trading frameworks.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "XRAY_UNTRUSTED_SOCIAL_TIP_TEN_V1"
SOURCE = "https://x.com/aura_lixx/status/2111615210503168164"
KIND = "USER_SCREENSHOT_UNVERIFIED_INVESTMENT_CLAIMS"
IDENTITY_AUTHORITY = "NASDAQTRADER_EXPLICIT_TYPE_FILTER_V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER"
SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,9}\Z")
ROOT = Path(__file__).resolve().parent
TIP_KEYS = {"schema", "source_url", "observed_at", "tickers", "source_kind",
            "execution", "real_money", "production_authority",
            "r92_authority", "can_notify_user"}


def require(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError("XRAY_SOCIAL_TIP_" + label)


def iso_date(value: object) -> date:
    require(type(value) is str, "DATE_TYPE")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("XRAY_SOCIAL_TIP_DATE_FORMAT") from exc
    require(parsed.isoformat() == value, "DATE_CANONICAL")
    return parsed


def symbols(value: object, *, label: str) -> list[str]:
    require(type(value) is list, label + "_LIST")
    require(all(type(x) is str and SYMBOL.fullmatch(x) for x in value),
            label + "_INVALID_SYMBOL")
    require(len(value) == len(set(value)), label + "_DUPLICATE")
    return value


def validate_tip(tip: object) -> None:
    require(type(tip) is dict, "TIP_OBJECT")
    require(set(tip) == TIP_KEYS, "UNEXPECTED_TIP_FIELDS")
    require(tip.get("schema") == SCHEMA, "TIP_SCHEMA")
    require(tip.get("source_url") == SOURCE, "SOURCE_URL")
    require(tip.get("source_kind") == KIND, "SOURCE_KIND")
    observed = iso_date(tip.get("observed_at"))
    require(observed == date(2026, 10, 18), "SOURCE_OBSERVED_EPOCH")
    tickers = symbols(tip.get("tickers"), label="TIP")
    require(len(tickers) == 10, "TIP_TEN_EXACT")
    require(tip.get("execution") == "NONE" and
            tip.get("real_money") == "NO-GO", "NO_TRADE")
    for flag in ("production_authority", "r92_authority", "can_notify_user"):
        require(tip.get(flag) is False, "TIP_AUTHORITY_" + flag)


def validate_master(master: object) -> None:
    require(type(master) is dict, "MASTER_OBJECT")
    iso_date(master.get("asof_et"))
    require(master.get("identity_authority") == IDENTITY_AUTHORITY,
            "MASTER_NOT_OFFICIAL_NASDAQ_IDENTITY")
    require(master.get("unknown_never_pass") is True, "MASTER_UNKNOWN_SAFETY")
    require(master.get("execution") == "NONE" and
            master.get("real_money") == "NO-GO", "MASTER_NO_TRADE")
    passed = symbols(master.get("pass_symbols"), label="MASTER_PASS")
    unknown = symbols(master.get("unknown_symbols"), label="MASTER_UNKNOWN")
    require(passed == sorted(passed), "MASTER_PASS_UNSORTED")
    require(unknown == sorted(unknown), "MASTER_UNKNOWN_UNSORTED")
    require(not set(passed).intersection(unknown), "MASTER_OVERLAP")
    require(len(passed) > 0, "MASTER_EMPTY")
    require(type(master.get("pass_count")) is int and
            master["pass_count"] == len(passed), "MASTER_PASS_COUNT")
    require(type(master.get("unknown_count")) is int and
            master["unknown_count"] == len(unknown), "MASTER_UNKNOWN_COUNT")
    counts = master.get("counts")
    require(type(counts) is dict and
            type(counts.get("PASS_IDENTITY")) is int and
            counts["PASS_IDENTITY"] == len(passed) and
            type(counts.get("UNKNOWN_IDENTITY")) is int and
            counts["UNKNOWN_IDENTITY"] == len(unknown),
            "MASTER_IDENTITY_PARTITION")


def assess(tip: dict, master: dict, master_raw: bytes) -> dict:
    """Describe tip vs verified identity partition, never classify NYSE."""
    validate_tip(tip)
    validate_master(master)
    require(type(master_raw) is bytes and len(master_raw) > 0,
            "MASTER_SOURCE_BYTES_REQUIRED")
    try:
        parsed_master = json.loads(master_raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("XRAY_SOCIAL_TIP_MASTER_RAW_NOT_JSON") from exc
    require(type(parsed_master) is dict and parsed_master == master,
            "MASTER_RAW_BYTES_OBJECT_MISMATCH")
    asof = iso_date(master["asof_et"])
    observed = iso_date(tip["observed_at"])
    require(asof < observed, "MASTER_ASOF_NOT_PRIOR_TO_POST")
    passed = set(master["pass_symbols"])
    unknown = set(master["unknown_symbols"])
    seen = set(tip["tickers"])
    good = sorted(seen & passed)
    pending = sorted(seen & unknown)
    not_present = sorted(seen - passed - unknown)
    require(len(good) + len(pending) + len(not_present) == 10,
            "IDENTITY_PARTITION_INCOMPLETE")
    return {
        "schema": "XRAY_SOCIAL_TIP_IDENTITY_QUARANTINE_RECEIPT_V1",
        "status": "RESEARCH_ONLY_IDENTITY_SCREEN_NO_AL",
        "source_url": SOURCE, "source_kind": KIND,
        "asof_et": master["asof_et"],
        "observed_at": tip["observed_at"],
        "master_blob_sha256": hashlib.sha256(master_raw).hexdigest(),
        "master_identity_authority": IDENTITY_AUTHORITY,
        "identity_only_symbols": good,
        "unknown_identity_symbols": pending,
        "not_in_master_symbols": not_present,
        "not_in_master_classification":
            "NOT_IN_NASDAQ_MASTER_ASOF_NOT_EXCHANGE_PROOF",
        "identity_only_does_not_establish_price_or_tradeability": True,
        "license_not_implied_by_open_source": True,
        "market_data_license_attested": False,
        "price_verified": False, "dv30_verified": False,
        "history_verified": False, "independent_mc_verified": False,
        "risk_evaluated": False, "event_state_verified": False,
        "production_authority": False, "r92_authority": False,
        "buy_signals": 0, "notifications": 0,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tip", type=Path, required=True)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    tip_path, master_path, out = (args.tip.resolve(),
                                  args.master.resolve(), args.out.resolve())
    require(out != tip_path and out != master_path, "OVERWRITE_INPUT")
    # This shadow may only write into a separate temp directory, never
    # overwrite GitHub-tracked repository evidence or canonical gates.
    require(not out.is_relative_to(ROOT.parent), "REPOSITORY_WRITE_FORBIDDEN")
    require(tip_path.name == "aura_ten_untrusted_tips_20261018_v1.json",
            "TIP_PATH_NOT_APPROVED")
    require(master_path.name == "canonical_current_master_manifest.json",
            "MASTER_PATH_NOT_APPROVED")
    tip = json.loads(tip_path.read_text(encoding="utf-8"))
    raw = master_path.read_bytes()
    master = json.loads(raw)
    result = assess(tip, master, raw)
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "identity_only": len(result["identity_only_symbols"]),
                      "unknown_identity": len(result["unknown_identity_symbols"]),
                      "not_in_master": len(result["not_in_master_symbols"]),
                      "AL": result["buy_signals"],
                      "R92": result["r92_authority"]}, sort_keys=True))


if __name__ == "__main__":
    main()
