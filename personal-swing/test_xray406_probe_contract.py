"""Synthetic positive and negative tests, no network or writes."""
from dataclasses import replace
from pathlib import Path
import unittest

from xray406_probe_contract import (
    Candidate, CHECK, GITHUB_ACTIONS_APP, REPOSITORY, STAGING, TARGET, WORKFLOW,
    admission, require_fixture,
)


class ProbeContractTests(unittest.TestCase):
    def setUp(self):
        self.base = "a" * 40
        self.head = "b" * 40
        self.c = Candidate(REPOSITORY, STAGING, TARGET, self.head, self.head,
                           self.base, self.base, self.base)
        self.run = dict(head_sha=self.head, head_branch=STAGING, path=WORKFLOW,
                        event="push", status="completed", conclusion="success",
                        repository={"full_name": REPOSITORY},
                        head_repository={"full_name": REPOSITORY})
        self.check = dict(name=CHECK, head_sha=self.head, status="completed",
                          conclusion="success", app={"id": GITHUB_ACTIONS_APP})

    def test_exact_green_fast_forward(self):
        self.assertEqual(admission(self.c, self.run, [self.check]),
                         "ALLOW_ISOLATED_FAST_FORWARD")

    def test_refuse_production_or_untrusted_repository(self):
        for field, value in (("target_branch", "main"), ("source_branch", "main"),
                             ("repository", "another/repository")):
            with self.subTest(field=field):
                self.assertEqual(admission(replace(self.c, **{field: value}),
                                           self.run, [self.check]), "SCOPE_REFUSED")

    def test_refuse_missing_or_duplicate_check(self):
        for records in ([], [self.check, self.check]):
            self.assertEqual(admission(self.c, self.run, records),
                             "CHECK_MISSING_OR_AMBIGUOUS")

    def test_refuse_wrong_app_sha_and_non_success(self):
        for changed in (dict(app={"id": 1}), dict(head_sha=self.base),
                        dict(status="in_progress"), dict(conclusion="skipped"),
                        dict(conclusion="neutral"), dict(conclusion="failure")):
            self.assertEqual(admission(self.c, self.run, [self.check | changed]),
                             "CHECK_NOT_VERIFIED")

    def test_refuse_wrong_workflow_event_ref_status_or_repository(self):
        for changed in (dict(path="other.yml"), dict(event="pull_request"),
                        dict(head_branch=TARGET), dict(head_sha=self.base),
                        dict(status="in_progress"), dict(conclusion="failure"),
                        dict(head_repository={"full_name": "fork/repository"})):
            self.assertEqual(admission(self.c, self.run | changed, [self.check]),
                             "WORKFLOW_NOT_VERIFIED")

    def test_refuse_changed_source_target_and_divergence(self):
        for changed, result in (
            (dict(observed_source_sha="c" * 40), "STAGING_HEAD_CHANGED"),
            (dict(observed_target_sha="c" * 40), "TARGET_HEAD_CHANGED"),
            (dict(merge_base_sha="c" * 40), "NOT_FAST_FORWARD"),
            (dict(merge_base_sha="bad"), "INVALID_SHA"),
            (dict(expected_target_sha=self.head, observed_target_sha=self.head),
             "ALREADY_AT_CANDIDATE"),
        ):
            self.assertEqual(admission(replace(self.c, **changed), self.run, [self.check]),
                             result)

    def test_probe_fixture_and_negative_control(self):
        require_fixture(Path(__file__).with_name("xray406_probe_case.txt").read_text())
        for value in ("FAIL\n", "", "PASS", "PASS\nPASS\n"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "XRAY_406_PROBE_FIXTURE_REJECTED"):
                    require_fixture(value)


class PublicationEvidenceTests(unittest.TestCase):
    def setUp(self):
        from xray406_probe_contract import PublicationEvidence
        self.commit = "c" * 40
        self.blob = "d" * 40
        self.cutoff = "2026-11-13T21:45:00Z"
        self.e = PublicationEvidence(REPOSITORY, TARGET, self.commit,
                                     self.blob, "2026-11-13T21:44:58Z")

    def test_exact_timely_target_readback(self):
        from xray406_probe_contract import publication_admission
        self.assertEqual(publication_admission(self.e, self.commit, self.blob, self.cutoff),
                         "ISOLATED_READBACK_BEFORE_CUTOFF")

    def test_early_commit_is_not_publication_evidence(self):
        from xray406_probe_contract import publication_admission
        self.assertEqual(publication_admission(None, self.commit, self.blob, self.cutoff),
                         "PUBLICATION_EVIDENCE_MISSING")
        late = replace(self.e, observed_at_utc="2026-11-13T21:46:00Z")
        self.assertEqual(publication_admission(late, self.commit, self.blob, self.cutoff),
                         "LATE_OR_UNPROVEN_PUBLICATION")

    def test_wrong_target_sha_blob_or_timezone_refused(self):
        from xray406_probe_contract import publication_admission
        for change, reason in (
            (dict(target_branch=STAGING), "SCOPE_REFUSED"),
            (dict(target_branch="main"), "SCOPE_REFUSED"),
            (dict(observed_target_sha="e" * 40), "PUBLICATION_READBACK_MISMATCH"),
            (dict(observed_blob_sha="e" * 40), "PUBLICATION_READBACK_MISMATCH"),
            (dict(observed_at_utc="2026-11-13T21:44:58"), "PUBLICATION_CLOCK_INVALID"),
        ):
            with self.subTest(change=change):
                self.assertEqual(
                    publication_admission(replace(self.e, **change), self.commit, self.blob,
                                          self.cutoff), reason
                )
