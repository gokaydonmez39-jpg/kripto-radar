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
    source_sha = watch.get("source_candidates_sha256")
    digest = watch.get("watchlist_digest")
    need(type(source_sha) is str and len(source_sha) == 64
         and source_sha == funnel.get("source_candidates_sha256")
         and type(digest) is str and len(digest) == 64
         and digest == funnel.get("watchlist_digest"),
         "CANDIDATE_SOURCE_AND_WATCH_DIGEST_MISMATCH")
    results = funnel.get("results")
    known = set(results) if type(results) is dict else set()
    universe = set(names)
    need(type(results) is dict and known.issubset(universe)
         and all(type(row) is dict and type(row.get("status")) is str
                 for row in results.values())
         and type(funnel.get("attempted_count")) is int
         and funnel["attempted_count"] == len(known),
         "RESULT_PARTITION_INCOMPLETE")
    unattempted = universe - known
    # The technical producer is allowed to stop mid-cohort. Its explicit
    # pending partition MUST contain precisely every unattempted symbol AND
    # every already-attempted UNKNOWN. A missing row is not a technical PASS.
    # It may still receive a separate *research-only* SIP history observation.
    if unattempted:
        pending = funnel.get("pending_symbols")
        pending_observed = {
            sym for sym, row in results.items()
            if row["status"].startswith("UNKNOWN_")
        }
        need(type(pending) is list and
             len(pending) == len(set(pending)) and
             all(type(sym) is str for sym in pending) and
             type(funnel.get("pending_count")) is int and
             funnel["pending_count"] == len(pending) and
             set(pending) == unattempted | pending_observed,
             "PENDING_PARTITION_UNATTESTED")
    target = sorted(unattempted | {
        sym for sym, row in results.items()
        if row["status"].startswith("UNKNOWN_")
    })
    need(len(target) <= len(names), "TARGETS_OUTSIDE_WATCH_SCOPE")
    daily, weeks = expected_dates(asof)
    need(len(daily) == 260 and len(weeks) == 52 and daily[-1] == asof,
         "OFFICIAL_260_52")
    return asof, target, daily, weeks

def candidate_local_source_partition(symbols, observations):
    """Classify provider HISTORY coverage symbol-by-symbol, never alpha readiness.

    All records must come from the completed same-run SIP audit. A complete
    260-date *research* observation is not a technical R1/RR, corporate-action
    proof, market-data rights attestation or production HISTORY/PASS.
    """
    need(type(symbols) is list and symbols == sorted(set(symbols)) and
         all(type(s) is str and s for s in symbols),
         "LOCAL_PARTITION_SCOPE_INVALID")
    need(type(observations) is dict and set(observations) == set(symbols),
         "LOCAL_PARTITION_UNEXPLAINED_SYMBOL")
    ready = []
    blocked = []
    for sym in symbols:
        rec = observations[sym]
        need(type(rec) is dict and
             rec.get("canonical_primary") is False and
             type(rec.get("source_availability")) is str and
             type(rec.get("observed_official_session_count")) is int and
             0 <= rec["observed_official_session_count"] <= 260,
             "LOCAL_PARTITION_RECORD_INVALID")
        if rec["source_availability"] == "SHADOW_260_DAILY_52_WEEK_OBSERVED":
            need(rec["observed_official_session_count"] == 260,
                 "LOCAL_PARTITION_FALSE_EXACT260")
            ready.append(sym)
        else:
            blocked.append(sym)
    digest = lambda names: hashlib.sha256(
        ("\n".join(names) + "\n").encode("utf-8")).hexdigest()
    need(len(ready) + len(blocked) == len(symbols) and
         not set(ready).intersection(blocked),
         "LOCAL_PARTITION_LOST_SYMBOL")
    return {
        "research_history_source_observed_symbols": ready,
        "research_history_source_observed_count": len(ready),
        "research_history_source_observed_sha256": digest(ready),
        "research_history_source_blocked_symbols": blocked,
        "research_history_source_blocked_count": len(blocked),
        "research_history_source_blocked_sha256": digest(blocked),
        "research_source_only_not_technical_pass": True,
        "research_source_only_not_canonical_history_pass": True,
        "candidate_local_unrelated_unknown_never_vetoes_observed": True
    }


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
        "research_history_source_observed_symbols": [],
        "research_history_source_observed_count": 0,
        "research_history_source_blocked_symbols": [],
        "research_history_source_blocked_count": 0,
        "research_source_only_not_technical_pass": True,
        "research_source_only_not_canonical_history_pass": True,
        "candidate_local_unrelated_unknown_never_vetoes_observed": True,
        "provider_observed_scope_count": 0, "failed_batch_count": 0,
        "upstream_request_count": 0, "source_circuit_breaker_open": False,
        "source_rate_limited": False,
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
    """Batch-local source resilience with an exact UNKNOWN census.

    One failing group never erases successful independent-source findings.
    Stop after HTTP 429 or two consecutive failed groups; mark every
    unqueried symbol explicitly UNKNOWN. This output cannot establish any
    canonical production authority.
    """
    report = base_report(asof, symbols, source_blob)
    need(now.tzinfo is not None and sufficient_delay(asof, now),
         "20MIN_OFFICIAL_CLOSE_HOLDBACK")
    need(symbols == sorted(set(symbols)), "SORTED_EXACT_UNIQUE_SCOPE")
    start = daily[0] + "T00:00:00Z"
    end = (dt.date.fromisoformat(asof) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    result = {}
    requests = 0
    observed = 0
    failures = 0
    consecutive_failures = 0
    rate_limited = False
    circuit_open = False
    for offset in range(0, len(symbols), BATCH):
        subset = symbols[offset:offset+BATCH]
        if rate_limited or circuit_open:
            why = ("UNKNOWN_SOURCE_RATE_LIMIT_NOT_QUERIED"
                   if rate_limited else "UNKNOWN_SOURCE_CIRCUIT_OPEN_NOT_QUERIED")
            for symbol in subset:
                result[symbol] = {"source_availability": why,
                                  "observed_official_session_count": 0,
                                  "canonical_primary": False}
            continue
        requests += 1
        data = None
        failure = None
        try:
            data = fetch(subset, start, end, asof)
        except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
            code = str(exc).upper()
            if "429" in code or "RATE_LIMIT" in code:
                failure = "UNKNOWN_SOURCE_HTTP_429"
                rate_limited = True
            else:
                failure = "UNKNOWN_SOURCE_PROVIDER_BATCH_TRANSPORT"
        if failure is None and (type(data) is not dict or set(data) != set(subset)):
            failure = "UNKNOWN_SOURCE_PROVIDER_BATCH_SCOPE"
        if failure is not None:
            failures += 1
            consecutive_failures += 1
            for symbol in subset:
                result[symbol] = {"source_availability": failure,
                                  "observed_official_session_count": 0,
                                  "canonical_primary": False}
            if consecutive_failures >= 2:
                circuit_open = True
        else:
            consecutive_failures = 0
            for symbol in subset:
                try:
                    status, count = classify(data[symbol], daily, weeks, asof)
                    need(type(status) is str and
                         type(count) is int and count >= 0,
                         "SOURCE_CLASSIFICATION_SCHEMA")
                    # A syntactically present response with invalid OHLCV or
                    # timestamps is an UNKNOWN provider observation, never
                    # measured healthy history.
                    allowed = {
                        "SHADOW_260_DAILY_52_WEEK_OBSERVED",
                        "MISSING_EXACT_COMPLETED_SESSIONS",
                        "MISSING_52_COMPLETED_WEEK_CLOSES",
                        "NO_BAR",
                    }
                    if status not in allowed:
                        status, count = "UNKNOWN_SOURCE_ROW_INVALID", 0
                except (RuntimeError, ValueError, TypeError, KeyError, IndexError):
                    status, count = "UNKNOWN_SOURCE_ROW_INVALID", 0
                result[symbol] = {"source_availability": status,
                                  "observed_official_session_count": count,
                                  "canonical_primary": False}
                observed += int(status != "UNKNOWN_SOURCE_ROW_INVALID")
        del data
    report["observations"] = result
    report["classification_counts"] = dict(sorted(
        collections.Counter(r["source_availability"] for r in result.values()).items()))
    report["measured_scope_count"] = len(result)
    report["provider_observed_scope_count"] = observed
    report["failed_batch_count"] = failures
    report["upstream_request_count"] = requests
    report["source_circuit_breaker_open"] = circuit_open
    report["source_rate_limited"] = rate_limited
    report.update(candidate_local_source_partition(symbols, result))
    need(len(result) == len(symbols) and
         sum(report["classification_counts"].values()) == len(symbols) and
         observed <= len(symbols), "SOURCE_EXACT_PARTITION")
    report["status"] = (
        "UNKNOWN_SOURCE_RATE_LIMIT_PARTIAL" if rate_limited else
        "UNKNOWN_SOURCE_CIRCUIT_BREAKER_PARTIAL" if circuit_open else
        "UNKNOWN_SOURCE_PARTIAL_DATA" if any(
            name.startswith("UNKNOWN_") for name in report["classification_counts"])
        else "SHADOW_PARTIAL_HISTORY_SOURCE_NO_AUTHORITY" if
            report["research_history_source_blocked_count"] else
        "SHADOW_SOURCE_AVAILABILITY_MEASURED_NO_AUTHORITY"
    )
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
    fake["watch_radar"]["source_candidates_sha256"] = "a"*64
    fake["watch_radar"]["watchlist_digest"] = "b"*64
    fake["candidate_technical_funnel"]["source_candidates_sha256"] = "a"*64
    fake["candidate_technical_funnel"]["watchlist_digest"] = "b"*64
    a, symbols, daily, weeks = source_scope(fake, now)
    need(a == asof and symbols == ["AAA"] and daily[-1] == asof
         and len(weeks) == 52, "ONLY_ACTUAL_UNKNOWN_LOCAL")
    fake["candidate_technical_funnel"]["watchlist_digest"] = "c"*64
    try:
        source_scope(fake, now)
    except ValueError as exc:
        need("CANDIDATE_SOURCE_AND_WATCH_DIGEST_MISMATCH" in str(exc),
             "WATCH_DIGEST_DRIFT_REASON")
    else:
        raise AssertionError("WATCH_DIGEST_DRIFT_ACCEPTED")
    fake["candidate_technical_funnel"]["watchlist_digest"] = "b"*64
    # All 120 local history UNKNOWN rows must be admitted in one source audit.
    expanded = {
        "execution": "NONE", "real_money": "NO-GO", "asof_et": asof,
        "watch_radar": dict(fake["watch_radar"]),
        "candidate_technical_funnel": dict(fake["candidate_technical_funnel"])
    }
    expanded_names = ["SYM%03d" % i for i in range(120)]
    expanded["watch_radar"]["watchlist"] = [
        {"symbol": sym} for sym in expanded_names]
    expanded["watch_radar"]["watchlist_count"] = len(expanded_names)
    expanded["candidate_technical_funnel"]["candidate_count"] = len(expanded_names)
    expanded["candidate_technical_funnel"]["attempted_count"] = len(expanded_names)
    expanded["candidate_technical_funnel"]["results"] = {
        sym: {"status": "UNKNOWN_260_OFFICIAL_HISTORY"}
        for sym in expanded_names}
    need(len(source_scope(expanded, now)[1]) == 120,
         "ALL_120_UNKNOWNS_NOT_TRUNCATED")
    # Same-ASOF mixed retry cohort: history, geometry and transport errors.
    # All seven must remain independently eligible for source recovery.
    seven=["ASTS","CCC","FISV","FOXA","KYMR","TLN","TWST"]
    seven_watch={"asof_et":asof,"watchlist":[{"symbol":s} for s in seven],
       "watchlist_count":7,"watchlist_cap":None,
       "all_eligible_candidates_tracked":True,
       "source_candidates_sha256":"a"*64,"watchlist_digest":"b"*64}
    seven_funnel={"asof_et":asof,"candidate_count":7,"attempted_count":7,
       "source_candidates_sha256":"a"*64,"watchlist_digest":"b"*64,
       "results":{s:{"status":(
          "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY" if s=="TWST"
          else "UNKNOWN_260_OFFICIAL_HISTORY" if s in ("CCC","FISV")
          else "UNKNOWN_TECHNICAL_PROVIDER_OR_ENGINE")} for s in seven}}
    seven_root={"execution":"NONE","real_money":"NO-GO","asof_et":asof,
                "watch_radar":seven_watch,"candidate_technical_funnel":seven_funnel}
    need(source_scope(seven_root,now)[1]==seven,
         "MIXED_SEVEN_LOCAL_PENDING_NOT_EXACT")
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
    saved = fake["candidate_technical_funnel"]["results"].pop("BBB")
    try:
        source_scope(fake, now)
    except ValueError as exc:
        need("RESULT_PARTITION_INCOMPLETE" in str(exc), "MISSING_CANDIDATE_FAIL_CLOSED")
    else:
        raise AssertionError("UNATTEMPTED_CANDIDATE_SILENTLY_OMITTED")
    # Positive: same exact source scope, with one tracked technical
    # candidate not yet attempted. Prove explicit source pending partition
    # and include it in historical diagnostics WITHOUT any technical PASS.
    fake["candidate_technical_funnel"]["attempted_count"] = 1
    fake["candidate_technical_funnel"]["pending_count"] = 2
    fake["candidate_technical_funnel"]["pending_symbols"] = ["AAA", "BBB"]
    need(source_scope(fake, now)[1] == ["AAA", "BBB"],
         "UNATTEMPTED_PENDING_LOCAL_INCLUDED")
    # A real current source may have 475/476 attempted and exactly one
    # unattempted; the 2 other UNKNOWN rows are already in results.
    pending_attack = [
        lambda f: f.update(pending_symbols=["AAA"]),
        lambda f: f.update(pending_symbols=["AAA", "BBB", "BBB"]),
        lambda f: f.update(pending_count=1),
        lambda f: f.update(attempted_count=2),
        lambda f: f.update(pending_symbols=["AAA", "CCC"],pending_count=2),
        lambda f: f.update(pending_symbols=["BBB"],pending_count=1),
    ]
    from copy import deepcopy
    for index, mutate in enumerate(pending_attack):
        altered = deepcopy(fake)
        mutate(altered["candidate_technical_funnel"])
        try:
            source_scope(altered, now)
        except ValueError:
            continue
        raise AssertionError("UNATTESTED_PARTIAL_SOURCE_ACCEPTED_" + str(index))
    fake["candidate_technical_funnel"]["results"]["BBB"] = saved
    fake["candidate_technical_funnel"]["attempted_count"] = 2
    fake["candidate_technical_funnel"].pop("pending_symbols")
    fake["candidate_technical_funnel"].pop("pending_count")
    fake["asof_et"] = "2026-10-12"
    try:
        source_scope(fake, now)
    except ValueError:
        pass
    else:
        raise AssertionError("MISMATCHED_ASOF_ACCEPTED")
    need(classify([], daily, weeks, asof)[0] == "NO_BAR",
         "MISSING_SIP_CANNOT_PASS")
    # A single 260-session gap must not erase unrelated good source coverage.
    test_scope = ["BSP", "CCC", "FISV", "TWST"]
    test_rows = {
        sym: {"source_availability":
              ("MISSING_EXACT_COMPLETED_SESSIONS" if sym == "BSP"
               else "SHADOW_260_DAILY_52_WEEK_OBSERVED"),
              "observed_official_session_count": (259 if sym == "BSP" else 260),
              "canonical_primary": False}
        for sym in test_scope}
    partition = candidate_local_source_partition(test_scope, test_rows)
    need(partition["research_history_source_observed_symbols"] ==
         ["CCC", "FISV", "TWST"] and
         partition["research_history_source_blocked_symbols"] == ["BSP"] and
         partition["research_source_only_not_technical_pass"] is True and
         partition["research_history_source_observed_count"] == 3,
         "BSP_GAP_MUST_NOT_BLOCK_THREE_INDEPENDENT_SYMBOLS")
    for failure in ("INCOMPLETE_COUNTS", "CANONICAL_LEAK",
                    "FOREIGN_SCOPE", "DUPLICATE_SCOPE"):
        clone = {s: dict(v) for s, v in test_rows.items()}
        scope = list(test_scope)
        if failure == "INCOMPLETE_COUNTS":
            clone["CCC"]["observed_official_session_count"] = 259
        elif failure == "CANONICAL_LEAK":
            clone["TWST"]["canonical_primary"] = True
        elif failure == "FOREIGN_SCOPE":
            clone["NEW"] = dict(clone["BSP"])
        else:
            scope[0] = scope[1]
        try:
            candidate_local_source_partition(scope, clone)
        except ValueError:
            pass
        else:
            raise AssertionError("LOCAL_SOURCE_NEGATIVE_ACCEPTED_" + failure)
    cohort = ["SYM%03d" % i for i in range(BATCH+1)]
    calls = []
    def one_failure(sub, begin, finish, session):
        calls.append(tuple(sub))
        if len(calls) == 1:
            raise RuntimeError("ALPACA_HTTP_503_TRANSIENT")
        return {sym: [] for sym in sub}
    partial = audit(asof, cohort, daily, weeks, "a"*40,
                    one_failure, now)
    need(len(calls) == 2
         and partial["failed_batch_count"] == 1
         and partial["upstream_request_count"] == 2
         and partial["measured_scope_count"] == len(cohort)
         and partial["classification_counts"]["UNKNOWN_SOURCE_PROVIDER_BATCH_TRANSPORT"] == BATCH
         and partial["classification_counts"]["NO_BAR"] == 1
         and partial["status"] == "UNKNOWN_SOURCE_PARTIAL_DATA",
         "ONE_FAILED_BATCH_MUST_NOT_ERASE_OTHER_BATCH")
    calls.clear()
    def all_limited(sub, begin, finish, session):
        calls.append(tuple(sub))
        raise RuntimeError("ALPACA_HTTP_429_TOO_MANY_REQUESTS")
    limited = audit(asof, cohort, daily, weeks, "a"*40,
                    all_limited, now)
    need(len(calls) == 1 and limited["source_rate_limited"]
         and limited["failed_batch_count"] == 1
         and limited["classification_counts"]["UNKNOWN_SOURCE_HTTP_429"] == BATCH
         and limited["classification_counts"]["UNKNOWN_SOURCE_RATE_LIMIT_NOT_QUERIED"] == 1
         and limited["status"] == "UNKNOWN_SOURCE_RATE_LIMIT_PARTIAL",
         "HTTP_429_MUST_HALT_FURTHER_VENDOR_CALLS")
    huge = ["SYM%03d" % i for i in range(BATCH*2+1)]
    calls.clear()
    def transient_outage(sub, begin, finish, session):
        calls.append(tuple(sub))
        raise RuntimeError("ALPACA_HTTP_503")
    cliff = audit(asof, huge, daily, weeks, "a"*40,
                  transient_outage, now)
    need(len(calls) == 2 and cliff["source_circuit_breaker_open"]
         and cliff["failed_batch_count"] == 2
         and cliff["measured_scope_count"] == len(huge)
         and cliff["classification_counts"]["UNKNOWN_SOURCE_CIRCUIT_OPEN_NOT_QUERIED"] == 1
         and cliff["status"] == "UNKNOWN_SOURCE_CIRCUIT_BREAKER_PARTIAL",
         "UPSTREAM_CLIFF_MUST_STOP_WITH_EXACT_UNQUERIED_SET")
    def injected_foreign(sub, begin, finish, session):
        return {**{sym: [] for sym in sub}, "FOREIGN": []}
    foreign = audit(asof, ["SYM000"], daily, weeks, "a"*40,
                    injected_foreign, now)
    need(foreign["observations"]["SYM000"]["source_availability"] ==
         "UNKNOWN_SOURCE_PROVIDER_BATCH_SCOPE",
         "FOREIGN_SYMBOL_MUST_NEVER_BE_ACCEPTED")
    def malformed_rows(sub, begin, finish, session):
        return {sym: "THIS_IS_NOT_OHLCV" for sym in sub}
    malformed = audit(asof, ["SYM000"], daily, weeks, "a"*40,
                      malformed_rows, now)
    need(malformed["observations"]["SYM000"]["source_availability"] ==
         "UNKNOWN_SOURCE_ROW_INVALID"
         and malformed["status"] == "UNKNOWN_SOURCE_PARTIAL_DATA",
         "MALFORMED_BAR_MUST_NEVER_LOOK_LIKE_COMPLETE_SOURCE")
    print("XRAY_CANDIDATE_LOCAL_SIP_RECOVERY_SELFTEST=PASS_EXACT_PENDING_UNATTEMPTED_6_NEGATIVES_NO_PRIMARY_R92")

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
    candidate_bytes = (ROOT / "sina_candidates.json").read_bytes()
    expected_sha = (root.get("watch_radar") or {}).get("source_candidates_sha256")
    need(hashlib.sha256(candidate_bytes).hexdigest() == expected_sha,
         "CANONICAL_CANDIDATE_FILE_NOT_BOUND_TO_TECHNICAL_SOURCE")
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
