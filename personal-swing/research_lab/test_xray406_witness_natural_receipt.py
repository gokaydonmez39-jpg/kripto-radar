import unittest

from xray406_witness_acceptance import GUARD, LEDGER, Rejected
from xray406_witness_handoff import REPO
from xray406_witness_natural_receipt import MERGE, PATH, PERSIST, SUMMARY, verify


class NaturalReceiptTests(unittest.TestCase):
    def setUp(self):
        self.base, self.head, self.guard, self.ledger = [c * 40 for c in "abcd"]
        self.run = dict(id=150, run_attempt=1, event="schedule", head_branch="main",
                        status="completed", conclusion="success", path=PATH,
                        repository={"full_name": REPO}, head_repository={"full_name": REPO},
                        head_sha=self.base)
        self.jobs = {"total_count": 1, "jobs": [
            dict(id=250, run_id=150, head_sha=self.base, name="resilience", status="completed",
                 conclusion="success", steps=[
                    dict(name=PERSIST, status="completed", conclusion="success", number=16),
                    dict(name=SUMMARY, status="completed", conclusion="success", number=17)])]}
        self.summary = "\n".join(["### XRAY #406 · Natural Official Witness observation", "",
            "Observation of the existing publication route. Not staging CI or production cutover acceptance.", "",
            *(f"- {k}: `{v}`" for k, v in zip(
                ("WITNESS_BASE", "WITNESS_HEAD", "WITNESS_GUARD", "WITNESS_LEDGER"),
                (self.base, self.head, self.guard, self.ledger))), ""])
        self.commit = dict(sha=self.head, parents=[{"sha": self.base}], files=[
            dict(filename=GUARD, sha=self.guard, status="modified"),
            dict(filename=LEDGER, sha=self.ledger, status="modified")])
        self.observed = {"root": "e"*40, "nasdaq": "f"*40}
        self.statuses = {self.base: "ahead"}
        self.here = {"sha": self.head, "tree": {"sha": self.observed["root"]}}
        self.root = {"sha": self.observed["root"], "truncated": False, "tree": [
            {"path": "nasdaq-xray", "sha": self.observed["nasdaq"], "type": "tree", "mode": "040000"}]}
        self.nested = {"sha": self.observed["nasdaq"], "truncated": False, "tree": [
            {"path": p.rsplit("/", 1)[1], "sha": v, "type": "blob", "mode": "100644"}
            for p, v in ((GUARD, self.guard), (LEDGER, self.ledger))]}
        self.reads = []

    def get(self, path):
        self.reads.append(path)
        if path == f"compare/{MERGE}...{self.base}":
            return {"status": self.statuses[self.base], "merge_base_commit": {"sha": MERGE}}
        if path == f"commits/{self.head}":
            return self.commit
        if path == f"git/commits/{self.head}":
            return self.here
        if path == f"git/trees/{self.observed['root']}":
            return self.root
        if path == f"git/trees/{self.observed['nasdaq']}":
            return self.nested
        raise AssertionError(path)

    def call(self):
        return verify(150, 250, self.run, self.jobs, self.summary, self.get)

    def test_valid_receipt_stays_old_route_only(self):
        x = self.call()
        self.assertEqual((x.run_id, x.job_id, x.base, x.head, x.guard, x.ledger),
                         (150, 250, self.base, self.head, self.guard, self.ledger))
        self.assertEqual(x.status, "OLD_ROUTE_NATURAL_RECEIPT_VERIFIED")
        self.assertFalse(x.proves_first_visibility)

    def test_push_rerun_other_branch_or_wrong_job(self):
        for changes in ({"event": "push"}, {"run_attempt": 2}, {"head_branch": "other"},
                        {"conclusion": "failure"}, {"head_repository": {"full_name": "other/repo"}}):
            with self.subTest(changes=changes):
                saved = self.run
                self.run = {**saved, **changes}
                with self.assertRaisesRegex(Rejected, "NATURAL_RUN_NOT_VERIFIED"):
                    self.call()
                self.run = saved
        self.jobs["jobs"][0]["head_sha"] = self.head
        with self.assertRaisesRegex(Rejected, "NATURAL_JOB_NOT_VERIFIED"):
            self.call()

    def test_receipt_missing_duplicate_wrong_blob_or_skipped(self):
        for candidate in ("", self.summary + self.summary,
                          self.summary.replace(self.ledger, self.base)):
            with self.subTest(summary=candidate[:12]):
                saved = self.summary
                self.summary = candidate
                with self.assertRaises(Rejected):
                    self.call()
                self.summary = saved
        self.jobs["jobs"][0]["steps"][1]["conclusion"] = "skipped"
        with self.assertRaisesRegex(Rejected, "NATURAL_STEP_NOT_VERIFIED"):
            self.call()

    def test_unrelated_commit_wrong_parent_or_non_exact_tree(self):
        self.statuses[self.base] = "diverged"
        with self.assertRaisesRegex(Rejected, "SOURCE_BEFORE_RECEIPT_MERGE"):
            self.call()
        self.statuses[self.base] = "ahead"
        self.commit["parents"].append({"sha": self.guard})
        with self.assertRaisesRegex(Rejected, "WITNESS_COMMIT_NOT_BOUND"):
            self.call()
        self.commit["parents"].pop()
        self.nested["tree"][1]["mode"] = "120000"
        with self.assertRaises(Rejected):
            self.call()

    def test_api_commit_and_immutable_tree_must_agree(self):
        self.nested["tree"][0]["sha"] = self.ledger
        with self.assertRaisesRegex(Rejected, "WITNESS_IMMUTABLE_BLOB_MISMATCH"):
            self.call()
        self.assertFalse(any("/blobs/" in x for x in self.reads))

    def test_base_can_advance_after_run_checkout(self):
        checkout = self.run["head_sha"]
        self.base = "0"*40
        self.summary = self.summary.replace(checkout, self.base)
        self.commit["parents"] = [{"sha": self.base}]
        fallback = self.get

        def read(path):
            if path == f"compare/{MERGE}...{checkout}":
                return {"status": "ahead", "merge_base_commit": {"sha": MERGE}}
            if path == f"compare/{checkout}...{self.base}":
                return {"status": "ahead", "merge_base_commit": {"sha": checkout}}
            return fallback(path)

        self.get = read
        self.assertEqual(self.call().base, self.base)
