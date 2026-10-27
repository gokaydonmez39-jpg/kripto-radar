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
        result=w.synchronize(snapshot(),RUN,api)
        self.assertEqual(result['status'],'PRIVATE_SHEET_READBACK_PASS')
        self.assertEqual(result['candidates'],2)
        self.assertFalse(result['device_ack'])
        self.assertEqual(api.apply_count,1)
        self.assertEqual(len(api.candidates),3)
        self.assertEqual(len(api.scans),2)

    def test_idempotent_replay_no_duplicate(self):
        api=FakeApi()
        w.synchronize(snapshot(),RUN,api)
        w.synchronize(snapshot(),RUN,api)
        self.assertEqual(api.apply_count,2)
        self.assertEqual(len(api.candidates),3)
        self.assertEqual(len(api.scans),2)
        self.assertEqual(w.payload_from_plan(
            w.plan(snapshot(),api.candidates,api.scans,RUN))['requests'],[])

    def test_header_drift_blocks(self):
        api=FakeApi()
        api.candidates[0][0]='WRONG HEADER'
        with self.assertRaisesRegex(w.HandoffBlocked,'SHEET_HEADER_DRIFT'):
            w.synchronize(snapshot(),RUN,api)
        self.assertEqual(api.apply_count,0)

    def test_existing_duplicate_episode_blocks(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN)
        api.candidates.extend([p['candidate_rows'][0]]*2)
        with self.assertRaisesRegex(w.HandoffBlocked,'DUPLICATE_CANDIDATE_KEYS'):
            w.synchronize(snapshot(),RUN,api)

    def test_immutable_original_stop_blocks_conflict(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN)
        row=copy.deepcopy(p['candidate_rows'][0])
        row[5]='100'
        api.candidates.append(row)
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_ORIGINAL_LEVEL_CONFLICT'):
            w.synchronize(snapshot(),RUN,api)
        self.assertEqual(api.apply_count,0)

    def test_same_asof_different_counts_blocks(self):
        api=FakeApi()
        p=w.plan(snapshot(),api.candidates,api.scans,RUN)
        row=copy.deepcopy(p['scan_rows'][0])
        row[7]='0'
        api.scans.append(row)
        with self.assertRaisesRegex(w.HandoffBlocked,'EXISTING_SCAN_EPOCH_CONFLICT'):
            w.synchronize(snapshot(),RUN,api)

    def test_concurrent_row_change_fails_closed_before_write(self):
        api=FakeApi()
        api.change_on_second_read=True
        with self.assertRaisesRegex(w.HandoffBlocked,'CONCURRENT_SHEET_EDIT_BLOCKED'):
            w.synchronize(snapshot(),RUN,api)
        self.assertEqual(api.apply_count,0)

    def test_missing_readback_blocks_false_delivery(self):
        api=FakeApi()
        api.break_readback=True
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_READBACK_MISSING'):
            w.synchronize(snapshot(),RUN,api)

    def test_bad_scope_and_partial_data_never_append(self):
        for field,value in [('valid_data_symbols',476),('scope_sha256','f'*64),
                            ('requested_symbols',478)]:
            with self.subTest(field=field):
                api=FakeApi()
                data=snapshot()
                data[field]=value
                with self.assertRaises(Exception):
                    w.synchronize(data,RUN,api)
                self.assertEqual(api.apply_count,0)

    def test_readback_rejects_corrupted_new_stop(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN)
        candidates=[list(w.CANDIDATE_HEADER)]+copy.deepcopy(p['candidate_rows'])
        scans=[list(w.SCAN_HEADER)]+copy.deepcopy(p['scan_rows'])
        candidates[1][5]='1,00'
        with self.assertRaisesRegex(w.HandoffBlocked,'READBACK'):
            w.verify_readback(p,candidates,scans)

    def test_readback_rejects_corrupted_new_scan_provenance(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN)
        candidates=[list(w.CANDIDATE_HEADER)]+copy.deepcopy(p['candidate_rows'])
        scans=[list(w.SCAN_HEADER)]+copy.deepcopy(p['scan_rows'])
        scans[1][8]='https://github.com/unrelated/actions/runs/123'
        with self.assertRaisesRegex(w.HandoffBlocked,'READBACK'):
            w.verify_readback(p,candidates,scans)

    def test_existing_price_one_cent_conflict_is_not_rounding(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN)
        old=copy.deepcopy(p['candidate_rows'][0])
        old[4]='100,01'
        with self.assertRaisesRegex(w.HandoffBlocked,'CANDIDATE_ORIGINAL_LEVEL_CONFLICT'):
            w.plan(snapshot(),[list(w.CANDIDATE_HEADER),old],
                   [list(w.SCAN_HEADER)],RUN)

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

    def test_no_credentials_is_explicit_nonzero_not_fake_success(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'snap.json'
            file.write_text('{}')
            with patch.dict('os.environ',{'GITHUB_RUN_ID':'42'},clear=True):
                self.assertEqual(w.main(['--snapshot',str(file)]),3)

    def test_candidate_rows_never_include_broker_or_orders(self):
        p=w.plan(snapshot(),[list(w.CANDIDATE_HEADER)],
                 [list(w.SCAN_HEADER)],RUN)
        self.assertEqual(len(p['candidate_rows']),2)
        self.assertEqual(len(p['scan_rows']),1)
        self.assertTrue(all('NO_BROKER_NO_ORDERS' in r[-1] for r in p['candidate_rows']))
        self.assertFalse(any('AL_NEW_EPISODE' in str(r) for r in p['candidate_rows']))


if __name__=='__main__':
    unittest.main()
