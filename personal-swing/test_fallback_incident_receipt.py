"""Pure offline negative acceptance tests: no provider or repository writes."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

import fallback_incident_receipt as receipt


def payload(**fields):
    base = {
        "status": "BLOCKED_DISPATCH_NOT_CONFIRMED",
        "reason_code": "NATURAL_FALLBACK_POLICY_LOCKED",
        "asof_et": "2026-11-20",
        "dispatch_requested": False,
        "execution": "NONE",
    }
    base.update(fields)
    return (json.dumps(base) + "\n").encode()


class RedactedFallbackReceipt(unittest.TestCase):
    def test_real_missing_primary_lock_produces_exact_safe_category(self):
        got = receipt.classify(payload())
        self.assertEqual(got, {"category": "MISSING_PRIMARY_RECOVERY_POLICY_LOCKED", "asof": "2026-11-20"})
        view = receipt.render(got)
        self.assertIn("NO_WORKFLOW_DISPATCH", view)
        self.assertIn("Canonical EOD completion: \x60UNVERIFIED\x60", view)
        self.assertIn("ChatGPT delivery: \x60UNKNOWN\x60", view)

    def test_unknown_dispatch_status_cannot_masquerade_as_safe_gap(self):
        for changes in ({"reason_code": "UNTRUSTED"}, {"dispatch_requested": True},
                        {"execution": "EXECUTED"}, {"asof_et": "2026-11-31"},
                        {"status": "DISPATCH_REQUEST_ACCEPTED_NOT_COMPLETED"}):
            with self.subTest(changes=changes):
                self.assertEqual(receipt.classify(payload(**changes))["category"], "UNVERIFIED_FAILURE")

    def test_known_expired_window_remains_hold_not_false_green(self):
        got = receipt.classify(payload(status="BLOCKED_NATURAL_FALLBACK_EXPIRED"))
        self.assertEqual(got["category"], "NATURAL_WINDOW_EXPIRED")
        self.assertIn("Recovery: \x60HOLD\x60", receipt.render(got))

    def test_provider_exception_has_no_claim_of_a_missing_asof(self):
        got = receipt.classify(payload(status="BLOCKED_GITHUB_API_UNCERTAIN", asof_et="2026-11-20"))
        self.assertEqual(got, {"category": "GITHUB_READ_UNCERTAIN", "asof": "UNKNOWN"})
        self.assertIn("DISPATCH_STATE_UNVERIFIED", receipt.render(got))

    def test_adversarial_and_incomplete_input_never_echoed(self):
        attack = "TOP_SECRET\n<svg><script>steal()</script>"
        cases = [None, "bad", b"", b"{}\n", b"{}\n{}\n", b"\xff\n",
                 payload(asof_et=attack), payload(status=attack),
                 payload(reason_code=attack), b"A" * 8193]
        for item in cases:
            with self.subTest(item=str(item)[:20]):
                view = receipt.render(receipt.classify(item))
                self.assertNotIn("TOP_SECRET", view)
                self.assertNotIn("<svg>", view)
                self.assertIn("UNVERIFIED", view)

    def test_cli_appends_summary_without_overwriting_existing_and_no_raw_json(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "incident.json")
            target = Path(folder, "summary.md")
            source.write_bytes(payload())
            target.write_text("Earlier trusted summary\n", encoding="utf-8")
            self.assertEqual(receipt.main(["--result", str(source), "--summary", str(target)]), 0)
            view = target.read_text(encoding="utf-8")
            self.assertTrue(view.startswith("Earlier trusted summary\n"))
            self.assertIn("MISSING_PRIMARY_RECOVERY_POLICY_LOCKED", view)
            self.assertNotIn('"reason_code"', view)

    def test_missing_file_reports_unknown_without_hidden_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "summary.md")
            self.assertEqual(receipt.main(["--result", str(Path(folder, 'missing')), "--summary", str(target)]), 0)
            self.assertIn("UNVERIFIED_FAILURE", target.read_text(encoding="utf-8"))


class SchedulerSourceStateDiagnostics(unittest.TestCase):
    """Only an already-RED fallback may ask for two exact GitHub GETs."""

    @staticmethod
    def runtime():
        return {"GITHUB_EVENT_NAME":"schedule",
                "GITHUB_REPOSITORY":"gokaydonmez39-jpg/kripto-radar",
                "GITHUB_REF":"refs/heads/main","GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_TOKEN":"TEST_ONLY_SECRET_NEVER_PRINT"}

    @staticmethod
    def trusted_pages(workflow_state="active",branch="main",
                      workflow_path=".github/workflows/xray-personal-477-eod.yml"):
        return {
            receipt.REPO_META_PATH: {
                "full_name":"gokaydonmez39-jpg/kripto-radar",
                "default_branch":branch,
            },
            receipt.WORKFLOW_META_PATH: {
                "path":workflow_path, "state":workflow_state,
            },
        }

    def test_unobserved_natural_epoch_active_workflow_stays_unresolved(self):
        calls=[]
        pages=self.trusted_pages()
        def fetch(path):
            calls.append(("GET",path))
            return pages[path]
        out=receipt.probe_source_metadata(payload(),self.runtime(),fetch)
        self.assertEqual(out,{"category":"WORKFLOW_ACTIVE_CAUSE_UNRESOLVED",
                              "asof":"2026-11-20"})
        self.assertEqual(calls,[("GET",receipt.REPO_META_PATH),
                                ("GET",receipt.WORKFLOW_META_PATH)])
        summary=receipt.render_source_probe(out)
        self.assertIn("CAUSE_UNRESOLVED",summary)
        self.assertIn("NO_DISPATCH",summary)
        self.assertNotIn("SUCCESSFUL_EOD",summary)

    def test_disabled_workflow_is_separate_from_unknown_scheduler_drop(self):
        for state in ("disabled_manually","disabled_inactivity","disabled_fork"):
            with self.subTest(state=state):
                pages=self.trusted_pages(workflow_state=state)
                out=receipt.probe_source_metadata(
                    payload(),self.runtime(),lambda path:pages[path])
                self.assertEqual(out["category"],"WORKFLOW_DISABLED_OBSERVED")
                self.assertEqual(out["asof"],"2026-11-20")

    def test_default_branch_drift_denied_without_second_api_get(self):
        calls=[]
        pages=self.trusted_pages(branch="other-branch")
        out=receipt.probe_source_metadata(
            payload(),self.runtime(),lambda path:
            calls.append(path) or pages[path])
        self.assertEqual(out["category"],"DEFAULT_BRANCH_NOT_MAIN")
        self.assertEqual(calls,[receipt.REPO_META_PATH])

    def test_wrong_workflow_identity_or_missing_state_stays_unverified(self):
        for pages in (self.trusted_pages(workflow_path=".github/workflows/other.yml"),
                      self.trusted_pages(workflow_state="unexpected"),
                      {receipt.REPO_META_PATH:{"default_branch":"main"}}):
            with self.subTest(pages=pages):
                out=receipt.probe_source_metadata(
                    payload(),self.runtime(),lambda path:pages[path])
                self.assertEqual(out["category"],"GITHUB_METADATA_UNVERIFIED")

    def test_unknown_or_tampered_fallback_never_contacts_metadata_provider(self):
        for raw in (b"{}",payload(reason_code="FORGED"),
                    payload(dispatch_requested=True),
                    payload(status="BLOCKED_GITHUB_API_UNCERTAIN"),
                    payload(asof_et="2026-11-31")):
            with self.subTest(raw=raw):
                calls=[]
                out=receipt.probe_source_metadata(
                    raw,self.runtime(),lambda path:calls.append(path))
                self.assertEqual(out["category"],"SOURCE_EVENT_NOT_ESTABLISHED")
                self.assertEqual(calls,[])

    def test_wrong_runner_identity_does_not_send_get_or_reflection(self):
        for k,v in (("GITHUB_EVENT_NAME","workflow_dispatch"),
                    ("GITHUB_REF","refs/heads/other"),
                    ("GITHUB_RUN_ATTEMPT","2"),
                    ("GITHUB_TOKEN",""),
                    ("GITHUB_REPOSITORY","attacker/repo")):
            with self.subTest(k=k):
                env={**self.runtime(),k:v}
                calls=[]
                out=receipt.probe_source_metadata(
                    payload(),env,lambda path:calls.append(path))
                self.assertEqual(out["category"],"SOURCE_RUNNER_UNVERIFIED")
                self.assertEqual(calls,[])
                self.assertNotIn("TEST_ONLY_SECRET",receipt.render_source_probe(out))

    def test_provider_unavailable_never_claims_disabled_or_echoes_http(self):
        def fail(_path):
            raise RuntimeError("SENSITIVE_GOOGLE_TOKEN_private_location")
        out=receipt.probe_source_metadata(payload(),self.runtime(),fail)
        self.assertEqual(out["category"],"GITHUB_METADATA_UNVERIFIED")
        self.assertNotIn("SENSITIVE_GOOGLE_TOKEN",receipt.render_source_probe(out))

    def test_cli_source_probe_writes_fixed_category_only(self):
        import contextlib,io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder,"incident.json")
            target=Path(folder,"summary.md")
            source.write_bytes(payload())
            target.write_text("Earlier trusted summary\\n",encoding="utf-8")
            pages=self.trusted_pages()
            with patch.dict("os.environ",self.runtime(),clear=True):
                with patch.object(receipt,"github_readonly_metadata",
                                  side_effect=lambda path,token:pages[path]):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        rc=receipt.main(["--result",str(source),
                                         "--summary",str(target),"--probe-source"])
            view=target.read_text(encoding="utf-8")
            self.assertEqual(rc,0)
            self.assertIn("WORKFLOW_ACTIVE_CAUSE_UNRESOLVED",view)
            self.assertIn("NO_DISPATCH",view)
            self.assertTrue(view.startswith("Earlier trusted summary"))
            self.assertNotIn("TEST_ONLY_SECRET",view+output.getvalue())


if __name__ == "__main__":
    unittest.main()
