#!/usr/bin/env python3
"""Append-only *proposal* for cross-session symbolic A/B/D research memory.

This is NOT canonical R92, AL, an investment return study, a notification, or
authority to write main. Input must be an independently verified XRAY research
operations acceptance receipt; only source-bound symbolic membership survives.
The caller must authenticate the Actions artifact and run IDs externally.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "XRAY_SYMBOLIC_CANDIDATE_MEMORY_V1"
RECEIPT_SCHEMA = "XRAY_PERSONAL_RESEARCH_OPERATIONS_ACCEPTANCE_V1"
WATCH_CLASSES = {"A", "B", "D"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,9}\Z")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def ensure(condition, reason):
    if not condition:
        raise ValueError("XRAY_MEMORY_" + reason)


def session_date(value):
    ensure(type(value) is str, "ASOF_TYPE")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("XRAY_MEMORY_ASOF_INVALID") from exc
    ensure(d.isoformat() == value, "ASOF_FORMAT")
    return d


def safe_families(obj):
    ensure(type(obj) is dict, "FAMILIES_TYPE")
    result = {}
    for symbol, families in obj.items():
        ensure(type(symbol) is str and SYMBOL.fullmatch(symbol) is not None,
               "SYMBOL_FORMAT")
        ensure(type(families) is list and families and
               families == sorted(set(families)) and
               all(type(x) is str and x in WATCH_CLASSES for x in families),
               "FAMILY_SET")
        result[symbol] = families
    return dict(sorted(result.items()))


def verify_receipt(receipt):
    ensure(type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA,
           "RECEIPT_SCHEMA")
    ensure(receipt.get("execution") == "NONE" and
           receipt.get("real_money") == "NO-GO" and
           receipt.get("orders") == [] and
           receipt.get("registered_R92_count") == 0,
           "RECEIPT_TRADING_AUTHORITY")
    for key in ("research_all_three_artifacts_same_asof_and_sha",
                "research_cohort_full_symbolic_partition_checked"):
        ensure(receipt.get(key) is True, "ACCEPTANCE_" + key)
    for key in ("operational_final_with_real_user_delivery_attested",
                "c417_primary_price_mc_release_attested",
                "source_rights_attested"):
        ensure(receipt.get(key) is False, "FALSE_PROMOTION_" + key)
    ensure(receipt.get("research_operational_state") ==
           "RESEARCH_EVIDENCE_VERIFIED_NO_RELEASE_OR_DEVICE_RECEIPT",
           "RESEARCH_STATE")
    asof = receipt.get("asof_et")
    session_date(asof)
    groups = safe_families(receipt.get("research_watch_families"))
    watch = receipt.get("research_watch_symbols")
    ensure(type(watch) is list and watch == sorted(groups) and
           len(watch) == receipt.get("research_technical_watch_count"),
           "WATCH_SYMBOL_SET")
    ensure(receipt.get("watch_membership_digest_sha256") ==
           sha({"asof_et": asof,
                "technical_setup_family_verified": groups}),
           "WATCH_MEMBERSHIP_SHA")
    for key in ("source_causal_digest_sha256",
                "research_symbol_set_sha256",
                "watch_membership_digest_sha256"):
        x = receipt.get(key)
        ensure(type(x) is str and HEX64.fullmatch(x) is not None,
               "SOURCE_HASH_" + key)
    for key in ("source_workflow_run_id", "technical_watch_workflow_run_id",
                "mirror_workflow_run_id"):
        ensure(type(receipt.get(key)) is int and receipt[key] > 0,
               "SOURCE_RUN_ID_" + key)
    n = receipt.get("rth_research_proxy_count")
    ensure(type(n) is int and n >= len(groups), "SOURCE_COHORT_COUNT")
    # No prices, raw OHLCV, issuer cap, or unverified symbol identity are stored.
    return asof, groups


def empty_ledger():
    return {"schema": SCHEMA, "execution": "NONE", "real_money": "NO-GO",
            "unknown_never_pass": True, "alpha_authority": False,
            "device_receipt_attested": False, "entries": []}


def transition_events(old, new):
    """Record observed membership differences; disappearance != proven failure."""
    events = []
    for symbol in sorted(set(old) | set(new)):
        if symbol not in old:
            kind = "WATCH_FIRST_OBSERVED"
        elif symbol not in new:
            kind = "WATCH_NOT_OBSERVED_IN_NEXT_ACCEPTED_SESSION"
        elif old[symbol] != new[symbol]:
            kind = "WATCH_FAMILY_CHANGED"
        else:
            continue
        events.append({
            "symbol": symbol, "event": kind,
            "old_families": list(old.get(symbol, [])),
            "new_families": list(new.get(symbol, [])),
            "reason_authority": "SYMBOLIC_MEMBERSHIP_DIFF_ONLY",
            "confirmed_invalidation": False, "r92": False, "al": False,
        })
    return events


def validate_ledger(ledger):
    ensure(type(ledger) is dict and
           set(ledger) == set(empty_ledger()) and
           all(ledger.get(k) == v for k, v in empty_ledger().items()
               if k != "entries") and type(ledger.get("entries")) is list,
           "LEDGER_HEADER")
    previous_hash = "0" * 64
    previous_asof = None
    previous_groups = {}
    for record in ledger["entries"]:
        ensure(type(record) is dict, "ENTRY_TYPE")
        record_without_hash = {k: v for k, v in record.items()
                               if k != "entry_sha256"}
        ensure(type(record.get("entry_sha256")) is str and
               record["entry_sha256"] == sha(record_without_hash),
               "ENTRY_SHA_DRIFT")
        asof = record.get("asof_et")
        session_date(asof)
        ensure(previous_asof is None or asof > previous_asof,
               "NONMONOTONIC_SESSIONS")
        ensure(record.get("prev_entry_sha256") == previous_hash,
               "HASH_CHAIN_BREAK")
        groups = safe_families(record.get("watch_families"))
        ensure(record.get("watch_events") ==
               transition_events(previous_groups, groups), "EVENT_REPLAY_DRIFT")
        ensure(record.get("watch_count") == len(groups) and
               record.get("execution") == "NONE" and
               record.get("real_money") == "NO-GO" and
               record.get("alpha_authority") is False and
               record.get("device_receipt_attested") is False and
               type(record.get("source_acceptance_sha256")) is str and
               HEX64.fullmatch(record["source_acceptance_sha256"]) is not None,
               "ENTRY_SAFETY_PROVENANCE")
        previous_hash, previous_asof, previous_groups = (
            record["entry_sha256"], asof, groups)
    return previous_hash


def propose(ledger, receipt):
    """Pure idempotent proposal: no writes, orders, alerts, provider calls."""
    validate_ledger(ledger)
    asof, groups = verify_receipt(receipt)
    receipt_sha = sha(receipt)
    entries = ledger["entries"]
    if entries:
        last = entries[-1]
        if asof == last["asof_et"]:
            ensure(receipt_sha == last["source_acceptance_sha256"],
                   "SAME_ASOF_REVISED_RECEIPT_REQUIRES_MANUAL_RECONCILIATION")
            return json.loads(canonical(ledger)), "IDEMPOTENT_NO_CHANGE"
        ensure(asof > last["asof_et"], "OUT_OF_ORDER_ASOF")
    old = entries[-1]["watch_families"] if entries else {}
    previous_hash = entries[-1]["entry_sha256"] if entries else "0" * 64
    record = {
        "asof_et": asof,
        "source_acceptance_sha256": receipt_sha,
        "source_run_ids": {
            "source": receipt["source_workflow_run_id"],
            "watch": receipt["technical_watch_workflow_run_id"],
            "mirror": receipt["mirror_workflow_run_id"],
        },
        "source_digests": {
            "causal": receipt["source_causal_digest_sha256"],
            "cohort": receipt["research_symbol_set_sha256"],
            "watch": receipt["watch_membership_digest_sha256"],
        },
        "watch_families": groups,
        "watch_count": len(groups),
        "watch_events": transition_events(old, groups),
        "prev_entry_sha256": previous_hash,
        "execution": "NONE", "real_money": "NO-GO",
        "alpha_authority": False, "device_receipt_attested": False,
        "scope_note": "Research technical cohort, NOT complete NASDAQ AL clearance",
        "limitations": [
            "Missing from later WATCH is not evidence of failed setup or trade",
            "Receipt digest is not an independent GitHub Actions authentication",
            "No point-in-time prices, forward returns, performance or learning",
        ],
    }
    record["entry_sha256"] = sha(record)
    proposal = json.loads(canonical(ledger))
    proposal["entries"].append(record)
    validate_ledger(proposal)
    return proposal, "NEW_ACCEPTED_SESSION"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    ensure(args.out.resolve() != args.ledger.resolve(),
           "LIVE_LEDGER_OVERWRITE_FORBIDDEN")
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    ledger = (json.loads(args.ledger.read_text(encoding="utf-8"))
              if args.ledger.exists() else empty_ledger())
    proposal, status = propose(ledger, receipt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(proposal) + b"\n")
    print(json.dumps({
        "status": status, "sessions": len(proposal["entries"]),
        "new_events": len(proposal["entries"][-1]["watch_events"])
                      if status == "NEW_ACCEPTED_SESSION" else 0,
        "alpha_authority": False, "execution": "NONE",
        "real_money": "NO-GO", "persisted_to_main": False,
        "iphone_delivery_receipt": False
    }, sort_keys=True))


if __name__ == "__main__":
    main()
