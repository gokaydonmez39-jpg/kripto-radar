"""Synthetic-only regression tests for the personal XRAY Guardian."""
import copy
import unittest

import alert_ledger_contract as lc
import alert_outbox_producer as out
import test_al_outbox_producer as cases
import test_panel_reconciler as panels
import xray_guardian as guardian


class Fixture(panels.FakeApi):
    def __init__(self):
        super().__init__()
        src = cases.Fake()
        out.synchronize(src.snap, src.scans[1][8], src)
        self.candidates = copy.deepcopy(src.candidates)
        self.scans = copy.deepcopy(src.scans)
        self.alerts = copy.deepcopy(src.alerts)
        self.asof = src.snap["asof_et"]

    def read(self, title, last):
        if title == "UYARI_OLAYLARI":
            return copy.deepcopy(self.alerts)
        return super().read(title, last)

    def evaluate(self):
        return guardian.evaluate(self.candidates, self.scans, self.alerts,
                                 self.panel, self.asof)


class GuardianTests(unittest.TestCase):
    def test_verified_eod_without_device_claim(self):
        a = Fixture()
        result = a.evaluate()
        self.assertEqual(result["valid_symbols"], 477)
        self.assertEqual(result["new_technical_al"], 2)
        self.assertEqual(result["pending_new_al"], 2)
        self.assertEqual(result["iphone_device_ack"], "UNKNOWN")
        self.assertEqual(result["full_autonomous_start"], "HOLD")

    def test_panel_repair_once_only(self):
        a = Fixture()
        before = copy.deepcopy((a.candidates, a.scans, a.alerts))
        r = guardian.run(a, a.asof)
        self.assertEqual(r["repair"], "PANEL_REPAIRED_AND_VERIFIED")
        self.assertEqual(r["panel_repair_attempts"], 1)
        self.assertEqual(a.writes, 1)
        self.assertEqual((a.candidates, a.scans, a.alerts), before)
        r = guardian.run(a, a.asof)
        self.assertEqual(r["panel_repair_attempts"], 0)
        self.assertEqual(a.writes, 1)

    def test_no_repair_mode(self):
        a = Fixture()
        r = guardian.run(a, a.asof, panel_repair=False)
        self.assertEqual(r["repair"], "PANEL_ONLY_ONCE")
        self.assertEqual(a.writes, 0)

    def test_missing_al_event_holds(self):
        a = Fixture()
        a.alerts.pop()
        with self.assertRaisesRegex(guardian.GuardianHold, "AL_OUTBOX_EVENT_MISSING"):
            guardian.run(a, a.asof)
        self.assertEqual(a.writes, 0)

    def test_duplicate_event_key_holds(self):
        a = Fixture()
        a.alerts.append(copy.deepcopy(a.alerts[1]))
        with self.assertRaisesRegex(lc.LedgerRefused, "DUPLICATE_EVENT_KEY"):
            guardian.run(a, a.asof)

    def test_event_stop_drift_holds(self):
        a = Fixture()
        a.alerts[1][8] = "0.01"
        with self.assertRaisesRegex(guardian.GuardianHold, "AL_OUTBOX_IMMUTABLE_LEVEL_DRIFT"):
            guardian.run(a, a.asof)

    def test_invalid_rr_holds(self):
        a = Fixture()
        a.candidates[1][6] = "123456"
        with self.assertRaisesRegex(guardian.GuardianHold, "IMMUTABLE_RR_NOT_2R"):
            guardian.run(a, a.asof)

    def test_bad_coverage_holds(self):
        a = Fixture()
        a.scans[1][4] = "476"
        with self.assertRaisesRegex(guardian.GuardianHold, "SCOPE_OR_COVERAGE_DRIFT"):
            guardian.run(a, a.asof)

    def test_well_formed_but_untrusted_source_sha_holds(self):
        a = Fixture()
        original = a.scans[1][9]
        self.assertIn("scopeSHA=", original)
        old_sha = original.split("scopeSHA=")[1][:64]
        replacement = ("0" if old_sha[0] != "0" else "1") + old_sha[1:]
        a.scans[1][9] = original.replace(
            "scopeSHA=" + old_sha, "scopeSHA=" + replacement, 1)
        with self.assertRaisesRegex(guardian.GuardianHold,
                                    "SOURCE_SCOPE_OR_POLICY_SHA_DRIFT"):
            guardian.run(a, a.asof)
        self.assertEqual(a.writes, 0)

    def test_bad_asof_holds(self):
        a = Fixture()
        with self.assertRaisesRegex(guardian.GuardianHold, "LATEST_SCAN_ASOF_NOT_ACCEPTED"):
            guardian.run(a, "2026-10-28")

    def test_broken_source_sha_holds(self):
        a = Fixture()
        a.scans[1][9] = "scopeSHA=broken"
        with self.assertRaises(Exception):
            guardian.run(a, a.asof)

    def test_outside_15_sessions_holds(self):
        a = Fixture()
        a.candidates[1][7] = "AÇIK • 16/15 SEANS"
        with self.assertRaisesRegex(guardian.GuardianHold, "LIFECYCLE_15_SESSION_BOUNDS"):
            guardian.run(a, a.asof)

    def test_requested_does_not_mean_ack(self):
        a = Fixture()
        a.alerts[1][17] = lc.REQUESTED
        a.alerts[1][18] = "2026-11-03 12:17 TRT"
        r = a.evaluate()
        self.assertEqual(r["pending_new_al"], 1)
        self.assertEqual(r["iphone_device_ack"], "UNKNOWN")

    def test_suppression_required_for_prior_active_symbol(self):
        a = Fixture()
        symbol = a.candidates[1][2]
        a.candidates.insert(1, ["2026-10-23|" + symbol, "2026-10-23",
                                 symbol, "TEKNİK AL ADAYI", "100", "95", "110",
                                 "AÇIK • 2/15 SEANS"])
        with self.assertRaisesRegex(guardian.GuardianHold,
                                    "AL_OUTBOX_SUPPRESSION_OR_STATE_DRIFT"):
            guardian.run(a, a.asof)

    def test_bad_header_and_state_hold(self):
        a = Fixture()
        a.alerts[0][0] = "WRONG"
        with self.assertRaisesRegex(lc.LedgerRefused, "SHEET_HEADER_DRIFT"):
            guardian.run(a, a.asof)
        b = Fixture()
        b.alerts[1][17] = "DELIVERED"
        with self.assertRaisesRegex(lc.LedgerRefused, "UNKNOWN_DELIVERY_STATE"):
            guardian.run(b, b.asof)


    def test_legacy_two_decimal_rr_deviation_is_accepted_only_in_tolerance(self):
        a = Fixture()
        # Exactly 1 cent of display residual; still immutable matching event.
        a.candidates[1][4], a.candidates[1][5], a.candidates[1][6] = (
            "167,73", "156,29", "190,62")
        a.alerts[1][7], a.alerts[1][8], a.alerts[1][9] = (
            "167,73", "156,29", "190,62")
        result = a.evaluate()
        self.assertEqual(result["personal_research_start"], "PASS")
        a.candidates[1][6] = "190,64"
        with self.assertRaisesRegex(guardian.GuardianHold, "IMMUTABLE_RR_NOT_2R"):
            a.evaluate()

    def test_readonly_transport_retry_once(self):
        import private_sheet_writer as writer
        a = Fixture()
        original = a.read
        reads = [0]
        def glitch(name, last):
            if reads[0] == 0:
                reads[0] += 1
                raise writer.HandoffBlocked("READ_TRANSIENT")
            return original(name, last)
        a.read = glitch
        data = guardian.run(a, a.asof, panel_repair=False)
        self.assertEqual(data["personal_research_start"], "PASS")
        self.assertEqual(reads[0], 1)
        self.assertEqual(a.writes, 0)

    def test_readonly_double_failure_must_not_write(self):
        import private_sheet_writer as writer
        a = Fixture()
        def transport_down(name, last):
            raise writer.HandoffBlocked("READ_TRANSPORT_FAIL")
        a.read = transport_down
        with self.assertRaises(writer.HandoffBlocked):
            guardian.run(a, a.asof)
        self.assertEqual(a.writes, 0)

    def test_redacted_receipt_hides_extra_source_fields(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "safe.json"
            receipt = guardian._emit({
                "status": "PERSONAL_EOD_AND_AL_LEDGER_VERIFIED",
                "asof_et": "2026-11-02",
                "new_technical_al": 2,
                "source_private_value": "SYNTHETIC_PRIVATE_MARKER",
            }, path)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", path.read_text())
            self.assertNotIn("source_private_value", path.read_text())
            self.assertEqual(receipt["iphone_device_ack"], "UNKNOWN")
            self.assertEqual(receipt["full_autonomous_start"], "HOLD")


if __name__ == "__main__":
    unittest.main()
