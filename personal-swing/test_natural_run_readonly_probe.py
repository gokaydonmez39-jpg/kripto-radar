#!/usr/bin/env python3
"""No-network acceptance: real natural-run canary has GET-only authority."""
import unittest
from unittest.mock import patch

import epoch_lease as lease
from test_epoch_lease import MockGit, env, ASOF, NOW
import natural_run_readonly_probe as probe


def schedule_page(git, *, extra=(), total=None, rows=None):
    """Test-only GET response for the exact natural schedule collection."""
    current={
        "id":890123,"event":"schedule","path":lease.WORKFLOW,
        "head_branch":"main","head_sha":"a"*40,"run_attempt":1,
        "repository":{"full_name":lease.REPO},
        "created_at":"2026-11-23T22:03:00Z",
    }
    records=[current,*extra] if rows is None else rows
    def request(method,path,body=None):
        if method=="GET" and path.startswith("/actions/workflows/"):
            git.calls.append((method,path,body))
            return {"total_count":len(records) if total is None else total,
                    "workflow_runs":records}
        return git(method,path,body)
    return request


class NaturalReadOnlyCanary(unittest.TestCase):
    def test_exact_current_producer_requires_one_get_and_no_mutations(self):
        git=MockGit()
        out=probe.verify_once(env(),schedule_page(git),now=NOW,
                              completed_session=lambda _:ASOF)
        self.assertEqual(out["status"],"NATURAL_RUN_GITHUB_READ_ONLY_VERIFIED")
        self.assertEqual(out["asof_et"],ASOF)
        self.assertEqual(out["run_id"],890123)
        self.assertEqual(out["writes"],0)
        self.assertFalse(out["orders"])
        self.assertFalse(out["ab_release_authorized"])
        self.assertEqual(out["device_ack"],"UNKNOWN")
        self.assertEqual([(m,p) for m,p,_ in git.calls],
                         [("GET","/actions/runs/890123"),
                          ("GET",probe.schedule_runs_path(ASOF))])

    def test_forged_provider_cannot_promote_event_branch_sha_or_clock(self):
        variants=(
            ("event","workflow_dispatch"),
            ("path",".github/workflows/not-canonical.yml"),
            ("head_branch","other"),
            ("head_sha","b"*40),
            ("id",890124),
            ("run_attempt",2),
            ("status","completed"),
            ("created_at","2026-11-23T21:20:00Z"),
        )
        for key,bad in variants:
            with self.subTest(key=key):
                git=MockGit();git.run_overrides[key]=bad
                with self.assertRaisesRegex(lease.LeaseHold,
                         "LEASE_NATURAL_RUN_READBACK_UNVERIFIED"):
                    probe.verify_once(env(),git,now=NOW,
                                      completed_session=lambda _:ASOF)
                self.assertFalse(any(m=="POST" for m,_,_ in git.calls))


    def test_schedule_collection_query_is_exact_official_xnas_close_window(self):
        """Real dated evidence: 18 Nov EOD created 19 Nov UTC; do not count
        it as a competing 19 Nov source which was created on 20 Nov UTC.
        GitHub action receipts: 44456649926 and 44671232964.
        """
        stem="/actions/workflows/xray-personal-477-eod.yml/runs?"
        prefix=stem+"event=schedule&per_page=100&created="
        self.assertEqual(
            probe.schedule_runs_path("2026-11-19"),
            prefix+"2026-11-19T21:45:00Z..2026-11-20T07:45:00Z")
        self.assertEqual(
            probe.schedule_runs_path("2026-11-23"),
            prefix+"2026-11-23T21:45:00Z..2026-11-24T07:45:00Z")
        # Official Black Friday XNAS 13:00 NY early close => 18:45 UTC.
        self.assertEqual(
            probe.schedule_runs_path("2026-11-27"),
            prefix+"2026-11-27T18:45:00Z..2026-11-28T04:45:00Z")
        from datetime import datetime
        start=datetime.fromisoformat("2026-11-19T21:45:00+00:00")
        end=datetime.fromisoformat("2026-11-20T07:45:00+00:00")
        previous=datetime.fromisoformat("2026-11-19T04:11:58+00:00")
        current=datetime.fromisoformat("2026-11-20T03:58:10+00:00")
        self.assertFalse(start<=previous<=end)
        self.assertTrue(start<=current<=end)
        with self.assertRaisesRegex(
                lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
            probe.schedule_runs_path("2026-11-22")

    def test_competing_natural_run_any_status_is_blocked_before_private_scan(self):
        for state in ("queued","in_progress","completed"):
            with self.subTest(state=state):
                git=MockGit()
                duplicate={
                    "id":890124,"event":"schedule","path":lease.WORKFLOW,
                    "head_branch":"main","head_sha":"a"*40,
                    "run_attempt":1,"repository":{"full_name":lease.REPO},
                    "created_at":"2026-11-23T23:00:00Z","status":state,
                }
                with self.assertRaisesRegex(
                        lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
                    probe.verify_once(env(),schedule_page(git,extra=[duplicate]),
                                      now=NOW,completed_session=lambda _:ASOF)
                self.assertEqual(len(git.calls),2)
                self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_missing_hidden_or_forged_collection_never_passes(self):
        valid={
            "id":890123,"event":"schedule","path":lease.WORKFLOW,
            "head_branch":"main","head_sha":"a"*40,"run_attempt":1,
            "repository":{"full_name":lease.REPO},
            "created_at":"2026-11-23T22:03:00Z",
        }
        cases=(
            ("missing_current",[],0),
            ("hidden_second",[valid],2),
            ("truncated_page",[valid]*100,101),
            ("wrong_origin",[{**valid,"event":"workflow_dispatch"}],1),
            ("wrong_id",[{**valid,"id":890124}],1),
            ("created_drift",[{**valid,"created_at":"2026-11-23T22:04:00Z"}],1),
            ("missing_count",[valid],None),
        )
        for label,records,total in cases:
            with self.subTest(label=label):
                git=MockGit()
                def reply(method,path,body=None):
                    if method=="GET" and path.startswith("/actions/workflows/"):
                        git.calls.append((method,path,body))
                        return {"workflow_runs":records,
                                **({"total_count":total} if total is not None else {})}
                    return git(method,path,body)
                with self.assertRaisesRegex(
                        lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
                    probe.verify_once(env(),reply,now=NOW,
                                      completed_session=lambda _:ASOF)
                self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_schedule_collection_http_error_fails_closed(self):
        git=MockGit()
        def unavailable(method,path,body=None):
            if path.startswith("/actions/workflows/"):
                raise TimeoutError("simulated natural run list failure")
            return git(method,path,body)
        with self.assertRaisesRegex(
                lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
            probe.verify_once(env(),unavailable,now=NOW,
                              completed_session=lambda _:ASOF)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_bounded_collection_get_transport_never_allows_broad_or_mutating_api(self):
        def fail_if_authorized(*_args,**_kwargs):
            raise AssertionError("EXACT_ALLOWED_NATURAL_GET")
        tr=lease.github_transport("masked-offline-token",opener=fail_if_authorized)
        exact=probe.schedule_runs_path(ASOF)
        self.assertIn("event=schedule",exact)
        with self.assertRaisesRegex(AssertionError,"EXACT_ALLOWED_NATURAL_GET"):
            tr("GET",exact)
        for method,path in (
            ("POST",exact),
            ("GET",exact.replace("event=schedule","event=workflow_dispatch")),
            ("GET",exact.replace("per_page=100","per_page=1000")),
            ("GET",exact.split("created=",1)[0]+
                     "created=2026-11-19..2026-11-20"),
            ("GET",exact+"&page=2"),
            ("GET",exact.replace("xray-personal-477-eod.yml","other.yml")),
        ):
            with self.subTest(method=method,path=path):
                with self.assertRaisesRegex(lease.LeaseHold,"LEASE_API_PATH_INVALID"):
                    tr(method,path)

    def test_non_natural_runner_is_blocked_before_api_get(self):
        for field,value in (
            ("GITHUB_EVENT_NAME","workflow_dispatch"),
            ("GITHUB_REF","refs/heads/feature"),
            ("GITHUB_RUN_ATTEMPT","2"),
            ("GITHUB_REPOSITORY","untrusted/repo"),
        ):
            with self.subTest(field=field):
                e=env();e[field]=value
                git=MockGit()
                with self.assertRaises(lease.LeaseHold):
                    probe.verify_once(e,git,now=NOW,
                                      completed_session=lambda _:ASOF)
                self.assertEqual(git.calls,[])

    def test_provider_failure_is_hold_without_writes(self):
        def unavailable(method,path,body=None):
            raise TimeoutError("simulated network loss")
        with self.assertRaisesRegex(
             lease.LeaseHold,"NATURAL_RUN_READ_ONLY_GET_UNAVAILABLE"):
            probe.verify_once(env(),unavailable,now=NOW,
                              completed_session=lambda _:ASOF)

    def test_no_session_never_contacts_provider(self):
        git=MockGit()
        with self.assertRaises(lease.LeaseHold):
            probe.verify_once(env(),git,now=NOW,
                              completed_session=lambda _:None)
        self.assertEqual(git.calls,[])

    def test_cli_rejects_unapproved_actions_without_http(self):
        with patch.object(probe.lease,"github_transport") as transport:
            self.assertNotEqual(probe.main([]),0)
            self.assertNotEqual(probe.main(["--claim","2026-11-23"]),0)
            transport.assert_not_called()

    def test_cli_requires_token_and_github_repository(self):
        with patch.dict("os.environ",{"GITHUB_REPOSITORY":lease.REPO,
                                      "GITHUB_TOKEN":""},clear=True):
            with patch.object(probe.lease,"github_transport") as transport:
                self.assertNotEqual(probe.main(["--verify"]),0)
                transport.assert_not_called()


class BoundedNaturalGetRecoveryTests(unittest.TestCase):
    """Retry only transient read-side lag; never loosen source admission."""

    def test_empty_index_then_exact_natural_page_recovers_with_get_only(self):
        git=MockGit(); original=schedule_page(git)
        pages=[{"total_count":0,"workflow_runs":[]}]
        delays=[]
        def transport(method,path,body=None):
            if method=="GET" and path.startswith("/actions/workflows/") and pages:
                git.calls.append((method,path,body))
                return pages.pop(0)
            return original(method,path,body)
        result=probe.verify_bounded(
            env(),transport,now_factory=lambda:NOW,
            pause=lambda seconds:delays.append(seconds),
            completed_session=lambda _:ASOF)
        self.assertEqual(result["source_get_attempts"],2)
        self.assertEqual(len(delays),1)
        self.assertTrue(0<delays[0]<=5)
        self.assertEqual([m for m,_,_ in git.calls],
                         ["GET","GET","GET","GET"])
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_transient_run_receipt_timeout_can_recover(self):
        git=MockGit(); original=schedule_page(git)
        first=[True]; delays=[]
        def transport(method,path,body=None):
            if path=="/actions/runs/890123" and first[0]:
                first[0]=False
                git.calls.append((method,path,body))
                raise TimeoutError("simulated transient GitHub read timeout")
            return original(method,path,body)
        result=probe.verify_bounded(
            env(),transport,now_factory=lambda:NOW,
            pause=lambda seconds:delays.append(seconds),
            completed_session=lambda _:ASOF)
        self.assertEqual(result["source_get_attempts"],2)
        self.assertEqual(len(delays),1)
        self.assertEqual([m for m,_,_ in git.calls],
                         ["GET","GET","GET"])

    def test_persistent_empty_index_fails_closed_after_exactly_three_gets(self):
        git=MockGit(); calls=[]; pauses=[]
        def transport(method,path,body=None):
            calls.append((method,path))
            if path.startswith("/actions/workflows/"):
                return {"total_count":0,"workflow_runs":[]}
            return git(method,path,body)
        with self.assertRaises(lease.LeaseHold):
            probe.verify_bounded(
                env(),transport,now_factory=lambda:NOW,
                pause=lambda seconds:pauses.append(seconds),
                completed_session=lambda _:ASOF)
        self.assertEqual(len(calls),6)
        self.assertEqual(len(pauses),2)
        self.assertEqual({m for m,_ in calls},{"GET"})

    def test_two_natural_rows_never_retry_or_call_side_effects(self):
        git=MockGit()
        second={"id":890124,"event":"schedule","path":lease.WORKFLOW,
                "head_branch":"main","head_sha":"a"*40,"run_attempt":1,
                "repository":{"full_name":lease.REPO},
                "created_at":"2026-11-23T23:01:00Z"}
        delays=[]
        with self.assertRaisesRegex(lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
            probe.verify_bounded(
                env(),schedule_page(git,extra=[second]),
                now_factory=lambda:NOW,
                pause=lambda seconds:delays.append(seconds),
                completed_session=lambda _:ASOF)
        self.assertEqual(delays,[])
        self.assertEqual(len(git.calls),2)
        self.assertTrue(all(m=="GET" for m,_,_ in git.calls))

    def test_forged_first_run_never_retries(self):
        git=MockGit(); git.run_overrides["head_sha"]="b"*40
        pauses=[]
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_NATURAL_RUN_READBACK_UNVERIFIED"):
            probe.verify_bounded(
                env(),schedule_page(git),now_factory=lambda:NOW,
                pause=lambda seconds:pauses.append(seconds),
                completed_session=lambda _:ASOF)
        self.assertEqual(pauses,[])
        self.assertEqual(len(git.calls),1)

    def test_http_403_is_not_a_transient_retry(self):
        from urllib.error import HTTPError
        calls=[]; delays=[]
        def rejected(method,path,body=None):
            calls.append(method)
            raise HTTPError("https://api.github.com/",403,"FORBIDDEN",None,None)
        with self.assertRaises(lease.LeaseHold):
            probe.verify_bounded(
                env(),rejected,now_factory=lambda:NOW,
                pause=lambda seconds:delays.append(seconds),
                completed_session=lambda _:ASOF)
        self.assertEqual(calls,["GET"])
        self.assertEqual(delays,[])

    def test_freshness_window_expiration_stops_without_more_io(self):
        from datetime import timedelta
        git=MockGit(); calls=[]; delays=[]
        later=NOW+timedelta(hours=20)
        clocks=iter((NOW,later))
        def empty_index(method,path,body=None):
            calls.append((method,path))
            if path.startswith("/actions/workflows/"):
                return {"total_count":0,"workflow_runs":[]}
            return git(method,path,body)
        with self.assertRaises(lease.LeaseHold):
            probe.verify_bounded(
                env(),empty_index,now_factory=lambda:next(clocks),
                pause=lambda seconds:delays.append(seconds),
                completed_session=lambda instant:ASOF if instant==NOW else None)
        self.assertEqual(len(calls),2)
        self.assertEqual(len(delays),1)
        self.assertTrue(all(m=="GET" for m,_ in calls))



# The existing normal and optimized EOD offline suites discover this class.
from test_recovery_owner_collection import OwnedCollectionTests

class RecoveryOwnerShadowIntegration(unittest.TestCase):
    def setup_claim(self):
        from test_epoch_lease import claim, natural
        git=MockGit()
        claim(natural(),git)
        git.calls.clear()
        return git

    def transport(self, git, *, early=False, incomplete=False):
        def read(method,path,body=None):
            if method=="GET" and path.startswith("/actions/workflows/"):
                git.calls.append((method,path,body))
                current=dict(git.run_context.receipt)
                other=dict(current,id=890124,status="queued",
                           created_at="2026-11-23T22:04:59Z" if early else "2026-11-23T22:06:00Z",
                           updated_at="2026-11-23T22:06:00Z")
                return {"total_count":3 if incomplete else 2,
                        "workflow_runs":[current,other]}
            return git(method,path,body)
        return read

    def consume(self, git, *, shadow=False, run="890123", early=False, incomplete=False):
        from datetime import timedelta
        return lease.verify_existing_tag_consumer(
            ASOF,self.transport(git,early=early,incomplete=incomplete),
            now=NOW+timedelta(minutes=2),runtime_env=env(run),
            completed_session=lambda _:ASOF,recovery_owner_shadow=shadow)

    def test_late_competitor_shadow_has_distinct_non_authorizing_receipt(self):
        git=self.setup_claim()
        out=self.consume(git,shadow=True)
        self.assertEqual(out["state"],"LEASE_RECOVERY_OWNER_SHADOW_READBACK_ONLY")
        self.assertEqual(out["recovery_owner_shadow"]["later_competitors"],1)
        self.assertFalse(out["write_authority"])
        self.assertFalse(out["ab_release_authorized"])
        self.assertEqual(out["sheet_writes"],0)
        self.assertTrue(all(method=="GET" for method,_,_ in git.calls))

    def test_default_path_still_rejects_duplicate(self):
        git=self.setup_claim()
        with self.assertRaisesRegex(lease.LeaseHold,"NATURAL_EOD_EPOCH_AMBIGUOUS"):
            self.consume(git)
        self.assertTrue(all(method=="GET" for method,_,_ in git.calls))

    def test_other_run_cannot_borrow_owner_even_in_shadow(self):
        git=self.setup_claim()
        with self.assertRaisesRegex(lease.LeaseHold,"LEASE_CONSUMER_OWNER_MISMATCH"):
            self.consume(git,shadow=True,run="890124")
        self.assertTrue(all(method=="GET" for method,_,_ in git.calls))

    def test_earlier_competitor_and_partial_page_hold(self):
        for kwargs in ({"early":True},{"incomplete":True}):
            git=self.setup_claim()
            with self.assertRaisesRegex(lease.LeaseHold,"RECOVERY_OWNER_COLLECTION_SHADOW_HOLD"):
                self.consume(git,shadow=True,**kwargs)
            self.assertTrue(all(method=="GET" for method,_,_ in git.calls))

    def test_revoked_protection_does_not_pass_shadow(self):
        git=self.setup_claim()
        git.protection="disabled"
        with self.assertRaises(lease.LeaseHold):
            self.consume(git,shadow=True)
        self.assertTrue(all(method=="GET" for method,_,_ in git.calls))


if __name__=="__main__":
    unittest.main()
