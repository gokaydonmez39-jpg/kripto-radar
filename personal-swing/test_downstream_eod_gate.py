import copy, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import downstream_eod_gate as g

NOW=datetime(2026,11,28,2,0,tzinfo=timezone.utc)
RUN={'id':123,'run_attempt':1,'event':'schedule','path':g.PATH,'head_branch':'main','status':'completed','conclusion':'success','repository':{'full_name':g.REPO},'head_sha':'a'*40,'created_at':'2026-11-27T23:16:00Z','updated_at':'2026-11-28T00:00:00Z'}
EVENT={'action':'completed','repository':{'full_name':g.REPO},'workflow_run':RUN}
JOBS={'total_count':6,'jobs':[{'id':i+1,'run_id':123,'name':name,'status':'completed','conclusion':'success'} for i,name in enumerate(sorted(g.JOBS))]}
PROOF={'status':'PRIMARY_EOD_SIX_JOB_PROVEN_GH_ONLY','asof_et':'2026-11-27','run_id':123,'source_event':'schedule','private_sheet_verified':False,'ab_release_authorized':False,'orders':False,'device_ack':'UNKNOWN'}

class GateTests(unittest.TestCase):
    def setUp(self):
        self.event=copy.deepcopy(EVENT);self.detail=copy.deepcopy(RUN);self.listing={'total_count':1,'workflow_runs':[copy.deepcopy(RUN)]};self.jobs=copy.deepcopy(JOBS);self.validator=Mock(return_value=copy.deepcopy(PROOF));self.calls=[]
    def get(self,url):
        self.calls.append(url)
        if '/workflows/' in url:return self.listing
        if url.endswith('/jobs?per_page=100'):return self.jobs
        return self.detail
    def run_gate(self,now=NOW):return g.admit(self.event,now,self.get,self.validator)
    def rejects(self,now=NOW):
        with self.assertRaises(g.Hold):self.run_gate(now)
    def test_valid_early_close(self):
        self.assertEqual(self.run_gate()['asof_et'],'2026-11-27');self.assertEqual(len(self.calls),3);self.assertIn('2026-11-27T18:45:00Z..2026-11-28T04:45:00Z',self.calls[1]);self.validator.assert_called_once()
    def test_holiday_real_time(self):
        self.rejects(datetime(2026,11,27,5,6,tzinfo=timezone.utc));self.assertEqual(self.calls,[])
    def test_exact_cutoff_and_end(self):
        t=datetime(2026,11,27,18,45,tzinfo=timezone.utc);self.assertEqual(g.current_epoch(t)[0],'2026-11-27');self.assertEqual(g.current_epoch(t+timedelta(hours=10))[0],'2026-11-27')
        for bad in (t-timedelta(seconds=1),t+timedelta(hours=10,seconds=1)):
            with self.assertRaises(g.Hold):g.current_epoch(bad)
    def test_wrong_event(self):
        self.event['action']='requested';self.rejects();self.assertFalse(self.calls)
    def test_wrong_parent(self):
        for key,val in [('event','workflow_dispatch'),('head_branch','feature'),('run_attempt',2),('status','in_progress'),('conclusion','failure'),('path','other'),('id',True)]:
            with self.subTest(key=key):
                self.setUp();self.event['workflow_run'][key]=val;self.rejects();self.assertFalse(self.calls)
    def test_stale_parent(self):
        self.event['workflow_run']['created_at']='2026-11-26T05:08:00Z';self.rejects();self.assertFalse(self.calls)
    def test_detail_drift(self):
        self.detail['head_sha']='b'*40;self.rejects();self.assertEqual(len(self.calls),1)
    def test_duplicate_epoch(self):
        self.listing['total_count']=2;self.listing['workflow_runs'].append(copy.deepcopy(RUN));self.rejects();self.validator.assert_not_called()
    def test_list_drift(self):
        self.listing['workflow_runs'][0]['updated_at']='2026-11-28T00:01:00Z';self.rejects();self.validator.assert_not_called()
    def test_missing_listing(self):
        self.listing={'total_count':0,'workflow_runs':[]};self.rejects()
    def test_noop_green_parent_five_skipped(self):
        for j in self.jobs['jobs']:
            if j['name']!='offline-guard':j['conclusion']='skipped'
        self.rejects();self.validator.assert_not_called()
    def test_failed_guardian(self):
        next(j for j in self.jobs['jobs'] if j['name']=='guardian-acceptance')['conclusion']='failure';self.rejects()
    def test_duplicate_job(self):
        self.jobs['jobs'][0]['id']=self.jobs['jobs'][1]['id'];self.rejects()
    def test_wrong_job_run(self):
        self.jobs['jobs'][0]['run_id']=124;self.rejects()
    def test_missing_job(self):
        self.jobs['jobs'].pop();self.rejects()
    def test_validator_rejects_steps(self):
        self.validator.side_effect=g.Hold('STEP_INVALID');self.rejects()
    def test_validator_wrong_proof(self):
        for field,value in [('asof_et','2026-11-25'),('run_id',999),('orders',True),('ab_release_authorized',True),('private_sheet_verified',True),('device_ack','ACK')]:
            with self.subTest(field=field):
                self.setUp();self.validator.return_value[field]=value;self.rejects()
    def test_transport_error_propagates(self):
        with self.assertRaises(TimeoutError):g.admit(self.event,NOW,Mock(side_effect=TimeoutError),self.validator)
        self.validator.assert_not_called()
if __name__=='__main__':unittest.main()
