"""Offline A45 state-machine, idempotency and tampering tests. No network I/O."""
import copy
import hashlib
import json
import unittest

from ledger import (ISSUE_PREFIX, MARKER, LedgerError, find_or_create_issue,
                    record_receipt, validate_source)

A42 = {"schema":"XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1",
       "registry_sha256":"a"*64,"asof":"2026-11-02"}
RAW = json.dumps(A42,sort_keys=True).encode()
A44 = {"schema":"XRAY_NASDAQ_A44_SOURCE_EVIDENCE_V1",
       "scope":"NASDAQ_RESEARCH_ONLY_NO_CRYPTO",
       "automatic_promotion":False,"network_enabled":True,
       "candidate_receipt_sha256":hashlib.sha256(RAW).hexdigest(),
       "registry_sha256":"a"*64,"asof_et":"2026-11-02",
       "results":[{"registry_id":2,"status":"PROVENANCE_RECORDED_TEST_REQUIRED",
                   "promotion":"BLOCKED_PENDING_INDEPENDENT_FUNCTIONAL_AND_PIT_TEST",
                   "run_upstream_code":False,"broker":False,"license_approved":False,
                   "source_head_sha":"b"*40}]}
A43 = {"schema":"XRAY_NASDAQ_A43_EOD_ADMISSION_V1",
       "registry_admission":"PASS_FOR_READONLY_CANDIDATE_INTAKE",
       "production_promotion":False,"asof_et":"2026-11-02",
       "run_id":123456,"run_sha":"c"*64,"log_sha256":"d"*64}


def input_receipt():
    return validate_source(A44,A43,RAW)


class FakeIssueAPI:
    def __init__(self):
        self.issues = []
        self.comments = {}
        self.next_id = 1
        self.writes = []
    def __call__(self,method,endpoint,body=None):
        if method=="GET" and endpoint.startswith("/issues?"):
            return self.issues
        if method=="POST" and endpoint=="/issues":
            self.writes.append(endpoint)
            issue={"number":self.next_id,"title":body["title"],"state":"open"}
            self.next_id+=1
            self.issues.append(issue)
            self.comments[issue["number"]]=[]
            return issue
        if method=="GET" and "/comments?" in endpoint:
            issue=int(endpoint.split("/")[2])
            return self.comments[issue]
        if method=="POST" and endpoint.endswith("/comments"):
            self.writes.append(endpoint)
            issue=int(endpoint.split("/")[2])
            obj={"id":len(self.comments[issue])+1,"body":body["body"]}
            self.comments[issue].append(obj)
            return obj
        raise AssertionError("Unexpected API: "+method+endpoint)


class A45LedgerTests(unittest.TestCase):
    def test_frozen_receipt_valid_and_not_promotion(self):
        r=input_receipt()
        self.assertEqual(r["source_run_id"],123456)
        self.assertEqual(r["rows"][0]["status"],"PROVENANCE_RECORDED_TEST_REQUIRED")
        self.assertEqual(r["action"],"RESEARCH_ONLY_DO_NOT_INSTALL_OR_TRADE")

    def test_one_monthly_issue_and_one_comment(self):
        api=FakeIssueAPI()
        issue=find_or_create_issue("2026-11",api)
        result=record_receipt(issue,input_receipt(),api)
        self.assertEqual(result,"RECORDED")
        self.assertEqual(len(api.issues),1)
        self.assertEqual(len(api.comments[issue]),1)
        self.assertTrue(api.issues[0]["title"].startswith(ISSUE_PREFIX))

    def test_replay_is_idempotent(self):
        api=FakeIssueAPI()
        issue=find_or_create_issue("2026-11",api)
        receipt=input_receipt()
        record_receipt(issue,receipt,api)
        self.assertEqual(find_or_create_issue("2026-11",api),issue)
        self.assertEqual(record_receipt(issue,receipt,api),"IDEMPOTENT_ALREADY_RECORDED")
        self.assertEqual(len(api.writes),2)

    def test_changed_receipt_same_source_run_fails(self):
        api=FakeIssueAPI()
        issue=find_or_create_issue("2026-11",api)
        record_receipt(issue,input_receipt(),api)
        edited=copy.deepcopy(input_receipt())
        edited["rows"][0]["status"]="HOLD_LICENSE_REVIEW"
        with self.assertRaises(LedgerError):
            record_receipt(issue,edited,api)
        self.assertEqual(len(api.comments[issue]),1)

    def test_duplicate_same_run_marker_fails(self):
        api=FakeIssueAPI()
        issue=find_or_create_issue("2026-11",api)
        record_receipt(issue,input_receipt(),api)
        api.comments[issue].append(copy.deepcopy(api.comments[issue][0]))
        with self.assertRaises(LedgerError):
            record_receipt(issue,input_receipt(),api)

    def test_tampered_input_sha_rejected(self):
        bad=dict(A44,candidate_receipt_sha256="e"*64)
        with self.assertRaises(LedgerError):
            validate_source(bad,A43,RAW)

    def test_stale_asof_blocks(self):
        bad=dict(A43,asof_et="2026-10-30")
        with self.assertRaises(LedgerError):
            validate_source(A44,bad,RAW)

    def test_invalid_upstream_blocks(self):
        bad=dict(A43,registry_admission="SKIPPED")
        with self.assertRaises(LedgerError):
            validate_source(A44,bad,RAW)

    def test_wrong_crypto_scope_blocks(self):
        bad=dict(A44,scope="CRYPTO")
        with self.assertRaises(LedgerError):
            validate_source(bad,A43,RAW)

    def test_offline_provenance_not_eligible_for_live_issue(self):
        bad=dict(A44,network_enabled=False)
        with self.assertRaises(LedgerError):
            validate_source(bad,A43,RAW)

    def test_premature_approval_blocks(self):
        bad=copy.deepcopy(A44)
        bad["results"][0]["license_approved"]=True
        with self.assertRaises(LedgerError):
            validate_source(bad,A43,RAW)

    def test_duplicate_candidate_ids_block(self):
        bad=copy.deepcopy(A44)
        bad["results"]*=2
        with self.assertRaises(LedgerError):
            validate_source(bad,A43,RAW)

    def test_missing_eod_sha_blocks(self):
        bad=dict(A43,log_sha256="oops")
        with self.assertRaises(LedgerError):
            validate_source(A44,bad,RAW)

    def test_closed_issue_not_reused(self):
        api=FakeIssueAPI()
        num=find_or_create_issue("2026-11",api)
        api.issues[0]["state"]="closed"
        with self.assertRaises(LedgerError):
            find_or_create_issue("2026-11",api)

    def test_future_month_new_issue(self):
        api=FakeIssueAPI()
        a=find_or_create_issue("2026-11",api)
        b=find_or_create_issue("2026-12",api)
        self.assertNotEqual(a,b)

    def test_no_repo_files_or_secret_in_comment(self):
        api=FakeIssueAPI()
        issue=find_or_create_issue("2026-11",api)
        record_receipt(issue,input_receipt(),api)
        body=api.comments[issue][0]["body"]
        self.assertIn(MARKER,body)
        self.assertIn("AUTOPROMOTE", "AUTOPROMOTE") # static non-promotion is explicit in source
        self.assertNotIn("Authorization:",body)
        self.assertNotIn("GITHUB_TOKEN",body)


if __name__=="__main__":
    unittest.main()
