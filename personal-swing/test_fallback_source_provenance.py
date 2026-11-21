#!/usr/bin/env python3
"""Negative and boundary tests. Only synthetic identities; no vendor IO."""
from __future__ import annotations
import copy
import unittest
import fallback_source_provenance as f

ASOF = "2026-11-23"
CUT = "2026-11-23T21:45:00Z"
NOW = "2026-11-24T02:00:00Z"
SHA40 = "a" * 40
SHA64 = "b" * 64


def fixture():
    parent = {"id": 101, "repository": {"full_name": f.REPO},
              "path": f.PARENT_PATH, "event": "schedule",
              "head_branch": "main", "run_attempt": 1,
              "status": "completed", "conclusion": "success",
              "head_sha": SHA40,
              "created_at": "2026-11-24T00:50:00Z",
              "updated_at": "2026-11-24T00:55:00Z"}
    child = {"id": 102, "repository": {"full_name": f.REPO},
             "path": f.CHILD_PATH, "event": "workflow_dispatch",
             "head_branch": "main", "run_attempt": 1,
             "status": "completed", "conclusion": "success",
             "head_sha": SHA40, "created_at": "2026-11-24T00:53:00Z",
             "updated_at": "2026-11-24T01:50:00Z"}
    witness = {"schema": "XRAY_477_FALLBACK_PARENT_RECEIPT_V1",
               "parent_run_id": 101, "parent_source_event": "schedule",
               "parent_workflow": f.PARENT_PATH, "parent_head_sha": SHA40,
               "parent_ref": "refs/heads/main", "requested_asof_et": ASOF,
               "dispatch_request_accepted": True,
               "eod_completion_proven": False,
               "ab_release_authorized": False, "writes": 0, "orders": 0}
    child_witness = {"schema": "XRAY_477_RECOVERY_CHILD_RECEIPT_V1",
                     "parent_run_id": 101, "child_run_id": 102,
                     "asof_et": ASOF, "source_event": "workflow_dispatch",
                     "source_sha": SHA40, "source_readback_verified": True,
                     "orders": False}
    jobs = [{"id": i + 1, "name": name, "run_id": 102, "run_attempt": 1,
             "status": "completed", "conclusion": "success"}
            for i, name in enumerate(sorted(f.JOBS))]
    scan = {"asof_et": ASOF, "source_event": "workflow_dispatch",
            "run_id": 102, "requested": 477, "processed": 477, "valid": 477,
            "missing": 0, "final_ready": True,
            "independent_get_verified": True, "scope_sha": SHA64,
            "policy_sha": SHA64}
    lock = {"asof_et": ASOF, "owner_run_id": 102,
            "unique_reservation": True, "independent_get_verified": True,
            "competing_writer_observed": False}
    return [parent, witness, child, child_witness, jobs, scan, lock]


def verify(values, *, asof=ASOF, cutoff=CUT, now=NOW):
    return f.attest(*values, expected_asof=asof,
                    official_cutoff=cutoff, observed_at=now)


class SourceProvenanceAcceptance(unittest.TestCase):
    def test_complete_synthetic_chain_only_proves_source_not_delivery(self):
        r = verify(fixture())
        self.assertEqual(r["state"], "RECOVERY_CHAIN_PROVEN_READ_ONLY")
        self.assertTrue(r["parent_child_proven"])
        self.assertFalse(r["ab_release_authorized"])
        self.assertFalse(r["orders"])
        self.assertEqual(r["sheet_writes"], 0)
        self.assertEqual(r["device_ack"], "UNKNOWN")

    def test_parent_mutations_fail_closed(self):
        changes = [
            ("event", "workflow_dispatch"), ("path", f.CHILD_PATH),
            ("head_branch", "feature"), ("run_attempt", 2),
            ("status", "in_progress"), ("conclusion", "failure"),
            ("head_sha", "bad"),
            ("created_at", "2026-11-24T08:00:00Z"),
            ("updated_at", "2026-11-24T09:00:00Z"),
            ("repository", {"full_name": "wrong/repo"}),
        ]
        for k, v in changes:
            with self.subTest(key=k, value=v):
                p = fixture(); p[0][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_child_mutations_fail_closed(self):
        for k, v in [
            ("event", "schedule"), ("path", f.PARENT_PATH),
            ("head_branch", "feature"), ("run_attempt", 2),
            ("status", "queued"), ("conclusion", "failure"),
            ("created_at", "2026-11-23T20:00:00Z"),
            ("updated_at", "2026-11-24T06:00:00Z"),
        ]:
            with self.subTest(key=k):
                p = fixture(); p[2][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_parent_receipt_integrity(self):
        for k, v in [
            ("parent_run_id", 999), ("parent_source_event", "manual"),
            ("parent_workflow", "other"), ("parent_head_sha", "x" * 40),
            ("requested_asof_et", "2026-11-20"),
            ("dispatch_request_accepted", False),
            ("eod_completion_proven", True),
            ("ab_release_authorized", True), ("writes", 1), ("orders", 1),
        ]:
            with self.subTest(key=k):
                p = fixture(); p[1][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_child_receipt_parent_binding(self):
        for k, v in [
            ("parent_run_id", 1), ("child_run_id", 103),
            ("asof_et", "2026-11-20"), ("source_event", "schedule"),
            ("source_sha", "c" * 40),
            ("source_readback_verified", False), ("orders", True),
        ]:
            with self.subTest(key=k):
                p = fixture(); p[3][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_six_successful_jobs_required(self):
        for mutation in ("missing", "skipped", "duplicate", "foreign_run"):
            with self.subTest(mutation=mutation):
                p = fixture()
                if mutation == "missing": p[4].pop()
                if mutation == "skipped": p[4][0]["conclusion"] = "skipped"
                if mutation == "duplicate": p[4][1]["name"] = p[4][0]["name"]
                if mutation == "foreign_run": p[4][0]["run_id"] = 999
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_private_readback_must_bind_exact_child(self):
        for k, v in [
            ("asof_et", "2026-11-19"), ("source_event", "schedule"),
            ("run_id", 103), ("valid", 476), ("missing", 1),
            ("final_ready", False), ("scope_sha", ""),
            ("policy_sha", "bad"), ("independent_get_verified", False),
        ]:
            with self.subTest(key=k):
                p = fixture(); p[5][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_epoch_lock_cannot_be_assumed(self):
        for k, v in [
            ("asof_et", "2026-11-19"), ("owner_run_id", 103),
            ("unique_reservation", False),
            ("independent_get_verified", False),
            ("competing_writer_observed", True),
        ]:
            with self.subTest(key=k):
                p = fixture(); p[6][k] = v
                self.assertEqual(verify(p)["state"], "HOLD")

    def test_missing_full_epoch_lock(self):
        p = fixture(); p[6] = None
        self.assertEqual(verify(p)["stage"], "ATOMIC_EPOCH_LOCK_NOT_VERIFIED")

    def test_invalid_clock_and_session(self):
        for asof, cut, now in [
            ("2026-02-30", CUT, NOW), (ASOF, "bad", NOW),
            (ASOF, CUT, "2026-11-22T00:00:00Z"),
            ("2026-11-20", CUT, NOW),
        ]:
            with self.subTest(asof=asof,cut=cut,now=now):
                self.assertEqual(verify(fixture(), asof=asof, cutoff=cut, now=now)["state"], "HOLD")

    def test_historical_run_is_not_replay_authority(self):
        p = fixture()
        p[0]["created_at"] = "2026-11-25T00:00:00Z"
        p[0]["updated_at"] = "2026-11-25T00:01:00Z"
        self.assertEqual(verify(p)["state"], "HOLD")

    def test_pure_call_does_not_mutate_evidence(self):
        p = fixture()
        before = copy.deepcopy(p)
        verify(p)
        self.assertEqual(p, before)


if __name__ == "__main__":
    unittest.main()
