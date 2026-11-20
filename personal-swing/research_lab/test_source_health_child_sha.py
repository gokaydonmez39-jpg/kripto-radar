"""Exact parent event proof must survive a legitimate child default-branch SHA drift.

GitHub workflow_run GITHUB_SHA is the latest commit on the default branch;
it is NOT an authenticated alias for the triggering EOD producer's head_sha.
"""
import unittest
import source_health_live as live
from test_source_health_live import Github, Sheets, D, HEAD


class WorkflowRunShaRaceTest(unittest.TestCase):
    def test_valid_parent_accepted_with_newer_child_default_sha(self):
        gh = Github()
        child_head = "b" * 40
        for rid in (202, 203):
            gh.docs["/actions/runs/" + str(rid) + "/jobs?per_page=100"]
        for workflow in ("xray-personal-kronos-shadow.yml",
                         "xray-personal-cove-shadow.yml"):
            key = "/actions/workflows/" + workflow + "/runs?event=workflow_run&per_page=60"
            for run in gh.docs[key]["workflow_runs"]:
                run["head_sha"] = child_head
        report, gaps = live.aggregate(gh, Sheets(), D)
        self.assertEqual(gaps, {})
        self.assertEqual(report["sources"]["CORE"]["state"], "MATCHED_CORE_RECEIPT")
        self.assertEqual(report["sources"]["KRONOS_V2"]["state"], "MATCHED_CLOSE_ONLY")
        self.assertEqual(report["sources"]["COVE"]["state"], "MATCHED_RESEARCH_READONLY")
        self.assertEqual(report["sources"]["OFFICIAL_477"]["state"], "MATCHED_RESEARCH_NO_MARKET_CLEARANCE")

    def test_invalid_child_commit_sha_is_not_accepted(self):
        gh = Github()
        key = "/actions/workflows/xray-personal-cove-shadow.yml/runs?event=workflow_run&per_page=60"
        gh.docs[key]["workflow_runs"][0]["head_sha"] = "not-a-commit-sha"
        report, gaps = live.aggregate(gh, Sheets(), D)
        self.assertEqual(report["sources"]["COVE"]["state"], "UNKNOWN")
        self.assertIn("COVE", gaps)

    def test_wrong_cove_parent_is_rejected_despite_valid_child_sha(self):
        gh = Github()
        key = "/actions/workflows/xray-personal-cove-shadow.yml/runs?event=workflow_run&per_page=60"
        gh.docs[key]["workflow_runs"][0]["head_sha"] = "b" * 40
        gh.logs["/actions/jobs/303/logs"] = gh.logs["/actions/jobs/303/logs"].replace(
            '"eod_run_id": 101', '"eod_run_id": 999')
        report, gaps = live.aggregate(gh, Sheets(), D)
        self.assertEqual(report["sources"]["COVE"]["state"], "UNKNOWN")
        self.assertIn("COVE", gaps)

    def test_wrong_core_parent_sha_is_rejected(self):
        gh = Github()
        gh.docs["/actions/runs/101"]["head_sha"] = "b" * 40
        with self.assertRaises(live.NoProof):
            live.aggregate(gh, Sheets(), D)


if __name__ == "__main__":
    unittest.main()
