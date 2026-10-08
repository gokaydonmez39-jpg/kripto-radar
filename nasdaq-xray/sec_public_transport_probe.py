#!/usr/bin/env python3
"""Read-only, bounded SEC endpoint access feasibility probe (non-authoritative).

Does not bulk-download filings, classify issuers, create MC/AL/R92, or
republish SEC data. SEC 403/429 stays UNKNOWN. Only one request per endpoint.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request

URLS = {
    "SEC_SUBMISSIONS_ONE": ("GET", "https://data.sec.gov/submissions/CIK0002096900.json"),
    "SEC_BULK_SUBMISSIONS": ("HEAD", "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"),
    "SEC_EXCHANGE_TICKERS": ("HEAD", "https://www.sec.gov/files/company_tickers_exchange.json"),
}
UA = "NASDAQ-SWING-XRAY/1.0 research contact xray-dataplane-bot@users.noreply.github.com"
MAX_BODY = 250_000
BULK_SIZE_BUDGET_BYTES = 150_000_000


def classify_http(method, status, content_length, read_length, truncated):
    if method not in ("HEAD", "GET"):
        return "INVALID_METHOD"
    if status in (403, 429):
        return "BLOCKED_ACCESS_OR_RATE_LIMIT"
    if status != 200:
        return "UNKNOWN_HTTP_" + str(status)
    if method == "HEAD":
        if content_length is None:
            return "REACHABLE_SIZE_UNKNOWN_NON_ALPHA"
        if content_length > BULK_SIZE_BUDGET_BYTES:
            return "REACHABLE_BUT_OVERSIZE_ZERO_COST_CI_BUDGET"
        return "REACHABLE_WITHIN_BYTES_BUDGET_NON_ALPHA"
    if truncated:
        return "REACHABLE_BOUNDED_SAMPLE_NON_ALPHA"
    return "REACHABLE_BOUNDED_RESPONSE_NON_ALPHA"


def probe(name, method, url):
    req = urllib.request.Request(
        url, method=method,
        headers={"User-Agent": UA, "Accept": "application/json,application/zip,*/*", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status = int(response.status)
            length = response.headers.get("Content-Length")
            content_length = int(length) if length and length.isdecimal() else None
            body = response.read(MAX_BODY + 1) if method == "GET" else b""
            truncated = len(body) > MAX_BODY
            return {
                "method": method, "url": url,
                "http_status": status, "reported_content_length_bytes": content_length,
                "sample_bytes": min(len(body), MAX_BODY),
                "status": classify_http(method, status, content_length, len(body), truncated),
                "body_persisted": False,
            }
    except urllib.error.HTTPError as e:
        return {
            "method": method, "url": url, "http_status": int(e.code),
            "reported_content_length_bytes": None, "sample_bytes": 0,
            "status": classify_http(method, int(e.code), None, 0, False),
            "body_persisted": False,
        }
    except (OSError, TimeoutError) as e:
        return {
            "method": method, "url": url, "http_status": None,
            "reported_content_length_bytes": None, "sample_bytes": 0,
            "status": "UNKNOWN_TRANSPORT_" + type(e).__name__,
            "body_persisted": False,
        }


def selftest():
    assert classify_http("HEAD", 200, 900_000_000, 0, False) == "REACHABLE_BUT_OVERSIZE_ZERO_COST_CI_BUDGET"
    assert classify_http("HEAD", 200, None, 0, False) == "REACHABLE_SIZE_UNKNOWN_NON_ALPHA"
    assert classify_http("HEAD", 200, 1000, 0, False) == "REACHABLE_WITHIN_BYTES_BUDGET_NON_ALPHA"
    assert classify_http("GET", 200, None, MAX_BODY + 1, True) == "REACHABLE_BOUNDED_SAMPLE_NON_ALPHA"
    for code in (403, 429):
        assert classify_http("GET", code, None, 0, False) == "BLOCKED_ACCESS_OR_RATE_LIMIT"
    assert classify_http("GET", 500, None, 0, False) == "UNKNOWN_HTTP_500"
    assert classify_http("POST", 200, 0, 0, False) == "INVALID_METHOD"
    print("XRAY_SEC_PUBLIC_TRANSPORT_PROBE_SELFTEST=PASS (NO_DATA_NO_ALPHA)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="/tmp/xray_sec_access_probe.json")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    probes = {name: probe(name, method, url) for name, (method, url) in URLS.items()}
    doc = {
        "schema": "XRAY_SEC_OFFICIAL_TRANSPORT_FEASIBILITY_V1",
        "asof_et": "2026-10-07",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "authority": "READ_ONLY_TRANSPORT_DIAGNOSTIC_NOT_A_SEC_CLASSIFICATION",
        "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
        "alpha_authority": False, "r92_created": False, "mc_primary_pass_created": False,
        "master_exclusion_created": False, "bulk_download_performed": False,
        "max_body_bytes": MAX_BODY, "bulk_size_budget_bytes": BULK_SIZE_BUDGET_BYTES,
        "results": probes,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({name: p["status"] for name, p in probes.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
