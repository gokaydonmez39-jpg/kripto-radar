"""Adversarial deterministic tests; never provider I/O or orders."""
from copy import deepcopy
import unittest
from xray_v44_fiserv_venue_pit_shadow import audit, VenueEvidenceBlocked

BASE = {'issuer_cik':'0000798354', 'issuer':'Fiserv, Inc.',
        'session_date':'2025-11-11', 'decision_asof_date':'2025-11-11',
        'scope':'US_LISTED_COMMON_STOCK'}

class VenuePITWitnessTests(unittest.TestCase):
    def run_query(self, **kw):
        d=deepcopy(BASE);d.update(kw);return audit(d)

    def blocked(self, **kw):
        with self.assertRaises(VenueEvidenceBlocked):self.run_query(**kw)

    def test_2025_transfer_announced_not_retrospectively_confirmed_asof(self):
        x=self.run_query()
        self.assertEqual((x['expected_symbol_from_transfer_document_research_only'],
                          x['expected_primary_listing_venue_research_only']),('FISV','NASDAQ'))
        self.assertTrue(x['contemporaneous_plan_was_published_asof_decision'])
        self.assertFalse(x['retrospective_transfer_confirmed_asof_decision'])
        self.assertTrue(x['future_disclosure_excluded_from_historical_decision'])
        self.assertIsNone(x['post_event_confirmation_source_10k'])
        self.assertEqual(x['status'],'CONTEMPORANEOUS_PLAN_ONLY_EXECUTION_UNCONFIRMED_ASOF')

    def test_2025_last_nyse_fi_session_planned(self):
        x=self.run_query(session_date='2025-11-10',decision_asof_date='2025-11-10')
        self.assertEqual((x['expected_symbol_from_transfer_document_research_only'],
                          x['expected_primary_listing_venue_research_only']),('FI','NYSE'))
        self.assertFalse(x['retrospective_transfer_confirmed_asof_decision'])

    def test_2026_retro_confirms_transfer_but_not_daily_history(self):
        x=self.run_query(session_date='2025-11-11',decision_asof_date='2026-02-20')
        self.assertTrue(x['retrospective_transfer_confirmed_asof_decision'])
        self.assertFalse(x['daily_listing_master_complete'])
        self.assertFalse(x['all_historical_venue_sessions_attested'])
        self.assertFalse(x['a1_release_ready'])

    def test_2026_current_symbol_research_only(self):
        x=self.run_query(session_date='2026-10-22',decision_asof_date='2026-10-22')
        self.assertEqual(x['expected_symbol_from_transfer_document_research_only'],'FISV')
        self.assertFalse(x['canonical_price_pass'])
        self.assertFalse(x['point_in_time_market_cap_attested'])
        self.assertEqual(x['registered_r92_count'],0)

    def test_10k_one_day_before_cannot_be_used(self):
        x=self.run_query(session_date='2025-11-11',decision_asof_date='2026-02-18')
        self.assertFalse(x['retrospective_transfer_confirmed_asof_decision'])
        self.assertIsNone(x['post_event_confirmation_source_10k'])

    def test_same_day_10k_filing_is_not_intraday_attested(self):
        x=self.run_query(session_date='2025-11-11',decision_asof_date='2026-02-19')
        self.assertFalse(x['retrospective_transfer_confirmed_asof_decision'])
        self.assertFalse(x['filing_intraday_acceptance_time_proven'])

    def test_same_day_8k_filing_is_not_intraday_attested(self):
        x=self.run_query(session_date='2025-10-29',decision_asof_date='2025-10-29')
        self.assertFalse(x['contemporaneous_plan_was_published_asof_decision'])
        self.assertFalse(x['filing_intraday_acceptance_time_proven'])

    def test_caller_has_no_override_for_future_document(self):
        x=deepcopy(BASE);x['override_evidence']='2026-02-19'
        with self.assertRaises(VenueEvidenceBlocked):audit(x)

    def test_negative_scope_and_time_mutations(self):
        cases=[
            {'issuer_cik':'798354'}, {'issuer_cik':798354}, {'issuer':'FISV'},
            {'scope':'BONDS'}, {'session_date':'2025-11-09'},
            {'session_date':'2025-11-08'}, {'session_date':'2025-10-20'},
            {'session_date':'2025-11-31'}, {'decision_asof_date':'2025-11-10'},
            {'decision_asof_date':'2026-10-24'}, {'decision_asof_date':'2025-11-xx'},
            {'session_date':'2026-10-24'}, {'session_date':'2026-10-23'},
            {'session_date':'2026-11-01'}, {'session_date':None},
            {'scope':None}, {'session_date':'2025-11-11T00:00Z'},
        ]
        for row in cases:
            with self.subTest(row=row):self.blocked(**row)

    def test_no_promotion_even_when_retrospective(self):
        x=self.run_query(session_date='2025-11-11',decision_asof_date='2026-02-20')
        for field in ('a1_release_ready','canonical_price_pass','issuer_mc_pass',
                      'g9_pass','c417_pass','source_data_licensing_rights_attested',
                      'cross_venue_260_session_replay_authorized',
                      'official_market_calendar_individually_attested','iphone_receipt_attested'):
            with self.subTest(field=field):self.assertFalse(x[field])
        self.assertEqual(x['real_money'],'NO-GO')
        self.assertEqual(x['execution'],'NONE')
        self.assertEqual(x['orders'],[])

    def test_empty_and_invalid_types(self):
        for obj in (None, [], {}, 42, 'x'):
            with self.subTest(obj=obj),self.assertRaises(VenueEvidenceBlocked): audit(obj)

    def test_input_not_mutated(self):
        src=deepcopy(BASE);original=deepcopy(src);audit(src);self.assertEqual(src,original)

if __name__=='__main__':unittest.main()