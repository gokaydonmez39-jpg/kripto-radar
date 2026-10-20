"""Offline fail-closed provider scheduling: no duplicate paid/free SIP scans.

A full-universe provider request runs only on its daily scheduled slot or an
explicit human dispatch. PRs and code pushes run offline tests, never make
another automatic 542-symbol request. Does not claim any market-data rights.
"""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[2]
WORKFLOWS=ROOT/".github"/"workflows"

def read(filename):
    data=yaml.load((WORKFLOWS/filename).read_text(),Loader=yaml.BaseLoader)
    assert data.get("permissions",{}).get("contents")=="read"
    return data

class QuotaDedupContract(unittest.TestCase):
    def test_root_backup_does_not_refetch_on_every_hourly_root_success(self):
        d=read("xray-personal-full-universe-sip-coverage.yml")
        event=d["on"]
        self.assertNotIn("workflow_run",event)
        self.assertNotIn("push",event)
        self.assertNotIn("pull_request",event)
        self.assertIn("schedule",event)
        self.assertIn("workflow_dispatch",event)
        self.assertEqual(event["schedule"][0]["cron"],"10 22 * * 1-5")
        self.assertEqual(d["concurrency"]["cancel-in-progress"],"false")
        self.assertEqual(d["jobs"]["coverage"].get("if"),
            "${{ needs.session-gate.outputs.allow == 'true' }}")

    def test_candidate_scan_only_nightly_or_directly_requested(self):
        d=read("xray-candidate-local-alpaca-sip-recovery.yml")
        event=d["on"]
        self.assertNotIn("push",event)
        self.assertNotIn("pull_request",event)
        self.assertNotIn("workflow_run",event)
        self.assertEqual(event["schedule"][0]["cron"],"10 23 * * 1-5")
        self.assertIn("workflow_dispatch",event)
        self.assertEqual(d["concurrency"]["cancel-in-progress"],"false")
        source=d["jobs"]["source-recovery"]
        price=d["jobs"]["personal-price-current-exact30"]
        self.assertIn("alpaca_candidate_local_260_recovery_shadow.py",str(source))
        self.assertIn("alpaca_personal_price_current_exact30.py",str(price))
        self.assertIn("personal-eod-verified-snapshot",d["jobs"])

    def test_scheduled_vendor_io_requires_official_nasdaq_session(self):
        # RED pre-fix: cron fires on US weekdays that are Nasdaq holidays.
        # Existing root_weekend_quota_guard is authoritative and fails closed.
        for filename, vendor_jobs in (
            ("xray-personal-full-universe-sip-coverage.yml", ("coverage",)),
            ("xray-candidate-local-alpaca-sip-recovery.yml",
             ("source-recovery", "personal-price-current-exact30")),
        ):
            with self.subTest(workflow=filename):
                d=read(filename)
                gate=d["jobs"].get("session-gate")
                self.assertIsNotNone(gate, "SCHEDULED_PROVIDER_SESSION_GATE_MISSING")
                expected_allow=("${{ steps.session.outputs.allow_compute == 'true' && "
                                "steps.source.outputs.ready == 'true' }}"
                                if filename=="xray-personal-full-universe-sip-coverage.yml"
                                else "${{ steps.session.outputs.allow_compute }}")
                self.assertEqual(gate["outputs"]["allow"],expected_allow)
                if filename=="xray-personal-full-universe-sip-coverage.yml":
                    source_steps=[step for step in gate["steps"]
                                  if step.get("id")=="source"]
                    self.assertEqual(len(source_steps),1)
                    self.assertIn("personal_sip_head_preflight.py --selftest",
                                  source_steps[0].get("run",""))
                    self.assertIn("personal_sip_head_preflight.py --emit",
                                  source_steps[0].get("run",""))
                guard_steps=[s for s in gate["steps"] if
                    s.get("id")=="session"]
                self.assertEqual(len(guard_steps),1)
                self.assertIn("root_weekend_quota_guard.py --emit",
                    guard_steps[0].get("run",""))
                self.assertTrue(any(
                    "pandas_market_calendars==5.4.0" in s.get("run","")
                    for s in gate["steps"]))
                for name in vendor_jobs:
                    job=d["jobs"][name]
                    expected_needs = (["session-gate","source-recovery"]
                        if name=="personal-price-current-exact30"
                        else ["session-gate"])
                    self.assertEqual(job.get("needs"),expected_needs,
                        "UNGUARDED_SCHEDULED_PROVIDER_JOB:"+name)
                    expected_if = "${{ needs.session-gate.outputs.allow == 'true' }}"
                    if name=="personal-price-current-exact30":
                        expected_if = ("${{ needs.session-gate.outputs.allow == 'true' "
                                       "&& needs.source-recovery.result == 'success' }}")
                    self.assertEqual(job.get("if"), expected_if)

    def test_standalone_price_vendor_traffic_manual_only(self):
        d=read("xray-personal-current-sip-price-unknown-shadow.yml")
        self.assertIn("pull_request",d["on"])
        self.assertIn("push",d["on"])
        self.assertIn("workflow_dispatch",d["on"])
        steps=d["jobs"]["research-only"]["steps"]
        scan=next(x for x in steps if
                 x.get("name","").startswith("Current main only"))
        self.assertEqual(scan["if"],
            "${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}")
        uploads=[x for x in steps if
                 x.get("name","").startswith("Archive sanitized counts")]
        self.assertEqual(len(uploads),1)
        self.assertEqual(uploads[0]["if"],
            "${{ always() && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}")
        self.assertEqual(d["concurrency"]["cancel-in-progress"],"false")

if __name__=="__main__":
    unittest.main()
