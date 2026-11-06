"""Offline tests for private Sheets handoff; no Google writes or secrets."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import private_sheet_writer as w
import runner

SYMS=runner.get_scope(watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')))
RUN='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001'


def snapshot():
    rows=[{'asof_et':'2026-10-26','symbol':s,'decision':'ELE'} for s in SYMS]
    # Deliberately fictional synthetic fixtures; never check in real
    # privately observed candidate identities or stop/target levels.
    for symbol,price,atr,stop,target in [
            (SYMS[0],100.,2.5,95.,110.),
            (SYMS[1],200.,5.,190.,220.)]:
        r=next(x for x in rows if x['symbol']==symbol)
        r.update(decision='AL',close=price,atr14=atr,
                 indicative_stop=stop,indicative_target_2r=target,
                 relative_iex_volume=1.7,rsi14=60.,
                 sma20=price-10.,sma50=price-20.,prior_high20=price-1.,
                 atr_risk_pct=round(200*atr/price,2))
    return {'scope_sha256':runner.sha_symbols(SYMS),
            'analysis_fingerprint_sha256':runner.analysis_fingerprint(),
            'asof_et':'2026-10-26','requested_symbols':477,'processed_symbols':477,
            'valid_data_symbols':477,'insufficient_data_symbols':0,'remaining_symbols':0,
            'coverage_complete':True,'valid_data_coverage_complete':True,
            'new_signal_publishable':True,'not_broker':True,'orders_sent':0,
            'auto_trading':False,'failed_groups':[],
            'counts':{'START':477,'TEKNIK_AL_ADAYI':2,
                      'YAKIN_IZLE':0,'ELE':475,'VERI_YETERSIZ':0},'rows':rows}


class FakeApi:
    def __init__(self):
        self.candidates=[list(w.CANDIDATE_HEADER)]
        self.scans=[list(w.SCAN_HEADER)]
        self.apply_count=0
        self.break_readback=False
        self.change_on_second_read=False
        self.read_count=0

    def check_metadata(self):
        return True

    def read(self,title,last_col):
        self.read_count+=1
        if self.change_on_second_read and self.read_count==3:
            self.candidates.append(['2026-10-23|CVLT','2026-10-23','CVLT'])
        if title=='ADAY_GECMISI':
            return copy.deepcopy(self.candidates)
        return copy.deepcopy(self.scans)

    def apply(self,p):
        self.apply_count+=1
        self.scans.extend(copy.deepcopy(p['scan_rows']))
        if not self.break_readback:
            self.candidates.extend(copy.deepcopy(p['candidate_rows']))


class PrivateSheetHandoffTests(unittest.TestCase):
    def test_atomic_two_sheet_append_and_independent_readback(self):
        api=FakeApi()
        result=w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(result['status'],'PRIVATE_SHEET_READBACK_PASS')
        self.assertEqual(result['candidates'],2)
        self.assertFalse(result['device_ack'])
        self.assertEqual(api.apply_count,1)
        self.assertEqual(len(api.candidates),3)
        self.assertEqual(len(api.scans),2)

    def test_new_eod_source_provenance_matches_real_github_trigger(self):
        expected = {
            'schedule': 'GitHub schedule VERIFIED IEX EOD',
            'workflow_dispatch': 'GitHub workflow_dispatch VERIFIED IEX EOD',
            'push': 'GitHub push VERIFIED IEX EOD',
        }
        for event, label in expected.items():
            with self.subTest(event=event):
                p = w.plan(snapshot(), [list(w.CANDIDATE_HEADER)],
                           [list(w.SCAN_HEADER)], RUN, run_event=event)
                self.assertEqual(p['scan_rows'][0][1], label)
                self.assertIn('source_event=' + event, p['scan_rows'][0][9])
                self.assertTrue(all('source_event=' + event in r[12]
                                    for r in p['candidate_rows']))
                self.assertFalse(any('private auto handoff' in r[12]
                                     for r in p['candidate_rows']))

    def test_untrusted_or_missing_event_fails_before_sheet_write(self):
        for event in ('', 'pull_request', 'workflow_run', 'bogus', None):
            with self.subTest(event=event):
                api = FakeApi()
                with self.assertRaisesRegex(w.HandoffBlocked,
                                            'UNTRUSTED_GITHUB_EVENT'):
                    w.synchronize(snapshot(), RUN, api, run_event=event)
                self.assertEqual(api.apply_count, 0)

    def test_legacy_scan_replay_never_changes_historical_provenance(self):
        api = FakeApi()
        w.synchronize(snapshot(), RUN, api, run_event='workflow_dispatch')
        original = copy.deepcopy(api.scans[1])
        w.synchronize(snapshot(), RUN, api, run_event='schedule')
        self.assertEqual(api.scans[1], original)
        self.assertEqual(len(api.scans), 2)

    def test_idempotent_replay_no_duplicate(self):
        api=FakeApi()
        w.synchronize(snapshot(),RUN,api,run_event='schedule')
        w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,2)
        self.assertEqual(len(api.candidates),3)
        self.assertEqual(len(api.scans),2)
        self.assertEqual(w.payload_from_plan(
            w.plan(snapshot(),api.candidates,api.scans,RUN,run_event='schedule'))['requests'],[])

    def test_header_drift_blocks(self):
        api=FakeApi()
        api.candidates[0][0]='WRONG HEADER'
        with self.assertRaisesRegex(w.HandoffBlocked,'SHEET_HEADER_DRIFT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)

    def test_existing_duplicate_episode_blocks(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN,run_event='schedule')
        api.candidates.extend([p['candidate_rows'][0]]*2)
        with self.assertRaisesRegex(w.HandoffBlocked,'DUPLICATE_CANDIDATE_KEYS'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')

    def test_immutable_original_stop_blocks_conflict(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN,run_event='schedule')
        row=copy.deepcopy(p['candidate_rows'][0])
        row[5]='100'
        api.candidates.append(row)
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_ORIGINAL_LEVEL_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)

    def test_same_asof_different_counts_blocks(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN,run_event='schedule')
        row=copy.deepcopy(p['scan_rows'][0])
        row[7]='0'
        api.scans.append(row)
        with self.assertRaisesRegex(w.HandoffBlocked,'EXISTING_SCAN_EPOCH_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')

    def test_same_asof_source_proof_mutations_block_before_write(self):
        api = FakeApi()
        w.synchronize(snapshot(), RUN, api, run_event='schedule')
        original = api.scans[1][9]
        data = snapshot()
        cases = [
            original.replace('scopeSHA=' + data['scope_sha256'],
                             'scopeSHA=' + 'f' * 64),
            original.replace('algorithmSHA=' + data['analysis_fingerprint_sha256'],
                             'algorithmSHA=' + 'f' * 64),
            ';'.join(part for part in original.split(';')
                     if not part.startswith('scopeSHA=')),
            original + ';scopeSHA=' + data['scope_sha256'],
        ]
        for altered in cases:
            with self.subTest(altered=altered != original):
                self.assertNotEqual(altered, original)
                api.scans[1][9] = altered
                with self.assertRaisesRegex(
                        w.HandoffBlocked,
                        'EXISTING_SCAN_SOURCE_(SHA_CONFLICT|PROOF_MISSING_OR_MALFORMED)'):
                    w.synchronize(data, RUN, api, run_event='schedule')
                self.assertEqual(api.apply_count, 1)
        api.scans[1][9] = original
        w.synchronize(data, RUN, api, run_event='schedule')
        self.assertEqual(len(api.scans), 2)
        self.assertEqual(len(api.candidates), 3)

    def test_concurrent_row_change_fails_closed_before_write(self):
        api=FakeApi()
        api.change_on_second_read=True
        with self.assertRaisesRegex(w.HandoffBlocked,'CONCURRENT_SHEET_EDIT_BLOCKED'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)

    def test_missing_readback_blocks_false_delivery(self):
        api=FakeApi()
        api.break_readback=True
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_READBACK_MISSING'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')

    def test_bad_scope_and_partial_data_never_append(self):
        for field,value in [('valid_data_symbols',476),('scope_sha256','f'*64),
                            ('requested_symbols',478)]:
            with self.subTest(field=field):
                api=FakeApi()
                data=snapshot()
                data[field]=value
                with self.assertRaises(Exception):
                    w.synchronize(data,RUN,api,run_event='schedule')
                self.assertEqual(api.apply_count,0)

    def test_readback_rejects_corrupted_new_stop(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN,run_event='schedule')
        candidates=[list(w.CANDIDATE_HEADER)]+copy.deepcopy(p['candidate_rows'])
        scans=[list(w.SCAN_HEADER)]+copy.deepcopy(p['scan_rows'])
        candidates[1][5]='1,00'
        with self.assertRaisesRegex(w.HandoffBlocked,'READBACK'):
            w.verify_readback(p,candidates,scans)

    def test_readback_rejects_corrupted_new_scan_provenance(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN,run_event='schedule')
        candidates=[list(w.CANDIDATE_HEADER)]+copy.deepcopy(p['candidate_rows'])
        scans=[list(w.SCAN_HEADER)]+copy.deepcopy(p['scan_rows'])
        scans[1][8]='https://github.com/unrelated/actions/runs/123'
        with self.assertRaisesRegex(w.HandoffBlocked,'READBACK'):
            w.verify_readback(p,candidates,scans)

    def test_existing_price_one_cent_conflict_is_not_rounding(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN,run_event='schedule')
        old=copy.deepcopy(p['candidate_rows'][0])
        old[4]='100,01'
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_ORIGINAL_LEVEL_CONFLICT'):
            w.plan(snapshot(),[list(w.CANDIDATE_HEADER),old],
                   [list(w.SCAN_HEADER)],RUN,run_event='schedule')

    def test_wrong_workbook_timezone_and_missing_panel_are_rejected(self):
        api=w.SheetApi.__new__(w.SheetApi)
        api.token='test-only'
        api.base='unused'
        api.sheet_ids=None
        api.request=lambda path: {'properties':{'timeZone':'Etc/UTC'},
                                  'sheets':[{'properties':{'title':'ADAY_GECMISI','sheetId':101}},
                                            {'properties':{'title':'TARAMA_KAYITLARI','sheetId':102}}]}
        with self.assertRaisesRegex(w.HandoffBlocked,'SHEET'):
            api.check_metadata()

    def test_missing_authorization_is_not_green(self):
        """The private writer must be a required production step."""
        workflow=Path(__file__).resolve().parent.parent/'.github/workflows/xray-personal-477-eod.yml'
        source=workflow.read_text(encoding='utf-8')
        start=source.index('      - name: Private Google Sheets writer')
        end=source.index('      - name: Reserve verified new AL events PENDING',start)
        writer=source[start:end]
        self.assertIn('BLOCKED_NO_AUTH_OR_PRIVATE_ID_NOT_A_DELIVERY_PASS',writer)
        self.assertIn('exit 3',writer)
        self.assertNotIn('exit 0',writer.split('BLOCKED_NO_AUTH_OR_PRIVATE_ID_NOT_A_DELIVERY_PASS')[1])

    def test_outbox_auth_failure_is_never_counted_as_delivery(self):
        workflow=Path(__file__).resolve().parent.parent/'.github/workflows/xray-personal-477-eod.yml'
        source=workflow.read_text(encoding='utf-8')
        start=source.index('      - name: Reserve verified new AL events PENDING')
        end=source.index('      - name: No public delivery',start)
        step=source[start:end]
        self.assertIn('AL_OUTBOX=BLOCKED_NO_PRIVATE_AUTH',step)
        self.assertIn('exit 3',step)
        self.assertNotIn('exit 0',step.split('AL_OUTBOX=BLOCKED_NO_PRIVATE_AUTH')[1])
        self.assertIn('python alert_outbox_producer.py --snapshot',step)
        self.assertNotIn('continue-on-error: true',step)

    def test_private_auth_preflight_is_read_only_and_exposes_no_secrets(self):
        workflow=Path(__file__).resolve().parent.parent/'.github/workflows/xray-personal-477-eod.yml'
        text=workflow.read_text(encoding='utf-8')
        self.assertIn('  private-sheets-auth-preflight:',text)
        segment=text.split('  private-sheets-auth-preflight:',1)[1].split(
            '  private-episode-followups:',1)[0]
        self.assertIn('PRIVATE_SHEETS_PREFLIGHT=READ_PASS_WRITE_NOT_VERIFIED',segment)
        self.assertIn('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON',segment)
        self.assertIn('XRAY_PRIVATE_SPREADSHEET_ID',segment)
        self.assertIn('api.check_metadata()',segment)
        self.assertIn("api.read('ADAY_GECMISI','M')",segment)
        self.assertIn("api.read('TARAMA_KAYITLARI','J')",segment)
        self.assertIn("api.read('UYARI_OLAYLARI','T')",segment)
        self.assertNotIn('api.apply(',segment)
        self.assertNotIn(':batchUpdate',segment)
        self.assertNotIn('private_sheet_writer.py --snapshot',segment)

    def test_no_credentials_is_explicit_nonzero_not_fake_success(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'snap.json'
            file.write_text('{}')
            with patch.dict('os.environ',{'GITHUB_RUN_ID':'42'},clear=True):
                self.assertEqual(w.main(['--snapshot',str(file)]),3)

    def test_candidate_rows_never_include_broker_or_orders(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN,run_event='schedule')
        self.assertEqual(len(p['candidate_rows']),2)
        self.assertEqual(len(p['scan_rows']),1)
        self.assertTrue(all('NO_BROKER_NO_ORDERS' in r[-1] for r in p['candidate_rows']))
        self.assertFalse(any('AL_NEW_EPISODE' in str(r) for r in p['candidate_rows']))



class SheetsTransportRegressionTests(unittest.TestCase):
    """Fail-first: quota, read retry, public diagnostics, and no POST replay."""

    def _api(self):
        api = w.SheetApi.__new__(w.SheetApi)
        api.base = 'https://sheets.googleapis.com/v4/spreadsheets/TEST_ONLY'
        api.token = 'PRIVATE_TEST_TOKEN_MUST_NOT_APPEAR'
        return api

    def _rate_limited(self):
        from urllib.error import HTTPError
        return HTTPError('https://sheets.googleapis.com/v4/spreadsheets/TEST_ONLY',
                         429, 'synthetic quota', {}, None)

    @patch.object(w.time, 'sleep')
    @patch.object(w, 'urlopen')
    def test_get_quota_exhaustion_has_four_bounded_backoffs_and_safe_code(self, opener, sleep):
        opener.side_effect = self._rate_limited()
        with self.assertRaisesRegex(w.HandoffBlocked, '^GOOGLE_SHEETS_HTTP_429$'):
            self._api().request('/values/TEST_ONLY')
        self.assertEqual(opener.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        for n, call in enumerate(sleep.call_args_list):
            interval = call.args[0]
            self.assertGreaterEqual(interval, 2 ** n)
            self.assertLessEqual(interval, 2 ** n + 0.26)

    @patch.object(w.time, 'sleep')
    @patch.object(w, 'urlopen')
    def test_get_recovers_from_two_429_errors_without_post(self, opener, sleep):
        import io
        opener.side_effect = [self._rate_limited(), self._rate_limited(),
                              io.BytesIO(b'{"values": []}')]
        self.assertEqual(self._api().request('/values/TEST_ONLY'), {'values': []})
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch.object(w.time, 'sleep')
    @patch.object(w, 'urlopen')
    def test_batch_post_429_is_never_retried(self, opener, sleep):
        opener.side_effect = self._rate_limited()
        with self.assertRaisesRegex(w.HandoffBlocked, '^GOOGLE_SHEETS_HTTP_429$'):
            self._api().request(':batchUpdate', method='POST',
                                body={'requests': [{'updateCells': {}}]})
        self.assertEqual(opener.call_count, 1)
        sleep.assert_not_called()

    def test_public_report_contains_categorical_code_not_private_error(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'synthetic.json'
            file.write_text('{}', encoding='utf-8')
            env = {'GITHUB_RUN_ID': '77', 'GITHUB_EVENT_NAME': 'schedule',
                   'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON': 'PRIVATE_TEST_TOKEN_MUST_NOT_APPEAR'}
            with patch.dict(w.os.environ, env, clear=True):
                with patch.object(w, 'SheetApi', return_value=object()):
                    with patch.object(w, 'synchronize',
                                      side_effect=w.HandoffBlocked('GOOGLE_SHEETS_HTTP_429')):
                        with patch('builtins.print') as output:
                            self.assertEqual(w.main(['--snapshot', str(file)]), 3)
            text = output.call_args.args[0]
            receipt = w.json.loads(text)
            self.assertEqual(receipt['reason_code'], 'GOOGLE_SHEETS_HTTP_429')
            self.assertEqual(receipt['status'], 'PRIVATE_SHEET_SYNC_BLOCKED')
            self.assertNotIn('PRIVATE_TEST_TOKEN', text)
            self.assertFalse(receipt['device_ack'])

    def test_untrusted_exception_details_never_enter_public_report(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'synthetic.json'
            file.write_text('{}', encoding='utf-8')
            env = {'GITHUB_RUN_ID': '77', 'GITHUB_EVENT_NAME': 'schedule',
                   'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON': 'SENSITIVE_UNIT_TEST'}
            with patch.dict(w.os.environ, env, clear=True):
                with patch.object(w, 'SheetApi', return_value=object()):
                    with patch.object(w, 'synchronize',
                                      side_effect=ValueError('SENSITIVE_UNIT_TEST-private-url')):
                        with patch('builtins.print') as output:
                            self.assertEqual(w.main(['--snapshot', str(file)]), 3)
            text = output.call_args.args[0]
            receipt = w.json.loads(text)
            self.assertEqual(receipt['reason_code'], 'UNCLASSIFIED')
            self.assertNotIn('SENSITIVE_UNIT_TEST', text)



if __name__=='__main__':
    unittest.main()
