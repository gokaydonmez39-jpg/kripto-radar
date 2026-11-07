#!/usr/bin/env python3
"""Deterministic release preflight and negative tests; no network or SDKs."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from candidate_release_gate import assess, GATES, BLOCKERS

ROOT = Path(__file__).parent


class CandidateReleaseGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'candidate_manifest.json').read_text(encoding='utf-8'))

    def test_all_eight_covered(self):
        result = assess(self.manifest)
        self.assertEqual(result['total'], 8)
        self.assertEqual(result['research_review_ready'], 8)
        self.assertEqual(result['production_authorized'], 0)
        self.assertEqual(result['sdk_execution_pass'], 0)
        self.assertEqual(result['live_pit_pass'], 0)
        self.assertEqual(len(GATES), 8)
        self.assertEqual(set(GATES), {c['id'] for c in result['candidates']})
        self.assertTrue(all(c['status'] == 'BLOCKED_PENDING_EXTERNAL_EVIDENCE' for c in result['candidates']))

    def test_unique_gates_present_and_not_self_attested(self):
        report = assess(self.manifest)
        for row in report['candidates']:
            with self.subTest(row=row['id']):
                self.assertGreaterEqual(len(row['required_independent_gates']), 4)
                self.assertEqual(row['passed_independent_gates'], [])
                self.assertFalse(row['runtime_sdk_verified'])
                self.assertFalse(row['vendor_pit_verified'])
                self.assertFalse(row['financial_alpha_verified'])
                self.assertFalse(row['production_authorized'])
                self.assertEqual(len(row['snapshot_sha']), 40)

    def test_no_order_gate(self):
        self.assertIn('NO_ORDER_EVEN_PAPER_TRANSPORT_ISOLATION', GATES['alpaca-mcp'])
        self.assertIn('AUTHORITY', BLOCKERS)

    def test_weights_are_separate_license(self):
        self.assertIn('SOURCE_LICENSE_AND_MODEL_WEIGHTS_LICENSE_VERIFIED', GATES['timesfm'])

    def test_qlib_real_history_not_confused_with_synthetic(self):
        self.assertIn('AT_LEAST_500_VERIFIED_XNAS_SESSIONS', GATES['qlib'])
        self.assertIn('FIFTEEN_SESSION_PURGE_EMBARGO', GATES['qlib'])

    def test_no_mcp_unrestricted_tools(self):
        self.assertIn('ALL_TOOL_RESOURCE_PROMPT_SURFACES_ENUMERATED', GATES['mcp-use'])

    def test_reject_fake_source_pin(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['candidates'][0]['upstream_snapshot_sha'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, 'UPSTREAM_SHA_MISMATCH'):
            assess(manifest)

    def test_reject_source_alias_forgery(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['candidates'][3]['existing_registry_key'] = 'code:fake/source'
        with self.assertRaisesRegex(ValueError, 'REGISTRY_ALIAS_DRIFT'):
            assess(manifest)

    def test_reject_promoted_candidate(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['candidates'][0]['production_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'UNPROVEN_SUCCESS'):
            assess(manifest)

    def test_reject_new_paid_services(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['core_policy']['paid_new_services'] = True
        with self.assertRaisesRegex(ValueError, 'CORE_SIDE_EFFECT_paid_new_services'):
            assess(manifest)

    def test_reject_hidden_mcp_call_access(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['candidates'][1]['policy']['may_fetch_external_data'] = True
        with self.assertRaisesRegex(ValueError, 'FORBIDDEN_may_fetch_external_data'):
            assess(manifest)

    def test_report_mode_passes_but_production_mode_blocks(self):
        tool = ROOT / 'candidate_release_gate.py'
        ok = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True)
        deny = subprocess.run([sys.executable, str(tool), '--require-production'], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(deny.returncode, 3)
        self.assertEqual(json.loads(ok.stdout)['production_authorized'], 0)
        self.assertEqual(json.loads(deny.stdout)['production_authorized'], 0)


if __name__ == '__main__':
    unittest.main()
