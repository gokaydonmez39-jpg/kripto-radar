"""Offline threat-model regressions for historical Fiserv alias leakage."""
import copy
import json
from pathlib import Path
import unittest
from xray_v47_pit_symbol_mapping_shadow import AliasBlocked, audit

FIXTURE = Path(__file__).with_name('xray_v47_hypothetical_fisv_cross_transition.json')

def sample():
    return json.loads(FIXTURE.read_text())

class AliasTests(unittest.TestCase):
    def run_with(self, **changes):
        s = sample();s.update(changes);return audit(s)

    def assert_bad(self, **changes):
        with self.assertRaises(AliasBlocked):
            self.run_with(**changes)

    def test_cross_boundary_not_released(self):
        s=self.run_with()
        self.assertTrue(s['window_crosses_2025_11_11_listing_transfer'])
        self.assertEqual(s['status'],'CROSS_TRANSITION_VENUE_PARTITION_REQUIRED')
        self.assertTrue(s['retrospective_alias_risk'])

    def test_pre_transfer_2025_fi_under_2026_fisv_alias_risk(self):
        s=self.run_with(window_first='2025-11-10',window_last='2025-11-10')
        self.assertEqual(s['status'],'HISTORIC_NYSE_TRADE_MAY_BE_RELABELLED_FISV')
        self.assertFalse(s['original_trade_venue_per_record_attested'])

    def test_same_day_transition_remains_unattested(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2025-11-11',api_asof='2025-11-11')
        self.assertFalse(s['window_crosses_2025_11_11_listing_transfer'])
        self.assertFalse(s['daily_venue_master_independently_checked'])

    def test_transfer_day_asof_mapping_latency_not_proven(self):
        # Alpaca FAQ documents T+1 availability for FB/META example ONLY.
        # The FISV transfer day must not receive the same-day identity PASS.
        s=self.run_with(window_first='2025-11-11', window_last='2025-11-11',
                        decision_asof='2025-11-11',api_asof='2025-11-11')
        self.assertTrue(s['provider_same_day_rename_mapping_not_attested'])
        self.assertEqual(s['status'], 'TRANSFER_DAY_MAPPING_AVAILABILITY_UNVERIFIED')
        self.assertFalse(s['a2_actual_historical_pages_verified'])

    def test_tplus_one_example_does_not_prove_fisv_same_day(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2025-11-12',api_asof='2025-11-12')
        self.assertTrue(s['provider_same_day_rename_mapping_not_attested'])
        self.assertFalse(s['fisv_mapping_rename_day_proven'])
        self.assertFalse(s['canonical_price_pass'])

    def test_mapping_disabled_not_falsely_treated_as_fisv_proof(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2025-11-11',api_asof='-')
        self.assertFalse(s['provider_same_day_rename_mapping_not_attested'])
        self.assertTrue(s['api_asof_mapping_disabled'])
        self.assertFalse(s['fisv_mapping_rename_day_proven'])

    def test_asof_after_decision_is_future_identity_lookahead(self):
        s=self.run_with(window_first='2025-11-10',window_last='2025-11-10',
                        decision_asof='2025-11-10',api_asof='2026-10-22')
        self.assertEqual(s['status'],'FUTURE_API_ASOF_LOOKAHEAD_BLOCKED')
        self.assertTrue(s['api_asof_is_after_historical_decision'])

    def test_asof_dash_not_proof_of_venue(self):
        s=self.run_with(api_asof='-')
        self.assertTrue(s['api_asof_mapping_disabled'])
        self.assertFalse(s['historic_original_symbols_per_record_attested'])
        self.assertFalse(s['a1_listing_scope_release_ready'])

    def test_dash_single_day_remains_unattested(self):
        s=self.run_with(api_asof='-',window_first='2025-11-10',
                        window_last='2025-11-10')
        self.assertEqual(s['status'],'ASOF_MAPPING_SKIPPED_VENUE_UNATTESTED')

    def test_2026_10k_not_known_2025(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        api_asof='2025-11-11',decision_asof='2025-11-11')
        self.assertFalse(s['sec_10k_retrospective_confirmation_known_asof_decision'])

    def test_2026_10k_confirmation_still_not_daily_master(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2026-02-20',api_asof='2026-02-20')
        self.assertTrue(s['sec_10k_retrospective_confirmation_known_asof_decision'])
        self.assertFalse(s['a1_listing_scope_release_ready'])

    def test_10k_filing_same_day_not_intraday_proven(self):
        s=self.run_with(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2026-02-19',api_asof='2026-02-19')
        self.assertFalse(s['sec_10k_retrospective_confirmation_known_asof_decision'])
        self.assertFalse(s['sec_filing_intraday_cutoff_attested'])

    def test_pre_transfer_named_fi_research_not_auto_go(self):
        s=self.run_with(query_symbol='FI',returned_label='FI',
                        window_first='2025-11-10',window_last='2025-11-10',
                        decision_asof='2025-11-10',api_asof='2025-11-10')
        self.assertFalse(s['retrospective_alias_risk'])
        self.assertFalse(s['a1_listing_scope_release_ready'])

    def test_post_transfer_named_fisv_still_no_pass(self):
        s=self.run_with(window_first='2026-10-22',window_last='2026-10-22')
        self.assertFalse(s['a3_sip_correction_volume_verified'])
        self.assertFalse(s['original_trade_venue_per_record_attested'])

    def test_perfectly_matching_reported_label_not_authority(self):
        s=self.run_with()
        self.assertFalse(s['return_symbol_is_historical_listing_evidence'])
        self.assertFalse(s['canonical_price_pass'])

    def test_misleading_returned_fi_label_no_magic_proof(self):
        s=self.run_with(returned_label='FI')
        self.assertFalse(s['daily_venue_master_independently_checked'])

    def test_wrong_issuer_or_scope(self):
        for change in ({'issuer_cik':'798354'},{'issuer_cik':798354},
                       {'issuer_cik':'0000000000'},{'query_symbol':'AAPL'},
                       {'returned_label':'TSLA'},{'query_symbol':True},
                       {'sample_type':'REAL_PROVIDER_SIP'},{'feed':'iex'}):
            with self.subTest(change=change):self.assert_bad(**change)

    def test_synthetic_sample_rejects_extra_certification(self):
        q=sample();q['price_pass']=True
        with self.assertRaises(AliasBlocked):audit(q)

    def test_invalid_dates(self):
        for key,value in [('window_first','2025-11-31'),('window_last','2026-10-23'),
                          ('window_first','2025-10-28'),('decision_asof','2026-10-23'),
                          ('api_asof','n/a'),('decision_asof','2025-01-01'),
                          ('window_first',None),('api_asof',True)]:
            with self.subTest(key=key,value=value):self.assert_bad(**{key:value})

    def test_inverted_window(self):
        self.assert_bad(window_first='2025-11-12',window_last='2025-11-10')

    def test_future_historical_window(self):
        self.assert_bad(window_first='2025-11-11',window_last='2025-11-11',
                        decision_asof='2025-11-10')

    def test_unknown_document_type(self):
        self.assert_bad(schema='OTHER')

    def test_no_mutation(self):
        a=sample();old=copy.deepcopy(a)
        audit(a)
        self.assertEqual(a,old)

    def test_no_broker_no_order_no_signal(self):
        s=self.run_with()
        for field in ('a0_account_rights_verified','a1_listing_scope_release_ready',
                      'a2_actual_historical_pages_verified','canonical_price_pass',
                      'issuer_mc_pass','g9_pass','c417_pass','iphone_receipt_attested'):
            with self.subTest(field=field):self.assertIs(s[field],False)
        self.assertEqual(s['registered_r92_count'],0)
        self.assertEqual(s['execution'],'NONE')
        self.assertEqual(s['real_money'],'NO-GO')
        self.assertEqual(s['orders'],[])

if __name__ == '__main__':unittest.main()