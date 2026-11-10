#!/usr/bin/env python3
"""Strict negative tests; calendar is real, data is synthetic."""
import copy
import json
from datetime import date
from pathlib import Path
import unittest

from candidate_independent_preflight import assess, check_xnas_sessions, PACKAGES

ROOT = Path(__file__).resolve().parent

class CandidatePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT/'candidate_manifest.json').read_text(encoding='utf-8'))
        import exchange_calendars as xc
        x = xc.get_calendar('XNAS')
        cls.sessions = [a.strftime('%Y-%m-%d') for a in x.sessions_in_range('2023-01-03','2026-11-06')][:500]

    def test_8_candidates_no_production(self):
        r = assess(self.manifest, distribution_versions={})
        self.assertEqual(r['candidate_count'],8)
        self.assertEqual(r['sdk_runtime_pass'],0)
        self.assertEqual(r['licence_pass'],0)
        self.assertEqual(r['production_approved'],0)
        self.assertTrue(all(x['sdk_executed'] is False for x in r['candidates']))

    def test_existing_installed_package_is_not_sdk_pass(self):
        r = assess(self.manifest, distribution_versions={'pydantic-ai-slim':'9.9.9'})
        x = next(x for x in r['candidates'] if x['candidate']=='pydantic-ai')
        self.assertTrue(x['distribution_installed'])
        self.assertFalse(x['installed_version_matched_to_reviewed_commit'])
        self.assertFalse(x['sdk_executed'])

    def test_no_distribution_not_found_is_explicit(self):
        r=assess(self.manifest, distribution_versions={})
        self.assertEqual(r['candidates'][0]['status'],'SDK_NOT_INSTALLED')

    def test_js_is_not_python_sdk(self):
        r=assess(self.manifest, distribution_versions={})
        x=next(x for x in r['candidates'] if x['candidate']=='tradingview-charts')
        self.assertEqual(x['status'],'JS_ARTIFACT_NOT_TESTED')

    def test_bad_distribution_input_rejected(self):
        with self.assertRaisesRegex(ValueError,'DISTRIBUTION_INPUT_INVALID'):
            assess(self.manifest, distribution_versions={'fake':'injected\nstatus=PASS'})

    def test_manifest_downgrade_rejected(self):
        m=copy.deepcopy(self.manifest)
        m['candidates'][0]['production_authorized']=True
        with self.assertRaisesRegex(ValueError,'UNPROVEN_SUCCESS_production_authorized'):
            assess(m,distribution_versions={})

    def test_xnas_real_calendar_shape(self):
        r=check_xnas_sessions(self.sessions)
        self.assertEqual(r['session_count'],500)
        self.assertFalse(r['external_data_rights_verified'])
        self.assertFalse(r['per_symbol_477_pit_verified'])
        self.assertFalse(r['production_authorized'])

    def test_499_rejected(self):
        with self.assertRaisesRegex(ValueError,'XNAS_INSUFFICIENT_SESSIONS'):
            check_xnas_sessions(self.sessions[:499])

    def test_min_lowering_rejected(self):
        with self.assertRaisesRegex(ValueError,'FROZEN_XNAS_MIN_HISTORY_500'):
            check_xnas_sessions(self.sessions[:100],expected_min=100)

    def test_duplicate_session_rejected(self):
        v=self.sessions.copy()
        v[1]=v[0]
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_UNORDERED_XNAS_DATE'):
            check_xnas_sessions(v)

    def test_unsorted_rejected(self):
        v=self.sessions.copy()
        v[0],v[1]=v[1],v[0]
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_UNORDERED_XNAS_DATE'):
            check_xnas_sessions(v)

    def test_missing_xnas_session_rejected(self):
        v=self.sessions.copy()
        del v[240]
        v.append('2026-11-06')
        with self.assertRaisesRegex(ValueError,'NON_XNAS_OR_MISSING_SESSION'):
            check_xnas_sessions(v)

    def test_weekend_rejected(self):
        v=self.sessions.copy()
        v[5]='2023-01-07'  # Saturday: cannot be an XNAS session
        with self.assertRaisesRegex(ValueError,'NON_XNAS_OR_MISSING_SESSION|DUPLICATE_OR_UNORDERED_XNAS_DATE'):
            check_xnas_sessions(v)

    def test_bad_calendar_date_rejected(self):
        v=self.sessions.copy()
        v[1]='2023-02-30'
        with self.assertRaisesRegex(ValueError,'INVALID_XNAS_DATE'):
            check_xnas_sessions(v)

    def test_bool_or_float_min_rejected(self):
        for n in (False,500.0):
            with self.subTest(n=n),self.assertRaisesRegex(ValueError,'FROZEN_XNAS_MIN_HISTORY_500'):
                check_xnas_sessions(self.sessions,expected_min=n)

    def test_duplicate_manifest_rejected(self):
        m=copy.deepcopy(self.manifest)
        m['candidates'][1]['id']=m['candidates'][0]['id']
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_MISSING_ID'):
            assess(m,distribution_versions={})

if __name__=='__main__':
    unittest.main()