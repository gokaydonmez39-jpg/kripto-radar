"""No-IO adversarial tests for the personal 477 XNAS schedule fallback."""
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
import schedule_failover as sf


def utc(s):
    return datetime.fromisoformat(s.replace('Z','+00:00'))


def record(*,created='2026-10-26T22:57:18Z',event='schedule',
           status='completed',conclusion='success',branch='main',run_attempt=1,
           id=890123):
    return {'id':id, 'path':'.github/workflows/xray-personal-477-eod.yml',
            'repository':{'full_name':'gokaydonmez39-jpg/kripto-radar'},
            'head_sha':'a'*40, 'created_at':created,'event':event,
            'status':status,'conclusion':conclusion,'head_branch':branch,
            'run_attempt':run_attempt}


class OfficialXnasFailover(unittest.TestCase):
    def setUp(self):
        # Exercise hypothetical authorized recovery decision mechanics;
        # live production remains policy-locked. The separate isolation
        # tests below always verify the default DENY side-effect boundary.
        policy=patch.object(sf, "allow_dispatch_for_event",return_value=True)
        policy.start()
        self.addCleanup(policy.stop)

    def test_october_postclose_absent_run_would_dispatch_once(self):
        verdict,day=sf.decision(utc('2026-10-27T00:25:00Z'),[])
        self.assertEqual((verdict,day),('DISPATCH_ONE_MISSING_SCHEDULE','2026-10-26'))

    def test_current_session_success_no_duplicate(self):
        verdict,day=sf.decision(utc('2026-10-27T00:25:00Z'),[record()])
        self.assertEqual((verdict,day),('NOOP_CURRENT_EPOCH_RUN_EXISTS','2026-10-26'))

    def test_incomplete_or_failed_natural_run_blocks_without_retrigger(self):
        instant=utc('2026-10-27T00:25:00Z')
        for status,conclusion,expected in [
            ('queued',None,'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE'),
            ('in_progress',None,'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE'),
            ('completed','failure','BLOCKED_CURRENT_EPOCH_NATURAL_EOD_NOT_SUCCESS'),
            ('completed','cancelled','BLOCKED_CURRENT_EPOCH_NATURAL_EOD_NOT_SUCCESS')]:
            with self.subTest(status=status,conclusion=conclusion):
                item=record(status=status,conclusion=conclusion)
                v,_=sf.decision(instant,[item])
                self.assertEqual(v,expected)
                called=[]
                out=sf.run(now=instant,
                    read_runs=lambda:called.append('GET') or {
                        'workflow_runs':[item],'total_count':1},
                    request_dispatch=lambda asof:called.append('POST'))
                self.assertEqual(out['status'],expected)
                self.assertEqual(called,['GET'])
                self.assertEqual(sf.exit_code_for_result(out,'schedule'),3)

    def test_offline_push_must_not_mask_missing_natural_eod(self):
        # Reproduce 21 Nov 00:37 UTC: an offline-only EOD push completed
        # after Friday's close but cannot supply any private Sheet receipt.
        instant=utc('2026-11-21T00:45:00Z')
        for status in ('completed','queued','in_progress'):
            with self.subTest(status=status):
                bogus=record(created='2026-11-21T00:37:35Z',
                             event='push',status=status)
                verdict,asof=sf.decision(instant,[bogus])
                self.assertEqual((verdict,asof),
                                 ('DISPATCH_ONE_MISSING_SCHEDULE','2026-11-20'))
        real=record(created='2026-11-21T00:40:00Z',
                    event='schedule',status='queued')
        self.assertEqual(sf.decision(instant,[bogus,real]),
                         ('BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE','2026-11-20'))

    def test_previous_session_success_cannot_suppress_today(self):
        v,_=sf.decision(utc('2026-10-27T00:25:00Z'),
                        [record(created='2026-10-23T21:30:00Z')])
        self.assertEqual(v,'DISPATCH_ONE_MISSING_SCHEDULE')

    def test_untrusted_pr_only_is_not_production_run(self):
        v,_=sf.decision(utc('2026-10-27T00:25:00Z'),
                        [record(event='pull_request',branch='some-branch')])
        self.assertEqual(v,'DISPATCH_ONE_MISSING_SCHEDULE')

    def test_manual_source_never_masquerades_as_natural_schedule(self):
        instant=utc('2026-11-21T00:26:00Z')
        manual=record(created='2026-11-20T23:55:00Z',
                      event='workflow_dispatch',conclusion='success')
        self.assertEqual(sf.decision(instant,[manual]),
                         ('BLOCKED_CURRENT_EPOCH_NON_NATURAL_SOURCE','2026-11-20'))
        real=record(created='2026-11-20T23:56:00Z',
                    event='schedule',conclusion='success')
        for runs in ([manual,real],[real,manual]):
            self.assertEqual(sf.decision(instant,runs),
                             ('NOOP_CURRENT_EPOCH_RUN_EXISTS','2026-11-20'))

    def test_10h_window_boundary_then_expired_scheduled_fallback(self):
        # Friday 20 Nov official XNAS close +45m is Friday 21:45 UTC.
        self.assertEqual(sf.decision(utc('2026-11-21T07:45:00Z'),[])[0],
                         'DISPATCH_ONE_MISSING_SCHEDULE')
        calls=[]
        result=sf.run(now=utc('2026-11-21T07:45:01Z'),
            trigger_event='schedule',
            read_runs=lambda:calls.append('GET') or {'workflow_runs':[],'total_count':0},
            request_dispatch=lambda asof:calls.append('POST:'+asof))
        self.assertEqual(result['status'],'BLOCKED_NATURAL_FALLBACK_EXPIRED')
        self.assertEqual(result['asof_et'],'2026-11-20')
        self.assertEqual(calls,[])
        self.assertEqual(sf.exit_code_for_result(result,'schedule'),3)

    def test_scheduled_thanksgiving_noop_stays_green(self):
        x=sf.run(now=utc('2026-11-27T00:26:00Z'),
            trigger_event='schedule',
            read_runs=lambda:self.fail('NO_GITHUB_GET_ON_HOLIDAY'),
            request_dispatch=lambda asof:self.fail('NO_DISPATCH_ON_HOLIDAY'))
        self.assertEqual(x['status'],'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW')
        self.assertEqual(sf.exit_code_for_result(x,'schedule'),0)

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
        self.assertEqual(calls,['GET','GET','POST:2026-10-26'])
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
        self.assertEqual(calls,['GET','GET','POST:2026-10-26'])
        self.assertEqual(result['asof_et'],'2026-10-26')
        self.assertTrue(result['dispatch_requested'])

    def test_fallback_crosses_xnas_ten_hour_deadline_during_gets(self):
        """The first clock was legal; by the LAST moment it is too late."""
        calls=[]
        old=utc('2026-11-21T07:44:58Z')
        late=utc('2026-11-21T07:45:01Z')
        result=sf.run(now=old,
            trigger_event='schedule',
            read_runs=lambda:calls.append('GET') or
                {'workflow_runs':[],'total_count':0},
            request_dispatch=lambda asof:calls.append('POST:'+asof) or True,
            fresh_now=lambda:late)
        self.assertEqual(result['status'],
                         'BLOCKED_DISPATCH_WINDOW_EXPIRED')
        self.assertEqual(result['asof_et'],'2026-11-20')
        self.assertFalse(result['dispatch_requested'])
        self.assertEqual(calls,['GET','GET'])

    def test_exact_last_second_of_xnas_window_still_allowed(self):
        calls=[]
        old=utc('2026-11-21T07:44:58Z')
        edge=utc('2026-11-21T07:45:00Z')
        result=sf.run(now=old,
            trigger_event='schedule',
            read_runs=lambda:calls.append('GET') or
                {'workflow_runs':[],'total_count':0},
            request_dispatch=lambda asof:calls.append('POST:'+asof) or True,
            fresh_now=lambda:edge)
        self.assertEqual(result['status'],
                         'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED')
        self.assertEqual(calls,['GET','GET','POST:2026-11-20'])

    def test_bad_or_backward_clock_never_authorizes_dispatch(self):
        old=utc('2026-11-21T07:44:58Z')
        cases=(None,utc('2026-11-21T07:44:50Z'),
               utc('2026-11-21T07:46:00Z').replace(tzinfo=None))
        for candidate in cases:
            with self.subTest(candidate=candidate):
                calls=[]
                result=sf.run(now=old,trigger_event='schedule',
                    read_runs=lambda:calls.append('GET') or
                        {'workflow_runs':[],'total_count':0},
                    request_dispatch=lambda asof:calls.append('POST:'+asof) or True,
                    fresh_now=lambda:candidate)
                self.assertEqual(result['status'],
                                 'BLOCKED_DISPATCH_CLOCK_UNVERIFIED')
                self.assertFalse(result['dispatch_requested'])
                self.assertEqual(calls,['GET','GET'])

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


    def test_created_window_filters_only_complete_safe_fallback_epoch(self):
        from urllib.parse import parse_qs,urlparse
        base='https://api.github.com/repos/owner/repo/actions/workflows/eod.yml'
        url=sf.windowed_runs_url(base,utc('2026-11-03T00:25:00Z'))
        parsed=urlparse(url)
        query=parse_qs(parsed.query)
        self.assertEqual(parsed.path,'/repos/owner/repo/actions/workflows/eod.yml/runs')
        self.assertEqual(query['per_page'],['100'])
        # 10h maximum from completed XNAS cutoff, plus a 5m margin.
        self.assertEqual(query['created'],['>=2026-11-02T14:20:00Z'])
        with self.assertRaisesRegex(ValueError,'AWARE_UTC_NOW_REQUIRED'):
            sf.windowed_runs_url(base,datetime(2026,11,3,0,25))

    def test_overfull_one_hundred_page_also_fails_closed(self):
        calls=[]
        payload={'workflow_runs':[
            record(created='2026-10-27T00:24:00Z',
                   event='pull_request',branch='feature')
            for _ in range(100)],'total_count':101}
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=lambda:payload,
                      request_dispatch=lambda asof:calls.append(asof) or True)
        self.assertEqual(calls,[])
        self.assertEqual(result['status'],'BLOCKED_UNTRUSTED_RUN_PAGINATION')

    def test_second_read_new_main_run_suppresses_duplicate_dispatch(self):
        calls=[]
        snapshots=[
            {'workflow_runs':[],'total_count':0},
            {'workflow_runs':[record(created='2026-10-27T00:24:00Z',
                                     event='schedule',status='queued',
                                     conclusion=None)],'total_count':1},
        ]
        def read():
            calls.append('GET')
            return snapshots.pop(0)
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=read,
                      request_dispatch=lambda asof:calls.append('POST:'+asof) or True)
        self.assertEqual(calls,['GET','GET'])
        self.assertEqual(result['status'],'BLOCKED_RECHECK_UNCERTAIN_RUN_STATE')
        self.assertFalse(result['dispatch_requested'])

    def test_second_read_unknown_pagination_fails_closed(self):
        calls=[]
        snapshots=[
            {'workflow_runs':[],'total_count':0},
            {'workflow_runs':[],'total_count':1},
        ]
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=lambda:calls.append('GET') or snapshots.pop(0),
                      request_dispatch=lambda asof:calls.append('POST:'+asof) or True)
        self.assertEqual(calls,['GET','GET'])
        self.assertEqual(result['status'],'BLOCKED_RECHECK_UNTRUSTED_RUN_PAGINATION')
        self.assertFalse(result['dispatch_requested'])

    def test_second_read_invalid_payload_fails_closed(self):
        calls=[]
        snapshots=[{'workflow_runs':[],'total_count':0},None]
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=lambda:calls.append('GET') or snapshots.pop(0),
                      request_dispatch=lambda asof:calls.append('POST:'+asof) or True)
        self.assertEqual(calls,['GET','GET'])
        self.assertEqual(result['status'],'BLOCKED_RECHECK_INVALID_GITHUB_RUN_RESPONSE')
        self.assertFalse(result['dispatch_requested'])



class NaturalSourceAmbiguityNegativeAcceptance(unittest.TestCase):
    """One successful schedule does not justify green health if another
    natural run or a manual rerun competes for that XNAS session.
    The fallback remains detection-only: never dispatch a child on HOLD.
    """
    NOW=utc('2026-10-27T00:25:00Z')

    def test_two_natural_schedules_even_with_one_success_are_not_healthy(self):
        for other in (
            record(status='completed',conclusion='success'),
            record(status='completed',conclusion='failure'),
            record(status='queued',conclusion=None),
            record(status='in_progress',conclusion=None),
        ):
            with self.subTest(other_status=other['status'],
                              conclusion=other['conclusion']):
                runs=[record(),other]
                for order in (runs,list(reversed(runs))):
                    status,day=sf.decision(self.NOW,order)
                    self.assertEqual(day,'2026-10-26')
                    self.assertEqual(status,
                                     'BLOCKED_CURRENT_EPOCH_DUPLICATE_NATURAL_RUN')
                    self.assertEqual(sf.exit_code_for_result(
                        {'status':status},'schedule'),3)

    def test_untrusted_attempt_cannot_masquerade_as_successful_natural_first(self):
        for attempt in (2,3,0,'1',None):
            with self.subTest(attempt=attempt):
                status,_=sf.decision(self.NOW,[record(run_attempt=attempt)])
                self.assertEqual(
                    status,'BLOCKED_CURRENT_EPOCH_NATURAL_RUN_NOT_FIRST_ATTEMPT')
                self.assertEqual(sf.exit_code_for_result(
                    {'status':status},'schedule'),3)

    def test_duplicate_schedule_never_calls_dispatch_callback(self):
        calls=[]
        items=[record(),record(status='queued',conclusion=None)]
        result=sf.run(now=self.NOW,
                      read_runs=lambda:calls.append('GET') or
                        {'workflow_runs':items,'total_count':2},
                      request_dispatch=lambda day:
                        calls.append('POST:'+day) or True,
                      trigger_event='schedule')
        self.assertEqual(result['status'],
                         'BLOCKED_CURRENT_EPOCH_DUPLICATE_NATURAL_RUN')
        self.assertFalse(result['dispatch_requested'])
        self.assertEqual(calls,['GET'])


class NaturalRunIdentityNegativeTests(unittest.TestCase):
    """An unbound GitHub status row cannot prove the canonical EOD source."""

    def test_missing_or_wrong_primary_source_identity_is_always_hold(self):
        good=record()
        invalid=(
            ("missing_id",{k:v for k,v in good.items() if k!="id"}),
            ("zero_id",{**good,"id":0}),
            ("bool_id",{**good,"id":True}),
            ("wrong_path",{**good,"path":".github/workflows/another.yml"}),
            ("missing_path",{k:v for k,v in good.items() if k!="path"}),
            ("other_repo",{**good,"repository":{"full_name":"evil/other"}}),
            ("missing_repo",{k:v for k,v in good.items() if k!="repository"}),
            ("unbound_sha",{**good,"head_sha":"Z"*40}),
            ("missing_sha",{k:v for k,v in good.items() if k!="head_sha"}),
        )
        for name,row in invalid:
            with self.subTest(name=name):
                status,asof=sf.decision(utc("2026-10-27T00:25:00Z"),[row])
                self.assertEqual(asof,"2026-10-26")
                self.assertEqual(status,
                                 "BLOCKED_CURRENT_EPOCH_NATURAL_PROVENANCE_UNVERIFIED")
                self.assertEqual(sf.exit_code_for_result(
                    {"status":status},"schedule"),3)

    def test_fake_source_never_suppresses_missing_canonical_eod(self):
        fake=record(id=42)
        fake["path"]=".github/workflows/xray-something-else.yml"
        calls=[]
        out=sf.run(
            now=utc("2026-10-27T00:25:00Z"),
            trigger_event="schedule",
            read_runs=lambda:calls.append("GET") or
                {"total_count":1,"workflow_runs":[fake]},
            request_dispatch=lambda day:calls.append("POST:"+day) or True)
        self.assertEqual(out["status"],
                         "BLOCKED_CURRENT_EPOCH_NATURAL_PROVENANCE_UNVERIFIED")
        self.assertEqual(calls,["GET"])
        self.assertFalse(out["dispatch_requested"])

    def test_current_real_github_shape_is_green_scheduler_only(self):
        status,asof=sf.decision(utc("2026-10-27T00:25:00Z"),[record()])
        self.assertEqual((status,asof),
                         ("NOOP_CURRENT_EPOCH_RUN_EXISTS","2026-10-26"))


class NaturalRunClockSanityTests(unittest.TestCase):
    """GitHub source created after the observer's clock cannot be green."""

    def test_future_natural_timestamp_over_five_second_skew_is_hold(self):
        now=utc('2026-10-27T00:25:00Z')
        for stamp in ('2026-10-27T00:25:06Z',
                      '2026-10-27T05:20:00Z'):
            with self.subTest(stamp=stamp):
                v,day=sf.decision(now,[record(created=stamp)])
                self.assertEqual(day,'2026-10-26')
                self.assertEqual(v,'BLOCKED_RUN_TIMESTAMP_IN_FUTURE')
                self.assertEqual(sf.exit_code_for_result(
                    {'status':v},'schedule'),3)

    def test_five_second_clock_skew_keeps_existing_provenance(self):
        status,asof=sf.decision(
            utc('2026-10-27T00:25:00Z'),
            [record(created='2026-10-27T00:25:05Z')])
        self.assertEqual((status,asof),
                         ('NOOP_CURRENT_EPOCH_RUN_EXISTS','2026-10-26'))

    def test_future_dated_source_never_calls_dispatch(self):
        calls=[]
        fake=record(created='2026-10-27T00:25:06Z')
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
            trigger_event='schedule',
            read_runs=lambda:calls.append('GET') or
                {'workflow_runs':[fake],'total_count':1},
            request_dispatch=lambda asof:calls.append('POST:'+asof))
        self.assertEqual(result['status'],'BLOCKED_RUN_TIMESTAMP_IN_FUTURE')
        self.assertFalse(result['dispatch_requested'])
        self.assertEqual(calls,['GET'])


class FallbackParentReceiptSafety(unittest.TestCase):
    """Evidence for later parent checks, never permission to emit A/B."""
    def setUp(self):
        self.env={
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'44850000001',
            'GITHUB_SHA':'a'*40,
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_REPOSITORY':'gokaydonmez39-jpg/kripto-radar',
        }
        self.accepted={
            'status':'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED',
            'dispatch_requested':True,'no_execution':True,
            'asof_et':'2026-11-20',
        }

    def test_genuine_scheduled_parent_request_emits_non_authoritative_witness(self):
        receipt=sf.scheduler_parent_receipt(self.accepted,self.env)
        self.assertEqual(receipt['schema'],'XRAY_477_FALLBACK_PARENT_RECEIPT_V1')
        self.assertEqual(receipt['parent_run_id'],44850000001)
        self.assertEqual(receipt['requested_asof_et'],'2026-11-20')
        self.assertEqual(receipt['parent_source_event'],'schedule')
        self.assertFalse(receipt['eod_completion_proven'])
        self.assertFalse(receipt['ab_release_authorized'])
        self.assertEqual((receipt['writes'],receipt['orders']),(0,0))

    def test_refuse_all_non_scheduled_or_wrong_origin(self):
        for key,value in (('GITHUB_EVENT_NAME','workflow_dispatch'),
                          ('GITHUB_EVENT_NAME','push'),
                          ('GITHUB_EVENT_NAME','pull_request'),
                          ('GITHUB_REPOSITORY','other/repo'),
                          ('GITHUB_REF','refs/heads/dev'),
                          ('GITHUB_SHA','x'*40),
                          ('GITHUB_SHA','a'*39),
                          ('GITHUB_RUN_ID','0'),
                          ('GITHUB_RUN_ID','not-an-id'),
                          ('GITHUB_RUN_ID','12.5')):
            with self.subTest(key=key,value=value):
                env=dict(self.env);env[key]=value
                self.assertIsNone(sf.scheduler_parent_receipt(self.accepted,env))

    def test_refuse_incomplete_or_ambiguous_dispatch(self):
        for key,value in (('status','BLOCKED_DISPATCH_NOT_CONFIRMED'),
                          ('status','DRY_RUN_WOULD_DISPATCH'),
                          ('status','NOOP_CURRENT_EPOCH_RUN_EXISTS'),
                          ('dispatch_requested',False),
                          ('dispatch_requested',1),
                          ('no_execution',False),
                          ('asof_et','2026-02-30'),
                          ('asof_et','2026-11-20T00:00:00Z'),
                          ('asof_et','2026-11-20-extra'),
                          ('asof_et',None)):
            with self.subTest(key=key,value=value):
                item=dict(self.accepted);item[key]=value
                self.assertIsNone(sf.scheduler_parent_receipt(item,self.env))

    def test_no_witness_when_missing_context(self):
        for key in self.env:
            env=dict(self.env);del env[key]
            with self.subTest(key=key):
                self.assertIsNone(sf.scheduler_parent_receipt(self.accepted,env))
        self.assertIsNone(sf.scheduler_parent_receipt(None,self.env))
        self.assertIsNone(sf.scheduler_parent_receipt(self.accepted,None))

    def test_witness_does_not_change_dispatch_decision(self):
        before=dict(self.accepted)
        _=sf.scheduler_parent_receipt(self.accepted,self.env)
        self.assertEqual(self.accepted,before)
        self.assertEqual(sf.decision(utc('2026-11-21T00:26:00Z'),[])[0],
                         'DISPATCH_ONE_MISSING_SCHEDULE')


class NaturalFallbackExitSemantics(unittest.TestCase):
    """Never mark a missing official EOD as success just because no POST ran."""

    def test_scheduled_gap_is_hard_failure_not_green(self):
        for status in (
            'DISPATCH_ONE_MISSING_SCHEDULE',
            'BLOCKED_DISPATCH_NOT_CONFIRMED',
            'BLOCKED_RECHECK_INVALID_GITHUB_RUN_RESPONSE',
            'BLOCKED_UNTRUSTED_RUN_PAGINATION',
            'BLOCKED_GITHUB_API_UNCERTAIN',
            'BLOCKED_NATURAL_FALLBACK_EXPIRED',
            'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_NOT_SUCCESS',
            'BLOCKED_CURRENT_EPOCH_NATURAL_EOD_INCOMPLETE',
            'BLOCKED_CURRENT_EPOCH_NON_NATURAL_SOURCE',
            'DRY_RUN_WOULD_DISPATCH',
            'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED',
            None,
        ):
            with self.subTest(status=status):
                self.assertEqual(
                    sf.exit_code_for_result({'status':status},'schedule'),3)

    def test_only_existence_or_official_calendar_noop_is_scheduled_success(self):
        for status in ('NOOP_CURRENT_EPOCH_RUN_EXISTS',
                       'NOOP_RECHECK_CURRENT_EPOCH_RUN_EXISTS',
                       'NOOP_SESSION_NOT_READY',
                       'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW'):
            self.assertEqual(
                sf.exit_code_for_result({'status':status},'schedule'),0)

    def test_manual_probe_is_not_scheduled_provenance(self):
        status='DRY_RUN_WOULD_DISPATCH'
        self.assertEqual(
            sf.exit_code_for_result({'status':status},'workflow_dispatch'),0)
        self.assertEqual(
            sf.exit_code_for_result({'status':status},'schedule'),3)
        self.assertEqual(sf.exit_code_for_result({
            'status':'DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED'},
            'workflow_dispatch'),3)

    def test_thanksgiving_is_normal_safe_noop_not_false_incident(self):
        # 27 Nov 00:26Z is Thanksgiving evening ET. No new XNAS EOD
        # exists and the previous completed session is outside the window.
        out=sf.run(now=utc('2026-11-27T00:26:00Z'),
                   read_runs=lambda: self.fail('NO_GITHUB_API_ON_HOLIDAY'),
                   request_dispatch=lambda asof:self.fail('NO_DISPATCH'))
        self.assertEqual(out['status'],'NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW')
        self.assertEqual(sf.exit_code_for_result(out,'schedule'),0)

    def test_missing_result_and_unknown_trigger_are_fail_closed(self):
        for obj,event in ((None,'schedule'),({},'schedule'),
                          ({'status':'NOOP_CURRENT_EPOCH_RUN_EXISTS'},'push'),
                          ({'status':'NOOP_CURRENT_EPOCH_RUN_EXISTS'},None)):
            with self.subTest(obj=obj,event=event):
                self.assertEqual(sf.exit_code_for_result(obj,event),3)


class AutomaticFallbackProvenanceGate(unittest.TestCase):
    def test_scheduler_must_not_dispatch_before_child_provenance_release(self):
        for event in ('schedule','push','pull_request','workflow_run',None,''):
            with self.subTest(event=event):
                self.assertFalse(sf.allow_dispatch_for_event(event))

    def test_unverified_manual_recovery_cannot_dispatch_or_impersonate_schedule(self):
        # Manual fallback does not have parent-child/CAS authority and
        # cannot safely obtain a canonical private EOD receipt.
        for event in ('workflow_dispatch', 'schedule', 'push', None):
            with self.subTest(event=event):
                self.assertFalse(sf.allow_dispatch_for_event(event))


class PrimaryEodPendingIsolationTests(unittest.TestCase):
    def test_offline_main_push_cannot_evict_pending_natural_eod(self):
        # Github's default concurrency can replace an older pending run.
        # An offline-only main push MUST have its own isolated test group.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / '.github' /
                  'workflows' / 'xray-personal-477-eod.yml').read_text(encoding='utf-8')
        groups = [line.strip() for line in source.splitlines()
                  if line.lstrip().startswith('group:')]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertIn("github.event_name == 'schedule' && github.run_attempt == 1 &&", group)
        self.assertIn("|| format('xray-personal-477-daily-eod-test-{0}', github.run_id)", group)
        self.assertIn("&& 'xray-personal-477-daily-eod' ||", group)
        self.assertIn('cancel-in-progress: false', source)
        self.assertEqual(source.count("    - cron: '16 23 * * 1-5'"), 1)


    def test_fallback_offline_checks_cannot_evict_scheduled_recovery(self):
        # The scheduled fallback must be insulated from PR and push checks.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / '.github' /
                  'workflows' / 'xray-personal-477-schedule-fallback.yml').read_text(encoding='utf-8')
        groups = [line.strip() for line in source.splitlines()
                  if line.lstrip().startswith('group:')]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertIn("github.event_name == 'schedule' && github.run_attempt == 1 &&", group)
        self.assertIn("|| format('xray-personal-477-scheduler-fallback-test-{0}', github.run_id)", group)
        self.assertIn("&& 'xray-personal-477-scheduler-fallback' ||", group)
        self.assertIn('cancel-in-progress: false', source)
        self.assertEqual(source.count("    - cron: '26 0 * * 2-6'"), 1)


class ManualEodSourceIsolation(unittest.TestCase):
    """Manual workflow invocations may run offline tests only.

    With canonical writer failing closed on workflow_dispatch, allowing the
    preceding 477-vendor scan is a partial side effect and no recovery.
    """
    def test_all_private_producers_require_natural_schedule(self):
        from pathlib import Path
        import re
        source=(Path(__file__).resolve().parents[1] / '.github' /
                'workflows' / 'xray-personal-477-eod.yml').read_text()
        # Match top-level two-space job blocks only; a plain split would
        # also break on nested four-space 'if' and 'needs' lines.
        names=(
            'daily-private-scan',
            'private-sheets-auth-preflight',
            'private-episode-followups',
            'guardian-acceptance',
            'daily-private-score-acceptance',
        )
        for name in names:
            with self.subTest(job=name):
                matched=re.search(r"(?ms)^  "+re.escape(name)+
                                  r":\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
                                  source)
                self.assertIsNotNone(matched)
                found=re.search(r"(?m)^    if: (.*)$",matched.group(1))
                self.assertIsNotNone(found)
                expr=found.group(1)
                self.assertIn("github.event_name == 'schedule'",expr)
                self.assertNotIn("workflow_dispatch",expr)
        self.assertEqual(source.count("    - cron: '16 23 * * 1-5'"),1)
        self.assertIn("  workflow_dispatch:",source)
        self.assertIn("    needs: offline-guard",source)
        self.assertIn("cancel-in-progress: false",source)


class DispatchCallbackPolicyIsolation(unittest.TestCase):
    """An injectable dispatch callback may never bypass release policy."""

    def test_locked_natural_and_manual_cannot_invoke_callback(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                reads=[]
                calls=[]
                def runs():
                    reads.append(1)
                    return {"total_count":0,"workflow_runs":[]}
                def forbidden(asof):
                    calls.append(asof)
                    raise AssertionError("POLICY_LOCK_BYPASSED_REQUEST_DISPATCH")
                result=sf.run(now=utc("2026-10-27T00:25:00Z"),
                              read_runs=runs,
                              request_dispatch=forbidden,
                              trigger_event=event)
                self.assertEqual(len(reads),2)
                self.assertEqual(calls,[])
                self.assertEqual(result["status"],"BLOCKED_DISPATCH_NOT_CONFIRMED")
                self.assertEqual(result["reason_code"],
                    "NATURAL_FALLBACK_POLICY_LOCKED" if event=="schedule"
                    else "MANUAL_FALLBACK_POLICY_LOCKED")
                self.assertFalse(result["dispatch_requested"])
                self.assertEqual(sf.exit_code_for_result(result,event),3)

class MissingEodFailureAttributionTests(unittest.TestCase):
    def test_natural_fallback_policy_lock_is_explicit_but_still_red(self):
        reads = []
        requests = []
        def runs():
            reads.append(True)
            return {'total_count':0,'workflow_runs':[]}
        def denied(asof):
            requests.append(asof)
            return False
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=runs,request_dispatch=denied,trigger_event='schedule')
        self.assertEqual(result['status'],'BLOCKED_DISPATCH_NOT_CONFIRMED')
        self.assertEqual(result['reason_code'],'NATURAL_FALLBACK_POLICY_LOCKED')
        self.assertEqual(result['dispatch_requested'],False)
        self.assertEqual(sf.exit_code_for_result(result,'schedule'),3)
        self.assertEqual(reads,[True,True])
        self.assertEqual(requests,[])

    def test_manual_recovery_policy_lock_is_explicit_and_nongreen(self):
        def runs():
            return {'total_count':0, 'workflow_runs':[]}
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=runs,request_dispatch=lambda _asof:
                      sf.allow_dispatch_for_event('workflow_dispatch'),
                      trigger_event='workflow_dispatch')
        self.assertEqual(result['status'],'BLOCKED_DISPATCH_NOT_CONFIRMED')
        self.assertEqual(result['dispatch_requested'],False)
        self.assertEqual(sf.exit_code_for_result(result,'workflow_dispatch'),3)

    def test_unconfirmed_explicit_manual_request_never_fake_ack(self):
        def runs():
            return {'total_count':0,'workflow_runs':[]}
        result=sf.run(now=utc('2026-10-27T00:25:00Z'),
                      read_runs=runs,request_dispatch=lambda asof:False,
                      trigger_event='workflow_dispatch')
        self.assertEqual(result['reason_code'],'MANUAL_FALLBACK_POLICY_LOCKED')
        self.assertEqual(result['status'],'BLOCKED_DISPATCH_NOT_CONFIRMED')
        self.assertEqual(sf.exit_code_for_result(result,'workflow_dispatch'),3)



class FallbackTokenPrivilegeIsolation(unittest.TestCase):
    """P0: detection-only fallback must not carry workflow-dispatch powers."""

    def test_github_job_token_is_read_only_with_exact_original_schedule(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / '.github' /
                  'workflows' / 'xray-personal-477-schedule-fallback.yml').read_text(
                      encoding='utf-8')
        job_marker = '  dispatch-if-missing:\n'
        self.assertEqual(source.count(job_marker), 1)
        job = source.split(job_marker, 1)[1]
        self.assertIn('    permissions:\n      contents: read\n      actions: read\n', job)
        self.assertNotIn('actions: write', source)
        self.assertEqual(source.count("    - cron: '26 0 * * 2-6'"), 1)
        self.assertIn("  workflow_dispatch:\n", source)

    def test_python_level_dispatch_remains_deny_by_default(self):
        for origin in ('schedule', 'workflow_dispatch', 'push',
                       'pull_request', 'workflow_run', None):
            with self.subTest(origin=origin):
                self.assertIs(sf.allow_dispatch_for_event(origin), False)


class PendingNaturalSourceQueueIsolation(unittest.TestCase):
    """Manual diagnostics must never evict a pending real scheduled EOD/A34."""

    @staticmethod
    def workflow(name):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / '.github' /
                'workflows' / name).read_text(encoding='utf-8')

    def test_canonical_eod_only_natural_schedule_uses_production_group(self):
        source=self.workflow('xray-personal-477-eod.yml')
        line=next(line.strip() for line in source.splitlines()
                  if line.lstrip().startswith('group:'))
        self.assertIn("github.event_name == 'schedule' && github.run_attempt == 1 && 'xray-personal-477-daily-eod'",line)
        self.assertIn("|| format('xray-personal-477-daily-eod-test-{0}', github.run_id)",line)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count("    - cron: '16 23 * * 1-5'"),1)

    def test_manual_fallback_cannot_displace_pending_natural_fallback(self):
        source=self.workflow('xray-personal-477-schedule-fallback.yml')
        line=next(line.strip() for line in source.splitlines()
                  if line.lstrip().startswith('group:'))
        self.assertIn("github.event_name == 'schedule' && github.run_attempt == 1 && 'xray-personal-477-scheduler-fallback'",line)
        self.assertIn("|| format('xray-personal-477-scheduler-fallback-test-{0}', github.run_id)",line)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count("    - cron: '26 0 * * 2-6'"),1)

    def test_a34_only_genuine_natural_sources_share_private_queue(self):
        source=self.workflow('xray-nasdaq-a34-preopen.yml')
        line=next(line.strip() for line in source.splitlines()
                  if line.lstrip().startswith('group:'))
        for fragment in (
            "github.run_attempt == 1 && (github.event_name == 'schedule'",
            "github.event_name == 'workflow_run'",
            "github.event.workflow_run.event == 'schedule'",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.run_attempt == 1",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.path == '.github/workflows/xray-personal-477-eod.yml'",
            "github.event.workflow_run.repository.full_name == github.repository",
            "&& 'xray-nasdaq-a34-private-preopen'",
            "|| format('xray-nasdaq-a34-test-{0}', github.run_id)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment,line)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count("    - cron: '17 3 * * 1-5'"),1)

if __name__=='__main__':
    unittest.main()
