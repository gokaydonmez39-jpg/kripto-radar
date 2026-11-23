#!/usr/bin/env python3
"""Adversarial NO-IO suite for the narrow scheduled tag canary."""
from __future__ import annotations
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import epoch_natural_claim_canary as canary
import epoch_lease as lease
from test_epoch_lease import ASOF, NOW, MockGit, env


def injected(environment, git, *, at=NOW, session=ASOF):
    # Fixed test-only clock and official XNAS session.
    return canary.run(environment, transport=git, now=at,
                      completed_session=lambda _: session)


class NaturalScheduleOnlyClaim(unittest.TestCase):
    def test_first_claim_readbacks_cannot_authorize_sheets_or_push(self):
        git=MockGit()
        e=env()
        e["GITHUB_TOKEN"]="synthetic-token-do-not-log"
        result=injected(e,git)
        self.assertEqual(result["status"],canary.PASS)
        self.assertEqual(result["asof_et"],ASOF)
        self.assertEqual(result["run_id"],int(e["GITHUB_RUN_ID"]))
        self.assertTrue(result["git_tag_verified"])
        self.assertEqual(result["sheet_writes"],0)
        self.assertFalse(result["orders"])
        self.assertFalse(result["ab_release_authorized"])
        self.assertEqual(result["device_ack"],"UNKNOWN")
        self.assertEqual(len(git.refs),1)
        self.assertEqual([x[1] for x in git.calls if x[0]=="POST"],
                         ["/git/tags","/git/refs"])
        self.assertTrue(all(x[0] in ("GET","POST") for x in git.calls))

    def test_second_same_epoch_is_never_repeated_or_authorized(self):
        git=MockGit()
        e=env()
        e["GITHUB_TOKEN"]="synthetic-token"
        injected(e,git)
        before=len([x for x in git.calls if x[0]=="POST" and
                    x[1]=="/git/refs"])
        with self.assertRaises(lease.LeaseHold):
            injected(e,git)
        self.assertEqual(len(git.refs),1)
        self.assertEqual(len([x for x in git.calls if x[0]=="POST" and
                              x[1]=="/git/refs"]),before+1)
        # No retry loop, no retrying the failed claimant.

    def test_non_natural_source_cannot_read_or_post(self):
        for mod in (
            {"GITHUB_EVENT_NAME":"workflow_dispatch"},
            {"GITHUB_REF":"refs/heads/attacker"},
            {"GITHUB_RUN_ATTEMPT":"2"},
            {"GITHUB_REPOSITORY":"someone/another-repo"},
            {"GITHUB_WORKFLOW_REF":"other/workflow"},
            {"GITHUB_SHA":"not-a-commit"},
            {"GITHUB_RUN_ID":"0"},
        ):
            with self.subTest(mod=mod):
                git=MockGit()
                e=env();e.update(mod);e["GITHUB_TOKEN"]="synthetic"
                with self.assertRaises(lease.LeaseHold):
                    injected(e,git)
                self.assertEqual(git.calls,[])

    def test_no_token_no_provider_request(self):
        git=MockGit()
        e=env()
        with self.assertRaisesRegex(lease.LeaseHold,"CANARY_TOKEN_UNAVAILABLE"):
            injected(e,git)
        self.assertEqual(git.calls,[])

    def test_wrong_completed_session_never_writes(self):
        git=MockGit()
        e=env();e["GITHUB_TOKEN"]="synthetic"
        with self.assertRaises(lease.LeaseHold):
            injected(e,git,session="2026-11-20")
        self.assertEqual(git.refs,{})
        self.assertFalse([x for x in git.calls if x[0]=="POST"])

    def test_missing_or_mutable_ruleset_never_writes(self):
        for state in ("absent","disabled","no_update","no_non_fast_forward",
                      "bypass","bypass_hidden"):
            with self.subTest(state=state):
                git=MockGit();git.protection=state
                e=env();e["GITHUB_TOKEN"]="synthetic"
                with self.assertRaises(lease.LeaseHold):
                    injected(e,git)
                self.assertEqual(git.refs,{})
                self.assertFalse([x for x in git.calls if x[0]=="POST"])

    def test_duplicate_natural_run_readback_never_post(self):
        git=MockGit()
        git.run_overrides={"event":"workflow_dispatch"}
        e=env();e["GITHUB_TOKEN"]="synthetic"
        with self.assertRaises(lease.LeaseHold):
            injected(e,git)
        self.assertEqual(git.refs,{})
        self.assertFalse([x for x in git.calls if x[0]=="POST"])

    def test_provider_timeout_does_not_retry(self):
        git=MockGit()
        e=env();e["GITHUB_TOKEN"]="synthetic"
        from urllib.error import URLError
        class FailsOnFirstTag:
            def __init__(self):self.tag_tries=0
            def __call__(self,method,path,body=None):
                if method=="POST" and path=="/git/tags":
                    self.tag_tries+=1
                    raise URLError("secret-provider-response")
                return git(method,path,body)
        fail=FailsOnFirstTag()
        with self.assertRaises(lease.LeaseHold):
            injected(e,fail)
        self.assertEqual(fail.tag_tries,1)
        self.assertEqual(git.refs,{})

    def test_entry_has_no_asof_or_manual_replay_option(self):
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(canary.main(["--schedule-canary","2026-11-20"]),3)
        parsed=json.loads(output.getvalue())
        self.assertEqual(parsed["status"],canary.HOLD)
        self.assertFalse(parsed["ab_release_authorized"])
        self.assertNotIn("GITHUB_TOKEN",output.getvalue())

    def test_runtime_error_log_is_redacted_and_nonblocking(self):
        out=io.StringIO()
        with patch.object(canary,"run",side_effect=RuntimeError(
                "EXTREMELY_SENSITIVE_PROVIDER_TOKEN")):
            with redirect_stdout(out):
                self.assertEqual(canary.main(["--schedule-canary"]),0)
        text=out.getvalue()
        self.assertNotIn("EXTREMELY_SENSITIVE_PROVIDER_TOKEN",text)
        v=json.loads(text)
        self.assertEqual(v["status"],canary.HOLD)
        self.assertEqual(v["sheet_writes"],0)
        self.assertFalse(v["ab_release_authorized"])

    def test_valid_shape_has_exact_nontrading_public_fields(self):
        git=MockGit()
        e=env();e["GITHUB_TOKEN"]="synthetic"
        result=injected(e,git)
        self.assertEqual(set(result),{"schema","status","asof_et",
            "run_id","git_tag_verified","sheet_writes","orders",
            "ab_release_authorized","device_ack"})

    def test_required_workflow_has_single_limited_schedule_only_step(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent/
            ".github/workflows/xray-personal-477-eod.yml").read_text()
        self.assertEqual(workflow.count(
            "- name: Bounded natural Git protected-tag first-claim canary"),1)
        self.assertEqual(workflow.count("python epoch_natural_claim_canary.py --schedule-canary"),1)
        scan=workflow.split("\n  daily-private-scan:",1)[1].split(
            "\n  private-sheets-auth-preflight:",1)[0]
        self.assertIn("      contents: write",scan)
        self.assertIn("      actions: read",scan)
        self.assertIn("github.event_name == 'schedule'",scan)
        self.assertIn("github.run_attempt == 1",scan)
        self.assertIn("github.ref == 'refs/heads/main'",scan)
        self.assertIn("persist-credentials: false",scan)
        self.assertNotIn("XRAY_PERSONAL477_EPOCH_LEASE_MODE: ENFORCE",workflow)
        self.assertEqual(workflow.count("    - cron: '16 23 * * 1-5'"),1)
        before=workflow.split("\n  daily-private-scan:",1)[0]
        self.assertNotIn("contents: write",before)
        after=workflow.split("\n  private-sheets-auth-preflight:",1)[1]
        self.assertNotIn("contents: write",after)



class NaturalScheduleSummaryWitness(unittest.TestCase):
    """Advisory GitHub step summary must expose claim HOLD distinct from job success."""

    def test_failed_claim_prints_redacted_explicit_hold_in_step_summary(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            summary=Path(folder)/"gh_summary"
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY":str(summary)}):
                with patch.object(canary, "run", side_effect=RuntimeError(
                        "SECRET_PROVIDER_DETAIL_MUST_NOT_LEAK")):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(canary.main(["--schedule-canary"]),0)
            content=summary.read_text()
            self.assertIn("XRAY_NASDAQ_EPOCH_CANARY=HOLD_NO_TAG_AUTHORITY",content)
            self.assertNotIn("SECRET_PROVIDER_DETAIL_MUST_NOT_LEAK",content)
            self.assertNotIn("PASS_GITHUB_TAG",content)

    def test_successful_claim_only_summary_reports_tag_not_eod_or_device(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            summary=Path(folder)/"gh_summary"
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY":str(summary)}):
                with patch.object(canary, "run",
                                  return_value={"status":canary.PASS}):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(canary.main(["--schedule-canary"]),0)
            content=summary.read_text()
            self.assertIn("XRAY_NASDAQ_EPOCH_CANARY=PASS_GITHUB_TAG_READBACK_ONLY",content)
            self.assertIn("NOT_EOD_NOT_SHEET_NOT_DEVICE_ACK",content)
            self.assertNotIn("FULL_FINAL=PASS",content)


if __name__=="__main__":
    unittest.main()
