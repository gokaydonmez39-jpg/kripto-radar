from dataclasses import replace
from datetime import timedelta
import subprocess
import unittest

import test_xray406_witness_acceptance as fixtures
from xray406_witness_acceptance import GUARD, LEDGER, MainReceipt, Rejected
from xray406_witness_github import GitHubIsolatedTransport
from xray406_witness_handoff import ACTOR, CI_PATH, REPO, CheckSource, RunReceipt, staging_ref
from xray406_witness_publish import Indeterminate, publish


class LocalGitTransport:
    ref = "refs/heads/xray406-protected-target"

    def __init__(self, fixture):
        self.f = fixture
        self.stage = staging_ref(fixture.head)
        fixture.run_git("update-ref", self.stage, fixture.head)
        fixture.run_git("update-ref", self.ref, fixture.base)
        self.calls = 0
        self.mode = "normal"

    def head(self, ref):
        return self.f.run_git("rev-parse", self.ref if ref == "target" else ref)

    def publish_once(self, expected, candidate, not_after):
        self.calls += 1
        if self.mode == "race":
            self.f.run_git("update-ref", self.ref, self.f.head, expected)
        if self.mode == "unknown_ack":
            return None
        if subprocess.run(
            ["git", "-C", str(self.f.root), "merge-base", "--is-ancestor", expected, candidate],
            check=False, capture_output=True,
        ).returncode != 0:
            return False
        result = subprocess.run(
            ["git", "-C", str(self.f.root), "update-ref", self.ref, candidate, expected],
            check=False, capture_output=True,
        )
        if self.mode == "lost_response":
            raise TimeoutError
        return result.returncode == 0

    def read_target(self, candidate):
        head = self.head("target")
        blob = lambda p: self.f.run_git("rev-parse", f"{head}:{p}")
        observed = self.f.cutoff + timedelta(seconds=1) if self.mode == "late" else self.f.readback.observed_at
        return MainReceipt(head, observed, blob(GUARD), blob(LEDGER))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        f = self.f
        self.t = LocalGitTransport(f)
        self.run = RunReceipt(REPO, REPO, staging_ref(f.head), f.head, ACTOR, "push", CI_PATH, 20, 1)
        self.source = CheckSource(f.check, 20, 1, 30, f"https://github.com/{REPO}/actions/runs/20/job/30")

    def call(self, source=None, clock=None):
        f = self.f
        return publish(f.root, f.base, f.head, self.run, source or self.source,
                       self.t, clock or (lambda: f.readback.observed_at), f.cutoff)

    def test_exact_write_and_readback(self):
        r = self.call()
        self.assertEqual(r.candidate, self.f.head)
        self.assertEqual(r.guard_blob, self.f.readback.guard_blob)
        self.assertEqual(r.ledger_blob, self.f.readback.ledger_blob)
        self.assertEqual(self.t.head("target"), self.f.head)
        self.assertEqual(self.t.calls, 1)

    def test_red_ci_never_writes(self):
        with self.assertRaisesRegex(Rejected, "EXACT_CI"):
            self.call(source=replace(self.source, check=replace(self.f.check, conclusion="failure")))
        self.assertEqual(self.t.calls, 0)
        self.assertEqual(self.t.head("target"), self.f.base)

    def test_clock_expires_between_validation_and_write(self):
        time = iter((self.f.readback.observed_at, self.f.cutoff))
        with self.assertRaisesRegex(Rejected, "WINDOW_CLOSED"):
            self.call(clock=lambda: next(time))
        self.assertEqual(self.t.calls, 0)

    def test_repository_lookup_crosses_deadline_no_mutation(self):
        f = self.f
        now = f.readback.observed_at
        requests = []

        def api(path, payload=None):
            nonlocal now
            requests.append(path)
            if path == f"repos/{REPO}":
                now = f.cutoff
                return {"full_name": REPO, "node_id": "R_test"}
            if path == "graphql":
                return {"data": {"updateRefs": {"clientMutationId":
                        f"xray406-witness-{f.head}"}}}
            raise AssertionError(path)

        transport = GitHubIsolatedTransport(lambda: now, api)
        transport.head = self.t.head
        transport.read_target = self.t.read_target
        with self.assertRaisesRegex(Rejected, "PUBLISH_WINDOW_CLOSED"):
            publish(f.root, f.base, f.head, self.run, self.source,
                    transport, lambda: now, f.cutoff)
        self.assertEqual(requests, [f"repos/{REPO}"])

    def test_lost_lease_does_not_repeat_write(self):
        self.t.mode = "race"
        with self.assertRaisesRegex(Rejected, "LEASE_REJECTED"):
            self.call()
        self.assertEqual(self.t.calls, 1)

    def test_lost_response_is_not_retried_even_if_ref_moved(self):
        self.t.mode = "lost_response"
        with self.assertRaisesRegex(Indeterminate, "OUTCOME_UNKNOWN_DO_NOT_RETRY"):
            self.call()
        self.assertEqual(self.t.calls, 1)
        self.assertEqual(self.t.head("target"), self.f.head)

    def test_unknown_ack_is_not_retried(self):
        self.t.mode = "unknown_ack"
        with self.assertRaisesRegex(Indeterminate, "ACK_UNKNOWN_DO_NOT_RETRY"):
            self.call()
        self.assertEqual(self.t.calls, 1)

    def test_late_readback_is_not_a_pass(self):
        self.t.mode = "late"
        with self.assertRaisesRegex(Indeterminate, "READBACK_UNPROVEN_DO_NOT_RETRY"):
            self.call()
        self.assertEqual(self.t.calls, 1)


if __name__ == "__main__":
    unittest.main()
