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

if __name__=="__main__":
    unittest.main()
