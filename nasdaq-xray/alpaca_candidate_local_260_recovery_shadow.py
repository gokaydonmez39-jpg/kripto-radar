#!/usr/bin/env python3
"""Candidate-local current-ASOF SIP 260/52 recovery probe: research ONLY.

Consumes real runner-authorized historical Alpaca SIP through the repository's
existing paginated transport. Never persists OHLCV, promotes a Sina failure
to canonical HISTORY, asserts market-data redistribution rights, writes
production gates, trades, registers R92 or notifies any user.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from alpaca_free_sip_shadow_guard import request_batch, sufficient_delay
from alpaca_full_scope_260_shadow import classify
from current_history_source_request import expected_dates
from source_epoch_freshness_guard import last_complete_session

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "orchestrator_state.json"
SCHEMA = "XRAY_CANDIDATE_LOCAL_REAL_SIP_260_52_RECOVERY_SHADOW_V1"
UTC = dt.timezone.utc
MAX_SCOPE = 96
BATCH = 12

def need(valid, why):
    if not valid:
        raise ValueError("XRAY_CANDIDATE_LOCAL_SIP_" + why)

def blob_sha(path):
    b = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()

def source_scope(root, now):
    """Select ALL unresolved tracked symbols; never leak other symbols' veto."""
    need(now.tzinfo is not None, "UTC_CLOCK_REQUIRED")
    watch = root.get("watch_radar") or {}
    funnel = root.get("candidate_technical_funnel") or {}
    asof = root.get("asof_et")
    need(root.get("execution") == "NONE" and root.get("real_money") == "NO-GO",
         "ROOT_SAFETY")
    need(type(asof) is str and asof == watch.get("asof_et")
         and asof == funnel.get("asof_et"), "EXACT_SAME_ASOF")
    need(asof == last_complete_session(now), "NOT_LATEST_COMPLETED_EXCHANGE_SESSION")
    rows = watch.get("watchlist")
    need(type(rows) is list and watch.get("all_eligible_candidates_tracked") is True
         and watch.get("watchlist_cap") is None
         and len(rows) == watch.get("watchlist_count")
         and len(rows) == funnel.get("candidate_count"),
         "FULL_CANDIDATE_COHORT")
    names = [row.get("symbol") for row in rows if type(row) is dict]
    need(len(names) == len(rows) and len(set(names)) == len(names)
         and all(type(s) is str and s for s in names),
         "CANDIDATE_UNIVERSE_MALFORMED")
    results = funnel.get("results")
    need(type(results) is dict and set(results) == set(names)
         and funnel.get("attempted_count") == len(names),
         "RESULT_PARTITION_INCOMPLETE")
    target = sorted(sym for sym in names if type(results.get(sym)) is dict
                    and type(results[sym].get("status")) is str
                    and results[sym]["status"].startswith("UNKNOWN_"))
    need(len(target) <= MAX_SCOPE, "NO_SILENT_SCOPE_TRUNCATION")
    daily, weeks = expected_dates(asof)
    need(len(daily) == 260 and len(weeks) == 52 and daily[-1] == asof,
         "OFFICIAL_260_52")
    return asof, target, daily, weeks

def base_report(asof, symbols, source_blob):
    return {
        "schema": SCHEMA, "asof_et": asof,
        "source_orchestrator_git_blob_sha": source_blob,
        "scope_symbols": symbols, "scope_count": len(symbols),
        "expected_daily_sessions": 260, "required_week_closes": 52,
        "feed": "ALPACA_HISTORICAL_SIP", "adjustment": "raw",
        "mode": "INDEPENDENT_SOURCE_AVAILABILITY_ONLY",
        "status": "UNKNOWN_UNMEASURED", "observations": {},
        "classification_counts": {}, "measured_scope_count": 0,
        "unattended_runner_data_access_credential_present": False,
        "source_market_data_rights_independently_attested": False,
        "issuer_corporate_actions_pit_reconciled": False,
        "legal_nasdaq_halt_event_regime_mc_approved": False,
        "canonical_history_promoted": False,
        "canonical_price_promoted": False,
        "final_buy_signals": [], "registered_r92_count": 0,
        "vendor_ohlcv_in_artifact": False, "vendor_raw_bars_persisted": False,
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True
    }

def audit(asof, symbols, daily, weeks, source_blob, fetch, now):
    report = base_report(asof, symbols, source_blob)
    need(now.tzinfo is not None and sufficient_delay(asof, now),
         "20MIN_OFFICIAL_CLOSE_HOLDBACK")
    need(symbols == sorted(set(symbols)), "SORTED_EXACT_UNIQUE_SCOPE")
    start = daily[0] + "T00:00:00Z"
    end = (dt.date.fromisoformat(asof) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    result = {}
    for offset in range(0, len(symbols), BATCH):
        subset = symbols[offset:offset+BATCH]
        raw = fetch(subset, start, end, asof)
        need(type(raw) is dict and set(raw) == set(subset),
             "PARTIAL_OR_FOREIGN_SOURCE_BATCH")
        for symbol in subset:
            status, count = classify(raw[symbol], daily, weeks, asof)
            result[symbol] = {"source_availability": status,
                              "observed_official_session_count": count,
                              "canonical_primary": False}
        del raw
    report["observations"] = result
    report["classification_counts"] = dict(sorted(
        collections.Counter(r["source_availability"] for r in result.values()).items()))
    report["measured_scope_count"] = len(result)
    need(len(result) == len(symbols) and
         sum(report["classification_counts"].values()) == len(symbols),
         "SOURCE_EXACT_PARTITION")
    report["status"] = "SHADOW_SOURCE_AVAILABILITY_MEASURED_NO_AUTHORITY"
    return report

def selftest():
    asof = "2026-10-13"
    now = dt.datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
    fake = {"execution": "NONE", "real_money": "NO-GO", "asof_et": asof,
            "watch_radar": {"asof_et": asof,
                 "watchlist": [{"symbol": "AAA"}, {"symbol": "BBB"}],
                 "watchlist_count": 2, "watchlist_cap": None,
                 "all_eligible_candidates_tracked": True},
            "candidate_technical_funnel": {"asof_et": asof,
                 "candidate_count": 2, "attempted_count": 2, "results": {
                   "AAA": {"status": "UNKNOWN_260_OFFICIAL_HISTORY"},
                   "BBB": {"status": "NO_CURRENT_OR_RECENT_WEEKLY_GATE"}}}}
    a, symbols, daily, weeks = source_scope(fake, now)
    need(a == asof and symbols == ["AAA"] and daily[-1] == asof
         and len(weeks) == 52, "ONLY_ACTUAL_UNKNOWN_LOCAL")
    report = base_report(asof, symbols, "a"*40)
    need(report["registered_r92_count"] == 0 and
         report["source_market_data_rights_independently_attested"] is False
         and report["canonical_history_promoted"] is False,
         "NO_PREMATURE_SOURCE_PROMOTION")
    fake["candidate_technical_funnel"]["results"]["BBB"]["status"] = "UNKNOWN_R1"
    need(source_scope(fake, now)[1] == ["AAA", "BBB"], "ALL_UNKNOWNS_INCLUDED")
    fake["candidate_technical_funnel"]["candidate_count"] = 1
    try:
        source_scope(fake, now)
    except ValueError as exc:
        need("FULL_CANDIDATE_COHORT" in str(exc), "TRUNCATION_REASON")
    else:
        raise AssertionError("TRUNCATED_SCOPE_ACCEPTED")
    fake["candidate_technical_funnel"]["candidate_count"] = 2
    fake["asof_et"] = "2026-10-12"
    try:
        source_scope(fake, now)
    except ValueError:
        pass
    else:
        raise AssertionError("MISMATCHED_ASOF_ACCEPTED")
    need(classify([], daily, weeks, asof)[0] == "NO_BAR",
         "MISSING_SIP_CANNOT_PASS")
    print("XRAY_CANDIDATE_LOCAL_SIP_RECOVERY_SELFTEST=PASS_SOURCE_EXACT_NO_PRIMARY_NO_R92")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    need(args.out is not None and
         not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "EPHEMERAL_OUTPUT_ONLY")
    now = dt.datetime.now(UTC)
    root = json.loads(STATE.read_text())
    asof, symbols, daily, weeks = source_scope(root, now)
    key = (os.getenv("XRAY_ALPACA_DATA_KEY_ID") or
           os.getenv("XRAY_ALPACA_API_KEY_ID") or "").strip()
    secret = (os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or
              os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "").strip()
    report = base_report(asof, symbols, blob_sha(STATE))
    if not symbols:
        report["status"] = "NO_UNRESOLVED_SOURCE_SYMBOLS"
    elif not (key and secret):
        report["status"] = "UNKNOWN_ALPACA_RUNNER_CREDENTIALS"
    else:
        report["unattended_runner_data_access_credential_present"] = True
        try:
            report = audit(asof, symbols, daily, weeks, blob_sha(STATE),
                lambda sub, start, end, asof: request_batch(
                  sub, start, end, key, secret, adjustment="raw", asof=asof), now)
            report["unattended_runner_data_access_credential_present"] = True
        except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
            code = str(exc)
            report["status"] = ("UNKNOWN_" + code if code.startswith("ALPACA_")
                                else "UNKNOWN_SOURCE_TRANSPORT_OR_SCHEMA")
    args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("XRAY_SIP_CANDIDATE_LOCAL_STATUS=" + report["status"])
    print("XRAY_SIP_CANDIDATE_LOCAL_COUNTS=" +
          json.dumps(report["classification_counts"], sort_keys=True))
    print("XRAY_SIP_CANDIDATE_LOCAL_PER_SYMBOL=" +
          json.dumps({symbol: item["source_availability"]
                      for symbol,item in sorted(report["observations"].items())},
                     sort_keys=True))
    if report["status"].startswith("UNKNOWN_"):
        raise SystemExit(2)

if __name__ == "__main__":
    main()
