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
        self.assertTrue(d["jobs"]["coverage"].get("if") in (None,"true"))

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
