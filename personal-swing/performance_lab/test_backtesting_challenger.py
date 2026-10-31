"""A35 synthetic cross-engine, adversarial and safety checks (no vendor secrets)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import exchange_calendars as ec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nasdaq_performance_guard import EvidenceBlocked, SOURCE
from backtesting_challenger import (compare_episode, cost_stress, PASS,
                                    NO_EXECUTION, _valid_prior_bars)

CAL = ec.get_calendar('XNAS')
START = '2026-10-22'


def day(i):
    return CAL.session_offset(CAL.date_to_session(START), i).date().isoformat()


def bar(i, o=100, h=104, l=98, c=100, v=500000):
    return {'date': day(i), 'open': str(o), 'high': str(h),
            'low': str(l), 'close': str(c), 'volume': v}


def fixture(rows, *, cutoff=None):
    return {'episode': {
        'episode_id': START+'|FAKE', 'symbol': 'FAKE',
        'signal_asof': START, 'data_through': cutoff or day(15),
        'source': SOURCE, 'scope_sha256': 'a'*64, 'policy_sha256': 'b'*64,
        'reference_close': '100', 'stop': '95', 'target': '110',
        'bars': rows},
        'previous_bar': bar(-1), 'signal_bar': bar(0)}


class Contract(unittest.TestCase):
    def test_missing_matured_bar_rejected(self):
        with self.assertRaisesRegex(EvidenceBlocked, 'MISSING_MATURED'):
            compare_episode(fixture([bar(1)]))

    def test_previous_bar_is_exact_xnas_session(self):
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['previous_bar']['date'] = day(-2)
        with self.assertRaisesRegex(EvidenceBlocked, 'PRIOR_BAR_TIME'):
            compare_episode(w)

    def test_signal_close_drift_fail_closed(self):
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['signal_bar']['close'] = '99'
        with self.assertRaisesRegex(EvidenceBlocked, 'SIGNAL_CLOSE_DRIFT'):
            compare_episode(w)

    def test_unauthorized_source_and_target_mutation_blocked(self):
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['episode']['source'] = 'SIP'
        with self.assertRaisesRegex(EvidenceBlocked, 'UNAUTHORIZED_PRICE_SOURCE'):
            compare_episode(w)
        w['episode']['source'] = SOURCE
        w['episode']['target'] = '150'
        with self.assertRaisesRegex(EvidenceBlocked, 'ORIGINAL_2R'):
            compare_episode(w)

    def test_bad_volume_nan_and_extra_schema(self):
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['previous_bar']['volume'] = 0
        with self.assertRaisesRegex(EvidenceBlocked, 'PRIOR_BAR_VOLUME'):
            compare_episode(w)
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['signal_bar']['high'] = 'NaN'
        with self.assertRaises(EvidenceBlocked):
            compare_episode(w)
        w = fixture([bar(1, h=111)], cutoff=day(1))
        w['unauthorized_private_output'] = True
        with self.assertRaisesRegex(EvidenceBlocked, 'CHALLENGER_SCHEMA'):
            compare_episode(w)

    def test_first_open_outside_bounds_no_fill(self):
        for values in [(92,93,89,91), (113,115,111,113)]:
            w = fixture([bar(1, *values)], cutoff=day(1))
            q = compare_episode(w)
            self.assertEqual(q['status'], 'HOLD_ENTRY_GAP_INVALIDATED_NO_FILL')
            self.assertFalse(q['real_fills_proven'])

    def test_censored_episode_never_counts_as_trade(self):
        w = fixture([bar(1)], cutoff=day(1))
        q = compare_episode(w)
        self.assertEqual(q['status'], 'HOLD_CENSORED_NO_CLOSED_TRADE')

    def test_fifteenth_session_time_exit_excluded_not_misrepresented(self):
        w = fixture([bar(i) for i in range(1,16)])
        q = compare_episode(w)
        self.assertEqual(q['status'], 'HOLD_15TH_CLOSE_MODEL_NOT_EQUIVALENT')

    def test_no_real_execution_in_all_outputs(self):
        w = fixture([bar(1, h=111)], cutoff=day(1))
        x = compare_episode(w)
        for k,v in NO_EXECUTION.items():
            self.assertIs(x[k], v)
        self.assertNotIn('symbol', x)
        self.assertNotIn('secret', str(x).lower())


class WithBacktesting(unittest.TestCase):
    def test_corrupted_exit_price_fails_closed(self):
        w = fixture([bar(1, 100, 112, 99, 111)], cutoff=day(1))
        bad = [{'entry_date': day(1), 'exit_date': day(1),
                'entry': 100.0, 'exit': 109.0, 'return_pct': 9.0}]
        with patch('backtesting_challenger._engine', return_value=(bad, False)):
            result = compare_episode(w)
        self.assertEqual(result['status'], 'HOLD_EXECUTION_MODEL_DIVERGENCE')
        self.assertFalse(result['exit_matches'])

    def test_wrong_exit_session_fails_closed(self):
        w = fixture([bar(1, 100, 112, 99, 111)], cutoff=day(1))
        bad = [{'entry_date': day(1), 'exit_date': day(2),
                'entry': 100.0, 'exit': 110.0, 'return_pct': 10.0}]
        with patch('backtesting_challenger._engine', return_value=(bad, False)):
            result = compare_episode(w)
        self.assertEqual(result['status'], 'HOLD_EXECUTION_MODEL_DIVERGENCE')
        self.assertFalse(result['dates_match'])

    def test_next_open_target_reconciles(self):
        w = fixture([bar(1, 100, 112, 99, 111)], cutoff=day(1))
        self.assertEqual(compare_episode(w)['status'], PASS)

    def test_next_open_stop_reconciles(self):
        w = fixture([bar(1, 100, 104, 93, 97)], cutoff=day(1))
        self.assertEqual(compare_episode(w)['status'], PASS)

    def test_later_session_stop_gap_reconciles_or_holds_not_falsely_pass(self):
        w = fixture([bar(1),bar(2, 85, 88, 82, 86)], cutoff=day(2))
        out=compare_episode(w)
        self.assertIn(out['status'], {PASS, 'HOLD_EXECUTION_MODEL_DIVERGENCE'})
        if out['status'] == PASS:
            self.assertTrue(out['exit_matches'])

    def test_same_bar_stop_target_never_claims_clean_pass(self):
        w = fixture([bar(1, 100, 115, 90, 104)], cutoff=day(1))
        self.assertEqual(compare_episode(w)['status'], 'HOLD_INTRABAR_PATH_AMBIGUOUS')

    def test_cost_increases_never_improve_same_trade(self):
        w = fixture([bar(1, 100, 112, 99, 111)], cutoff=day(1))
        x=cost_stress(w)
        self.assertEqual(x['commission_each_side_bps'], [0,15,40])
        self.assertTrue(x['monotonically_nonincreasing'])
        self.assertGreater(x['engine_trade_return_pct'][0], x['engine_trade_return_pct'][2])
        self.assertFalse(x['orders'])

    def test_no_input_mutation_repeatable(self):
        w = fixture([bar(1, 100, 112, 99, 111)], cutoff=day(1))
        original = deepcopy(w)
        a=compare_episode(w); b=compare_episode(w)
        self.assertEqual(a,b)
        self.assertEqual(w,original)


if __name__ == '__main__':
    unittest.main()
