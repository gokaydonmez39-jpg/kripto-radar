"""Offline tests for NASDAQ PANEL reconciliation. Synthetic rows only."""
import copy
import unittest
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
        self.panel[15]=['Sinyal geçmişi','0 TEKNİK KAYIT','old']
        self.candidates=[list(CANDIDATE_HEADER),
                         [DAY+'|AAAA',DAY,'AAAA','TEKNİK AL ADAYI',
                          '100','95','110','AÇIK • 0/15 SEANS','','','','','']]
        self.scans=[list(SCAN_HEADER),
                    [DAY,'GitHub auto VERIFIED IEX EOD','477','477',
                     '477','0','TRUE','1',URL,'no-device-ack']]
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
        self.assertEqual(api.panel[15][1],'1 TEKNİK KAYIT')
        self.assertEqual(api.candidates,original_candidates)
        self.assertEqual(api.scans,original_scans)
        self.assertFalse(got['device_ack'])

    def test_idempotent_replay_has_no_second_write(self):
        api=FakeApi()
        p.synchronize(api)
        again=p.synchronize(api)
        self.assertFalse(again['changed'])
        self.assertEqual(api.writes,1)

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


if __name__=='__main__':
    unittest.main()
