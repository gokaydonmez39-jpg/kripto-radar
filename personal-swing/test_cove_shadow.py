"""Cove-method-inspired XRAY personal NASDAQ research shadow: offline safety TDD.

No official Cove Trader source is used. No market API, Sheets, broker or secrets.
"""
import copy
import datetime as dt
import json
import math
import unittest
from unittest.mock import patch

import exchange_calendars as ec
import runner
import cove_shadow as shadow

ASOF = "2026-11-06"
ENTRY = "2026-10-22"
CAL = ec.get_calendar("XNAS")
DAYS = [str(t.date()) for t in CAL.sessions_in_range("2026-08-13", ASOF)][-52:]
FUTURE = [d for d in DAYS if d > ENTRY]
SCOPE = sorted(runner.get_scope(
    watchlist_file="nasdaq_watchlist_477.json", asof=ASOF))
SYMBOL = SCOPE[0]


def baseline_bars():
    return [dict(timestamp=d + "T16:00:00-04:00", open=100.0,
                 high=103.0, low=98.0, close=100.0, volume=10000.0)
            for d in DAYS]


def episode():
    return dict(id=ENTRY+"|"+SYMBOL, symbol=SYMBOL,
                asof_et=ENTRY, reference_close=100.0,
                stop=95.0, target_2r=110.0)


def bundle():
    bars = baseline_bars()
    return dict(schema="XRAY_COVE_METHOD_SHADOW_INPUT_V1", asof_et=ASOF,
                feed="ALPACA_IEX_DAILY_RAW_1DAY",
                scope_sha256=runner.sha_symbols(SCOPE),
                algorithm_sha256=runner.analysis_fingerprint(),
                source_counts={"requested":477,"processed":477,
                               "valid":477,"missing":0,"final":True},
                episodes=[episode()], bars_by_symbol={SYMBOL:bars})


def place_event(data, day, *, o=100., h=103., l=98., c=100.):
    row=next(x for x in data["bars_by_symbol"][SYMBOL] if x["timestamp"][:10]==day)
    row.update(open=o,high=h,low=l,close=c)


class CoveShadowContractTests(unittest.TestCase):
    def test_source_sha_exact_477_and_readonly(self):
        src=bundle()
        original=copy.deepcopy(src)
        out=shadow.run_bundle(src)
        self.assertEqual(src,original)
        self.assertEqual(out["scope"],477)
        self.assertEqual(out["schema"],shadow.OUTPUT_SCHEMA)
        self.assertFalse(out["orders"])
        self.assertFalse(out["writes"])
        self.assertEqual(out["alpha_claim"],"HOLD_UNVERIFIED_PIT_OOS")
        self.assertEqual(out["data_authority"],"SUPPLIED_BUNDLE_NOT_INDEPENDENT_RECEIPT")
        self.assertEqual(out["robustness"]["baseline_multiplier"],1.0)

    def test_scope_drift_and_policy_drift_fail_before_audit(self):
        for field in ("scope_sha256","algorithm_sha256"):
            src=bundle()
            src[field]="0"*64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,"SHA_MISMATCH"):
                shadow.run_bundle(src)
        src=bundle()
        src["source_counts"]["valid"]=476
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_477_FINAL"):
            shadow.run_bundle(src)

    def test_both_touch_lower_stop_upper_target_ambiguous(self):
        src=bundle()
        place_event(src,FUTURE[0],o=100,h=111,l=94,c=100)
        out=shadow.run_bundle(src)
        base=out["baseline"]
        self.assertEqual(base["ambiguous"],1)
        self.assertEqual(base["terminal_counts"]["BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS"],1)
        self.assertEqual(base["net_r_min_mean"],-1.)
        self.assertEqual(base["net_r_max_mean"],2.)
        self.assertIsNone(base["wilson_win_rate_95pct"])

    def test_gap_through_stop_does_not_claim_stop_fill(self):
        src=bundle()
        place_event(src,FUTURE[0],o=92,h=96,l=91,c=94)
        out=shadow.run_bundle(src)
        self.assertEqual(out["baseline"]["terminal_counts"]["GAP_BELOW_STOP_OPEN_PROXY"],1)
        self.assertAlmostEqual(out["baseline"]["net_r_min_mean"],-1.6)
        self.assertEqual(out["baseline"]["ambiguous"],0)

    def test_target_gap_overrides_later_same_day_low(self):
        src=bundle()
        place_event(src,FUTURE[0],o=112,h=114,l=94,c=97)
        out=shadow.run_bundle(src)
        self.assertEqual(out["baseline"]["terminal_counts"]["GAP_ABOVE_TARGET_OPEN_PROXY"],1)
        self.assertEqual(out["baseline"]["ambiguous"],0)
        self.assertGreater(out["baseline"]["net_r_min_mean"],2.)

    def test_target_and_cost_sensitivity(self):
        src=bundle()
        place_event(src,FUTURE[0],o=100,h=111,l=99,c=105)
        no_cost=shadow.run_bundle(src)
        with_cost=shadow.run_bundle(src,slippage_bps=20,commission_per_share=0.01)
        self.assertEqual(no_cost["baseline"]["terminal_counts"]["TARGET_TOUCHED"],1)
        self.assertAlmostEqual(no_cost["baseline"]["net_r_min_mean"],2.)
        self.assertLess(with_cost["baseline"]["net_r_min_mean"],2.)
        self.assertGreater(with_cost["baseline"]["net_r_min_mean"],1.)

    def test_no_future_bar_or_duplicate_bar(self):
        src=bundle()
        src["bars_by_symbol"][SYMBOL].append(
            dict(timestamp="2026-11-09T16:00:00-05:00",
                 open=100.,high=103.,low=98.,close=100.,volume=1000.))
        with self.assertRaisesRegex(ValueError,"FUTURE_BAR"):
            shadow.run_bundle(src)
        src=bundle()
        src["bars_by_symbol"][SYMBOL].append(copy.deepcopy(src["bars_by_symbol"][SYMBOL][-1]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BAR"):
            shadow.run_bundle(src)

    def test_iex_geometry_and_missing_source_session_fail_closed(self):
        src=bundle()
        src["bars_by_symbol"][SYMBOL][20]["low"]=104.
        with self.assertRaisesRegex(ValueError,"INVALID_OHLC"):
            shadow.run_bundle(src)
        src=bundle()
        src["bars_by_symbol"][SYMBOL].pop(20)
        with self.assertRaisesRegex(ValueError,"NONCONTIGUOUS_52_XNAS"):
            shadow.run_bundle(src)

    def test_signal_entry_mismatch_and_future_episode_block(self):
        src=bundle()
        src["episodes"][0]["reference_close"]=99.
        with self.assertRaisesRegex(ValueError,"ENTRY_SOURCE_CLOSE_MISMATCH"):
            shadow.run_bundle(src)
        src=bundle()
        src["episodes"][0]["asof_et"]="2026-11-09"
        src["episodes"][0]["id"]="2026-11-09|"+SYMBOL
        with self.assertRaisesRegex(ValueError,"FUTURE_EPISODE"):
            shadow.run_bundle(src)

    def test_original_2r_and_symbol_identity_immutable(self):
        src=bundle()
        src["episodes"][0]["target_2r"]=111.
        with self.assertRaisesRegex(ValueError,"NON_2R_LEVEL"):
            shadow.run_bundle(src)
        src=bundle()
        src["episodes"][0]["symbol"]="EXCLUDED"
        with self.assertRaisesRegex(ValueError,"BAD_EPISODE_IDENTITY"):
            shadow.run_bundle(src)

    def test_fifteen_session_time_exit_and_unfinished_open(self):
        src=bundle()
        # ASOF 2026-11-06 has fewer than 15 completed sessions since Oct 22.
        self.assertEqual(shadow.run_bundle(src)["baseline"]["terminal_counts"],{"OPEN":1})
        src=bundle()
        # Early entry with full 15-session watch window.
        old_day=[d for d in DAYS if d <= ASOF][-40]
        src["episodes"][0].update(asof_et=old_day,id=old_day+"|"+SYMBOL)
        out=shadow.run_bundle(src)
        self.assertEqual(out["baseline"]["terminal_counts"],{"TIME_EXIT_CLOSE_PROXY":1})
        self.assertEqual(out["baseline"]["completed"],1)

    def test_finite_nonnegative_cost_and_strict_type(self):
        for kw in ({"slippage_bps":-1}, {"slippage_bps":float("nan")},
                   {"commission_per_share":-0.1}, {"slippage_bps":"5"}):
            with self.subTest(kw=kw),self.assertRaisesRegex(ValueError,"INVALID_COST"):
                shadow.run_bundle(bundle(),**kw)

    def test_no_episode_is_hold_not_zero_edge(self):
        src=bundle()
        src["episodes"]=[]
        src["bars_by_symbol"]={}
        out=shadow.run_bundle(src)
        self.assertEqual(out["baseline"]["completed"],0)
        self.assertIsNone(out["baseline"]["net_r_min_mean"])
        self.assertEqual(out["baseline"]["status"],"HOLD_NO_EPISODES")
        self.assertEqual(out["alpha_claim"],"HOLD_UNVERIFIED_PIT_OOS")

    def test_missing_bars_duplicate_episode_and_extra_symbol_fail(self):
        src=bundle()
        src["bars_by_symbol"]={}
        with self.assertRaisesRegex(ValueError,"MISSING_SYMBOL_BARS"):
            shadow.run_bundle(src)
        src=bundle()
        src["episodes"].append(copy.deepcopy(src["episodes"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_EPISODE"):
            shadow.run_bundle(src)
        src=bundle()
        src["bars_by_symbol"]["EXCLUDED"]=baseline_bars()
        with self.assertRaisesRegex(ValueError,"UNREQUESTED_BARS"):
            shadow.run_bundle(src)

    def test_wilson_only_nonambiguous_finished_trials(self):
        src=bundle()
        place_event(src,FUTURE[0],o=100,h=111,l=99,c=105)
        out=shadow.run_bundle(src)
        iv=out["baseline"]["wilson_win_rate_95pct"]
        self.assertIsNotNone(iv)
        self.assertAlmostEqual(iv["upper"],1.0)
        self.assertGreaterEqual(iv["lower"],0.)
        self.assertLessEqual(iv["lower"],iv["upper"])

    def test_counterfactual_sweep_does_not_change_original_exit(self):
        src=bundle()
        place_event(src,FUTURE[0],o=100,h=111,l=94,c=100)
        one=shadow.run_bundle(src,stop_multipliers=(1.0,))
        many=shadow.run_bundle(src,stop_multipliers=(0.8,1.0,1.2))
        self.assertEqual(one["baseline"],many["baseline"])
        self.assertEqual(len(many["robustness"]["counterfactual"]),3)
        self.assertEqual(many["robustness"]["recommendation"],"NONE_DIAGNOSTIC_ONLY")

    def test_provider_or_broker_import_is_forbidden(self):
        import inspect
        source=inspect.getsource(shadow)
        for forbidden in ("alpaca_trade_api", "TradingClient", "submit_order",
                          "place_order", "requests.post", "sheets.values.append"):
            self.assertNotIn(forbidden,source)


if __name__=="__main__":
    unittest.main()
