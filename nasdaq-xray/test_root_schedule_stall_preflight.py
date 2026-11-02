"""Hourly root schedule preflight — no false release, no permanent throttling."""
from __future__ import annotations
import datetime as dt
import pathlib
import unittest
from unittest.mock import patch

import root_schedule_stall_preflight as gate

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,2,18,tzinfo=UTC)
SHA="a"*40
RUN={
    "id":51,"name":"NASDAQ SWING XRAY Autonomous Data Plane",
    "head_branch":"main","created_at":"2026-11-02T16:30:00Z",
    "status":"completed","conclusion":"success","head_sha":SHA,
}
BASE={"event":"schedule","now":NOW,"runs":[RUN],
      "live_main":SHA,"local_head":SHA,"token":"TEST_READ_ONLY_TOKEN"}


def decide(**kwargs):
    return gate.decision(**{**BASE,**kwargs})


class RootScheduleCircuitTests(unittest.TestCase):
    def test_scheduled_semantic_stall_is_suppressed(self):
        with patch.object(gate,"permit_compute",return_value=True):
            o=decide(productivity=lambda *a: {"suppress":True,"reason":"SAME_ASOF_NO_RETRYABLE_HISTORY_NO_NEW_SOURCE"})
        self.assertFalse(o["allow"])
        self.assertEqual(o["reason"],"SAME_ASOF_NO_RETRYABLE_HISTORY_NO_NEW_SOURCE")

    def test_scheduled_new_evidence_releases_compute(self):
        with patch.object(gate,"permit_compute",return_value=True):
            o=decide(productivity=lambda *a: {"suppress":False,"reason":"NEW_TRACKED_SOURCE_OR_CODE_EVIDENCE"})
        self.assertTrue(o["allow"])
        self.assertEqual(o["reason"],"NEW_TRACKED_SOURCE_OR_CODE_EVIDENCE")

    def test_manual_dispatch_and_code_push_not_throttled(self):
        for event in ("workflow_dispatch","push"):
            with self.subTest(event=event):
                o=decide(event=event,token="",runs=[],live_main="",local_head="",
                         productivity=lambda *a: self.fail("UNEXPECTED_PROBE"))
                self.assertTrue(o["allow"])
                self.assertEqual(o["reason"],"EXPLICIT_OR_CODE_PUSH_DISTINCT_FROM_SCHEDULE")

    def test_failed_or_missing_prior_root_must_recover(self):
        with patch.object(gate,"permit_compute",return_value=True):
            self.assertTrue(decide(runs=[],productivity=lambda *a:None)["allow"])
            failed=dict(RUN,conclusion="failure")
            o=decide(runs=[failed],productivity=lambda *a: self.fail("WRONG_PROBE"))
            self.assertTrue(o["allow"])
            self.assertEqual(o["reason"],"LATEST_ROOT_FAILED_RECOVERY_ALLOWED")

    def test_unverifiable_source_cannot_burn_quota(self):
        tests=[
            ("token_missing", dict(token="")),
            ("main_moved",dict(local_head="b"*40)),
            ("invalid_root_rows",dict(runs=[None])),
            ("bad_event",dict(event="unknown")),
        ]
        for name,kwargs in tests:
            with self.subTest(name=name), patch.object(gate,"permit_compute",return_value=True):
                o=decide(**kwargs,productivity=lambda *a: self.fail("UNEXPECTED_PROBE"))
                self.assertFalse(o["allow"],name)

    def test_unverifiable_remote_probe_is_explicit_hold(self):
        with patch.object(gate,"permit_compute",return_value=True):
            def die(*a): raise TimeoutError("API_TIMEOUT")
            result=decide(productivity=die)
            self.assertFalse(result["allow"])
            self.assertEqual(result["reason"],"SOURCE_PROBE_FAILED_TimeoutError")
            result=decide(productivity=lambda *a: {})
            self.assertFalse(result["allow"])
            self.assertEqual(result["reason"],"SOURCE_PROBE_MALFORMED")

    def test_exchange_closed_root_not_a_data_plane_proof(self):
        closed=dict(RUN,id=52,created_at="2026-11-01T18:00:00Z")
        with patch.object(gate,"permit_compute",side_effect=lambda x,k:x.weekday() != 6):
            result=decide(runs=[closed],productivity=lambda *a:self.fail("SHOULD_NOT_PROBE"))
        self.assertTrue(result["allow"])
        self.assertEqual(result["reason"],"NO_PRIOR_COMPUTE_ROOT")

    def test_existing_root_workflow_has_two_independent_gates(self):
        workflow=(pathlib.Path(__file__).resolve().parents[1]/
                  ".github/workflows/nasdaq-xray-daily.yml").read_text()
        self.assertEqual(workflow.count('    - cron: "30 * * * *"'),1)
        self.assertEqual(workflow.count("  schedule:\n"),1)
        self.assertEqual(workflow.count("id: source_productivity"),1)
        self.assertIn("root_schedule_stall_preflight.py --emit",workflow)
        stages=[
            "Install zero-dollar research runtime",
            "Verify deterministic alpha semantics",
            "Run autonomous XRAY data plane",
            "Verify live root HISTORY source lineage and repair outcomes before commit",
            "Commit durable XRAY checkpoints",
        ]
        for stage in stages:
            start=workflow.index("- name: "+stage)
            block=workflow[start:start+310]
            self.assertIn("steps.session.outputs.allow_compute == 'true'",block)
            self.assertIn("steps.source_productivity.outputs.allow_compute == 'true'",block)
        relay=workflow.split("- name: Atomically wake pre-MC after root checkpoint",1)[1][:380]
        self.assertIn("steps.source_productivity.outputs.allow_compute == 'true'",relay)

if __name__=="__main__":
    unittest.main()
