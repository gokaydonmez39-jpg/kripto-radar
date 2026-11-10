"""Synthetic XNAS date-shape tests, not provider/market or OOS evidence."""
import copy
import unittest
import exchange_calendars as xc
from candidate_symbol_history_gate import assess

class HistoryEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = xc.get_calendar("XNAS")
        cls.universe = ["AAPL", "CRWV", "NBIS"] + [f"Z{i:04d}" for i in range(474)]
        cls.aapl = [v.strftime("%Y-%m-%d") for v in
                    c.sessions_in_range("2024-09-03", "2026-11-06")]
        cls.crwv = [v.strftime("%Y-%m-%d") for v in
                    c.sessions_in_range("2025-03-28", "2026-11-06")]
        cls.nbis = [v.strftime("%Y-%m-%d") for v in
                    c.sessions_in_range("2024-10-21", "2026-11-06")]
        cls.rows = {
            "AAPL": {"sessions": cls.aapl, "feed": "iex", "basis": "RAW"},
            "CRWV": {"sessions": cls.crwv, "feed": "iex", "basis": "RAW"},
            "NBIS": {"sessions": cls.nbis, "feed": "iex", "basis": "RAW"}
        }

    def test_membership_kept_at_477(self):
        out = assess(self.universe, "2026-11-06", self.rows)
        self.assertEqual(out["universe_covered"], 477)
        self.assertEqual(len(out["records"]), 477)
        self.assertEqual(out["counts"]["UNKNOWN_HISTORY"], 474)
        self.assertFalse(out["can_use_for_production"])

    def test_new_listing_not_fabricated(self):
        out = assess(self.universe, "2026-11-06", self.rows)
        rows = {r["symbol"]: r for r in out["records"]}
        self.assertEqual(rows["CRWV"]["observed_sessions"], 406)
        self.assertEqual(rows["CRWV"]["status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(rows["AAPL"]["status"], "DATE_SHAPE_500_PASS_ONLY")
        self.assertEqual(rows["NBIS"]["status"], "DATE_SHAPE_500_PASS_ONLY")
        self.assertFalse(out["first_known_at_verified"])
        self.assertFalse(out["real_pit_verified"])

    def test_missing_session_hold(self):
        v = copy.deepcopy(self.rows)
        v["AAPL"]["sessions"].pop(200)
        self.assertEqual(assess(self.universe, "2026-11-06", v)["records"][0]["status"],
                         "GAPPED_HISTORY_HOLD")

    def test_future_rejected(self):
        v = copy.deepcopy(self.rows)
        v["CRWV"]["sessions"].append("2026-11-09")
        with self.assertRaisesRegex(ValueError, "FUTURE_SESSION"):
            assess(self.universe, "2026-11-06", v)

    def test_wrong_tape_rejected(self):
        v = copy.deepcopy(self.rows)
        v["AAPL"]["feed"] = "sip"
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_TAPE_OR_ADJUSTMENT"):
            assess(self.universe, "2026-11-06", v)

    def test_duplicate_rejected(self):
        v = copy.deepcopy(self.rows)
        v["AAPL"]["sessions"][1] = v["AAPL"]["sessions"][0]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_NONMONOTONIC_SESSIONS"):
            assess(self.universe, "2026-11-06", v)

    def test_weekend_rejected(self):
        v = copy.deepcopy(self.rows)
        v["CRWV"]["sessions"][6] = "2025-04-05"
        with self.assertRaisesRegex(ValueError, "NON_XNAS_SESSION_IN_HISTORY"):
            assess(self.universe, "2026-11-06", v)

    def test_universe_size_rejected(self):
        with self.assertRaisesRegex(ValueError, "REQUIRES_FIXED_477_UNIVERSE"):
            assess(["AAPL"], "2026-11-06", self.rows)

    def test_unknown_symbol_rejected(self):
        v = copy.deepcopy(self.rows)
        v["FAKE"] = {"sessions": self.crwv, "feed": "iex", "basis": "RAW"}
        with self.assertRaisesRegex(ValueError, "UNKNOWN_HISTORY_SYMBOL"):
            assess(self.universe, "2026-11-06", v)

    def test_duplicate_universe_rejected(self):
        v = self.universe.copy()
        v[2] = v[0]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_UNIVERSE_SYMBOL"):
            assess(v, "2026-11-06", self.rows)

    def test_stale_rejected(self):
        v = copy.deepcopy(self.rows)
        v["AAPL"]["sessions"].pop()
        self.assertEqual(assess(self.universe, "2026-11-06", v)["records"][0]["status"],
                         "STALE_HISTORY_HOLD")

if __name__ == "__main__":
    unittest.main()
