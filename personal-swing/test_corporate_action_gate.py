"""Fail-closed, no-network ROKU delisting acceptance contracts."""
import copy
import unittest
from decimal import Decimal

import corporate_action_gate as gate


def fixtures():
    scope = [f'T{i:04d}' for i in range(475)] + ['ROKU', 'FOXA']
    action = {
        'symbol': 'ROKU',
        'last_trading_date': '2026-11-06',
        'effective_asof_et': '2026-11-09',
        'successor_security': 'FOXA',
        'cash_usd_per_share': '95.30',
        'successor_shares_per_share': '0.9799',
        'nasdaq_notice': 'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806',
        'sec_filing': 'https://www.sec.gov/Archives/edgar/data/1428439/000119312526451874/d181620d8k.htm'
    }
    provider = {
        'symbol': 'ROKU', 'asset_status': 'inactive', 'tradable': False,
        'bar_dates': ['2026-11-02', '2026-11-03', '2026-11-04',
                      '2026-11-05', '2026-11-06']
    }
    episode = {
        'id': '2026-10-30|ROKU', 'symbol': 'ROKU',
        'asof_et': '2026-10-30', 'reference_close': '100',
        'original_stop': '95', 'original_target_2r': '110',
        'status': 'AÇIK • 3/15 SEANS'
    }
    return scope, action, provider, episode


class CorporateActionGateTests(unittest.TestCase):
    def run_gate(self, *, asof='2026-11-09', mutate=None):
        original = fixtures()
        vals = copy.deepcopy(original)
        if mutate is not None:
            mutate(*vals)
        frozen = copy.deepcopy(vals)
        result = gate.assess(*vals, asof_et=asof)
        self.assertEqual(vals, frozen, 'input mutation is forbidden')
        return result

    def test_known_roku_delisting_keeps_universe_frozen_and_holds(self):
        r = self.run_gate()
        self.assertEqual(r['status'], 'P0_DELISTED_MEMBER_REPLACEMENT_REQUIRED')
        self.assertEqual(r['historical_universe_count'], 477)
        self.assertEqual(r['active_tradable_count'], 476)
        self.assertEqual(r['unresolved_slot_count'], 1)
        self.assertEqual(r['unresolved_episode_count'], 1)
        self.assertTrue(r['successor_already_in_scope'])
        self.assertFalse(r['ready_for_477_eod'])
        self.assertFalse(r['allow_any_al_release'])
        self.assertEqual(r['execution'], 'NONE')
        self.assertFalse(r['orders'])
        self.assertFalse(r['write_sheets'])
        self.assertFalse(r['modify_watchlist'])
        self.assertFalse(r['authorize_replay'])
        self.assertEqual(r['source_evidence'], 'REFERENCED_NOT_INDEPENDENTLY_VERIFIED_BY_CODE')
        self.assertEqual(r['episode_outcome'], 'CORPORATE_ACTION_REVIEW_PENDING')
        self.assertEqual(r['original_stop'], '95')
        self.assertEqual(r['original_target_2r'], '110')
        self.assertIsNone(r['realized_return_pct'])

    def test_prior_session_is_not_delisted_retroactively(self):
        r = self.run_gate(asof='2026-11-06')
        self.assertEqual(r['status'], 'NOT_EFFECTIVE_ASOF')
        self.assertEqual(r['historical_universe_count'], 477)
        self.assertEqual(r['active_tradable_count'], 477)
        self.assertFalse(r['ready_for_477_eod'])  # This source does not prove EOD PASS.

    def test_newer_sessions_still_hold_without_replacement(self):
        r = self.run_gate(asof='2026-11-10')
        self.assertEqual(r['status'], 'P0_DELISTED_MEMBER_REPLACEMENT_REQUIRED')

    def test_duplicate_symbol_never_becomes_an_auto_replacement(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'DUPLICATE_OR_INVALID_SCOPE'):
            self.run_gate(mutate=lambda scope, a, p, e: scope.__setitem__(-2, 'FOXA'))

    def test_shortened_476_universe_refused(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'EXACT_477_REQUIRED'):
            self.run_gate(mutate=lambda scope, a, p, e: scope.remove('ROKU'))

    def test_successor_must_already_exist_in_scope_for_this_incident(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'SUCCESSOR_SCOPE_MISMATCH'):
            self.run_gate(mutate=lambda scope, a, p, e: scope.remove('FOXA') or scope.append('T9999'))

    def test_synthetic_same_day_bar_is_rejected(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'DELISTING_BAR_CONFLICT'):
            self.run_gate(mutate=lambda scope, a, p, e: p['bar_dates'].append('2026-11-09'))

    def test_missing_last_real_bar_refused(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'LAST_TRADING_BAR_MISSING'):
            self.run_gate(mutate=lambda scope, a, p, e: p['bar_dates'].remove('2026-11-06'))

    def test_provider_still_active_refused(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'ASSET_INACTIVITY_UNCONFIRMED'):
            self.run_gate(mutate=lambda scope, a, p, e: p.__setitem__('asset_status', 'active'))

    def test_provider_tradable_refused(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'ASSET_INACTIVITY_UNCONFIRMED'):
            self.run_gate(mutate=lambda scope, a, p, e: p.__setitem__('tradable', True))

    def test_asof_before_action_requires_a_real_session(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'NOT_XNAS_SESSION'):
            self.run_gate(asof='2026-11-08')

    def test_merger_terms_not_generic_symbol_swap(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'MERGER_TERMS_NOT_PINNED'):
            self.run_gate(mutate=lambda scope, a, p, e: a.__setitem__('cash_usd_per_share', '0'))

    def test_merger_share_ratio_must_not_be_rounded(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'MERGER_TERMS_NOT_PINNED'):
            self.run_gate(mutate=lambda scope, a, p, e: a.__setitem__('successor_shares_per_share', '0.98'))

    def test_untrusted_documents_must_not_be_accepted(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'OFFICIAL_REFERENCE_MISMATCH'):
            self.run_gate(mutate=lambda scope, a, p, e: a.__setitem__('sec_filing', 'https://evil.test/filing'))

    def test_original_2r_level_must_be_immutable(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'HISTORICAL_LEVELS_INVALID'):
            self.run_gate(mutate=lambda scope, a, p, e: e.__setitem__('original_target_2r', '120.00'))

    def test_original_episode_identity_must_match(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'HISTORICAL_EPISODE_IDENTITY_INVALID'):
            self.run_gate(mutate=lambda scope, a, p, e: e.__setitem__('id', '2026-11-02|FOXA'))

    def test_action_dates_cannot_be_backdated(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'OFFICIAL_DATE_MISMATCH'):
            self.run_gate(mutate=lambda scope, a, p, e: a.__setitem__('effective_asof_et', '2026-11-06'))

    def test_bad_source_shape_rejected(self):
        with self.assertRaisesRegex(gate.CorporateActionHold, 'PROVIDER_SHAPE_INVALID'):
            self.run_gate(mutate=lambda scope, a, p, e: p.__setitem__('bar_dates', ['2026-11-06', '2026-11-06']))

    def test_no_user_toggle_can_self_approve_release(self):
        r = self.run_gate(mutate=lambda scope, a, p, e: a.__setitem__('owner_approved', True))
        self.assertFalse(r['ready_for_477_eod'])
        self.assertTrue(r['owner_approval_required'])


if __name__ == '__main__':
    unittest.main()
