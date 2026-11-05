#!/usr/bin/env python3
"""Read-only personal EOD delivery/score evidence audit.

This file MUST NOT issue messages, change delivery flags, replay old AL/STOP
events, write Sheets, log private event keys, or infer a ChatGPT/device ACK.
The historical note "CHATGPT_MESSAGE_NOT_SENT" is a reconciliation flag;
it does not prove that an external ChatGPT message was never shown.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date

import alert_ledger_contract as ledger
import private_sheet_writer as writer
import swing_score_daily as scoring

SCHEMA = "XRAY_PERSONAL_PRIVATE_EVIDENCE_AUDIT_V1"
NOT_SENT = "CHATGPT_MESSAGE_NOT_SENT"
STATUS_ALLOWED = frozenset((scoring.READY, scoring.REQUESTED))


class EvidenceHold(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise EvidenceHold(code)


def _row_cells(row, size):
    return list(row) + [""] * (size - len(row))


def assess(alerts, scores, scans, expected_asof=None):
    """Pure, fail-closed aggregate; no symbol or row is ever returned."""
    events = ledger.parse_ledger(alerts)
    scan_rows = writer.rows_only(scans, writer.SCAN_HEADER)
    need(bool(scan_rows), "NO_VERIFIED_SCAN")
    days = [r[0] for r in scan_rows]
    need(days == sorted(set(days)), "SCAN_ORDER_OR_DUPLICATE")
    try:
        for day in days:
            need(date.fromisoformat(day).isoformat() == day, "SCAN_BAD_DATE")
    except (ValueError, TypeError) as exc:
        raise EvidenceHold("SCAN_BAD_DATE") from exc
    current = days[-1]
    if expected_asof is not None:
        need(expected_asof == current, "EXPECTED_ASOF_DRIFT")

    need(isinstance(scores, list) and scores and
         tuple(scores[0]) == scoring.HEADER, "SCORE_TAB_MISSING_OR_SCHEMA_DRIFT")
    score_rows = [list(r) for r in scores[1:] if r and r[0]]
    score_keys = [r[0] for r in score_rows]
    need(len(score_keys) == len(set(score_keys)), "SCORE_DUPLICATE_KEY")
    by_day = {}
    for raw in score_rows:
        need(len(raw) <= len(scoring.HEADER), "SCORE_TOO_MANY_COLUMNS")
        r = _row_cells(raw, len(scoring.HEADER))
        asof, kind = r[1], r[4]
        need(asof in days and asof <= current, "SCORE_ASOF_NOT_IN_SCAN")
        need(kind in ("SUMMARY", "EPISODE"), "SCORE_UNEXPECTED_KIND")
        need((r[0] == asof + "|SUMMARY") if kind == "SUMMARY" else
             (r[0] == asof + "|" + r[2] and bool(r[2])),
             "SCORE_IDENTITY_DRIFT")
        by_day.setdefault(asof, {"summary": [], "episodes": []})
        by_day[asof]["summary" if kind == "SUMMARY" else "episodes"].append(r)
    historical_valid = 0
    for asof, rows in by_day.items():
        need(len(rows["summary"]) == 1, "SCORE_SUMMARY_NOT_UNIQUE")
        summary = rows["summary"][0]
        try:
            active, scored, hold, distinct = (int(summary[i]) for i in (5, 6, 7, 8))
        except (ValueError, TypeError) as exc:
            raise EvidenceHold("SCORE_COUNTS_INVALID") from exc
        need(0 <= scored <= active and 0 <= hold <= active and
             scored + hold == active and 0 <= distinct <= active and
             active == len(rows["episodes"]), "SCORE_COUNT_OR_ROW_MISMATCH")
        need(summary[27] in STATUS_ALLOWED, "SCORE_NOTIFICATION_STATE_DRIFT")
        need(len(summary[29]) == 64 and
             all(r[29] == summary[29] for r in rows["episodes"]),
             "SCORE_DIGEST_DRIFT")
        if summary[27] == scoring.REQUESTED:
            need(bool(summary[28]), "SCORE_REQUESTED_WITHOUT_TIME")
        else:
            need(not summary[28], "SCORE_READY_BUT_TIMESTAMPED")
        historical_valid += 1

    counts = Counter(v["status"] for v in events.values())
    explicit_not_sent = sum(
        v["status"] == ledger.REQUESTED and
        NOT_SENT in str(v["row"][19] if len(v["row"]) > 19 else "")
        for v in events.values()
    )
    need(explicit_not_sent <= counts.get(ledger.REQUESTED, 0),
         "UNRECONCILED_COUNT_INVALID")
    requested_count = counts.get(ledger.REQUESTED, 0)
    pending = counts.get(ledger.CONFIRMED_PENDING, 0)
    current_score = by_day.get(current)
    score_state = "SUMMARY_PRESENT" if current_score else "MISSING_FOR_LATEST_VERIFIED_SCAN"
    # In the absence of an explicit host chat_ref, no Sheet cell can prove delivery.
    delivery_state = ("RECONCILIATION_REQUIRED" if explicit_not_sent or pending else
                      "PLATFORM_DELIVERY_UNKNOWN")
    return {
        "schema": SCHEMA,
        "status": "READ_ONLY_EVIDENCE_AUDIT",
        "last_verified_scan_asof": current,
        "last_asof_score": score_state,
        "historical_score_summaries_validated": historical_valid,
        "scored_active_episodes": int(current_score["summary"][0][5]) if current_score else None,
        "score_count": int(current_score["summary"][0][6]) if current_score else None,
        "score_hold_count": int(current_score["summary"][0][7]) if current_score else None,
        "alarm_event_count": len(events),
        "alarm_request_intents": requested_count,
        "alarm_pending_intents": pending,
        "unreconciled_explicit_not_sent_notes": explicit_not_sent,
        "suppressed": counts.get(ledger.SUPPRESSED, 0),
        "quarantined": counts.get(ledger.QUARANTINED, 0),
        "delivery_evidence": delivery_state,
        "chatgpt_visible_message_proven": False,
        "platform_ack": "UNKNOWN",
        "device_ack": "UNKNOWN",
        "retry_or_replay_permitted": False,
        "sheet_writes": 0,
        "messages_sent": 0,
        "execution": "NONE",
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--expected-asof", default=None)
    args = p.parse_args(argv)
    try:
        credentials = os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON", "")
        need(bool(credentials), "PRIVATE_AUTH_MISSING")
        api = writer.SheetApi(credentials)
        api.check_metadata()
        scan = api.read("TARAMA_KAYITLARI", "J")
        events = api.read("UYARI_OLAYLARI", "T")
        scores = api.read(scoring.TAB, "AI")
        report = assess(events, scores, scan, args.expected_asof)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        # Safe static exception class only; never leak private source content,
        # credentials, URLs, row identity, traceback or symbol names.
        print(json.dumps({
            "schema": SCHEMA,
            "status": "EVIDENCE_AUDIT_HOLD",
            "reason_type": type(exc).__name__,
            "chatgpt_visible_message_proven": False,
            "platform_ack": "UNKNOWN",
            "sheet_writes": 0,
            "messages_sent": 0,
            "execution": "NONE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
