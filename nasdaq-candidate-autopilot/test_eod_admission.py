"""A43 independent fail-closed test vectors; synthetic GitHub log lines only."""
import copy
import datetime as dt
import json
import unittest
from eod_admission import Blocked, record_lines, json_receipts, validate_event

ET = "2026-10-30"
SHA = "a" * 64
SCOPE = "b" * 64
EVENT = {
    "run_id": 41159725169,
    "repository": "gokaydonmez39-jpg/kripto-radar",
    "workflow_name": "XRAY Personal 477 EOD Daily Health (Research Only)",
    "head_branch": "main",
    "head_sha": SHA,
    "event": "schedule",
    "status": "completed",
    "conclusion": "success",
    "created_at": "2026-10-31T02:22:40Z",
}
SCAN = {"analysis_fingerprint_sha256": SHA, "asof_et": ET, "final_ready": True,
        "invalid_or_missing": 0, "new_entries": 3, "no_execution": True,
        "processed": 477, "remaining": 0, "scope_sha256": SCOPE,
        "universe": 477, "valid": 477}
SHEET = {"asof_et": ET, "candidates": 3, "device_ack": False,
         "status": "PRIVATE_SHEET_READBACK_PASS"}
LIFE = {"asof_et": ET, "device_ack": False, "evaluated": 0,
        "status": "LIFECYCLE_READBACK_PASS"}
PANEL = {"asof_et": ET, "device_ack": False, "status": "PANEL_READBACK_PASS"}


def logline(payload):
    return "2026-10-31T02:23:29.6454360Z ***" + (
        json.dumps(payload, sort_keys=True)[1:-1] if isinstance(payload, dict) else payload) + "***"


def fixture(scan=None, sheet=None, life=None, panel=None,
            handoff=True, preflight=True):
    out = [logline(SCAN if scan is None else scan),
           logline(SHEET if sheet is None else sheet),
           logline(LIFE if life is None else life),
           logline(PANEL if panel is None else panel)]
    if handoff:
        out.append("2026-10-31T02:23:29.7791962Z "
                   "XRAY_PERSONAL_GITHUB_HANDOFF=PASS_477_477_SOURCE_POLICY_SHA_BOUND_PRIVATE")
    if preflight:
        out.append("2026-10-31T02:23:19.8525950Z "
                   "PRIVATE_SHEETS_PREFLIGHT=READ_PASS_WRITE_NOT_VERIFIED")
    return "\n".join(out)


class RealEODAdmissionTests(unittest.TestCase):
    def admitted(self, data=None, log=None):
        return validate_event(EVENT if data is None else data,
                              fixture() if log is None else log)

    def blocked(self, event=None, log=None):
        with self.assertRaises(Blocked):
            self.admitted(event, log)

    def test_real_shape_and_exact_session(self):
        x = self.admitted()
        self.assertTrue(x["sheet_readback"] and x["panel_readback"])
        self.assertEqual(x["asof_et"], ET)
        self.assertFalse(x["production_promotion"])

    def test_repeated_deterministic_receipt(self):
        self.assertEqual(self.admitted(), self.admitted())

    def test_successful_workflow_without_scan_is_not_pass(self):
        self.blocked(log=fixture(scan={}))

    def test_no_hand_off_is_not_pass(self):
        self.blocked(log=fixture(handoff=False))

    def test_missing_sheet_readback_is_not_pass(self):
        self.blocked(log=fixture(sheet={}))

    def test_missing_lifecycle_is_not_pass(self):
        self.blocked(log=fixture(life={}))

    def test_missing_panel_is_not_pass(self):
        self.blocked(log=fixture(panel={}))

    def test_missing_auth_preflight_is_not_pass(self):
        self.blocked(log=fixture(preflight=False))

    def test_wrong_477_count_blocks(self):
        bad = dict(SCAN, valid=476)
        self.blocked(log=fixture(scan=bad))

    def test_false_final_ready_blocks(self):
        self.blocked(log=fixture(scan=dict(SCAN, final_ready=False)))

    def test_missing_source_sha_blocks(self):
        self.blocked(log=fixture(scan=dict(SCAN, analysis_fingerprint_sha256="")))

    def test_wrong_private_asof_blocks(self):
        self.blocked(log=fixture(sheet=dict(SHEET, asof_et="2026-10-29")))

    def test_producer_looks_successful_on_holiday_but_blocks(self):
        self.blocked(event=dict(EVENT, created_at="2026-11-01T02:22:40Z"))

    def test_fallback_dispatch_not_admitted_without_proof(self):
        self.blocked(event=dict(EVENT, event="workflow_dispatch"))

    def test_untrusted_branch_fails(self):
        self.blocked(event=dict(EVENT, head_branch="feature-evil"))

    def test_wrong_repository_fails(self):
        self.blocked(event=dict(EVENT, repository="other/repo"))

    def test_wrong_workflow_fails(self):
        self.blocked(event=dict(EVENT, workflow_name="fake-run"))

    def test_failed_upstream_fails(self):
        self.blocked(event=dict(EVENT, conclusion="failure"))

    def test_unexpected_ack_claim_fails(self):
        self.blocked(log=fixture(sheet=dict(SHEET, device_ack=True)))

    def test_duplicate_receipt_fails_closed(self):
        self.blocked(log=fixture() + "\n" + logline(SCAN))

    def test_log_source_echo_does_not_count(self):
        fake = "2026-10-31T02:23:19.850Z \x1b[36;1mecho " + json.dumps(SCAN) + "\x1b[0m"
        self.assertEqual(json_receipts(record_lines(fake)), [])
        self.blocked(log=fake)

    def test_oversize_log_fails(self):
        self.blocked(log="a" * (5 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
