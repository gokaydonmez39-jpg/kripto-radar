"""A37 negative-fixture audit; no vendor traffic or real signals."""
import copy
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
from market_strength_a37 import (analyze, official_sessions, ShadowBlocked,
                                  EXPECTED_UNIVERSE)

ASOF = "2026-10-28"
SESSIONS = official_sessions(ASOF)
CUTOFF = "2026-10-29T00:00:00Z"
SYMBOLS = json.loads((Path(__file__).resolve().parents[1] / "nasdaq_watchlist_477.json").read_text(encoding="utf-8"))["liquidity_watch_symbols"]
TEST_SCOPE_SHA = hashlib.sha256(("\n".join(SYMBOLS)+"\n").encode()).hexdigest()

def fixture():
    base = datetime(2026, 10, 28, 21, 0, tzinfo=timezone.utc)
    def series(symbol, start, growth=0.001):
        return [{"session": d, "symbol": symbol, "feed":"iex", "basis":"raw",
                 "known_at_utc": (base + timedelta(seconds=20)).isoformat(),
                 "close": start * (1 + growth * i), "volume":10000+i}
                for i, d in enumerate(SESSIONS)]
    return dict(asof=ASOF, cutoff_utc=CUTOFF, symbols=SYMBOLS[:],
                bars={s:series(s, 50+ix*.1) for ix,s in enumerate(SYMBOLS)},
                benchmark=series("QQQ", 400, 0.0005), feed="iex", basis="raw", expected_scope_sha256=TEST_SCOPE_SHA)

class TestA37(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = fixture()

    def runbad(self, mutate, expected):
        x = copy.deepcopy(self.good)
        mutate(x)
        with self.assertRaisesRegex(ShadowBlocked, expected):
            analyze(**x)

    def test_positive_and_permissions(self):
        r=analyze(**self.good)
        self.assertEqual(r["universe"], 477)
        self.assertEqual(r["complete_official_sessions"],64)
        self.assertEqual(r["breadth_above_sma20_count"],477)
        self.assertEqual(r["breadth_above_sma50_count"],477)
        self.assertGreater(r["per_symbol_research"][SYMBOLS[0]]["relative_return_vs_qqq_63_sessions_pct"], 0)
        for k in ("may_generate_al","may_change_stops","may_write_sheets","may_emit_alert","may_trade"):
            self.assertIs(r[k],False)
        self.assertEqual(r["market_strength_site_calls"],0)
        self.assertTrue(r["canonical_scope_verified"])
        self.assertFalse(r["raw_source_provenance_independently_verified"])

    def test_replay_deterministic(self):
        self.assertEqual(analyze(**self.good), analyze(**self.good))

    def test_missing_one_symbol(self):
        self.runbad(lambda x: x["bars"].pop(SYMBOLS[1]), "MISSING_EXTRA_OR_DUPLICATE_SCOPE")

    def test_extra_symbol(self):
        self.runbad(lambda x: x["bars"].update({"ZZZ":x["bars"][SYMBOLS[1]]}), "MISSING_EXTRA_OR_DUPLICATE_SCOPE")

    def test_bad_universe_size(self):
        self.runbad(lambda x: x["symbols"].pop(), "WRONG_UNIVERSE_SIZE")

    def test_duplicate_symbol_scope(self):
        self.runbad(lambda x: x["symbols"].__setitem__(1, x["symbols"][0]), "DUPLICATE_UNIVERSE")

    def test_universe_order_bound(self):
        self.runbad(lambda x: x["symbols"].reverse(), "SCOPE_SHA_MISMATCH")

    def test_gapped_session(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]].pop(), "MISSING_OR_EXTRA_SESSIONS")

    def test_duplicate_session(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][1].update(session=SESSIONS[0]), "GAP_DUPLICATE_OR_WRONG_SESSION")

    def test_lookahead(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][1].update(known_at_utc="2026-10-29T00:01:00Z"), "LOOKAHEAD_KNOWN_AT")

    def test_premature_bar(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][0].update(known_at_utc=SESSIONS[0]+"T12:00:00Z"), "PREMATURE_FINAL_BAR")

    def test_mixed_feed(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][0].update(feed="sip"), "MIXED_FEED_OR_BASIS")

    def test_mixed_basis(self):
        self.runbad(lambda x: x["benchmark"][0].update(basis="split"), "MIXED_FEED_OR_BASIS")

    def test_zero_price(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][3].update(close=0), "INVALID_NUMERIC_VALUE")

    def test_nan_price(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][3].update(close=float("nan")), "INVALID_NUMERIC_VALUE")

    def test_boolean_volume(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][3].update(volume=True), "INVALID_NUMERIC_TYPE")

    def test_missing_known_at(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][3].pop("known_at_utc"), "MISSING_KNOWN_AT")

    def test_naive_known_at(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]][3].update(known_at_utc="2026-10-29T00:00:00"), "NAIVE_KNOWN_AT")

    def test_pinned_authority_sha(self):
        self.runbad(lambda x: x.update(expected_scope_sha256="0"*64), "UNAPPROVED_SCOPE_SHA_OVERRIDE")

    def test_unsupported_feed(self):
        self.runbad(lambda x: x.update(feed="marketstrength"), "UNAUTHORIZED_FEED_OR_BASIS")

    def test_unsupported_adjustment(self):
        self.runbad(lambda x: x.update(basis="all"), "UNAUTHORIZED_FEED_OR_BASIS")

    def test_incomplete_asof(self):
        self.runbad(lambda x: x.update(asof="2026-10-29",cutoff_utc="2026-10-29T16:00:00Z"), "ASOF_NOT_COMPLETED")

    def test_non_session(self):
        self.runbad(lambda x: x.update(asof="2026-10-24"), "NOT_XNAS_SESSION")

    def test_benchmark_removed(self):
        self.runbad(lambda x: x.update(benchmark=[]), "MISSING_OR_EXTRA_SESSIONS")

    def test_benchmark_in_scope(self):
        self.runbad(lambda x: x.update(symbols=sorted(["QQQ"]+SYMBOLS[:-1])), "SCOPE_SHA_MISMATCH")

    def test_coverage_not_rescued_by_52(self):
        self.runbad(lambda x: x["bars"][SYMBOLS[0]].__setitem__(slice(0,12),[]), "MISSING_OR_EXTRA_SESSIONS")

    def test_early_close_calendar(self):
        days=official_sessions("2026-11-27")
        self.assertEqual(len(days),64)
        self.assertEqual(days[-1],"2026-11-27")

    def test_weekend_not_session(self):
        with self.assertRaisesRegex(ShadowBlocked,"NOT_XNAS_SESSION"):
            official_sessions("2026-10-31")

    def test_decisive_equal_sma(self):
        x=copy.deepcopy(self.good)
        for sym in x["symbols"]:
            for row in x["bars"][sym]:
                row["close"]=100.0
        r=analyze(**x)
        self.assertEqual(r["breadth_above_sma20_count"],0)
        self.assertEqual(r["breadth_above_sma50_count"],0)

if __name__ == "__main__":
    unittest.main()
