"""Offline tests of natural parent provenance and two independent readbacks."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import research_epoch_binding as eb


def event():
    return {"action": "completed", "repository": {"full_name": eb.REPO},
            "workflow_run": {"path": eb.EOD_PATH, "id": 1234, "event": "schedule",
                             "head_repository": {"full_name": eb.REPO}, "head_branch": "main",
                             "head_sha": "a"*40, "run_attempt": 1,
                             "status": "completed", "conclusion": "success"}}


class ResearchEpochBindingTest(unittest.TestCase):
    def run_event(self, value, **env_edits):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "event.json"
            path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
            env = {"GITHUB_EVENT_PATH": str(path), "GITHUB_EVENT_NAME": "workflow_run",
                   "GITHUB_REPOSITORY": eb.REPO} | env_edits
            return eb.scheduled_parent(env)

    def test_exact_scheduled_parent_then_two_receipts(self):
        parent = self.run_event(event())
        self.assertEqual(parent, eb.Parent(1234,"a"*40))
        for url in [eb.EOD_WEB+"1234", eb.EOD_WEB+"1234/jobs/987"]:
            self.assertIsNone(eb.verify_sheet_parent(parent, url, url))
        self.assertEqual(eb.redacted_parent(parent,"2026-01-02"),
                         {"asof_et":"2026-01-02", "eod_run_id":1234, "eod_head_sha":"a"*40})

    def test_wrong_parent_event_is_denied_even_when_green(self):
        for key, v in [("event", "workflow_dispatch"), ("run_attempt", 2), ("id", True),
                       ("head_branch", "feature"), ("head_sha", "not-sha"),
                       ("path", ".github/workflows/different.yml"), ("conclusion", "failure"),
                       ("head_repository", {"full_name":"other/project"})]:
            with self.subTest(key=key, value=v), self.assertRaisesRegex(
                    eb.EpochBindingError,"PARENT_NOT_EXACT_NATURAL_EOD"):
                x=event()
                x["workflow_run"][key]=v
                self.run_event(x)

    def test_child_context_and_payload_owner_checked(self):
        with self.assertRaisesRegex(eb.EpochBindingError,"NOT_PERSONAL_RESEARCH_WORKFLOW_EVENT"):
            self.run_event(event(), GITHUB_EVENT_NAME="workflow_dispatch")
        doc=event()
        doc["repository"]["full_name"]="other/project"
        with self.assertRaisesRegex(eb.EpochBindingError,"PARENT_EVENT_IDENTITY"):
            self.run_event(doc)

    def test_duplicate_json_and_size_are_denied(self):
        with self.assertRaisesRegex(eb.EpochBindingError,"DUPLICATE_PARENT_EVENT_FIELD"):
            self.run_event('{"action":"completed","action":"other"}')
        with self.assertRaisesRegex(eb.EpochBindingError,"PARENT_EVENT_SIZE"):
            self.run_event(" "*(eb.MAX_EVENT_BYTES+1))

    def test_matching_asof_does_not_override_source_run(self):
        parent=self.run_event(event())
        valid=eb.EOD_WEB+"1234"
        for scan, score in [(valid,eb.EOD_WEB+"1235"), (valid+"/jobs/2",valid+"/jobs/3"),
                            (valid+"#fake",valid+"#fake"),
                            (valid.replace("github.com/","alternate.test/"),valid), (None,valid)]:
            with self.subTest(scan=scan, score=score), self.assertRaisesRegex(
                    eb.EpochBindingError,"PARENT_SHEET_RECEIPTS_MISMATCH"):
                eb.verify_sheet_parent(parent,scan,score)

    def test_payload_not_returned_or_modified(self):
        x=event() | {"private_example": "DO_NOT_REPEAT_FIXTURE"}
        before=deepcopy(x)
        parent=self.run_event(x)
        self.assertEqual(x,before)
        self.assertNotIn("DO_NOT_REPEAT_FIXTURE",json.dumps(eb.redacted_parent(parent,"2026-01-02")))
