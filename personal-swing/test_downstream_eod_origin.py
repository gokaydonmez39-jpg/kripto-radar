"""Offline workflow admission contracts: genuine current EOD only, no push/PR no-op."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
KRONOS = "xray-personal-kronos-shadow.yml"
A34 = "xray-nasdaq-a34-preopen.yml"
COVE = "xray-personal-cove-shadow.yml"

ORIGINS = (
    "(github.event.workflow_run.event == 'schedule' || "
    "github.event.workflow_run.event == 'workflow_dispatch')"
)

def job_condition(file, job):
    data = yaml.safe_load((ROOT / file).read_text(encoding="utf-8"))
    return " ".join(data["jobs"][job]["if"].split())

class DownstreamOriginTests(unittest.TestCase):
    def assert_origin_contract(self, file, job):
        condition = job_condition(file,job)
        self.assertIn(ORIGINS,condition)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",condition)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",condition)
        self.assertNotIn("github.event.workflow_run.event != 'pull_request'",condition)
        self.assertIn("github.repository",condition)

    def test_kronos_v1_oos_never_runs_for_noop_push(self):
        self.assert_origin_contract(KRONOS,"independent-private-inference")

    def test_kronos_v2_never_runs_for_noop_push(self):
        self.assert_origin_contract(KRONOS,"kronos-v2-full-477-research")

    def test_a34_private_workflow_run_never_uses_noop_push(self):
        self.assert_origin_contract(A34,"private-preopen")

    def test_a34_skips_test_only_upstream_workflow_run(self):
        self.assertEqual(job_condition(A34,"offline-guard"),
                         "github.event_name != 'workflow_run' || " + ORIGINS)

    def test_cove_accepts_verified_same_epoch_dispatch_fallback(self):
        self.assert_origin_contract(COVE,"private-eod-research")

    def test_a34_retains_independent_direct_preopen(self):
        condition=job_condition(A34,"private-preopen")
        self.assertIn("github.event_name != 'workflow_run' ||",condition)
        self.assertIn("github.ref == 'refs/heads/main'",condition)
        self.assertIn("github.event_name != 'push'",condition)
        self.assertIn("github.event_name != 'pull_request'",condition)

    def test_no_new_cron_in_research_sidecars(self):
        for name in (KRONOS,COVE):
            data=yaml.safe_load((ROOT/name).read_text(encoding="utf-8"))
            trigger=data.get("on",data.get(True,{}))
            self.assertNotIn("schedule",trigger)

if __name__ == "__main__":
    unittest.main()
