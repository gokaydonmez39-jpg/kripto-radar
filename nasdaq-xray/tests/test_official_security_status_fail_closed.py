"""Official Nasdaq security-status parsing and point-in-time safety regressions.

Isolated fixtures only. No provider HTTP, credentials, price, broker, or signal IO.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_source_guard import parse_security_status_html, derive_security_suspensions

PAGE = "<html><body><h1>Nasdaq Security Status Updates</h1><p>Search By Date Range: From: To:</p>{}</body></html>"


def event(date, symbol, action):
    return {"EffectiveDate": date, "Symbol": symbol, "IssueEvent": action}


class OfficialSecurityStatusFailClosed(unittest.TestCase):
    def test_redirect_login_page_must_not_be_empty_pass(self):
        with self.assertRaises(ValueError):
            parse_security_status_html("<html><body>Login required</body></html>")

    def test_lookalike_table_without_official_page_identity_rejected(self):
        fake = "<html><table><tr><td>2026-10-16</td><td>XYZ</td><td>X</td><td>Security Additions</td></tr></table></html>"
        with self.assertRaises(ValueError):
            parse_security_status_html(fake)

    def test_official_page_malformed_empty_without_no_results_rejected(self):
        with self.assertRaises(ValueError):
            parse_security_status_html(PAGE.format("<div>upstream layout changed</div>"))

    def test_official_explicit_no_results_is_allowed_as_empty(self):
        self.assertEqual(parse_security_status_html(PAGE.format("<p>No results found.</p>")), [])

    def test_fake_no_results_outside_official_page_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_security_status_html("<html><body>No results found.</body></html>")

    def test_parse_official_valid_rows(self):
        page = PAGE.format("<table><tr><td>2026-10-16</td><td>ZZZ</td><td>Issuer</td><td>Issue Suspensions</td></tr></table>")
        rows = parse_security_status_html(page)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Symbol"], "ZZZ")

    def test_future_effective_addition_cannot_clear_current_suspension(self):
        rows = [
            event("2026-10-16", "ZZZ", "Issue Suspensions"),
            event("2026-10-20", "ZZZ", "Security Additions"),
        ]
        suspended, details = derive_security_suspensions(rows, asof_date="2026-10-19")
        self.assertEqual(suspended, ["ZZZ"])
        self.assertEqual(details["ZZZ"]["latest_addition"], None)

    def test_effective_date_arrives_then_clears(self):
        rows = [
            event("2026-10-16", "ZZZ", "Issue Suspensions"),
            event("2026-10-20", "ZZZ", "Security Additions"),
        ]
        suspended, _ = derive_security_suspensions(rows, asof_date="2026-10-20")
        self.assertEqual(suspended, [])

    def test_invalid_effective_date_does_not_clear(self):
        rows = [
            event("2026-10-16", "ZZZ", "Issue Suspensions"),
            event("2026-99-99", "ZZZ", "Security Additions"),
        ]
        suspended, _ = derive_security_suspensions(rows, asof_date="2026-10-19")
        self.assertEqual(suspended, ["ZZZ"])

    def test_future_only_event_ignored_at_asof(self):
        suspended, evidence = derive_security_suspensions([
            event("2026-10-20", "ZZZ", "Issue Suspensions"),
        ], asof_date="2026-10-19")
        self.assertEqual(suspended, [])
        self.assertEqual(evidence, {})

    def test_same_day_conflict_stays_suspended(self):
        suspended, evidence = derive_security_suspensions([
            event("2026-10-19", "ZZZ", "Security Additions"),
            event("2026-10-19", "ZZZ", "Issue Suspensions"),
        ], asof_date="2026-10-19")
        self.assertEqual(suspended, ["ZZZ"])
        self.assertEqual(evidence["ZZZ"]["latest_suspension"], "2026-10-19")


if __name__ == "__main__":
    unittest.main()
