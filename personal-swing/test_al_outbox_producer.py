"""Offline regressions for private AL PENDING outbox; no Google or broker calls."""
import copy
import unittest

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
               '50', '45', '60', 'AÇIK • 2/15 SEANS']
        a.candidates.insert(1, old)
        result = out.synchronize(a.snap, RUN, a)
        self.assertEqual(result['new_suppressed'], 1)
        self.assertEqual(result['new_pending'], 1)
        matched = [r for r in a.alerts if len(r) > 3 and r[3] == sym]
        self.assertEqual(matched[0][17], lc.SUPPRESSED)
        self.assertEqual(result['messages_sent'], 0)

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
