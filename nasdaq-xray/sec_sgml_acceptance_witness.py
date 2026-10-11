#!/usr/bin/env python3
"""Research-only official SEC SGML acceptance clock witness.

Never infers MC, vendor rights, stock class, price, history, PRIMARY, R92,
or an executable trade. An API acceptanceDateTime Z suffix is not reliable
enough for exact market-close PIT, so the SEC SGML header is the clock root.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sec_official_free_mc_transport_probe import (
    official_nasdaq_close_utc, valid_operator_contact
)

APPLE_ACC = "0000320193-26-000018"
APPLE_CIK = "0000320193"
APPLE_ASOF = "2026-07-30"
SCHEMA = "XRAY_SEC_SGML_ACCEPTANCE_CLOCK_WITNESS_V1"
ACC = re.compile(r"^\d{10}-\d{2}-\d{6}$")
CIK = re.compile(r"^\d{10}$")
LIM = 131072


def sec_official_url(accession: str, cik: str) -> str:
    if not isinstance(accession, str) or not ACC.fullmatch(accession):
        raise ValueError("SEC_ACCESSION_INVALID")
    if not isinstance(cik, str) or not CIK.fullmatch(cik):
        raise ValueError("SEC_CIK_INVALID")
    return ("https://www.sec.gov/Archives/edgar/data/"
            + str(int(cik)) + "/" + accession.replace("-", "")
            + "/" + accession + ".txt")


def strict_edgar_eastern_utc(raw_clock: str) -> dt.datetime:
    """Reject wall-clock ambiguities and DST gaps in official SGML timestamps.

    Python ZoneInfo.replace(tzinfo=...) silently chooses fold=0 even when the
    local clock has two possible UTC meanings or none. A PIT proof cannot
    choose an unobserved fold. This guard does not repair vendor MC authority.
    """
    if not isinstance(raw_clock, str) or not re.fullmatch(r"\d{14}", raw_clock):
        raise ValueError("SEC_SGML_CLOCK_FORMAT_INVALID")
    try:
        naive = dt.datetime.strptime(raw_clock, "%Y%m%d%H%M%S")
        eastern = ZoneInfo("America/New_York")
        possibilities = set()
        for fold in (0, 1):
            candidate = naive.replace(tzinfo=eastern, fold=fold)
            utc = candidate.astimezone(dt.timezone.utc)
            restored = utc.astimezone(eastern).replace(tzinfo=None)
            if restored == naive:
                possibilities.add(utc)
        if len(possibilities) != 1:
            raise ValueError("SEC_SGML_DST_CLOCK_AMBIGUOUS_OR_NONEXISTENT")
        return next(iter(possibilities))
    except (OverflowError, TypeError) as exc:
        raise ValueError("SEC_SGML_CLOCK_FORMAT_INVALID") from exc


def parse_official_header(data: bytes, accession: str, cik: str, asof: str) -> dict:
    url = sec_official_url(accession, cik)
    if not isinstance(data, bytes) or not 0 < len(data) <= LIM:
        raise ValueError("SEC_SGML_HEADER_SIZE_INVALID")
    prefix = data.split(b"</SEC-HEADER>", 1)
    if len(prefix) != 2 or b"<SEC-HEADER>" not in prefix[0]:
        raise ValueError("SEC_SGML_HEADER_INCOMPLETE")
    # The first two bytes of actual SEC full-submission text identify its
    # accession and header. Later document bodies cannot substitute for them.
    text = prefix[0].decode("ascii", errors="strict")
    fileacc = re.search(r"(?m)^<SEC-DOCUMENT>(\d{10}-\d{2}-\d{6})\.txt\s*:", text)
    headeracc = re.findall(r"(?m)^\s*ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})\s*$", text)
    ciks = re.findall(r"(?m)^\s*CENTRAL INDEX KEY:\s*(\d{1,10})\s*$", text)
    clocks = re.findall(r"(?m)^<ACCEPTANCE-DATETIME>(\d{14})\s*$", text)
    if (not fileacc or fileacc.group(1) != accession
            or len(headeracc) != 1 or headeracc[0] != accession):
        raise ValueError("SEC_SGML_ACCESSION_PROVENANCE_MISMATCH")
    # Multi-filer headers need independent class/CIK disambiguation.
    if len(ciks) != 1 or ciks[0].zfill(10) != cik:
        raise ValueError("SEC_SGML_CIK_AMBIGUOUS_OR_MISMATCH")
    if len(clocks) != 1:
        raise ValueError("SEC_SGML_ACCEPTANCE_CLOCK_NOT_UNIQUE")
    try:
        utc = strict_edgar_eastern_utc(clocks[0])
        cutoff = official_nasdaq_close_utc(asof)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueError("SEC_SGML_CLOCK_OR_EXCHANGE_CUTOFF_INVALID") from e
    return {
        "schema": SCHEMA,
        "status": ("SGML_ACCEPTED_PRE_RTH_CLOSE_SHADOW_ONLY"
                   if utc <= cutoff else "SGML_ACCEPTED_AFTER_RTH_CLOSE_UNKNOWN"),
        "asof_et": asof, "accession": accession, "issuer_cik": cik,
        "source_url": url,
        "sec_header_sha256": hashlib.sha256(prefix[0] + b"</SEC-HEADER>").hexdigest(),
        "source_clock": "SEC_SGML_HEADER_NEW_YORK",
        "accepted_at_utc": utc.isoformat(),
        "exchange_close_utc": cutoff.isoformat(),
        "source_transport_attested_by_pure_parser": False,
        "issuer_share_class_verified": False,
        "corporate_actions_verified": False,
        "production_mc_primary_pass": False,
        "can_register_R92": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
        "vendor_bars_or_share_numbers_exported": False
    }


def get_official_canary() -> dict:
    url = sec_official_url(APPLE_ACC, APPLE_CIK)
    ua = os.environ.get("XRAY_SEC_USER_AGENT", "")
    if not valid_operator_contact(ua):
        return {"schema": SCHEMA, "status": "BLOCKED_OPERATOR_CONTACT",
                "source_transport_attested": False, "execution": "NONE",
                "real_money": "NO-GO", "can_register_R92": False}
    req = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept": "text/plain",
        "Accept-Encoding": "identity", "Range": "bytes=0-131071"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status not in (200, 206) or response.geturl() != url:
                raise ValueError("SEC_SGML_OFFICIAL_ORIGIN_OR_HTTP_INVALID")
            buf = response.read(LIM)
    except urllib.error.HTTPError as e:
        return {"schema": SCHEMA, "status": "BLOCKED_SEC_HTTP_" + str(e.code),
                "source_transport_attested": False, "execution": "NONE",
                "real_money": "NO-GO", "can_register_R92": False}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return {"schema": SCHEMA, "status": "BLOCKED_SEC_SGML_TRANSPORT",
                "source_transport_attested": False, "execution": "NONE",
                "real_money": "NO-GO", "can_register_R92": False}
    try:
        result = parse_official_header(buf, APPLE_ACC, APPLE_CIK, APPLE_ASOF)
    except (UnicodeError, ValueError):
        return {"schema": SCHEMA, "status": "UNKNOWN_SEC_SGML_PROVENANCE_INVALID",
                "source_transport_attested": False, "execution": "NONE",
                "real_money": "NO-GO", "can_register_R92": False}
    result["source_transport_attested"] = True
    return result


def sample_header(clock: str = "20260730163028") -> bytes:
    return (
        "<SEC-DOCUMENT>0000320193-26-000018.txt : 20260730\n"
        "<SEC-HEADER>0000320193-26-000018.hdr.sgml : 20260730\n"
        "<ACCEPTANCE-DATETIME>" + clock + "\n"
        "ACCESSION NUMBER:\t0000320193-26-000018\n"
        "FILER:\n  CENTRAL INDEX KEY:\t0000320193\n"
        "</SEC-HEADER>\n<DOCUMENT>\n").encode("ascii")


def require_test(ok: bool, label: str) -> None:
    if not ok:
        raise AssertionError(label)


def selftest() -> None:
    close = dt.datetime(2026, 7, 30, 20, tzinfo=dt.timezone.utc)
    with patch(__name__ + ".official_nasdaq_close_utc", return_value=close):
        a = parse_official_header(sample_header(), APPLE_ACC, APPLE_CIK, APPLE_ASOF)
        require_test(a["accepted_at_utc"] == "2026-07-30T20:30:28+00:00", "APPLE_ACCEPTED_CLOCK")
        require_test(a["status"] == "SGML_ACCEPTED_AFTER_RTH_CLOSE_UNKNOWN", "APPLE_AFTER_CLOSE")
        require_test(a["production_mc_primary_pass"] is False and a["can_register_R92"] is False, "NO_PRIMARY_NO_R92")
        good = parse_official_header(
            sample_header("20260730155900"), APPLE_ACC, APPLE_CIK, APPLE_ASOF)
        require_test(good["status"] == "SGML_ACCEPTED_PRE_RTH_CLOSE_SHADOW_ONLY", "PRE_CLOSE_SHADOW")
        cases = [
            (sample_header(), APPLE_ACC, "0000002178"),
            (sample_header(), "0000320193-26-000019", APPLE_CIK),
            (sample_header().replace(b"</SEC-HEADER>", b"</NOT-HEADER>"),
             APPLE_ACC, APPLE_CIK),
            (sample_header().replace(
                b"<ACCEPTANCE-DATETIME>20260730163028",
                b"<ACCEPTANCE-DATETIME>20260730163028\n<ACCEPTANCE-DATETIME>20260730163100"),
             APPLE_ACC, APPLE_CIK),
            (sample_header().replace(b"FILER:", b"FILER:\n CENTRAL INDEX KEY: 0000320193"),
             APPLE_ACC, APPLE_CIK),
            (b"", APPLE_ACC, APPLE_CIK),
            (sample_header() + b"x" * LIM, APPLE_ACC, APPLE_CIK),
        ]
        for data, acc, cik in cases:
            try:
                parse_official_header(data, acc, cik, APPLE_ASOF)
            except (ValueError, UnicodeError):
                continue
            raise AssertionError("SEC_SGML_PROVENANCE_NEGATIVE_BYPASS")
    require_test(sec_official_url(APPLE_ACC, APPLE_CIK).endswith(
        "/000032019326000018/0000320193-26-000018.txt"), "ACCESSION_URL_EXACT")
    # The old naive ZoneInfo.replace silently chose a UTC instant for both.
    require_test(strict_edgar_eastern_utc("20260730155900").isoformat() ==
                 "2026-07-30T19:59:00+00:00", "NORMAL_DST_ORIGIN")
    require_test(strict_edgar_eastern_utc("20261102155900").isoformat() ==
                 "2026-11-02T20:59:00+00:00", "NORMAL_STANDARD_TIME")
    for bad_time in ("20261101013000",  # repeated 01:30; two valid UTC instants
                     "20260308023000"): # skipped 02:30; no valid UTC instant
        try:
            strict_edgar_eastern_utc(bad_time)
        except ValueError as exc:
            require_test(str(exc) == "SEC_SGML_DST_CLOCK_AMBIGUOUS_OR_NONEXISTENT",
                         "DST_WRONG_REJECTION_REASON")
        else:
            raise AssertionError("SEC_SGML_DST_NEGATIVE_BYPASS")
        try:
            with patch(__name__ + ".official_nasdaq_close_utc", return_value=close):
                parse_official_header(sample_header(bad_time), APPLE_ACC, APPLE_CIK, APPLE_ASOF)
        except ValueError as exc:
            require_test(str(exc) == "SEC_SGML_CLOCK_OR_EXCHANGE_CUTOFF_INVALID",
                         "SGML_DST_FAIL_CLOSED_WRONG_REASON")
        else:
            raise AssertionError("SEC_SGML_PARSE_DST_NEGATIVE_BYPASS")
    print("XRAY_SEC_SGML_HEADER_SELFTEST=PASS_4_POSITIVE_11_NEGATIVE_NO_PRIMARY_PYTHON_O_SAFE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--apple-canary", action="store_true")
    parser.add_argument("--out", type=Path)
    a = parser.parse_args()
    if a.selftest:
        selftest()
    elif a.apple_canary:
        o = get_official_canary()
        if a.out:
            a.out.write_text(json.dumps(o, sort_keys=True, indent=2) + "\n")
        print("XRAY_SEC_SGML_CLOCK_WITNESS=" + o["status"])
        print("XRAY_SEC_SGML_NO_MC_NO_R92=PASS")
    else:
        parser.error("--selftest or --apple-canary required")
