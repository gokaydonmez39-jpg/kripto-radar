"""Negative-first, deterministic tests. No real bars, securities or market APIs."""
from copy import deepcopy
import math
import unittest

from tradinghub_methodology_shadow import (
    NO_AUTHORITY, SOURCE, _matrix, _sharpe, costed_long_trade,
    cpcv_audit, cpcv_folds, pbo_cscv, synthetic_fixture,
    synthetic_report, walk_forward_audit, walk_forward_folds,
)


class TradingHubMethodShadowTests(unittest.TestCase):
    def setUp(self):
        self.rows = synthetic_fixture()

    def test_source_release_pinned_no_unreviewed_change(self):
        self.assertEqual(SOURCE["commit"],
                         "9c17ef1957ccd20ad2b04feadf2c69241504a86b")
        self.assertEqual(SOURCE["release"], "v1.1.0")
        self.assertIn("COMMONS_CLAUSE", SOURCE["license"])

    def test_synthetic_output_discloses_no_real_evidence(self):
        x = synthetic_report()
        self.assertEqual(x["schema"], "XRAY_TRADINGHUB_METHOD_COMPARISON_SHADOW_V1")
        self.assertEqual(x["data"], "SYNTHETIC_ONLY")
        self.assertEqual(x["network_requests"], 0)
        self.assertEqual(x["production_scope_symbols_evaluated"], 0)
        self.assertEqual(x["comparison"]["numeric_cross_language_parity"], "NOT_TESTED")
        self.assertEqual(x["conclusion"], "RESEARCH_ONLY_NO_SIGNAL_OR_PRODUCTION_CHANGE")
        self.assertTrue(all(v is False for v in x["no_authority"].values()))

    def test_same_seed_is_reproducible(self):
        self.assertEqual(synthetic_fixture(), synthetic_fixture())
        self.assertNotEqual(synthetic_fixture(101), synthetic_fixture(102))

    def test_252_cscv_splits_for_ten_blocks(self):
        p = pbo_cscv(self.rows)
        self.assertEqual(p["splits"], 252)
        self.assertTrue(0 <= p["pbo"] <= 1)
        self.assertTrue(0 <= p["oos_loss_fraction"] <= 1)

    def test_planted_edge_is_only_synthetic_not_alpha(self):
        p = pbo_cscv(self.rows)
        self.assertLess(p["pbo"], 0.2)
        self.assertGreater(
            walk_forward_audit(self.rows)["selected_net_synthetic_units"],
            walk_forward_audit(self.rows)["fixed_baseline_net_synthetic_units"])

    def test_precommitted_noise_null_average_is_not_extreme(self):
        # Predeclared before running these particular seeds: 2000..2009.
        # This is a coarse synthetic null sanity check, NOT a proof of calibration.
        import random
        values = []
        for seed in range(2000, 2010):
            rng = random.Random(seed)
            noise = [[rng.gauss(0, 1) for _ in range(320)]
                     for _ in range(8)]
            values.append(pbo_cscv(noise)["pbo"])
        mean = sum(values) / len(values)
        self.assertGreaterEqual(mean, 0.30, values)
        self.assertLessEqual(mean, 0.70, values)

    def test_identical_zero_pnl_is_conservative_no_edge(self):
        # ASC rank ties map to worst rank: do not claim alpha from no variation.
        p = pbo_cscv([[0.0] * 320 for _ in range(8)])
        self.assertEqual(p["splits"], 252)
        self.assertEqual(p["pbo"], 1.0)
        self.assertEqual(p["oos_loss_fraction"], 1.0)

    def test_cscv_rejects_underlength_data(self):
        with self.assertRaisesRegex(ValueError, "PBO_BLOCKS_REQUIRE"):
            pbo_cscv([list(range(30)) for _ in range(4)])

    def test_cscv_rejects_odd_blocks(self):
        with self.assertRaisesRegex(ValueError, "PBO_BLOCKS_REQUIRE"):
            pbo_cscv(self.rows, blocks=9)

    def test_nonfinite_and_boolean_pnl_rejected(self):
        for v in [math.nan, math.inf, -math.inf, True]:
            rows = deepcopy(self.rows)
            rows[0][0] = v
            with self.subTest(v=str(v)), self.assertRaisesRegex(ValueError, "INVALID_PNL"):
                _matrix(rows)

    def test_ragged_matrix_rejected(self):
        rows = deepcopy(self.rows)
        rows[3].pop()
        with self.assertRaisesRegex(ValueError, "RAGGED_PNL_MATRIX"):
            pbo_cscv(rows)

    def test_insufficient_candidates_rejected(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_CANDIDATES"):
            pbo_cscv(self.rows[:3])

    def test_rolling_folds_are_past_only_with_15_session_purge(self):
        folds = walk_forward_folds(320, 80, 20, 15)
        self.assertEqual(len(folds), 12)
        all_test = []
        for train, test in folds:
            self.assertEqual(len(train), 65)
            self.assertEqual(len(test), 20)
            self.assertLess(max(train) + 15, min(test))
            self.assertTrue(set(train).isdisjoint(test))
            all_test.extend(test)
        self.assertEqual(len(all_test), len(set(all_test)))
        self.assertEqual(all_test, list(range(80, 320)))

    def test_rolling_bad_train_history_rejected(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_WALK_FORWARD_HISTORY"):
            walk_forward_folds(100, 20, 20, 15)

    def test_rolling_rejects_zero_purge_or_bool(self):
        for p in (0, True):
            with self.assertRaisesRegex(ValueError, "INVALID_PURGE"):
                walk_forward_folds(320, 80, 20, p)

    def test_28_cpcv_pair_folds_and_each_group_seven_times(self):
        folds = cpcv_folds(320, 8, 15, 15)
        self.assertEqual(len(folds), 28)
        hits = [0] * 8
        for f in folds:
            for group in f["groups"]:
                hits[group] += 1
        self.assertEqual(hits, [7] * 8)
        self.assertEqual(cpcv_audit(self.rows)["test_appearances_per_group"],
                         [7] * 8)

    def test_cpcv_has_no_label_overlap_or_embargo_leak(self):
        folds = cpcv_folds(320, 8, 15, 15)
        for f in folds:
            self.assertTrue(set(f["train"]).isdisjoint(f["test"]))
            for i in f["train"]:
                for g in f["groups"]:
                    start = 320 * g // 8
                    end = 320 * (g + 1) // 8
                    self.assertFalse(i + 15 >= start and i < end + 15)

    def test_cpcv_rejects_short_or_invalid_history(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_CPCV_HISTORY"):
            cpcv_folds(100, 8, 15, 15)
        with self.assertRaisesRegex(ValueError, "INVALID_EMBARGO"):
            cpcv_folds(320, 8, 15, 0)

    def test_cost_zero_is_gross(self):
        x = costed_long_trade(100, 101, 10, 0, 0)
        self.assertEqual(x["gross_usd"], 10)
        self.assertEqual(x["net_usd"], 10)
        self.assertEqual(x["cost_usd"], 0)

    def test_cost_arithmetic_independent_formula(self):
        x = costed_long_trade(100, 101, 10, 4, 5)
        buy, sell = 100.05, 100.9495
        fees = (buy + sell) * 10 * 4 / 10000
        self.assertAlmostEqual(x["net_usd"], round((sell-buy)*10-fees, 8))
        self.assertGreater(x["cost_usd"], 0)
        self.assertLess(x["net_usd"], x["gross_usd"])

    def test_cost_can_turn_small_gain_negative(self):
        x = costed_long_trade(100, 100.01, 10, 10, 10)
        self.assertGreater(x["gross_usd"], 0)
        self.assertLess(x["net_usd"], 0)

    def test_no_free_profit_from_increasing_cost(self):
        low = costed_long_trade(100, 101, 10, 1, 1)
        high = costed_long_trade(100, 101, 10, 20, 20)
        self.assertLess(high["net_usd"], low["net_usd"])

    def test_nonfinite_or_negative_trade_inputs_fail(self):
        for params in [
            (math.nan, 101, 10, 4, 5), (100, 101, 0, 4, 5),
            (100, 101, 10, -1, 5), (100, 101, 10, 4, math.inf),
            (100, 101, 10, 4, 10000),
        ]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                costed_long_trade(*params)

    def test_sharpe_constant_zero(self):
        self.assertEqual(_sharpe([0.0] * 8), 0.0)

    def test_no_authority_contract(self):
        self.assertFalse(any(NO_AUTHORITY.values()))
        self.assertEqual(set(NO_AUTHORITY), {
            "may_generate_al", "may_change_stops",
            "may_write_private_sheet", "may_send_notification",
            "may_place_order", "may_fetch_market_data",
            "may_use_private_credentials", "alpha_proven",
            "csharp_binary_parity_verified",
        })


if __name__ == "__main__":
    unittest.main()
