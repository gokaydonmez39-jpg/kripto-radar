"""Offline red/green and adversarial acceptance for 477 official-source shadow."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

import official_477_shadow as s
import official_provider_raw_once as raw

UID_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
UID_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
HASH = '1' * 64
ASOF = '2026-10-31T14:05:56Z'

def fixture():
    symbols = raw.read_immutable_477_scope()
    assert len(symbols) == 477
    ids = {
        UID_A: ('cash_dividends', '2026-10-15', HASH),
        UID_B: ('stock_and_cash_mergers', '2026-10-30', HASH)
    }
    roles = {
        UID_A: (symbols[0],),
        UID_B: tuple(sorted((symbols[0], symbols[1])))
    }
    return {
        'status': raw.__dict__['audit_all_477'].__doc__ and
                  'ALL_477_BATCH_CHAINS_EXHAUSTED_NOT_MARKET_CLEARANCE',
        'requested_symbols': 477, 'batches': 20, 'http_pages': 20,
        'data_quality_requested': 'all',
        'cross_batch_unique_events_proven': True,
        'historical_pit_proven': False, 'may_clear_risk': False,
        'unique_event_ids_observed': 2,
        'observed_query_event_occurrences': 3,
        '_internal_id_index': ids,
        '_internal_symbol_roles': roles,
    }

class ShadowTests(unittest.TestCase):
    def test_valid_all477_exact_join_never_clears(self):
        result = s.build_477_shadow(asof_utc=ASOF, alpaca=fixture())
        summary, rows = result['summary'], result['rows']
        self.assertEqual(summary['scope_count'], 477)
        self.assertEqual(summary['unique_provider_events'], 2)
        self.assertEqual(summary['symbol_event_associations'], 3)
        self.assertEqual(summary['symbols_requiring_review'], 2)
        self.assertEqual(summary['symbols_unknown_not_clear'], 475)
        self.assertEqual(len(rows),477)
        self.assertTrue(all(not summary[k] for k in (
            'may_clear_risk','may_modify_al','may_change_stop_target',
            'may_notify','may_place_order','may_write_sheet',
            'may_promote_to_daily_eod','historical_pit_proven')))
        self.assertNotIn(UID_A, json.dumps(summary))
        self.assertNotIn(UID_B, json.dumps(summary))

    def test_empty_page_chain_is_not_clear(self):
        x=fixture()
        x['_internal_id_index']={}
        x['_internal_symbol_roles']={}
        x['unique_event_ids_observed']=0
        x['observed_query_event_occurrences']=0
        out=s.build_477_shadow(asof_utc=ASOF,alpaca=x)
        self.assertEqual(out['summary']['symbols_unknown_not_clear'],477)
        self.assertFalse(out['summary']['may_clear_risk'])

    def test_wrong_universe_order_refused(self):
        symbols=list(raw.read_immutable_477_scope())
        symbols[0],symbols[1]=symbols[1],symbols[0]
        with self.assertRaisesRegex(s.ShadowRefused, 'WATCHLIST_SHA_OR_ORDER_DRIFT'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),symbols=symbols)

    def test_cross_batch_multi_issuer_role_counts_once_each(self):
        out=s.build_477_shadow(asof_utc=ASOF,alpaca=fixture())
        rows=out['rows']
        self.assertEqual(rows[0]['alpaca_event_count'],2)
        self.assertEqual(rows[1]['alpaca_event_count'],1)
        self.assertEqual(out['summary']['unique_provider_events'],2)

    def test_missing_pagination_guard_refused(self):
        x=fixture();x['cross_batch_unique_events_proven']=False
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_SCOPE_OR_SOURCE_CONTRACT_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=x)

    def test_complete_quality_cannot_claim_all(self):
        x=fixture();x['data_quality_requested']='complete'
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_SCOPE_OR_SOURCE_CONTRACT_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=x)

    def test_missing_roles_fails_closed(self):
        x=fixture();x['_internal_symbol_roles'].pop(UID_A)
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_INTERNAL_INDEX_NOT_PROVEN'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=x)

    def test_duplicate_roles_refused(self):
        x=fixture()
        first=raw.read_immutable_477_scope()[0]
        x['_internal_symbol_roles'][UID_A]=(first,first)
        with self.assertRaisesRegex(s.ShadowRefused,'EVENT_ROLE_SCOPE_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=x)

    def test_role_outside_477_rejected(self):
        x=fixture();x['_internal_symbol_roles'][UID_A]=('ZZZZZZZZZZ',)
        with self.assertRaisesRegex(s.ShadowRefused,'EVENT_ROLE_SCOPE_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=x)

    def test_non_utc_asof_refused(self):
        with self.assertRaisesRegex(s.ShadowRefused,'ASOF_NOT_UTC'):
            s.build_477_shadow(asof_utc='2026-10-31T14:00:00+03:00',
                               alpaca=fixture())

    def test_sec_pilot_does_not_clear_others(self):
        sec={'status':s.SEC_STATUS,
             'first_public_availability_proven':False,'may_modify_al':False}
        out=s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),sec=sec)
        self.assertEqual(out['summary']['sec_pilot'],'ROAD_PILOT_FORMAT_OBSERVED')
        self.assertEqual(out['summary']['symbols_unknown_not_clear'],475)
        self.assertFalse(out['summary']['historical_pit_proven'])

    def test_sec_false_pit_certificate_refused(self):
        sec={'status':s.SEC_STATUS,
             'first_public_availability_proven':True,'may_modify_al':False}
        with self.assertRaisesRegex(s.ShadowRefused,'SEC_PILOT_EVIDENCE_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),sec=sec)

    def test_nasdaq_scope_flag_requires_unique_position(self):
        obj={'source':'NASDAQ_DIRECTORY','state':s.NAS_STATUS,
             'scope_status':'CURRENT_SNAPSHOT_REVIEW_ONLY',
             'flagged_watchlist_index_zero_based':1,
             'directory_flagged':2,
             'may_clear_risk':False,'may_modify_al':False}
        with self.assertRaisesRegex(s.ShadowRefused,'DIRECTORY_FLAG_INDEX_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),directory=obj)
        obj['directory_flagged']=1
        out=s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),directory=obj)
        self.assertEqual(out['rows'][1]['nasdaq_directory'],'FLAG_REVIEW_REQUIRED')
        self.assertFalse(out['summary']['may_modify_al'])

    def test_reject_nasdaq_claim_of_risk_clearance(self):
        obj={'source':'NASDAQ_HALTS','state':s.NAS_STATUS,
             'may_clear_risk':True,'may_modify_al':False}
        with self.assertRaisesRegex(s.ShadowRefused,'NASDAQ_PROBE_EVIDENCE_INVALID'):
            s.build_477_shadow(asof_utc=ASOF,alpaca=fixture(),halt=obj)

    def test_deterministic_hash_and_no_mutation_of_source(self):
        f=fixture();original=copy.deepcopy(f)
        a=s.build_477_shadow(asof_utc=ASOF,alpaca=f)
        b=s.build_477_shadow(asof_utc=ASOF,alpaca=f)
        self.assertEqual(a,b)
        self.assertEqual(f,original)

    def test_live_missing_secret_fails_before_any_provider_call(self):
        with patch.dict('os.environ',{'XRAY_ALPACA_DATA_KEY_ID':'',
             'XRAY_ALPACA_DATA_SECRET_KEY':'',
             'XRAY_SEC_DECLARED_USER_AGENT':''},clear=True):
            with patch.object(raw,'audit_all_477',
                 side_effect=AssertionError('HTTP_MUST_NOT_HAPPEN')):
                with self.assertRaisesRegex(s.ShadowRefused,
                         'MISSING_AUTHORIZED_SOURCE_CONFIGURATION'):
                    s.run_manual_live()

if __name__ == '__main__':
    unittest.main()
