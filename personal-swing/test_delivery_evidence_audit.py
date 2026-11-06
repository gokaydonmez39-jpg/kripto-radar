"""Read-only evidence audit: tests must pass under normal and python -O."""
import copy
import unittest

import alert_ledger_contract as ledger
import delivery_evidence_audit as audit
import private_sheet_writer as writer
import swing_score_daily as scoring


def fixture():
    scans = [list(writer.SCAN_HEADER),
             ["2026-11-04", "GitHub schedule VERIFIED IEX EOD",
              "477", "477", "477", "0", "TRUE", "1",
              "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/123", "NO_ORDER"]]
    key = ledger.event_key("2026-11-04", "EXM", "2026-11-04", "AL_NEW_EPISODE")
    event = ["" for _ in ledger.EVENT_HEADER]
    event[0:6] = [key, "2026-11-04|EXM", "2026-11-04", "EXM",
                  "2026-11-04", "AL_NEW_EPISODE"]
    event[17] = ledger.REQUESTED
    event[18] = "2026-11-05 10:00 TRT"
    event[19] = "FIRST_VERIFIED_EOD_EVENT_PENDING; CHATGPT_MESSAGE_NOT_SENT"
    alarms = [list(ledger.EVENT_HEADER), event]
    summary = ["" for _ in scoring.HEADER]
    summary[0:9] = ["2026-11-04|SUMMARY", "2026-11-04",
                    "", "", "SUMMARY", "1", "1", "0", "1"]
    summary[27] = scoring.REQUESTED
    summary[28] = "2026-11-05 11:00 TRT"
    summary[29] = "a" * 64
    episode = ["" for _ in scoring.HEADER]
    episode[0:7] = ["2026-11-04|2026-11-04|EXM", "2026-11-04",
                    "2026-11-04|EXM", "EXM", "EPISODE", "1", "76.4"]
    episode[29] = "a" * 64
    scores = [list(scoring.HEADER), summary, episode]
    return alarms, scores, scans


class AuditTests(unittest.TestCase):
    def test_note_still_not_sent_even_if_requested(self):
        r = audit.assess(*fixture())
        self.assertEqual(r["unreconciled_explicit_not_sent_notes"], 1)
        self.assertEqual(r["delivery_evidence"], "RECONCILIATION_REQUIRED")
        self.assertFalse(r["chatgpt_visible_message_proven"])
        self.assertFalse(r["retry_or_replay_permitted"])
        self.assertEqual(r["messages_sent"], 0)

    def test_no_notes_never_claims_platform_ack(self):
        a, s, c = fixture()
        a[1][19] = "REQUESTED_NOT_DEVICE_ACK"
        r = audit.assess(a, s, c)
        self.assertEqual(r["delivery_evidence"], "PLATFORM_DELIVERY_UNKNOWN")
        self.assertEqual(r["platform_ack"], "UNKNOWN")
        self.assertEqual(r["alarm_request_intents"], 1)

    def test_new_pending_not_equated_to_delivered(self):
        a, s, c = fixture()
        a[1][17], a[1][18], a[1][19] = ledger.CONFIRMED_PENDING, "", ""
        r = audit.assess(a, s, c)
        self.assertEqual(r["alarm_pending_intents"], 1)
        self.assertEqual(r["delivery_evidence"], "RECONCILIATION_REQUIRED")

    def test_missing_score_for_verified_new_date_holds_only_score(self):
        a, s, c = fixture()
        c.append(["2026-11-05","schedule","477","477","477","0","TRUE",
                  "0","https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/124","NO_ORDER"])
        r = audit.assess(a, s, c)
        self.assertEqual(r["last_asof_score"], "MISSING_FOR_LATEST_VERIFIED_SCAN")
        self.assertIsNone(r["scored_active_episodes"])
        self.assertEqual(r["last_verified_scan_asof"], "2026-11-05")

    def test_score_present_matches_current_asof(self):
        r = audit.assess(*fixture(), expected_asof="2026-11-04")
        self.assertEqual(r["last_asof_score"], "SUMMARY_PRESENT")
        self.assertEqual(r["scored_active_episodes"], 1)
        self.assertEqual(r["score_count"], 1)

    def test_wrong_expected_asof_fails_closed(self):
        with self.assertRaisesRegex(audit.EvidenceHold, "EXPECTED_ASOF_DRIFT"):
            audit.assess(*fixture(), expected_asof="2026-11-05")

    def test_score_no_summary_blocks(self):
        a,s,c = fixture()
        s.pop(1)
        with self.assertRaisesRegex(audit.EvidenceHold, "SCORE_SUMMARY_NOT_UNIQUE"):
            audit.assess(a,s,c)

    def test_score_wrong_digest_blocks(self):
        a,s,c = fixture()
        s[2][29] = "b"*64
        with self.assertRaisesRegex(audit.EvidenceHold, "SCORE_DIGEST_DRIFT"):
            audit.assess(a,s,c)

    def test_score_wrong_counts_blocks(self):
        a,s,c = fixture()
        s[1][5] = "2"
        with self.assertRaisesRegex(audit.EvidenceHold, "SCORE_COUNT_OR_ROW_MISMATCH"):
            audit.assess(a,s,c)

    def test_score_ready_with_notified_time_blocks(self):
        a,s,c=fixture()
        s[1][27]=scoring.READY
        with self.assertRaisesRegex(audit.EvidenceHold, "SCORE_READY_BUT_TIMESTAMPED"):
            audit.assess(a,s,c)

    def test_duplicate_alert_blocks(self):
        a,s,c=fixture()
        a.append(copy.deepcopy(a[1]))
        with self.assertRaisesRegex(ledger.LedgerRefused, "DUPLICATE_EVENT_KEY"):
            audit.assess(a,s,c)

    def test_wrong_score_header_blocks(self):
        a,s,c=fixture()
        s[0][0]="WRONG"
        with self.assertRaisesRegex(audit.EvidenceHold, "SCORE_TAB_MISSING_OR_SCHEMA_DRIFT"):
            audit.assess(a,s,c)

    def test_scan_order_drifts_blocks(self):
        a,s,c=fixture()
        c.append(copy.deepcopy(c[1]))
        with self.assertRaisesRegex(audit.EvidenceHold, "SCAN_ORDER_OR_DUPLICATE"):
            audit.assess(a,s,c)

    def test_no_mutation_of_inputs(self):
        x=fixture()
        before=copy.deepcopy(x)
        audit.assess(*x)
        self.assertEqual(x,before)

    def test_historical_note_cannot_force_resend(self):
        a,s,c=fixture()
        a[1][19]="CHATGPT_MESSAGE_NOT_SENT"
        r=audit.assess(a,s,c)
        self.assertFalse(r["retry_or_replay_permitted"])
        self.assertFalse(r["chatgpt_visible_message_proven"])



class AsOfDeliveryReconciliationTests(unittest.TestCase):
    """Aggregate receipt contradictions by latest ASOF, never replay events."""

    def test_current_day_note_is_not_misreported_as_historical(self):
        report = audit.assess(*fixture())
        self.assertEqual(report["unreconciled_explicit_not_sent_notes"], 1)
        self.assertEqual(report["not_sent_latest_verified_asof"], 1)
        self.assertEqual(report["not_sent_prior_verified_asof"], 0)
        self.assertFalse(report["chatgpt_visible_message_proven"])
        self.assertFalse(report["retry_or_replay_permitted"])

    def test_historical_and_current_notes_partition_exactly(self):
        alerts, scores, scans = fixture()
        old = copy.deepcopy(alerts[1])
        old[0] = ledger.event_key("2026-11-03", "OLD", "2026-11-03",
                                  "AL_NEW_EPISODE")
        old[1], old[2], old[3], old[4] = (
            "2026-11-03|OLD", "2026-11-03", "OLD", "2026-11-03")
        alerts.append(old)
        scans.insert(1, ["2026-11-03", "GitHub schedule VERIFIED IEX EOD",
                         "477", "477", "477", "0", "TRUE", "1",
                         "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/122",
                         "NO_ORDER"])
        original = copy.deepcopy((alerts, scores, scans))
        report = audit.assess(alerts, scores, scans)
        self.assertEqual(report["unreconciled_explicit_not_sent_notes"], 2)
        self.assertEqual(report["not_sent_prior_verified_asof"], 1)
        self.assertEqual(report["not_sent_latest_verified_asof"], 1)
        self.assertEqual((alerts, scores, scans), original)
        self.assertEqual(report["delivery_evidence"], "RECONCILIATION_REQUIRED")
        self.assertEqual(report["sheet_writes"], 0)
        self.assertEqual(report["messages_sent"], 0)
        self.assertNotIn("OLD", str(report))
        self.assertNotIn("EXM", str(report))

    def test_future_not_sent_event_blocks_before_any_reconciliation_claim(self):
        alerts, scores, scans = fixture()
        event = alerts[1]
        event[4] = "2026-11-05"
        event[0] = ledger.event_key(event[2], event[3], event[4], event[5])
        with self.assertRaisesRegex(
                audit.EvidenceHold, "^UNSENT_NOTE_EVENT_ASOF_INVALID$"):
            audit.assess(alerts, scores, scans)

    def test_no_note_still_does_not_prove_delivery(self):
        alerts, scores, scans = fixture()
        alerts[1][19] = "NO_EXTERNAL_RECEIPT"
        report = audit.assess(alerts, scores, scans)
        self.assertEqual(report["unreconciled_explicit_not_sent_notes"], 0)
        self.assertEqual(report["not_sent_prior_verified_asof"], 0)
        self.assertEqual(report["not_sent_latest_verified_asof"], 0)
        self.assertFalse(report["chatgpt_visible_message_proven"])
        self.assertEqual(report["platform_ack"], "UNKNOWN")
        self.assertFalse(report["retry_or_replay_permitted"])



class RequiredCiEvidenceGateTests(unittest.TestCase):
    """The mandatory PR check must test this P0 evidence contract."""

    def test_required_pr_ci_runs_evidence_audit_normal_and_optimized(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parent.parent /
                    ".github/workflows/xray-nasdaq-477-pr-required-readonly.yml"
                    ).read_text(encoding="utf-8")
        self.assertIn("python -m unittest -q test_delivery_evidence_audit", workflow)
        self.assertIn("python -O -m unittest -q test_delivery_evidence_audit", workflow)
        self.assertIn("  xray-477-required-ci:", workflow)
        self.assertNotIn("continue-on-error: true", workflow)


if __name__ == "__main__":
    unittest.main()
