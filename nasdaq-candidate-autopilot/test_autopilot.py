"""Positive and adversarial tests; synthetic data only; never performs network I/O."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from autopilot import (BATCH, GateError, candidate_url, evidence, parse_registry, plan)

HERE = Path(__file__).parent
RAW = (HERE / "registry.json").read_bytes()
DATA = json.loads(RAW)


class CandidateAutopilotTests(unittest.TestCase):
    def test_284_real_inventory_admitted(self):
        self.assertEqual(len(parse_registry(RAW)), 284)

    def test_expected_7_first_day(self):
        selection = plan(parse_registry(RAW), dt.date(2026, 11, 2))
        self.assertEqual(selection["eligible_count"], 249)
        self.assertEqual(selection["blocked_count"], 35)
        self.assertEqual(selection["cohort_pages"], 36)
        self.assertEqual([x["registry_id"] for x in selection["selected"]],
                         [2, 3, 11, 61, 83, 253, 255])

    def test_rotation_and_deterministic_receipt(self):
        date = dt.date(2026, 11, 3)
        a = evidence(RAW, date)
        self.assertEqual(a, evidence(RAW, date))
        self.assertEqual(a["selection"]["cohort_page"], 2)
        self.assertEqual(a["findings"][0]["tier"], "P0-EXISTING-CORE-VERIFY")
        self.assertTrue(all(x["integration_status"] == "NOT_INTEGRATED" for x in a["findings"]))

    def test_held_never_selected(self):
        entries = parse_registry(RAW)
        for offset in range(56):
            date = dt.date(2026, 11, 2) + dt.timedelta(days=offset)
            if date.weekday() >= 5:
                continue
            chosen = plan(entries, date)
            self.assertTrue(all(x["tier"] not in ("HOLD", "HOLD/SEPARATE")
                                for x in chosen["selected"]))

    def check_block(self, change):
        bad = copy.deepcopy(DATA)
        change(bad)
        with self.assertRaises(GateError):
            parse_registry(json.dumps(bad).encode())

    def test_duplicate_id_red(self):
        self.check_block(lambda d: d["entries"][1].update(registry_id=1))

    def test_scope_violation_red(self):
        self.check_block(lambda d: d.update(scope="CRYPTO"))

    def test_count_drift_red(self):
        self.check_block(lambda d: d["entries"].pop())

    def test_tier_drift_red(self):
        self.check_block(lambda d: d["entries"][0].update(recomputed_tier="P1-VALIDATE"))

    def test_http_url_red(self):
        self.check_block(lambda d: d["entries"][0].update(url="http://github.com/x/y"))

    def test_host_escapes_blocked(self):
        blocked = ["https://github.com.evil.test/u/r", "https://127.0.0.1/private",
                   "https://github.com@evil.test/u/r", "https://github.com:444/u/r",
                   "file:///etc/passwd", "https://github.com/u/r?token=x",
                   "https://github.com/u/r#fragment", "https://github.com/u"]
        self.assertTrue(all(candidate_url(url) is None for url in blocked))
        self.assertEqual(candidate_url("https://github.com/Graphify-Labs/graphify"),
                         "https://github.com/Graphify-Labs/graphify")

    def test_network_off_by_default(self):
        receipt = evidence(RAW, dt.date(2026, 11, 2))
        self.assertFalse(receipt["network_used"])
        self.assertFalse(receipt["automatic_promotion"])
        self.assertFalse(receipt["orders"])
        self.assertEqual(len(receipt["registry_sha256"]), 64)

    def test_bad_date_and_batch_red(self):
        items = parse_registry(RAW)
        with self.assertRaises(GateError):
            plan(items, dt.date(2026, 11, 1))
        with self.assertRaises(GateError):
            plan(items, dt.date(2026, 11, 2), batch=BATCH + 1)


if __name__ == "__main__":
    unittest.main()
