#!/usr/bin/env python3
"""NASDAQ-only candidate intake; NEVER runs upstream code or approves trading.

Stdlib-only, bound URL metadata checks. Emits versioned, deterministic receipts.
Artifact-only workflow: no git commits, Sheets, Alpaca, broker or ChatGPT tasks.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

SCHEMA = "XRAY_NASDAQ_CANDIDATE_PRIORITIZATION_V1"
SCOPE = "NASDAQ_RESEARCH_ONLY_NO_CRYPTO"
ORDER = ("P1-ENGINEERING-TEST", "P0-EXISTING-CORE-VERIFY", "P1-VALIDATE",
         "P2-RESEARCH-SHADOW", "P2-BACKLOG")
EXCLUDED = frozenset(("HOLD", "HOLD/SEPARATE"))
START = dt.date(2026, 11, 2)
BATCH = 7


class GateError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise GateError(code)


def registry_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_registry(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    require(isinstance(data, dict) and data.get("schema") == SCHEMA, "REGISTRY_SCHEMA")
    require(data.get("scope") == SCOPE, "CRYPTO_SCOPE_BREACH")
    records = data.get("entries")
    require(isinstance(records, list) and len(records) == 284 and data.get("unique_records") == 284,
            "INVENTORY_284_COUNT")
    seen = set()
    counts = {}
    for r in records:
        require(isinstance(r, dict) and type(r.get("registry_id")) is int,
                "REGISTRY_ID_MISSING")
        i = r["registry_id"]
        require(1 <= i <= 284 and i not in seen, "DUPLICATE_OR_INVALID_ID")
        seen.add(i)
        require(isinstance(r.get("name"), str) and bool(r["name"].strip()), "NAME_MISSING")
        tier = r.get("recomputed_tier")
        require(tier in (*ORDER, *EXCLUDED), "UNKNOWN_PRIORITY")
        counts[tier] = counts.get(tier, 0) + 1
        url = r.get("url")
        require(url is None or (isinstance(url, str) and
                (url == "" or url.startswith("https://"))), "UNSAFE_URL_SCHEME")
    require(seen == set(range(1, 285)), "MISSING_REGISTRY_ID")
    require(counts == data.get("tier_counts"), "TIER_COUNT_DRIFT")
    return records


def candidate_url(url: str) -> str | None:
    """Only allow public github.com content; no redirects (no SSRF)."""
    if not isinstance(url, str):
        return None
    try:
        p = urlparse(url)
        if (p.scheme != "https" or p.hostname != "github.com" or
                p.username is not None or p.password is not None or
                p.port not in (None, 443) or p.query or p.fragment):
            return None
        if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^?#]*)?", p.path):
            return None
        return url
    except ValueError:
        return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def probe_url(url: str, timeout: float = 5.0) -> str:
    """One anonymous bounded HEAD request, never follows a redirect or executes code."""
    checked = candidate_url(url)
    if checked is None:
        return "SKIPPED_EXTERNAL_OR_UNSAFE_HOST"
    opener = build_opener(NoRedirect, HTTPSHandler(context=ssl.create_default_context()))
    req = Request(checked, method="HEAD", headers={"User-Agent": "XRAY-NASDAQ-intake/1.0"})
    try:
        with opener.open(req, timeout=timeout) as response:
            return "HTTP_2XX" if 200 <= response.status < 300 else "HTTP_OTHER"
    except HTTPError as ex:
        return "HTTP_REDIRECT_NOT_FOLLOWED" if 300 <= ex.code < 400 else "HTTP_ERROR"
    except (URLError, TimeoutError, OSError, ValueError):
        return "NETWORK_UNKNOWN"


def plan(records: list[dict], on: dt.date, batch: int = BATCH) -> dict:
    require(type(on) is dt.date, "DATE_REQUIRED")
    require(type(batch) is int and 1 <= batch <= 7, "UNSAFE_BATCH_SIZE")
    require(on >= START, "DATE_BEFORE_REGISTRY")
    ranked = sorted((r for r in records if r["recomputed_tier"] in ORDER),
                    key=lambda r: (ORDER.index(r["recomputed_tier"]), r["registry_id"]))
    require(on.weekday() < 5, "NON_BUSINESS_DAY_COHORT")
    days = (on - START).days
    weekday_index = 5 * (days // 7) + sum(
        (START + dt.timedelta(days=i)).weekday() < 5 for i in range(days % 7))
    pages = (len(ranked) + batch - 1) // batch
    page = weekday_index % pages
    selected = ranked[page * batch:(page + 1) * batch]
    return {"date": on.isoformat(), "cohort_page": page + 1, "cohort_pages": pages,
            "eligible_count": len(ranked), "blocked_count": len(records) - len(ranked),
            "selected": [{"registry_id": r["registry_id"], "name": r["name"],
                          "tier": r["recomputed_tier"], "url": r.get("url") or ""}
                         for r in selected]}


def evidence(raw: bytes, on: dt.date, network: bool = False,
             queue: dict | None = None) -> dict:
    records = parse_registry(raw)
    p = plan(records, on)
    if queue is not None:
        require(type(queue) is dict and queue.get("schema") ==
             "XRAY_NASDAQ_A46_LEDGER_QUEUE_V1" and
             queue.get("asof_et") == on.isoformat() and
             queue.get("registry_sha256") == registry_hash(raw) and
             queue.get("automatic_promotion") is False and
             queue.get("execution") == "NONE", "QUEUE_RECEIPT_OR_SCOPE_MISMATCH")
        selected_ids = queue.get("selected_ids")
        require(type(selected_ids) is list and 1 <= len(selected_ids) <= BATCH and
             all(type(i) is int and 1 <= i <= 284 for i in selected_ids) and
             len(set(selected_ids)) == len(selected_ids), "QUEUE_ID_COUNT_INVALID")
        eligible = {r["registry_id"]: r for r in records
                    if r["recomputed_tier"] in ORDER}
        require(all(i in eligible for i in selected_ids), "QUEUE_HOLD_OR_UNKNOWN_ID")
        p["selected"] = [{"registry_id": i, "name": eligible[i]["name"],
                          "tier": eligible[i]["recomputed_tier"],
                          "url": eligible[i].get("url") or ""}
                         for i in selected_ids]
        p["cohort_page"] = "LEDGER_DRIVEN"
        p["selection_mode"] = queue.get("mode")
        p["remaining_unseen_before"] = queue.get("remaining_unseen_before")
    findings = []
    for candidate in p["selected"]:
        url = candidate["url"]
        status = probe_url(url) if network else (
            "NOT_PROBED_OFFLINE" if candidate_url(url) else "NEEDS_MANUAL_PROVENANCE")
        findings.append({"registry_id": candidate["registry_id"], "name": candidate["name"],
                         "tier": candidate["tier"], "url": url, "url_evidence": status,
                         "integration_status": "NOT_INTEGRATED",
                         "next_gate": "LICENSE_PROVENANCE_FUNCTIONAL_TEST_AND_INDEPENDENT_PR"})
    return {"schema": "XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1",
            "asof": on.isoformat(), "registry_sha256": registry_hash(raw),
            "source": SCOPE, "execution": "NONE", "orders": False,
            "private_sheet_writes": False, "automatic_promotion": False,
            "network_used": network, "selection": {k: v for k, v in p.items() if k != "selected"},
            "findings": findings}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="nasdaq-candidate-autopilot/registry.json")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--output", required=True)
    ap.add_argument("--network", action="store_true", help="bounded public GitHub HEAD only")
    ap.add_argument("--queue-receipt", help="A46 SHA-bound, read-only ledger-driven IDs")
    args = ap.parse_args()
    queue = json.loads(Path(args.queue_receipt).read_text(encoding="utf-8")) if args.queue_receipt else None
    result = evidence(Path(args.registry).read_bytes(), dt.date.fromisoformat(args.date), args.network, queue)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("XRAY_CANDIDATE_RECEIPT=PASS;COUNT=%d;COHORT=%d/%d;AUTOPROMOTE=FALSE" %
          (len(result["findings"]), result["selection"]["cohort_page"],
           result["selection"]["cohort_pages"]))


if __name__ == "__main__":
    main()
