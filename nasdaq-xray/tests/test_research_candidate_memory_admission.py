#!/usr/bin/env python3
"""Negative/positive admission tests: API run identity and receipt time fence."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_candidate_memory_admission as a
from test_research_candidate_memory import receipt


def run():
    return {
        "id": 567, "name":
            "XRAY Research Operations Cross-Artifact Acceptance (No AL)",
        "path": a.WORKFLOW, "status": "completed",
        "conclusion": "success", "head_branch": "main",
        "head_repository": {"full_name": a.REPO},
        "repository": {"full_name": a.REPO},
        "head_sha": "a" * 40,
        "created_at": "2026-10-16T12:50:00Z",
        "updated_at": "2026-10-16T12:52:00Z",
    }


def artifact():
    return {"id": 12345, "name": a.ARTIFACT, "expired": False,
            "size_in_bytes": 1004, "workflow_run": {"id": 567}}


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.run = run()
        self.receipt = receipt()
        self.artifact = artifact()
        self.args = {
            "expected_asof": "2026-10-15",
            "expected_run_id": 567,
            "now_utc": dt.datetime(2026, 10, 16, 15, tzinfo=dt.timezone.utc),
        }

    def admit(self, r=None, v=None, artifact_override=None, **kwargs):
        opts = dict(self.args)
        opts.update(kwargs)
        return a.admit(self.run if r is None else r,
                       self.receipt if v is None else v,
                       artifact=self.artifact if artifact_override is None
                       else artifact_override, **opts)

    def test_positive_research_only(self):
        report = self.admit()
        self.assertEqual(report["symbolic_watch_count"], 2)
        self.assertEqual(report["run_id"], 567)
        self.assertFalse(report["alpha_authority"])
        self.assertFalse(report["iphone_receipt_attested"])

    def test_forged_workflow_and_repository(self):
        for change in (
            {"name": "Impostor"},
            {"path": "other-workflow.yml"},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"head_branch": "feature"},
            {"head_repository": {"full_name": "evil/repo"}},
            {"repository": {"full_name": "evil/repo"}},
            {"head_sha": "bad"},
            {"id": "567"},
        ):
            with self.subTest(change=change):
                r = {**self.run, **change}
                with self.assertRaises(ValueError):
                    self.admit(r=r)

    def test_event_id_and_artifact_metadata(self):
        with self.assertRaisesRegex(ValueError, "RUN_ID_EVENT_MISMATCH"):
            self.admit(expected_run_id=568)
        for changed in (
            {"name": "another"},
            {"expired": True},
            {"workflow_run": {"id": 999}},
            {"size_in_bytes": 0},
            {"size_in_bytes": 1048577},
            {"id": None},
        ):
            with self.subTest(changed=changed):
                art = {**self.artifact, **changed}
                with self.assertRaises(ValueError):
                    self.admit(artifact_override=art)

    def test_epoch_and_temporal_fences(self):
        with self.assertRaisesRegex(ValueError, "WRONG_OFFICIAL_COMPLETED_SESSION"):
            self.admit(expected_asof="2026-10-16")
        with self.assertRaisesRegex(ValueError, "RUN_IN_FUTURE"):
            self.admit(now_utc=dt.datetime(
                2026, 10, 15, 10, tzinfo=dt.timezone.utc))
        r = copy.deepcopy(self.run)
        r["created_at"] = "2026-10-17T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "RUN_NEGATIVE_DURATION"):
            self.admit(r=r)
        r = copy.deepcopy(self.run)
        r["created_at"] = "2026-10-16T12:50:00"
        with self.assertRaisesRegex(ValueError, "RUN_TIMESTAMP_UTC"):
            self.admit(r=r)

    def test_al_and_provenance_forgery(self):
        v = copy.deepcopy(self.receipt)
        v["registered_R92_count"] = 1
        with self.assertRaises(ValueError):
            self.admit(v=v)
        v = copy.deepcopy(self.receipt)
        v["research_watch_families"]["MANH"] = ["A"]
        with self.assertRaises(ValueError):
            self.admit(v=v)


if __name__ == "__main__":
    unittest.main()
