import copy
import unittest
from datetime import date, datetime, timezone
from personal_watch_artifact_admission import *
from personal_watch_run_lineage_guard import verify_run

# Minimal reconstruction of the actual 26-Nov ET scheduled source receipt.
RUN = dict(id=45938020728, head_sha="4a76b1a6122468e06343cc3bb506ed9fa9c80a7d",
           event="schedule", run_attempt=1, status="completed", conclusion="success",
           run_started_at="2026-11-27T04:06:54Z", updated_at="2026-11-27T04:07:15Z",
           name="XRAY Personal Full-Universe SIP EOD Coverage (Research Only)",
           path=".github/workflows/xray-personal-full-universe-sip-coverage.yml",
           head_branch="main", repository={"full_name":"gokaydonmez39-jpg/kripto-radar"},
           head_repository={"full_name":"gokaydonmez39-jpg/kripto-radar"})
COMMON = dict(run_id=RUN['id'], head_sha=RUN['head_sha'], run_attempt=1, status='completed')
G = dict(COMMON, name=GATE, conclusion='success', started_at='2026-11-27T04:06:56Z',
         completed_at='2026-11-27T04:07:14Z', steps=[
             dict(name=CALENDAR_STEP,status='completed',conclusion='success',started_at='2026-11-27T04:07:11Z',completed_at='2026-11-27T04:07:12Z'),
             dict(name=PREFLIGHT_STEP,status='completed',conclusion='skipped')])
JOBS = dict(total_count=8, jobs=[G]+[dict(COMMON,name=n,conclusion='skipped') for n in sorted(SKIPPED_JOBS)])
EMPTY = dict(total_count=0,artifacts=[])
LIVE = dict(total_count=1,artifacts=[dict(name=ARTIFACT,id=123,expired=False)])

def calendar_fixture(stamp,event):
    day=stamp.astimezone(NY).date()
    if day == date(2026,11,26): return False
    if day == date(2026,11,27): return True
    raise RuntimeError('unverified fixture day')

class T(unittest.TestCase):
    def setUp(self):
        self.r,self.j,self.a=map(copy.deepcopy,(RUN,JOBS,EMPTY))
    def admit(self): return admit(self.r,self.a,self.j,permit_compute=calendar_fixture)
    def test_holiday(self): self.assertEqual(self.admit(),'CLOSED_SESSION_NOOP')
    def test_live(self): self.assertEqual(admit(self.r,LIVE),'READY')
    def test_open_day(self):
        with self.assertRaises(ValueError): admit(self.r,self.a,self.j,permit_compute=lambda *_:True)
    def test_calendar_unknown(self):
        with self.assertRaises(ValueError): admit(self.r,self.a,self.j,permit_compute=lambda *_:None)
    def test_calendar_error(self):
        def err(*_): raise RuntimeError('calendar offline')
        with self.assertRaises(RuntimeError): admit(self.r,self.a,self.j,permit_compute=err)
    def test_missing_artifact_unrelated(self):
        self.a=dict(total_count=1,artifacts=[dict(name='other')]);self.assertRaises(ValueError,self.admit)
    def test_incomplete_artifact_list(self):
        self.a['total_count']=1;self.assertRaises(ValueError,self.admit)
    def test_expired(self):
        self.a=copy.deepcopy(LIVE);self.a['artifacts'][0]['expired']=True;self.assertRaises(ValueError,self.admit)
    def test_duplicate(self):
        self.a=copy.deepcopy(LIVE);self.a['artifacts']*=2;self.a['total_count']=2;self.assertRaises(ValueError,self.admit)
    def test_missing_job(self):
        self.j['jobs'].pop();self.j['total_count']-=1;self.assertRaises(ValueError,self.admit)
    def test_job_pagination(self):
        self.j['total_count']=9;self.assertRaises(ValueError,self.admit)
    def test_wrong_sha(self):
        self.j['jobs'][1]['head_sha']='a'*40;self.assertRaises(ValueError,self.admit)
    def test_wrong_run_id(self):
        self.j['jobs'][1]['run_id']=1;self.assertRaises(ValueError,self.admit)
    def test_wrong_attempt(self):
        self.r['run_attempt']=2;self.assertRaises(ValueError,self.admit)
    def test_dispatch(self):
        self.r['event']='workflow_dispatch';self.assertRaises(ValueError,self.admit)
    def test_job_not_skipped(self):
        self.j['jobs'][1]['conclusion']='success';self.assertRaises(ValueError,self.admit)
    def test_gate_failed(self):
        self.j['jobs'][0]['conclusion']='failure';self.assertRaises(ValueError,self.admit)
    def test_preflight_not_skipped(self):
        self.j['jobs'][0]['steps'][1]['conclusion']='success';self.assertRaises(ValueError,self.admit)
    def test_step_failed(self):
        self.j['jobs'][0]['steps'][0]['conclusion']='failure';self.assertRaises(ValueError,self.admit)
    def test_time_before_run(self):
        self.j['jobs'][0]['steps'][0]['started_at']='2026-11-27T04:00:00Z';self.assertRaises(ValueError,self.admit)
    def test_midnight(self):
        self.r['updated_at']='2026-11-27T05:01:00Z';self.j['jobs'][0]['completed_at']='2026-11-27T05:00:30Z';self.j['jobs'][0]['steps'][0]['completed_at']='2026-11-27T05:00:01Z';self.assertRaises(ValueError,self.admit)
    def shift_friday(self):
        self.r['run_started_at']='2026-11-27T15:00:00Z';self.r['updated_at']='2026-11-27T15:01:00Z'
        g=self.j['jobs'][0];g['started_at']='2026-11-27T15:00:01Z';g['completed_at']='2026-11-27T15:00:30Z'
        g['steps'][0]['started_at']='2026-11-27T15:00:20Z';g['steps'][0]['completed_at']='2026-11-27T15:00:21Z'
    def test_actual_early_close_day(self):
        self.shift_friday()
        self.assertRaises(ValueError,self.admit)
    def test_real_pinned_calendar_and_lineage(self):
        from root_weekend_quota_guard import permit_compute
        from importlib.metadata import version
        self.assertEqual(version("pandas_market_calendars"),"5.4.0")
        self.assertEqual(verify_run(self.r,self.r["repository"]["full_name"],expected_run_id=self.r["id"],expected_head_sha=self.r["head_sha"]),self.r["id"])
        self.assertEqual(admit(self.r,self.a,self.j,permit_compute=permit_compute),"CLOSED_SESSION_NOOP")
        self.shift_friday()
        with self.assertRaises(ValueError): admit(self.r,self.a,self.j,permit_compute=permit_compute)

if __name__=='__main__': unittest.main()
