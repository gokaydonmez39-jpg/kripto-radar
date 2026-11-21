#!/usr/bin/env python3
"""Adversarial, IO-free tests for atomic 477 Git-tag epoch claim."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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

    def __call__(self,method,path,body=None):
        with self.lock:
            self.calls.append((method,path,copy.deepcopy(body)))
        if method=="GET" and path=="/rulesets":
            if self.protection=="absent":
                return [{"id":1,"target":"branch","enforcement":"active"}]
            return [{"id":11,"target":"tag","enforcement":"active"}]
        if method=="GET" and path=="/rulesets/11":
            types=["update","deletion"]
            if self.protection=="no_update":
                types=["deletion"]
            return {
                "id":11,"target":"tag",
                "enforcement":"disabled" if self.protection=="disabled" else "active",
                "conditions":{"ref_name":{
                    "include":[lease.PROTECTED_PATTERN],
                    "exclude":[]}},
                "rules":[{"type":r} for r in types],
                "bypass_actors":[{"actor_id":1}] if self.protection=="bypass" else [],
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
        out=lease.acquire_first_claim(owner,git)
        self.assertEqual(out["state"],"FIRST_CLAIM_READBACK_VERIFIED_NOT_EOD")
        self.assertFalse(out["ab_release_authorized"])
        self.assertEqual(out["sheet_writes"],0)
        self.assertFalse(out["orders"])
        self.assertEqual(out["device_ack"],"UNKNOWN")
        self.assertEqual(
            [(method,path) for method,path,_ in git.calls],
            [("GET","/rulesets"),("GET","/rulesets/11"),
             ("POST","/git/tags"),("POST","/git/refs"),
             ("GET","/git/ref/tags/"+owner["tag"]),
             ("GET","/git/tags/"+out["tag_sha"])])
        manifest=json.loads(git.tags[out["tag_sha"]]["message"])
        self.assertEqual(manifest["run_id"],owner["run_id"])
        self.assertEqual(manifest["asof_et"],ASOF)
        self.assertNotIn("secret",manifest)
        self.assertNotIn("symbol",manifest)

    def test_idempotent_retry_cannot_repeat_first_claim(self):
        git=MockGit()
        lease.acquire_first_claim(natural(),git)
        with self.assertRaisesRegex(lease.LeaseHold,
                                   "LEASE_REF_COLLISION_OR_PROVIDER_REJECTION"):
            lease.acquire_first_claim(natural(),git)
        self.assertEqual(len(git.refs),1)

    def test_two_distinct_writers_race_one_wins(self):
        git=MockGit(rendezvous=2)
        def one(id):
            try:
                return lease.acquire_first_claim(natural(id),git)
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
                    lease.acquire_first_claim(natural(),git)

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
                    lease.acquire_first_claim(natural(),incomplete)
                self.assertEqual(
                    [(m,p) for m,p,_ in git.calls],
                    [("GET","/rulesets"),("GET","/rulesets/11"),
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
            lease.acquire_first_claim(natural(),lost)
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
                    lease.acquire_first_claim(owner,git)
                self.assertEqual(git.calls,[])

    def test_absent_or_mutable_tag_namespace_blocks_before_any_post(self):
        for mode in ("absent","disabled","bypass","no_update"):
            with self.subTest(mode=mode):
                git=MockGit()
                git.protection=mode
                with self.assertRaisesRegex(
                        lease.LeaseHold,"LEASE_TAG_PROTECTION_UNVERIFIED"):
                    lease.acquire_first_claim(natural(),git)
                self.assertFalse(
                    any(method=="POST" for method,_,_ in git.calls))

    def test_missing_token_is_fail_closed(self):
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_GITHUB_TOKEN_NOT_CONFIGURED"):
            lease.github_transport("")
        with self.assertRaisesRegex(lease.LeaseHold,
                                    "LEASE_API_PATH_INVALID"):
            lease.github_transport("redacted")("POST","/untrusted",{})


if __name__=="__main__":
    unittest.main()
