"""Offline regressions for private AL PENDING outbox; no Google or broker calls."""
import copy
import unittest
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import alert_ledger_contract as lc
import alert_outbox_producer as out
import private_sheet_writer as writer
from test_private_sheet_writer import RUN, snapshot


class Fake:
    def __init__(self, snap=None):
        self.snap = snap if snap is not None else snapshot()
        initial = writer.plan(self.snap, [list(writer.CANDIDATE_HEADER)],
                              [list(writer.SCAN_HEADER)], RUN)
        self.candidates = [list(writer.CANDIDATE_HEADER)] + initial['candidate_rows']
        self.scans = [list(writer.SCAN_HEADER)] + initial['scan_rows']
        self.alerts = [list(lc.EVENT_HEADER)]
        self.append_calls = 0
        self.discard_append = False
        self.drift_before_write = False
        self._read_alerts = 0

    def check_metadata(self):
        return True

    def read(self, title, column):
        if title == 'ADAY_GECMISI':
            return copy.deepcopy(self.candidates)
        if title == 'TARAMA_KAYITLARI':
            return copy.deepcopy(self.scans)
        if title == 'UYARI_OLAYLARI':
            self._read_alerts += 1
            if self.drift_before_write and self._read_alerts == 2:
                x = copy.deepcopy(self.alerts[0])
                x[0] = 'unexpected'
                self.alerts[0] = x
            return copy.deepcopy(self.alerts)
        raise AssertionError(title)

    def append_pending(self, rows):
        self.append_calls += 1 if rows else 0
        if not self.discard_append:
            self.alerts.extend(copy.deepcopy(rows))


class ALPendingOutboxSourceIsolation(unittest.TestCase):
    def test_valid_natural_eod_retains_pending_outbox_readback(self):
        good={
            'GITHUB_EVENT_NAME':'schedule','GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':writer.EXPECTED_EOD_REPOSITORY,
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_WORKFLOW_REF':writer.EXPECTED_EOD_WORKFLOW_REF,
            'GITHUB_SHA':'a'*40,
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }
        api=Fake()
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'synthetic.json'
            file.write_text(json.dumps(api.snap),encoding='utf-8')
            with patch.dict(os.environ,good,clear=True):
                with patch.object(out,'AlertApi',return_value=api) as provider:
                    with contextlib.redirect_stdout(io.StringIO()) as buf:
                        rc=out.main(['--snapshot',str(file)])
        result=json.loads(buf.getvalue())
        self.assertEqual(rc,0,result)
        self.assertEqual(result['status'],'AL_OUTBOX_PENDING_READBACK_PASS')
        self.assertEqual(result['messages_sent'],0)
        self.assertEqual(result['new_pending'],2)
        self.assertEqual(api.append_calls,1)
        provider.assert_called_once()

    def test_noncanonical_scheduled_producer_never_opens_outbox_sheet(self):
        good={
            'GITHUB_EVENT_NAME':'schedule','GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':writer.EXPECTED_EOD_REPOSITORY,
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_WORKFLOW_REF':writer.EXPECTED_EOD_WORKFLOW_REF,
            'GITHUB_SHA':'a'*40,
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }
        for key,bad in (('GITHUB_EVENT_NAME','push'),
                        ('GITHUB_EVENT_NAME','workflow_dispatch'),
                        ('GITHUB_WORKFLOW_REF','other/workflow@refs/heads/main'),
                        ('GITHUB_REPOSITORY','not-personal477/repo'),
                        ('GITHUB_REF','refs/heads/not-main'),
                        ('GITHUB_RUN_ATTEMPT','2')):
            with self.subTest(key=key,value=bad):
                env=dict(good);env[key]=bad
                with tempfile.TemporaryDirectory() as folder:
                    file=Path(folder)/'synthetic.json'
                    file.write_text(json.dumps(snapshot()))
                    with patch.dict(os.environ,env,clear=True):
                        with patch.object(out,'AlertApi',
                          side_effect=AssertionError('OUTBOX_PROVIDER_STARTED')
                        ) as provider,contextlib.redirect_stdout(io.StringIO()) as buf:
                            rc=out.main(['--snapshot',str(file)])
                result=json.loads(buf.getvalue())
                self.assertEqual(rc,3)
                self.assertEqual(result['reason_type'],'HandoffBlocked')
                provider.assert_not_called()

class ALPendingOutboxTests(unittest.TestCase):
    def test_new_al_is_pending_and_replay_is_noop(self):
        a = Fake()
        result = out.synchronize(a.snap, RUN, a)
        self.assertEqual(result['status'], 'AL_OUTBOX_PENDING_READBACK_PASS')
        self.assertEqual(result['technical_al'], 2)
        self.assertEqual(result['new_pending'], 2)
        self.assertEqual(result['messages_sent'], 0)
        self.assertEqual(a.append_calls, 1)
        self.assertEqual(len(a.alerts), 3)
        self.assertTrue(all(r[17] == lc.CONFIRMED_PENDING
                            for r in a.alerts[1:]))
        self.assertTrue(all(len(r) == len(lc.EVENT_HEADER)
                            for r in a.alerts[1:]))
        again = out.synchronize(a.snap, RUN, a)
        self.assertEqual(again['new_pending'], 0)
        self.assertEqual(again['new_suppressed'], 0)
        self.assertEqual(a.append_calls, 1)
        self.assertEqual(len(a.alerts), 3)

    def test_prior_open_episode_suppresses_only_repeat(self):
        a = Fake()
        sym = next(r['symbol'] for r in a.snap['rows']
                   if r['decision'] == 'AL')
        old = ['2026-10-23|' + sym, '2026-10-23', sym, 'TEKNİK AL ADAYI',
               '50', '45', '60', 'AÇIK • 0/15 SEANS']
        a.candidates.insert(1, old)
        result = out.synchronize(a.snap, RUN, a)
        self.assertEqual(result['new_suppressed'], 1)
        self.assertEqual(result['new_pending'], 1)
        matched = [r for r in a.alerts if len(r) > 3 and r[3] == sym]
        self.assertEqual(matched[0][17], lc.SUPPRESSED)
        self.assertEqual(result['messages_sent'], 0)

    def test_session_boundary_same_day_close_preserves_suppression(self):
        a = Fake()
        sym = next(r['symbol'] for r in a.snap['rows'] if r['decision'] == 'AL')
        day = a.snap['asof_et']
        old = ['2026-10-20|' + sym, '2026-10-20', sym, 'TEKNİK AL ADAYI',
               '50', '45', '60', 'AÇIK • 3/15 SEANS', '', '', '']
        a.candidates.insert(1, old)
        self.assertEqual(out.synchronize(a.snap, RUN, a)['new_suppressed'], 1)
        frozen = copy.deepcopy(a.alerts)
        old[7:11] = ['KAPALI • TIME_EXIT_AT_CLOSE • 15/15 SEANS',
                     day, 'TIME_EXIT_AT_CLOSE', '0']
        result = out.synchronize(a.snap, RUN, a)
        self.assertEqual(result['new_suppressed'], 0)
        self.assertEqual(a.alerts, frozen)
        self.assertEqual(a.append_calls, 1)

    def test_previous_session_close_not_suppressed_and_malformed_blocks(self):
        a = Fake()
        sym = next(r['symbol'] for r in a.snap['rows'] if r['decision'] == 'AL')
        old = ['2026-10-20|' + sym, '2026-10-20', sym, 'TEKNİK AL ADAYI',
               '50', '45', '60', 'KAPALI • STOP_TOUCHED • 3/15 SEANS',
               '2026-10-23', 'STOP_TOUCHED', '-10']
        a.candidates.insert(1, old)
        self.assertEqual(out.synchronize(a.snap, RUN, a)['new_pending'], 2)
        for bad in ('', '2026-10-27', '20261023'):
            b = Fake()
            row = copy.deepcopy(old)
            row[8] = bad
            b.candidates.insert(1, row)
            with self.assertRaisesRegex(lc.LedgerRefused,
                                        'PRIOR_EPISODE_BOUNDARY_UNPROVEN'):
                out.synchronize(b.snap, RUN, b)
            self.assertEqual(b.append_calls, 0)

    def test_overdue_prior_episode_blocks_before_any_new_event(self):
        a=Fake()
        sym=next(r['symbol'] for r in a.snap['rows'] if r['decision']=='AL')
        a.candidates.insert(1,['2026-10-22|'+sym,'2026-10-22',sym,
            'TEKNİK AL ADAYI','100','95','110','AÇIK • 0/15 SEANS','','',''])
        with self.assertRaisesRegex(out.OutboxBlocked,'PRIOR_EPISODE_HISTORY_NOT_CURRENT'):
            out.synchronize(a.snap,RUN,a)
        self.assertEqual(a.append_calls,0)
        self.assertEqual(len(a.alerts),1)

    def test_existing_requested_event_never_replayed(self):
        a = Fake()
        first = out.synchronize(a.snap, RUN, a)
        a.alerts[1][17] = lc.REQUESTED
        a.alerts[1][18] = '2026-11-03 12:17 TRT'
        second = out.synchronize(a.snap, RUN, a)
        self.assertEqual(first['new_pending'], 2)
        self.assertEqual(second['new_pending'], 0)
        self.assertEqual(a.append_calls, 1)
        self.assertEqual(a.alerts[1][17], lc.REQUESTED)

    def test_missing_upstream_scan_or_candidate_blocks(self):
        a = Fake()
        a.candidates = [list(writer.CANDIDATE_HEADER)]
        with self.assertRaisesRegex(out.OutboxBlocked,
                                    'UPSTREAM_PRIVATE_SHEET_READBACK_REQUIRED'):
            out.synchronize(a.snap, RUN, a)
        self.assertEqual(a.append_calls, 0)

    def test_corrupted_candidate_price_fails_before_write(self):
        a = Fake()
        a.candidates[1][5] = '0.01'
        with self.assertRaises(writer.HandoffBlocked):
            out.synchronize(a.snap, RUN, a)
        self.assertEqual(a.append_calls, 0)

    def test_header_and_duplicate_event_fail_closed(self):
        a = Fake()
        a.alerts[0][0] = 'BAD HEADER'
        with self.assertRaisesRegex(lc.LedgerRefused, 'SHEET_HEADER_DRIFT'):
            out.synchronize(a.snap, RUN, a)
        a = Fake()
        out.synchronize(a.snap, RUN, a)
        a.alerts.append(copy.deepcopy(a.alerts[1]))
        with self.assertRaisesRegex(lc.LedgerRefused, 'DUPLICATE_EVENT_KEY'):
            out.synchronize(a.snap, RUN, a)

    def test_concurrent_write_blocks_without_append(self):
        a = Fake()
        a.drift_before_write = True
        with self.assertRaisesRegex(out.OutboxBlocked,
                                    'OUTBOX_CONCURRENT_PRIVATE_EDIT_BLOCKED'):
            out.synchronize(a.snap, RUN, a)
        self.assertEqual(a.append_calls, 0)

    def test_lost_readback_blocks_claim_of_success(self):
        a = Fake()
        a.discard_append = True
        with self.assertRaisesRegex(out.OutboxBlocked,
                                    'OUTBOX_READBACK_COUNT_OR_CONCURRENT_DRIFT'):
            out.synchronize(a.snap, RUN, a)

    def test_existing_wrong_suppression_requires_review(self):
        a = Fake()
        out.synchronize(a.snap, RUN, a)
        a.alerts[1][17] = lc.SUPPRESSED
        with self.assertRaisesRegex(out.OutboxBlocked,
                                    'EXISTING_EVENT_STATUS_CONFLICT'):
            out.synchronize(a.snap, RUN, a)

    def test_wrong_immutable_event_level_rejected(self):
        a = Fake()
        out.synchronize(a.snap, RUN, a)
        a.alerts[1][8] = '0.01'
        with self.assertRaisesRegex(out.OutboxBlocked,
                                    'EXISTING_EVENT_IMMUTABLE_LEVEL_OR_ID_DRIFT'):
            out.synchronize(a.snap, RUN, a)

    def test_unknown_future_technical_candidate_cannot_use_made_up_data(self):
        a = Fake()
        a.snap['valid_data_symbols'] = 476
        with self.assertRaises(Exception):
            out.synchronize(a.snap, RUN, a)
        self.assertEqual(a.append_calls, 0)


if __name__ == '__main__':
    unittest.main()
