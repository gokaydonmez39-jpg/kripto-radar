"""Offline regressions: 200/min historical SIP per-account cap, no provider I/O."""
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SimulatedClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        assert delay >= 0
        self.waits.append(delay)
        self.now += delay


class PageQuotaContract(unittest.TestCase):
    def test_paginated_provider_callsites_must_pace_each_http_page(self):
        # A batch-level sleep does not protect 32 pages per 8-ticker group.
        for name, function in (
            ("alpaca_personal_joint_260_d30_rth_shadow.py", "pager"),
            ("alpaca_personal_price_20261013_exact30_census.py", "fetch"),
            ("alpaca_free_sip_shadow_guard.py", "fetch_page"),
        ):
            with self.subTest(file=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                portion = source.split("def " + function + "(", 1)[1].split(
                    "\ndef ", 1
                )[0]
                self.assertIn("PACER.pace()", portion, "PAGE_LEVEL_PACING_MISSING")
                self.assertIn("urllib.request.urlopen(", portion)

    def test_full_universe_coverage_paces_each_paginated_http_attempt(self):
        # This is a separate 1Day coverage endpoint, not the shared 260D pager.
        source = (ROOT / "alpaca_full_universe_asof_sip_availability.py").read_text(
            encoding="utf-8"
        )
        portion = source.split("def query_sip(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("with opener(", portion)
        self.assertIn("PACER.pace()", portion, "COVERAGE_HTTP_PAGE_PACING_MISSING")

        # A real two-page *offline* transport must debit AND pace each page.
        import json
        from unittest.mock import patch
        import alpaca_full_universe_asof_sip_availability as sip

        returned = [
            {"bars": {"AAPL": []}, "next_page_token": "NEXT_PAGE"},
            {"bars": {"AAPL": []}, "next_page_token": None},
        ]
        urls = []

        class MockResponse:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(self.data).encode()

        def opener(req, timeout):
            self.assertEqual(timeout, 24)
            urls.append(req.full_url)
            return MockResponse(returned[len(urls) - 1])

        budget = sip.RequestBudget(3)
        with patch.object(sip.PACER, "pace") as pacing:
            result, count = sip.query_sip(
                ["AAPL"], "2026-10-16", "OFFLINE_KEY", "OFFLINE_SECRET",
                opener=opener, budget=budget,
                window_fn=lambda *_: ("2026-10-16T00:00:00Z",
                                     "2026-10-16T23:00:00Z"),
            )
        self.assertEqual((count, budget.used, len(urls)), (2, 2, 2))
        self.assertEqual(pacing.call_count, 2, "EVERY_PAGE_MUST_BE_PACED")
        self.assertEqual(result, {"AAPL": []})
        self.assertNotIn("page_token=", urls[0])
        self.assertIn("page_token=NEXT_PAGE", urls[1])


    def test_account_wide_workflow_mutex_and_intra_workflow_serial_io(self):
        import yaml
        files = (
            "xray-personal-full-universe-sip-coverage.yml",
            "xray-candidate-local-alpaca-sip-recovery.yml",
            "xray-personal-full-cohort-early-watch.yml",
            "xray-alpaca-delayed-sip-research.yml",
        )
        for name in files:
            with self.subTest(name=name):
                x = yaml.load(
                    (ROOT.parent / ".github" / "workflows" / name).read_text(),
                    Loader=yaml.BaseLoader,
                )
                self.assertEqual(
                    x["concurrency"]["group"],
                    "xray-alpaca-historical-sip-account-${{ github.event_name == 'pull_request' && github.event.pull_request.number || 'production' }}",
                )
                self.assertEqual(x["concurrency"]["cancel-in-progress"], "false")
                self.assertEqual(
                    x["concurrency"].get("queue"), "max",
                    "GITHUB_SINGLE_PENDING_LAST_WRITER_CANCELS_RESEARCH_SCAN",
                )
                self.assertEqual(x["concurrency"]["group"],
                    "xray-alpaca-historical-sip-account-${{ github.event_name == 'pull_request' && github.event.pull_request.number || 'production' }}",
                    "PR_OFFLINE_RUN_MUST_NOT_STARVE_PRODUCTION_ACCOUNT_MUTEX")
        candidate = yaml.load(
            (ROOT.parent / ".github" / "workflows" / files[1]).read_text(),
            Loader=yaml.BaseLoader,
        )
        price = candidate["jobs"]["personal-price-current-exact30"]
        self.assertEqual(price["needs"], ["session-gate", "source-recovery"])
        self.assertIn("needs.source-recovery.result == 'success'", price["if"])

    def test_push_triggered_secondary_sip_workflows_share_production_quota_mutex(self):
        # Both workflows run on a main push that modifies shared SIP guard code.
        # A distinct lock allows their vendor requests to overlap with the daily
        # SIP full-universe scan although all use the SAME provider account.
        import yaml
        expected = (
            "xray-alpaca-historical-sip-account-"
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.number || 'production' }}"
        )
        for name in (
            "xray-alpaca-free-sip-shadow-proof.yml",
            "xray-alpaca-full-515-260-sip-shadow.yml",
        ):
            with self.subTest(workflow=name):
                wf = yaml.load(
                    (ROOT.parent / ".github" / "workflows" / name).read_text(),
                    Loader=yaml.BaseLoader,
                )
                self.assertIn("push", wf["on"])
                self.assertEqual(
                    wf["concurrency"]["group"], expected,
                    "SECONDARY_HTTP_WORKFLOW_ESCAPES_SHARED_ACCOUNT_LOCK",
                )
                self.assertEqual(wf["concurrency"].get("queue"), "max")
                self.assertEqual(wf["concurrency"]["cancel-in-progress"], "false")

    def test_all_secondary_sip_workflows_share_account_lock_and_keep_pr_offline(self):
        import yaml
        expected = (
            "xray-alpaca-historical-sip-account-"
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.number || 'production' }}"
        )
        target = {
            "xray-p0-alpaca-515-raw-split.yml":
                "Measure current 515 raw + split pairs with same session mapping ASOF",
            "xray-personal-seven-sip-technical.yml":
                "Run actual SIP 260 daily/52 weekly A-B-D/R1 technical research",
            "xray-candidate-local-price-50-page.yml":
                "One-ticker historical SIP 1Day plus 30Min official 30 sessions",
        }
        for filename, vendor_step_name in target.items():
            with self.subTest(workflow=filename):
                cfg = yaml.load(
                    (ROOT.parent / ".github" / "workflows" / filename).read_text(),
                    Loader=yaml.BaseLoader,
                )
                self.assertEqual(cfg["concurrency"]["group"], expected)
                self.assertEqual(cfg["concurrency"]["cancel-in-progress"], "false")
                self.assertEqual(cfg["concurrency"]["queue"], "max")
                self.assertIn("pull_request", cfg["on"])
                steps = next(iter(cfg["jobs"].values()))["steps"]
                vendor = next(x for x in steps if x.get("name") == vendor_step_name)
                self.assertIn("github.event_name != 'pull_request'", vendor["if"])
                self.assertIn("github.ref == 'refs/heads/main'", vendor["if"])
                for step in steps:
                    if (step.get("name", "").startswith(("Verify exact current", "Assert 50-symbol",
                           "Verify no canonical", "Validate exact full"))
                            or "upload-artifact" in step.get("uses", "")):
                        self.assertIn("github.event_name != 'pull_request'",
                                      step.get("if", ""), "PR_MUST_NOT_REQUIRE_VENDOR_ARTIFACT")
        path = ROOT.parent / ".github" / "workflows" / (
            "xray-personal-current-sip-price-unknown-shadow.yml"
        )
        current = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(current["concurrency"]["group"], expected)
        self.assertEqual(current["concurrency"]["cancel-in-progress"], "false")
        self.assertEqual(current["concurrency"]["queue"], "max")
        step = next(
            x for x in next(iter(current["jobs"].values()))["steps"]
            if x.get("name", "").startswith("Current main only")
        )
        self.assertIn("workflow_dispatch", step["if"])
        self.assertIn("refs/heads/main", step["if"])

    def test_pacer_monotonic_actual_spacing_and_clock_regression(self):
        mod = importlib.import_module("alpaca_sip_request_pacer")
        fake = SimulatedClock()
        pacer = mod.SipRequestPacer(clock=fake.monotonic, sleeper=fake.sleep)
        self.assertGreaterEqual(mod.MIN_INTERVAL_SECONDS, 0.65)
        marks = []
        for _ in range(210):
            pacer.pace()
            marks.append(fake.now)
        self.assertTrue(all(b-a >= 0.65-1e-8
                            for a,b in zip(marks, marks[1:])))
        # Any rolling 60-second interval has < 100 calls per single process.
        self.assertTrue(all(sum(t <= x < t+60 for x in marks) <= 95
                            for t in (0,30,60,90)))
        self.assertEqual(len(fake.waits), 209)
        fake.now -= 10
        with self.assertRaisesRegex(ValueError, "MONOTONIC_CLOCK_REGRESSION"):
            pacer.pace()

    def test_invalid_intervals_fail_closed(self):
        mod = importlib.import_module("alpaca_sip_request_pacer")
        for v in (0, -1, float("nan"), float("inf"), True, 0.05):
            with self.subTest(value=v):
                with self.assertRaises(ValueError):
                    mod.SipRequestPacer(interval=v)


if __name__ == "__main__":
    unittest.main()
