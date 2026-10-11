#!/usr/bin/env python3
"""Merge independent XRAY backup-delivery ledgers without losing receipts.

Never interprets a GitHub issue or workflow success as device push receipt.
No alpha, account, broker, execution, or price logic in this module.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "XRAY_DELIVERY_LEDGER_V1"
STATUS_RANK = {"MISSING_RETRY_REQUIRED": 1, "DELIVERED": 2}
NEUTRAL = "ENABLED_PLATFORM_NOT_OBSERVABLE"


def _checked_at(row):
    """UTC time of issue CONTENT readback. Legacy undated rows are weakest."""
    value = row.get("last_checked_at_utc")
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("ISSUE_READBACK_TIMESTAMP_INVALID")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ISSUE_READBACK_TIMESTAMP_INVALID") from exc
    if t.tzinfo is None:
        raise ValueError("ISSUE_READBACK_TIMESTAMP_UNZONED")
    return t.astimezone(timezone.utc)


def _check(ledger):
    if not isinstance(ledger, dict):
        raise ValueError("LEDGER_NOT_OBJECT")
    if ledger.get("schema") != SCHEMA:
        raise ValueError("LEDGER_SCHEMA_MISMATCH")
    if ledger.get("execution") != "NONE" or ledger.get("real_money") != "NO-GO":
        raise ValueError("LEDGER_SAFETY_MISMATCH")
    rows = ledger.get("deliveries")
    if not isinstance(rows, dict):
        raise ValueError("DELIVERIES_NOT_OBJECT")
    for key, row in rows.items():
        if not isinstance(key, str) or not key or not isinstance(row, dict):
            raise ValueError("INVALID_DELIVERY_RECORD")
        status = row.get("backup_issue_status")
        _checked_at(row)
        if status is not None and status not in STATUS_RANK:
            raise ValueError("INVALID_BACKUP_STATUS")
        n = row.get("backup_issue_number")
        if status == "DELIVERED" and (type(n) is not int or n < 1):
            raise ValueError("DELIVERED_WITHOUT_ISSUE_RECEIPT")
        if n is not None and (type(n) is not int or n < 1):
            raise ValueError("INVALID_ISSUE_NUMBER")


def merge(current, incoming):
    _check(current)
    _check(incoming)
    merged = dict(current)
    rows = {k: dict(v) for k, v in current["deliveries"].items()}
    for key, next_row in incoming["deliveries"].items():
        older = rows.get(key)
        if older is None:
            rows[key] = dict(next_row)
            continue
        if older.get("symbol") and next_row.get("symbol") and older["symbol"] != next_row["symbol"]:
            raise ValueError("DELIVERY_KEY_SYMBOL_CONFLICT")
        issues = {
            r["backup_issue_number"] for r in (older, next_row)
            if r.get("backup_issue_status") == "DELIVERED"
        }
        if len(issues) > 1:
            raise ValueError("DELIVERY_ISSUE_RECEIPT_CONFLICT")
        # An older positive receipt MUST NOT mask a newer failed exact Issue
        # readback (deleted, altered body, wrong key, or API unavailable).
        # Compare observation timestamps first, not optimistic status rank.
        # Undated legacy observations are weaker than dated observations.
        older_at, newer_at = _checked_at(older), _checked_at(next_row)
        if older_at is not None and newer_at is not None and older_at == newer_at:
            if (older.get("backup_issue_status") != next_row.get("backup_issue_status")
                or older.get("backup_issue_number") != next_row.get("backup_issue_number")):
                raise ValueError("DELIVERY_EQUAL_TIMESTAMP_RECEIPT_CONFLICT")
        if older_at is not None and newer_at is not None:
            best = older if older_at >= newer_at else next_row
        elif older_at is not None:
            best = older
        elif newer_at is not None:
            best = next_row
        else:
            # Historical ledger compatibility: both sides have no observation
            # time. Keep previously recorded positive rather than invent age.
            ranks = (STATUS_RANK.get(older.get("backup_issue_status"), 0),
                     STATUS_RANK.get(next_row.get("backup_issue_status"), 0))
            best = older if ranks[0] >= ranks[1] else next_row
        combined = {**older, **next_row}
        combined["backup_issue_status"] = best.get("backup_issue_status")
        combined["backup_issue_number"] = best.get("backup_issue_number")
        if best.get("last_checked_at_utc") is not None:
            combined["last_checked_at_utc"] = best["last_checked_at_utc"]
        else:
            combined.pop("last_checked_at_utc", None)
        for field in ("chatgpt_notification", "email_notification"):
            # Keep verified source receipts if separately attested; don't mint one.
            if older.get(field) == "USER_RECEIPT_VERIFIED":
                combined[field] = "USER_RECEIPT_VERIFIED"
            elif field not in combined:
                combined[field] = NEUTRAL
        rows[key] = combined
    merged["deliveries"] = rows
    merged["execution"] = "NONE"
    merged["real_money"] = "NO-GO"
    merged["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _check(merged)
    return merged


def selftest():
    a = {"schema": SCHEMA, "execution": "NONE", "real_money": "NO-GO",
         "deliveries": {
             "OLD|A|1": {"symbol": "OLD", "backup_issue_status": "DELIVERED",
                          "backup_issue_number": 91},
             "ALSO|B|1": {"symbol": "ALSO", "backup_issue_status": "MISSING_RETRY_REQUIRED",
                           "backup_issue_number": None}}}
    b = {"schema": SCHEMA, "execution": "NONE", "real_money": "NO-GO",
         "deliveries": {
             "OLD|A|1": {"symbol": "OLD", "backup_issue_status": "MISSING_RETRY_REQUIRED",
                          "backup_issue_number": None},
             "NEW|D|1": {"symbol": "NEW", "backup_issue_status": "DELIVERED",
                          "backup_issue_number": 92}}}
    m = merge(a, b)
    assert set(m["deliveries"]) == {"OLD|A|1", "ALSO|B|1", "NEW|D|1"}
    assert m["deliveries"]["OLD|A|1"]["backup_issue_status"] == "DELIVERED"
    assert m["deliveries"]["OLD|A|1"]["backup_issue_number"] == 91
    assert set(merge(m, b)["deliveries"]) == set(m["deliveries"])
    wrong = json.loads(json.dumps(b))
    wrong["deliveries"]["OLD|A|1"] = {
        "symbol": "OLD", "backup_issue_status": "DELIVERED", "backup_issue_number": 999}
    try:
        merge(a, wrong)
    except ValueError as e:
        assert str(e) == "DELIVERY_ISSUE_RECEIPT_CONFLICT"
    else:
        raise AssertionError("CONFLICT_MUST_FAIL_CLOSED")
    wrong = json.loads(json.dumps(b))
    wrong["deliveries"]["OLD|A|1"]["symbol"] = "OTHER"
    try:
        merge(a, wrong)
    except ValueError as e:
        assert str(e) == "DELIVERY_KEY_SYMBOL_CONFLICT"
    else:
        raise AssertionError("SYMBOL_CONFLICT_MUST_FAIL_CLOSED")
    # Same key: the most recent current exact Issue readback wins.
    # A later tamper/deletion must revoke the current backup DELIVERED claim.
    a_new = json.loads(json.dumps(a))
    a_new["deliveries"]["OLD|A|1"]["last_checked_at_utc"] = "2026-10-11T16:30:00Z"
    b_later = json.loads(json.dumps(b))
    b_later["deliveries"]["OLD|A|1"]["last_checked_at_utc"] = "2026-10-11T16:40:00+00:00"
    last = merge(a_new, b_later)["deliveries"]["OLD|A|1"]
    assert last["backup_issue_status"] == "MISSING_RETRY_REQUIRED"
    assert last["backup_issue_number"] is None
    assert last["last_checked_at_utc"] == "2026-10-11T16:40:00+00:00"
    rev = merge(b_later, a_new)["deliveries"]["OLD|A|1"]
    assert rev["backup_issue_status"] == "MISSING_RETRY_REQUIRED"
    assert rev["backup_issue_number"] is None
    # Stale failed results cannot erase a later actually verified issue.
    b_earlier = json.loads(json.dumps(b))
    b_earlier["deliveries"]["OLD|A|1"]["last_checked_at_utc"] = "2026-10-11T16:20:00Z"
    assert merge(a_new, b_earlier)["deliveries"]["OLD|A|1"]["backup_issue_number"] == 91
    # Equal-time contradictory observations or naive/malformed clocks FAIL.
    b_same = json.loads(json.dumps(b_later))
    b_same["deliveries"]["OLD|A|1"]["last_checked_at_utc"] = "2026-10-11T16:30:00+00:00"
    try:
        merge(a_new, b_same)
    except ValueError as exc:
        assert str(exc) == "DELIVERY_EQUAL_TIMESTAMP_RECEIPT_CONFLICT"
    else:
        raise AssertionError("EQUAL_TIMESTAMP_STATUS_CONFLICT_ACCEPTED")
    for bad in ("2026-10-11T16:50:00", "NOT_A_DATE", 123):
        x = json.loads(json.dumps(b_later))
        x["deliveries"]["OLD|A|1"]["last_checked_at_utc"] = bad
        try:
            merge(a_new, x)
        except ValueError:
            pass
        else:
            raise AssertionError("INVALID_RECEIPT_CLOCK_ACCEPTED")
    # Prior separately attested platform receipts are never minted or erased.
    a_verified=json.loads(json.dumps(a_new))
    a_verified["deliveries"]["OLD|A|1"]["chatgpt_notification"]="USER_RECEIPT_VERIFIED"
    kept=merge(a_verified,b_later)["deliveries"]["OLD|A|1"]
    assert kept["chatgpt_notification"]=="USER_RECEIPT_VERIFIED"
    assert kept["backup_issue_status"]=="MISSING_RETRY_REQUIRED"
    print("XRAY_LEDGER_MERGE_RACE_AND_CONFLICT_SELFTEST=PASS_CHRONOLOGICAL_RECHECK_REVOKES_STALE_DELIVERED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--current")
    parser.add_argument("--incoming")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not all((args.current, args.incoming, args.out)):
        parser.error("--current, --incoming, --out required")
    current = json.loads(Path(args.current).read_text())
    incoming = json.loads(Path(args.incoming).read_text())
    merged = merge(current, incoming)
    output = Path(args.out)
    tmp = output.with_name(output.name + ".merge-tmp")
    tmp.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, output)
    print("XRAY_LEDGER_MERGE_RECORDS=" + str(len(merged["deliveries"])))


if __name__ == "__main__":
    main()
