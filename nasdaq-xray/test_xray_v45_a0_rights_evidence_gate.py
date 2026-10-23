"""Offline tests for A0 documentary evidence intake and fail-closed behavior."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import unittest
from xray_v45_a0_rights_evidence_gate import audit, RightsBlocked, CLAIMS

FIXTURE=Path(__file__).with_name('xray_v45_a0_empty_rights_evidence.json')


def example():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def submitted():
    d=example()
    for x in CLAIMS:
        d['claims'][x]={'status':'SUBMITTED_UNREVIEWED',
                        'document_sha256':'a'*64,'document_date':'2026-10-22'}
    return d


class RightsEvidenceTests(unittest.TestCase):
    def blocked(self, change):
        d=example();change(d)
        with self.assertRaises(RightsBlocked):audit(d)

    def test_missing_seven_claims_stays_blocked(self):
        v=audit(example())
        self.assertEqual(v['claim_count'],7)
        self.assertEqual(v['status'],'BLOCKED_MISSING_USER_APPLICABLE_EVIDENCE')
        self.assertEqual(v['missing_claims'],list(CLAIMS))
        self.assertFalse(v['a0_release_ready'])
        self.assertFalse(v['may_run_vendor_historical_backfill'])

    def test_even_all_submitted_remains_unattested(self):
        v=audit(submitted())
        self.assertEqual(v['submitted_unreviewed_count'],7)
        self.assertEqual(v['status'],'BLOCKED_AWAIT_EXTERNAL_ENTITLEMENT_REVIEW')
        self.assertFalse(v['independent_provider_entitlement_attested'])
        self.assertFalse(v['non_display_and_retention_rights_attested'])
        self.assertFalse(v['canonical_price_pass'])
        self.assertEqual(v['registered_r92_count'],0)

    def test_provider_denial_stronger_than_unreviewed(self):
        d=submitted()
        d['claims']['unattended_github_runner_processing']['status']='PROVIDER_DENIED'
        v=audit(d)
        self.assertEqual(v['status'],'BLOCKED_PROVIDER_DENIAL')
        self.assertEqual(v['denied_claims'],['unattended_github_runner_processing'])

    def test_partial_submitted_still_missing(self):
        d=example()
        d['claims']['account_specific_plan_and_feed']=submitted()['claims']['account_specific_plan_and_feed']
        v=audit(d)
        self.assertEqual(v['submitted_unreviewed_count'],1)
        self.assertEqual(len(v['missing_claims']),6)

    def test_reject_forged_verified_and_pass_labels(self):
        for word in ('VERIFIED','PASS','APPROVED','SIGNED','true',True):
            with self.subTest(word=word):
                self.blocked(lambda d:d['claims']['account_specific_plan_and_feed'].__setitem__('status',word))

    def test_reject_raw_contract_text_and_credentials(self):
        for key in ('api_key','raw_contract','bearer_token','customer_id','name','email'):
            with self.subTest(key=key):
                self.blocked(lambda d:d.__setitem__(key,'SENSITIVE_DO_NOT_STORE'))

    def test_reject_secret_in_claim(self):
        self.blocked(lambda d:d['claims']['non_display_usage_classification'].__setitem__('api_secret','***'))

    def test_reject_missing_claim(self):
        self.blocked(lambda d:d['claims'].pop('private_cache_and_retention'))

    def test_reject_fake_document_hash_and_url(self):
        for val in ('https://example.org/private', 'abc','z'*64,42):
            with self.subTest(val=val):
                self.blocked(lambda d:d['claims']['account_specific_plan_and_feed'].update(status='SUBMITTED_UNREVIEWED',document_sha256=val,document_date='2026-10-22'))

    def test_reject_future_and_bad_document_dates(self):
        for val in ('2026-10-24','2026-02-30','2026/10/22',None):
            with self.subTest(val=val):
                self.blocked(lambda d:d['claims']['account_specific_plan_and_feed'].update(status='SUBMITTED_UNREVIEWED',document_sha256='a'*64,document_date=val))

    def test_reject_missing_metadata_with_submitted_state(self):
        self.blocked(lambda d:d['claims']['account_specific_plan_and_feed'].__setitem__('status','SUBMITTED_UNREVIEWED'))

    def test_reject_metadata_on_missing_claim(self):
        self.blocked(lambda d:d['claims']['account_specific_plan_and_feed'].__setitem__('document_sha256','a'*64))

    def test_reject_modified_sources_and_catalog_schema(self):
        self.blocked(lambda d:d['catalog_source_ids'].append('RT-999'))
        self.blocked(lambda d:d.__setitem__('catalog_schema','NEW_AL_PASSED'))

    def test_reject_wrong_usage_and_provider(self):
        self.blocked(lambda d:d.__setitem__('provider','ANOTHER'))
        self.blocked(lambda d:d.__setitem__('usage','LIVE_AUTO_TRADING'))

    def test_reject_epoch_rollback_and_unknown_field(self):
        self.blocked(lambda d:d.__setitem__('asof_date','2026-10-22'))
        self.blocked(lambda d:d['claims']['non_display_usage_classification'].__setitem__('approved',True))

    def test_complete_safety_invariants(self):
        for obj in (example(),submitted()):
            v=audit(obj)
            for field in ('a0_release_ready','may_run_vendor_historical_backfill',
                          'a1_release_ready','a2_pagination_complete',
                          'a3_trade_correction_complete','canonical_price_pass',
                          'issuer_mc_pass','g9_pass','c417_pass','iphone_receipt_attested'):
                with self.subTest(field=field):self.assertIs(v[field],False)
            self.assertEqual(v['real_money'],'NO-GO')
            self.assertEqual(v['execution'],'NONE')
            self.assertFalse(v['broker'])
            self.assertEqual(v['orders'],[])
            self.assertTrue(v['unknown_never_pass'])

    def test_inputs_immutable(self):
        obj=submitted();copy=deepcopy(obj)
        audit(obj)
        self.assertEqual(copy,obj)

    def test_reject_wrong_input_types(self):
        for v in (None,[],'x',44,True):
            with self.subTest(v=v),self.assertRaises(RightsBlocked):audit(v)

if __name__ == '__main__':unittest.main()