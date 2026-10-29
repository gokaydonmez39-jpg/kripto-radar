"""Regression for A37 metadata evidence receipts: fail closed on exaggerated claims."""
import copy
import json
from pathlib import Path
import unittest
from a37_source_receipt import validate, ReceiptRejected


ROOT=Path(__file__).resolve().parent
GOOD=json.loads((ROOT/"a37_connected_iex_20261028_receipt.json").read_text(encoding="utf-8"))

class TestReceipt(unittest.TestCase):
    def reject(self, fn, regex):
        x=copy.deepcopy(GOOD)
        fn(x)
        with self.assertRaisesRegex(ReceiptRejected, regex):
            validate(x)

    def test_good_aggregate_only(self):
        r=validate(GOOD)
        self.assertEqual(r["covered"],477)
        self.assertEqual(r["series"],478)
        self.assertEqual(r["required_bars"],30592)
        self.assertEqual(r["sma20_pct"],59.119497)
        self.assertEqual(r["sma50_pct"],45.91195)
        self.assertEqual(r["rs63_positive_pct"],34.591195)
        self.assertFalse(r["may_issue_al"])
        self.assertFalse(r["may_write_sheet"])
        self.assertFalse(r["may_trade"])

    def test_schema_corruption(self):
        self.reject(lambda x: x.update(schema="bad"), "BAD_SCHEMA")

    def test_future_or_wrong_asof(self):
        self.reject(lambda x: x.update(asof_et="2026-10-29"), "UNEXPECTED_ASOF")

    def test_incomplete_bar_leak(self):
        self.reject(lambda x: x.update(include_partial_2026_10_29=True), "PARTIAL_SESSION_LEAK")

    def test_counterfeited_full_raw_evidence(self):
        self.reject(lambda x: x.update(raw_market_bars_persisted=True), "UNSUPPORTED_RAW_EVIDENCE_CLAIM")

    def test_pit_bogus_promotion(self):
        self.reject(lambda x: x.update(historical_point_in_time_provenance_verified=True),
                    "ILLEGAL_PROMOTION_historical_point_in_time")

    def test_ca_bogus_promotion(self):
        self.reject(lambda x: x.update(corporate_actions_coverage_verified=True),
                    "ILLEGAL_PROMOTION_corporate_actions")

    def test_backtest_bogus_promotion(self):
        self.reject(lambda x: x.update(backtest_oos_completed=True), "ILLEGAL_PROMOTION_backtest")

    def test_signal_bogus_promotion(self):
        self.reject(lambda x: x.update(production_al_enabled=True), "ILLEGAL_PROMOTION_production")

    def test_wrong_scope(self):
        self.reject(lambda x: x.update(scope_sha256="a"*64), "SCOPE_MISMATCH")

    def test_partial_source(self):
        self.reject(lambda x: x.update(feed="sip"), "BAD_FEED")

    def test_wrong_calendar_begin(self):
        self.reject(lambda x: x.update(first_required_xnas_session="2026-07-31"), "SESSION_MISMATCH")

    def test_group_gap(self):
        self.reject(lambda x: x["groups"][1].update(first_index=121), "COUNT_MISMATCH")

    def test_last_index_mismatch(self):
        self.reject(lambda x: x["groups"][2].update(last_index=360), "BATCH_GAP_OVERLAP")

    def test_group_duplicate_not_overweighted(self):
        self.reject(lambda x: x["groups"][0].update(above_sma20=121), "GROUP_METRIC_OUT_OF_RANGE")

    def test_overstated_total(self):
        self.reject(lambda x: x["totals"].update(above_sma20=477), "COUNT_MISMATCH")

    def test_boolean_as_integer(self):
        self.reject(lambda x: x["groups"][0].update(series=True), "NON_INTEGER_COUNT")

    def test_wrong_benchmark(self):
        self.reject(lambda x: x.update(benchmark="SPY"), "BENCHMARK_MISMATCH")

    def test_wrong_benchmark_return(self):
        self.reject(lambda x: x.update(benchmark_return_63_pct_approx=55), "BENCHMARK_MISMATCH")

    def test_missing_series(self):
        self.reject(lambda x: x.update(observed_required_bar_cells=30528), "COUNT_MISMATCH")

if __name__=="__main__":
    unittest.main()
