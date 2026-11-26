"""Offline XNAS lifecycle regression. Synthetic only: no vendor, secrets, orders."""
import copy
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import private_lifecycle as life
import runner
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER, HandoffBlocked


SOURCE_RUN='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/123456'
SOURCE_SCOPE=runner.get_scope(watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),asof='2026-10-26')
SOURCE_PROOF='scopeSHA='+runner.sha_symbols(SOURCE_SCOPE)+';algorithmSHA='+runner.analysis_fingerprint()+';source_event=schedule;NO_ORDERS'

def row(day, ref, stop, target, held, *,symbol='AAA'):
    return [day+'|'+symbol,day,symbol,'TEKNİK AL ADAYI',
            str(ref),str(stop),str(target),'AÇIK • %d/15 SEANS'%held,
            '','','','PRESERVE_NOTIFICATION','PRESERVE_NOTE']


def sheet():
    return [list(CANDIDATE_HEADER),
            row('2026-10-22',100.,90.,120.,1),
            row('2026-10-23',102.,97.,112.,0)]


def bar(day='2026-10-26', *,o=101.,h=113.,l=96.,c=106.,v=1000.):
    return {'timestamp':day+'T04:00:00+00:00',
            'open':o,'high':h,'low':l,'close':c,'volume':v}


def fetch(symbols,asof):
    assert symbols==['AAA'] and asof=='2026-10-26'
    return {'AAA':[bar()]}


class LifeCycleNaturalWriterSourceAcceptance(unittest.TestCase):
    def source_env(self):
        import private_sheet_writer as writer
        return {
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':writer.EXPECTED_EOD_REPOSITORY,
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_SHA':'a'*40,
            'GITHUB_WORKFLOW_REF':writer.EXPECTED_EOD_WORKFLOW_REF,
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }

    def test_noncanonical_runner_cannot_evaluate_or_mutate_lifecycle(self):
        for key,bad in (
            ('GITHUB_EVENT_NAME','workflow_dispatch'),
            ('GITHUB_EVENT_NAME','push'),
            ('GITHUB_REPOSITORY','other/repo'),
            ('GITHUB_REF','refs/heads/not-main'),
            ('GITHUB_WORKFLOW_REF','other/schedule.yml@refs/heads/main'),
            ('GITHUB_SHA','X'*40),
            ('GITHUB_RUN_ATTEMPT','2'),
            ('GITHUB_RUN_ID','00077'),
        ):
            with self.subTest(key=key,bad=bad):
                env=self.source_env();env[key]=bad
                with patch.dict(os.environ,env,clear=True):
                    with patch.object(life.daily_job,'current_completed_session',
                          return_value='2026-11-23') as calendar:
                        with patch.object(life,'SheetApi',
                          side_effect=AssertionError('PRIVATE_PROVIDER_STARTED')
                        ) as provider,contextlib.redirect_stdout(io.StringIO()) as captured:
                            rc=life.main([])
                result=json.loads(captured.getvalue())
                self.assertEqual(rc,3)
                self.assertEqual(result['status'],'LIFECYCLE_BLOCKED')
                self.assertEqual(result['reason_type'],'HandoffBlocked')
                calendar.assert_not_called()
                provider.assert_not_called()

    def test_valid_natural_session_reaches_offline_lifecycle_contract(self):
        with patch.dict(os.environ,self.source_env(),clear=True):
            with patch.object(life.daily_job,'current_completed_session',
                              return_value='2026-11-23') as clock:
                with patch.object(life,'SheetApi',return_value=object()) as provider:
                    with patch.object(life,'synchronize',
                        return_value={
                            'status':'LIFECYCLE_READBACK_PASS',
                            'asof_et':'2026-11-23','device_ack':False,
                            'notification_delivery':'NOT_ATTEMPTED_BY_GITHUB',
                            'terminal_updates':0,
                        }) as operation,contextlib.redirect_stdout(io.StringIO()) as captured:
                            rc=life.main([])
        result=json.loads(captured.getvalue())
        self.assertEqual(rc,0,result)
        self.assertEqual(result['status'],'LIFECYCLE_READBACK_PASS')
        self.assertFalse(result['device_ack'])
        clock.assert_called_once()
        provider.assert_called_once()
        operation.assert_called_once()

    def test_pre_al_expired_or_wrong_session_blocks_before_sheet(self):
        for eligible in (None,'2026-11-25'):
            with self.subTest(eligible=eligible),patch.dict(os.environ,self.source_env(),clear=True):
                with patch.object(life.daily_job,'current_completed_session',return_value=eligible):
                    with patch.object(life,'SheetApi',side_effect=AssertionError('NO_SHEET')) as api:
                        with contextlib.redirect_stdout(io.StringIO()) as captured:
                            rc=life.main(['--asof','2026-11-23','--before-al-reservation'])
            self.assertEqual(rc,3)
            self.assertEqual(json.loads(captured.getvalue())['reason_code'],
                             'LIFECYCLE_PRE_AL_CURRENT_SESSION_REQUIRED')
            api.assert_not_called()

    def test_legitimate_natural_no_session_preserves_noop_without_sheet(self):
        with patch.dict(os.environ,self.source_env(),clear=True):
            with patch.object(life.daily_job,'current_completed_session',
                              return_value=None) as calendar:
                with patch.object(life,'SheetApi',
                     side_effect=AssertionError('SHOULD_NOT_OPEN_PROVIDER')
                ) as provider,contextlib.redirect_stdout(io.StringIO()) as captured:
                    rc=life.main([])
        result=json.loads(captured.getvalue())
        self.assertEqual(rc,0,result)
        self.assertEqual(result['status'],'LIFECYCLE_NO_COMPLETED_SESSION')
        self.assertFalse(result['market_data_called'])
        calendar.assert_called_once()
        provider.assert_not_called()

class FakeApi:
    def __init__(self):
        self.rows=sheet()
        self.sheet_ids={'candidate':432,'alerts':433}
        self.alert_rows=[list(life.ALERT_HEADER)]
        self.scans=[list(SCAN_HEADER),
                    ['2026-10-26','GitHub schedule VERIFIED IEX EOD',
                     '477','477','477','0','TRUE','0',SOURCE_RUN,SOURCE_PROOF]]
        self.writes=0
        self.corrupt=False

    def check_metadata(self):return True

    def read(self,title,last_column):
        if title=='ADAY_GECMISI' and last_column=='M':
            return copy.deepcopy(self.rows)
        if title=='UYARI_OLAYLARI' and last_column=='T':
            return copy.deepcopy(self.alert_rows)
        if title=='TARAMA_KAYITLARI' and last_column=='J':
            return copy.deepcopy(self.scans)
        raise AssertionError('unknown private table')

    def request(self,path,*,method='GET',body=None):
        assert path==':batchUpdate' and method=='POST'
        self.writes+=1
        for command in body['requests']:
            if 'appendCells' in command:
                obj=command['appendCells']
                assert obj['sheetId']==433
                for item in obj['rows']:
                    self.alert_rows.append([
                        v['userEnteredValue']['stringValue']
                        for v in item['values']])
                continue
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
    def test_pre_al_catchup_noop_and_exact_run_fence(self):
        api=FakeApi()
        with patch.object(life,'build_updates',side_effect=AssertionError('NO_VENDOR_OR_PLAN')):
            result=life.synchronize(api,'2026-10-26',fetch,before_al_run_url=SOURCE_RUN)
        self.assertEqual(result['status'],'LIFECYCLE_PRE_AL_CURRENT_HISTORY_NOOP')
        self.assertEqual(api.writes,0)
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_PRE_AL_EXACT_RUN_REQUIRED'):
            life.synchronize(api,'2026-10-26',fetch,before_al_run_url=SOURCE_RUN+'9')
        self.assertEqual(api.writes,0)

    def test_pre_al_catchup_missed_friday_and_repeat(self):
        api=FakeApi()
        api.rows=[list(CANDIDATE_HEADER),row('2026-10-22',100.,95.,110.,0)]
        before=copy.deepcopy(api.rows)
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_MISSING_INTERMEDIATE_SESSION'):
            life.synchronize(api,'2026-10-26',fetch,before_al_run_url=SOURCE_RUN)
        self.assertEqual(api.rows,before)
        self.assertEqual(api.writes,0)
        def read(syms,day):
            self.assertEqual((syms,day),(['AAA'],'2026-10-26'))
            return {'AAA':[bar('2026-10-23',o=100,h=104,l=94,c=100)]}
        result=life.synchronize(api,'2026-10-26',read,before_al_run_url=SOURCE_RUN)
        self.assertEqual(result['terminal_updates'],1)
        self.assertEqual(api.rows[1][8],'2026-10-23')
        self.assertEqual(api.rows[1][:7],before[1][:7])
        self.assertEqual(api.writes,1)
        again=life.synchronize(api,'2026-10-26',
            lambda *args: self.fail('NO_REPEAT_VENDOR_CALL'),before_al_run_url=SOURCE_RUN)
        self.assertEqual(again['status'],'LIFECYCLE_PRE_AL_CURRENT_HISTORY_NOOP')
        self.assertEqual(api.writes,1)

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
        self.assertEqual(result['terminal_events_reserved'],1)
        self.assertEqual(len(api.alert_rows),2)
        self.assertEqual(api.alert_rows[1][17],life.EVENT_PENDING)
        self.assertFalse(result['device_ack'])
        self.assertEqual(api.writes,1)
        after=copy.deepcopy(api.rows)
        again=life.synchronize(api,'2026-10-26',lambda s,d: (_ for _ in ()).throw(AssertionError('read_not_needed')))
        self.assertEqual(again['evaluated'],0)
        self.assertEqual(api.writes,1)
        self.assertEqual(after,api.rows)
        self.assertEqual(len(api.alert_rows),2)

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
                lambda symbols,day:{'AAA':[bar('2026-10-23',o=101.,h=104.,l=99.,c=102.)]})

    def test_nov19_to_nov23_terminal_event_uses_utc_nov20_without_scan(self):
        # The 20 Nov production EOD is absent. Contiguous IEX daily bars
        # may still resolve an older 19 Nov episode on the next natural EOD.
        rows=[list(CANDIDATE_HEADER),
              row('2026-11-19',100.,95.,110.,0)]
        friday=bar('2026-11-19',o=100.,h=104.,l=94.,c=100.)
        friday['timestamp']='2026-11-19T23:30:00-05:00'
        monday=bar('2026-11-23',o=115.,h=130.,l=112.,c=120.)
        plan=life.build_updates(rows,'2026-11-23',
                lambda syms,asof:{'AAA':[friday,monday]})
        self.assertEqual((plan['evaluated'],plan['closed']),(1,1))
        event=plan['updates'][0]['event']
        self.assertEqual(event['event_day'],'2026-11-20')
        self.assertEqual(event['event_code'],'STOP_TOUCHED')
        self.assertEqual(event['days_held'],1)
        self.assertTrue(plan['updates'][0]['terminal'])

    def test_public_timestamp_failure_is_categorical_not_raw_source(self):
        self.assertEqual(
            life.lifecycle_public_failure_code(
                ValueError('FOLLOWUP_TIMESTAMP_WITHOUT_TZ')),
            'LIFECYCLE_FOLLOWUP_TIMESTAMP_WITHOUT_TZ')
        self.assertEqual(
            life.lifecycle_public_failure_code(
                ValueError('FOLLOWUP_TIMESTAMP_INVALID')),
            'LIFECYCLE_FOLLOWUP_TIMESTAMP_INVALID')

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

    def test_terminal_event_and_closed_episode_are_same_transaction(self):
        api=FakeApi()
        life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(api.writes,1)
        self.assertEqual(api.alert_rows[1][1],'2026-10-23|AAA')
        self.assertEqual(api.alert_rows[1][4],'2026-10-26')
        self.assertEqual(api.alert_rows[1][5],
                         'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS')
        self.assertIn('BOTH_TOUCHED',api.rows[2][7])
        self.assertEqual(api.alert_rows[1][17],
                         'EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        self.assertEqual(api.alert_rows[1][16], SOURCE_RUN)

    def test_terminal_evidence_requires_valid_current_scan_source(self):
        for mutation in ("missing","wrong_asof","broken_scope","wrong_url","not_final"):
            with self.subTest(mutation=mutation):
                api=FakeApi()
                if mutation=="missing":api.scans=[list(SCAN_HEADER)]
                elif mutation=="wrong_asof":api.scans[1][0]="2026-10-23"
                elif mutation=="broken_scope":api.scans[1][9]="scopeSHA=BAD;algorithmSHA=BAD"
                elif mutation=="wrong_url":api.scans[1][8]="https://example.com/not-a-gh-run"
                elif mutation=="not_final":api.scans[1][4]="476"
                with self.assertRaises((HandoffBlocked,ValueError)):
                    life.synchronize(api,'2026-10-26',fetch)
                self.assertEqual(api.writes,0)

    def test_invalid_canonical_eod_never_calls_price_provider(self):
        """P0: verify current scan before fetching any new IEX market bars."""
        for kind in ("missing", "stale", "non_final", "wrong_origin",
                     "broken_scope", "duplicate"):
            with self.subTest(kind=kind):
                api=FakeApi()
                if kind=="missing":
                    api.scans=[list(SCAN_HEADER)]
                elif kind=="stale":
                    api.scans[1][0]="2026-10-23"
                elif kind=="non_final":
                    api.scans[1][4]="476"
                elif kind=="wrong_origin":
                    api.scans[1][1]=life.RUN_EVENT_LABELS["workflow_dispatch"]
                    api.scans[1][9]=api.scans[1][9].replace(
                        "source_event=schedule",
                        "source_event=workflow_dispatch")
                elif kind=="broken_scope":
                    api.scans[1][9]="scopeSHA=BAD;algorithmSHA=BAD"
                elif kind=="duplicate":
                    api.scans.append(copy.deepcopy(api.scans[1]))
                calls=[]
                def observed_provider(symbols,day):
                    calls.append((symbols,day))
                    return fetch(symbols,day)
                with self.assertRaises((HandoffBlocked,ValueError)):
                    life.synchronize(api,"2026-10-26",observed_provider)
                self.assertEqual(calls,[],
                                 "IEX provider touched before source proof")
                self.assertEqual(api.writes,0)

    def test_non_natural_eod_cannot_reserve_terminal_stop_or_target(self):
        # EOD workflow push is offline only; manual dispatch has no
        # certified parent-child/Sheet single-writer fallback authority.
        for source in ('workflow_dispatch','push'):
            with self.subTest(source_event=source):
                api=FakeApi()
                api.scans[1][1]=life.RUN_EVENT_LABELS[source]
                api.scans[1][9]=api.scans[1][9].replace(
                    'source_event=schedule','source_event='+source)
                original=copy.deepcopy(api.rows)
                with self.assertRaisesRegex(
                        HandoffBlocked,'LIFECYCLE_NON_NATURAL_EOD_SOURCE'):
                    life.synchronize(api,'2026-10-26',fetch)
                self.assertEqual(api.writes,0)
                self.assertEqual(api.rows,original)
                self.assertEqual(len(api.alert_rows),1)

    def test_terminal_scan_non_monotonic_history_must_fail_closed(self):
        api=FakeApi()
        api.scans[1:1]=[
            ['2026-10-24'],['2026-10-23']]
        with self.assertRaisesRegex(
                HandoffBlocked,'LIFECYCLE_SCAN_DATE_ORDER_INVALID'):
            life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(api.writes,0)
        self.assertEqual(len(api.alert_rows),1)

    def test_source_scan_cannot_change_between_preflight_and_write(self):
        api=FakeApi()
        original=api.read
        reads=[0]
        def racing_read(title, lastcol):
            values=original(title,lastcol)
            if title=='TARAMA_KAYITLARI':
                reads[0]+=1
                if reads[0]>1:
                    values[1][8]='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/777777'
            return values
        api.read=racing_read
        with self.assertRaises(HandoffBlocked):
            life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(api.writes,0)

    def test_source_scan_header_and_duplicate_asof_refused(self):
        for kind in ('bad_header','duplicate_asof','bad_policy'):
            with self.subTest(kind=kind):
                api=FakeApi()
                if kind=='bad_header':api.scans[0][0]='NOT_ASOF_ET'
                if kind=='duplicate_asof':api.scans.append(copy.deepcopy(api.scans[1]))
                if kind=='bad_policy':
                    api.scans[1][9]=api.scans[1][9].replace(
                        runner.analysis_fingerprint(),'f'*64)
                with self.assertRaises(HandoffBlocked):
                    life.synchronize(api,'2026-10-26',fetch)
                self.assertEqual(api.writes,0)

    def test_source_proof_independent_readback_and_replay_immutability(self):
        api=FakeApi()
        life.synchronize(api,'2026-10-26',fetch)
        original=copy.deepcopy(api.alert_rows[1])
        self.assertEqual(original[16],SOURCE_RUN)
        life.synchronize(api,'2026-10-26',
            lambda s,d: (_ for _ in ()).throw(AssertionError('NO_PROVIDER_REPLAY')))
        self.assertEqual(api.alert_rows[1],original)
        self.assertEqual(api.writes,1)

    def test_suppressed_observation_closes_without_new_terminal_user_alert(self):
        """An AL never notified cannot later create an orphan STOP notification."""
        api=FakeApi()
        old=['']*len(life.ALERT_HEADER)
        old[0]='2026-10-23|AAA|2026-10-23|AL_NEW_EPISODE|1'
        old[1]='2026-10-23|AAA'
        old[2:6]=['2026-10-23','AAA','2026-10-23','AL_NEW_EPISODE']
        old[7:10]=['102','97','112']
        old[17]='DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT'
        api.alert_rows.append(old)
        result=life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(result['terminal_updates'],1)
        self.assertEqual(result['terminal_events_reserved'],0)
        self.assertIn('KAPALI',api.rows[2][7])
        self.assertEqual(len(api.alert_rows),2)
        self.assertEqual(api.alert_rows[1][17],old[17])
    def test_duplicate_terminal_event_key_blocks_before_any_update(self):
        api=FakeApi()
        plan=life.build_updates(api.rows,'2026-10-26',fetch)
        event=plan['updates'][1]['event']
        row=[event['event_key']]+['fake']*19
        api.alert_rows.extend([row,row])
        with self.assertRaisesRegex(HandoffBlocked,
                                    'LIFECYCLE_ALERT_DUPLICATE_OR_INVALID'):
            life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(api.writes,0)

    def test_alarm_header_drift_blocks_before_update(self):
        api=FakeApi()
        api.alert_rows[0][0]='WRONG_EVENT_HEADER'
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_ALERT_HEADER_DRIFT'):
            life.synchronize(api,'2026-10-26',fetch)
        self.assertEqual(api.writes,0)

    def test_terminal_outbox_readback_mutation_is_blocked(self):
        api=FakeApi()
        def corrupted_read(title,last_col):
            if title=='ADAY_GECMISI':
                return copy.deepcopy(api.rows)
            if title=='TARAMA_KAYITLARI':
                return copy.deepcopy(api.scans)
            values=copy.deepcopy(api.alert_rows)
            if len(values)>1:
                values[1][8]='CORRUPTED_STOP'
            return values
        api.read=corrupted_read
        with self.assertRaisesRegex(HandoffBlocked,'LIFECYCLE_ALERT_READBACK'):
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



class TestLedgerNew52EventCompatibility(unittest.TestCase):
    """Synthetic-only regression for a real event code in the private ledger."""

    def synthetic_ledger(self):
        import alert_ledger_contract as contract
        day = '2026-10-28'
        event_day = '2026-10-29'
        symbol = 'SYN'
        key = contract.event_key(
            day, symbol, event_day, 'NEW_52_SESSION_HIGH')
        record = [''] * len(contract.EVENT_HEADER)
        record[0] = key
        record[1] = day + '|' + symbol
        record[2] = day
        record[3] = symbol
        record[4] = event_day
        record[5] = 'NEW_52_SESSION_HIGH'
        record[6] = 'ÖNEMLİ'
        record[17] = contract.REQUESTED
        return contract, key, [list(contract.EVENT_HEADER), record]

    def test_real_new52_event_code_parses_and_stays_unacknowledged(self):
        contract, key, matrix = self.synthetic_ledger()
        parsed = contract.parse_ledger(matrix)
        self.assertEqual(set(parsed), {key})
        self.assertEqual(parsed[key]['status'], contract.REQUESTED)
        self.assertEqual(
            contract.delivery_status(matrix, key),
            'DELIVERY_UNKNOWN_NO_RESEND')

    def test_new52_replay_is_rejected_when_already_reserved(self):
        contract, key, matrix = self.synthetic_ledger()
        with self.assertRaisesRegex(
                contract.LedgerRefused, 'EVENT_ALREADY_RECORDED_NO_RESEND'):
            contract.verify_first_reservation(matrix, matrix, [key])

    def test_unknown_event_type_still_fails_closed(self):
        import alert_ledger_contract as contract
        with self.assertRaisesRegex(
                contract.LedgerRefused, 'BAD_EVENT_KIND_OR_EPISODE'):
            contract.event_key(
                '2026-10-28', 'SYN', '2026-10-29',
                'UNRECOGNIZED_EVENT_CODE')


class TestPendingToRequestedContract(unittest.TestCase):
    """Synthetic-only: record-first transition never proves push delivery."""

    def ledger(self, status, *, timestamp='', note='source confirmed'):
        import alert_ledger_contract as contract
        key = contract.event_key('2026-11-02', 'SYN', '2026-11-02',
                                 'AL_NEW_EPISODE')
        row = [''] * len(contract.EVENT_HEADER)
        row[0] = key
        row[1] = '2026-11-02|SYN'
        row[2:6] = ['2026-11-02', 'SYN', '2026-11-02', 'AL_NEW_EPISODE']
        row[7:10] = ['100.000', '95.000', '110.000']
        row[16] = 'https://github.com/example/research'
        row[17], row[18], row[19] = status, timestamp, note
        return contract, key, [list(contract.EVENT_HEADER), row]

    def test_first_reservation_must_be_pending_not_requested(self):
        c, key, pending = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        before = [list(c.EVENT_HEADER)]
        result = c.verify_first_reservation(before, pending, [key])
        self.assertTrue(result['request_allowed_after_readback'])
        self.assertFalse(result['device_delivery_attested'])
        self.assertEqual(result['new_event_count'], 1)

    def test_direct_requested_first_reservation_must_be_refused(self):
        c, key, after = self.ledger('ALERT_REQUESTED_NOT_DEVICE_ACK',
                                    timestamp='2026-11-03 12:17 TRT')
        before = [list(c.EVENT_HEADER)]
        with self.assertRaisesRegex(c.LedgerRefused,
                                    'EVENT_NOT_PENDING_ON_FIRST_RESERVATION'):
            c.verify_first_reservation(before, after, [key])

    def test_first_reservation_replay_fails_closed(self):
        c, key, after = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        with self.assertRaisesRegex(c.LedgerRefused,
                                    'EVENT_ALREADY_RECORDED_NO_RESEND'):
            c.verify_first_reservation(after, after, [key])

    def test_first_reservation_preserves_other_event_rows(self):
        c, key, after = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        before = [list(c.EVENT_HEADER)]
        other = list(after[1])
        for col in (0, 1, 3):
            other[col] = other[col].replace('SYN', 'ZZZ')
        other[17] = c.SUPPRESSED
        before.append(other)
        import copy
        after = [list(c.EVENT_HEADER), copy.deepcopy(other), after[1]]
        result = c.verify_first_reservation(before, after, [key])
        self.assertEqual(result['new_event_count'], 1)
        after[1][19] = 'tampered'
        with self.assertRaisesRegex(c.LedgerRefused,
                                    'EXISTING_EVENT_CHANGED_DURING_RESERVATION'):
            c.verify_first_reservation(before, after, [key])

    def test_transition_proves_only_ledger_update(self):
        c, key, before = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        _, _, after = self.ledger('ALERT_REQUESTED_NOT_DEVICE_ACK',
                                  timestamp='2026-11-03 12:17 TRT')
        outcome = c.verify_pending_request_transition(before, after, [key])
        self.assertEqual(outcome['recorded_intents'], 1)
        self.assertFalse(outcome['chatgpt_message_proven'])
        self.assertFalse(outcome['device_delivery_attested'])

    def test_replay_must_be_refused(self):
        c, key, before = self.ledger('ALERT_REQUESTED_NOT_DEVICE_ACK',
                                     timestamp='2026-11-03 12:17 TRT')
        with self.assertRaisesRegex(c.LedgerRefused, 'EVENT_NOT_PENDING_NO_RESEND'):
            c.verify_pending_request_transition(before, before, [key])

    def test_changed_price_and_note_must_be_refused(self):
        c, key, before = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        _, _, after = self.ledger('ALERT_REQUESTED_NOT_DEVICE_ACK',
                                  timestamp='2026-11-03 12:17 TRT')
        after[1][8] = '0.01'
        with self.assertRaisesRegex(c.LedgerRefused, 'EVENT_FIELDS_CHANGED'):
            c.verify_pending_request_transition(before, after, [key])
        after[1][8] = before[1][8]
        after[1][19] = 'not the original note'
        with self.assertRaisesRegex(c.LedgerRefused, 'EVENT_FIELDS_CHANGED'):
            c.verify_pending_request_transition(before, after, [key])

    def test_malformed_timestamp_and_unknown_extra_event_refused(self):
        c, key, before = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        _, _, after = self.ledger('ALERT_REQUESTED_NOT_DEVICE_ACK',
                                  timestamp='2026-11-03 12:17 TRT')
        after[1][18] = ''
        with self.assertRaisesRegex(c.LedgerRefused, 'REQUEST_TIMESTAMP_INVALID'):
            c.verify_pending_request_transition(before, after, [key])
        after[1][18] = '2026-11-03 12:17 TRT'
        extra = list(after[1])
        extra[0] = extra[0].replace('SYN', 'COST')
        extra[1] = extra[1].replace('SYN', 'COST')
        extra[3] = 'COST'
        after.append(extra)
        with self.assertRaisesRegex(c.LedgerRefused, 'UNEXPECTED_EVENT_CHANGE'):
            c.verify_pending_request_transition(before, after, [key])

    def test_concurrent_existing_row_mutation_refused(self):
        c, key, before = self.ledger('EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST')
        other = list(before[1])
        for cell in (0, 1, 3):
            other[cell] = other[cell].replace('SYN', 'COST')
        other[17] = c.SUPPRESSED
        before.append(other)
        import copy
        after = copy.deepcopy(before)
        after[1][17] = c.REQUESTED
        after[1][18] = '2026-11-03 12:17 TRT'
        after[2][19] = 'mutated concurrent event'
        with self.assertRaisesRegex(c.LedgerRefused, 'UNEXPECTED_EVENT_CHANGE'):
            c.verify_pending_request_transition(before, after, [key])




class LifecyclePublicDiagnosticsTests(unittest.TestCase):
    """Fail-first regression: redact public lifecycle errors, distinguish causes."""

    def run_synthetic_failure(self, error):
        with patch.object(life.daily_job, 'current_completed_session',
                          return_value='2026-11-05'):
            with patch.dict(life.os.environ,
                            {'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON': 'SYNTHETIC_SECRET',
                             'GITHUB_EVENT_NAME':'schedule',
                             'GITHUB_RUN_ID':'999001',
                             'GITHUB_RUN_ATTEMPT':'1',
                             'GITHUB_REPOSITORY':'gokaydonmez39-jpg/kripto-radar',
                             'GITHUB_REF':'refs/heads/main',
                             'GITHUB_SHA':'a'*40,
                             'GITHUB_WORKFLOW_REF':
                              'gokaydonmez39-jpg/kripto-radar/'
                              '.github/workflows/xray-personal-477-eod.yml@refs/heads/main'},
                            clear=True):
                with patch.object(life, 'SheetApi', return_value=object()):
                    with patch.object(life, 'synchronize', side_effect=error):
                        with patch('builtins.print') as output:
                            exit_code = life.main([])
        self.assertEqual(output.call_count, 1)
        return exit_code, output.call_args.args[0]

    def test_lifecycle_known_scan_failure_is_categorical(self):
        code, message = self.run_synthetic_failure(
            HandoffBlocked('LIFECYCLE_CURRENT_FINAL_SCAN_MISSING'))
        receipt = life.json.loads(message)
        self.assertEqual(code, 3)
        self.assertEqual(receipt['status'], 'LIFECYCLE_BLOCKED')
        self.assertEqual(receipt['reason_code'], 'LIFECYCLE_CURRENT_FINAL_SCAN_MISSING')
        self.assertEqual(receipt['execution'], 'NONE')
        self.assertFalse(receipt['device_ack'])

    def test_lifecycle_google_429_retains_safe_transport_category(self):
        code, message = self.run_synthetic_failure(
            HandoffBlocked('GOOGLE_SHEETS_HTTP_429'))
        receipt = life.json.loads(message)
        self.assertEqual(code, 3)
        self.assertEqual(receipt['reason_code'], 'GOOGLE_SHEETS_HTTP_429')
        self.assertNotIn('SYNTHETIC_SECRET', message)

    def test_lifecycle_untrusted_exception_is_never_exposed(self):
        code, message = self.run_synthetic_failure(
            ValueError('private row/SYNTHETIC_SECRET/token'))
        receipt = life.json.loads(message)
        self.assertEqual(code, 3)
        self.assertEqual(receipt['reason_code'], 'UNCLASSIFIED')
        self.assertNotIn('SYNTHETIC_SECRET', message)
        self.assertNotIn('private row', message)



class UncertainGooglePrivateLifecyclePost(unittest.TestCase):
    """Production-shape no-network negative acceptance for uncertain Google POST.

    Readback is NOT a receipt. A lost 200/timeout may follow a full,
    zero or partial vendor commit: no retry, duplicate event or false PASS.
    """

    class UncertainApi(FakeApi):
        def __init__(self, mode):
            super().__init__()
            self.mode=mode

        def request(self, path, *, method='GET', body=None):
            if self.mode=='committed_then_lost_receipt':
                # Emulate one successfully applied atomic batch whose HTTP
                # response disappears. The caller cannot assume delivery.
                super().request(path,method=method,body=body)
            elif self.mode=='not_committed_then_timeout':
                self.writes+=1
            elif self.mode=='partial_commit_fault_injection':
                # Adversarial model, not a claim Google normally applies a
                # partial atomic batch. Never re-enter the write path.
                self.writes+=1
                first=body['requests'][0]['updateCells']
                i=first['start']['rowIndex']
                self.rows[i][7]=first['rows'][0]['values'][0][
                    'userEnteredValue']['stringValue']
            else:
                raise AssertionError('UNSUPPORTED_TEST_SCENARIO')
            raise HandoffBlocked('GOOGLE_SHEETS_TRANSPORT_TimeoutError')

    def test_lost_google_post_receipt_never_retries_or_reports_delivery(self):
        for mode in ('committed_then_lost_receipt',
                     'not_committed_then_timeout',
                     'partial_commit_fault_injection'):
            with self.subTest(mode=mode):
                api=self.UncertainApi(mode)
                before_rows=copy.deepcopy(api.rows)
                before_alerts=copy.deepcopy(api.alert_rows)
                with self.assertRaisesRegex(
                    HandoffBlocked,'GOOGLE_SHEETS_TRANSPORT_TimeoutError'):
                    life.synchronize(api,'2026-10-26',fetch)
                self.assertEqual(api.writes,1)
                self.assertEqual(api.rows[1][:7],before_rows[1][:7])
                self.assertEqual(api.rows[2][:7],before_rows[2][:7])
                self.assertEqual(api.rows[1][11:],before_rows[1][11:])
                if mode=='committed_then_lost_receipt':
                    self.assertNotEqual(api.rows,before_rows)
                    self.assertEqual(len(api.alert_rows),
                                     len(before_alerts)+1)
                    self.assertEqual(api.alert_rows[-1][17],life.EVENT_PENDING)
                elif mode=='not_committed_then_timeout':
                    self.assertEqual(api.rows,before_rows)
                    self.assertEqual(api.alert_rows,before_alerts)
                else:
                    self.assertNotEqual(api.rows,before_rows)
                    self.assertEqual(api.alert_rows,before_alerts)

    def test_absent_20_nov_scan_cannot_collapse_two_same_symbol_episodes(self):
        # Synthetic current-day read-only plan only; NO Sheet mutation,
        # backfill, replay, alarm reservation or market provider HTTP.
        rows=[list(CANDIDATE_HEADER),
              row('2026-10-30',100.,95.,110.,14,symbol='AAA'),
              row('2026-11-19',101.,96.,111.,0,symbol='AAA')]
        original=copy.deepcopy(rows)
        called=[]
        def offline_read(symbols,asof):
            called.append((list(symbols),asof))
            return {'AAA':[
                bar('2026-11-20',o=101.,h=103.,l=100.,c=102.),
                bar('2026-11-23',o=102.,h=104.,l=101.,c=103.)
            ]}
        result=life.build_updates(rows,'2026-11-23',offline_read)
        self.assertEqual((result['evaluated'],result['closed']),(2,1))
        self.assertEqual(called,[(['AAA'],'2026-11-23')])
        old,new=result['updates']
        self.assertEqual(old['event']['event_day'],'2026-11-20')
        self.assertEqual(old['event']['event_code'],'TIME_EXIT_AT_CLOSE')
        self.assertEqual(old['new_cells'][0],
                         'KAPALI • TIME_EXIT_AT_CLOSE • 15/15 SEANS')
        self.assertEqual(new['new_cells'][0],'AÇIK • 2/15 SEANS')
        self.assertFalse(new['terminal'])
        self.assertIsNone(new['event'])
        self.assertEqual(rows,original)



if __name__=='__main__':
    unittest.main()
