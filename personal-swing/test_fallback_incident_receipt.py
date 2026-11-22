"""Pure offline negative acceptance tests: no provider or repository writes."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

import fallback_incident_receipt as receipt


def payload(**fields):
    base = {
        "status": "BLOCKED_DISPATCH_NOT_CONFIRMED",
        "reason_code": "NATURAL_FALLBACK_POLICY_LOCKED",
        "asof_et": "2026-11-20",
        "dispatch_requested": False,
        "execution": "NONE",
    }
    base.update(fields)
    return (json.dumps(base) + "\n").encode()


class RedactedFallbackReceipt(unittest.TestCase):
    def test_real_missing_primary_lock_produces_exact_safe_category(self):
        got = receipt.classify(payload())
        self.assertEqual(got, {"category": "MISSING_PRIMARY_RECOVERY_POLICY_LOCKED", "asof": "2026-11-20"})
        view = receipt.render(got)
        self.assertIn("NO_WORKFLOW_DISPATCH", view)
        self.assertIn("Canonical EOD completion: \x60UNVERIFIED\x60", view)
        self.assertIn("ChatGPT delivery: \x60UNKNOWN\x60", view)

    def test_unknown_dispatch_status_cannot_masquerade_as_safe_gap(self):
        for changes in ({"reason_code": "UNTRUSTED"}, {"dispatch_requested": True},
                        {"execution": "EXECUTED"}, {"asof_et": "2026-11-31"},
                        {"status": "DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED"}):
            with self.subTest(changes=changes):
                self.assertEqual(receipt.classify(payload(**changes))["category"], "UNVERIFIED_FAILURE")

    def test_known_expired_window_remains_hold_not_false_green(self):
        got = receipt.classify(payload(status="BLOCKED_NATURAL_FALLBACK_EXPIRED"))
        self.assertEqual(got["category"], "NATURAL_WINDOW_EXPIRED")
        self.assertIn("Recovery: \x60HOLD\x60", receipt.render(got))

    def test_provider_exception_has_no_claim_of_a_missing_asof(self):
        got = receipt.classify(payload(status="BLOCKED_GITHUB_API_UNCERTAIN", asof_et="2026-11-20"))
        self.assertEqual(got, {"category": "GITHUB_READ_UNCERTAIN", "asof": "UNKNOWN"})
        self.assertIn("DISPATCH_STATE_UNVERIFIED", receipt.render(got))

    def test_adversarial_and_incomplete_input_never_echoed(self):
        attack = "TOP_SECRET\n<svg><script>steal()</script>"
        cases = [None, "bad", b"", b"{}\n", b"{}\n{}\n", b"\xff\n",
                 payload(asof_et=attack), payload(status=attack),
                 payload(reason_code=attack), b"A" * 8193]
        for item in cases:
            with self.subTest(item=str(item)[:20]):
                view = receipt.render(receipt.classify(item))
                self.assertNotIn("TOP_SECRET", view)
                self.assertNotIn("<svg>", view)
                self.assertIn("UNVERIFIED", view)

    def test_cli_appends_summary_without_overwriting_existing_and_no_raw_json(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "incident.json")
            target = Path(folder, "summary.md")
            source.write_bytes(payload())
            target.write_text("Earlier trusted summary\n", encoding="utf-8")
            self.assertEqual(receipt.main(["--result", str(source), "--summary", str(target)]), 0)
            view = target.read_text(encoding="utf-8")
            self.assertTrue(view.startswith("Earlier trusted summary\n"))
            self.assertIn("MISSING_PRIMARY_RECOVERY_POLICY_LOCKED", view)
            self.assertNotIn('"reason_code"', view)

    def test_missing_file_reports_unknown_without_hidden_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "summary.md")
            self.assertEqual(receipt.main(["--result", str(Path(folder, 'missing')), "--summary", str(target)]), 0)
            self.assertIn("UNVERIFIED_FAILURE", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
