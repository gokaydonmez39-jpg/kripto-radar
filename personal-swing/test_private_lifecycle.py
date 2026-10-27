"""Offline XNAS lifecycle regression. Synthetic only: no vendor, secrets, orders."""
import copy
import unittest

import private_lifecycle as life
from private_sheet_writer import CANDIDATE_HEADER, HandoffBlocked


def row(day, ref, stop, target, held, *,symbol='AAA'):
    return [day+'|'+symbol,day,symbol,'TEKNİK AL ADAYI',
            str(ref),str(stop),str(target),'AÇIK • %d/15 SEANS'%held,
            '','','','PRESERVE_NOTIFICATION','PRESERVE_NOTE']


def sheet():
    return [list(CANDIDATE_HEADER),
            row('2026-10-22',100.,95.,110.,1),
            row('2026-10-23',102.,97.,112.,0)]


def bar(day='2026-10-26', *,o=101.,h=113.,l=96.,c=106.,v=1000.):
    return {'timestamp':day+'T04:00:00+00:00',
            'open':o,'high':h,'low':l,'close':c,'volume':v}


def fetch(symbols,asof):
    assert symbols==['AAA'] and asof=='2026-10-26'
    return {'AAA':[bar()]}


class FakeApi:
    def __init__(self):
        self.rows=sheet()
        self.sheet_ids={'candidate':432}
        self.writes=0
        self.corrupt=False

    def check_metadata(self):return True

    def read(self,title,last_column):
        assert title=='ADAY_GECMISI' and last_column=='M'
        return copy.deepcopy(self.rows)

    def request(self,path,*,method='GET',body=None):
        assert path==':batchUpdate' and method=='POST'
        self.writes+=1
        for command in body['requests']:
            obj=command['updateCells']
            assert obj['start']['sheetId']==432
            index=obj['start']['rowIndex']
            assert obj['start']['columnIndex']==7
            cells=[v['userEnteredValue']['stringValue']
                   for v in obj['rows'][0]['values']]
            self.rows[index][7:11]=cells
        if self.corrupt:
            self.rows[1][5]='BAD_ORIGINAL_STOP'
        return {}


class LifecycleTruthTests(unittest.TestCase):
    def test_same_symbol_multiple_episodes_distinct_outcomes(self):
        plan=life.build_updates(sheet(),'2026-10-26',fetch)
        self.assertEqual((plan['evaluated'],plan['closed']),(2,1))
        self.assertEqual(plan['updates'][0]['new_cells'][0],'AÇIK • 2/15 SEANS')
        self.assertIn('BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS',
                      plan['updates'][1]['new_cells'][0])
        self.assertEqual(plan['updates'][0]['id'],'2026-10-22|AAA')
        self.assertEqual(plan['updates'][1]['id'],'2026-10-23|AAA')

    def test_readback_and_idempotent_repeat(self):
        api=FakeApi()
        result=life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(result['status'],'LIFECYCLE_READBACK_PASS')
        self.assertEqual(result['terminal_updates'],1)
        self.assertFalse(result['device_ack'])
        self.assertEqual(api.writes,1)
        after=copy.deepcopy(api.rows)
        again=life.synchronize(api,'2026-10-26',lambda s,d: (_ for _ in ()).throw(AssertionError('read_not_needed')))
        self.assertEqual(again['evaluated'],0)
        self.assertEqual(api.writes,1)
        self.assertEqual(after,api.rows)

    def test_old_levels_and_alert_status_are_immutable(self):
        api=FakeApi()
        life.synchronize(api,'2026-10-26',fetch)
        for index,original in enumerate(sheet()[1:],start=1):
            self.assertEqual(api.rows[index][:7],original[:7])
            self.assertEqual(api.rows[index][11:],original[11:])

    def test_missing_intermediate_session_blocks_without_write(self):
        rows=[list(CANDIDATE_HEADER),row('2026-10-22',100.,95.,110.,0)]
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_MISSING_INTERMEDIATE_SESSION'):
            life.build_updates(rows,'2026-10-26',
                               lambda symbols,day:{'AAA':[bar()]})

    def test_missing_asof_bar_blocks_even_when_older_prefix_exists(self):
        rows=[list(CANDIDATE_HEADER),row('2026-10-22',100.,95.,110.,0)]
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_ASOF_BAR_MISSING'):
            life.build_updates(rows,'2026-10-26',
                lambda symbols,day:{'AAA':[bar('2026-10-23',h=104,l=99)]})

    def test_duplicate_iex_bar_blocks(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_FOLLOWUP_BAR'):
            life.build_updates(sheet(),'2026-10-26',
                               lambda s,d:{'AAA':[bar(),bar()]})

    def test_corrupted_old_price_not_advanced(self):
        rows=sheet()
        rows[1][6]='2000'
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_NON_2R'):
            life.build_updates(rows,'2026-10-26',fetch)

    def test_two_episode_ids_cannot_be_collapsed(self):
        rows=sheet()
        rows[2][0]=rows[1][0]
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_DUPLICATE_ID'):
            life.build_updates(rows,'2026-10-26',fetch)

    def test_no_future_or_non_session_asof(self):
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_ASOF_NOT_SESSION'):
            life.build_updates(sheet(),'2026-10-25',fetch)
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_FUTURE_OR_UNVERIFIED_COUNT'):
            life.decode_open_episodes(sheet(),'2026-10-22')

    def test_bad_ohlcv_fails_before_any_partial_write(self):
        api=FakeApi()
        with self.assertRaises(ValueError):
            life.synchronize(api,'2026-10-26',
                lambda s,d:{'AAA':[bar(l=-1.)]})
        self.assertEqual(api.writes,0)

    def test_missing_provider_response_fails_closed(self):
        api=FakeApi()
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_MISSING_SYMBOL_BARS'):
            life.synchronize(api,'2026-10-26',lambda s,d:{})
        self.assertEqual(api.writes,0)

    def test_corrupted_readback_original_is_rejected(self):
        api=FakeApi()
        api.corrupt=True
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_READBACK_ORIGINAL_MODIFIED'):
            life.synchronize(api,'2026-10-26',fetch)

    def test_fifteenth_session_expires_at_close(self):
        from exchange_calendars import get_calendar
        cal=get_calendar('XNAS')
        start='2026-10-22'
        day=cal.session_offset(cal.date_to_session(start),15).date().isoformat()
        rows=[list(CANDIDATE_HEADER),row(start,100.,95.,110.,14)]
        result=life.build_updates(rows,day,
                lambda s,d:{'AAA':[bar(day,h=104.,l=98.,c=102.)]})
        self.assertEqual(result['closed'],1)
        self.assertIn('TIME_EXIT_AT_CLOSE',result['updates'][0]['new_cells'][0])
        self.assertIn('15/15',result['updates'][0]['new_cells'][0])

    def test_both_touched_is_not_an_executable_fill(self):
        p=life.build_updates(sheet(),'2026-10-26',fetch)
        self.assertNotIn('FILLED',str(p))
        self.assertTrue(p['updates'][1]['terminal'])


if __name__=='__main__':
    unittest.main()
