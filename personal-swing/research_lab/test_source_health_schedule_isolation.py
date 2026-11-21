"""Source-health delivery path isolation and fail-closed diagnostics.

Pure tests; no GitHub API calls, no Sheet access, no notifications, no orders.
These tests protect the original source schedule and natural observation lane.
"""
import unittest
from pathlib import Path

import source_health_live as live

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "xray-research-source-lab.yml"


class ResearchSourceLabSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_push_or_pr_must_not_cancel_natural_research_check(self):
        groups = [line.strip() for line in self.source.splitlines()
                  if line.lstrip().startswith("group:")]
        self.assertEqual(len(groups), 1)
        self.assertIn("github.event_name == 'pull_request'", groups[0])
        self.assertIn("github.event_name == 'push'", groups[0])
        self.assertIn("github.run_id", groups[0])
        self.assertIn("|| 'xray-research-source-lab-natural'", groups[0])
        self.assertNotIn("github.ref }}", groups[0])

    def test_natural_check_not_canceled_during_push(self):
        self.assertIn("cancel-in-progress: false", self.source)
        self.assertNotIn("cancel-in-progress: true", self.source)

    def test_no_new_clock_or_delivery_channel(self):
        self.assertEqual(self.source.count("- cron: '41 5 * * *'"), 1)
        self.assertEqual(self.source.count("  schedule:"), 1)
        self.assertNotIn("notify_parent", self.source)
        self.assertNotIn("webhook", self.source.lower())
        self.assertIn("source-health-natural:", self.source)
        self.assertIn("github.event_name == 'schedule'", self.source)


class SourceHealthSanitizedFailureTests(unittest.TestCase):
    def test_cause_is_safe_and_specific_but_payload_never_escapes(self):
        secret = "sk-FAKE_DO_NOT_PRINT_TEST_CREDENTIAL"
        result = live.safe_failure_diagnostic(
            "PROVENANCE_AGGREGATE", RuntimeError("source-private-url "+secret))
        self.assertEqual(result["stage"], "PROVENANCE_AGGREGATE")
        self.assertEqual(result["fault_type"], "RuntimeError")
        self.assertEqual(result["market_source"], "UNVERIFIED")
        self.assertFalse(result["private_rows_logged"])
        self.assertEqual(result["mutations"], 0)
        self.assertEqual(result["notifications"], 0)
        self.assertNotIn(secret, str(result))
        self.assertNotIn("source-private-url", str(result))

    def test_unexpected_stage_and_exception_are_classified_without_text(self):
        class SecretTypedError(Exception):
            pass
        result = live.safe_failure_diagnostic(
            "SHEET!A1 contains private symbol", SecretTypedError("secret"))
        self.assertEqual(result["stage"], "UNKNOWN")
        self.assertEqual(result["fault_type"], "UNCLASSIFIED")
        self.assertNotIn("secret", str(result).lower())

    def test_missing_credentials_is_hold_not_success_or_retry(self):
        import contextlib, io, os
        from unittest.mock import patch
        buf = io.StringIO()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "", "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON": "",
                                     "XRAY_PRIVATE_SPREADSHEET_ID": ""}):
            with contextlib.redirect_stdout(buf):
                code = live.main()
        self.assertEqual(code, 3)
        out = buf.getvalue()
        self.assertIn("XRAY_SOURCE_HEALTH_AUTO_V1=HOLD_UNVERIFIED_NO_DATA_PUBLISHED", out)
        self.assertIn('"stage": "CREDENTIAL_CHECK"', out)
        self.assertNotIn("PRIVATE_SPREADSHEET_ID", out)
        self.assertNotIn("Authorization:", out)
        self.assertNotIn("GITHUB_TOKEN", out)


if __name__ == "__main__":
    unittest.main()
