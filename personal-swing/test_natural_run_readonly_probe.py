#!/usr/bin/env python3
"""No-network acceptance: real natural-run canary has GET-only authority."""
import unittest
from unittest.mock import patch

import epoch_lease as lease
from test_epoch_lease import MockGit, env, ASOF, NOW
import natural_run_readonly_probe as probe


class NaturalReadOnlyCanary(unittest.TestCase):
    def test_exact_current_producer_requires_one_get_and_no_mutations(self):
        git=MockGit()
        out=probe.verify_once(env(),git,now=NOW,
                              completed_session=lambda _:ASOF)
        self.assertEqual(out["status"],"NATURAL_RUN_GITHUB_READ_ONLY_VERIFIED")
        self.assertEqual(out["asof_et"],ASOF)
        self.assertEqual(out["run_id"],890123)
        self.assertEqual(out["writes"],0)
        self.assertFalse(out["orders"])
        self.assertFalse(out["ab_release_authorized"])
        self.assertEqual(out["device_ack"],"UNKNOWN")
        self.assertEqual([(m,p) for m,p,_ in git.calls],
                         [("GET","/actions/runs/890123")])

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


if __name__=="__main__":
    unittest.main()
