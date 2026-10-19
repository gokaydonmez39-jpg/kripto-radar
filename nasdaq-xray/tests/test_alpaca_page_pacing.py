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
        ):
            with self.subTest(file=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                portion = source.split("def " + function + "(", 1)[1].split(
                    "\ndef ", 1
                )[0]
                self.assertIn("PACER.pace()", portion, "PAGE_LEVEL_PACING_MISSING")
                self.assertIn("urllib.request.urlopen(", portion)

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
