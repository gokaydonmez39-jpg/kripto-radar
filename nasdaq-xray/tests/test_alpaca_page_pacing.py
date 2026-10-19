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
