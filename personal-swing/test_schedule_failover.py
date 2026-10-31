"""No-IO adversarial tests for the personal 477 XNAS schedule fallback."""
import unittest
from datetime import datetime,timezone
import schedule_failover as sf


def utc(s):
    return datetime.fromisoformat(s.replace('Z','+00:00'))


def record(*,created='2026-10-26T22:57:18Z',event='push',
           status='completed',conclusion='success',branch='main'):
    return {'created_at':created,'event':event,
            'status':status,'conclusion':conclusion,'head_branch':branch}


class OfficialXnasFailover(unittest.TestCase):
    def test_october_postclose_absent_run_would_dispatch_once(self):
        verdict,day=sf.decision(utc('2026-10-27T00:25:00Z'),[])
        self.assertEqual((verdict,day),('DISPATCH_ONE_MISSING_SCHEDULE','2026-10-26'))

    def test_current_session_success_no_duplicate(self):
        verdict,day=sf.decision(utc('2026-10-27T00:25:00Z'),[record()])
        self.assertEqual((verdict,day),('NOOP_CURRENT_EPOCH_RUN_EXISTS','2026-10-26'))

    def test_queued_inprogress_failed_all_prevent_infinite_retry(self):
        instant=utc('2026-10-27T00:25:00Z')
        for status,conclusion in [('queued',None),('in_progress',None),('completed','failure'),('completed','cancelled')]:
            with self.subTest(status=status,conclusion=conclusion):
                v,_=sf.decision(instant,[record(status=status,conclusion=conclusion)])
                self.assertEqual(v,'NOOP_CURRENT_EPOCH_RUN_EXISTS')

    def test_previous_session_success_cannot_suppress_today(self):
        v,_=sf.decision(utc('2026-10-27T00:25:00Z'),
                        [record(created='2026-10-23T21:30:00Z')])
        self.assertEqual(v,'DISPATCH_ONE_MISSING_SCHEDULE')

    def test_untrusted_pr_only_is_not_production_run(self):
        v,_=sf.decision(utc('2026-10-27T00:25:00Z'),
                        [record(event='pull_request',branch='some-branch')])
        self.assertEqual(v,'DISPATCH_ONE_MISSING_SCHEDULE')

    def test_no_dispatch_before_xnas_close_plus_45_minutes(self):
        v,_=sf.decision(utc('2026-10-26T20:44:00Z'),[])
        self.assertEqual(v,'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW')

    def test_november_dst_standard_time_correct(self):
        v,day=sf.decision(utc('2026-11-03T00:25:00Z'),[])
        self.assertEqual((v,day),('DISPATCH_ONE_MISSING_SCHEDULE','2026-11-02'))

    def test_holiday_and_weekend_do_not_call_github(self):
        for instant in ('2026-10-25T20:00:00Z','2026-11-26T20:00:00Z'):
            called=[]
            result=sf.run(now=utc(instant),
                read_runs=lambda:called.append('GET'),
                request_dispatch=lambda asof:called.append('POST:'+asof))
            self.assertEqual(called,[])
            self.assertEqual(result['status'],'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW')

    def test_malformed_and_unknown_status_fail_closed(self):
        instant=utc('2026-10-27T00:25:00Z')
        for rows in [[record(status='NONEXISTENT')],[{'event':'schedule','head_branch':'main'}],
                     [None]]:
            v,_=sf.decision(instant,rows)
            self.assertTrue(v.startswith('BLOCKED_'),v)

    def test_runner_real_no_workflow_runs_requests_one_dispatch(self):
        calls=[]
        def get():
            calls.append('GET')
            return {'workflow_runs':[],'total_count':0}
        def dispatch(asof):
            calls.append('POST:'+asof)
            return True
        x=sf.run(now=utc('2026-10-27T00:25:00Z'),read_runs=get,
                 request_dispatch=dispatch)
        self.assertEqual(calls,['GET','POST:2026-10-26'])
        self.assertEqual(x['status'],'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED')
        self.assertEqual(x['dispatch_requested'],True)

    def test_delayed_github_job_after_ny_midnight_still_checks_monday(self):
        # Real scheduler incident: 27 Oct 05:17 UTC = Tuesday 01:17 NY.
        # Monday 26 Oct close+45m remains the eligible target.
        v,day=sf.decision(utc('2026-10-27T05:17:32Z'),[])
        self.assertEqual((v,day),('DISPATCH_ONE_MISSING_SCHEDULE','2026-10-26'))

    def test_real_october_primary_run_suppresses_delayed_duplicate(self):
        v,day=sf.decision(
            utc('2026-10-27T05:17:32Z'),
            [record(created='2026-10-27T02:04:34Z',event='schedule')])
        self.assertEqual((v,day),('NOOP_CURRENT_EPOCH_RUN_EXISTS','2026-10-26'))

    def test_delayed_outside_ten_hour_window_fails_closed(self):
        # The user must not see a silent or very late replay.
        v,day=sf.decision(utc('2026-10-27T08:45:00Z'),[])
        self.assertEqual((v,day),('NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW','2026-10-26'))

    def test_early_close_is_measured_from_official_close(self):
        # Friday after Thanksgiving 2026, XNAS 13:00 ET early close.
        v,day=sf.decision(utc('2026-11-28T00:25:00Z'),[])
        self.assertEqual((v,day),('DISPATCH_ONE_MISSING_SCHEDULE','2026-11-27'))

    def test_delayed_runner_uses_prior_session_and_will_not_dispatch_if_run_exists(self):
        calls=[]
        def get():
            calls.append('GET')
            return {'workflow_runs':[
                record(created='2026-10-27T02:04:34Z',event='schedule')],
                'total_count':1}
        def dispatch(asof):
            calls.append('POST:'+asof)
            return True
        result=sf.run(now=utc('2026-10-27T05:17:32Z'),read_runs=get,
                      request_dispatch=dispatch)
        self.assertEqual(calls,['GET'])
        self.assertEqual(result['status'],'NOOP_CURRENT_EPOCH_RUN_EXISTS')
        self.assertEqual(result['asof_et'],'2026-10-26')

    def test_delayed_runner_dispatches_exactly_once_if_missing(self):
        calls=[]
        result=sf.run(now=utc('2026-10-27T05:17:32Z'),
                      read_runs=lambda:calls.append('GET') or
                          {'workflow_runs':[],'total_count':0},
                      request_dispatch=lambda asof:calls.append('POST:'+asof) or True)
        self.assertEqual(calls,['GET','POST:2026-10-26'])
        self.assertEqual(result['asof_et'],'2026-10-26')
        self.assertTrue(result['dispatch_requested'])

    def test_invalid_github_collection_blocks_dispatch(self):
        calls=[]
        x=sf.run(now=utc('2026-10-27T00:25:00Z'),
                 read_runs=lambda:{'missing':'data'},
                 request_dispatch=lambda asof:calls.append('POST:'+asof))
        self.assertEqual(calls,[])
        self.assertEqual(x['status'],'BLOCKED_INVALID_GITHUB_RUN_RESPONSE')

    def test_negative_dispatch_ack_cannot_be_success(self):
        x=sf.run(now=utc('2026-10-27T00:25:00Z'),
            read_runs=lambda:{'workflow_runs':[],'total_count':0},
            request_dispatch=lambda asof:False)
        self.assertEqual(x['status'],'BLOCKED_DISPATCH_NOT_CONFIRMED')
        self.assertFalse(x['dispatch_requested'])


    def test_hidden_existing_run_on_second_page_fails_closed(self):
        # Repro: 50 unrelated first-page runs hide a valid current-epoch
        # main run on the next page. Never emit a duplicate dispatch.
        calls=[]
        payload={'workflow_runs':[
            record(created='2026-10-27T00:24:00Z',
                   event='pull_request',branch='feature')
            for _ in range(50)],'total_count':51}
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=lambda:payload,
                      request_dispatch=lambda asof:calls.append(asof) or True)
        self.assertEqual(calls,[])
        self.assertEqual(result['status'],'BLOCKED_UNTRUSTED_RUN_PAGINATION')
        self.assertFalse(result['dispatch_requested'])

    def test_missing_or_forged_pagination_total_fails_closed(self):
        now=utc('2026-10-27T00:25:00Z')
        for total in (None,False,'0',-1):
            with self.subTest(total=total):
                calls=[]
                out=sf.run(now=now,read_runs=lambda:{
                    'workflow_runs':[], 'total_count':total},
                    request_dispatch=lambda asof:calls.append(asof) or True)
                self.assertEqual(calls,[])
                self.assertEqual(out['status'],'BLOCKED_UNTRUSTED_RUN_PAGINATION')


if __name__=='__main__':
    unittest.main()
