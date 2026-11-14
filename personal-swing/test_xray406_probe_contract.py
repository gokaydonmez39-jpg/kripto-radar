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
