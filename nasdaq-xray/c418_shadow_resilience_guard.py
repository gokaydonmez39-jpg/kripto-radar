#!/usr/bin/env python3
"""C4.18 advisory failover + point-in-time backtest guards.

No network, raw bars, credentials, mutation, PRIMARY, R92 or live orders.
A routable SHADOW candidate is NOT an approved unattended data entitlement.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

SCHEMA = "XRAY_C418_SHADOW_RESILIENCE_GUARD_V1"
PURPOSES = {
    "MC": ("Bigdata", "Massive"),
    "HISTORY": ("Alpaca", "Rallies", "Massive"),
    "PRICE": ("Alpaca", "Rallies", "Massive"),
}
FAIL_CLOSED = {
    "schema": SCHEMA, "activation": "INACTIVE_RESEARCH_ONLY",
    "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True,
    "production_authority": False, "can_create_PRIMARY": False,
    "can_create_HISTORY_PASS": False, "can_register_R92": False,
    "calls_performed": 0, "vendor_raw_data_exported": False,
}

def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp_missing")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timezone_missing")
    return stamp.astimezone(timezone.utc)

def _latest_completed_nasdaq_session(now):
    """Calendar-certified market close plus >=20min SIP holdback. No day guess."""
    import pandas_market_calendars as mcal
    calendar = mcal.get_calendar("NASDAQ")
    schedule = calendar.schedule(
        start_date=(now.date() - timedelta(days=14)).isoformat(),
        end_date=now.date().isoformat(),
    )
    for idx, session in schedule.iloc[::-1].iterrows():
        close = session["market_close"].to_pydatetime()
        if close.tzinfo is None:
            raise ValueError("unverified_session_timezone")
        if now >= close.astimezone(timezone.utc) + timedelta(minutes=20):
            return idx.date().isoformat()
    raise ValueError("no_settled_session")

def advisory_route(profile: dict, state: dict, purpose: str, asof: str,
                   now_utc: str) -> dict:
    """Pure selection for later human/legal review, NEVER actual provider calls."""
    report = dict(FAIL_CLOSED, purpose=purpose, asof_et=asof,
                  status="DATA_BLOCKED", advisory_order=[], reasons={})
    if (not isinstance(profile, dict)
        or profile.get("schema") != "XRAY_C418_MULTI_SOURCE_PROFILE_V1"
        or profile.get("activation") != "INACTIVE_RESEARCH_ONLY"
        or profile.get("effective_policy") != "C4.17"
        or profile.get("unknown_never_pass") is not True
        or purpose not in PURPOSES):
        return dict(report, reasons={"GLOBAL": "PROFILE_OR_PURPOSE_UNSAFE"})
    try:
        now = _timestamp(now_utc)
        parsed = date.fromisoformat(asof)
        if parsed.isoformat() != asof:
            raise ValueError("asof_noncanonical")
    except (ValueError, TypeError):
        return dict(report, reasons={"GLOBAL": "DATE_OR_CLOCK_INVALID"})
    try:
        latest = _latest_completed_nasdaq_session(now)
    except (ValueError, TypeError, AttributeError, ImportError, KeyError, OverflowError):
        return dict(report, reasons={"GLOBAL": "OFFICIAL_NASDAQ_SESSION_CLOCK_UNAVAILABLE"})
    if asof != latest:
        return dict(report, reasons={"GLOBAL": "ASOF_NOT_LATEST_SETTLED_NASDAQ_SESSION"})
    if not isinstance(state, dict):
        return dict(report, reasons={"GLOBAL": "NO_PROVIDER_HEALTH"})
    for name in PURPOSES[purpose]:
        source = profile.get("sources", {}).get(name)
        health = state.get(name)
        reason = "UNKNOWN_HEALTH"
        if not isinstance(source, dict) or source.get("production_eligible") is not False:
            reason = "SOURCE_PROFILE_ROLE_TAMPERED"
        elif not isinstance(health, dict):
            reason = "UNKNOWN_HEALTH"
        elif health.get("asof_et") != asof:
            reason = "STALE_SOURCE_ASOF"
        else:
            try:
                sampled_at = _timestamp(health.get("observed_at_utc"))
                if sampled_at > now or (now - sampled_at).total_seconds() > 3600:
                    reason = "HEALTH_TIMESTAMP_STALE_OR_FUTURE"
                elif health.get("status") in {"CREDIT_EXHAUSTED", "AUTH_DENIED"}:
                    reason = "CREDIT_OR_ACCESS_BLOCKED_NO_PAID_FALLBACK"
                elif health.get("status") == "RATE_LIMITED":
                    reason = "RATE_LIMITED_DO_NOT_CALL"
                elif health.get("status") != "HEALTHY":
                    reason = "PROVIDER_UNAVAILABLE_OR_UNKNOWN"
                elif type(health.get("remaining_credits")) is not int or health["remaining_credits"] <= 0:
                    reason = "NO_VERIFIED_POSITIVE_CREDIT_QUOTA"
                elif type(health.get("consecutive_failures")) is not int or health["consecutive_failures"] < 0:
                    reason = "INVALID_CIRCUIT_STATE"
                elif health["consecutive_failures"] >= 2 and (
                    not health.get("circuit_reset_after_utc") or
                    _timestamp(health["circuit_reset_after_utc"]) > now
                ):
                    reason = "CIRCUIT_OPEN"
                elif health.get("runner_callable") is not True:
                    reason = "UNATTENDED_RUNNER_NOT_PROVEN"
                elif health.get("private_rights_scope_verified") is not True:
                    reason = "AUTOMATED_NONDISPLAY_RETENTION_RIGHTS_UNVERIFIED"
                elif health.get("upstream_feed_verified") is not True:
                    reason = "UPSTREAM_FEED_NOT_VERIFIED"
                else:
                    reason = "SHADOW_CANDIDATE_REQUIRES_EXTERNAL_LEGAL_AND_SOURCE_REVIEW"
                    report["advisory_order"].append(name)
            except (ValueError, TypeError, OverflowError):
                reason = "MALFORMED_PROVIDER_TIME"
        report["reasons"][name] = reason
    if report["advisory_order"]:
        report["status"] = "ADVISORY_ROUTE_ONLY_NO_FETCH_NO_PRIMARY"
    return report

def backtest_pit_guard(evidence: dict) -> dict:
    """Structural PIT checks do not authorize a live/production backtest."""
    result = dict(FAIL_CLOSED, status="BACKTEST_DATA_BLOCKED", reason_codes=[])
    if not isinstance(evidence, dict):
        result["reason_codes"] = ["MISSING_PIT_EVIDENCE"]
        return result
    try:
        decision = _timestamp(evidence["decision_at_utc"])
        required = (
            "features_available_at_utc", "identity_available_at_utc",
            "membership_available_at_utc", "corporate_actions_available_at_utc",
        )
        for key in required:
            if _timestamp(evidence[key]) > decision:
                result["reason_codes"].append("FUTURE_INFORMATION_" + key)
    except (KeyError, ValueError, TypeError, OverflowError):
        result["reason_codes"].append("PIT_TIMESTAMPS_INVALID")
    for key in (
        "full_historical_universe_including_delisted_verified",
        "ticker_cik_class_continuity_verified", "raw_vs_adjusted_basis_verified",
        "splits_dividends_pit_verified", "next_session_execution_model_verified",
        "commissions_spread_slippage_model_verified", "benchmark_verified",
        "out_of_sample_walk_forward_defined", "provider_backtest_rights_verified",
    ):
        if evidence.get(key) is not True:
            result["reason_codes"].append("UNPROVEN_" + key.upper())
    if not result["reason_codes"]:
        result["status"] = "PIT_STRUCTURE_REVIEW_ONLY_NOT_A_LIVE_BACKTEST"
        result["reason_codes"] = ["INDEPENDENT_SOURCE_AND_REAL_DATA_REPLAY_STILL_REQUIRED"]
    return result

def selftest():
    profile = {"schema": "XRAY_C418_MULTI_SOURCE_PROFILE_V1",
               "activation": "INACTIVE_RESEARCH_ONLY", "effective_policy": "C4.17",
               "unknown_never_pass": True,
               "sources": {n: {"production_eligible": False}
                           for vals in PURPOSES.values() for n in vals}}
    now = "2026-10-11T11:00:00Z"
    template = {"asof_et": "2026-10-09", "observed_at_utc": "2026-10-11T10:30:00Z",
                "status": "HEALTHY", "remaining_credits": 20,
                "consecutive_failures": 0, "runner_callable": True,
                "private_rights_scope_verified": True,
                "upstream_feed_verified": True}
    routes = {name: dict(template) for name in PURPOSES["HISTORY"]}
    valid = advisory_route(profile, routes, "HISTORY", "2026-10-09", now)
    assert valid["advisory_order"] == list(PURPOSES["HISTORY"])
    assert valid["can_create_PRIMARY"] is False and valid["can_register_R92"] is False
    assert advisory_route(profile, routes, "HISTORY", "2026-10-12", now)["reasons"] == {"GLOBAL": "ASOF_NOT_LATEST_SETTLED_NASDAQ_SESSION"}
    assert advisory_route(profile, routes, "HISTORY", "2026-10-08", now)["reasons"] == {"GLOBAL": "ASOF_NOT_LATEST_SETTLED_NASDAQ_SESSION"}
    assert advisory_route(profile, routes, "HISTORY", "2026-10-10", now)["reasons"] == {"GLOBAL": "ASOF_NOT_LATEST_SETTLED_NASDAQ_SESSION"}
    early = "2026-10-12T19:45:00Z"
    early_routes = {name: dict(template, observed_at_utc="2026-10-12T19:30:00Z")
                    for name in PURPOSES["HISTORY"]}
    assert advisory_route(profile, early_routes, "HISTORY", "2026-10-09", early)["advisory_order"] == list(PURPOSES["HISTORY"])
    settled = "2026-10-12T20:30:00Z"
    assert advisory_route(profile, early_routes, "HISTORY", "2026-10-09", settled)["reasons"] == {"GLOBAL": "ASOF_NOT_LATEST_SETTLED_NASDAQ_SESSION"}
    assert advisory_route(profile, routes, "HISTORY", "invalid-date", now)["reasons"] == {"GLOBAL": "DATE_OR_CLOCK_INVALID"}
    import copy
    negatives = [
        ("NO_HEALTH", lambda x: x.pop("Alpaca"), "UNKNOWN_HEALTH"),
        ("CREDIT", lambda x: x["Alpaca"].update(remaining_credits=0), "NO_VERIFIED_POSITIVE_CREDIT_QUOTA"),
        ("OUT_OF_CREDIT", lambda x: x["Alpaca"].update(status="CREDIT_EXHAUSTED"), "CREDIT_OR_ACCESS_BLOCKED_NO_PAID_FALLBACK"),
        ("RATE", lambda x: x["Alpaca"].update(status="RATE_LIMITED"), "RATE_LIMITED_DO_NOT_CALL"),
        ("CIRCUIT", lambda x: x["Alpaca"].update(consecutive_failures=2), "CIRCUIT_OPEN"),
        ("ASOF", lambda x: x["Alpaca"].update(asof_et="2026-10-08"), "STALE_SOURCE_ASOF"),
        ("FUTURE", lambda x: x["Alpaca"].update(observed_at_utc="2026-10-11T12:00:00Z"), "HEALTH_TIMESTAMP_STALE_OR_FUTURE"),
        ("RIGHTS", lambda x: x["Alpaca"].update(private_rights_scope_verified=False), "AUTOMATED_NONDISPLAY_RETENTION_RIGHTS_UNVERIFIED"),
        ("RUNNER", lambda x: x["Alpaca"].update(runner_callable=False), "UNATTENDED_RUNNER_NOT_PROVEN"),
        ("FEED", lambda x: x["Alpaca"].update(upstream_feed_verified=False), "UPSTREAM_FEED_NOT_VERIFIED"),
        ("BAD_CREDIT", lambda x: x["Alpaca"].update(remaining_credits=True), "NO_VERIFIED_POSITIVE_CREDIT_QUOTA"),
        ("BAD_CIRCUIT_TIME", lambda x: x["Alpaca"].update(consecutive_failures=2, circuit_reset_after_utc="BAD"), "MALFORMED_PROVIDER_TIME"),
    ]
    for case, change, expected in negatives:
        x = copy.deepcopy(routes)
        change(x)
        output = advisory_route(profile, x, "HISTORY", "2026-10-09", now)
        assert output["reasons"]["Alpaca"] == expected, (case, output)
        assert "Alpaca" not in output["advisory_order"], (case, output)
        assert output["can_create_PRIMARY"] is False and output["can_register_R92"] is False
    pit = backtest_pit_guard(None)
    assert pit["status"] == "BACKTEST_DATA_BLOCKED"
    defaults = {"decision_at_utc": "2026-10-09T20:15:00Z",
                "features_available_at_utc": "2026-10-09T20:14:00Z",
                "identity_available_at_utc": "2026-10-09T19:00:00Z",
                "membership_available_at_utc": "2026-10-09T19:00:00Z",
                "corporate_actions_available_at_utc": "2026-10-09T19:00:00Z"}
    fields = (
        "full_historical_universe_including_delisted_verified",
        "ticker_cik_class_continuity_verified", "raw_vs_adjusted_basis_verified",
        "splits_dividends_pit_verified", "next_session_execution_model_verified",
        "commissions_spread_slippage_model_verified", "benchmark_verified",
        "out_of_sample_walk_forward_defined", "provider_backtest_rights_verified",
    )
    defaults.update({name: True for name in fields})
    assert backtest_pit_guard(defaults)["status"] == "PIT_STRUCTURE_REVIEW_ONLY_NOT_A_LIVE_BACKTEST"
    for field in fields:
        x = dict(defaults, **{field: False})
        assert backtest_pit_guard(x)["status"] == "BACKTEST_DATA_BLOCKED", field
    x = dict(defaults, features_available_at_utc="2026-10-10T20:00:00Z")
    assert "FUTURE_INFORMATION_features_available_at_utc" in backtest_pit_guard(x)["reason_codes"]
    print("XRAY_C418_SHADOW_RESILIENCE_SELFTEST=PASS_12_NEGATIVE_6_SETTLEMENT_PLUS_9_PIT_GATES_NO_PRIMARY_NO_R92")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--private-health", type=Path)
    parser.add_argument("--purpose", choices=tuple(PURPOSES), default="HISTORY")
    parser.add_argument("--asof", default="2026-10-09")
    parser.add_argument("--clock-utc")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.profile or not args.private_health or not args.clock_utc:
        print(json.dumps(dict(FAIL_CLOSED, status="DATA_BLOCKED",
                              reason_codes=["NO_PRIVATE_HEALTH_AND_RIGHTS_EVIDENCE"]), sort_keys=True))
        raise SystemExit(2)
    repo_dir = Path(__file__).resolve().parent.parent
    if args.private_health.resolve().is_relative_to(repo_dir):
        raise SystemExit("PRIVATE_HEALTH_MUST_STAY_OUTSIDE_PUBLIC_REPOSITORY")
    result = advisory_route(json.loads(args.profile.read_text()),
                            json.loads(args.private_health.read_text()), args.purpose,
                            args.asof, args.clock_utc)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2)

if __name__ == "__main__":
    main()
