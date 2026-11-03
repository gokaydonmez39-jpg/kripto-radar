#!/usr/bin/env python3
"""XRAY Ω personal 477 closed-loop Guardian.

A second, independent post-EOD private Sheets readback: candidate identities,
immutable 2R levels, AL event keys, suppression, lifecycle bounds, source
provenance and derived PANEL. This does NOT read market bars, submit orders,
send messages, inspect iOS notifications, or authorize canonical R92.

Automated repair is restricted to the already-tested PANEL reconciler, once,
after all source/AL/event gates pass; ambiguous event writes are NEVER replayed.
The only public receipt is a redacted aggregate. No symbol, price, private
spreadsheet ID, credential, or Sheet row may appear in logs/artifacts.
"""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

import alert_ledger_contract as lc
import panel_reconciler as panel
import private_sheet_writer as sheets
from daily_job import current_completed_session

SCHEMA = "XRAY_PERSONAL_GUARDIAN_V1"
EVENT_RUN = re.compile(
    r"^https://github[.]com/gokaydonmez39-jpg/kripto-radar/actions/runs/[0-9]+$")
FOLLOWUP_STATES = frozenset(
    (lc.CONFIRMED_PENDING, lc.REQUESTED, lc.UNKNOWN, lc.ACKED))
PANEL_REPAIR_BUDGET = 1


class GuardianHold(ValueError):
    """Controlled fail-close reason; never include user or provider values."""


def need(condition, code):
    if not condition:
        raise GuardianHold(code)


def price(value):
    x = sheets.numeric(value)
    need(0 < x < 1_000_000 and x == x, "INVALID_IMMUTABLE_PRICE")
    return x


def same_price(a, b):
    # Existing Sheet rows sometimes preserve 2 decimals instead of 3.
    # No drift of >= 1 cent can pass this tolerance.
    return abs(price(a) - price(b)) <= 0.00501


def evaluate(candidates, scans, alerts, dashboard, expected_asof,
             *, expected_run_id=None):
    """Side-effect-free evidence gate; no user-facing AL or delivery claim."""
    need(isinstance(expected_asof, str)
         and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", expected_asof),
         "EXPECTED_ASOF_INVALID")
    try:
        need(date.fromisoformat(expected_asof).isoformat() == expected_asof,
             "EXPECTED_ASOF_INVALID")
    except ValueError as exc:
        raise GuardianHold("EXPECTED_ASOF_INVALID") from exc

    rows = sheets.rows_only(candidates, sheets.CANDIDATE_HEADER)
    days = sheets.rows_only(scans, sheets.SCAN_HEADER)
    events = lc.parse_ledger(alerts)
    need(days and len({r[0] for r in days}) == len(days),
         "SCAN_MISSING_OR_DUPLICATE")
    ordered = [d[0] for d in days]
    need(ordered == sorted(ordered), "SCAN_ORDER_DRIFT")
    s = days[-1]
    need(len(s) >= 10 and s[0] == expected_asof,
         "LATEST_SCAN_ASOF_NOT_ACCEPTED")
    need([sheets.numeric(s[i]) for i in (2, 3, 4, 5)] ==
         [477., 477., 477., 0.], "SCOPE_OR_COVERAGE_DRIFT")
    need(str(s[6]).upper() == "TRUE", "FINAL_READY_FALSE")
    need(sheets.numeric(s[7]).is_integer()
         and 0 <= sheets.numeric(s[7]) <= 477, "AL_COUNT_INVALID")
    need(EVENT_RUN.fullmatch(str(s[8])) is not None, "UNTRUSTED_RUN_PROOF")
    sheets.scan_source_proof(s[9])
    need(len({r[0] for r in rows}) == len(rows),
         "CANDIDATE_KEY_DUPLICATE")

    same_day = [r for r in rows if len(r) > 2 and r[1] == expected_asof]
    need(len(same_day) == int(sheets.numeric(s[7])),
         "AL_COUNT_VS_CANDIDATE_ROWS")
    need(all(len(r) >= 8 and
             r[0] == f"{r[1]}|{r[2]}" and
             lc.TICKER.fullmatch(str(r[2])) and
             r[1] <= expected_asof
             for r in rows), "CANDIDATE_IDENTITY_DRIFT")
    need(all(str(r[7]).startswith(("AÇIK • ", "KAPALI • "))
             for r in rows), "CANDIDATE_LIFECYCLE_UNKNOWN")
    for r in rows:
        levels = [price(r[i]) for i in (4, 5, 6)]
        need(levels[1] < levels[0] < levels[2],
             "IMMUTABLE_PRICE_ORDER")
        need(abs((levels[2]-levels[0]) - 2*(levels[0]-levels[1])) <= 0.011,
             "IMMUTABLE_RR_NOT_2R")
        match = re.search(r"(\d+)/15 SEANS", str(r[7]))
        need(match is not None and 0 <= int(match.group(1)) <= 15,
             "LIFECYCLE_15_SESSION_BOUNDS")

    pending = 0
    suppressed = 0
    for r in same_day:
        asof, symbol = r[1], r[2]
        key = lc.event_key(asof, symbol, asof, "AL_NEW_EPISODE", 1)
        e = events.get(key)
        need(e is not None, "AL_OUTBOX_EVENT_MISSING")
        prev_open = any(
            old[2] == symbol and old[1] < asof and
            str(old[7]).startswith("AÇIK")
            for old in rows)
        allowed = {lc.SUPPRESSED} if prev_open else FOLLOWUP_STATES
        need(e["status"] in allowed, "AL_OUTBOX_SUPPRESSION_OR_STATE_DRIFT")
        erow = e["row"]
        need(len(erow) >= 18 and erow[1] == r[0]
             and all(same_price(erow[7+i], r[4+i]) for i in range(3)),
             "AL_OUTBOX_IMMUTABLE_LEVEL_DRIFT")
        pending += int(e["status"] == lc.CONFIRMED_PENDING)
        suppressed += int(e["status"] == lc.SUPPRESSED)

    # Independently compute existing versioned PANEL cells. A stale PANEL is
    # the only permitted automatic mutation, after every source gate passes.
    p = panel.plan(dashboard, candidates, scans)
    need(p["asof_et"] == expected_asof, "PANEL_SOURCE_ASOF_DRIFT")
    existing_run = s[8].rsplit("/", 1)[-1]
    if expected_run_id is not None:
        need(str(expected_run_id).isdigit(), "EXPECTED_RUN_ID_INVALID")
    replay = expected_run_id is not None and existing_run != str(expected_run_id)
    return {
        "schema": SCHEMA,
        "status": "PERSONAL_EOD_AND_AL_LEDGER_VERIFIED",
        "asof_et": expected_asof,
        "source_run_same": not replay,
        "valid_symbols": 477,
        "new_technical_al": len(same_day),
        "alarm_ledger_events": len(events),
        "pending_new_al": pending,
        "suppressed_new_al": suppressed,
        "panel_drift_rows": len(p["changes"]),
        "repair": "PANEL_ONLY_ONCE" if p["changes"] else "NONE",
        "personal_research_start": "PASS",
        "premium_task_emission": "UNVERIFIED",
        "iphone_device_ack": "UNKNOWN",
        "canonical_full_final": "NO-GO",
        "trading_execution": "NONE",
        "real_money": "NO-GO",
        "full_autonomous_start": "HOLD"
    }


def snapshot(api):
    # Self-heal bounded READ-ONLY transient Google errors. Do not retry any
    # ambiguous append/update, and never re-send an event on a timeout.
    for attempt in range(2):
        try:
            api.check_metadata()
            return (
                api.read("ADAY_GECMISI", "M"),
                api.read("TARAMA_KAYITLARI", "J"),
                api.read("UYARI_OLAYLARI", "T"),
                api.read("PANEL", "C"),
            )
        except sheets.HandoffBlocked:
            if attempt:
                raise
    raise GuardianHold("PROVIDER_READ_RETRY_EXHAUSTED")


def run(api, expected_asof, *, expected_run_id=None, panel_repair=True):
    before = snapshot(api)
    result = evaluate(*before, expected_asof,
                      expected_run_id=expected_run_id)
    result["panel_repair_attempts"] = 0
    if result["panel_drift_rows"] and panel_repair:
        # Re-read all FOUR authorities before permitting the only repair.
        need(snapshot(api) == before, "CONCURRENT_SOURCE_CHANGE_NO_REPAIR")
        result["panel_repair_attempts"] = PANEL_REPAIR_BUDGET
        panel.synchronize(api)
        after = snapshot(api)
        need(after[:3] == before[:3], "SOURCES_CHANGED_DURING_PANEL_REPAIR")
        final = evaluate(*after, expected_asof,
                         expected_run_id=expected_run_id)
        need(final["panel_drift_rows"] == 0, "PANEL_REPAIR_READBACK_FAILED")
        final["panel_repair_attempts"] = PANEL_REPAIR_BUDGET
        final["repair"] = "PANEL_REPAIRED_AND_VERIFIED"
        return final
    return result


def _emit(document, output):
    # Strict allowlist; never serialize Sheet rows/exception/credentials.
    public = {
        "schema": SCHEMA,
        "status": document["status"],
        "asof_et": document.get("asof_et"),
        "valid_symbols": document.get("valid_symbols"),
        "new_technical_al": document.get("new_technical_al"),
        "alarm_ledger_events": document.get("alarm_ledger_events"),
        "pending_new_al": document.get("pending_new_al"),
        "suppressed_new_al": document.get("suppressed_new_al"),
        "source_run_same": document.get("source_run_same"),
        "panel_drift_rows": document.get("panel_drift_rows"),
        "panel_repair_attempts": document.get("panel_repair_attempts"),
        "repair": document.get("repair", "NONE"),
        "personal_research_start": document.get("personal_research_start", "HOLD"),
        "premium_task_emission": "UNVERIFIED",
        "iphone_device_ack": "UNKNOWN",
        "canonical_full_final": "NO-GO",
        "full_autonomous_start": "HOLD",
        "execution": "NONE",
        "real_money": "NO-GO",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(public, sort_keys=True,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print("XRAY_GUARDIAN=" + public["status"])
    return public


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-asof")
    parser.add_argument("--expected-run-id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-panel-repair", action="store_true")
    args = parser.parse_args(argv)
    try:
        asof = args.expected_asof or current_completed_session()
        if asof is None:
            _emit({"status": "SKIPPED_NO_ELIGIBLE_XNAS_EOD"},
                  args.output)
            return 0
        creds = os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON", "")
        need(bool(creds), "MISSING_PRIVATE_GOOGLE_AUTH")
        api = sheets.SheetApi(creds)
        result = run(api, asof, expected_run_id=args.expected_run_id,
                     panel_repair=not args.no_panel_repair)
        _emit(result, args.output)
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, GuardianHold) else type(exc).__name__
        # Fixed reason classification without leaking arbitrary source text.
        code = code if code in {
            "EXPECTED_ASOF_INVALID", "SCAN_MISSING_OR_DUPLICATE",
            "SCAN_ORDER_DRIFT", "LATEST_SCAN_ASOF_NOT_ACCEPTED",
            "SCOPE_OR_COVERAGE_DRIFT", "FINAL_READY_FALSE",
            "AL_COUNT_INVALID", "UNTRUSTED_RUN_PROOF",
            "CANDIDATE_KEY_DUPLICATE", "AL_COUNT_VS_CANDIDATE_ROWS",
            "CANDIDATE_IDENTITY_DRIFT", "CANDIDATE_LIFECYCLE_UNKNOWN",
            "IMMUTABLE_PRICE_ORDER", "IMMUTABLE_RR_NOT_2R",
            "LIFECYCLE_15_SESSION_BOUNDS", "AL_OUTBOX_EVENT_MISSING",
            "AL_OUTBOX_SUPPRESSION_OR_STATE_DRIFT",
            "AL_OUTBOX_IMMUTABLE_LEVEL_DRIFT",
            "PANEL_SOURCE_ASOF_DRIFT", "EXPECTED_RUN_ID_INVALID",
            "CONCURRENT_SOURCE_CHANGE_NO_REPAIR",
            "SOURCES_CHANGED_DURING_PANEL_REPAIR",
            "PANEL_REPAIR_READBACK_FAILED", "MISSING_PRIVATE_GOOGLE_AUTH",
            "INVALID_IMMUTABLE_PRICE"} else "PROVIDER_OR_CONTRACT_BLOCKED"
        _emit({"status": "GUARDIAN_FAIL_CLOSED_" + code}, args.output)
        return 3


if __name__ == "__main__":
    sys.exit(main())
