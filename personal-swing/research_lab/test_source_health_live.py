"""Offline negative and positive tests for private, read-only Personal 477 health collector."""
import copy
import json
import unittest

import source_health_live as live

D = '2026-11-20'
HEAD = 'a' * 40
EID = 101
URL = live.ROOT + str(EID)


def run(rid, path, event='schedule', status='success'):
    return {'id': rid, 'path': path, 'event': event, 'head_branch': 'main',
            'head_sha': HEAD, 'run_attempt': 1, 'status': 'completed',
            'conclusion': status, 'head_repository': {'full_name': live.REPO}}


class Sheets:
    def __init__(self):
        self.rows = {
            'TARAMA_KAYITLARI': [live.SCAN_HEADER,
                [D, 'ALPACA', '477', '477', '477', '0', 'TRUE', '1', URL, 'RESEARCH']],
            'SWING_SKOR_GUNLUK': [[
                'KAYIT_KIMLIGI', 'ASOF_ET', 'EPIZOT_KIMLIGI', 'SEMBOL', 'KAYIT_TIPI'
            ] + [''] * 30, self.summary()]
        }
        kh=['KAYIT_KIMLIGI','ASOF_ET','SEMBOL','UFUK_SEANS','SON_IEX_KAPANIS_USD']+['']*15
        kronos=[kh]
        for i in range(477):
            for horizon in ('1','5','12'):
                row=['']*20
                row[0]=D+'|SYM'+str(i)+'|'+horizon
                row[1]=D;row[2]='SYM'+str(i);row[3]=horizon
                row[13]='EXACT_SCAN';row[14]='a'*64;row[15]='b'*64;row[19]='c'*64
                row[17]='RESEARCH_ONLY' if i<342 else 'RESEARCH_CLOSE_ONLY'
                kronos.append(row)
        self.rows['KRONOS2_2026_11']=kronos
        self.calls=[]

    @staticmethod
    def summary():
        r=['']*35
        r[0]=D+'|SUMMARY';r[1]=D;r[4]='SUMMARY';r[26]=URL
        r[27]='READY_FOR_CHATGPT_DAILY_DIGEST'
        return r

    def read(self, tab, col):
        self.calls.append((tab,col))
        return copy.deepcopy(self.rows[tab])


class Github:
    def __init__(self):
        jobs = [{'name': n, 'id': 100+i, 'conclusion': 'success'} for i, n in
            enumerate(['daily-private-scan','private-episode-followups',
                       'guardian-acceptance','daily-private-score-acceptance'])]
        self.docs={
            '/actions/runs/101': run(EID,live.contract.EOD),
            '/actions/runs/101/jobs?per_page=100': {'jobs':jobs},
            '/actions/workflows/xray-personal-kronos-shadow.yml/runs?event=workflow_run&per_page=60':
                {'workflow_runs':[run(202,live.contract.WORKFLOWS['KRONOS_V2'],'workflow_run')]},
            '/actions/workflows/xray-personal-cove-shadow.yml/runs?event=workflow_run&per_page=60':
                {'workflow_runs':[run(203,live.contract.WORKFLOWS['COVE'],'workflow_run')]},
            '/actions/runs/202/jobs?per_page=100':
                {'jobs':[{'name':'kronos-v2-full-477-research','id':302,'conclusion':'success'}]},
            '/actions/runs/203/jobs?per_page=100':
                {'jobs':[{'name':'private-eod-research','id':303,'conclusion':'success'}]},
        }
        kronos = {'asof_et':D, 'eod_run_id': EID, 'eod_head_sha': HEAD,
            'status':'KRONOS2_PRIVATE_READBACK_CLOSE_ONLY', 'scope':477,
            'rows_written':1431,'full_geometry':342,'close_only':135,'qc_hold':0}
        parent={'asof_et':D,'eod_run_id':EID,'eod_head_sha':HEAD}
        self.logs={
            '/actions/jobs/100/logs':'2026-11-21T00:00:00Z ' + json.dumps({
                'official_shadow_receipt':'RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE',
                'market_clearance_proven':False,'corporate_actions_unknown':477}),
            '/actions/jobs/302/logs':'2026-11-21T00:03:00Z '+json.dumps(kronos),
            '/actions/jobs/303/logs':'2026-11-21T00:02:00Z COVE_SOURCE_PARENT_V1='+
                json.dumps(parent)+'\n2026-11-21T00:02:05Z '
                'COVE_SHADOW_POST_EOD=READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS;NO_ORDERS'
        }
        self.calls=[]

    def json(self, path):
        self.calls.append(('json',path))
        return copy.deepcopy(self.docs[path])

    def text(self,path):
        self.calls.append(('text',path))
        return self.logs[path]


class LiveSourceHealthTest(unittest.TestCase):
    def test_valid_all_four_lanes(self):
        gh,s=Github(),Sheets()
        report,gaps=live.aggregate(gh,s,D)
        self.assertEqual(gaps,{})
        self.assertEqual(set(report['sources']),set(live.contract.WORKFLOWS))
        self.assertTrue(all(v['state'].startswith('MATCHED_') for v in report['sources'].values()))
        self.assertFalse(report['may_notify'])
        self.assertFalse(report['may_trade'])
        self.assertFalse(report['may_write_sheet'])
        self.assertEqual(s.calls,[('TARAMA_KAYITLARI','J'),('SWING_SKOR_GUNLUK','AI'),('KRONOS2_2026_11','T')])

    def test_latest_asof_must_match(self):
        with self.assertRaises(live.NoProof):
            live.aggregate(Github(),Sheets(),'2026-11-19')

    def test_wrong_score_eod_blocks_all(self):
        s=Sheets();s.rows['SWING_SKOR_GUNLUK'][1][26]=live.ROOT+'102'
        with self.assertRaises(live.NoProof):
            live.aggregate(Github(),s,D)

    def test_missing_cove_never_fakes_pass(self):
        gh=Github()
        gh.docs['/actions/workflows/xray-personal-cove-shadow.yml/runs?event=workflow_run&per_page=60']={'workflow_runs':[]}
        report,gaps=live.aggregate(gh,Sheets(),D)
        self.assertEqual(report['sources']['COVE']['state'],'UNKNOWN')
        self.assertIn('COVE',gaps)
        self.assertEqual(report['sources']['CORE']['state'],'MATCHED_CORE_RECEIPT')

    def test_wrong_kronos_parent_cannot_pass(self):
        gh=Github()
        gh.logs['/actions/jobs/302/logs']=gh.logs['/actions/jobs/302/logs'].replace('"eod_run_id": 101','"eod_run_id": 999')
        report,gaps=live.aggregate(gh,Sheets(),D)
        self.assertEqual(report['sources']['KRONOS_V2']['state'],'UNKNOWN')
        self.assertIn('KRONOS_V2',gaps)

    def test_green_without_official_receipt_is_unknown(self):
        gh=Github();gh.logs['/actions/jobs/100/logs']='SUCCESS'
        report,gaps=live.aggregate(gh,Sheets(),D)
        self.assertEqual(report['sources']['OFFICIAL_477']['state'],'UNKNOWN')
        self.assertIn('OFFICIAL_477',gaps)

    def test_wrong_cove_parent_cannot_pass(self):
        gh=Github()
        gh.logs['/actions/jobs/303/logs']=gh.logs['/actions/jobs/303/logs'].replace('"eod_run_id": 101','"eod_run_id": 999')
        report,gaps=live.aggregate(gh,Sheets(),D)
        self.assertEqual(report['sources']['COVE']['state'],'UNKNOWN')
        self.assertIn('COVE',gaps)

    def test_missing_producer_guardian_blocks_all(self):
        gh=Github()
        gh.docs['/actions/runs/101/jobs?per_page=100']['jobs'][2]['conclusion']='failure'
        with self.assertRaises(live.NoProof):
            live.aggregate(gh,Sheets(),D)

    def test_unverified_asof_is_fail_closed(self):
        s=Sheets();s.rows['TARAMA_KAYITLARI'][1][6]='FALSE'
        with self.assertRaises(live.NoProof):
            live.aggregate(Github(),s,D)


if __name__=='__main__':
    unittest.main()