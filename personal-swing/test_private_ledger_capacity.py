"""Fail-first synthetic acceptance for private Sheets ledger read expansion.

No Google calls, private rows, trading, credentials or notification sends.
Run under normal Python and -O; the new limit must both pass and block.
"""
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import private_sheet_writer as writer
from test_private_sheet_writer import snapshot, RUN


def local_api(values):
    obj = writer.SheetApi.__new__(writer.SheetApi)
    paths = []
    def fake_request(path, **kwargs):
        paths.append(path)
        return {"values": values}
    obj.request = fake_request
    return obj, paths


class LedgerCapacityTests(unittest.TestCase):
    def test_open_range_reads_beyond_original_1000_rows(self):
        fake = [["HEADER"]] + [["row"] for _ in range(1100)]
        obj, paths = local_api(fake)
        got = obj.read("UYARI_OLAYLARI", "T")
        self.assertEqual(len(got), 1101)
        self.assertEqual(len(paths), 1)
        self.assertIn("'UYARI_OLAYLARI'!A1:T", unquote(paths[0]))
        self.assertNotIn("T1000", unquote(paths[0]))

    def test_upper_bound_passes_at_limit(self):
        with patch.object(writer, "MAX_ROWS", 5):
            obj, _ = local_api([["x"] for _ in range(5)])
            self.assertEqual(len(obj.read("ADAY_GECMISI", "M")), 5)

    def test_upper_bound_rejects_one_extra_row(self):
        with patch.object(writer, "MAX_ROWS", 5):
            obj, _ = local_api([["x"] for _ in range(6)])
            with self.assertRaisesRegex(writer.HandoffBlocked, "SHEET_READ_CAPACITY_REACHED"):
                obj.read("UYARI_OLAYLARI", "T")

    def test_invalid_sheets_payload_blocks(self):
        obj, _ = local_api(None)
        with self.assertRaisesRegex(writer.HandoffBlocked, "SHEET_READ_CAPACITY_REACHED"):
            obj.read("TARAMA_KAYITLARI", "J")

    def test_candidate_append_is_allowed_below_cap(self):
        c = [list(writer.CANDIDATE_HEADER)]
        s = [list(writer.SCAN_HEADER)]
        with patch.object(writer, "MAX_ROWS", 3):
            p = writer.plan(snapshot(), c, s, RUN, run_event="schedule")
        self.assertEqual(len(p["candidate_rows"]), 2)
        self.assertEqual(len(p["scan_rows"]), 1)

    def test_candidate_append_blocks_at_cap(self):
        c = [list(writer.CANDIDATE_HEADER)]
        s = [list(writer.SCAN_HEADER)]
        with patch.object(writer, "MAX_ROWS", 2):
            with self.assertRaisesRegex(writer.HandoffBlocked, "SHEET_CAPACITY_REACHED"):
                writer.plan(snapshot(), c, s, RUN, run_event="schedule")

    def test_production_cap_above_episode_budget_and_minimum(self):
        self.assertGreaterEqual(writer.MAX_ROWS, 4770 + 1)
        self.assertLessEqual(writer.MAX_ROWS, 20000)


if __name__ == "__main__":
    unittest.main()
