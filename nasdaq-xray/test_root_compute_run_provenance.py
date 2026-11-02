"""Independent GitHub Actions step provenance contract for bounded root cooldown."""
from __future__ import annotations

import copy
import datetime as dt
import unittest

from root_compute_run_provenance import (
    ROOT_NAME, REAL_COMPUTE_STEP, last_real_compute, step_proof)

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,2,18,0,tzinfo=UTC)

def run(rid, at, status="completed", outcome="success"):
    return {"id":rid, "name":ROOT_NAME, "head_branch":"main",
            "created_at":at,"status":status,"conclusion":outcome,
            "head_sha":"a"*40}

def witness(name=REAL_COMPUTE_STEP, conclusion="success"):
    return {"jobs":[{"name":"dataplane","steps":[{"name":name,
                                               "conclusion":conclusion}]}]}

class ComputeProvenance(unittest.TestCase):
    def test_pass_needs_true_compute_step(self):
        rows=[run(100,"2026-11-02T16:30:00Z")]
        out=last_real_compute(now=NOW,runs=rows,
                             get_jobs=lambda i:witness())
        self.assertEqual(out["status"],"SUCCESS_COMPUTE")
        self.assertEqual(out["run_id"],100)
        self.assertEqual(out["age_seconds"],5400)

    def test_newer_green_noop_does_not_reset_bounded_window(self):
        rows=[run(102,"2026-11-02T17:30:00Z"),
              run(101,"2026-11-02T16:30:00Z")]
        responses={102:witness(conclusion="skipped"),
                   101:witness(conclusion="success")}
        out=last_real_compute(now=NOW,runs=rows,
                             get_jobs=lambda i:responses[i])
        self.assertEqual(out["status"],"SUCCESS_COMPUTE")
        self.assertEqual(out["run_id"],101)

    def test_four_hours_always_opens_new_compute_even_if_green_noops(self):
        rows=[run(102,"2026-11-02T17:30:00Z"),
              run(101,"2026-11-02T13:59:00Z")]
        calls=[]
        def get_jobs(i):
            calls.append(i)
            return witness(conclusion="skipped")
        out=last_real_compute(now=NOW,runs=rows,get_jobs=get_jobs)
        self.assertEqual(out["status"],"NO_RECENT_COMPUTE")
        self.assertEqual(calls,[102])

    def test_most_recent_failed_real_compute_never_hidden(self):
        rows=[run(104,"2026-11-02T17:50:00Z"),
              run(103,"2026-11-02T17:40:00Z",outcome="failure"),
              run(101,"2026-11-02T16:30:00Z")]
        responses={104:witness(conclusion="skipped"),
                   103:witness(conclusion="failure"),
                   101:witness()}
        out=last_real_compute(now=NOW,runs=rows,
                             get_jobs=lambda i:responses[i])
        self.assertEqual(out["status"],"FAILED_COMPUTE")
        self.assertEqual(out["run_id"],103)

    def test_wrong_or_missing_step_never_counts_success(self):
        forged=[
            {"jobs":[]}, {"jobs":[{"steps":[]}]},
            {"jobs":[{"steps":[{"name":"Compile","conclusion":"success"}]}]},
            {"jobs":[{"steps":[{"name":REAL_COMPUTE_STEP,
                               "conclusion":"success"},
                              {"name":REAL_COMPUTE_STEP,
                               "conclusion":"success"}]}]},
            {"jobs":[{"steps":[{"name":REAL_COMPUTE_STEP,
                               "conclusion":"pending"}]}]},
            {"jobs":[{"steps":[{"name":REAL_COMPUTE_STEP,
                               "conclusion":"success"}]},{}]},
            {}, {"jobs":None},
        ]
        for entry in forged:
            with self.subTest(entry=entry):
                self.assertEqual(step_proof(entry),"UNVERIFIED")

    def test_api_error_or_untrusted_ids_does_not_prove_compute(self):
        row=run(12,"2026-11-02T17:20:00Z")
        self.assertEqual(last_real_compute(
            now=NOW,runs=[row],
            get_jobs=lambda i:(_ for _ in ()).throw(ConnectionError())
        )["status"],"UNVERIFIED")
        row["id"]="injected"
        self.assertEqual(last_real_compute(now=NOW,runs=[row],
            get_jobs=lambda i:self.fail("UNEXPECTED_GET"))["status"],"UNVERIFIED")

    def test_missing_or_wrong_identity_rejected(self):
        cases=[
            [run(1,"invalid")],
            [dict(run(1,"2026-11-02T17:00:00Z"),name="Crypto")],
            [dict(run(1,"2026-11-02T17:00:00Z"),head_branch="crypto")],
            [dict(run(1,"2026-11-02T18:05:00Z"))],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertEqual(last_real_compute(
                    now=NOW,runs=rows,get_jobs=lambda i:self.fail("WRONG_GET")
                )["status"],"UNVERIFIED")

    def test_queued_root_not_false_compute(self):
        root=run(1,"2026-11-02T17:00:00Z",status="queued",outcome=None)
        out=last_real_compute(now=NOW,runs=[root],
                             get_jobs=lambda i:self.fail("QUEUED_GET"))
        self.assertEqual(out["status"],"NO_RECENT_COMPUTE")

    def test_lookups_are_bounded(self):
        rows=[run(i+1,f"2026-11-02T17:{i:02d}:00Z")
              for i in range(25)]
        hits=[]
        def get_jobs(i):
            hits.append(i)
            return witness(conclusion="skipped")
        out=last_real_compute(now=NOW,runs=rows,get_jobs=get_jobs)
        self.assertEqual(out["status"],"UNVERIFIED")
        self.assertEqual(len(hits),20)

if __name__=="__main__":
    unittest.main()
