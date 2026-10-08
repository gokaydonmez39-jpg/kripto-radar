#!/usr/bin/env python3
"""Exact-ASOF, official-Nasdaq historical halt witness: BLOCK -> terminal FAIL only.

No quote, synthetic bar, PASS, BUY, MC, Event or R92 authority is created.
Witness recorded from GitHub Action 37751249372, which fetched the Nasdaq
09/23/2026 RSS: 93 rows, GRAL official Mkt=Q, next-day resumption.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
WITNESS = ROOT / "evidence" / "nasdaq_gral_20260923_full_session_halt_v1.json"
SCHEMA = "XRAY_PRICE_HISTORICAL_HALT_FAIL_ONLY_WITNESS_V1"


def _time(value):
    clean = re.sub(r"\\s*\\.\\s*\\d+\\s*$", "", str(value or "")).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(clean, fmt).time()
        except ValueError:
            pass
    return None


def evaluate(witness, sym, asof, expected30, row):
    """Only an already-BLOCKED, exact-30 incomplete row can become FAIL."""
    if not isinstance(witness, dict) or not isinstance(row, dict):
        return None
    if row.get("status") != "BLOCK_CURRENT_RUN":
        return None
    if not (
        witness.get("schema") == SCHEMA
        and witness.get("asof_et") == asof
        and witness.get("symbol") == sym
        and witness.get("execution") == "NONE"
        and witness.get("real_money") == "NO-GO"
        and witness.get("unknown_never_pass") is True
        and witness.get("no_synthetic_bar") is True
        and witness.get("alpha_authority") is False
        and witness.get("decision_direction") == "BLOCK_TO_FAIL_ONLY_NEVER_PASS"
    ):
        return None
    dates = list(expected30 or [])
    if len(dates) != 30 or len(set(dates)) != 30 or dates[-1] != asof:
        return None
    info = row.get("info") or {}
    missing = list(info.get("missing_sessions") or [])
    if missing != [witness.get("halt_session")] or missing[0] not in dates:
        return None
    if info.get("observed_usable_sessions") != 29 or info.get("no_synthetic_bar") is not True:
        return None
    recovered = ((row.get("block_recovery_attempt") or {}).get("provider_result") or {})
    sina = recovered.get("sina_result") or {}
    if sina.get("known_session_count") != 29 or list(sina.get("missing_sessions") or []) != missing:
        return None
    official = witness.get("official_rss_record") or {}
    if not (
        official.get("IssueSymbol") == sym
        and official.get("Mkt") in ("Q", "G", "S")
        and official.get("HaltDate") == dt.date.fromisoformat(missing[0]).strftime("%m/%d/%Y")
        and official.get("ReasonCode") in ("T1", "T2", "T3")
    ):
        return None
    start = _time(official.get("HaltTime"))
    resume = _time(official.get("ResumptionTradeTime"))
    try:
        resumedate = dt.datetime.strptime(official["ResumptionDate"], "%m/%d/%Y").date()
        haltdate = dt.date.fromisoformat(missing[0])
    except (KeyError, ValueError, TypeError):
        return None
    if start is None or start > dt.time(9, 30) or resume is None:
        return None
    if resumedate < haltdate or (resumedate == haltdate and resume <= dt.time(16, 0)):
        return None
    source = witness.get("source") or {}
    if not (
        source.get("url") == "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate=09232026"
        and source.get("workflow_run_id") == 37751249372
        and source.get("workflow_head_sha") == "da25d4204220d34a00d0deb08ec9494f6154eb2d"
        and source.get("official_feed_row_count") == 93
        and source.get("matched_symbol_row_count") == 1
    ):
        return None
    return {
        "reason": "OFFICIAL_HISTORICAL_FULL_SESSION_HALT_30_USABLE_SESSIONS_IMPOSSIBLE",
        "proof": "NASDAQ_RSS_NEXT_DAY_RESUME_PLUS_RALLIES_SINA_EXACT_MISSING_DATE",
        "source": "NASDAQ_TRADER_HISTORICAL_RSS_NON_G9",
        "source_url": source["url"],
        "witness_path": "nasdaq-xray/evidence/nasdaq_gral_20260923_full_session_halt_v1.json",
        "official_halt_session": missing[0],
        "resumption_date": resumedate.isoformat(),
        "expected_session_count": 30,
        "observed_usable_sessions": 29,
        "missing_sessions": missing,
        "no_synthetic_bar": True,
        "unknown_never_pass": True,
        "decision_direction": "FAIL_ONLY_NEVER_PASS",
    }


def load_witness(asof):
    try:
        witness = json.loads(WITNESS.read_text(encoding="utf-8"))
        if witness.get("asof_et") == asof:
            return witness
    except (OSError, ValueError, TypeError):
        pass
    return None


def apply_to_results(results, asof, expected30):
    witness = load_witness(asof)
    if witness is None:
        return []
    sym = witness.get("symbol")
    row = results.get(sym)
    ev = evaluate(witness, sym, asof, expected30, row)
    if not ev:
        return []
    results[sym] = {
        "status": "FAIL_DV30_INSUFFICIENT_SESSIONS",
        "info": ev,
        "provenance": "EXACT_ASOF_NASDAQ_HISTORICAL_HALT_FAIL_ONLY",
    }
    return [sym]


def selftest():
    import copy
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    dates = [("2026-09-%02d" % x) for x in range(1, 31)]
    dates = [d for d in dates if d != "2026-09-06"][:29] + ["2026-10-07"]
    if "2026-09-23" not in dates:
        dates[5] = "2026-09-23"
    row = {
        "status": "BLOCK_CURRENT_RUN",
        "info": {"missing_sessions": ["2026-09-23"], "observed_usable_sessions": 29,
                 "no_synthetic_bar": True},
        "block_recovery_attempt": {"provider_result": {
            "sina_result": {"known_session_count": 29, "missing_sessions": ["2026-09-23"]}
        }},
    }
    valid = evaluate(witness, "GRAL", "2026-10-07", dates, row)
    assert valid and valid["decision_direction"] == "FAIL_ONLY_NEVER_PASS"
    cases = [
        (copy.deepcopy(witness), {**row, "status": "PASS_PRICE_DV30"}),
        ({**witness, "asof_et": "2026-10-08"}, row),
        ({**witness, "official_rss_record": {**witness["official_rss_record"], "Mkt": "N"}}, row),
        ({**witness, "official_rss_record": {**witness["official_rss_record"], "ResumptionDate": "09/23/2026", "ResumptionTradeTime": "15:59:59"}}, row),
        (witness, {**row, "info": {**row["info"], "missing_sessions": []}}),
        (witness, {**row, "block_recovery_attempt": {}}),
        ({**witness, "no_synthetic_bar": False}, row),
        ({**witness, "source": {**witness["source"], "workflow_run_id": 0}}, row),
    ]
    for badw, badrow in cases:
        assert evaluate(badw, "GRAL", "2026-10-07", dates, badrow) is None
    guarded = {"GRAL": copy.deepcopy(row), "TEST": {"status": "PASS_PRICE_DV30"}}
    applied = apply_to_results(guarded, "2026-10-07", dates)
    assert applied == ["GRAL"] and guarded["GRAL"]["status"] == "FAIL_DV30_INSUFFICIENT_SESSIONS"
    assert guarded["TEST"]["status"] == "PASS_PRICE_DV30"
    assert apply_to_results(guarded, "2026-10-07", dates) == []
    assert apply_to_results({"GRAL": copy.deepcopy(row)}, "2026-10-08", dates) == []
    print("XRAY_HISTORICAL_HALT_FAIL_ONLY_SELFTEST=PASS (NO_PASS_NO_SYNTHETIC_BAR)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        ap.error("--selftest only; production consumer imports apply_to_results")
