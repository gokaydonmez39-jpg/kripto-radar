"""No-I/O proof: fallback must not elevate a green GitHub workflow alone."""
import copy
import unittest
from datetime import datetime,timezone
import fallback_job_receipt as proof

ASOF="2026-11-19"
NOW=datetime(2026,11,20,1,0,tzinfo=timezone.utc)
RUN_ID=44671232964
REPO=proof.REPO
PATH=proof.PATH

def fixture():
    run={
        "id":RUN_ID,"repository":{"full_name":REPO},
        "path":PATH,"event":"schedule","head_branch":"main",
        "head_sha":"a"*40,"run_attempt":1,
        "status":"completed","conclusion":"success",
        "created_at":"2026-11-19T23:50:00Z",
        "updated_at":"2026-11-20T00:59:00Z",
    }
    jobs=[]
    for i,name in enumerate(proof.NAMES):
        steps=[{"name":s,"status":"completed","conclusion":"success"}
               for s in proof.REQUIRED_STEPS.get(name,())]
        jobs.append({"id":123450+i,"run_id":RUN_ID,"name":name,
                     "status":"completed","conclusion":"success",
                     "steps":steps})
    return run,{"total_count":6,"jobs":jobs}

class SixJobOnlyProof(unittest.TestCase):
    def test_valid_six_jobs_never_claim_sheet_or_chatgpt(self):
        run,jobs=fixture()
        result=proof.validate(run,jobs,ASOF,NOW)
        self.assertEqual(result["status"],"PRIMARY_EOD_SIX_JOB_PROVEN_GH_ONLY")
        self.assertFalse(result["private_sheet_verified"])
        self.assertFalse(result["ab_release_authorized"])
        self.assertEqual(result["device_ack"],"UNKNOWN")

    def test_missing_canonical_writer_is_fail_closed(self):
        run,jobs=fixture()
        jobs["jobs"][2]["steps"]= [
            s for s in jobs["jobs"][2]["steps"]
            if s["name"]!="Private Google Sheets writer (authorized service account only)"]
        with self.assertRaisesRegex(proof.ReceiptHold,"PRIMARY_JOB_STEP_RECEIPT_MISSING"):
            proof.validate(run,jobs,ASOF,NOW)

    def test_successful_parent_with_skipped_guardian_is_hold(self):
        run,jobs=fixture()
        jobs["jobs"][4]["conclusion"]="skipped"
        with self.assertRaisesRegex(proof.ReceiptHold,"PRIMARY_JOB_RECEIPT_MISSING"):
            proof.validate(run,jobs,ASOF,NOW)

    def test_wrong_origin_path_commit_or_attempt_cannot_pass(self):
        for key,value in (
            ("event","workflow_dispatch"),("path","different.yml"),
            ("head_branch","dev"),("head_sha","Z"*40),("run_attempt",2),
            ("conclusion","failure")):
            with self.subTest(key=key):
                run,jobs=fixture();run[key]=value
                with self.assertRaisesRegex(proof.ReceiptHold,
                                            "PRIMARY_RUN_ORIGIN_NOT_VERIFIED"):
                    proof.validate(run,jobs,ASOF,NOW)

    def test_missing_or_duplicate_jobs_never_count_as_six(self):
        for change in ("short","duplicate","wrong_run_id","unknown_job"):
            with self.subTest(change=change):
                run,jobs=fixture()
                if change=="short": jobs["jobs"].pop()
                if change=="duplicate": jobs["jobs"][0]["name"]=jobs["jobs"][1]["name"]
                if change=="wrong_run_id": jobs["jobs"][0]["run_id"]=42
                if change=="unknown_job": jobs["jobs"][0]["name"]="unknown"
                jobs["total_count"]=len(jobs["jobs"])
                with self.assertRaisesRegex(proof.ReceiptHold,"PRIMARY_JOB_RECEIPT_MISSING"):
                    proof.validate(run,jobs,ASOF,NOW)

    def test_ambiguous_provider_pagination_cannot_be_green(self):
        run,jobs=fixture();jobs["total_count"]=7
        with self.assertRaisesRegex(proof.ReceiptHold,"PRIMARY_JOB_RECEIPT_MISSING"):
            proof.validate(run,jobs,ASOF,NOW)

    def test_callback_is_never_used_to_mutate(self):
        run,jobs=fixture()
        copy_before=copy.deepcopy((run,jobs))
        proof.validate(run,jobs,ASOF,NOW)
        self.assertEqual((run,jobs),copy_before)

class ReadOnlyAuditSelection(unittest.TestCase):
    def test_exact_valid_run_uses_three_get_calls_and_no_post(self):
        run,jobs=fixture()
        calls=[]
        def get(url):
            calls.append(url)
            if "/actions/workflows/" in url:
                return {"total_count":1,
                        "workflow_runs":[{
                            "id":RUN_ID,"created_at":run["created_at"],
                            "head_branch":"main","event":"schedule",
                            "status":"completed","conclusion":"success"}]}
            if url.endswith("/jobs?per_page=100"):
                return copy.deepcopy(jobs)
            return copy.deepcopy(run)
        out=proof.audit(ASOF,now=NOW,get=get)
        self.assertEqual(out["run_id"],RUN_ID)
        self.assertEqual(len(calls),3)
        self.assertTrue(all("https://api.github.com/repos/"+REPO+"/actions/"
                            in item for item in calls))
        self.assertFalse(out["private_sheet_verified"])

    def test_successful_workflow_without_jobs_is_hold(self):
        run,jobs=fixture()
        def get(url):
            if "/actions/workflows/" in url:
                return {"total_count":1,
                        "workflow_runs":[{
                            "id":RUN_ID,"created_at":run["created_at"],
                            "head_branch":"main","event":"schedule",
                            "status":"completed","conclusion":"success"}]}
            if url.endswith("/jobs?per_page=100"):
                return {"total_count":0,"jobs":[]}
            return run
        with self.assertRaisesRegex(proof.ReceiptHold,
                                    "PRIMARY_JOB_RECEIPT_MISSING"):
            proof.audit(ASOF,now=NOW,get=get)

    def test_no_natural_run_never_accepted(self):
        called=[]
        def get(url):
            called.append(url)
            return {"total_count":0,"workflow_runs":[]}
        with self.assertRaisesRegex(proof.ReceiptHold,
                                    "PRIMARY_EOD_EPOCH_AMBIGUOUS"):
            proof.audit(ASOF,now=NOW,get=get)
        self.assertEqual(len(called),1)

    def test_successful_run_after_freshness_window_is_hold(self):
        run,jobs=fixture()
        run["created_at"]="2026-11-20T10:01:00Z"
        run["updated_at"]="2026-11-20T10:02:00Z"
        with self.assertRaisesRegex(proof.ReceiptHold,
                                    "PRIMARY_EOD_TIME_WINDOW_UNVERIFIED"):
            proof.validate(run,jobs,ASOF,
                           datetime(2026,11,20,11,tzinfo=timezone.utc))

if __name__=="__main__":
    unittest.main()
