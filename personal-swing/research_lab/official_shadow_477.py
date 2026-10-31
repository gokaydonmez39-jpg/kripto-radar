#!/usr/bin/env python3
"""XRAY 477 official-source research shadow: no HTTP, AL, alerts or writes.

Consumes the already-private verified EOD snapshot and an independently built,
possibly stale Nasdaq safety witness. SEC/Alpaca corporate-action PER-SYMBOL
coverage is deliberately UNKNOWN until separately evidenced. Never market-clear.
The CLI writes only an isolated local JSON witness, not a production sheet.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

PERSONAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERSONAL))
import handoff_guard
import runner

SCHEMA = "XRAY_NASDAQ_477_OFFICIAL_SHADOW_V1"
STATUS = "RESEARCH_SHADOW_ONLY_NO_AUTHORITY"

class ShadowRejected(ValueError):
    pass

def demand(ok, message):
    if not ok:
        raise ShadowRejected(message)

def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")

def sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def strict_instant(value):
    demand(type(value) is str and len(value) <= 40, "INVALID_OBSERVATION_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShadowRejected("INVALID_OBSERVATION_TIME") from None
    demand(stamp.tzinfo is not None, "NAIVE_OBSERVATION_TIME")
    return stamp.astimezone(timezone.utc)

def cutoff_for_session(day):
    # Must use the same XNAS session calendar as the existing EOD engine.
    import exchange_calendars as xc
    try:
        calendar = xc.get_calendar("XNAS")
        close = calendar.session_close(day).to_pydatetime()
    except (ValueError, KeyError, TypeError):
        raise ShadowRejected("INVALID_XNAS_SESSION") from None
    return close.astimezone(timezone.utc) + timedelta(minutes=45)

def exact_symbols(document):
    demand(type(document) is dict and type(document.get("source_count")) is int
           and document["source_count"] == 477, "WATCHLIST_COUNT_INVALID")
    symbols = document.get("liquidity_watch_symbols")
    demand(type(symbols) is list and len(symbols) == 477
           and len(set(symbols)) == 477 and
           all(type(s) is str and s.isascii() and s.isupper() and
               len(s) <= 15 for s in symbols), "WATCHLIST_SCOPE_INVALID")
    return symbols

def validate_safety_witness(witness):
    demand(type(witness) is dict, "OFFICIAL_GUARD_NOT_OBJECT")
    demand(witness.get("status") == "PASS" and
           witness.get("alpha_authority") is False and
           witness.get("execution") == "NONE" and
           witness.get("real_money") == "NO-GO",
           "OFFICIAL_GUARD_AUTHORITY_OR_STATUS_INVALID")
    safety = witness.get("candidate_safety")
    demand(type(safety) is dict and
           safety.get("halt_guard_status") == "PASS" and
           safety.get("security_status_guard_status") == "PASS",
           "OFFICIAL_GUARD_FEEDS_UNVERIFIED")
    sets = []
    for key in ("active_halt_symbols", "security_status_suspension_symbols",
                "veto_symbols"):
        values = safety.get(key)
        demand(type(values) is list and len(values) == len(set(values)) and
               all(type(s) is str and s and s.isascii() and s.isupper()
                   for s in values), "OFFICIAL_GUARD_SYMBOLS_INVALID")
        sets.append(set(values))
    demand(sets[2] == sets[0] | sets[1], "OFFICIAL_GUARD_VETO_UNION_DRIFT")
    return sets[2]

def make_shadow(snapshot, watchlist, guard):
    """No side effects. Source absence is UNKNOWN, never explicit no-risk."""
    symbols = exact_symbols(watchlist)
    before = sha(snapshot)
    # Reuse *production* handoff contract, never relax scope or AL rules.
    try:
        handoff_guard.validate_snapshot(
            snapshot, symbols, scope_sha=runner.sha_symbols(symbols),
            policy_sha=runner.analysis_fingerprint())
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise ShadowRejected("EOD_HANDOFF_REFUSED_"+type(exc).__name__) from None
    cutoff = cutoff_for_session(snapshot["asof_et"])
    veto = validate_safety_witness(guard)
    seen = strict_instant(guard.get("generated_at_utc"))
    if seen > cutoff:
        feed_state = "UNKNOWN_SOURCE_AFTER_EOD_CUTOFF"
    elif cutoff - seen > timedelta(hours=24):
        feed_state = "UNKNOWN_SOURCE_TOO_OLD"
    else:
        feed_state = "OBSERVED_CURRENT_SAFETY_WITNESS_REVIEW_ONLY"

    rows = []
    observed = 0
    for symbol in symbols:
        in_veto = symbol in veto and feed_state.startswith("OBSERVED_")
        observed += int(in_veto)
        rows.append({
            "symbol": symbol,
            "nasdaq": ("OBSERVED_VETO_REQUIRES_REVIEW" if in_veto else
                       "UNKNOWN_NOT_A_MARKET_CLEARANCE"),
            "sec": "UNKNOWN_NOT_477_PIT_PROVEN",
            "alpaca_corporate_actions": "UNKNOWN_NO_PER_SYMBOL_TIMELY_LEDGER",
            "market_cleared": False,
            "may_change_al": False,
            "may_change_stop_or_target": False,
            "may_notify": False,
            "may_place_order": False,
            "may_write_sheet": False,
        })
    demand(len(rows) == 477 and len({r["symbol"] for r in rows}) == 477,
           "SHADOW_SCOPE_DRIFT")
    demand(sha(snapshot) == before, "SOURCE_SNAPSHOT_MUTATED")
    return {
        "schema": SCHEMA, "status": STATUS,
        "asof_et": snapshot["asof_et"],
        "decision_cutoff_utc": cutoff.isoformat(),
        "source_observed_at_utc": seen.isoformat(),
        "nasdaq_source_state": feed_state,
        "scope_sha256": runner.sha_symbols(symbols),
        "analysis_fingerprint_sha256": runner.analysis_fingerprint(),
        "private_eod_snapshot_sha256": before,
        "nasdaq_witness_sha256": sha(guard),
        "rows_count": 477,
        "nasdaq_veto_events_observed": observed,
        "nasdaq_unknown": 477 - observed,
        "sec_unknown": 477,
        "corporate_actions_unknown": 477,
        "rows": rows,
        "market_clearance_proven": False,
        "historical_pit_proven": False,
        "first_public_availability_proven": False,
        "may_modify_al": False,
        "may_write_sheet": False,
        "may_notify": False,
        "may_place_order": False,
        "no_network_calls": True,
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--guard", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        snap_path = Path(args.snapshot)
        if not snap_path.is_file():
            print(json.dumps({"status":"SKIPPED_NO_COMPLETED_SCAN",
                              "rows_count":0,"market_clearance_proven":False}))
            return 0
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        watch = json.loads(Path(args.watchlist).read_text(encoding="utf-8"))
        guard = json.loads(Path(args.guard).read_text(encoding="utf-8"))
        result = make_shadow(snap, watch, guard)
        out = Path(args.out)
        demand(out.resolve() != snap_path.resolve(),
               "SHADOW_MUST_NOT_OVERWRITE_EOD")
        demand(out.resolve() not in {Path(args.watchlist).resolve(),
                                    Path(args.guard).resolve()},
               "SHADOW_MUST_NOT_OVERWRITE_SOURCE")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Only the local caller controls this private path; never commit it.
        tmp = out.with_suffix(out.suffix+".tmp")
        tmp.write_text(json.dumps(result, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(tmp, out)
        print(json.dumps({
            "status":result["status"],"rows_count":477,
            "nasdaq_source_state":result["nasdaq_source_state"],
            "nasdaq_veto_events_observed":result["nasdaq_veto_events_observed"],
            "sec_unknown":477,"corporate_actions_unknown":477,
            "market_clearance_proven":False,"may_modify_al":False,
            "private_ledger_sha256":sha(result),
        },sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            ArithmeticError) as exc:
        print(json.dumps({"status":"SHADOW_REFUSED",
                          "reason_type":type(exc).__name__,
                          "market_clearance_proven":False,
                          "may_modify_al":False},sort_keys=True))
        return 4

if __name__ == "__main__":
    sys.exit(main())
