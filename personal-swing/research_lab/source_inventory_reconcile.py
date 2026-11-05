#!/usr/bin/env python3
"""Read-only registry/archive reconciliation. Private CSV is optional.

No network, credentials, market prices, Sheets writes, notifications or orders.
Never run external code or commit the private archive to GitHub.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

FIELDS = (
    "production_enabled", "may_issue_al", "may_write_sheet",
    "may_emit_alert", "may_place_order", "may_fetch_unapproved_api",
)
ARCHIVE_FIELDS = {"ID", "Kaynak_depo", "Kabul_durumu", "Oncelik", "Paylasim_id_utc"}
PRIORITIES = {"P0", "P1", "P2", "HOLD"}


class ReconciliationBlocked(ValueError):
    """Untrusted research inventory violates an acceptance contract."""


def canonical_url(value: str) -> str:
    if not isinstance(value, str):
        raise ReconciliationBlocked("URL_NOT_TEXT")
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"https", "http"} or not parsed.hostname:
        raise ReconciliationBlocked("INVALID_SOURCE_URL")
    if parsed.username or parsed.password:
        raise ReconciliationBlocked("CREDENTIALS_IN_URL")
    host = parsed.hostname.lower()
    path = parsed.path.rstrip("/")
    if host == "github.com":
        path = re.sub(r"\.git$", "", path, flags=re.IGNORECASE).lower()
    return urlunsplit(("https", host, path, "", ""))


def audit_registry(document: dict) -> dict:
    if not isinstance(document, dict) or document.get("schema") != "XRAY_RESEARCH_UNIFIED_88_V1":
        raise ReconciliationBlocked("INVALID_REGISTRY_SCHEMA")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 88:
        raise ReconciliationBlocked("EXPECTED_88_REGISTRY_ENTRIES")
    keys = set()
    urls = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            raise ReconciliationBlocked("INVALID_REGISTRY_ENTRY")
        if entry["key"] in keys:
            raise ReconciliationBlocked("DUPLICATE_REGISTRY_KEY")
        keys.add(entry["key"])
        if any(entry.get(field) is not False for field in FIELDS):
            raise ReconciliationBlocked("UNAUTHORIZED_RESEARCH_PRODUCTION_PERMISSION")
        url = canonical_url(entry.get("url", ""))
        if not url:
            raise ReconciliationBlocked("REGISTRY_URL_MISSING")
        urls.setdefault(url, set()).add(entry["key"])
    return {"registered": len(entries), "production_authorized": 0, "urls": urls}


def audit_archive(rows: list[dict]) -> dict:
    if not isinstance(rows, list) or not rows:
        raise ReconciliationBlocked("ARCHIVE_EMPTY")
    ids = []
    priorities = Counter()
    missing_urls = 0
    post_id_present = 0
    urls = []
    for row in rows:
        if not isinstance(row, dict) or not ARCHIVE_FIELDS.issubset(row):
            raise ReconciliationBlocked("ARCHIVE_SCHEMA_INVALID")
        value = row["ID"].strip()
        if not re.fullmatch(r"RT-\d{3,}", value):
            raise ReconciliationBlocked("INVALID_RT_ID")
        ids.append(value)
        priority = row["Oncelik"].strip()
        if priority not in PRIORITIES:
            raise ReconciliationBlocked("UNKNOWN_ARCHIVE_PRIORITY")
        priorities[priority] += 1
        if not row["Kabul_durumu"].strip():
            raise ReconciliationBlocked("MISSING_ARCHIVE_STATUS")
        url = canonical_url(row["Kaynak_depo"])
        if not url:
            missing_urls += 1
        urls.append(url)
        if row["Paylasim_id_utc"].strip():
            post_id_present += 1
    if len(set(ids)) != len(ids):
        raise ReconciliationBlocked("DUPLICATE_RT_ID")
    nums = sorted(int(value[3:]) for value in ids)
    if nums != list(range(1, max(nums) + 1)):
        raise ReconciliationBlocked("RT_ID_GAP_OR_NONCANONICAL_START")
    return {
        "archive_records": len(rows), "priorities": dict(sorted(priorities.items())),
        "missing_urls": missing_urls,
        "post_ids_present_not_directly_verified": post_id_present, "urls": urls,
    }


def reconcile(document: dict, archive_rows: list[dict] | None) -> dict:
    registry = audit_registry(document)
    report = {
        "contract": "XRAY_SOURCE_INVENTORY_RECONCILE_V1",
        "registry_status": "SCHEMA_PASS_RESEARCH_ONLY",
        "github_registry_entries": registry["registered"],
        "production_sources_authorized": registry["production_authorized"],
        "archive_status": "NOT_SUPPLIED_UNKNOWN",
        "exact_url_matches": None,
        "catalogue_union_total": None,
        "live_pit_verified": False,
        "oos_alpha_verified": False,
        "may_promote_sources": False,
    }
    if archive_rows is None:
        return report
    archive = audit_archive(archive_rows)
    exact = 0
    matched_registry = set()
    for url in archive["urls"]:
        keys = registry["urls"].get(url, set())
        if len(keys) == 1:
            exact += 1
            matched_registry.update(keys)
    report.update({
        "archive_status": "SCHEMA_PASS_RESEARCH_ONLY",
        "archive_records": archive["archive_records"],
        "archive_priorities": archive["priorities"],
        "archive_missing_urls": archive["missing_urls"],
        "archive_post_ids_present_not_verified": archive["post_ids_present_not_directly_verified"],
        "exact_url_matches": exact,
        "distinct_registry_keys_exactly_matched": len(matched_registry),
        "unmatched_archive_rows_not_claimed_unique": archive["archive_records"] - exact,
    })
    return report


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not ARCHIVE_FIELDS.issubset(reader.fieldnames):
            raise ReconciliationBlocked("ARCHIVE_HEADERS_MISSING")
        return list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only 88/RT inventory QA")
    parser.add_argument("--registry", type=Path, default=Path(__file__).with_name("unified_research_88.json"))
    parser.add_argument("--archive", type=Path, help="Optional local/private RoundtableSpace CSV path")
    parser.add_argument("--require-archive", action="store_true")
    args = parser.parse_args()
    try:
        if args.require_archive and args.archive is None:
            raise ReconciliationBlocked("ARCHIVE_REQUIRED_BUT_NOT_SUPPLIED")
        document = json.loads(args.registry.read_text(encoding="utf-8"))
        archive = load_csv(args.archive) if args.archive else None
        report = reconcile(document, archive)
        if args.archive:
            report["private_archive_sha256"] = hashlib.sha256(args.archive.read_bytes()).hexdigest()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (ReconciliationBlocked, OSError, ValueError) as exc:
        print(json.dumps({
            "contract": "XRAY_SOURCE_INVENTORY_RECONCILE_V1",
            "status": "HOLD_RESEARCH_SOURCE_INPUT_INVALID", "reason": str(exc),
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
