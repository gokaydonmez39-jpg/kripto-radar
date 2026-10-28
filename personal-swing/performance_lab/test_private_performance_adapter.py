"""Synthetic private bridge tests. No network, real tickers, secrets or Sheets."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import private_performance_adapter as a

DAY1='2026-10-22'
DAY2='2026-10-23'
DAY3='2026-10-26'
SRC='a'*64
POL='b'*64
UNIVERSE=['FAKE']+['X%04d'%i for i in range(476)]


def bar(date, op=100, high=103, low=98, close=101, vol=40000):
    return {'timestamp':date+'T04:00:00+00:00',
            'open':op,'high':high,'low':low,'close':close,'volume':vol}


def scans(*, no_issuance=False, invalid_current=False, duplicate=False):
    good=f'scopeSHA={SRC};algorithmSHA={POL};NO_ORDERS'
    base=[*a.SCAN_HEADER]
    first=[DAY1,'fake','477','477','477','0','TRUE','1','private','manual unproven' if no_issuance else good]
    last=[DAY3,'fake','477','477','476' if invalid_current else '477','0','TRUE','1','private',good]
    rows=[base,first,last]
    if duplicate:rows.append(list(last))
    return rows


def sheet(*, mode='open'):
    if mode=='open':
        status='AÇIK • 2/15 SEANS'
        ended=['','','']
    elif mode=='win':
        status='KAPALI • TARGET_TOUCHED • 1/15 SEANS'
        ended=[DAY2,'TARGET_TOUCHED','10']
    elif mode=='fakewin':
        status='KAPALI • TARGET_TOUCHED • 1/15 SEANS'
        ended=[DAY2,'TARGET_TOUCHED','20']
    else:
        raise ValueError(mode)
    return [[*a.CANDIDATE_HEADER],
            [DAY1+'|FAKE',DAY1,'FAKE','TEKNİK AL ADAYI',
             '100','95','110',status,*ended,'KAYDEDİLDİ_BİLDİRİM_AYRI','fake private']]


def fetch_open(symbols, asof):
    if symbols != ['FAKE'] or asof != DAY3:
        raise AssertionError('unexpected provider request')
    return {'FAKE':[bar(DAY1,100,101,99,100),bar(DAY2),bar(DAY3)]}


def fetch_win(symbols, asof):
    r=fetch_open(symbols,asof)
    r['FAKE'][1]=bar(DAY2,100,112,99,111)
    return r


def plan(rows=None, histories=None, **kwargs):
    return a.source_plan(rows if rows is not None else sheet(),
                         histories if histories is not None else scans(),
                         DAY3,UNIVERSE,SRC,POL)


class PrivateBridge(unittest.TestCase):
    def test_zero_missing_symbol_is_valid_nonnegative_scan_count(self):
        self.assertEqual(a._count('0'), Decimal(0))
        self.assertEqual(a._count('477'), Decimal(477))
        self.assertEqual(len(plan()['verified']), 1)
        with self.assertRaisesRegex(a.EvidenceBlocked, 'SCAN_COUNT_NONINTEGER'):
            a._count('1.5')

    def test_signed_stop_loss_matches_unmodified_tracker(self):
        rows = sheet()
        rows[1][7] = 'KAPALI • STOP_TOUCHED • 1/15 SEANS'
        rows[1][8:11] = [DAY2, 'STOP_TOUCHED', '-5']
        def stop_data(symbols, asof):
            data = fetch_open(symbols,asof)
            data['FAKE'][1] = bar(DAY2,100,102,94,98)
            return data
        result = a.audit_plan(plan(rows),stop_data)
        self.assertEqual(result['n_complete'], 1)
        self.assertFalse(result['rule_change'])
        self.assertFalse(result['real_fill_proven'])

    def test_valid_two_day_open_is_censored_not_winner(self):
        x=a.audit_plan(plan(),fetch_open)
        self.assertEqual((x['verified_episodes'],x['n_complete'],x['n_censored']),
                         (1,0,1))
        self.assertFalse(x['rule_change'])
        self.assertFalse(x['notification_delivery'])
        self.assertFalse(x['real_fill_proven'])

    def test_completed_terminal_is_confirmed_against_legacy(self):
        x=a.audit_plan(plan(sheet(mode='win')),fetch_win)
        self.assertEqual(x['n_complete'],1)
        self.assertEqual(x['verified_episodes'],1)
        self.assertFalse(x['benchmark_proven'])
        self.assertNotEqual(x['status'],'PASS')

    def test_fabricated_private_terminal_pnl_blocks(self):
        with self.assertRaisesRegex(a.EvidenceBlocked,'TERMINAL_OUTCOME_DRIFT'):
            a.audit_plan(plan(sheet(mode='fakewin')),fetch_win)

    def test_lifecycle_stale_open_count_blocks(self):
        rows=sheet()
        rows[1][7]='AÇIK • 1/15 SEANS'
        with self.assertRaisesRegex(a.EvidenceBlocked,'DAY_COUNT_STALE'):
            a.audit_plan(plan(rows),fetch_open)

    def test_missing_original_iex_close_blocks(self):
        def missing(s,d):
            r=fetch_open(s,d)
            r['FAKE']=r['FAKE'][1:]
            return r
        with self.assertRaisesRegex(a.EvidenceBlocked,'MISSING_ORIGINAL'):
            a.audit_plan(plan(),missing)

    def test_original_close_changed_by_provider_blocks(self):
        def changed(s,d):
            r=fetch_open(s,d)
            r['FAKE'][0]['close']=101.0
            return r
        with self.assertRaisesRegex(a.EvidenceBlocked,'ORIGINAL_IEX_CLOSE_MISMATCH'):
            a.audit_plan(plan(),changed)

    def test_missing_daily_session_blocks(self):
        def missing(s,d):
            r=fetch_open(s,d)
            r['FAKE']=r['FAKE'][:2]
            return r
        with self.assertRaisesRegex(a.EvidenceBlocked,'MISSING_DUE_FOLLOWUP_BAR'):
            a.audit_plan(plan(),missing)

    def test_extra_unrequested_provider_symbol_blocks(self):
        def wrong(s,d):
            r=fetch_open(s,d)
            r['GOOG']=r['FAKE']
            return r
        with self.assertRaisesRegex(a.EvidenceBlocked,'UNEXPECTED_PROVIDER'):
            a.audit_plan(plan(),wrong)

    def test_unproven_old_manual_issue_excluded_not_fabricated(self):
        p=plan(histories=scans(no_issuance=True))
        self.assertEqual(p['excluded_unproven_issuance'],1)
        def forbid(*args):
            raise AssertionError('MUST_NOT_FETCH_UNPROVEN_ISSUANCE')
        output=a.audit_plan(p,forbid)
        self.assertEqual(output['status'],'HOLD_NO_PROVEN_ISSUANCE')
        self.assertEqual(output['verified_episodes'],0)

    def test_any_excluded_manual_epoch_makes_cohort_hold(self):
        rows=sheet()
        more=list(rows[1])
        more[0]=DAY3+'|FAKE'
        more[1]=DAY3
        more[7]='AÇIK • 0/15 SEANS'
        rows.append(more)
        p=plan(rows,histories=scans(no_issuance=True))
        self.assertEqual(p['excluded_unproven_issuance'],1)
        self.assertEqual(len(p['verified']),1)

    def test_current_day_requires_477_and_sha(self):
        with self.assertRaisesRegex(a.EvidenceBlocked,'CURRENT_SCAN_NOT_477_COMPLETE'):
            plan(histories=scans(invalid_current=True))
        ss=scans()
        ss[-1][9]='source changed'
        with self.assertRaisesRegex(a.EvidenceBlocked,'CURRENT_SCAN_SCOPE_OR_POLICY_MISMATCH'):
            plan(histories=ss)

    def test_duplicate_scan_or_episode_fail_closed(self):
        with self.assertRaisesRegex(a.EvidenceBlocked,'DUPLICATE_SCAN_DAY'):
            plan(histories=scans(duplicate=True))
        rr=sheet()
        rr.append(list(rr[1]))
        with self.assertRaisesRegex(a.EvidenceBlocked,'DUPLICATE_OR_NONSTRING_EPISODE'):
            plan(rows=rr)

    def test_new_stock_outside_477_is_rejected(self):
        rr=sheet()
        rr[1][2]='OTHER'
        rr[1][0]=DAY1+'|OTHER'
        with self.assertRaisesRegex(a.EvidenceBlocked,'CANDIDATE_IDENTITY_MISMATCH'):
            plan(rows=rr)

    def test_historical_stop_rewrite_is_rejected(self):
        rr=sheet()
        rr[1][5]='94'
        with self.assertRaisesRegex(a.EvidenceBlocked,'CANDIDATE_STOP_TARGET_DRIFT'):
            plan(rows=rr)

    def test_closed_numeric_loss_uses_negative_not_absolute(self):
        rr=sheet(mode='win')
        rr[1][10]='-10'
        with self.assertRaisesRegex(a.EvidenceBlocked,'TERMINAL_OUTCOME_DRIFT'):
            a.audit_plan(plan(rr),fetch_win)

    def test_sentinel_metadata_cannot_request_other_private_tab(self):
        obj=a.PrivateSheetReadOnly.__new__(a.PrivateSheetReadOnly)
        with self.assertRaisesRegex(a.EvidenceBlocked,'READ_ONLY_SHEET_WHITELIST'):
            obj.read('UYARI_OLAYLARI','T')

    def test_credential_scope_is_declared_readonly(self):
        import inspect
        src=inspect.getsource(a.PrivateSheetReadOnly.__init__)
        self.assertIn('spreadsheets.readonly',src)
        self.assertNotIn('scope=\'https://www.googleapis.com/auth/spreadsheets\'',src)

    def test_local_public_result_is_only_aggregate(self):
        result=a.audit_plan(plan(),fetch_open)
        public=json.dumps({'state':result['status'],'verified':result['verified_episodes'],
                           'finished':result['n_complete']})
        self.assertNotIn('FAKE',public)
        self.assertNotIn('100',public)
        self.assertNotIn(DAY1,public)

    def test_optimization_does_not_disable_explicit_gates(self):
        rr=sheet()
        rr[1][6]='1000'
        with self.assertRaises(a.EvidenceBlocked):
            plan(rows=rr)


if __name__=='__main__':
    unittest.main()
