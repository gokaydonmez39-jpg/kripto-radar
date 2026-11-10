"""Forward-only 477 NASDAQ PIT membership regression; no IEX or private Sheet writes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import runner

WATCHLIST = Path(__file__).with_name("nasdaq_watchlist_477.json")


def check_asof(day, watchlist=WATCHLIST):
    return runner.get_scope(watchlist_file=str(watchlist), asof=day)


class ForwardGntxPITTests(unittest.TestCase):
    def setUp(self):
        self.original = json.loads(WATCHLIST.read_text(encoding="utf-8"))

    def test_historical_9_nov_not_falsely_rewritten(self):
        old = check_asof("2026-11-09")
        self.assertEqual(len(old), 477)
        self.assertIn("ROKU", old)
        self.assertNotIn("GNTX", old)
        self.assertIn("SUPN", old)

    def test_10_nov_forward_scope_replaces_only_roku(self):
        old, new = check_asof("2026-11-09"), check_asof("2026-11-10")
        self.assertEqual(len(new), 477)
        self.assertEqual(len(set(new)), 477)
        self.assertEqual(sum(a != b for a,b in zip(old,new)), 1)
        idx = old.index("ROKU")
        self.assertEqual(new[idx], "GNTX")
        self.assertIn("FOXA", new)
        self.assertEqual(new.count("FOXA"), 1)
        self.assertNotIn("ROKU", new)

    def test_11_nov_keeps_forward_identity(self):
        self.assertEqual(check_asof("2026-11-11"), check_asof("2026-11-10"))

    def test_3_nov_indv_to_supn_unchanged(self):
        self.assertIn("INDV", check_asof("2026-11-02"))
        self.assertIn("SUPN", check_asof("2026-11-03"))
        self.assertNotIn("INDV", check_asof("2026-11-03"))

    def test_static_watchlist_preserves_historical_identity(self):
        self.assertIn("ROKU", self.original["liquidity_watch_symbols"])
        self.assertNotIn("GNTX", self.original["liquidity_watch_symbols"])
        self.assertEqual(len(self.original["liquidity_watch_symbols"]), 477)

    def test_pre_cutover_membership_and_fingerprint_unchanged(self):
        early = check_asof("2026-11-06")
        self.assertEqual(
            runner.sha_symbols(early),
            "4045849b129e74a600982db512f2e5ad5343a960544476721ca552544f328a20"
        )

    def test_foreign_unreviewed_third_transition_is_refused(self):
        bad = copy.deepcopy(self.original)
        bad["point_in_time_symbol_changes"].append({
            "effective_asof_et":"2026-11-11", "old_symbol":"AAPL", "new_symbol":"MSFT"
        })
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"watch.json"
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"UNREVIEWED_PIT_CHANGE_REGISTRY"):
                check_asof("2026-11-11",p)

    def test_replacement_collision_is_refused(self):
        bad = copy.deepcopy(self.original)
        bad["liquidity_watch_symbols"][-1] = "GNTX"
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"watch.json"
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"PIT_SYMBOL_IDENTITY_COLLISION"):
                check_asof("2026-11-10",p)

    def test_new_member_identity_source_tamper_is_refused(self):
        bad = copy.deepcopy(self.original)
        bad["point_in_time_symbol_changes"][1]["replacement_issuer_sec"] = "https://untrusted.invalid"
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"watch.json"
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"UNREVIEWED_PIT_SYMBOL_CHANGE"):
                check_asof("2026-11-10",p)

    def test_no_10_nov_membership_without_user_approved_registry(self):
        bad = copy.deepcopy(self.original)
        bad["point_in_time_symbol_changes"] = bad["point_in_time_symbol_changes"][:1]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"watch.json"
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"UNREVIEWED_PIT_CHANGE_REGISTRY"):
                check_asof("2026-11-10",p)

    def test_future_not_backfill_and_asof_validation(self):
        with self.assertRaisesRegex(ValueError, "INVALID_PIT_ASOF"):
            check_asof("2026-11-09XXX")
        self.assertNotIn("GNTX", check_asof("2026-11-09"))
        self.assertEqual(check_asof("2026-11-10").count("GNTX"),1)

    def test_does_not_contaminate_existing_foxa_and_supn_members(self):
        syms=check_asof("2026-11-10")
        self.assertEqual(syms.count("FOXA"),1)
        self.assertEqual(syms.count("SUPN"),1)


if __name__ == "__main__":
    unittest.main()
