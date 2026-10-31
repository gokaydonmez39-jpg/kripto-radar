"""Adversarial tests for isolated private official-risk shadow. Network is forbidden."""
from __future__ import annotations
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

import official_477_shadow_daily as s

def fixtures():
    symbols = list(s.provider.read_immutable_477_scope())
    today = datetime.now(timezone.utc).date().isoformat()
    snap = {
        'asof_et': today,
        'scope_sha256': s.runner.sha_symbols(symbols),
        'analysis_fingerprint_sha256': s.runner.analysis_fingerprint(),
        'requested_symbols': 477, 'processed_symbols': 477,
        'valid_data_symbols': 477, 'remaining_symbols': 0,
        'insufficient_data_symbols': 0,
        'coverage_complete': True, 'valid_data_coverage_complete': True,
        'new_signal_publishable': True,
        'not_broker': True, 'orders_sent': 0, 'auto_trading': False,
        'failed_groups': [],
        'rows': [{'symbol': x, 'asof_et': today, 'decision': 'ELE'}
                 for x in symbols],
        'counts': {'START': 477, 'TEKNIK_AL_ADAYI': 0,
                   'YAKIN_IZLE': 0, 'ELE': 477, 'VERI_YETERSIZ': 0},
    }
    alpaca = {
        'status': 'ALL_477_BATCH_CHAINS_EXHAUSTED_NOT_MARKET_CLEARANCE',
        'requested_symbols': 477, 'cross_batch_unique_events_proven': True,
        'unique_event_ids_observed': 0, 'http_pages': 20,
        'links': {x: () for x in symbols},
    }
    sec = {'status': 'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE',
           'parser_status': 'SEC_EVENTS_REVIEW'}
    nasdaq = {'status': 'SNAPSHOT_RECENT_REVIEW_ONLY',
              'veto_symbols': frozenset()}
    observed = datetime.now(timezone.utc).isoformat()
    return snap, symbols, alpaca, sec, nasdaq, observed

class Shadow477Tests(TestCase):
    def render(self, snap, symbols, alpaca, sec, nasdaq, observed):
        return s.compose_shadow(snap, symbols, observed_at=observed,
                                alpaca=alpaca, sec=sec, nasdaq=nasdaq)

    def test_exact_477_base_no_false_market_clearance(self):
        data = fixtures()
        self.assertEqual(s.validate_eod_snapshot(data[0], data[1]),
                         datetime.now(timezone.utc).date())
        m = self.render(*data)
        self.assertEqual(m['records_count'], 477)
        self.assertEqual(set(m['states']), {'REVIEW_REQUIRED','UNKNOWN'})
        self.assertEqual(m['states']['REVIEW_REQUIRED'], 1)  # ROAD SEC
        self.assertEqual(m['states']['UNKNOWN'], 476)
        self.assertEqual([r for r in m['records'] if
                          r['symbol']=='ROAD'][0]['sec']['status'],
                         'PILOT_OBSERVED_NOT_PIT')
        for k, v in s.NO_AUTHORITY.items():
            self.assertIs(m[k], v)
        self.assertTrue(all(r['state']!='CLEAR' for r in m['records']))

    def test_sec_road_only_other_476_unknown(self):
        snap, syms, a, sec, n, observed = fixtures()
        m = self.render(snap,syms,a,sec,n,observed)
        self.assertEqual(sum(r['sec']['status']==
                             'UNKNOWN_NO_477_CIK_COVERAGE'
                             for r in m['records']),476)
        sec['status']='SOURCE_REFUSED'
        m = self.render(snap,syms,a,sec,n,observed)
        self.assertEqual(m['states'],{'UNKNOWN':477})
        self.assertEqual(next(r for r in m['records']
            if r['symbol']=='ROAD')['sec']['status'],
            'PILOT_REFUSED_UNKNOWN')

    def test_merger_one_id_two_watchlist_roles_review(self):
        snap, syms, a, sec, n, observed = fixtures()
        uid='4d295965-0892-430c-950b-f31bedb5df72'
        for x in ('MU','NVDA'):
            a['links'][x]=((uid,'stock_and_cash_mergers',snap['asof_et']),)
        a['unique_event_ids_observed']=1
        m=self.render(snap,syms,a,sec,n,observed)
        self.assertEqual(m['alpaca_unique_events_observed'],1)
        self.assertEqual(m['alpaca_symbol_links'],2)
        self.assertEqual(m['states']['REVIEW_REQUIRED'],3)
        self.assertNotIn(uid,json.dumps(m))
        self.assertEqual(m['records'][0]['alpaca']['groups'],
                         {'stock_and_cash_mergers':1})

    def test_reject_477_join_missing_duplicate_bad_uuid_or_future(self):
        snap, syms, a, sec, n, observed = fixtures()
        del a['links']['MU']
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_SYMBOL_JOIN_INVALID'):
            self.render(snap,syms,a,sec,n,observed)
        a['links']['MU']=(('id','cash_dividends',
                          snap['asof_et']),)*2
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_LINK_INVALID'):
            self.render(snap,syms,a,sec,n,observed)
        a['links']['MU']=(('id','cash_dividends',
             (datetime.now(timezone.utc).date()+timedelta(days=1)).isoformat()),)
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_EVENT_AFTER_ASOF'):
            self.render(snap,syms,a,sec,n,observed)

    def test_cannot_clear_on_unknown_or_missing_provider(self):
        snap,syms,a,sec,n,observed=fixtures()
        a['cross_batch_unique_events_proven']=False
        with self.assertRaisesRegex(s.ShadowRefused,'ALPACA_UNVERIFIED'):
            self.render(snap,syms,a,sec,n,observed)
        a['cross_batch_unique_events_proven']=True
        sec['status']='SKIPPED_NO_AUTHORIZED_INPUT'
        m=self.render(snap,syms,a,sec,n,observed)
        self.assertEqual(m['states'],{'UNKNOWN':477})

    def test_nasdaq_snapshot_not_mistaken_for_live_clean(self):
        snap,syms,a,sec,n,observed=fixtures()
        n['veto_symbols']=frozenset({'MU'})
        m=self.render(snap,syms,a,sec,n,observed)
        self.assertEqual(m['records'][0]['state'],'REVIEW_REQUIRED')
        self.assertEqual(m['records'][1]['nasdaq']['status'],
                         'UNKNOWN_NO_CURRENT_CLEARANCE')
        self.assertFalse(m['market_clearance_proven'])

    def test_snapshot_changed_policy_scope_or_partial_rejected(self):
        snap,syms,*_=fixtures()
        for key,val in (('scope_sha256','0'*64),
                        ('analysis_fingerprint_sha256','0'*64),
                        ('processed_symbols',476),
                        ('valid_data_coverage_complete',False),
                        ('new_signal_publishable',False)):
            wrong=dict(snap);wrong[key]=val
            with self.subTest(key=key),self.assertRaises(Exception):
                s.validate_eod_snapshot(wrong,syms)

    def test_read_only_private_write_permissions_and_readback(self):
        snap,syms,a,sec,n,observed=fixtures()
        manifest=self.render(snap,syms,a,sec,n,observed)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'manifest.json'
            s.write_private(path,manifest)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(len(json.loads(path.read_text())['records']),477)
            self.assertFalse((Path(d)/'manifest.json.tmp').exists())

    def test_nasdaq_old_or_corrupt_witness_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'guard.json'
            obs=datetime.now(timezone.utc).isoformat()
            p.write_text(json.dumps({
                'generated_at_utc':
                    (datetime.now(timezone.utc)-timedelta(days=4)).isoformat(),
                'alpha_authority':False,
                'candidate_safety':{'veto_symbols':['MU']}}))
            g=s.read_nasdaq_witness(p,obs)
            self.assertEqual(g['status'],'SNAPSHOT_STALE_UNKNOWN')
            self.assertFalse(g['may_clear_risk'])
            p.write_text('{')
            self.assertEqual(s.read_nasdaq_witness(p,obs)['status'],
                             'SNAPSHOT_REFUSED_UNKNOWN')

    def test_missing_private_eod_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(s.provider,'audit_all_477',
                    side_effect=AssertionError('NO_HTTP_ALLOWED')):
                out=io.StringIO()
                with redirect_stdout(out):
                    result=s.main([
                        '--snapshot',str(Path(d)/'missing.json'),
                        '--output',str(Path(d)/'manifest.json'),
                        '--nasdaq-witness',str(Path(d)/'guard.json')])
            self.assertEqual(result,0)
            self.assertIn('SKIPPED_NO_VERIFIED_PRIVATE_EOD',out.getvalue())

    def test_no_alpaca_credentials_refused_before_any_network(self):
        snap,syms,*_=fixtures()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'latest.json';p.write_text(json.dumps(snap))
            out=io.StringIO()
            with patch.dict(s.os.environ,
                    {'XRAY_ALPACA_DATA_KEY_ID':'',
                     'XRAY_ALPACA_DATA_SECRET_KEY':''}):
                with patch.object(s.provider,'audit_all_477',
                        side_effect=AssertionError('NO_HTTP_ALLOWED')):
                    with redirect_stdout(out):
                        code=s.main(['--snapshot',str(p),
                            '--output',str(Path(d)/'shadow.json'),
                            '--nasdaq-witness',str(Path(d)/'guard.json')])
            self.assertEqual(code,4)
            self.assertIn('SOURCE_REFUSED_UNKNOWN',out.getvalue())
            self.assertFalse((Path(d)/'shadow.json').exists())

    def test_no_secret_or_decisions_in_stdout(self):
        snap,syms,a,sec,n,observed=fixtures()
        m=self.render(snap,syms,a,sec,n,observed)
        self.assertFalse(m['may_modify_al'])
        self.assertFalse(any('decision' in r for r in m['records']))
        self.assertNotIn('synthetic-secret',json.dumps(m))

if __name__=='__main__':
    import unittest
    unittest.main()
