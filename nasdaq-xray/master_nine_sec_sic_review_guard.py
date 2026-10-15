#!/usr/bin/env python3
"""Immutable 14-Oct SEC SIC research review; never overrides canonical UNKNOWN.

Public EDGAR filing-index metadata is reviewed separately from the runner's
own live SEC transport, which may be blocked. This validates provenance
shape, official domain/CIK, vintage and authoritative UNKNOWN partition.
It DOES NOT attest a live SEC request, symbol/CIK current mapping, SPAC
completion, licensed prices, R92, notifications or production readiness.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
REVIEW = ROOT / "research/master_20261014_nine_sec_sic_review_v1.json"
MASTER = ROOT / "canonical_current_master_manifest.json"
ASOF = "2026-10-14"
EXPECTED = {"ALIS", "BSAA", "FACT", "FVN", "HCAC", "IPXG",
            "MACI", "MCGA", "WTG"}
SAFE = {"execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True}


def require(test: bool, code: str) -> None:
    if not test:
        raise ValueError("XRAY_NINE_SEC_REVIEW_" + code)


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\\0" + raw
    ).hexdigest()


def check(doc: dict, master: dict, master_blob: str) -> dict:
    require(type(doc) is dict and type(master) is dict, "DOCUMENT_TYPE")
    require(doc.get("schema") == "XRAY_MASTER_NINE_SEC_SIC_REVIEW_V1",
            "REVIEW_SCHEMA")
    require(doc.get("asof_et") == master.get("asof_et") == ASOF, "ASOF")
    require(doc.get("master_blob_sha") == master_blob, "MASTER_BLOB")
    require(all(doc.get(k) == v and master.get(k) == v
                for k, v in SAFE.items()), "INVARIANTS")
    require(doc.get("authority") ==
            "PUBLIC_SEC_INDEX_METADATA_REVIEW_NOT_RUNNER_FETCHED_NO_IDENTITY_PROMOTION",
            "RESEARCH_AUTHORITY")
    require(all(doc.get(k) is False for k in (
        "source_vendor_raw_data", "canonical_mutation_authorized",
        "classification_override_authorized", "alpha_authority",
        "can_register_r92", "device_delivery_verified")), "UNSAFE_PROMOTION")
    require(set(master.get("unknown_symbols") or []) == EXPECTED
            and master.get("unknown_count") == len(EXPECTED)
            and master.get("status") == "PARTIAL_UNKNOWN", "EXACT_UNKNOWN_SCOPE")
    details = master.get("unknown_detail") or {}
    require(type(details) is dict and set(details) == EXPECTED
            and all(details[t].get("unknown_never_pass") is True
                    for t in EXPECTED), "UNKNOWN_DETAIL")
    rows = doc.get("records")
    require(type(rows) is dict and set(rows) == EXPECTED, "REVIEW_SCOPE")

    nonblank = []
    blank = []
    without = []
    for symbol, r in sorted(rows.items()):
        require(type(r) is dict, "ROW_TYPE")
        fields = (r.get("cik"), r.get("sic"),
                  r.get("filing_date"), r.get("source_url"))
        if all(x is None for x in fields):
            without.append(symbol)
            continue
        require(all(x is not None for x in fields), "PARTIAL_EVIDENCE")
        cik, sic, day, source = fields
        require(type(cik) is str and re.fullmatch(r"\\d{10}", cik) is not None,
                "CIK")
        require(type(sic) is int and 100 <= sic <= 9999, "SIC")
        require(type(day) is str and re.fullmatch(r"20\\d{2}-\\d{2}-\\d{2}", day)
                is not None, "DATE_FORMAT")
        try:
            dated = dt.date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("XRAY_NINE_SEC_REVIEW_INVALID_DATE") from exc
        require(dated <= dt.date.fromisoformat(ASOF), "FUTURE_LEAK")
        require(type(source) is str, "URL_TYPE")
        u = urlsplit(source)
        require(u.scheme == "https" and u.netloc == "www.sec.gov"
                and not u.username and not u.password and not u.query
                and not u.fragment, "OFFICIAL_DOMAIN")
        m = re.fullmatch(
            r"/Archives/edgar/data/(\\d+)/(\\d{18})/([A-Za-z0-9.-]+)-index\\.html?",
            u.path)
        require(m is not None and int(m.group(1)) == int(cik),
                "SEC_CIK_DOCUMENT_BINDING")
        # An Acquisition-name issuer with non-6770 SIC still requires a
        # separate *completed business combination* proof to become operating.
        # SIC 6770 also does not independently override this frozen snapshot.
        if sic == 6770:
            blank.append(symbol)
        else:
            nonblank.append(symbol)
    require(len(nonblank) == 6 and len(blank) == 1 and len(without) == 2,
            "RESEARCH_COVERAGE_REQUIRES_REVIEW")
    return {
        "schema": "XRAY_NINE_SEC_REVIEW_DIAGNOSTIC_V1",
        "asof_et": ASOF,
        "official_index_metadata_rows": len(nonblank) + len(blank),
        "sec_sic_non6770_acquisition_name_count": len(nonblank),
        "sec_sic_6770_no_current_override_count": len(blank),
        "source_not_attested_count": len(without),
        "canonical_identity_unknown_preserved": len(EXPECTED),
        "all_nine_still_unknown": True,
        "live_sec_network_proven": False,
        "completed_merger_proven": False,
        "classification_override_authorized": False,
        "alpha_authority": False,
        "can_register_r92": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
    }


def selftest() -> None:
    data = json.loads(REVIEW.read_text())
    raw = MASTER.read_bytes()
    master = json.loads(raw)
    want = blob_sha(raw)
    require(check(data, master, want)["all_nine_still_unknown"] is True,
            "GOOD_FIXTURE_REJECTED")
    testcases = []
    def mutate(fn):
        j = copy.deepcopy(data)
        m = copy.deepcopy(master)
        fn(j, m)
        testcases.append((j, m))
    mutate(lambda j, m: j.update(asof_et="2026-10-15"))
    mutate(lambda j, m: j.update(master_blob_sha="0"*40))
    mutate(lambda j, m: j.update(classification_override_authorized=True))
    mutate(lambda j, m: j.update(alpha_authority=True))
    mutate(lambda j, m: j["records"]["BSAA"].update(sic=6770))
    mutate(lambda j, m: j["records"]["BSAA"].update(
        source_url="https://evil.example/Archives/edgar/data/2051587/doc"))
    mutate(lambda j, m: j["records"]["BSAA"].update(
        source_url=j["records"]["BSAA"]["source_url"].replace("2051587", "2051588")))
    mutate(lambda j, m: j["records"]["BSAA"].update(filing_date="2026-10-16"))
    mutate(lambda j, m: j["records"]["FACT"].update(cik="0002028935"))
    mutate(lambda j, m: m.update(unknown_symbols=["ALIS"]))
    mutate(lambda j, m: m["unknown_detail"]["FVN"].update(unknown_never_pass=False))
    mutate(lambda j, m: j["records"].pop("WTG"))
    for n, (j, m) in enumerate(testcases):
        try:
            check(j, m, want)
        except ValueError:
            continue
        raise AssertionError("SIC_EVIDENCE_GUARD_BYPASS_" + str(n))
    print("XRAY_NINE_SEC_SIC_SELFTEST=PASS_1_REAL_FIXTURE_12_NEGATIVE_NO_ALPHA")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    if args.selftest == args.live:
        p.error("Select exactly one of --selftest and --live")
    if args.selftest:
        selftest()
        return
    raw = MASTER.read_bytes()
    doc = json.loads(REVIEW.read_text())
    result = check(doc, json.loads(raw), blob_sha(raw))
    print("XRAY_NINE_SEC_REVIEW=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
