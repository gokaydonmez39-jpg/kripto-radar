from datetime import datetime, timedelta, timezone
import unittest

from xray406_witness_acceptance import CHECK, GUARD, LEDGER, Rejected
from xray406_witness_github import GitHubIsolatedTransport, TARGET, receipt_pair
from xray406_witness_handoff import ACTOR, CI_PATH, REPO, staging_ref
from xray406_witness_publish import WindowClosedBeforeMutation

BASE, HEAD, ROOT, NODE, GB, LB = [x * 40 for x in "123456"]
PILOT_ID = 356585181


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 21, 12, tzinfo=timezone.utc)
        self.calls = []
        self.n = 0
        self.move = False
        self.error = False
        self.t = GitHubIsolatedTransport(lambda: self.now, self.call)

    def call(self, path, payload=None):
        self.calls.append((path, payload))
        if path == f"repos/{REPO}":
            return {"full_name": REPO, "node_id": "R_test"}
        if path == "graphql":
            if self.error:
                return {"errors": [{"message": "test ambiguity"}]}
            return {"data": {"updateRefs": {"clientMutationId": "xray406-witness-" + HEAD}}}
        base = f"repos/{REPO}/"
        if path == base + "git/ref/" + TARGET.removeprefix("refs/"):
            self.n += 1
            return {"ref": TARGET, "object": {"type": "commit",
                                              "sha": BASE if self.n > 1 and self.move else HEAD}}
        if path == base + f"git/commits/{HEAD}":
            return {"tree": {"sha": ROOT}}
        if path == base + f"git/trees/{ROOT}":
            return {"truncated": False, "tree": [
                {"path": "nasdaq-xray", "type": "tree", "mode": "040000", "sha": NODE}]}
        if path == base + f"git/trees/{NODE}":
            return {"truncated": False, "tree": [
                {"path": GUARD.split("/")[-1], "type": "blob", "mode": "100644", "sha": GB},
                {"path": LEDGER.split("/")[-1], "type": "blob", "mode": "100644", "sha": LB}]}
        raise AssertionError(path)

    def test_atomic_only_isolated_target(self):
        self.assertTrue(self.t.publish_once(BASE, HEAD, self.now + timedelta(minutes=1)))
        p = self.calls[-1][1]["variables"]["input"]["refUpdates"][0]
        self.assertEqual(p, {"name": TARGET, "beforeOid": BASE, "afterOid": HEAD, "force": False})

    def test_failed_mutation_is_uncertain_not_retried(self):
        self.error = True
        self.assertIsNone(self.t.publish_once(BASE, HEAD, self.now + timedelta(minutes=1)))
        self.assertEqual([p for p, _ in self.calls].count("graphql"), 1)

    def test_write_budget_boundary_is_inclusive_rejection(self):
        for seconds, accepted in ((29, False), (30, False), (31, True)):
            with self.subTest(seconds=seconds):
                self.calls.clear()
                deadline = self.now + timedelta(seconds=seconds)
                if accepted:
                    self.assertTrue(self.t.publish_once(BASE, HEAD, deadline))
                else:
                    with self.assertRaises(WindowClosedBeforeMutation):
                        self.t.publish_once(BASE, HEAD, deadline)
                self.assertEqual(sum(p == "graphql" for p, _ in self.calls), int(accepted))

    def test_main_ref_not_allowed(self):
        with self.assertRaisesRegex(Rejected, "REF_OUT_OF_SCOPE"):
            self.t.head("refs/heads/main")
        self.assertEqual(self.calls, [])

    def test_exact_blob_ids_no_contents_download(self):
        receipt = self.t.read_target(HEAD)
        self.assertEqual((receipt.head, receipt.guard_blob, receipt.ledger_blob, receipt.observed_at),
                         (HEAD, GB, LB, self.now))
        self.assertFalse(any("/contents/" in p for p, _ in self.calls))

    def test_race_during_readback_rejected(self):
        self.move = True
        with self.assertRaisesRegex(Rejected, "TARGET_MOVED"):
            self.t.read_target(HEAD)

    def test_symlink_and_truncation_rejected(self):
        for truncated, mode in ((True, "100644"), (False, "120000")):
            with self.subTest(truncated=truncated, mode=mode), self.assertRaises(Rejected):
                self.t.entry({"truncated": truncated, "tree": [
                    {"path": "data", "type": "blob", "mode": mode, "sha": GB}]},
                    "data", "blob", "100644")


class EvidenceTests(unittest.TestCase):
    def fixture(self, path, duplicate=False, bad_job=False, attempt=1, **run_overrides):
        if path.endswith(f"/attempts/{attempt}"):
            return {"id": 31, "run_attempt": attempt, "repository": {"full_name": REPO},
                    "head_repository": {"full_name": REPO}, "head_branch": staging_ref(HEAD)[11:],
                    "head_sha": HEAD, "actor": {"login": ACTOR, "id": PILOT_ID},
                    "triggering_actor": {"login": ACTOR, "id": PILOT_ID},
                    "status": "completed", "conclusion": "success",
                    "event": "push", "path": CI_PATH, **run_overrides}
        if "/check-runs?" in path:
            c = {"name": CHECK, "head_sha": HEAD, "app": {"id": 15368}, "status": "completed",
                 "conclusion": "success", "completed_at": "2026-11-16T21:11:00Z",
                 "details_url": f"https://github.com/{REPO}/actions/runs/31/job/44"}
            n = 2 if duplicate else 1
            return {"total_count": n, "check_runs": [c] * n}
        if "/jobs?" in path:
            return {"total_count": 1, "jobs": [{"id": 44, "name": CHECK, "head_sha": HEAD,
                    "status": "completed", "conclusion": "failure" if bad_job else "success"}]}
        raise AssertionError(path)

    def test_run_and_check_evidence(self):
        r, s = receipt_pair(31, 1, HEAD, self.fixture)
        self.assertEqual((r.ref, r.head, r.actor, s.job_id, s.check.app_id),
                         (staging_ref(HEAD), HEAD, ACTOR, 44, 15368))

    def test_duplicate_check_rejected(self):
        with self.assertRaisesRegex(Rejected, "CHECK_CARDINALITY"):
            receipt_pair(31, 1, HEAD, lambda path: self.fixture(path, duplicate=True))

    def test_failed_job_rejected(self):
        with self.assertRaisesRegex(Rejected, "JOB_NOT_VERIFIED"):
            receipt_pair(31, 1, HEAD, lambda path: self.fixture(path, bad_job=True))

    def test_rerun_not_allowed_even_with_green_job(self):
        with self.assertRaisesRegex(Rejected, "FIRST_ATTEMPT_REQUIRED"):
            receipt_pair(31, 2, HEAD, lambda path: self.fixture(path, attempt=2))

    def test_app_login_must_match_actor_id_and_trigger(self):
        for changes in ({"actor": {"login": ACTOR, "id": PILOT_ID + 1}},
                        {"triggering_actor": {"login": "operator", "id": 3}}):
            with self.subTest(changes=changes), self.assertRaisesRegex(Rejected, "APP_ACTOR_NOT_VERIFIED"):
                receipt_pair(31, 1, HEAD, lambda path: self.fixture(path, **changes))

    def test_whole_run_must_be_green(self):
        with self.assertRaisesRegex(Rejected, "RUN_NOT_VERIFIED"):
            receipt_pair(31, 1, HEAD, lambda path: self.fixture(path, conclusion="failure"))


if __name__ == "__main__":
    unittest.main()
