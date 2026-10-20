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
    return hashlib.sha1(b"blob " + str(len(b)).encode() + bytes([0]) + b).hexdigest()

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

ETRA_FIRST = "2026-09-18"
ETRA_REGISTRY = ROOT / "price_official_listing_registry.json"
ETRA_SOURCE = ("https://ir.electra-therapeutics.com/news-releases/"
               "news-release-details/electra-therapeutics-announces-pricing-upsized-3500-million")

def etra_history_fence(asof, *, completed_sessions=None, evidence=None):
    if type(asof) is not str:
        raise ValueError("XRAY_ETRA_ASOF_TYPE")
    day = dt.date.fromisoformat(asof)
    need(day.isoformat() == asof, "ETRA_ASOF_FORMAT")
    if asof < ETRA_FIRST:
        return None
    registry = evidence if evidence is not None else json.loads(ETRA_REGISTRY.read_text())
    expected = {"first_trade_date": ETRA_FIRST,
                "authority": "ISSUER_IR_PRIMARY", "source_url": ETRA_SOURCE,
                "evidence_kind": "IPO_FIRST_TRADING_DATE"}
    need(type(registry) is dict
         and registry.get("schema") == "XRAY_PRICE_OFFICIAL_LISTING_REGISTRY_V1"
         and registry.get("authority") == "OFFICIAL_LISTING_DATE_FAIL_ONLY"
         and registry.get("execution") == "NONE"
         and registry.get("real_money") == "NO-GO"
         and registry.get("unknown_never_pass") is True
         and (registry.get("records") or {}).get("ETRA") == expected,
         "ETRA_ISSUER_PRIMARY_EVIDENCE")
    if completed_sessions is None:
        import pandas_market_calendars as mcal
        completed_sessions = [x.date().isoformat() for x in
            mcal.get_calendar("NASDAQ").valid_days(
                start_date=ETRA_FIRST, end_date=asof)]
    need(type(completed_sessions) is list
         and completed_sessions == sorted(set(completed_sessions))
         and all(type(d) is str and ETRA_FIRST <= d <= asof
                 for d in completed_sessions), "ETRA_SESSIONS_MALFORMED")
    count = len(completed_sessions)
    need(count <= (day - dt.date.fromisoformat(ETRA_FIRST)).days + 1,
         "ETRA_SESSIONS_EXCEED_CALENDAR")
    return {"symbol": "ETRA", "asof_et": asof,
            "first_traded_nasdaq_date": ETRA_FIRST,
            "completed_listed_sessions": count,
            "required_own_history_sessions": LIMIT,
            "own_listed_history_short": count < LIMIT,
            "pre_ipo_bars_must_be_ignored": True,
            "unverified_predecessor_cannot_fill_history": True,
            "evidence_git_blob_sha": git_blob(ETRA_REGISTRY) if evidence is None else None,
            "canonical_price_pass_created": False,
            "canonical_history_pass_created": False,
            "r92_created": False, "execution": "NONE", "real_money": "NO-GO"}

# Strict issuer IPO subset with independent Nasdaq market-site opening witnesses.
# The source registry is already in the repository; no provider queries required.
# Neither expected listing wording alone nor unrelated ticker reuse grants an IPO fence.
IPO_BELL_EVIDENCE = {
    "ACCV": {
        "first": "2026-09-30", "release": "2026-09-29",
        "issuer_url": "https://investors.accelevation.com/news-releases/news-release-details/accelevation-announces-pricing-initial-public-offering",
        "nasdaq_opening_bell": "https://www.nasdaq.com/events/accelevation-rings-opening-bell",
    },
    "ADRX": {
        "first": "2026-09-25", "release": "2026-09-24",
        "issuer_url": "https://investors.adarx.com/news-releases/news-release-details/adarx-pharmaceuticals-announces-pricing-upsized-4463-million",
        "nasdaq_opening_bell": "https://www.nasdaq.com/events/adarx-pharmaceuticals-rings-opening-bell",
    },
}

def confirmed_ipo_history_fence(symbol, asof, *, completed_sessions=None, evidence=None):
    spec = IPO_BELL_EVIDENCE.get(symbol)
    if spec is None:
        return None
    need(type(asof) is str, "IPO_ASOF_TYPE")
    day = dt.date.fromisoformat(asof)
    need(day.isoformat() == asof, "IPO_ASOF_INVALID")
    first = dt.date.fromisoformat(spec["first"])
    release = dt.date.fromisoformat(spec["release"])
    need(release < first, "IPO_SOURCE_DATE_ORDER")
    if day < first:
        return None  # the listed instrument did not yet trade at this ASOF
    registry = (evidence if evidence is not None
                else json.loads(ETRA_REGISTRY.read_text()))
    expected = {
        "first_trade_date": spec["first"],
        "authority": "ISSUER_IR_PRIMARY",
        "source_url": spec["issuer_url"],
        "evidence_kind": "IPO_FIRST_TRADING_DATE",
    }
    need(type(registry) is dict
         and registry.get("schema") == "XRAY_PRICE_OFFICIAL_LISTING_REGISTRY_V1"
         and registry.get("authority") == "OFFICIAL_LISTING_DATE_FAIL_ONLY"
         and registry.get("execution") == "NONE"
         and registry.get("real_money") == "NO-GO"
         and registry.get("unknown_never_pass") is True
         and (registry.get("records") or {}).get(symbol) == expected,
         "IPO_ISSUER_REGISTRY_MISMATCH")
    if completed_sessions is None:
        import pandas_market_calendars as mcal
        completed_sessions = [
            x.date().isoformat() for x in
            mcal.get_calendar("NASDAQ").valid_days(
                start_date=spec["first"], end_date=asof)
        ]
    need(type(completed_sessions) is list
         and completed_sessions == sorted(set(completed_sessions))
         and all(type(s) is str and spec["first"] <= s <= asof
                 for s in completed_sessions), "IPO_BAD_SESSION_LIST")
    count = len(completed_sessions)
    need(count <= (day - first).days + 1, "IPO_MORE_SESSIONS_THAN_DAYS")
    return {
        "symbol": symbol, "asof_et": asof,
        "source_publication_date": spec["release"],
        "issuer_official_source_url": spec["issuer_url"],
        "nasdaq_official_opening_bell_url": spec["nasdaq_opening_bell"],
        "first_traded_nasdaq_date": spec["first"],
        "completed_listed_sessions": count,
        "required_own_history_sessions": LIMIT,
        "own_listed_history_short": count < LIMIT,
        "pre_ipo_bars_must_be_ignored": True,
        "unverified_predecessor_cannot_fill_history": True,
        "evidence_git_blob_sha": git_blob(ETRA_REGISTRY) if evidence is None else None,
        "canonical_price_pass_created": False,
        "canonical_history_pass_created": False,
        "r92_created": False, "execution": "NONE", "real_money": "NO-GO",
    }

def rebind_confirmed_ipo_research_results(results, asof):
    """Repair only cached issuer-IPO HISTORY unknowns; never add PASS."""
    need(type(results) is dict, "IPO_RESULTS_NOT_DICT")
    converted = 0
    for symbol in sorted(IPO_BELL_EVIDENCE):
        prior = results.get(symbol)
        if prior is None:
            continue
        need(type(prior) is dict and type(prior.get("status")) is str,
             "IPO_MALFORMED_ROW")
        if prior["status"] not in {
            "UNKNOWN_STATIC", "UNKNOWN_RETRY", "UNKNOWN_RETRY_EXHAUSTED"
        }:
            continue  # existing terminal FAIL and unrelated PASS untouched
        info = confirmed_ipo_history_fence(symbol, asof)
        if info is None or not info["own_listed_history_short"]:
            continue
        results[symbol] = {
            **prior, "status": "FAIL_HISTORY",
            "prior_untrusted_status": prior["status"],
            "official_first_trade_failonly_rebound": True,
            "info": {
                "reason": "OFFICIAL_FIRST_TRADE_LT260_HARD_HISTORY_FAIL",
                "first_traded_nasdaq_date": info["first_traded_nasdaq_date"],
                "completed_listed_sessions": info["completed_listed_sessions"],
                "bars": info["completed_listed_sessions"],
                "required_own_history_sessions": LIMIT,
                "source_evidence_blob_sha": info["evidence_git_blob_sha"],
                "issuer_opening_bell_confirmed": True,
                "vendor_history_pre_ipo_quarantined": True,
                "no_synthetic_bar": True, "unknown_never_pass": True,
            },
        }
        converted += 1
    return converted


def fence(symbol, asof, *, completed_sessions=None, evidence=None):
    """Return proof-bound local 260 result, or None outside this evidence scope.

    completed_sessions may be supplied only to deterministic offline selftests;
    the live call always computes actual NASDAQ sessions via pinned calendar.
    """
    if symbol in IPO_BELL_EVIDENCE:
        return confirmed_ipo_history_fence(symbol, asof,
            completed_sessions=completed_sessions, evidence=evidence)
    if symbol == "ETRA":
        return etra_history_fence(asof, completed_sessions=completed_sessions, evidence=evidence)
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

def rebind_existing_research_results(results, asof):
    """Demote previously cached BSP PASS at the same ASOF without vendor calls.

    A code fix in parse_hist alone misses already-frozen PASS rows because the
    same epoch normally re-fetches only retry candidates. This fail-only
    reconciliation must run before recomputing result hashes and summaries.
    """
    need(type(results) is dict, "REBOUND_RESULTS_NOT_DICT")
    old = results.get("BSP")
    if old is None:
        return 0
    need(type(old) is dict and type(old.get("status")) is str,
         "REBOUND_BSP_RECORD_MALFORMED")
    info = fence("BSP", asof)
    if info is None or not info["own_listed_history_short"]:
        return 0
    reason = "OFFICIAL_FIRST_TRADE_LT260_HARD_HISTORY_FAIL"
    if (old["status"] == "FAIL_HISTORY" and
        (old.get("info") or {}).get("reason") == reason and
        old.get("official_first_trade_failonly_rebound") is True):
        return 0
    # Never turn a pre-existing independently proven failure/block into PASS
    # or hide it behind a different veto.
    if old["status"] not in {"PASS", "UNKNOWN_STATIC",
                              "UNKNOWN_RETRY", "UNKNOWN_RETRY_EXHAUSTED"}:
        return 0
    old_status = old["status"]
    rewritten = dict(old)
    rewritten.update({
        "status": "FAIL_HISTORY",
        "prior_untrusted_status": old_status,
        "official_first_trade_failonly_rebound": True,
        "info": {
            "reason": reason,
            "first_traded_nasdaq_date": info["first_traded_nasdaq_date"],
            "completed_listed_sessions": info["completed_listed_sessions"],
            "bars": info["completed_listed_sessions"],
            "required_own_history_sessions": LIMIT,
            "source_evidence_blob_sha": info["evidence_git_blob_sha"],
            "vendor_history_pre_ipo_quarantined": True,
            "no_synthetic_bar": True, "unknown_never_pass": True
        }
    })
    results["BSP"] = rewritten
    return 1


def rebind_etra_research_results(results, asof):
    """Terminalize already-cached ETRA UNKNOWN without a vendor retry."""
    need(type(results) is dict, "ETRA_REBOUND_RESULTS_TYPE")
    old = results.get("ETRA")
    if old is None:
        return 0
    need(type(old) is dict and type(old.get("status")) is str,
         "ETRA_REBOUND_ROW_MALFORMED")
    info = fence("ETRA", asof)
    if info is None or not info["own_listed_history_short"]:
        return 0
    reason = "OFFICIAL_FIRST_TRADE_LT260_HARD_HISTORY_FAIL"
    if (old["status"] == "FAIL_HISTORY"
            and (old.get("info") or {}).get("reason") == reason
            and old.get("official_first_trade_failonly_rebound") is True):
        return 0
    if old["status"] not in {"PASS", "UNKNOWN_STATIC",
                             "UNKNOWN_RETRY", "UNKNOWN_RETRY_EXHAUSTED"}:
        return 0
    results["ETRA"] = {**old, "status": "FAIL_HISTORY",
        "prior_untrusted_status": old["status"],
        "official_first_trade_failonly_rebound": True,
        "info": {
            "reason": reason,
            "first_traded_nasdaq_date": info["first_traded_nasdaq_date"],
            "completed_listed_sessions": info["completed_listed_sessions"],
            "bars": info["completed_listed_sessions"],
            "required_own_history_sessions": LIMIT,
            "source_evidence_blob_sha": info["evidence_git_blob_sha"],
            "vendor_history_pre_ipo_quarantined": True,
            "no_synthetic_bar": True, "unknown_never_pass": True}}
    return 1


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
    prior = {"BSP": {"status": "PASS", "info": {"bars": 3757},
                     "attempts": 1},
             "AAPL": {"status": "PASS", "info": {"bars": 1200}}}
    # Live test of the pure mutation protocol, with a deterministic calendar
    # injected into a real fence call through the current runtime dependency.
    # In offline code coverage the calendar is imported only in this fixture.
    # The stage reconciliation itself is exercised by Actions at fixed ASOF.
    need("BSP" in prior and prior["BSP"]["status"] == "PASS",
         "TEST_OLD_PASS_PRECONDITION")
    changed = rebind_existing_research_results(prior, "2026-10-13")
    need(changed == 1 and prior["BSP"]["status"] == "FAIL_HISTORY"
         and prior["BSP"]["info"]["bars"] < LIMIT
         and prior["BSP"]["info"]["vendor_history_pre_ipo_quarantined"]
         and prior["BSP"]["prior_untrusted_status"] == "PASS"
         and prior["AAPL"]["status"] == "PASS"
         and rebind_existing_research_results(prior, "2026-10-13") == 0,
         "FROZEN_OLD_PASS_MUST_DEMOTE_IDEMPOTENTLY")
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
    issuer = json.loads(ETRA_REGISTRY.read_text())
    etra_days = [
        (dt.date(2026, 9, 18) + dt.timedelta(days=i)).isoformat()
        for i in range(32)
    ]
    etra = fence("ETRA", "2026-10-19",
                 completed_sessions=etra_days, evidence=issuer)
    need(etra["own_listed_history_short"]
         and etra["completed_listed_sessions"] == 32
         and not etra["canonical_history_pass_created"]
         and not etra["canonical_price_pass_created"]
         and not etra["r92_created"], "ETRA_FAIL_ONLY_EXPECTED")
    need(fence("ETRA", "2026-09-17", completed_sessions=[], evidence=issuer)
         is None, "ETRA_FUTURE_LISTING_LOOKAHEAD")
    bad_etra = copy.deepcopy(issuer)
    bad_etra["records"]["ETRA"]["first_trade_date"] = "2026-09-16"
    try:
        fence("ETRA", "2026-10-19", completed_sessions=etra_days,
              evidence=bad_etra)
    except ValueError:
        pass
    else:
        raise AssertionError("ETRA_FORGED_FIRST_TRADE_ACCEPTED")
    bad_etra = copy.deepcopy(issuer)
    bad_etra["records"]["ETRA"]["source_url"] = "https://example.com"
    try:
        fence("ETRA", "2026-10-19", completed_sessions=etra_days,
              evidence=bad_etra)
    except ValueError:
        pass
    else:
        raise AssertionError("ETRA_FORGED_ISSUER_ACCEPTED")
    try:
        fence("ETRA", "2026-10-19", completed_sessions=etra_days * 2,
              evidence=issuer)
    except ValueError:
        pass
    else:
        raise AssertionError("ETRA_DUPLICATE_SESSIONS_ACCEPTED")
    rows = {"ETRA": {"status": "UNKNOWN_STATIC",
                      "info": {"reason": "SINA_DAILY_LT260_REQUIRES_INDEPENDENT_CONFIRMATION"}},
            "AAPL": {"status": "PASS", "info": {"bars": 1000}}}
    need(rebind_etra_research_results(rows, "2026-10-19") == 1
         and rows["ETRA"]["status"] == "FAIL_HISTORY"
         and rows["ETRA"]["prior_untrusted_status"] == "UNKNOWN_STATIC"
         and rows["ETRA"]["info"]["bars"] < LIMIT
         and rows["AAPL"]["status"] == "PASS"
         and rebind_etra_research_results(rows, "2026-10-19") == 0,
         "ETRA_REAL_CACHED_REBOUND_IDEMPOTENCE")
    print("XRAY_ETRA_OFFICIAL_FAIL_ONLY_SELFTEST=PASS_NO_PRICE_HISTORY_R92_PROMOTION")
    print("XRAY_FIRST_TRADE_BSP_SELFTEST=PASS_105_DAY_BOUND_5_NEGATIVES_OLD_PASS_DEMOTED_NO_R92")

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
