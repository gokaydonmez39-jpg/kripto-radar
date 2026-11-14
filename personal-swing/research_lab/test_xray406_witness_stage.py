from datetime import timedelta
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_xray406_witness_acceptance as fixtures
from xray406_witness_acceptance import Rejected
from xray406_witness_handoff import staging_ref
from xray406_witness_stage import GitStageTransport, REMOTE, StageUnknown, stage


class StageTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.base, self.candidate = self.f.base, self.f.head
        self.values = {"refs/heads/main": self.base}
        self.creates = 0
        self.lost = False

    def read(self, ref):
        return self.values.get(ref)

    def create_only(self, root, ref, candidate):
        self.creates += 1
        self.values[ref] = candidate
        if self.lost:
            raise TimeoutError
        return True

    def invoke(self, now=None, cutoff=None):
        f = self.f
        return stage(f.root, self.base, self.candidate, cutoff or f.cutoff,
                     lambda: now or f.generated, self)

    def test_candidate_stages_once(self):
        self.assertFalse(self.invoke().already_staged)
        self.assertTrue(self.invoke().already_staged)
        self.assertEqual(self.creates, 1)

    def test_main_drift_prevents_creation(self):
        self.values["refs/heads/main"] = self.candidate
        with self.assertRaisesRegex(Rejected, "BASE_MOVED"):
            self.invoke()
        self.assertEqual(self.creates, 0)

    def test_occupied_ref_never_changes(self):
        self.values[staging_ref(self.candidate)] = self.base
        with self.assertRaisesRegex(Rejected, "ALREADY_OCCUPIED"):
            self.invoke()
        self.assertEqual(self.creates, 0)

    def test_no_stage_with_insufficient_budget(self):
        with self.assertRaisesRegex(Rejected, "WINDOW_CLOSED"):
            self.invoke(now=self.f.generated + timedelta(minutes=1))
        self.assertEqual(self.creates, 0)

    def test_uncertain_stage_does_not_retry(self):
        self.lost = True
        with self.assertRaisesRegex(StageUnknown, "DO_NOT_RETRY"):
            self.invoke()
        self.assertEqual(self.creates, 1)

    def test_real_git_create_lease_rejects_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            bare = Path(temp) / "remote.git"
            subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
            def command(args, **kwargs):
                return subprocess.run([str(bare) if x == REMOTE else x for x in args], **kwargs)
            t = GitStageTransport(command)
            ref = staging_ref(self.candidate)
            self.assertIsNone(t.read(ref))
            self.assertTrue(t.create_only(self.f.root, ref, self.candidate))
            self.assertEqual(t.read(ref), self.candidate)
            # Use a second fixed ref with the candidate suffix and an already
            # present, distinct commit. The empty-lease push must refuse it.
            subprocess.run(["git", "-C", str(bare), "update-ref", ref, self.base, self.candidate],
                           check=True)
            self.assertFalse(t.create_only(self.f.root, ref, self.candidate))
            self.assertEqual(t.read(ref), self.base)

    def test_remote_scope_cannot_write_main(self):
        t = GitStageTransport(lambda *args, **kwargs: self.fail("unexpected command"))
        with self.assertRaisesRegex(Rejected, "REF_OUT_OF_SCOPE"):
            t.create_only(self.f.root, "refs/heads/main", self.candidate)

    def test_app_credential_only_in_push_child_environment(self):
        calls = []
        def command(args, **kwargs):
            calls.append((args, kwargs["env"]))
            return subprocess.CompletedProcess(args, 2 if "ls-remote" in args else 0, "", "")
        t = GitStageTransport(command, app_token="isolated-fixture-only")
        ref = staging_ref(self.candidate)
        with patch.dict("os.environ", {"GITHUB_TOKEN": "fixture", "GIT_TRACE_CURL": "1"}):
            self.assertIsNone(t.read(ref))
            self.assertTrue(t.create_only(self.f.root, ref, self.candidate))
        for args, env in calls:
            self.assertNotIn("isolated-fixture-only", " ".join(args))
            self.assertNotIn("GITHUB_TOKEN", env)
            self.assertNotIn("GIT_TRACE_CURL", env)
        self.assertNotIn("GH_TOKEN", calls[0][1])
        self.assertEqual(calls[1][1]["GH_TOKEN"], "isolated-fixture-only")


if __name__ == "__main__":
    unittest.main()
