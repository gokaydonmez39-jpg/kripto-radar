#!/usr/bin/env python3
"""Adversarial, IO-free tests for atomic 477 Git-tag epoch claim."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from hashlib import sha1
from threading import Barrier, Lock
from urllib.error import HTTPError
import json
import unittest

import epoch_lease as lease

ASOF="2026-11-23"
NOW=datetime(2026,11,23,22,5,tzinfo=timezone.utc)


def env(run="890123",event="schedule"):
    return {
        "GITHUB_SHA":"a"*40,
        "GITHUB_RUN_ID":run,
        "GITHUB_REF":"refs/heads/main",
        "GITHUB_REPOSITORY":lease.REPO,
        "GITHUB_WORKFLOW_REF":
            lease.REPO+"/"+lease.WORKFLOW+"@refs/heads/main",
        "GITHUB_EVENT_NAME":event,
        "GITHUB_RUN_ATTEMPT":"1",
    }


def natural(run="890123"):
    return lease.verified_natural_owner(
        env(run),ASOF,NOW,completed_session=lambda _:ASOF)


def claim(owner, transport):
    # Fixed source clock only for offline, no-I/O regression tests.
    # Production acquire_first_claim uses its actual UTC clock.
    return lease.acquire_first_claim(owner, transport, now=NOW,
                                     runtime_env=env(str(owner["run_id"])))


class MockGit:
    """Atomic fake reference endpoint; multiple tag objects may coexist."""
    def __init__(self, *, rendezvous=0):
        self.lock=Lock()
        self.tags={}
        self.refs={}
        self.calls=[]
        self.barrier=Barrier(rendezvous) if rendezvous else None
        self.tamper=None
        self.protection="valid"
        self.disable_after_ref=False
        self.run_overrides={}

    def __call__(self,method,path,body=None):
        with self.lock:
            self.calls.append((method,path,copy.deepcopy(body)))
        if method=="GET" and path.startswith("/actions/runs/"):
            rid=path.split("/")[-1]
            receipt={
                "id":int(rid),"run_attempt":1,"event":"schedule",
                "path":lease.WORKFLOW,"head_branch":"main",
                "head_sha":"a"*40,
                "repository":{"full_name":lease.REPO},
                "status":"in_progress","conclusion":None,
                "created_at":"2026-11-23T22:03:00Z",
                "updated_at":"2026-11-23T22:04:00Z",
            }
            receipt.update(self.run_overrides)
            return receipt
        if method=="GET" and path=="/rulesets":
            if self.protection=="absent":
                return [{"id":1,"target":"branch","enforcement":"active"}]
            return [{"id":11,"target":"tag","enforcement":"active"}]
        if method=="GET" and path=="/rulesets/11":
            types=["update","deletion","non_fast_forward"]
            if self.protection=="no_update":
                types=["deletion","non_fast_forward"]
            if self.protection=="no_non_fast_forward":
                types=["update","deletion"]
            return {
                "id":11,"target":"tag",
                "enforcement":"disabled" if self.protection=="disabled" else "active",
                "conditions":{"ref_name":{
                    "include":[lease.PROTECTED_PATTERN],
                    "exclude":[]}},
                "rules":[{"type":r} for r in types],
                **({} if self.protection=="bypass_hidden" else
                   {"bypass_actors":[{"actor_id":1}] if self.protection=="bypass" else []}),
            }
        if method=="POST" and path=="/git/tags":
            tag_sha=sha1(json.dumps(body,sort_keys=True).encode()).hexdigest()
            with self.lock:
                self.tags[tag_sha]=dict(body,sha=tag_sha)
            if self.barrier is not None:
                self.barrier.wait(timeout=6)
            return {"sha":tag_sha}
        if method=="POST" and path=="/git/refs":
            with self.lock:
                if body["ref"] in self.refs:
                    raise HTTPError("https://fake.invalid",422,"duplicate",None,None)
                self.refs[body["ref"]]=body["sha"]
                if self.disable_after_ref:
                    self.protection="disabled"
            return {"ref":body["ref"],
                    "object":{"type":"tag","sha":body["sha"]}}
        if method=="GET" and path.startswith("/git/ref/tags/"):
            key="refs/tags/"+path[len("/git/ref/tags/"):]
            with self.lock:
                sha=self.refs[key]
            return {"ref":key,"object":{"type":"tag","sha":sha}}
        if method=="GET" and path.startswith("/git/tags/"):
            sha=path[len("/git/tags/"):]
            with self.lock:
                record=copy.deepcopy(self.tags[sha])
            observed={"tag":record["tag"],"sha":sha,
                "message":record["message"],
                "object":{"type":"commit","sha":record["object"]}}
            if self.tamper=="message":
                observed["message"]+=";FORGED"
            if self.tamper=="commit":
                observed["object"]["sha"]="f"*40
            return observed
        raise AssertionError("UNEXPECTED_VENDOR_CALL_"+method+"_"+path)


class NaturalLeaseOwnerGate(unittest.TestCase):
    def test_exact_natural_producer_and_current_official_session(self):
        owner=natural()
        self.assertEqual(owner["asof_et"],ASOF)
        self.assertEqual(owner["source_event"],"schedule")
        self.assertEqual(owner["ref"],lease.REF_PREFIX+ASOF)
        self.assertEqual(owner["run_id"],890123)

    def test_bad_identity_is_never_a_producer(self):
        changes={
            "GITHUB_EVENT_NAME":["workflow_dispatch","push","workflow_run"],
            "GITHUB_REF":["refs/heads/dev","refs/heads/main/other"],
            "GITHUB_REPOSITORY":["wrong/repo"],
            "GITHUB_WORKFLOW_REF":[lease.REPO+"/"+lease.WORKFLOW+"@refs/heads/dev",
                                   lease.REPO+"/.github/workflows/fallback.yml@refs/heads/main"],
            "GITHUB_RUN_ATTEMPT":["2","0",""],
            "GITHUB_SHA":["bad","F"*40],
            "GITHUB_RUN_ID":["0","0x345",""],
        }
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key,value=value):
                    e=env();e[key]=value
                    with self.assertRaisesRegex(lease.LeaseHold,
                                               "LEASE_NATURAL_PRODUCER_UNVERIFIED"):
                        lease.verified_natural_owner(
                            e,ASOF,NOW,completed_session=lambda _:ASOF)

    def test_never_use_wrong_or_expired_session(self):
        for wrong in ("2026-11-20","2026-11-24",None):
            with self.subTest(wrong=wrong):
                with self.assertRaisesRegex(lease.LeaseHold,
                            "LEASE_XNAS_CURRENT_WINDOW_UNVERIFIED"):
                    lease.verified_natural_owner(
                        env(),ASOF,NOW,completed_session=lambda _:wrong)

    def test_calendar_or_clock_error_fail_closed(self):
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_XNAS_CURRENT_WINDOW_UNVERIFIED"):
            lease.verified_natural_owner(
                env(),ASOF,NOW,
                completed_session=lambda _:1/0)
        with self.assertRaisesRegex(lease.LeaseHold,"LEASE_CLOCK_UNKNOWN"):
            lease.verified_natural_owner(
                env(),ASOF,datetime(2026,11,23,22,5),
                completed_session=lambda _:ASOF)

    def test_invalid_date_rejected(self):
        for asof in ("2026-02-30","2026-11-3","2026-11-23;rm -rf /",""):
            with self.subTest(asof=asof):
                with self.assertRaisesRegex(lease.LeaseHold,"EPOCH_DATE_INVALID"):
                    lease.verified_natural_owner(
                        env(),asof,NOW,completed_session=lambda _:asof)


class FirstClaimAndReadback(unittest.TestCase):
    def test_one_success_is_source_only_not_sheet_or_device(self):
        git=MockGit()
        owner=natural()
        out=claim(owner,git)
        self.assertEqual(out["state"],"FIRST_CLAIM_READBACK_VERIFIED_NOT_EOD")
        self.assertFalse(out["ab_release_authorized"])
        self.assertEqual(out["sheet_writes"],0)
        self.assertFalse(out["orders"])
        self.assertEqual(out["device_ack"],"UNKNOWN")
        self.assertEqual(
            [(method,path) for method,path,_ in git.calls],
            [("GET","/actions/runs/"+str(owner["run_id"])),
             ("GET","/rulesets"),("GET","/rulesets/11"),
             ("POST","/git/tags"),("POST","/git/refs"),
             ("GET","/git/ref/tags/"+owner["tag"]),
             ("GET","/git/tags/"+out["tag_sha"]),
             ("GET","/rulesets"),("GET","/rulesets/11")])
        manifest=json.loads(git.tags[out["tag_sha"]]["message"])
        self.assertEqual(manifest["run_id"],owner["run_id"])
        self.assertEqual(manifest["asof_et"],ASOF)
        self.assertNotIn("secret",manifest)
        self.assertNotIn("symbol",manifest)

    def test_actual_github_run_receipt_must_match_before_claim(self):
        variants=(
            ("id",890124),
            ("event","workflow_dispatch"),
            ("path",".github/workflows/foreign.yml"),
            ("head_branch","dev"),
            ("head_sha","b"*40),
            ("run_attempt",2),
            ("repository",{"full_name":"other/repo"}),
            ("status","completed"),
            ("conclusion","failure"),
            ("created_at","2026-11-24T00:00:00Z"),
            ("created_at","2026-11-23T21:20:00Z"),
            ("updated_at","2026-11-24T00:00:00Z"),
        )
        for key,bad in variants:
            with self.subTest(key=key):
                git=MockGit();git.run_overrides={key:bad}
                with self.assertRaisesRegex(
                        lease.LeaseHold,"LEASE_NATURAL_RUN_READBACK_UNVERIFIED"):
                    claim(natural(),git)
                self.assertFalse(any(method=="POST" for method,_,_ in git.calls))
                self.assertEqual(git.refs,{})

    def test_unavailable_real_run_receipt_is_never_authority(self):
        git=MockGit()
        def gone(method,path,body=None):
            if method=="GET" and path.startswith("/actions/runs/"):
                raise TimeoutError("ambiguous GitHub GET")
            return git(method,path,body)
        with self.assertRaisesRegex(
                lease.LeaseHold,"LEASE_GITHUB_TRANSPORT_UNCERTAIN"):
            claim(natural(),gone)
        self.assertEqual(git.tags,{})
        self.assertEqual(git.refs,{})

    def test_idempotent_retry_cannot_repeat_first_claim(self):
        git=MockGit()
        claim(natural(),git)
        with self.assertRaisesRegex(lease.LeaseHold,
                                   "LEASE_REF_COLLISION_OR_PROVIDER_REJECTION"):
            claim(natural(),git)
        self.assertEqual(len(git.refs),1)

    def test_two_distinct_writers_race_one_wins(self):
        git=MockGit(rendezvous=2)
        def one(id):
            try:
                return claim(natural(id),git)
            except lease.LeaseHold as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(one,("890123","890124")))
        good=[x for x in results if isinstance(x,dict)]
        bad=[x for x in results if isinstance(x,str)]
        self.assertEqual(len(good),1,results)
        self.assertEqual(bad,["LEASE_REF_COLLISION_OR_PROVIDER_REJECTION"])
        self.assertEqual(len(git.refs),1)
        self.assertEqual(len(git.tags),2)

    def test_independent_tag_message_or_commit_drift_blocks_claim(self):
        for mutation in ("message","commit"):
            with self.subTest(mutation=mutation):
                git=MockGit();git.tamper=mutation
                with self.assertRaisesRegex(lease.LeaseHold,
                                            "LEASE_READBACK_CONFLICT"):
                    claim(natural(),git)

    def test_ruleset_revoked_mid_claim_never_authorizes_writer(self):
        # The Git tag may already exist; a now-unprotected ref is NOT a
        # valid one-writer lease. No Sheet or A/B authorization may follow.
        git=MockGit()
        git.disable_after_ref=True
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_TAG_PROTECTION_UNVERIFIED"):
            claim(natural(),git)
        self.assertEqual(len(git.refs),1)
        self.assertEqual(len(git.tags),1)
        self.assertEqual(git.protection,"disabled")

    def test_missing_post_receipt_and_error_are_not_authority(self):
        for response in (None,{},{"sha":"malformed"}):
            with self.subTest(response=response):
                git=MockGit()
                def incomplete(method,path,body=None):
                    if method=="POST" and path=="/git/tags":
                        git.calls.append((method,path,copy.deepcopy(body)))
                        return response
                    return git(method,path,body)
                with self.assertRaisesRegex(lease.LeaseHold,
                                            "LEASE_TAG_OBJECT_UNVERIFIED"):
                    claim(natural(),incomplete)
                self.assertEqual(
                    [(m,p) for m,p,_ in git.calls],
                    [("GET","/actions/runs/"+str(natural()["run_id"])),
                     ("GET","/rulesets"),("GET","/rulesets/11"),
                     ("POST","/git/tags")])

    def test_transport_timeout_does_not_retry_post(self):
        git=MockGit()
        calls=[]
        def lost(method,path,body=None):
            if method=="POST":
                calls.append((method,path))
                raise TimeoutError("ambiguous write")
            return git(method,path,body)
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_GITHUB_TRANSPORT_UNCERTAIN"):
            claim(natural(),lost)
        self.assertEqual(calls,[("POST","/git/tags")])

    def test_untrusted_mutated_owner_cannot_acquire(self):
        for key,value in (("source_event","workflow_dispatch"),
                          ("run_attempt",2),("tag","foreign"),
                          ("ref","refs/tags/forged"),("source_sha","g"*40)):
            with self.subTest(key=key):
                owner=natural();owner[key]=value
                git=MockGit()
                with self.assertRaisesRegex(lease.LeaseHold,
                                            "LEASE_OWNER_CONTRACT_INVALID"):
                    claim(owner,git)
                self.assertEqual(git.calls,[])

    def test_absent_or_mutable_tag_namespace_blocks_before_any_post(self):
        for mode in ("absent","disabled","bypass","no_update"):
            with self.subTest(mode=mode):
                git=MockGit()
                git.protection=mode
                with self.assertRaisesRegex(
                        lease.LeaseHold,"LEASE_TAG_PROTECTION_UNVERIFIED"):
                    claim(natural(),git)
                self.assertFalse(
                    any(method=="POST" for method,_,_ in git.calls))

    def test_invalid_asof_must_not_ever_write_permanent_tag(self):
        for asof in ("2026-02-30","2026-11-3","2099-01-01","2026-11-22"):
            with self.subTest(asof=asof):
                owner=natural()
                owner["asof_et"]=asof
                owner["tag"]=lease.TAG_PREFIX+asof
                owner["ref"]=lease.REF_PREFIX+asof
                git=MockGit()
                with self.assertRaisesRegex(
                    lease.LeaseHold,"LEASE_OWNER_CONTRACT_INVALID"):
                    claim(owner,git)
                self.assertEqual(git.calls,[])
                self.assertEqual(git.refs,{})

    def test_invalid_or_unbounded_observation_must_not_write(self):
        invalid=("invalid",None,1,"2026-11-23T22:05:00+03:00",
                 "2026-11-23T22:05:00","2026-11-24T15:05:00Z",
                 "2026-11-20T22:05:00Z")
        for at in invalid:
            with self.subTest(value=at):
                owner=natural()
                owner["observed_at"]=at
                git=MockGit()
                with self.assertRaisesRegex(
                    lease.LeaseHold,"LEASE_OWNER_CONTRACT_INVALID"):
                    claim(owner,git)
                self.assertEqual(git.calls,[])

    def test_fresh_asof_with_stale_timestamp_is_denied_before_vendor(self):
        owner=natural()
        owner["observed_at"]=(NOW-timedelta(minutes=11)).isoformat().replace("+00:00","Z")
        git=MockGit()
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_OWNER_CONTRACT_INVALID"):
            claim(owner,git)
        self.assertEqual(git.calls,[])

    def test_http_transport_only_exact_lease_endpoints(self):
        def fail_on_network(*_args,**_kwargs):
            raise AssertionError("UNAUTHORIZED_VENDOR_REQUEST_SENT")
        tr=lease.github_transport("redacted",opener=fail_on_network)
        for method,path in (
            ("POST","/git/commits"),("POST","/git/blobs"),
            ("POST","/git/ref/tags/forged"),
            ("POST","/rulesets"),
            ("GET","/git/blobs/"+"a"*40),
            ("GET","/git/ref/heads/main"),
            ("GET","/git/tags/not-a-sha"),
            ("GET","/git/ref/tags/xray-not-personal477-epoch-2026-11-23"),
            ("GET","/rulesets/01"),
            ("GET","/actions/runs/not-an-id"),
            ("GET","/actions/runs/01"),
            ("GET","/actions/runs/890123/jobs"),
            ("POST","/actions/runs/890123"),
        ):
            with self.subTest(method=method,path=path):
                with self.assertRaisesRegex(
                    lease.LeaseHold,"LEASE_API_PATH_INVALID"):
                    tr(method,path,{} if method=="POST" else None)

    def test_only_exact_run_get_is_a_read_route(self):
        def fail_on_network(*_args,**_kwargs):
            raise AssertionError("EXACT_ALLOWED_GITHUB_GET_PATH")
        tr=lease.github_transport("masked-test-token",opener=fail_on_network)
        with self.assertRaisesRegex(
                AssertionError,"EXACT_ALLOWED_GITHUB_GET_PATH"):
            tr("GET","/actions/runs/890123")

    def test_untrusted_github_runtime_source_cannot_claim_natural(self):
        import os
        from unittest.mock import patch
        adversaries=(
            ("GITHUB_EVENT_NAME","workflow_dispatch"),
            ("GITHUB_EVENT_NAME","push"),
            ("GITHUB_REPOSITORY","other/repository"),
            ("GITHUB_REF","refs/heads/dev"),
            ("GITHUB_WORKFLOW_REF",lease.REPO+"/.github/workflows/other.yml@refs/heads/main"),
            ("GITHUB_RUN_ATTEMPT","2"),
            ("GITHUB_SHA","b"*40),
            ("GITHUB_RUN_ID","890999"),
        )
        for key,bad in adversaries:
            with self.subTest(key=key,bad=bad):
                runtime=env()
                runtime[key]=bad
                git=MockGit()
                with patch.dict(os.environ,runtime,clear=True):
                    with self.assertRaisesRegex(
                        lease.LeaseHold,
                        "LEASE_NATURAL_PRODUCER_UNVERIFIED|LEASE_OWNER_PROVENANCE_UNVERIFIED"):
                        lease.acquire_first_claim(natural(),git,now=NOW)
                self.assertEqual(git.calls,[])
                self.assertEqual(git.refs,{})

    def test_missing_live_github_env_must_never_claim(self):
        import os
        from unittest.mock import patch
        git=MockGit()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(
                lease.LeaseHold,"LEASE_NATURAL_PRODUCER_UNVERIFIED"):
                lease.acquire_first_claim(natural(),git,now=NOW)
        self.assertEqual(git.calls,[])

    def test_missing_token_is_fail_closed(self):
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_GITHUB_TOKEN_NOT_CONFIGURED"):
            lease.github_transport("")
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_API_PATH_INVALID"):
            lease.github_transport("redacted")("POST","/untrusted",{})


class ExistingLeaseConsumerReadback(unittest.TestCase):
    """No second tag write: consumer must prove the unique current owner."""

    def consumed(self, git, *, run="890123", now=NOW, runtime=None):
        return lease.verify_existing_tag_consumer(
            ASOF,git,now=now,
            runtime_env=env(run) if runtime is None else runtime,
            completed_session=lambda _:ASOF)

    def test_existing_owner_can_be_revalidated_twice_without_post(self):
        git=MockGit()
        claim(natural(),git)
        git.calls.clear()
        for _ in range(2):
            result=self.consumed(git)
            self.assertEqual(result["state"],"LEASE_OWNER_READBACK_ONLY")
            self.assertEqual(result["run_id"],890123)
            self.assertEqual(result["sheet_writes"],0)
            self.assertFalse(result["ab_release_authorized"])
            self.assertFalse(result["orders"])
            self.assertEqual(result["device_ack"],"UNKNOWN")
        self.assertTrue(git.calls)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_other_run_id_cannot_borrow_existing_lease(self):
        git=MockGit()
        claim(natural(),git)
        git.calls.clear()
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_CONSUMER_OWNER_MISMATCH"):
            self.consumed(git,run="890124")
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_tag_message_and_underlying_commit_drift_are_denied(self):
        for mode in ("message","commit"):
            with self.subTest(mode=mode):
                git=MockGit()
                claim(natural(),git)
                git.tamper=mode
                git.calls.clear()
                with self.assertRaisesRegex(lease.LeaseHold,
                                             "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED"):
                    self.consumed(git)
                self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_missing_tag_never_grants_consumer(self):
        git=MockGit()
        with self.assertRaisesRegex(lease.LeaseHold,
                                     "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED"):
            self.consumed(git)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_tag_immutability_revoked_cannot_authorize(self):
        git=MockGit()
        claim(natural(),git)
        git.protection="disabled"
        git.calls.clear()
        with self.assertRaisesRegex(lease.LeaseHold,
                                     "LEASE_TAG_PROTECTION_UNVERIFIED"):
            self.consumed(git)
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_non_natural_consumer_is_rejected_before_vendor(self):
        for name,value in (
            ("GITHUB_EVENT_NAME","workflow_dispatch"),
            ("GITHUB_REF","refs/heads/feature"),
            ("GITHUB_RUN_ATTEMPT","2"),
        ):
            with self.subTest(name=name):
                git=MockGit()
                e=env();e[name]=value
                with self.assertRaises(lease.LeaseHold):
                    self.consumed(git,runtime=e)
                self.assertEqual(git.calls,[])

    def test_stale_owner_epoch_does_not_gain_write_authority(self):
        git=MockGit()
        claim(natural(),git)
        with self.assertRaises(lease.LeaseHold):
            self.consumed(git,now=NOW+timedelta(hours=11))
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls[-4:]))


class LiveTagReadonlyCanaryTests(unittest.TestCase):
    def test_missing_non_fast_forward_rule_cannot_authorize_tag_claim(self):
        git=MockGit()
        git.protection="no_non_fast_forward"
        with self.assertRaisesRegex(
                lease.LeaseHold,"LEASE_TAG_PROTECTION_UNVERIFIED"):
            claim(natural(),git)
        self.assertFalse(any(method=="POST" for method,_,_ in git.calls))
        self.assertEqual(git.refs,{})

    def test_live_cli_requires_real_active_ruleset_and_never_posts(self):
        import os
        from unittest.mock import patch
        git=MockGit()
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":lease.REPO,
                                    "GITHUB_TOKEN":"masked-test-token"}):
            with patch.object(lease,"github_transport",
                              return_value=git) as transport:
                rc=lease.main(["--verify-tag-protection"])
        self.assertEqual(rc,0)
        transport.assert_called_once_with("masked-test-token")
        self.assertEqual([(x,y) for x,y,_ in git.calls],
                         [("GET","/rulesets"),("GET","/rulesets/11")])
        self.assertFalse(any(x=="POST" for x,_,_ in git.calls))

    def test_live_cli_fails_closed_without_protection_and_cannot_post(self):
        import os
        from unittest.mock import patch
        for mode in ("absent","disabled","bypass","no_update","bypass_hidden"):
            with self.subTest(mode=mode):
                git=MockGit();git.protection=mode
                with patch.dict(os.environ,
                    {"GITHUB_REPOSITORY":lease.REPO,
                     "GITHUB_TOKEN":"masked-test-token"}):
                    with patch.object(lease,"github_transport",return_value=git):
                        self.assertEqual(lease.main(
                            ["--verify-tag-protection"]),3)
                self.assertFalse(any(x=="POST" for x,_,_ in git.calls))

    def test_probe_public_projection_with_hidden_bypass_has_no_release(self):
        import os
        from unittest.mock import patch
        git=MockGit()
        git.protection="bypass_hidden"
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":lease.REPO,
                                    "GITHUB_TOKEN":"masked-test-token"}):
            with patch.object(lease,"github_transport",return_value=git):
                self.assertEqual(lease.main(["--probe-tag-protection"]),0)
                self.assertEqual(lease.main(["--verify-tag-protection"]),3)
        self.assertFalse(any(method=="POST" for method,_,_ in git.calls))

    def test_probe_does_not_accept_actual_bypass(self):
        import os
        from unittest.mock import patch
        git=MockGit()
        git.protection="bypass"
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":lease.REPO,
                                    "GITHUB_TOKEN":"masked-test-token"}):
            with patch.object(lease,"github_transport",return_value=git):
                self.assertEqual(lease.main(["--probe-tag-protection"]),3)
        self.assertFalse(any(method=="POST" for method,_,_ in git.calls))

    def test_live_cli_rejects_missing_token_or_wrong_repository(self):
        import os
        from unittest.mock import patch
        for repo,token in ((lease.REPO,""),("forged/repo","dummy")):
            with self.subTest(repo=repo,token_present=bool(token)):
                with patch.dict(os.environ,{"GITHUB_REPOSITORY":repo,
                                             "GITHUB_TOKEN":token}):
                    with patch.object(lease,"github_transport") as api:
                        self.assertEqual(lease.main(
                            ["--verify-tag-protection"]),3)
                        api.assert_not_called()

    def test_live_cli_has_no_other_actions(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":lease.REPO,
                                    "GITHUB_TOKEN":"masked-test-token"}):
            with patch.object(lease,"github_transport") as api:
                for args in ([],["--help-bypass"],["--claim","2026-11-23"]):
                    with self.subTest(args=args):
                        self.assertEqual(lease.main(args),3)
                api.assert_not_called()


if __name__=="__main__":
    unittest.main()
