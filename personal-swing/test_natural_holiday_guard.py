import unittest
from datetime import datetime,timedelta,timezone
import exchange_calendars as ec
import natural_holiday_guard as h

NOW=datetime.fromisoformat('2026-11-27T05:06:26+00:00')
SHA='b4e89d714ecef0b23f1a47d8808a9d566ec4bb52'
OLD_SHA='3db057d3b39e37c189c2fb9633f21a94631dffdc'

def env():
    return {'GITHUB_REPOSITORY':h.REPO,'GITHUB_REF':'refs/heads/main','GITHUB_WORKFLOW_REF':h.REPO+'/'+h.WORKFLOW+'@refs/heads/main','GITHUB_EVENT_NAME':'schedule','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':SHA,'GITHUB_RUN_ID':'45943723975'}
def run(rid,sha,created,status,conclusion):
    return {'id':rid,'head_sha':sha,'created_at':created,'updated_at':created,'event':'schedule','path':h.WORKFLOW,'head_branch':'main','run_attempt':1,'repository':{'full_name':h.REPO},'status':status,'conclusion':conclusion}
def records():
    return run(45943723975,SHA,'2026-11-27T05:05:45Z','in_progress',None),run(45759566518,OLD_SHA,'2026-11-26T05:08:00Z','completed','failure')
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.cal=ec.get_calendar('XNAS')
    def invoke(self,*,now=NOW,runtime=None,current=None,old=None,page=None):
        a,b=records(); a=a if current is None else current; b=b if old is None else old
        self.calls=[]
        def tr(m,p):
            self.calls.append((m,p)); self.assertEqual(m,'GET')
            return a if '/actions/runs/' in p else ({'total_count':1,'workflow_runs':[b]} if page is None else page)
        return h.classify_holiday_noop(env() if runtime is None else runtime,tr,now,calendar=self.cal)
    def test_reproduce_old_window_and_new_holiday_noop(self):
        cutoff=self.cal.session_close('2026-11-25').to_pydatetime()+timedelta(minutes=45)
        self.assertFalse(cutoff<=NOW<=cutoff+timedelta(hours=10))
        result=self.invoke(); self.assertEqual(result['status'],h.HOLIDAY);self.assertFalse(h.private_jobs_eligible(result));self.assertEqual(result['prior_eod_conclusion'],'failure');self.assertEqual(result['prior_asof_et'],'2026-11-25');self.assertEqual(result['writes'],0);self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[1][1],'/actions/workflows/xray-personal-477-eod.yml/runs?event=schedule&per_page=100&created=2026-11-25T21:45:00Z..2026-11-26T07:45:00Z')
    def test_success_prior_does_not_promote_holiday(self):
        _,b=records(); b['conclusion']='success';self.assertFalse(h.private_jobs_eligible(self.invoke(old=b)))
    def test_ordinary_day_late_holds(self):
        with self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_NOT_CLOSED_WEEKDAY'): self.invoke(now=datetime.fromisoformat('2026-11-26T09:00:00+00:00'))
        self.assertEqual(self.calls,[])
    def test_weekend_holds(self):
        with self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_SLOT_UNPROVEN'): self.invoke(now=datetime.fromisoformat('2026-11-29T05:00:00+00:00'))
    def test_slot_boundary(self):
        slot=datetime.fromisoformat('2026-11-26T23:16:00+00:00'); a,_=records(); a['created_at']=a['updated_at']='2026-11-26T23:16:00Z'
        self.assertEqual(self.invoke(now=slot,current=a)['status'],h.HOLIDAY)
        self.assertEqual(self.invoke(now=slot+timedelta(hours=10),current=a)['status'],h.HOLIDAY)
        with self.assertRaises(h.HolidayHold): self.invoke(now=slot+timedelta(hours=10,seconds=1),current=a)
    def test_early_close_day_never_holiday(self):
        with self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_NOT_CLOSED_WEEKDAY'): self.invoke(now=datetime.fromisoformat('2026-11-28T02:00:00+00:00'))
    def test_no_prior_or_duplicate_or_incomplete(self):
        _,b=records()
        for p in ({'total_count':0,'workflow_runs':[]},{'total_count':2,'workflow_runs':[b,b]},{'total_count':2,'workflow_runs':[b]},{'total_count':True,'workflow_runs':[b]}):
            with self.subTest(p=p), self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_PRIOR_EOD_NOT_UNIQUE'): self.invoke(page=p)
    def test_wrong_origin_or_runtime_blocks_before_get(self):
        for key,bad in [('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/other'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_SHA','bad')]:
            r=env();r[key]=bad
            with self.subTest(key=key),self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_RUNTIME_INVALID'):self.invoke(runtime=r)
            self.assertEqual(self.calls,[])
    def test_bad_current_receipt(self):
        for key,bad in [('status','completed'),('head_sha','a'*40),('event','push'),('id',4),('conclusion','success'),('run_attempt',True)]:
            a,_=records();a[key]=bad
            with self.subTest(key=key),self.assertRaises(h.HolidayHold): self.invoke(current=a)
    def test_current_created_before_slot(self):
        a,_=records();a['created_at']='2026-11-26T23:15:59Z'
        with self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_CURRENT_RECEIPT_CLOCK_DRIFT'):self.invoke(current=a)
    def test_prior_wrong_session_and_inprogress(self):
        for key,bad in [('created_at','2026-11-26T07:45:01Z'),('status','in_progress'),('event','workflow_dispatch'),('conclusion',None)]:
            _,b=records();b[key]=bad
            with self.subTest(key=key),self.assertRaises(h.HolidayHold):self.invoke(old=b)
    def test_gate_accepts_only_existing_positive_receipt(self):
        holiday=self.invoke(); result={k:v for k,v in holiday.items() if k not in ('holiday_date','prior_asof_et','prior_eod_conclusion','prior_run_id')}; result.update(status=h.VERIFIED,asof_et='2026-11-27',source_get_attempts=1);self.assertTrue(h.private_jobs_eligible(result))
        with self.assertRaises(h.HolidayHold):h.private_jobs_eligible(dict(holiday,status=h.VERIFIED,asof_et='2026-11-27',source_get_attempts=1))
        for key,bad in [('status','HOLD'),('writes',1),('writes',False),('orders',True),('ab_release_authorized',True),('lease_issued',True),('device_ack','ACKED')]:
            r=dict(result);r[key]=bad
            with self.subTest(key=key),self.assertRaises(h.HolidayHold):h.private_jobs_eligible(r)
    def test_clock_naive_refused(self):
        with self.assertRaisesRegex(h.HolidayHold,'HOLIDAY_CLOCK_INVALID'):self.invoke(now=NOW.replace(tzinfo=None))
    def test_provider_failure_not_swallowed(self):
        def timeout(*args):raise TimeoutError
        with self.assertRaises(TimeoutError):h.classify_holiday_noop(env(),timeout,NOW,calendar=self.cal)
if __name__=='__main__':unittest.main()
