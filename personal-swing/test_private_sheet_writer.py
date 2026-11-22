"""Offline tests for private Sheets handoff; no Google writes or secrets."""
import contextlib
import copy
import io
import json
import os
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
    @staticmethod
    def pit_fixture_asof(day):
        """Produce exactly the reviewed 477 PIT aliases for synthetic ASOF."""
        snap=snapshot()
        current=runner.get_scope(
            watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),
            asof=day)
        original={row['symbol']:row for row in snap['rows']}
        aliases={'SUPN':'INDV','GNTX':'ROKU'}
        rows=[]
        for symbol in current:
            seed=original.get(symbol)
            if seed is None:
                seed=original[aliases[symbol]]
            row=copy.deepcopy(seed)
            row['symbol']=symbol
            row['asof_et']=day
            rows.append(row)
        snap['rows']=rows
        snap['asof_et']=day
        snap['scope_sha256']=runner.sha_symbols(current)
        return snap

    def test_natural_scan_source_is_exact_single_field_not_substring(self):
        row=["2026-11-23",w.RUN_EVENT_LABELS["schedule"],
             "477","477","477","0","TRUE","0",RUN,
             "scopeSHA="+"a"*64+";algorithmSHA="+"b"*64+
             ";source_event=schedule;NO_ORDERS"]
        self.assertTrue(w.canonical_natural_scan_source(row))
        for origin,label in (
            ("source_event=workflow_dispatch",w.RUN_EVENT_LABELS["schedule"]),
            ("source_event=scheduled",w.RUN_EVENT_LABELS["schedule"]),
            ("source_event=schedule;source_event=push",w.RUN_EVENT_LABELS["schedule"]),
            ("source_event=schedule",w.RUN_EVENT_LABELS["workflow_dispatch"]),
        ):
            with self.subTest(origin=origin,label=label):
                fake=list(row)
                fake[9]=fake[9].replace("source_event=schedule",origin)
                fake[1]=label
                self.assertFalse(w.canonical_natural_scan_source(fake))

    def test_real_cli_non_natural_run_cannot_write_canonical_eod(self):
        # Existing manual fallback lacks separately attested parent/child
        # and immutable single-writer provenance. It must NOT poison the
        # only canonical Sheet, even inside today's completed ASOF window.
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'snapshot.json'
            path.write_text(json.dumps(snapshot()),encoding='utf-8')
            for event in ('workflow_dispatch','push'):
                with self.subTest(event=event):
                    output=io.StringIO()
                    with patch.dict(os.environ,{
                        'GITHUB_EVENT_NAME':event,
                        'GITHUB_RUN_ID':'999001',
                        'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'synthetic-offline-test',
                    }), patch.object(
                        w,'SheetApi',
                        side_effect=AssertionError('PROVIDER_CLIENT_MUST_NOT_START')
                    ) as client,contextlib.redirect_stdout(output):
                        rc=w.main(['--snapshot',str(path)])
                    result=json.loads(output.getvalue())
                    self.assertEqual(rc,3)
                    self.assertEqual(result['status'],'PRIVATE_SHEET_SYNC_BLOCKED')
                    self.assertEqual(
                        result['reason_code'],
                        'NON_NATURAL_CANONICAL_EOD_WRITE_UNAUTHORIZED')
                    self.assertFalse(result['device_ack'])
                    client.assert_not_called()

    def test_canonical_writer_rejects_wrong_natural_job_before_provider(self):
        # A runner with valid Sheets credentials is not sufficient:
        # workflow path, branch, repo, source SHA and attempt also matter.
        good={
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':'gokaydonmez39-jpg/kripto-radar',
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_SHA':'a'*40,
            'GITHUB_WORKFLOW_REF':
                'gokaydonmez39-jpg/kripto-radar/'
                '.github/workflows/xray-personal-477-eod.yml@refs/heads/main',
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }
        adversaries=(
            ('GITHUB_REPOSITORY','other/repo'),
            ('GITHUB_REF','refs/heads/dev'),
            ('GITHUB_WORKFLOW_REF','gokaydonmez39-jpg/kripto-radar/'
             '.github/workflows/other-scheduled.yml@refs/heads/main'),
            ('GITHUB_WORKFLOW_REF','gokaydonmez39-jpg/kripto-radar/'
             '.github/workflows/xray-personal-477-eod.yml@refs/heads/dev'),
            ('GITHUB_RUN_ATTEMPT','2'),
            ('GITHUB_SHA','invalid'),
            ('GITHUB_SHA','B'*40),
            ('GITHUB_RUN_ID','0'),
            ('GITHUB_RUN_ID','001'),
        )
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'synthetic.json'
            file.write_text(json.dumps(snapshot()),encoding='utf-8')
            for key,value in adversaries:
                with self.subTest(key=key,value=value):
                    environment=dict(good)
                    environment[key]=value
                    with patch.dict(os.environ,environment,clear=True):
                        with patch.object(w,'SheetApi',
                            side_effect=AssertionError('AUTHENTICATED_SHEET_STARTED')
                        ) as provider,contextlib.redirect_stdout(io.StringIO()) as out:
                            rc=w.main(['--snapshot',str(file)])
                    result=json.loads(out.getvalue())
                    self.assertEqual(rc,3)
                    self.assertEqual(result['reason_code'],
                                     'NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED')
                    provider.assert_not_called()

    def test_canonical_sheet_writer_rejects_stale_or_unverifiable_asof_before_google(self):
        # RED-first: syntactically genuine natural run metadata cannot promote
        # a stale snapshot. No private Google client may be instantiated.
        import daily_job
        good={
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':'gokaydonmez39-jpg/kripto-radar',
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_SHA':'a'*40,
            'GITHUB_WORKFLOW_REF':
                'gokaydonmez39-jpg/kripto-radar/'
                '.github/workflows/xray-personal-477-eod.yml@refs/heads/main',
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'synthetic-offline-token',
        }
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'stale_private_snapshot.json'
            path.write_text(json.dumps(snapshot()),encoding='utf-8')
            for latest in ('2026-11-23',None):
                with self.subTest(latest=latest):
                    output=io.StringIO()
                    with patch.dict(os.environ,good,clear=True), \
                         patch.object(daily_job,'current_completed_session',
                                      return_value=latest), \
                         patch.object(w,'SheetApi',
                                      side_effect=AssertionError('NO_GOOGLE_ALLOWED')) as client, \
                         contextlib.redirect_stdout(output):
                        code=w.main(['--snapshot',str(path)])
                    receipt=json.loads(output.getvalue())
                    self.assertEqual(code,3)
                    self.assertEqual(receipt['reason_code'],
                                     'NATURAL_EOD_SNAPSHOT_NONCURRENT_ASOF')
                    client.assert_not_called()
            output=io.StringIO()
            with patch.dict(os.environ,good,clear=True), \
                 patch.object(daily_job,'current_completed_session',
                              side_effect=RuntimeError('calendar unavailable')), \
                 patch.object(w,'SheetApi',
                              side_effect=AssertionError('NO_GOOGLE_ALLOWED')) as client, \
                 contextlib.redirect_stdout(output):
                code=w.main(['--snapshot',str(path)])
            self.assertEqual(code,3)
            self.assertEqual(json.loads(output.getvalue())['reason_code'],
                             'NATURAL_EOD_SNAPSHOT_NONCURRENT_ASOF')
            client.assert_not_called()

    def test_canonical_writer_complete_scheduled_identity_accepts_fake_api(self):
        good={
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':'gokaydonmez39-jpg/kripto-radar',
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_SHA':'a'*40,
            'GITHUB_WORKFLOW_REF':
                'gokaydonmez39-jpg/kripto-radar/'
                '.github/workflows/xray-personal-477-eod.yml@refs/heads/main',
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'synthetic.json'
            file.write_text(json.dumps(snapshot()),encoding='utf-8')
            fake=FakeApi()
            with patch.dict(os.environ,good,clear=True), \
                 patch('daily_job.current_completed_session',return_value='2026-10-26'):
                with patch.object(w,'SheetApi',return_value=fake) as provider:
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        rc=w.main(['--snapshot',str(file)])
            result=json.loads(out.getvalue())
            self.assertEqual(rc,0,result)
            self.assertEqual(result['status'],'PRIVATE_SHEET_READBACK_PASS')
            self.assertEqual(fake.apply_count,1)
            provider.assert_called_once()

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

    def test_github_run_url_rejects_cross_repo_and_path_spoofs(self):
        forged = (
            'https://github.com/another-owner/repo/actions/runs/999001',
            'https://github.com/gokaydonmez39-jpg/kripto-radar-evil/actions/runs/999001',
            'https://github.com/gokaydonmez39-jpg/kripto-radar/notreal/actions/runs/999001',
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001/extra',
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001?redirect=1',
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/00099',
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/not-a-number',
        )
        for run_url in forged:
            with self.subTest(source=run_url):
                api = FakeApi()
                with self.assertRaisesRegex(w.HandoffBlocked, 'UNVERIFIED_RUN_ID'):
                    w.synchronize(snapshot(), run_url, api, run_event='schedule')
                self.assertEqual(api.apply_count, 0)

    def test_untrusted_or_missing_event_fails_before_sheet_write(self):
        for event in ('', 'pull_request', 'workflow_run', 'bogus', None):
            with self.subTest(event=event):
                api = FakeApi()
                with self.assertRaisesRegex(w.HandoffBlocked,
                                            'UNTRUSTED_GITHUB_EVENT'):
                    w.synchronize(snapshot(), RUN, api, run_event=event)
                self.assertEqual(api.apply_count, 0)

    def test_same_asof_different_trigger_must_not_borrow_existing_receipt(self):
        api = FakeApi()
        w.synchronize(snapshot(), RUN, api, run_event='workflow_dispatch')
        original = copy.deepcopy(api.scans[1])
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'EXISTING_SCAN_SOURCE_IDENTITY_CONFLICT'):
            w.synchronize(snapshot(), RUN, api, run_event='schedule')
        self.assertEqual(api.scans[1], original)
        self.assertEqual(len(api.scans), 2)
        self.assertEqual(api.apply_count, 1)

    def test_same_asof_different_github_run_cannot_claim_existing_receipt(self):
        api = FakeApi()
        w.synchronize(snapshot(), RUN, api, run_event='schedule')
        other='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999002'
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'EXISTING_SCAN_SOURCE_IDENTITY_CONFLICT'):
            w.synchronize(snapshot(), other, api, run_event='schedule')
        self.assertEqual(api.apply_count, 1)
        self.assertEqual(len(api.scans), 2)

    def test_same_asof_source_note_or_label_tamper_fails_closed(self):
        for kind in ('label','missing_event','duplicate_event','wrong_event','run_url'):
            with self.subTest(kind=kind):
                api = FakeApi()
                w.synchronize(snapshot(), RUN, api, run_event='schedule')
                if kind == 'label':
                    api.scans[1][1]='GitHub workflow_dispatch VERIFIED IEX EOD'
                elif kind == 'missing_event':
                    api.scans[1][9]=api.scans[1][9].replace(';source_event=schedule','')
                elif kind == 'duplicate_event':
                    api.scans[1][9]+=';source_event=schedule'
                elif kind == 'wrong_event':
                    api.scans[1][9]=api.scans[1][9].replace(
                        ';source_event=schedule',';source_event=workflow_dispatch')
                else:
                    api.scans[1][8]='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999002'
                with self.assertRaisesRegex(w.HandoffBlocked,
                                            'EXISTING_SCAN_SOURCE_IDENTITY_CONFLICT'):
                    w.synchronize(snapshot(), RUN, api, run_event='schedule')
                self.assertEqual(api.apply_count, 1)

    def test_same_asof_same_run_same_trigger_preserves_idempotent_noop(self):
        api = FakeApi()
        w.synchronize(snapshot(), RUN, api, run_event='schedule')
        p=w.plan(snapshot(),api.candidates,api.scans,RUN,run_event='schedule')
        self.assertEqual(p['scan_rows'],[])
        self.assertEqual(p['candidate_rows'],[])

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


    def test_23_nov_forward_natural_eod_survives_missing_20_nov_without_backfill(self):
        """Only a NEW verified natural epoch may append; missing 20 stays missing.

        This is a fake offline Google API, never live market data, dispatch,
        Sheet mutation, notification or an old-asof replay.
        """
        api=FakeApi()
        old=['2026-11-19',w.RUN_EVENT_LABELS['schedule'],
             '477','477','477','0','TRUE','0',
             'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/44671232964',
             'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64+
             ';source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK']
        api.scans.append(old)
        evidence=copy.deepcopy(old)
        current=self.pit_fixture_asof('2026-11-23')
        result=w.synchronize(current,RUN,api,run_event='schedule')
        self.assertEqual(result['status'],'PRIVATE_SHEET_READBACK_PASS')
        self.assertEqual(result['asof_et'],'2026-11-23')
        self.assertEqual(api.apply_count,1)
        self.assertEqual(api.scans[1],evidence)
        self.assertEqual([x[0] for x in api.scans[1:]],
                         ['2026-11-19','2026-11-23'])
        self.assertNotIn('2026-11-20',[x[0] for x in api.scans[1:]])
        self.assertFalse(result['device_ack'])
        again=w.synchronize(current,RUN,api,run_event='schedule')
        self.assertEqual(again['status'],'PRIVATE_SHEET_READBACK_PASS')
        self.assertEqual(api.apply_count,1)

    def test_late_20_nov_source_after_new_23_nov_eod_is_always_rejected(self):
        api=FakeApi()
        api.scans.append([
            '2026-11-23',w.RUN_EVENT_LABELS['schedule'],
            '477','477','477','0','TRUE','0',RUN,
            'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64+
            ';source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK'])
        source=self.pit_fixture_asof('2026-11-20')
        old=copy.deepcopy(api.scans)
        with self.assertRaisesRegex(
                w.HandoffBlocked,'SCAN_DATE_ORDER_OR_STALE_ASOF'):
            w.synchronize(source,RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)
        self.assertEqual(api.scans,old)


    def test_20_nov_forensic_data_receipt_is_explicitly_not_final_or_dispatch(self):
        """An audited 477x52 bar set is evidence, not an absent natural run."""
        file=(Path(__file__).resolve().parent.parent /
              'nasdaq-xray/incident-receipts/'
              'personal477-eod-missing-2026-11-20.json')
        incident=json.loads(file.read_text(encoding='utf8'))
        self.assertEqual(
            incident['schema'],'XRAY_PERSONAL477_NATURAL_EOD_MISSING_EVIDENCE_V1')
        self.assertFalse(incident['canonical_final'])
        self.assertIsNone(incident['source_run_id'])
        self.assertFalse(incident['source_run_success'])
        self.assertFalse(incident['source_scan_readback'])
        self.assertFalse(incident['allows_backfill'])
        self.assertFalse(incident['allows_replay'])
        self.assertFalse(incident['allows_automatic_dispatch'])
        self.assertFalse(incident['new_signal_publishable'])
        self.assertFalse(incident['chatgpt_delivery_ack'])
        self.assertFalse(incident['device_ack'])
        self.assertFalse(incident['forward_policy']['full_final_release_authorized'])
        v=incident['independently_checked_market_data']
        self.assertEqual(v['pit_unique_symbols'],477)
        self.assertEqual(v['xnas_official_sessions'],52)
        self.assertEqual(v['total_observed_bars'],477*52)
        self.assertEqual(sum(g['bars'] for g in v['by_group']),477*52)
        self.assertEqual(sum(g['symbols'] for g in v['by_group']),477)
        self.assertEqual(v['symbol_sets_with_exact_52_dates'],477)
        self.assertFalse(v['production_engine_analytical_recompute_verified'])
        self.assertEqual(incident['observed_incident']['exact_primary_workflow_matches'],0)
        self.assertEqual(incident['observed_incident']['private_sheet_2026_11_20_final_count'],0)

    def test_old_asof_manual_dispatch_must_never_append_behind_latest_scan(self):
        api = FakeApi()
        api.scans.append(['2026-10-27','GitHub schedule VERIFIED IEX EOD',
                          '477','477','477','0','TRUE','0',RUN,'source_event=schedule'])
        original=copy.deepcopy(api.scans)
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'SCAN_DATE_ORDER_OR_STALE_ASOF'):
            w.synchronize(snapshot(),RUN,api,run_event='workflow_dispatch')
        self.assertEqual(api.apply_count,0)
        self.assertEqual(api.scans,original)
        self.assertEqual(len(api.candidates),1)

    def test_older_same_run_epoch_reuse_after_newer_scan_must_be_refused(self):
        api = FakeApi()
        w.synchronize(snapshot(),RUN,api,run_event='schedule')
        api.scans.append(['2026-10-27','GitHub schedule VERIFIED IEX EOD',
                          '477','477','477','0','TRUE','0',RUN,'source_event=schedule'])
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'SCAN_DATE_ORDER_OR_STALE_ASOF'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,1)
        self.assertEqual(len(api.scans),3)

    def test_corrupted_existing_scan_order_must_block_future_append(self):
        api=FakeApi()
        api.scans.extend([
            ['2026-10-27'],['2026-10-25']])
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'SCAN_DATE_ORDER_OR_STALE_ASOF'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)

    def test_existing_eod_missing_one_candidate_must_not_reconstruct(self):
        api=FakeApi()
        w.synchronize(snapshot(),RUN,api,run_event='schedule')
        api.candidates.pop()
        original=copy.deepcopy(api.candidates)
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'CANDIDATE_EPOCH_SET_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,1)
        self.assertEqual(api.candidates,original)

    def test_existing_eod_extra_same_asof_candidate_must_not_be_accepted(self):
        api=FakeApi()
        w.synchronize(snapshot(),RUN,api,run_event='schedule')
        extra=copy.deepcopy(api.candidates[1])
        extra[0]='2026-10-26|'+SYMS[2]
        extra[2]=SYMS[2]
        api.candidates.append(extra)
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'CANDIDATE_EPOCH_SET_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,1)

    def test_candidate_without_same_asof_scan_cannot_repair_partial_epoch(self):
        api=FakeApi()
        first=w.plan(snapshot(),api.candidates,api.scans,RUN)
        api.candidates.append(copy.deepcopy(first['candidate_rows'][0]))
        before=copy.deepcopy(api.candidates)
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'CANDIDATE_EPOCH_SET_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,0)
        self.assertEqual(api.candidates,before)
        self.assertEqual(len(api.scans),1)

    def test_after_write_unexpected_same_day_candidate_must_fail_readback(self):
        class InjectUnexpectedAfterApply(FakeApi):
            def apply(self,p):
                super().apply(p)
                extra=copy.deepcopy(self.candidates[1])
                extra[0]='2026-10-26|'+SYMS[2]
                extra[2]=SYMS[2]
                self.candidates.append(extra)
        api=InjectUnexpectedAfterApply()
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    'CANDIDATE_EPOCH_READBACK_SET_CONFLICT'):
            w.synchronize(snapshot(),RUN,api,run_event='schedule')
        self.assertEqual(api.apply_count,1)

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



class PrivateSheetDestinationContract(unittest.TestCase):
    """Real runner uses authenticated metadata; these are network-free negatives."""

    @staticmethod
    def api():
        a=w.SheetApi.__new__(w.SheetApi)
        a.base="https://sheets.googleapis.com/v4/spreadsheets/SYNTHETIC"
        a.token="NEVER_EXPOSE"
        a.sheet_ids={'scan':101,'candidate':102,'alerts':103}
        a._post_scope={'scan':101,'candidate':102,'alerts':103,
                       'panel':104,'score':105,'neon':106}
        return a

    @staticmethod
    def cells(n, value="2026-11-23"):
        return w.as_cells([[value]*n],101)

    def test_source_and_candidate_append_require_authenticated_epoch_batch(self):
        """No single append to source scan or candidates, even with valid cells."""
        api=self.api()
        rogue=(
            w.as_cells([['2026-11-23']*10],101),
            w.as_cells([['2026-11-23|AL']*13],102),
            w.as_cells([['manual']*23],104),
            w.as_cells([['manual']*35],999),
        )
        for request in rogue:
            with self.subTest(sheet=request['appendCells']['sheetId']):
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    "GOOGLE_UNAUTHORIZED_MUTATION")) as net,patch.object(
                    w,'require_source_lastmile_before_private_post') as src,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(w.HandoffBlocked,
                                                'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',
                                    body={'requests':[request]})
                    net.assert_not_called()
                    src.assert_not_called()
                    lease.assert_not_called()

    def test_epoch_marker_cannot_bind_to_alert_sheet_or_forged_candidate_asof(self):
        api=self.api()
        valid_marker=w.epoch_marker('2026-11-23',101)
        fake_alert_marker=w.epoch_marker('2026-11-23',103)
        rogue=(
            [{'addNamedRange':{'namedRange':fake_alert_marker}},
             w.as_cells([['2026-11-23']*10],103)],
            [{'addNamedRange':{'namedRange':valid_marker}},
             w.as_cells([['2026-11-23']*10],101),
             w.as_cells([['2026-11-22|AL']*13],102)],
            [{'addNamedRange':{'namedRange':valid_marker}},
             w.as_cells([['2026-11-23']*10],101),
             w.as_cells([['2026-11-23|AL']*13],103)],
        )
        for requests in rogue:
            with self.subTest(candidate=requests[-1]['appendCells']['sheetId']):
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    "GOOGLE_UNAUTHORIZED_MUTATION")) as net,patch.object(
                    w,'require_source_lastmile_before_private_post') as src,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(w.HandoffBlocked,
                                                'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',
                                    body={'requests':requests})
                    net.assert_not_called()
                    src.assert_not_called()
                    lease.assert_not_called()

    def test_updates_cannot_retarget_candidate_or_panel_destination(self):
        api=self.api()
        cell=lambda x:{'userEnteredValue':{'stringValue':x}}
        rogue=(
            {'updateCells':{'start':{'sheetId':103,'rowIndex':5,'columnIndex':7},
                            'rows':[{'values':[cell('x') for _ in range(4)]}],
                            'fields':'userEnteredValue'}},
            {'updateCells':{'range':{'sheetId':101,'startRowIndex':5,
                                    'endRowIndex':6,'startColumnIndex':1,
                                    'endColumnIndex':3},
                            'rows':[{'values':[cell('x'),cell('y')]}],
                            'fields':'userEnteredValue'}},
        )
        for request in rogue:
            with self.subTest(request=request):
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    "GOOGLE_UNAUTHORIZED_MUTATION")) as net,patch.object(
                    w,'require_source_lastmile_before_private_post') as src,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(w.HandoffBlocked,
                                                'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',
                                    body={'requests':[request]})
                    net.assert_not_called()
                    src.assert_not_called()
                    lease.assert_not_called()


class SheetsTransportRegressionTests(unittest.TestCase):
    """Fail-first: quota, read retry, public diagnostics, and no POST replay."""

    def _api(self):
        api = w.SheetApi.__new__(w.SheetApi)
        api.base = 'https://sheets.googleapis.com/v4/spreadsheets/TEST_ONLY'
        api.token = 'PRIVATE_TEST_TOKEN_MUST_NOT_APPEAR'
        api._post_scope={'scan':1,'candidate':2,'alerts':3,
                         'panel':1146954931,'score':5,'neon':477300001}
        return api

    def _rate_limited(self):
        from urllib.error import HTTPError
        return HTTPError('https://sheets.googleapis.com/v4/spreadsheets/TEST_ONLY',
                         429, 'synthetic quota', {}, None)

    def test_unapproved_mutating_http_verbs_never_reach_google(self):
        """No DELETE/PATCH/PUT from the shared private Sheets transport."""
        api=self._api()
        for method in ('DELETE','PATCH','PUT','HEAD'):
            with self.subTest(method=method):
                with patch.object(w,'urlopen',
                    side_effect=AssertionError('UNAUTHORIZED_HTTP_SENT')) as http:
                    with patch.object(w,'require_source_lastmile_before_private_post'
                        ) as source:
                        with patch.object(w,'require_epoch_lease_before_private_post'
                            ) as lease:
                            with self.assertRaisesRegex(
                                w.HandoffBlocked,'GOOGLE_SHEETS_METHOD_SCOPE_INVALID'):
                                api.request(':batchUpdate',method=method,
                                            body={'requests':[]})
                            http.assert_not_called()
                            source.assert_not_called()
                            lease.assert_not_called()

    def test_unapproved_post_paths_and_destructive_batch_requests_denied(self):
        """Prevent caller drift into unauthorized Google Sheet mutations."""
        api=self._api()
        invalid=(
            ('/values/PRIVATE:clear',{'requests':[]}),
            ('/values/PRIVATE:append',{'requests':[]}),
            (':batchUpdate',{'requests':[{'deleteSheet':{'sheetId':1}}]}),
            (':batchUpdate',{'requests':[{'deleteDimension':{}}]}),
            (':batchUpdate',{'requests':[{'deleteNamedRange':{}}]}),
            (':batchUpdate',{'requests':[{'updateSpreadsheetProperties':{}}]}),
            (':batchUpdate',{'requests':[{'appendCells':{}},
                                        {'deleteSheet':{}}]}),
            (':batchUpdate',{'requests':[], 'includeSpreadsheetInResponse':True}),
            (':batchUpdate',None),
        )
        for path,body in invalid:
            with self.subTest(path=path,body=body):
                with patch.object(w,'urlopen',
                    side_effect=AssertionError('UNAUTHORIZED_POST_SENT')) as http:
                    with patch.object(w,'require_source_lastmile_before_private_post'
                        ) as source:
                        with patch.object(w,'require_epoch_lease_before_private_post'
                            ) as lease:
                            with self.assertRaisesRegex(
                                w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                                api.request(path,method='POST',body=body)
                            http.assert_not_called()
                            source.assert_not_called()
                            lease.assert_not_called()

    def test_nested_batch_payload_cannot_clear_or_retarget_private_cells(self):
        """Known POST method is not enough: shape and exact columns matter."""
        cell={'userEnteredValue':{'stringValue':'safe'}}
        row={'values':[cell]}
        invalid=(
            {'updateCells':{'start':{'sheetId':1,'rowIndex':1,'columnIndex':0},
                            'rows':[row],'fields':'*'}},
            {'updateCells':{'start':{'sheetId':1,'rowIndex':1,'columnIndex':0},
                            'rows':[row],'fields':'userEnteredValue'}},
            {'updateCells':{'range':{'sheetId':1,'startRowIndex':0,
                            'endRowIndex':1,'startColumnIndex':0,
                            'endColumnIndex':2},'rows':[row],
                            'fields':'userEnteredValue'}},
            {'appendCells':{'sheetId':1,'rows':[row],'fields':'*'}},
            {'appendCells':{'sheetId':1,'rows':[{'values':[{
                'userEnteredValue':{'formulaValue':'=HYPERLINK("unsafe")'}}]}],
                'fields':'userEnteredValue'}},
            {'appendCells':{'sheetId':1,'rows':[row],
                            'fields':'userEnteredValue',
                            'insertDataOption':'OVERWRITE'}},
            {'appendCells':{'sheetId':'1','rows':[row],
                            'fields':'userEnteredValue'}},
            {'addNamedRange':{'namedRange':{'name':'FORGED_OWNER',
                'namedRangeId':'forged','range':{'sheetId':1,
                'startRowIndex':0,'endRowIndex':1,'startColumnIndex':0,
                'endColumnIndex':1}}}},
            {'updateCells':{'start':{'sheetId':1,'rowIndex':1,
                'columnIndex':7},'rows':[row],
                'fields':'userEnteredValue','extra':True}},
        )
        api=self._api()
        for request in invalid:
            with self.subTest(verb=next(iter(request)),body=request):
                with patch.object(w,'urlopen',
                                  side_effect=AssertionError('GOOGLE_MUTATION_SENT')) as http:
                    with patch.object(w,'require_source_lastmile_before_private_post'
                        ) as source,patch.object(
                        w,'require_epoch_lease_before_private_post'
                        ) as lease:
                        with self.assertRaisesRegex(
                                w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                            api.request(':batchUpdate',method='POST',
                                        body={'requests':[request]})
                        http.assert_not_called()
                        source.assert_not_called()
                        lease.assert_not_called()

    @staticmethod
    def canonical_eod_payload():
        asof='2026-11-23'
        scan=[asof,w.RUN_EVENT_LABELS['schedule'],'477','477','477',
              '0','TRUE','1',
              'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001',
              'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64+
              ';source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK']
        candidate=[asof+'|SYNA',asof,'SYNA','TEKNİK AL ADAYI',
                   '100','95','110','AÇIK • 0/15 SEANS','','','',
                   'KAYDEDİLDİ_BİLDİRİM_AYRI',
                   'GitHub private handoff; source_event=schedule; '
                   'IEX single exchange; RSI14=60.0 RVOL=1.7; run='+
                   scan[8]+'; NO_BROKER_NO_ORDERS']
        return {'requests':[{'addNamedRange':{'namedRange':w.epoch_marker(asof,1)}},
                            w.as_cells([scan],1),w.as_cells([candidate],2)]}

    def test_invalid_canonical_final_scan_is_denied_before_any_network(self):
        """A correctly shaped source row cannot fabricate 477 FINAL authority."""
        cases=(
            (1,'GitHub workflow_dispatch VERIFIED IEX EOD'),
            (2,'476'),(3,'476'),(4,'476'),(5,'1'),
            (6,'FALSE'),(7,'2'),
            (8,'https://github.com/other/repo/actions/runs/999001'),
            (8,'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/0'),
            (9,'scopeSHA=INVALID;algorithmSHA='+'b'*64+
                ';source_event=schedule;NO_ORDERS'),
            (9,'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64+
                ';source_event=workflow_dispatch;NO_ORDERS'),
            (9,'scopeSHA='+'a'*64+';algorithmSHA='+'b'*64+
                ';source_event=schedule;source_event=push;NO_ORDERS'),
        )
        api=self._api()
        for field,value in cases:
            with self.subTest(field=field,value=value[:35]):
                data=self.canonical_eod_payload()
                data['requests'][1]['appendCells']['rows'][0]['values'][field][
                    'userEnteredValue']['stringValue']=value
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    'UNAUTHORIZED_FINAL_REACHED_GOOGLE')) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                    ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(
                        w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',body=data)
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_canonical_candidate_epoch_set_must_match_final_al_count(self):
        """No false AL count, wrong key, or duplicate AL in the atomic batch."""
        original=self.canonical_eod_payload()
        duplicate=copy.deepcopy(original)
        duplicate['requests'][2]['appendCells']['rows'].append(
            copy.deepcopy(duplicate['requests'][2]['appendCells']['rows'][0]))
        duplicate['requests'][1]['appendCells']['rows'][0]['values'][7][
            'userEnteredValue']['stringValue']='2'
        wrong_key=copy.deepcopy(original)
        wrong_key['requests'][2]['appendCells']['rows'][0]['values'][0][
            'userEnteredValue']['stringValue']='2026-11-23|DIFFERENT'
        no_candidate=copy.deepcopy(original)
        no_candidate['requests'].pop()
        api=self._api()
        for label,data in (('duplicate',duplicate),('bad-key',wrong_key),
                           ('count-mismatch',no_candidate)):
            with self.subTest(case=label):
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    'UNAUTHORIZED_EPOCH_REACHED_GOOGLE')) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                    ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(
                        w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',body=data)
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_enforced_lastmile_final_source_url_must_match_actual_runner(self):
        """A canonical-looking EOD receipt cannot borrow another run ID."""
        api=self._api()
        for runner_id in ('999002','999010','0','000999001','',None):
            with self.subTest(runner_id=runner_id):
                runtime={'XRAY_PERSONAL477_SOURCE_LASTMILE_MODE':'ENFORCE_GET'}
                if runner_id is not None:
                    runtime['GITHUB_RUN_ID']=runner_id
                with patch.dict(w.os.environ,runtime,clear=True),patch.object(
                    w,'urlopen',side_effect=AssertionError(
                    'WRONG_RUN_REACHED_GOOGLE')) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                    ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(
                            w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',
                                    body=self.canonical_eod_payload())
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_enforced_lastmile_rejects_stale_final_even_with_current_run_url(self):
        """An old ASOF must never borrow a currently valid scheduled run ID.

        This covers the last HTTP mutation boundary, independent from the
        earlier snapshot validation. No GitHub or Google access is permitted.
        """
        import daily_job
        api=self._api()
        body=self.canonical_eod_payload()
        old="2026-11-20"
        body["requests"][0]["addNamedRange"]["namedRange"]=w.epoch_marker(old,1)
        body["requests"][1]["appendCells"]["rows"][0]["values"][0][
            "userEnteredValue"]["stringValue"]=old
        row=body["requests"][2]["appendCells"]["rows"][0]["values"]
        row[0]["userEnteredValue"]["stringValue"]=old+"|SYNA"
        row[1]["userEnteredValue"]["stringValue"]=old
        self.assertTrue(w._valid_private_batch_post(body))
        self.assertTrue(w._valid_private_batch_targets(body,api._post_scope))
        env={"XRAY_PERSONAL477_SOURCE_LASTMILE_MODE":"ENFORCE_GET",
             "GITHUB_RUN_ID":"999001"}
        with patch.dict(w.os.environ,env,clear=True),patch.object(
             daily_job,"current_completed_session",return_value="2026-11-23"
        ),patch.object(
             w,"urlopen",side_effect=AssertionError("STALE_EOD_REACHED_GOOGLE")
        ) as http,patch.object(
             w,"require_source_lastmile_before_private_post"
        ) as source,patch.object(
             w,"require_epoch_lease_before_private_post"
        ) as lease:
            with self.assertRaisesRegex(
                    w.HandoffBlocked,"GOOGLE_SHEETS_POST_SCOPE_INVALID"):
                api.request(":batchUpdate",method="POST",body=body)
            source.assert_not_called()
            lease.assert_not_called()
            http.assert_not_called()


    def test_enforced_lastmile_rejects_forged_scope_or_analysis_sha_before_io(self):
        """Even current ASOF + genuine run ID may not write forged policy/SHA.

        Before fix the generic transport admits both valid-looking SHA strings
        and reaches mocked Google POST. No private data or real POST here.
        """
        import daily_job
        import runner
        api=self._api()
        good=self.canonical_eod_payload()
        env={'XRAY_PERSONAL477_SOURCE_LASTMILE_MODE':'ENFORCE_GET',
             'GITHUB_RUN_ID':'999001'}
        for field in ('scope','analysis'):
            with self.subTest(field=field):
                body=copy.deepcopy(good)
                note=body['requests'][1]['appendCells']['rows'][0]['values'][9][
                    'userEnteredValue']['stringValue']
                if field=='scope':
                    note=note.replace('scopeSHA='+'a'*64, 'scopeSHA='+'f'*64)
                else:
                    note=note.replace('algorithmSHA='+'b'*64,
                                      'algorithmSHA='+'f'*64)
                body['requests'][1]['appendCells']['rows'][0]['values'][9][
                    'userEnteredValue']['stringValue']=note
                self.assertTrue(w._valid_private_batch_post(body))
                self.assertTrue(w._valid_private_batch_targets(body,api._post_scope))
                with patch.dict(w.os.environ,env,clear=True),patch.object(
                    daily_job,'current_completed_session',return_value='2026-11-23'
                ),patch.object(runner,'get_scope',return_value=SYMS
                ),patch.object(runner,'sha_symbols',return_value='a'*64
                ),patch.object(runner,'analysis_fingerprint',return_value='b'*64
                ),patch.object(
                    w,'urlopen',side_effect=AssertionError('FORGED_SHA_REACHED_GOOGLE')
                ) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post'
                ) as lease:
                    with self.assertRaisesRegex(
                            w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',body=body)
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_enforced_lastmile_canonical_sha_still_allows_existing_real_source(self):
        """Current code/policy fingerprints preserve authorized exact source."""
        import daily_job
        import runner
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self):return b'{"replies":[]}'
        api=self._api()
        env={'XRAY_PERSONAL477_SOURCE_LASTMILE_MODE':'ENFORCE_GET',
             'GITHUB_RUN_ID':'999001'}
        with patch.dict(w.os.environ,env,clear=True),patch.object(
            daily_job,'current_completed_session',return_value='2026-11-23'
        ),patch.object(runner,'get_scope',return_value=SYMS
        ),patch.object(runner,'sha_symbols',return_value='a'*64
        ),patch.object(runner,'analysis_fingerprint',return_value='b'*64
        ),patch.object(w,'urlopen',return_value=Reply()) as http,patch.object(
            w,'require_source_lastmile_before_private_post') as source,patch.object(
            w,'require_epoch_lease_before_private_post') as lease:
            self.assertEqual(api.request(':batchUpdate',method='POST',
                             body=self.canonical_eod_payload()),{'replies':[]})
            http.assert_called_once()
            source.assert_called_once()
            lease.assert_called_once()

    def test_enforced_lastmile_same_run_keeps_real_final_and_other_producers(self):
        """Correct runner + canonical source may still pass existing guards."""
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self):return b'{"replies":[]}'
        api=self._api()
        canonical=self.canonical_eod_payload()
        alert={'requests':[w.as_cells([['synthetic']*20],3)]}
        env={'XRAY_PERSONAL477_SOURCE_LASTMILE_MODE':'ENFORCE_GET',
             'GITHUB_RUN_ID':'999001'}
        import daily_job
        with patch.dict(w.os.environ,env,clear=True),patch.object(
             daily_job,'current_completed_session',return_value='2026-11-23'
        ),patch.object(runner,'sha_symbols',return_value='a'*64
        ),patch.object(runner,'analysis_fingerprint',return_value='b'*64
        ),patch.object(
             w,'urlopen',return_value=Reply()) as http,patch.object(
             w,'require_source_lastmile_before_private_post') as source,patch.object(
             w,'require_epoch_lease_before_private_post') as lease:
            for body in (canonical,alert):
                self.assertEqual(api.request(':batchUpdate',method='POST',
                                             body=body),{'replies':[]})
            self.assertEqual(http.call_count,2)
            self.assertEqual(source.call_count,2)
            self.assertEqual(lease.call_count,2)

    def test_candidate_notes_reject_conflicting_or_forged_origin(self):
        """An exact source marker cannot bless a contradictory AL note."""
        raw=self.canonical_eod_payload()
        base=(raw['requests'][2]['appendCells']['rows'][0]['values'][12]
              ['userEnteredValue']['stringValue'])
        url='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001'
        bad=(
            base.replace('source_event=schedule;',
                         'source_event=workflow_dispatch; source_event=schedule;'),
            base.replace('source_event=schedule;',
                         'source_event=schedule; source_event=push;'),
            base.replace('run='+url+';', 'run='+url+'; run='+
                         'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999002;'),
            base.replace('run='+url+';', 'run='+url+'-FORGED;'),
            base+'; ORDER_EXECUTED=true',
            base.replace('RSI14=60.0', 'RSI14=nan'),
            base.replace('RSI14=60.0', 'RSI14=110.0'),
            base.replace('RVOL=1.7', 'RVOL=-1'),
            base.replace('IEX single exchange; ', ''),
            base.replace('GitHub private handoff; ', ''),
        )
        api=self._api()
        for item in bad:
            with self.subTest(note=item[:95]):
                candidate=copy.deepcopy(raw)
                candidate['requests'][2]['appendCells']['rows'][0]['values'][12][
                    'userEnteredValue']['stringValue']=item
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    'FORGED_AL_NOTE_REACHED_GOOGLE')) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                    ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(
                        w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',body=candidate)
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_candidate_levels_reject_nan_unsafe_stop_and_non_2r(self):
        """Literal cells must respect close > stop > 0 and the 2R target."""
        cases=(
            (4,'nan'),(4,'inf'),(4,'0'),
            (5,'nan'),(5,'101'),(5,'0'),
            (6,'nan'),(6,'99'),(6,'105'),
            (4,'not-a-price'),(5,'100'),(6,'100'),
        )
        api=self._api()
        for field,value in cases:
            with self.subTest(field=field,value=value):
                body=self.canonical_eod_payload()
                body['requests'][2]['appendCells']['rows'][0]['values'][field][
                    'userEnteredValue']['stringValue']=value
                with patch.object(w,'urlopen',side_effect=AssertionError(
                    'MALFORMED_AL_LEVEL_REACHED_GOOGLE')) as http,patch.object(
                    w,'require_source_lastmile_before_private_post'
                    ) as source,patch.object(
                    w,'require_epoch_lease_before_private_post') as lease:
                    with self.assertRaisesRegex(
                        w.HandoffBlocked,'GOOGLE_SHEETS_POST_SCOPE_INVALID'):
                        api.request(':batchUpdate',method='POST',body=body)
                    http.assert_not_called()
                    source.assert_not_called()
                    lease.assert_not_called()

    def test_candidate_three_decimal_rounded_2r_remains_valid(self):
        """False rejection of a legitimate 0.001 rounding delta is a bug."""
        class Reply:
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self): return b'{"replies":[]}'
        api=self._api()
        body=self.canonical_eod_payload()
        levels=body['requests'][2]['appendCells']['rows'][0]['values']
        for idx,value in ((4,'100,001'),(5,'95,002'),(6,'109,998')):
            levels[idx]['userEnteredValue']['stringValue']=value
        with patch.object(w,'urlopen',return_value=Reply()) as http,patch.object(
            w,'require_source_lastmile_before_private_post') as source,patch.object(
            w,'require_epoch_lease_before_private_post') as lease:
            self.assertEqual(api.request(':batchUpdate',method='POST',body=body),
                             {'replies':[]})
            http.assert_called_once()
            source.assert_called_once()
            lease.assert_called_once()

    def test_existing_authorized_batchupdate_stays_compatible(self):
        """Legitimate source/episode/PANEL/NEON verbs stay permitted."""
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self):return b'{"replies":[]}'
        api=self._api()
        cell=lambda value:{'userEnteredValue':{'stringValue':value}}
        eod=self.canonical_eod_payload()
        # Also use the REAL 477-scoped handoff->plan->batch serializer,
        # not only a handcrafted valid shape, to guard production EOD.
        real_plan=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                         [list(w.SCAN_HEADER)],RUN)
        real_eod=w.payload_from_plan(real_plan,{'scan':1,'candidate':2})
        no_al=copy.deepcopy(eod)
        no_al['requests'].pop()
        no_al['requests'][1]['appendCells']['rows'][0]['values'][7][
            'userEnteredValue']['stringValue']='0'
        allowed_bodies=(
            real_eod,
            eod,
            no_al,
            {'requests':[w.as_cells([['N/A']*23 for _ in range(477)],477300001)]},
            {'requests':[{'updateCells':{
                'start':{'sheetId':2,'rowIndex':2,'columnIndex':7},
                'rows':[{'values':[cell('test') for _ in range(4)]}],
                'fields':'userEnteredValue'}}]},
            {'requests':[{'updateCells':{
                'range':{'sheetId':1146954931,'startRowIndex':8,
                         'endRowIndex':9,'startColumnIndex':1,'endColumnIndex':3},
                'rows':[{'values':[cell('date'),cell('receipt')]}],
                'fields':'userEnteredValue'}}]},
        )
        with patch.object(w,'urlopen',return_value=Reply()) as http:
            with patch.object(w,'require_source_lastmile_before_private_post'
                ) as source:
                with patch.object(w,'require_epoch_lease_before_private_post'
                    ) as lease:
                    for body in allowed_bodies:
                        receipt=api.request(':batchUpdate',method='POST',body=body)
                        self.assertEqual(receipt,{'replies':[]})
                    self.assertEqual(http.call_count,len(allowed_bodies))
                    self.assertEqual(source.call_count,len(allowed_bodies))
                    self.assertEqual(lease.call_count,len(allowed_bodies))

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
                                body={'requests': [w.as_cells([['synthetic']*20],3)]})
        self.assertEqual(opener.call_count, 1)
        sleep.assert_not_called()

    def test_public_report_contains_categorical_code_not_private_error(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'synthetic.json'
            file.write_text('{}', encoding='utf-8')
            env = {'GITHUB_RUN_ID': '77', 'GITHUB_EVENT_NAME': 'schedule',
                   'GITHUB_RUN_ATTEMPT':'1',
                   'GITHUB_REPOSITORY':w.EXPECTED_EOD_REPOSITORY,
                   'GITHUB_REF':'refs/heads/main',
                   'GITHUB_WORKFLOW_REF':w.EXPECTED_EOD_WORKFLOW_REF,
                   'GITHUB_SHA':'a'*40,
                   'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON': 'PRIVATE_TEST_TOKEN_MUST_NOT_APPEAR'}
            # This test isolates public exception sanitization, not ASOF freshness.
            with patch.dict(w.os.environ, env, clear=True), \
                 patch.object(w,'require_current_natural_eod_snapshot',return_value=True):
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
                   'GITHUB_RUN_ATTEMPT':'1',
                   'GITHUB_REPOSITORY':w.EXPECTED_EOD_REPOSITORY,
                   'GITHUB_REF':'refs/heads/main',
                   'GITHUB_WORKFLOW_REF':w.EXPECTED_EOD_WORKFLOW_REF,
                   'GITHUB_SHA':'a'*40,
                   'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON': 'SENSITIVE_UNIT_TEST'}
            # This test isolates public exception sanitization, not ASOF freshness.
            with patch.dict(w.os.environ, env, clear=True), \
                 patch.object(w,'require_current_natural_eod_snapshot',return_value=True):
                with patch.object(w, 'SheetApi', return_value=object()):
                    with patch.object(w, 'synchronize',
                                      side_effect=ValueError('SENSITIVE_UNIT_TEST-private-url')):
                        with patch('builtins.print') as output:
                            self.assertEqual(w.main(['--snapshot', str(file)]), 3)
            text = output.call_args.args[0]
            receipt = w.json.loads(text)
            self.assertEqual(receipt['reason_code'], 'UNCLASSIFIED')
            self.assertNotIn('SENSITIVE_UNIT_TEST', text)




class AtomicSheetWriteLeaseFence(unittest.TestCase):
    """Injectable offline tag owner. No actual Google or GitHub mutation."""

    def setUp(self):
        import test_epoch_lease as cases
        self.cases=cases
        self.git=cases.MockGit()
        cases.claim(cases.natural(),self.git)
        self.git.calls.clear()

    def runtime(self,run="890123"):
        return {**self.cases.env(run),
                "GITHUB_TOKEN":"fake-offline-gh-token",
                "XRAY_PERSONAL477_EPOCH_LEASE_MODE":"ENFORCE"}

    def test_current_owner_can_pass_read_only_fence(self):
        out=w.require_epoch_lease_before_private_post(
            self.runtime(),transport=self.git,now=self.cases.NOW,
            completed_session=lambda _:self.cases.ASOF)
        self.assertEqual(out["state"],"LEASE_OWNER_READBACK_ONLY")
        self.assertEqual(out["run_id"],890123)
        self.assertFalse(any(m=="POST" for m,_,_ in self.git.calls))

    def test_another_runner_cannot_borrow_one_tag(self):
        with self.assertRaisesRegex(
                w.HandoffBlocked,"EPOCH_LEASE_CONSUMER_UNVERIFIED"):
            w.require_epoch_lease_before_private_post(
                self.runtime("890124"),transport=self.git,now=self.cases.NOW,
                completed_session=lambda _:self.cases.ASOF)
        self.assertFalse(any(m=="POST" for m,_,_ in self.git.calls))

    def test_disabled_tag_protection_denied(self):
        self.git.protection="disabled"
        with self.assertRaisesRegex(
                w.HandoffBlocked,"EPOCH_LEASE_CONSUMER_UNVERIFIED"):
            w.require_epoch_lease_before_private_post(
                self.runtime(),transport=self.git,now=self.cases.NOW,
                completed_session=lambda _:self.cases.ASOF)

    def test_unknown_mode_missing_token_and_wrong_event_fail_closed(self):
        variants=(
            ({"XRAY_PERSONAL477_EPOCH_LEASE_MODE":"BAD"},
             "EPOCH_LEASE_MODE_UNRECOGNIZED"),
            ({**self.runtime(),"GITHUB_TOKEN":""},
             "EPOCH_LEASE_TOKEN_MISSING"),
            ({**self.runtime(),"GITHUB_EVENT_NAME":"workflow_dispatch"},
             "NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED"),
        )
        for runtime,reason in variants:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(w.HandoffBlocked,reason):
                    w.require_epoch_lease_before_private_post(
                        runtime,transport=self.git,now=self.cases.NOW,
                        completed_session=lambda _:self.cases.ASOF)

    def test_enforced_batch_post_rejected_before_google_network(self):
        api=object.__new__(w.SheetApi)
        api.base="https://sheets.googleapis.com/v4/spreadsheets/OFFLINE"
        api.token="OFFLINE"
        api._post_scope={'scan':1,'candidate':2,'alerts':3,'panel':4}
        with patch.dict(os.environ,self.runtime(),clear=True):
            with patch.object(w,"require_epoch_lease_before_private_post",
                side_effect=w.HandoffBlocked("EPOCH_LEASE_CONSUMER_UNVERIFIED")
            ) as guard,patch.object(w,"urlopen",
                side_effect=AssertionError("GOOGLE_POST_SENT")
            ) as net:
                with self.assertRaisesRegex(w.HandoffBlocked,
                         "EPOCH_LEASE_CONSUMER_UNVERIFIED"):
                    api.request(":batchUpdate",method="POST",body={"requests":[w.as_cells([["OFFLINE"]*20],3)]})
                guard.assert_called_once()
                net.assert_not_called()

    def test_two_natural_writers_only_one_can_reach_fake_google_post(self):
        """End-to-end offline race: one immutable tag and one POST at most."""
        import test_epoch_lease as cases
        import epoch_lease as lease
        import daily_job
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace

        git=cases.MockGit(rendezvous=2)
        def try_claim(number):
            try:
                cases.claim(cases.natural(number),git)
                return number
            except lease.LeaseHold:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcome=list(pool.map(try_claim,("890123","890124")))
        winners=[x for x in outcome if x is not None]
        self.assertEqual(len(winners),1,outcome)
        self.assertEqual(len(git.refs),1)
        self.assertEqual(len(git.tags),2)
        losers=[x for x in ("890123","890124") if x not in winners]
        self.assertEqual(len(losers),1)
        git.calls.clear()

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self,*_):
                return False
            def read(self):
                return b'{"offline":true}'

        api=object.__new__(w.SheetApi)
        api.base="https://sheets.googleapis.com/v4/spreadsheets/OFFLINE"
        api.token="offline-google-token"
        api._post_scope={'scan':1,'candidate':2,'alerts':3,'panel':4}
        with patch.object(lease,"github_transport",return_value=git):
            with patch.object(w,"datetime",
                    SimpleNamespace(now=lambda _:cases.NOW)):
                with patch.object(daily_job,"current_completed_session",
                                  return_value=cases.ASOF):
                    with patch.object(w,"urlopen",return_value=FakeResponse()
                    ) as google:
                        for candidate in losers+winners:
                            runtime=self.runtime(candidate)
                            with patch.dict(os.environ,runtime,clear=True):
                                if candidate in losers:
                                    with self.assertRaisesRegex(
                                        w.HandoffBlocked,
                                        "EPOCH_LEASE_CONSUMER_UNVERIFIED"):
                                        api.request(":batchUpdate",method="POST",
                                                    body={"requests":[w.as_cells([["OFFLINE"]*20],3)]})
                                else:
                                    result=api.request(":batchUpdate",method="POST",
                                                       body={"requests":[w.as_cells([["OFFLINE"]*20],3)]})
                                    self.assertEqual(result,{"offline":True})
                        self.assertEqual(google.call_count,1)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_live_owner_revocation_blocks_before_fake_google_post(self):
        import epoch_lease as lease
        import daily_job
        from types import SimpleNamespace
        self.git.protection="disabled"
        api=object.__new__(w.SheetApi)
        api.base="https://sheets.googleapis.com/v4/spreadsheets/OFFLINE"
        api.token="offline-google-token"
        api._post_scope={'scan':1,'candidate':2,'alerts':3,'panel':4}
        with patch.dict(os.environ,self.runtime(),clear=True):
            with patch.object(lease,"github_transport",return_value=self.git):
                with patch.object(w,"datetime",
                        SimpleNamespace(now=lambda _:self.cases.NOW)):
                    with patch.object(daily_job,"current_completed_session",
                                      return_value=self.cases.ASOF):
                        with patch.object(w,"urlopen",
                             side_effect=AssertionError("NO_GOOGLE_POST")
                        ) as google:
                            with self.assertRaisesRegex(
                                    w.HandoffBlocked,
                                    "EPOCH_LEASE_CONSUMER_UNVERIFIED"):
                                api.request(":batchUpdate",method="POST",
                                            body={"requests":[w.as_cells([["OFFLINE"]*20],3)]})
                            google.assert_not_called()

    def test_default_off_does_not_query_github_or_google(self):
        out=w.require_epoch_lease_before_private_post(
            self.cases.env(),transport=self.git,now=self.cases.NOW,
            completed_session=lambda _:self.cases.ASOF)
        self.assertEqual(out["state"],"LEASE_ENFORCEMENT_NOT_ACTIVATED")
        self.assertEqual(self.git.calls,[])



class GoogleSheetsNativeEpochCASAcceptance(unittest.TestCase):
    """No real Sheets I/O: production CAS contract from 5 live temp-sheet races."""

    def epoch(self):
        p=w.plan(snapshot(), [list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)], RUN, run_event="schedule")
        ids={"scan":432001002,"candidate":432001003}
        return p,ids

    def test_new_canonical_epoch_claim_is_in_same_atomic_batch_as_all_rows(self):
        p,ids=self.epoch()
        requests=w.payload_from_plan(p,ids)["requests"]
        self.assertEqual(len(requests),3)
        named=requests[0]["addNamedRange"]["namedRange"]
        self.assertEqual(named["name"],"XRAY_P477_EOD_EPOCH_20261026")
        self.assertEqual(named["namedRangeId"],"xray_p477_eod_epoch_20261026")
        self.assertEqual(named["range"],{
            "sheetId":ids["scan"],"startRowIndex":0,"endRowIndex":1,
            "startColumnIndex":0,"endColumnIndex":1})
        self.assertEqual([x["appendCells"]["sheetId"] for x in requests[1:]],
                         [ids["scan"],ids["candidate"]])

    def test_same_run_idempotent_reuse_never_attempts_second_epoch_insert(self):
        api=FakeApi()
        w.synchronize(snapshot(),RUN,api,run_event="schedule")
        p=w.plan(snapshot(),api.candidates,api.scans,RUN,run_event="schedule")
        self.assertEqual(p["scan_rows"],[])
        self.assertEqual(w.payload_from_plan(p,{"scan":1,"candidate":2})["requests"],[])

    def test_bad_marker_post_receipt_is_never_readback_pass(self):
        from unittest.mock import Mock
        p,ids=self.epoch()
        api=object.__new__(w.SheetApi)
        api.sheet_ids=ids
        api.request=Mock(return_value={"replies":[{}, {}, {}]})
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    "EPOCH_CAS_POST_RECEIPT_UNVERIFIED"):
            api.apply(p)
        self.assertEqual(api.request.call_count,1)
        self.assertEqual(api.request.call_args.args[0],":batchUpdate")
        self.assertEqual(api.request.call_args.kwargs["method"],"POST")

    def test_missing_marker_on_independent_google_get_blocks_acceptance(self):
        from unittest.mock import Mock
        p,ids=self.epoch()
        first=w.payload_from_plan(p,ids)["requests"][0]["addNamedRange"]["namedRange"]
        response={"replies":[{"addNamedRange":{"namedRange":first}}, {}, {}]}
        api=object.__new__(w.SheetApi)
        api.sheet_ids=ids
        api.request=Mock(side_effect=[response,{"namedRanges":[]}])
        with self.assertRaisesRegex(w.HandoffBlocked,
                                    "EPOCH_CAS_INDEPENDENT_GET_UNVERIFIED"):
            api.apply(p)
        self.assertEqual(api.request.call_count,2)
        self.assertIn("namedRanges",api.request.call_args.args[0])
        self.assertEqual(api.request.call_args.kwargs.get("method","GET"),"GET")

    def test_exact_named_range_and_batch_receipt_pass_with_independent_get(self):
        from unittest.mock import Mock
        p,ids=self.epoch()
        marker=w.payload_from_plan(p,ids)["requests"][0]["addNamedRange"]["namedRange"]
        api=object.__new__(w.SheetApi)
        api.sheet_ids=ids
        api.request=Mock(side_effect=[
            {"replies":[{"addNamedRange":{"namedRange":marker}}, {}, {}]},
            {"namedRanges":[dict(marker)]},
        ])
        self.assertIsNone(api.apply(p))
        self.assertEqual(api.request.call_count,2)


class CanonicalSheetPostReadOnlyNaturalFence(unittest.TestCase):
    """P0: source may change AFTER offline-guard and BEFORE Google POST."""

    def runtime(self, run="890123"):
        import test_epoch_lease as cases
        return {**cases.env(run),
                "GITHUB_TOKEN":"offline-fake-readonly-token",
                "XRAY_PERSONAL477_SOURCE_LASTMILE_MODE":"ENFORCE_GET"}

    def test_readonly_gate_checks_real_run_and_exact_unique_schedule_page(self):
        import test_epoch_lease as cases
        git=cases.MockGit()
        output=w.require_source_lastmile_before_private_post(
            self.runtime(),transport=git,now=cases.NOW,
            completed_session=lambda _:cases.ASOF)
        self.assertEqual(output["status"],
                         "NATURAL_RUN_GITHUB_READ_ONLY_VERIFIED")
        self.assertEqual(output["run_id"],890123)
        self.assertEqual(output["asof_et"],cases.ASOF)
        self.assertEqual([m for m,p,b in git.calls],["GET","GET"])
        self.assertFalse(output["ab_release_authorized"])

    def test_late_competing_schedule_denies_writer_before_google(self):
        import test_epoch_lease as cases
        import natural_run_readonly_probe as probe
        git=cases.MockGit()
        def duplicated(method,path,body=None):
            response=git(method,path,body)
            if method=="GET" and path.startswith("/actions/workflows/"):
                second={**response["workflow_runs"][0],"id":890124}
                return {"total_count":2,
                        "workflow_runs":[*response["workflow_runs"],second]}
            return response
        with self.assertRaisesRegex(
                w.HandoffBlocked,"SOURCE_LASTMILE_PROVENANCE_UNVERIFIED"):
            w.require_source_lastmile_before_private_post(
                self.runtime(),transport=duplicated,now=cases.NOW,
                completed_session=lambda _:cases.ASOF)
        self.assertEqual(len(git.calls),2)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_missing_token_and_wrong_origin_fail_closed_without_provider(self):
        import test_epoch_lease as cases
        git=cases.MockGit()
        for overrides,reason in (
            ({"GITHUB_TOKEN":""},"SOURCE_LASTMILE_TOKEN_MISSING"),
            ({"GITHUB_EVENT_NAME":"workflow_dispatch"},
             "NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED"),
            ({"GITHUB_RUN_ATTEMPT":"2"},
             "NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED"),
            ({"XRAY_PERSONAL477_SOURCE_LASTMILE_MODE":"BROKEN"},
             "SOURCE_LASTMILE_MODE_UNRECOGNIZED"),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(w.HandoffBlocked,reason):
                    w.require_source_lastmile_before_private_post(
                        {**self.runtime(),**overrides},transport=git,
                        now=cases.NOW,
                        completed_session=lambda _:cases.ASOF)
        self.assertEqual(git.calls,[])

    def test_actual_sheet_post_lastmile_refusal_prevents_google_network(self):
        api=object.__new__(w.SheetApi)
        api.base="https://sheets.googleapis.com/v4/spreadsheets/SYNTHETIC"
        api.token="synthetic"
        api._post_scope={'scan':1,'candidate':2,'alerts':3,'panel':4}
        with patch.dict(os.environ,self.runtime(),clear=True):
            with patch.object(
                w,"require_source_lastmile_before_private_post",
                side_effect=w.HandoffBlocked("SOURCE_LASTMILE_PROVENANCE_UNVERIFIED")
            ) as gh, patch.object(w,"urlopen",
                                  side_effect=AssertionError("GOOGLE_WRITTEN")
            ) as google:
                with self.assertRaisesRegex(
                    w.HandoffBlocked,"SOURCE_LASTMILE_PROVENANCE_UNVERIFIED"):
                    api.request(":batchUpdate",method="POST",body={"requests":[w.as_cells([["OFFLINE"]*20],3)]})
                gh.assert_called_once()
                google.assert_not_called()

    def test_gate_off_in_local_legacy_does_not_authorize_delivery(self):
        import test_epoch_lease as cases
        git=cases.MockGit()
        output=w.require_source_lastmile_before_private_post(
            cases.env(),transport=git,now=cases.NOW,
            completed_session=lambda _:cases.ASOF)
        self.assertEqual(output["status"],"LASTMILE_MODE_OFF_NOT_AUTHORITY")
        self.assertFalse(output["ab_release_authorized"])
        self.assertEqual(git.calls,[])

    def test_every_production_sheet_writer_job_has_readonly_run_credential(self):
        workflow=(Path(__file__).resolve().parent.parent/
            ".github/workflows/xray-personal-477-eod.yml").read_text("utf8")
        expected=(
            ("daily-private-scan","private-sheets-auth-preflight"),
            ("private-episode-followups","guardian-acceptance"),
            ("guardian-acceptance","daily-private-score-acceptance"),
            ("daily-private-score-acceptance",None),
        )
        for job,nxt in expected:
            with self.subTest(job=job):
                section=workflow.split("\n  "+job+":",1)[1]
                if nxt:
                    section=section.split("\n  "+nxt+":",1)[0]
                self.assertIn("XRAY_PERSONAL477_SOURCE_LASTMILE_MODE: ENFORCE_GET",section)
                self.assertIn("GITHUB_TOKEN: ${{ github.token }}",section)
        self.assertIn("  actions: read\n",workflow)
        guardian=workflow.split("\n  guardian-acceptance:",1)[1].split(
            "\n  daily-private-score-acceptance:",1)[0]
        self.assertIn("      actions: read",guardian)
        self.assertNotIn("contents: write",workflow)

if __name__=='__main__':
    unittest.main()
