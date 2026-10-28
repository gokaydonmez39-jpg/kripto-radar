"""Deterministic adversarial tests for isolated private NASDAQ performance lab."""
from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
import unittest

import exchange_calendars as ec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nasdaq_performance_guard import (SOURCE, EvidenceBlocked, evaluate_episode,
                                      scorecard, integrity_alerts, canonical_hash,
                                      drift_watch, challenger_card)

CAL = ec.get_calendar('XNAS')
START = '2026-10-22'


def dt(n):
    return CAL.session_offset(CAL.date_to_session(START), n).date().isoformat()


def bar(i, o=100, h=103, l=98, c=101, v=100000):
    return {'date': dt(i), 'open': str(o), 'high': str(h),
            'low': str(l), 'close': str(c), 'volume': v}


def episode(bars=None):
    return {'episode_id': START + '|FAKE', 'symbol': 'FAKE',
            'signal_asof': START, 'data_through': dt(15),
            'source': SOURCE, 'scope_sha256': 'a'*64, 'policy_sha256': 'b'*64,
            'reference_close': '100', 'stop': '95', 'target': '110',
            'bars': [] if bars is None else bars}


class OutcomeTests(unittest.TestCase):
    def test_only_next_session_is_eligible(self):
        r = evaluate_episode(episode([bar(1, 100, 111, 99, 108)]))
        self.assertEqual(r['status'], 'COMPLETE')
        self.assertEqual(r['event'], 'TARGET_TOUCHED')
        self.assertEqual(r['days_held'], 1)
        self.assertAlmostEqual(r['reference_pct'], 10.)
        self.assertLess(r['next_open_net_pct'], 10.)
        self.assertFalse(r['real_fill_proven'])

    def test_stop_first_ambiguous_even_with_positive_close(self):
        r = evaluate_episode(episode([bar(1, 100, 115, 90, 109)]))
        self.assertTrue(r['ambiguous'])
        self.assertEqual(r['event'], 'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS')
        self.assertLess(r['next_open_net_pct'], 0)

    def test_gap_below_stop_loses_beyond_original_stop(self):
        r = evaluate_episode(episode([bar(1), bar(2, 80, 83, 79, 82)]))
        self.assertEqual(r['event'], 'STOP_GAP_OPEN')
        self.assertTrue(r['gap'])
        self.assertLess(r['reference_pct'], -5)
        self.assertIn('STOP_GAP_SLIPPAGE_EXPOSURE', [a['code'] for a in integrity_alerts([r])])

    def test_gap_above_target_exit_at_open_not_target(self):
        r = evaluate_episode(episode([bar(1), bar(2, 115, 117, 112, 116)]))
        self.assertEqual(r['event'], 'TARGET_GAP_OPEN')
        self.assertGreater(r['reference_pct'], 10)

    def test_entry_outside_original_bounds_is_never_filled(self):
        for o,h,l,c in [(91, 93, 88, 92), (114, 115, 112, 113)]:
            r = evaluate_episode(episode([bar(1, o,h,l,c)]))
            self.assertEqual(r['status'], 'ENTRY_INVALIDATED_BY_GAP')
            self.assertIsNone(r['next_open_net_pct'])

    def test_contiguous_ten_days_does_not_claim_15_day_exit(self):
        e = episode([bar(i) for i in range(1,11)])
        e['data_through'] = dt(10)
        r = evaluate_episode(e)
        self.assertEqual(r['status'], 'OPEN_CENSORED')
        self.assertIsNone(r['reference_pct'])
        self.assertEqual(len(integrity_alerts([r])), 1)

    def test_exact_fifteenth_session_time_exit(self):
        r = evaluate_episode(episode([bar(i) for i in range(1,16)]))
        self.assertEqual(r['event'], 'TIME_EXIT_AT_CLOSE')
        self.assertEqual(r['days_held'], 15)
        self.assertEqual(r['exit_date'], dt(15))

    def test_future_data_after_cutoff_blocked(self):
        e = episode([bar(1)])
        e['data_through'] = START
        with self.assertRaisesRegex(EvidenceBlocked, 'FUTURE_BAR'):
            evaluate_episode(e)

    def test_missing_intermediate_xnas_session_blocked(self):
        with self.assertRaisesRegex(EvidenceBlocked, 'MISSING_OR_OUT_OF_ORDER'):
            evaluate_episode(episode([bar(2)]))

    def test_missing_matured_sessions_fail_closed_not_censored(self):
        e = episode([bar(i) for i in range(1,11)])
        with self.assertRaisesRegex(EvidenceBlocked, 'MISSING_MATURED_XNAS_SESSIONS'):
            evaluate_episode(e)

    def test_duplicate_bar_blocked(self):
        with self.assertRaises(EvidenceBlocked):
            evaluate_episode(episode([bar(1), bar(1)]))

    def test_weekend_signal_rejected(self):
        e = episode()
        e['signal_asof'] = '2026-10-24'
        e['episode_id'] = e['signal_asof']+'|FAKE'
        with self.assertRaisesRegex(EvidenceBlocked, 'NOT_XNAS_SESSION'):
            evaluate_episode(e)

    def test_original_2r_tampering_blocked(self):
        e = episode()
        e['target'] = '300'
        with self.assertRaisesRegex(EvidenceBlocked, 'ORIGINAL_2R'):
            evaluate_episode(e)

    def test_bad_source_or_missing_sha_blocked(self):
        e = episode()
        e['source'] = 'SIP'
        with self.assertRaisesRegex(EvidenceBlocked, 'UNAUTHORIZED_PRICE_SOURCE'):
            evaluate_episode(e)
        e['source'] = SOURCE
        e['scope_sha256'] = 'guessed'
        with self.assertRaisesRegex(EvidenceBlocked, 'MISSING_SOURCE_POLICY_SHA'):
            evaluate_episode(e)

    def test_nan_nonfinite_ohlcv_and_boolean_price_blocked(self):
        for k,v in [('high','NaN'), ('open',float('inf')), ('low',-1), ('close',True)]:
            e = episode([bar(1)])
            e['bars'][0][k] = v
            with self.assertRaises(EvidenceBlocked):
                evaluate_episode(e)

    def test_bar_geometry_and_missing_volume_blocked(self):
        e = episode([bar(1, 100, 101, 102, 100)])
        with self.assertRaisesRegex(EvidenceBlocked, 'OHLC_RANGE'):
            evaluate_episode(e)
        e = episode([bar(1, v=0)])
        with self.assertRaisesRegex(EvidenceBlocked, 'VOLUME'):
            evaluate_episode(e)

    def test_high_cost_worse_and_cost_limit_blocked(self):
        e = episode([bar(1, 100, 111, 99, 108)])
        no_cost = evaluate_episode(e, entry_cost_bps=0, exit_cost_bps=0)
        cost = evaluate_episode(e, entry_cost_bps=40, exit_cost_bps=40)
        self.assertLess(cost['next_open_net_pct'], no_cost['next_open_net_pct'])
        with self.assertRaisesRegex(EvidenceBlocked, 'UNBOUNDED_COST'):
            evaluate_episode(e, entry_cost_bps=1000)

    def test_stable_data_fingerprint_and_unique_event_alerts(self):
        e = episode([bar(1, 100, 115, 90, 109)])
        a = evaluate_episode(e)
        b = evaluate_episode(deepcopy(e))
        self.assertEqual(a['proof_hash'], b['proof_hash'])
        self.assertEqual(integrity_alerts([a]), integrity_alerts([b]))
        self.assertTrue(all(z['delivery'] == 'NOT_REQUESTED' for z in integrity_alerts([a])))


class ScientificDecisionTests(unittest.TestCase):
    def test_no_samples_is_hold_not_pass(self):
        s = scorecard([])
        self.assertEqual(s['status'], 'HOLD_INSUFFICIENT_EVIDENCE')
        self.assertIn('NO_COMPLETED_EPISODES', s['why'])

    def test_small_sample_holds_even_high_success(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        s = scorecard([r])
        self.assertNotIn('PASS',s['status'])
        self.assertIn('SAMPLE_OR_DATE_COHORT_TOO_SMALL',s['why'])
        self.assertIn('NO_MATCHED_NEXT_OPEN_CONTROL',s['why'])
        self.assertLess(s['wilson_win_95'][0], 1)

    def test_censored_excluded_and_denominator_not_faked(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        eq = episode([bar(1)])
        eq['data_through'] = dt(1)
        q = evaluate_episode(eq)
        q['episode_id'] = START + '|OTHER'
        s=scorecard([r,q])
        self.assertEqual((s['n_total'],s['n_complete'],s['n_censored_or_invalidated']),(2,1,1))
        self.assertIn('EXCESSIVE_CENSORING',str(s['why']))

    def test_repeated_id_rejected_not_double_counted(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        with self.assertRaisesRegex(EvidenceBlocked,'DUPLICATE_EPISODE_COUNTS'):
            scorecard([r,r])

    def test_misaligned_comparator_rejected(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        with self.assertRaisesRegex(EvidenceBlocked,'CONTROL_MATCHED'):
            scorecard([r],control_net_returns={'wrong':0.0})

    def test_control_cannot_auto_approve_without_provenance(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        s = scorecard([r],phase='HOLDOUT',holdout_registration_proven=True,
                      control_net_returns={r['episode_id']: -1.0})
        self.assertTrue(s['paired_control'])
        self.assertIn('CONTROL_PROVENANCE_NOT_AUTHENTICATED_BY_FUNCTION',s['why'])
        self.assertFalse(s['automated_rule_change'])
        self.assertNotEqual(s['status'],'PASS')

    def test_drift_watch_refuses_low_sample(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        d = drift_watch([r])
        self.assertFalse(d['alert'])
        self.assertEqual(d['state'], 'HOLD_UNDERPOWERED')

    def test_challenger_is_proposal_only_and_rejects_unsafe_lever(self):
        r = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        sc = scorecard([r])
        c = challenger_card(sc, hypothesis_id='XRAY-H-0001',
                            lever='RVOL_RESEARCH',
                            proposed_falsifier='No improvement over paired OOS baseline after costs.',
                            baseline_sha='c'*64)
        self.assertFalse(c['AL_CHANGE'])
        self.assertEqual(c['research_status'], 'PROPOSED_NOT_TESTED')
        with self.assertRaisesRegex(EvidenceBlocked, 'UNSAFE_OR_UNREGISTERED'):
            challenger_card(sc, hypothesis_id='XRAY-H-0002',
                            lever='AUTO_BUY_ORDERS',
                            proposed_falsifier='Reject if costs exceed improvement.',
                            baseline_sha='c'*64)

    def test_drift_watch_fixed_threshold_is_only_suspicion(self):
        source = evaluate_episode(episode([bar(1, 100, 112, 99, 111)]))
        rr=[]
        for k in range(40):
            r=dict(source)
            r['episode_id']='2026-10-%02d|S%02d'%(1+(k%20), k)
            r['signal_asof']='2026-09-%02d'%(1+k//2)
            r['next_open_net_pct']=1.2 if k < 20 else -0.8
            rr.append(r)
        d=drift_watch(rr)
        self.assertTrue(d['alert'])
        self.assertFalse(d['statistical_significance_proven'])
        self.assertFalse(d['rule_change_authorized'])

    def test_input_never_produces_real_order_or_delivery(self):
        e = episode([bar(1, 100, 112, 99, 111)])
        r = evaluate_episode(e)
        self.assertFalse(r['notification_sent'])
        self.assertFalse(r['real_fill_proven'])
        self.assertEqual(scorecard([r])['execution'], 'NONE')


if __name__ == '__main__':
    unittest.main()
