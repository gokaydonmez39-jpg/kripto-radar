#!/usr/bin/env python3
"""Fail-only first-trade history fence: a ticker's prior owner is not this issuer.

A dated Nasdaq source can prove a newly listed issuer lacks 260 own-symbol
completed sessions. This DOES NOT prove any future history PASS, attribute
unverified predecessor OHLCV or alter canonical PRICE/MC/R92.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence/bsp_20260701_official_first_trade_v1.json"
SCHEMA = "XRAY_OFFICIAL_FIRST_TRADE_HISTORY_FENCE_V1"
URL = ("https://www.nasdaq.com/press-release/"
       "bending-spoons-spa-announces-closing-initial-public-offering-2026-07-02")
ASOF_MIN = "2026-07-02"
BSP_FIRST = "2026-07-01"
LIMIT = 260

def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_FIRST_TRADE_HISTORY_" + reason)

def git_blob(path):
    b = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\\0" + b).hexdigest()

def validate_evidence(doc):
    need(type(doc) is dict and doc.get("schema") == SCHEMA, "SCHEMA")
    expected = {
        "symbol": "BSP", "issuer": "Bending Spoons S.p.A.",
        "source": "NASDAQ_PUBLISHED_ISSUER_PRESS_RELEASE",
        "source_url": URL, "source_publication_date": ASOF_MIN,
        "first_traded_nasdaq_date": BSP_FIRST,
        "first_traded_exchange": "NASDAQ_GLOBAL_SELECT_MARKET",
        "asof_applicability": "SOURCE_PUBLISHED_ON_OR_BEFORE_ASOF_ONLY",
        "historical_ticker_reuse_must_not_imply_issuer_continuity": True,
        "pre_ipo_vendor_bars_excluded_from_same_issuer_260_history": True,
        "actual_source_html_sha256_captured": False,
        "issuer_predecessor_continuity_proven": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
        "canonical_price_pass_created": False,
        "canonical_history_pass_created": False, "r92_created": False}
    for k, v in expected.items():
        need(doc.get(k) == v, "EVIDENCE_" + k.upper())
    need(dt.date.fromisoformat(BSP_FIRST) <
         dt.date.fromisoformat(ASOF_MIN), "SOURCE_TIME_ORDER")

def fence(symbol, asof, *, completed_sessions=None, evidence=None):
    """Return proof-bound local 260 result, or None outside this evidence scope.

    completed_sessions may be supplied only to deterministic offline selftests;
    the live call always computes actual NASDAQ sessions via pinned calendar.
    """
    if symbol != "BSP":
        return None
    need(type(asof) is str and dt.date.fromisoformat(asof).isoformat() == asof,
         "ASOF_INVALID")
    if asof < ASOF_MIN:
        return None  # A 2-Jul source may not certify an earlier ASOF.
    doc = evidence if evidence is not None else json.loads(EVIDENCE.read_text())
    validate_evidence(doc)
    if completed_sessions is None:
        import pandas_market_calendars as mcal
        completed_sessions = [
            t.date().isoformat()
            for t in mcal.get_calendar("NASDAQ").valid_days(
                start_date=BSP_FIRST, end_date=asof)
        ]
    need(type(completed_sessions) is list and
         completed_sessions == sorted(set(completed_sessions)) and
         all(type(day) is str and BSP_FIRST <= day <= asof
             for day in completed_sessions),
         "SESSION_PROOF_MALFORMED")
    count = len(completed_sessions)
    # The calendar count is solely an upper bound on valid issuer HISTORY;
    # old Sina bars from a previous ticker occupant are never inherited.
    return {
        "symbol": "BSP", "asof_et": asof,
        "source_publication_date": ASOF_MIN,
        "first_traded_nasdaq_date": BSP_FIRST,
        "completed_listed_sessions": count,
        "required_own_history_sessions": LIMIT,
        "own_listed_history_short": count < LIMIT,
        "pre_ipo_bars_must_be_ignored": True,
        "unverified_predecessor_cannot_fill_history": True,
        "evidence_git_blob_sha": git_blob(EVIDENCE) if evidence is None else None,
        "canonical_price_pass_created": False,
        "canonical_history_pass_created": False,
        "r92_created": False, "execution": "NONE", "real_money": "NO-GO"
    }

def selftest():
    doc = json.loads(EVIDENCE.read_text())
    validate_evidence(doc)
    # Deterministic upper bound: the actual official calendar can contain
    # fewer days, never more than the total calendar-day range.
    cal_days = [(dt.date(2026, 7, 1) + dt.timedelta(days=i)).isoformat()
                for i in range((dt.date(2026, 10, 13) -
                                dt.date(2026, 7, 1)).days + 1)]
    result = fence("BSP", "2026-10-13", completed_sessions=cal_days)
    need(result["own_listed_history_short"] and
         result["completed_listed_sessions"] < LIMIT and
         not result["canonical_history_pass_created"] and
         result["unverified_predecessor_cannot_fill_history"],
         "OCT13_BSP_MUST_NOT_HAVE_260")
    need(fence("AAPL", "2026-10-13", completed_sessions=cal_days) is None,
         "FOREIGN_ISSUER_VETO")
    need(fence("BSP", "2026-07-01", completed_sessions=[]) is None,
         "FUTURE_PUBLICATION_LOOKAHEAD")
    # Post-260 coverage only removes a short-history VETO; does not grant PASS.
    late = fence("BSP", "2027-12-30", completed_sessions=[
        (dt.date(2026, 7, 1) + dt.timedelta(days=i)).isoformat()
        for i in range(260)])
    need(not late["own_listed_history_short"] and
         not late["canonical_history_pass_created"],
         "260_IS_NOT_PRODUCTION_PASS")
    mutants = [
        ("EARLY_SOURCE", lambda d: d.update(source_publication_date="2026-06-30")),
        ("FOREIGN_URL", lambda d: d.update(source_url="https://example.net")),
        ("FAKE_PREDECESSOR", lambda d: d.update(issuer_predecessor_continuity_proven=True)),
        ("FALSE_RELEASE", lambda d: d.update(canonical_history_pass_created=True)),
        ("FAKE_FIRST_DAY", lambda d: d.update(first_traded_nasdaq_date="2025-07-01")),
    ]
    for name, mutate in mutants:
        bad = copy.deepcopy(doc)
        mutate(bad)
        try:
            fence("BSP", "2026-10-13", completed_sessions=cal_days,
                  evidence=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("BAD_EVIDENCE_ACCEPTED_" + name)
    print("XRAY_FIRST_TRADE_BSP_SELFTEST=PASS_105_CALENDAR_DAY_UPPER_BOUND_5_NEGATIVES_NO_HIST_PASS_R92")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--asof", default="2026-10-13")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        x = fence("BSP", a.asof)
        print(json.dumps(x, sort_keys=True))

if __name__ == "__main__":
    main()
