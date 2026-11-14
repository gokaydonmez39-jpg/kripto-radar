from dataclasses import replace
from datetime import timedelta
import unittest

import test_xray406_witness_acceptance as fixtures
from xray406_witness_acceptance import Rejected
from xray406_witness_handoff import (
    ACTOR, CI_PATH, REPO, CheckSource, RunReceipt, plan, staging_ref,
)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        head = self.f.head
        self.run = RunReceipt(REPO, REPO, staging_ref(head), head, ACTOR, "push",
                              CI_PATH, 314, 1)
        self.source = CheckSource(self.f.check, 314, 1, 159,
                                  f"https://github.com/{REPO}/actions/runs/314/job/159")

    def call(self, **overrides):
        f = self.f
        args = dict(root=f.root, base=f.base, head=f.head, run=self.run, source=self.source,
                    stage_head=f.head, target_head=f.base, now=f.readback.observed_at,
                    cutoff=f.cutoff)
        return plan(**{**args, **overrides})

    def test_positive_exact_immutable_candidate(self):
        p = self.call()
        self.assertEqual((p.expected, p.candidate), (self.f.base, self.f.head))
        self.assertEqual((p.guard_blob, p.ledger_blob),
                         (self.f.readback.guard_blob, self.f.readback.ledger_blob))
        self.assertEqual(p.latest_observed_at, self.f.cutoff)

    def test_wrong_event_actor_workflow_repo_or_branch(self):
        for patch in ({"event": "workflow_dispatch"}, {"actor": "another[bot]"},
                      {"workflow": ".github/workflows/different.yml"},
                      {"repo": "other/example"}, {"head_repo": "other/example"},
                      {"ref": "refs/heads/main"}, {"ref": staging_ref(self.f.base)},
                      {"head": self.f.base}):
            with self.subTest(patch=patch), self.assertRaisesRegex(Rejected, "RUN_SCOPE"):
                self.call(run=replace(self.run, **patch))

    def test_check_run_attempt_and_job_link_binding(self):
        for patch in ({"run_id": 315}, {"attempt": 2}, {"job_id": 160},
                      {"details_url": self.source.details_url + "?extra=1"}):
            with self.subTest(patch=patch), self.assertRaisesRegex(Rejected, "CHECK_RUN_BINDING"):
                self.call(source=replace(self.source, **patch))

    def test_matching_rerun_receipts_still_rejected(self):
        with self.assertRaisesRegex(Rejected, "FIRST_ATTEMPT_REQUIRED"):
            self.call(run=replace(self.run, attempt=2),
                      source=replace(self.source, attempt=2))

    def test_success_required_for_same_commit(self):
        for patch in ({"head": self.f.base}, {"app_id": 9}, {"conclusion": "failure"}):
            with self.subTest(patch=patch), self.assertRaisesRegex(Rejected, "EXACT_CI"):
                self.call(source=replace(self.source, check=replace(self.f.check, **patch)))

    def test_ref_drift_rejects_both_paths(self):
        for patch in ({"target_head": self.f.head}, {"stage_head": self.f.base}):
            with self.subTest(patch=patch), self.assertRaisesRegex(Rejected, "REF_DRIFT"):
                self.call(**patch)

    def test_no_mutation_at_or_after_deadline(self):
        for now in (self.f.cutoff, self.f.cutoff + timedelta(microseconds=1)):
            with self.subTest(now=now), self.assertRaisesRegex(Rejected, "WINDOW_CLOSED"):
                self.call(now=now)
        with self.assertRaisesRegex(Rejected, "WINDOW_CLOSED"):
            self.call(now=self.f.generated + timedelta(minutes=15),
                      cutoff=self.f.generated + timedelta(minutes=30))

    def test_check_must_precede_plan(self):
        with self.assertRaisesRegex(Rejected, "WINDOW_CLOSED"):
            self.call(now=self.f.generated)


if __name__ == "__main__":
    unittest.main()
