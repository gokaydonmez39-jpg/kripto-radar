"""No-I/O proof: fallback must not elevate a green GitHub workflow alone."""
import copy
import unittest
from datetime import datetime,timezone,timedelta
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
        start=datetime(2026,11,19,23,51+i,tzinfo=timezone.utc)
        end=start+timedelta(seconds=45)
        stamps=lambda t:t.isoformat().replace("+00:00","Z")
        steps=[{"name":s,"status":"completed","conclusion":"success",
                "number":j+1,
                "started_at":stamps(start+timedelta(seconds=2+j*5)),
                "completed_at":stamps(start+timedelta(seconds=3+j*5))}
               for j,s in enumerate(proof.REQUIRED_STEPS.get(name,()))]
        jobs.append({"id":123450+i,"run_id":RUN_ID,"name":name,
                     "run_attempt":1,
                     "run_url":proof.EOD_RUN_BASE+str(RUN_ID),
                     "head_sha":run["head_sha"],"head_branch":"main",
                     "started_at":stamps(start),"completed_at":stamps(end),
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

    def test_green_jobs_without_exact_offline_panel_or_score_steps_hold(self):
        for job_name, required in (
            ("offline-guard", "Static tests before any data API access"),
            ("offline-guard", "Require real natural EOD GitHub-run receipt (GET only, no tag claim)"),
            ("private-episode-followups", "Reconcile PANEL from verified private scan and immutable candidate ledger"),
            ("private-episode-followups", "Private EOD swing ranking V1 (advisory; never blocks AL or Guardian)"),
        ):
            with self.subTest(job=job_name, step=required):
                run, jobs = fixture()
                job = next(j for j in jobs["jobs"] if j["name"] == job_name)
                job["steps"] = [s for s in job["steps"] if s["name"] != required]
                with self.assertRaisesRegex(proof.ReceiptHold,
                                            "PRIMARY_JOB_STEP_RECEIPT_MISSING"):
                    proof.validate(run, jobs, ASOF, NOW)

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

    def test_noninteger_attempt_or_job_source_ids_must_hold(self):
        # Python True == 1 and 1.0 == 1. GitHub source provenance
        # requires exact integer types, not merely numeric equality.
        for forged in (True, 1.0):
            with self.subTest(field="run_attempt", forged=forged):
                run,jobs=fixture()
                run["run_attempt"]=forged
                with self.assertRaisesRegex(
                        proof.ReceiptHold,"PRIMARY_RUN_ORIGIN_NOT_VERIFIED"):
                    proof.validate(run,jobs,ASOF,NOW)
            with self.subTest(field="job_attempt", forged=forged):
                run,jobs=fixture()
                jobs["jobs"][0]["run_attempt"]=forged
                with self.assertRaisesRegex(
                        proof.ReceiptHold,"PRIMARY_JOB_RECEIPT_MISSING"):
                    proof.validate(run,jobs,ASOF,NOW)
        run,jobs=fixture()
        jobs["jobs"][0]["run_id"]=float(RUN_ID)
        with self.assertRaisesRegex(
                proof.ReceiptHold,"PRIMARY_JOB_RECEIPT_MISSING"):
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

    def test_wrong_job_origin_or_missing_clock_cannot_pass(self):
        run,jobs=fixture()
        changes={
            "head_sha":"b"*40,
            "head_branch":"feature",
            "run_attempt":2,
            "run_url":"https://api.github.com/repos/wrong/project/actions/runs/"+str(RUN_ID),
            "started_at":"2000-01-01T00:00:00Z",
            "completed_at":"2026-11-21T00:00:00Z",
        }
        for key,value in changes.items():
            with self.subTest(key=key):
                damaged=copy.deepcopy(jobs)
                damaged["jobs"][2][key]=value
                with self.assertRaisesRegex(proof.ReceiptHold,
                                            "PRIMARY_JOB_RECEIPT_MISSING"):
                    proof.validate(run,damaged,ASOF,NOW)

    def test_incorrect_dag_order_is_hold(self):
        run,jobs=fixture()
        # Guardian overlaps its mandatory predecessor followups.
        jobs["jobs"][4]["started_at"]="2026-11-19T23:53:00Z"
        with self.assertRaisesRegex(proof.ReceiptHold,
                                    "PRIMARY_JOB_DAG_UNVERIFIED"):
            proof.validate(run,jobs,ASOF,NOW)

    def test_required_writer_step_cannot_be_out_of_order_or_out_of_job(self):
        run,jobs=fixture()
        for mutate in ("step_order","step_clock","missing_step_number"):
            with self.subTest(mutate=mutate):
                damaged=copy.deepcopy(jobs)
                required=damaged["jobs"][2]["steps"]
                if mutate=="step_order":
                    required[2]["number"]=1
                elif mutate=="step_clock":
                    required[2]["completed_at"]="2026-11-21T00:00:00Z"
                else:
                    required[2].pop("number")
                with self.assertRaisesRegex(proof.ReceiptHold,
                                            "PRIMARY_JOB_STEP_RECEIPT_MISSING"):
                    proof.validate(run,damaged,ASOF,NOW)

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
                            "path":PATH,"repository":{"full_name":REPO},"head_sha":"a"*40,
                            "run_attempt":1,
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

    def test_list_detail_identity_drift_stops_before_jobs(self):
        run, jobs = fixture()
        # Old code accepted same-ID substituted detail and matching job SHA.
        for key, value in (
            ("head_sha", "b"*40),
            ("created_at", "2026-11-19T23:49:00Z"),
            ("run_attempt", True),
            ("id", float(RUN_ID)),
            ("repository", {"full_name": "other/project"}),
            ("status", "in_progress"),
        ):
            with self.subTest(key=key):
                detail = copy.deepcopy(run)
                detail[key] = value
                changed_jobs = copy.deepcopy(jobs)
                if key == "head_sha":
                    for job in changed_jobs["jobs"]:
                        job["head_sha"] = value
                calls = []
                def get(url):
                    calls.append(url)
                    if "/actions/workflows/" in url:
                        return {"total_count": 1, "workflow_runs": [run]}
                    if url.endswith("/jobs?per_page=100"):
                        return changed_jobs
                    return detail
                with self.assertRaisesRegex(proof.ReceiptHold,
                                            "PRIMARY_RUN_LIST_DETAIL_DRIFT"):
                    proof.audit(ASOF, now=NOW, get=get)
                self.assertEqual(len(calls), 2)

    def test_equivalent_utc_created_timestamp_is_not_false_drift(self):
        run, jobs = fixture()
        detail = copy.deepcopy(run)
        detail["created_at"] = "2026-11-19T18:50:00-05:00"
        def get(url):
            if "/actions/workflows/" in url:
                return {"total_count": 1, "workflow_runs": [run]}
            if url.endswith("/jobs?per_page=100"):
                return jobs
            return detail
        self.assertEqual(proof.audit(ASOF, now=NOW, get=get)["run_id"], RUN_ID)

    def test_dag_reason_is_safe_public_category(self):
        self.assertIn("PRIMARY_JOB_DAG_UNVERIFIED", proof.PUBLIC_ERRORS)
        self.assertIn("PRIMARY_RUN_LIST_DETAIL_DRIFT", proof.PUBLIC_ERRORS)

    def test_competing_natural_run_in_same_epoch_is_hold(self):
        # A second natural EOD could have touched the private writer even
        # when its final GitHub state is failed, queued or still in progress.
        # A green first producer is NOT a unique source receipt.
        cases=(("queued",None),("in_progress",None),
               ("completed","failure"),("completed","success"))
        for status,conclusion in cases:
            with self.subTest(status=status,conclusion=conclusion):
                run,jobs=fixture()
                calls=[]
                primary={"id":RUN_ID,"created_at":run["created_at"],
                         "head_branch":"main","event":"schedule",
                            "path":PATH,"repository":{"full_name":REPO},"head_sha":"a"*40,
                         "run_attempt":1,
                         "status":"completed","conclusion":"success"}
                competing={"id":RUN_ID+1,"created_at":"2026-11-19T23:52:00Z",
                           "head_branch":"main","event":"schedule",
                            "path":PATH,"repository":{"full_name":REPO},"head_sha":"a"*40,
                           "run_attempt":1,
                           "status":status,"conclusion":conclusion}
                def get(url):
                    calls.append(url)
                    if "/actions/workflows/" in url:
                        return {"total_count":2,
                                "workflow_runs":[primary,competing]}
                    if url.endswith("/jobs?per_page=100"):
                        return copy.deepcopy(jobs)
                    return copy.deepcopy(run)
                with self.assertRaisesRegex(
                        proof.ReceiptHold,"PRIMARY_EOD_EPOCH_AMBIGUOUS"):
                    proof.audit(ASOF,now=NOW,get=get)
                # Ambiguous selection must stop before selecting job records.
                self.assertEqual(len(calls),1)

    def test_successful_rerun_or_missing_attempt_cannot_be_unique_eod(self):
        run,jobs=fixture()
        for attempt in (2,0,'1',None):
            with self.subTest(attempt=attempt):
                calls=[]
                def get(url):
                    calls.append(url)
                    if "/actions/workflows/" in url:
                        return {"total_count":1,"workflow_runs":[{
                            "id":RUN_ID,"created_at":run["created_at"],
                            "head_branch":"main","event":"schedule",
                            "path":PATH,"repository":{"full_name":REPO},"head_sha":"a"*40,
                            "run_attempt":attempt,
                            "status":"completed","conclusion":"success"}]}
                    self.fail('UNEXPECTED_READ_AFTER_INVALID_ATTEMPT')
                with self.assertRaisesRegex(
                        proof.ReceiptHold,"PRIMARY_EOD_EPOCH_AMBIGUOUS"):
                    proof.audit(ASOF,now=NOW,get=get)
                self.assertEqual(len(calls),1)

    def test_successful_workflow_without_jobs_is_hold(self):
        run,jobs=fixture()
        def get(url):
            if "/actions/workflows/" in url:
                return {"total_count":1,
                        "workflow_runs":[{
                            "id":RUN_ID,"created_at":run["created_at"],
                            "head_branch":"main","event":"schedule",
                            "path":PATH,"repository":{"full_name":REPO},"head_sha":"a"*40,
                            "run_attempt":1,
                            "status":"completed","conclusion":"success"}]}
            if url.endswith("/jobs?per_page=100"):
                return {"total_count":0,"jobs":[]}
            return run
        with self.assertRaisesRegex(proof.ReceiptHold,
                                    "PRIMARY_JOB_RECEIPT_MISSING"):
            proof.audit(ASOF,now=NOW,get=get)

    def test_unbound_success_list_record_cannot_reach_job_receipt(self):
        run,_=fixture()
        for missing in ("path","repository","head_sha","id"):
            with self.subTest(missing=missing):
                row={"id":RUN_ID,"created_at":run["created_at"],
                     "head_branch":"main","event":"schedule","run_attempt":1,
                     "path":PATH,"repository":{"full_name":REPO},
                     "head_sha":"a"*40,"status":"completed",
                     "conclusion":"success"}
                row.pop(missing)
                calls=[]
                def get(url):
                    calls.append(url)
                    if "/actions/workflows/" in url:
                        return {"total_count":1,"workflow_runs":[row]}
                    self.fail('INVALID_RUN_MUST_NOT_REACH_JOB_GET')
                with self.assertRaisesRegex(
                        proof.ReceiptHold,"PRIMARY_EOD_EPOCH_AMBIGUOUS"):
                    proof.audit(ASOF,now=NOW,get=get)
                self.assertEqual(len(calls),1)

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
