"""A36 deterministic proof: passing and failing controls, no network or side effects."""
from __future__ import annotations
import copy
import unittest
from a36_personal_source_audit import scan_sources, validate_report

SHA = "a" * 40
PY = "personal-swing/"
WF = ".github/workflows/xray-personal-demo.yml"


def corpus():
    return {PY + "engine.py": "def signal():\n    return 'AL'\n",
            PY + "daily_job.py": "import engine\n\ndef scan():\n    return engine.signal()\n",
            PY + "tracker.py": "import engine\n\ndef observe():\n    return engine.signal()\n",
            WF: "name: Example\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  check:\n    steps:\n      - uses: actions/checkout@" + "f"*40 + "\n      - run: python personal-swing/daily_job.py\n"}


class A36(unittest.TestCase):
    def test_positive_exact_edges(self):
        files = corpus()
        r = scan_sources(files, commit_sha=SHA)
        validate_report(r, files)
        self.assertEqual(len(r["edges"]), 3)
        self.assertEqual(sum(x["relation"].startswith("mentions") for x in r["edges"]), 1)
        self.assertTrue(all(e["confidence"] == "EXTRACTED" for e in r["edges"]))
        self.assertEqual(len(r["coverage_ledger"]), len(files))
        self.assertFalse(r["network_calls"])
        self.assertFalse(r["writes"])

    def test_mutated_report_source_is_rejected(self):
        files = corpus()
        r = scan_sources(files, commit_sha=SHA)
        files[PY + "engine.py"] += "# tampered\n"
        with self.assertRaisesRegex(ValueError, "COVERAGE_SOURCE_TAMPER"):
            validate_report(r, files)

    def test_missing_coverage_is_rejected(self):
        files = corpus()
        r = scan_sources(files, commit_sha=SHA)
        r["coverage_ledger"] = r["coverage_ledger"][:-1]
        with self.assertRaisesRegex(ValueError, "COVERAGE_INCOMPLETE"):
            validate_report(r, files)

    def test_unpinned_action_is_needs_validation_not_confirmed(self):
        files = corpus()
        files[WF] = files[WF].replace("f"*40, "main")
        r = scan_sources(files, commit_sha=SHA)
        self.assertIn("ACTION_NOT_SHA_PINNED", [x["code"] for x in r["findings"]])
        self.assertTrue(all(x["verdict"] == "needs_validation" for x in r["findings"]))
        self.assertTrue(all(x["severity"] is None for x in r["findings"]))

    def test_unpinned_reusable_workflow_job_is_detected(self):
        files = corpus()
        files[WF] += "  reusable:\n    uses: owner/repository/.github/workflows/child.yml@main\n"
        r = scan_sources(files, commit_sha=SHA)
        self.assertIn("ACTION_NOT_SHA_PINNED", [x["code"] for x in r["findings"]])

    def test_pinned_reusable_workflow_job_is_accepted(self):
        files = corpus()
        files[WF] += "  reusable:\n    uses: owner/repository/.github/workflows/child.yml@" + "b"*40 + "\n"
        r = scan_sources(files, commit_sha=SHA)
        self.assertFalse(any(x["code"] == "ACTION_NOT_SHA_PINNED" for x in r["findings"]))

    def test_pr_target_is_needs_validation_not_vulnerability(self):
        files = corpus()
        files[WF] += "  pull_request_target:\n"
        r = scan_sources(files, commit_sha=SHA)
        self.assertIn("PR_TARGET_TRUST_BOUNDARY_REVIEW", [x["code"] for x in r["findings"]])
        self.assertFalse(any(x["verdict"] == "confirmed" for x in r["findings"]))

    def test_reject_path_escape_and_symlink_style(self):
        for key in ("personal-swing/../secret.py", "/personal-swing/engine.py",
                    "personal-swing/evil\\thing.py"):
            f = corpus()
            f[key] = "a = 1\n"
            with self.assertRaisesRegex(ValueError, "PATH_OR_SOURCE_BOUND"):
                scan_sources(f, commit_sha=SHA)

    def test_comment_not_marked_execution(self):
        f = corpus()
        f[WF] = "name: Demo\n# python personal-swing/tracker.py\n"
        r = scan_sources(f, commit_sha=SHA)
        self.assertFalse(any(e["to"].endswith("tracker.py") for e in r["edges"]))

    def test_runtime_claim_fails_closed(self):
        f = corpus()
        r = scan_sources(f, commit_sha=SHA)
        r["runtime_reachable_proven"] = True
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_CAPABILITY_CLAIM"):
            validate_report(r, f)

    def test_dynamic_import_unproven(self):
        f = corpus()
        f[PY + "daily_job.py"] = "import importlib\nx = importlib.import_module('engine')\n"
        r = scan_sources(f, commit_sha=SHA)
        self.assertFalse(any(e["from"].endswith("daily_job.py") for e in r["edges"]))

    def test_invalid_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_COMMIT"):
            scan_sources(corpus(), commit_sha="main")

    def test_input_remains_unmodified_and_deterministic(self):
        f = corpus()
        original = copy.deepcopy(f)
        a = scan_sources(f, commit_sha=SHA)
        b = scan_sources(f, commit_sha=SHA)
        self.assertEqual(a, b)
        self.assertEqual(f, original)


if __name__ == "__main__":
    unittest.main()
