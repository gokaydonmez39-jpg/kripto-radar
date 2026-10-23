"""Adversarial strictly synthetic AU/VV scope and settled EOD counterexamples."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import unittest

from xray_v50_au_vv_eod_reconcile_shadow import audit,EODScopeBlocked,micros

F=Path(__file__).with_name('xray_v50_au_vv_synthetic_fixture.json')
def sample():return json.loads(F.read_text(encoding='utf-8'))

class SyntheticEODGateTests(unittest.TestCase):
    def bad(self,change):
        data=sample();change(data)
        with self.assertRaises(EODScopeBlocked):audit(data)

    def test_valid_synthetic_au_vv_arithmetic_never_grants_authority(self):
        x=audit(sample())
        self.assertTrue(x['vv_all_issues_is_not_one_issue_reference'])
        self.assertTrue(x['rth_closing_auction_counted_once'])
        self.assertTrue(x['synthetic_net_corrections_arithmetic_checked'])
        self.assertTrue(x['three_synthetic_au_phases_checked'])
        for k in ('real_utp_au_final_received','real_utp_vv_received',
                  'independent_real_per_issue_reference_verified',
                  'actual_correction_lineage_and_source_coverage_verified',
                  'actual_provider_auction_verified','legal_non_display_entitlement_verified',
                  'official_session_and_venue_verified','official_2026_utp_spec_runtime_mapping_verified',
                  'actual_90_symbol_session_completeness_verified',
                  'a0_release_ready','a1_release_ready','a2_release_ready','a3_release_ready',
                  'canonical_price_pass','issuer_mc_pass','g9_pass','c417_pass','iphone_receipt_attested'):
            with self.subTest(field=k): self.assertIs(x[k],False)
        self.assertEqual((x['registered_r92_count'],x['execution'],x['real_money']),
                         (0,'NONE','NO-GO'))
        self.assertEqual(x['orders'],[])

    def test_provider_auction_not_added_twice(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__(
            'rth_including_auction_microshares',15000000))

    def test_auction_omitted_rth_should_be_rejected(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__(
            'rth_including_auction_microshares',7000000))

    def test_extended_vs_all_hours_mismatch(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('extended_hours_microshares',0))

    def test_rth_continuous_mismatch(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('rth_continuous_microshares',8000000))

    def test_canceled_shares_larger_than_original(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('canceled_microshares',13000000))

    def test_correction_delta_mismatch(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('corrected_delta_microshares',2000000))

    def test_final_report_still_old_preliminary_volume(self):
        self.bad(lambda d:d['utp_issue_summaries'][2].__setitem__('volume_microshares',12000000))

    def test_missing_final_report(self):
        self.bad(lambda d:d['utp_issue_summaries'].pop())

    def test_preliminary_report_used_as_final_incorrect(self):
        self.bad(lambda d:d['utp_issue_summaries'][0].__setitem__(
            'phase','FINAL_AFTER_END_TRADE_REPORTING'))

    def test_final_without_end_reporting_message(self):
        self.bad(lambda d:d['utp_issue_summaries'][2].__setitem__(
            'synthetic_end_report_control_seen',False))

    def test_premature_end_reporting_claim(self):
        self.bad(lambda d:d['utp_issue_summaries'][0].__setitem__(
            'synthetic_end_report_control_seen',True))

    def test_wrong_message_type_vv_as_symbol_issue(self):
        self.bad(lambda d:d['utp_issue_summaries'][2].__setitem__('message_type','V'))

    def test_wrong_category_vv_as_symbol_issue(self):
        self.bad(lambda d:d['utp_issue_summaries'][2].__setitem__('category','V'))

    def test_wrong_aggregate_vv_scope(self):
        self.bad(lambda d:d['utp_all_issues_snapshot'].__setitem__('scope','ONE_ISSUE'))

    def test_wrong_aggregate_vv_message(self):
        self.bad(lambda d:d['utp_all_issues_snapshot'].__setitem__('message_type','U'))

    def test_vv_numeric_equals_single_issue_even_then_not_proof(self):
        d=sample();d['utp_all_issues_snapshot']['volume_microshares']=13000000
        x=audit(d)
        self.assertTrue(x['vv_all_issues_is_not_one_issue_reference'])
        self.assertFalse(x['independent_real_per_issue_reference_verified'])

    def test_fractional_six_decimal_resolution_accepted_synthetically(self):
        d=sample();d['synthetic_replay']['original_microshares']+=1
        d['synthetic_replay']['net_all_hours_microshares']+=1
        d['synthetic_replay']['extended_hours_microshares']+=1
        d['utp_issue_summaries'][2]['volume_microshares']+=1
        x=audit(d)
        self.assertFalse(x['canonical_price_pass'])

    def test_float_fractional_units_denied(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('original_microshares',12.5))

    def test_bool_integer_units_denied(self):
        self.bad(lambda d:d['provider_auction'].__setitem__('volume_microshares',True))

    def test_negative_microshares_denied(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__('canceled_microshares',-1))

    def test_large_overflow_denied(self):
        self.bad(lambda d:d['synthetic_replay'].__setitem__(
            'original_microshares',10**25))

    def test_auction_provider_source_is_not_utp(self):
        self.bad(lambda d:d['provider_auction'].__setitem__('source','OFFICIAL_UTP_AU'))

    def test_auction_caller_cannot_claim_real_trade_ids(self):
        self.bad(lambda d:d['provider_auction'].__setitem__(
            'real_auction_trade_ids_matched',True))

    def test_auction_from_other_symbol(self):
        self.bad(lambda d:d['provider_auction'].__setitem__('issue','MSFT'))

    def test_wrong_auction_aggregation_scope(self):
        self.bad(lambda d:d['provider_auction'].__setitem__(
            'scope','ALL_NASDAQ_ISSUES_ALL_MARKETS'))

    def test_wrong_auction_component(self):
        self.bad(lambda d:d['provider_auction'].__setitem__('volume_microshares',5000000))

    def test_wrong_per_issue_record_symbol(self):
        self.bad(lambda d:d['utp_issue_summaries'][1].__setitem__('issue','MSFT'))

    def test_wrong_report_date(self):
        self.bad(lambda d:d['utp_issue_summaries'][1].__setitem__(
            'session_day','2026-10-21'))

    def test_wrong_vv_date(self):
        self.bad(lambda d:d['utp_all_issues_snapshot'].__setitem__(
            'session_day','2026-10-21'))

    def test_wrong_eastern_rth_clock(self):
        self.bad(lambda d:d.__setitem__('et_close','20:00'))

    def test_wrong_source_version(self):
        self.bad(lambda d:d.__setitem__('utp_spec', 'https://example.com/'))

    def test_false_real_data_authority_rejected(self):
        self.bad(lambda d:d.__setitem__('actual_evidence_attested', True))

    def test_extra_sip_trade_data_rejected(self):
        self.bad(lambda d:d.__setitem__('raw_trade_ids',[123]))

    def test_bad_fixture_date_and_type(self):
        for value in ('2026-02-30','2026-10-23','2025-11-11',None,20261022):
            with self.subTest(value=value):
                self.bad(lambda d:d.__setitem__('session_day',value))

    def test_wrong_source_api(self):
        self.bad(lambda d:d.__setitem__('auction_doc','https://not-known.com'))

    def test_negative_or_invalid_record(self):
        self.bad(lambda d:d['utp_issue_summaries'][1].__setitem__('volume_microshares',-1))

    def test_synthetic_only(self):
        self.bad(lambda d:d.__setitem__('sample_type','ACTUAL_SIP_WITH_RIGHTS'))

    def test_reject_wrong_doc_type(self):
        for x in (None,42,True,[],{}):
            with self.subTest(value=x),self.assertRaises(EODScopeBlocked):audit(x)

    def test_input_is_never_modified(self):
        x=sample();y=deepcopy(x);audit(x);self.assertEqual(x,y)

if __name__=='__main__':unittest.main()