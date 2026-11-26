"""Offline tests for NASDAQ PANEL reconciliation. Synthetic rows only."""
import copy
import unittest
from pathlib import Path
import runner
import panel_reconciler as p
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER, HandoffBlocked

DAY='2026-10-27'
URL='https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001'


class FakeApi:
    def __init__(self):
        self.sheet_ids={'candidate':22,'scan':33,'alerts':44}
        self.panel=[['XRAY — KİŞİSEL NASDAQ START / FINAL']]
        while len(self.panel)<16:
            self.panel.append([''])
        self.panel[8]=['Son doğrulanmış tarama seansı','2026-10-26','stale']
        self.panel[9]=['GitHub çalışma kanıtı','https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/123','old']
        self.panel[10]=['GÜNCELLİK NOTU','2026-10-26','stale']
        self.panel[12]=['START','BAŞARILI','26 Ekim']
        self.panel[13]=['FINAL motoru','BAŞARILI','26 Ekim']
        self.panel[15]=['Sinyal geçmişi','0 TEKNİK KAYIT','old']
        self.candidates=[list(CANDIDATE_HEADER),
                         [DAY+'|AAAA',DAY,'AAAA','TEKNİK AL ADAYI',
                          '100','95','110','AÇIK • 0/15 SEANS','','','','','']]
        scope=runner.get_scope(
            watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),
            asof=DAY)
        proof=('scopeSHA='+runner.sha_symbols(scope)+
               ';algorithmSHA='+runner.analysis_fingerprint()+
               ';source_event=schedule;NO_ORDERS; NOT_DEVICE_ACK')
        self.scans=[list(SCAN_HEADER),
                    [DAY,'GitHub schedule VERIFIED IEX EOD','477','477',
                     '477','0','TRUE','1',URL,proof]]
        self.writes=0
        self.mutate_second=False
        self.reads=0
        self.corrupt=False

    def check_metadata(self):
        return True

    def read(self,title,last):
        self.reads+=1
        if self.mutate_second and self.reads==4:
            self.candidates.append(['unexpected'])
        if title=='PANEL':
            return copy.deepcopy(self.panel)
        if title=='ADAY_GECMISI':
            return copy.deepcopy(self.candidates)
        if title=='TARAMA_KAYITLARI':
            return copy.deepcopy(self.scans)
        raise AssertionError('unexpected private read')

    def request(self,path,method='GET',body=None):
        if path.startswith('?fields='):
            return {'properties':{'timeZone':'Europe/Istanbul'},
                    'sheets':[{'properties':{'title':'PANEL','sheetId':11}}]}
        self.writes+=1
        assert path==':batchUpdate' and method=='POST'
        for request in body['requests']:
            obj=request['updateCells']
            assert obj['range']['sheetId']==11
            assert obj['fields']=='userEnteredValue'
            assert obj['range']['startColumnIndex']==1
            r=obj['range']['startRowIndex']
            vals=[v['userEnteredValue']['stringValue']
                  for v in obj['rows'][0]['values']]
            assert len(vals)==2
            self.panel[r]=self.panel[r][:1]+vals
        if self.corrupt:
            self.panel[8][1]='bad'
        return {}


class PanelReconcileTests(unittest.TestCase):
    def test_updates_only_three_derived_panel_rows(self):
        api=FakeApi()
        original_candidates=copy.deepcopy(api.candidates)
        original_scans=copy.deepcopy(api.scans)
        got=p.synchronize(api)
        self.assertEqual(got['status'],'PANEL_READBACK_PASS')
        self.assertTrue(got['changed'])
        self.assertEqual(api.writes,1)
        self.assertEqual(api.panel[8][1],DAY)
        self.assertEqual(api.panel[9][1],URL)
        self.assertIn('1 gözlem: 1 açık, 0 kapalı',api.panel[10][1])
        self.assertIn(DAY,api.panel[12][2])
        self.assertIn(DAY,api.panel[13][2])
        self.assertEqual(api.panel[12][1],
                         'KİŞİSEL ARAŞTIRMA START AKTİF · CHATGPT TESLİMİ AYRI')
        self.assertEqual(api.panel[13][1],
                         'IEX TARAMA PASS · EOD KABULÜ AYRI · CANONICAL NO-GO')
        self.assertIn('ChatGPT',api.panel[12][2])
        self.assertIn('ayrı kabul',api.panel[13][2])
        self.assertEqual(api.panel[15][1],'1 TEKNİK KAYIT')
        self.assertEqual(api.candidates,original_candidates)
        self.assertEqual(api.scans,original_scans)
        self.assertFalse(got['device_ack'])

    def test_chatgpt_only_acceptance_omits_obsolete_device_ack_gate(self):
        api=FakeApi()
        plan=p.plan(api.panel,api.candidates,api.scans)
        texts=' | '.join(' '.join(plan['values'][r])
                         for r in (9,10,12,13))
        self.assertIn('ChatGPT',texts)
        self.assertNotIn('iPhone',texts)
        self.assertNotIn('PUSH',texts)
        self.assertNotIn('ACK UNKNOWN',texts)
        self.assertNotIn('cihaz ACK',texts)
        self.assertIn('ayrı kabul',texts)
    def test_pre_guardian_panel_never_claims_full_eod_pass(self):
        api=FakeApi()
        plan=p.plan(api.panel,api.candidates,api.scans)
        self.assertTrue(plan['values'][10][0].startswith('Son doğrulanmış tarama '))
        self.assertNotIn('Son FINAL',plan['values'][10][0])
        self.assertIn('EOD KABULÜ AYRI',plan['values'][13][0])
        self.assertNotIn('EOD PASS',plan['values'][13][0])
        self.assertIn('Guardian ve tam EOD',plan['values'][13][1])

    def test_idempotent_replay_has_no_second_write(self):
        api=FakeApi()
        p.synchronize(api)
        again=p.synchronize(api)
        self.assertFalse(again['changed'])
        self.assertEqual(api.writes,1)

    def test_closed_episodes_are_counted_without_changing_their_levels(self):
        api=FakeApi()
        api.candidates[1][7]='KAPALI • STOP_TOUCHED • 1/15 SEANS'
        api.candidates[1][8]=DAY
        api.candidates[1][9]='STOP_TOUCHED'
        original=copy.deepcopy(api.candidates)
        p.synchronize(api)
        self.assertIn('1 gözlem: 0 açık, 1 kapalı',api.panel[10][1])
        self.assertEqual(api.candidates,original)

    def test_unknown_status_blocks_all_dashboard_writes(self):
        api=FakeApi()
        api.candidates[1][7]='FILLED_REAL_TRADE'
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_UNKNOWN_LIFECYCLE_STATUS'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_no_477_final_never_writes(self):
        api=FakeApi()
        api.scans[1][4]='476'
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_LATEST_NOT_477_FINAL'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_old_or_bogus_run_link_fails_closed(self):
        api=FakeApi()
        api.scans[1][8]='https://untrusted.example/123'
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_UNTRUSTED_PROVENANCE_LINK'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_non_natural_source_must_not_repair_panel(self):
        api=FakeApi()
        api.scans[1][1]='GitHub workflow_dispatch VERIFIED IEX EOD'
        api.scans[1][9]='source_event=workflow_dispatch'
        with self.assertRaisesRegex(HandoffBlocked,
                                    'PANEL_NON_NATURAL_EOD_SOURCE'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_duplicated_natural_origin_is_not_exact_receipt(self):
        api=FakeApi()
        api.scans[1][1]='GitHub schedule VERIFIED IEX EOD'
        api.scans[1][9]='source_event=schedule;source_event=workflow_dispatch'
        with self.assertRaisesRegex(HandoffBlocked,
                                    'PANEL_NON_NATURAL_EOD_SOURCE'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_wrong_private_source_sha_never_writes_panel(self):
        api=FakeApi()
        note=api.scans[1][9]
        sha=note.split('scopeSHA=')[1][:64]
        api.scans[1][9]=note.replace('scopeSHA='+sha,'scopeSHA='+'f'*64,1)
        with self.assertRaisesRegex(HandoffBlocked,
                                    'PANEL_SOURCE_SHA_CONFLICT'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_unmatched_new_candidate_count_never_writes(self):
        api=FakeApi()
        api.scans[1][7]='0'
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_NEW_EPISODE_COUNT_MISMATCH'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_duplicate_episode_id_blocks(self):
        api=FakeApi()
        api.candidates.append(copy.deepcopy(api.candidates[1]))
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_DUPLICATE_EPISODE'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_modified_source_between_reads_fails_before_update(self):
        api=FakeApi()
        api.mutate_second=True
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_CONCURRENT_SOURCE_CHANGE'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_readback_corruption_is_detected(self):
        api=FakeApi()
        api.corrupt=True
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_READBACK_MISMATCH'):
            p.synchronize(api)
        self.assertEqual(api.writes,1)

    def test_panel_title_drift_fails_before_mutation(self):
        api=FakeApi()
        api.panel[8][0]='wrong'
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_LABEL_DRIFT'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)

    def test_never_uses_incomplete_future_scan_as_latest(self):
        api=FakeApi()
        api.scans.append(['2026-10-28','EOD','477','477','476','1','FALSE','0',URL,'bad'])
        with self.assertRaisesRegex(HandoffBlocked,'PANEL_LATEST_NOT_477_FINAL'):
            p.synchronize(api)
        self.assertEqual(api.writes,0)



class PanelEntrypointNaturalEODSourceTests(unittest.TestCase):
    def env(self,event="schedule"):
        from private_sheet_writer import EXPECTED_EOD_REPOSITORY, EXPECTED_EOD_WORKFLOW_REF
        return {"GITHUB_EVENT_NAME":event,
                "GITHUB_REPOSITORY":EXPECTED_EOD_REPOSITORY,
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_RUN_ID":"999001",
                "GITHUB_SHA":"a"*40,
                "GITHUB_WORKFLOW_REF":EXPECTED_EOD_WORKFLOW_REF,
                "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"OFFLINE_SYNTHETIC"}

    def test_foreign_workflow_cannot_open_panel_sheet(self):
        import os,io,contextlib
        from unittest.mock import patch
        for event in ("workflow_dispatch","push"):
            with self.subTest(event=event):
                with patch.dict(os.environ,self.env(event),clear=True):
                    with patch.object(p,"SheetApi",
                        side_effect=AssertionError("UNAUTHORIZED_PANEL_GOOGLE_STARTED")
                    ) as client,contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(p.main(),3)
                client.assert_not_called()

    def test_no_current_session_cannot_open_panel_sheet(self):
        import os,io,contextlib
        from unittest.mock import patch
        with patch.dict(os.environ,self.env(),clear=True):
            with patch.object(p,"current_completed_session",return_value=None):
                with patch.object(p,"SheetApi",
                    side_effect=AssertionError("STALE_PANEL_GOOGLE_STARTED")
                ) as client,contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(p.main(),3)
        client.assert_not_called()

    def test_current_natural_panel_requires_matching_scan_before_write(self):
        import os,io,contextlib
        from unittest.mock import patch
        api=FakeApi()
        api.scans[1][0]="2026-10-27"
        with patch.dict(os.environ,self.env(),clear=True):
            with patch.object(p,"current_completed_session",return_value="2026-10-28"):
                with patch.object(p,"SheetApi",return_value=api):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(p.main(),3)
        self.assertEqual(api.writes,0)


if __name__=='__main__':
    unittest.main()
