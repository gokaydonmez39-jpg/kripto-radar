"""No-network regression for optional SEC read-only acquisition."""
import json
import unittest
from datetime import datetime, timezone

from fundamental_shadow import ShadowHold, analyze
from fundamental_sec_capture import SecCapture, capture_one, safe_url
from test_fundamental_shadow import fixture, CIK, ACC


class TestSECReadOnlyCapture(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture()
        self.calls = []
        self.sleeps = []

        def fake(request, timeout):
            url = request.full_url
            self.calls.append((url, request.get_method(), request.get_header("User-agent")))
            self.assertEqual(timeout, 15.0)
            if "/submissions/" in url:
                return json.dumps(self.fixture["submissions"]).encode("utf-8")
            if "/api/xbrl/companyfacts/" in url:
                return json.dumps(self.fixture["companyfacts"]).encode("utf-8")
            if "-index-headers.html" in url:
                return self.fixture["filing_headers"][ACC]["raw"].encode("utf-8")
            raise AssertionError("Unexpected request " + url)

        self.client = SecCapture(identity="Research Audit audit@example.org",
                                 transport=fake, clock=lambda: 20.0,
                                 sleeper=lambda n: self.sleeps.append(n))

    def test_exact_three_sec_get_and_structural_only(self):
        data = capture_one("ABNB", CIK, None,
                           client=self.client,
                           clock_utc=lambda: datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(data["observed_at_utc"], data["asof_utc"])
        self.assertEqual(data["observed_at_utc"], "2026-11-08T19:00:00+00:00")
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))
        self.assertTrue(all(agent == "Research Audit audit@example.org" for _, _, agent in self.calls))
        self.assertTrue(all(url.startswith("https://") for url, _, _ in self.calls))
        self.assertTrue(all(url.startswith("https://www.sec.gov/") or
                            url.startswith("https://data.sec.gov/") for url, _, _ in self.calls))
        self.assertEqual(len(self.sleeps), 2)
        self.assertEqual(analyze(data, {"ABNB"})["status"],
                         "OFFLINE_STRUCTURE_PASS_NOT_LIVE")

    def test_disallowed_host_or_path_holds(self):
        for url in ("https://evil.example/CIK0001559720.json",
                    "http://data.sec.gov/submissions/CIK0001559720.json",
                    "https://data.sec.gov/other/path",
                    "https://www.sec.gov/Archives/edgar/data/1559720/secrets.json",
                    "https://www.sec.gov/Archives/edgar/data/1559720/000155972026000011/0001559720-26-000011-index-headers.html?forward=x"):
            with self.subTest(url=url), self.assertRaises(ShadowHold):
                safe_url(url)

    def test_identity_required(self):
        for value in ("", "anonymous", "someone@example.org", "bad\nmail address@example.org"):
            with self.subTest(identity=value), self.assertRaises(ShadowHold):
                SecCapture(identity=value, transport=lambda *a: b"{}")

    def test_future_source_collected_after_asof_holds(self):
        with self.assertRaisesRegex(ShadowHold, "HISTORICAL_SEC_RETRIEVAL_NOT_PIT"):
            capture_one("ABNB", CIK, "2026-11-06T21:00:00+00:00",
                        client=self.client,
                        clock_utc=lambda: datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(self.calls, [])

    def test_future_cutoff_cannot_misstate_historical_pit(self):
        with self.assertRaisesRegex(ShadowHold, "HISTORICAL_SEC_RETRIEVAL_NOT_PIT"):
            capture_one("ABNB", CIK, "2099-01-01T00:00:00+00:00",
                        client=self.client,
                        clock_utc=lambda: datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(self.calls, [])

    def test_current_capture_keeps_pit_unproven(self):
        data = capture_one("ABNB", CIK, None, client=self.client,
                           clock_utc=lambda: datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc))
        result = analyze(data, {"ABNB"})
        self.assertFalse(result["historical_pit_proven"])
        self.assertFalse(result["independent_sec_origin_proven"])
        self.assertFalse(result["may_change_al"])

    def test_transport_exception_holds_before_read(self):
        client = SecCapture(identity="Research Audit audit@example.org",
                            transport=lambda *args: (_ for _ in ()).throw(ShadowHold("SEC_HTTP_UNAVAILABLE")))
        with self.assertRaisesRegex(ShadowHold, "SEC_HTTP_UNAVAILABLE"):
            capture_one("ABNB", CIK, None, client=client)


if __name__ == "__main__":
    unittest.main()
