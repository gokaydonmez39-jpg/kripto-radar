#!/usr/bin/env python3
"""No-provider-calls negative and acceptance tests for mock adapter ABI."""
import copy
from datetime import date
import json
from pathlib import Path
import unittest

from candidate_shadow import (
    audit_local_provider_contract, audit_mock_mcp_tools,
    validate_offline_observation, RECORD_SCHEMA, TOOL_SCHEMA, PROVIDER_SCHEMA,
)

ROOT = Path(__file__).parent


class CandidateShadowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT/'candidate_manifest.json').read_text(encoding='utf-8'))
        cls.index = {c['id']:c for c in cls.manifest['candidates']}

    def evidence(self, **fields):
        c = self.index['pydantic-ai']
        obj = {'schema':RECORD_SCHEMA,'candidate_id':'pydantic-ai',
               'source_url':c['url'],'source_sha':c['upstream_snapshot_sha'],
               'status':'DOCS_VERIFIED','mode':'OFFLINE_FIXTURE_ONLY',
               'asof_et':'2026-11-06','observed_at_utc':'2026-11-07T10:00:00Z',
               'evidence':{'fixture':True},'may_generate_al':False,
               'may_write_private_sheet':False,'may_emit_alert':False,
               'may_place_order':False,'may_fetch_vendor_api':False,
               'model_executed':False}
        obj.update(fields)
        return obj

    def mcp(self, tools=None, **fields):
        obj={'schema':TOOL_SCHEMA,'mode':'MOCK_METADATA_ONLY',
             'candidate_id':'mcp-use', 'tools': tools if tools is not None else [
                {'name':'get_public_repository_metadata', 'read_only':True,
                 'side_effects':False}]}
        obj.update(fields)
        return obj

    def provider(self, **fields):
        obj={'schema':PROVIDER_SCHEMA, 'candidate_id':'openbb-v5',
             'mode':'OFFLINE_FIXTURE_ONLY', 'asof_et':'2026-11-06',
             'decision_cutoff_utc':'2026-11-07T01:00:00Z',
             'known_at_utc':'2026-11-06T23:00:00Z', 'symbol':'AAPL',
             'venue':'IEX', 'basis':'RAW', 'rights_independently_verified':False}
        obj.update(fields)
        return obj

    def denied(self, fn, code):
        with self.assertRaisesRegex(ValueError, code):
            fn()

    def test_evidence_pass(self):
        r=validate_offline_observation(self.manifest,self.evidence())
        self.assertEqual(r['status'],'DOCS_VERIFIED')
        self.assertFalse(r['production_authorized'])

    def test_false_live_claim_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(status='LIVE_PIT_PASS')),'UNAUTHORIZED_STATUS')

    def test_evidence_wrong_sha_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(source_sha='0'*40)),'EVIDENCE_SOURCE_SHA_MISMATCH')

    def test_evidence_wrong_url_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(source_url='https://attacker.invalid')),
                    'EVIDENCE_SOURCE_URL_MISMATCH')

    def test_evidence_order_escalation_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(may_place_order=True)),'AUTHORITY_ESCALATION_may_place_order')

    def test_evidence_model_claim_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(model_executed=True)),'AUTHORITY_ESCALATION_model_executed')

    def test_evidence_future_observation_requirement(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(observed_at_utc='2026-11-05T10:00:00Z')),
                    'OBSERVED_BEFORE_ASOF')

    def test_evidence_utc_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(observed_at_utc='2026-11-07T13:00:00+03:00')),
                    'TIMESTAMP_NOT_UTC')

    def test_evidence_nan_denied(self):
        self.denied(lambda:validate_offline_observation(
            self.manifest,self.evidence(evidence={'metric':float('nan')})),
                    'INVALID_EVIDENCE_VALUE')

    def test_evidence_missing_flags_denied(self):
        p=self.evidence(); del p['may_emit_alert']
        self.denied(lambda:validate_offline_observation(
            self.manifest,p),'AUTHORITY_ESCALATION_may_emit_alert')

    def test_mcp_mock_pass(self):
        r=audit_mock_mcp_tools(self.mcp())
        self.assertEqual(r['checked_tools'],1)
        self.assertFalse(r['connected_server'])

    def test_mcp_paper_order_denied(self):
        self.denied(lambda:audit_mock_mcp_tools(self.mcp([
            {'name':'submit_paper_order','read_only':True,'side_effects':False}])),
                    'MCP_TOOL_DENIED')

    def test_mcp_unapproved_read_denied(self):
        self.denied(lambda:audit_mock_mcp_tools(self.mcp([
            {'name':'get_private_sheet','read_only':True,'side_effects':False}])),
                    'MCP_TOOL_DENIED')

    def test_mcp_duplicate_denied(self):
        t={'name':'get_public_repository_metadata','read_only':True,'side_effects':False}
        self.denied(lambda:audit_mock_mcp_tools(self.mcp([t,t])), 'DUPLICATE_MCP_TOOL')

    def test_mcp_side_effect_denied(self):
        self.denied(lambda:audit_mock_mcp_tools(self.mcp([
            {'name':'get_sec_filing_metadata','read_only':True,'side_effects':True}])),
                    'MCP_SIDE_EFFECT_DENIED')

    def test_mcp_external_connection_denied(self):
        self.denied(lambda:audit_mock_mcp_tools(self.mcp(mode='CONNECT_LIVE')),
                    'MCP_LIVE_CONNECT_DENIED')

    def test_mcp_extra_fields_denied(self):
        self.denied(lambda:audit_mock_mcp_tools(self.mcp([
            {'name':'get_public_repository_metadata','read_only':True,
             'side_effects':False,'hidden_tools':['send_order']}])),
                    'MCP_TOOL_FIELDS_INVALID')

    def test_mock_provider_pass(self):
        r=audit_local_provider_contract(self.provider())
        self.assertTrue(r['canonical_contract_compatible_claim'])
        self.assertFalse(r['production_authorized'])

    def test_mock_provider_other_venue_is_not_canonical(self):
        r=audit_local_provider_contract(self.provider(venue='US_CONSOLIDATED'))
        self.assertFalse(r['canonical_contract_compatible_claim'])

    def test_mock_provider_adjusted_is_not_canonical(self):
        r=audit_local_provider_contract(self.provider(basis='SPLIT_ADJUSTED'))
        self.assertFalse(r['canonical_contract_compatible_claim'])

    def test_mock_provider_pit_lookahead_denied(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            known_at_utc='2026-11-07T02:00:00Z')), 'PIT_LOOKAHEAD')

    def test_mock_provider_rights_pass_forgery_denied(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            rights_independently_verified=True)), 'UNAUTHORIZED_RIGHTS_CERTIFICATION')

    def test_mock_provider_wrong_candidate_denied(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            candidate_id='timesfm')), 'WRONG_PROVIDER_CANDIDATE')

    def test_mock_provider_invalid_symbol_denied(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            symbol='BTC/USDT')), 'INVALID_SYMBOL')

    def test_mock_provider_offline_only(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            mode='LIVE')), 'PROVIDER_LIVE_DENIED')

    def test_mock_provider_missing_timestamp(self):
        self.denied(lambda:audit_local_provider_contract(self.provider(
            known_at_utc=None)), 'TIMESTAMP_NOT_UTC')


if __name__ == '__main__':
    unittest.main()
