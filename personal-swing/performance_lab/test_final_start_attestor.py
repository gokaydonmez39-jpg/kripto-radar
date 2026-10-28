"""A20 synthetic safety gates: no network, private rows or live trading."""
from copy import deepcopy
import unittest
import final_start_attestor as gate

def sample():
    names=gate.RUN_NAMES
    events={"eod":"push","a14":"workflow_run","private_readback":"push","resilience":"schedule"}
    runs={k:{"name":names[k],"event":events[k],"id":gate.RUNS[k],
             "status":"completed","conclusion":"success","head_sha":"a"*40,
             "created_at":"2026-10-28T09:58:42Z" if k=="a14" else "2026-10-28T09:57:28Z",
             "run_attempt":2} for k in events}
    jobs={
      "eod":[{"name":n,"conclusion":"success"} for n in
             ("offline-guard","private-sheets-auth-preflight","daily-private-scan")],
      "a14":[{"name":n,"conclusion":"success"} for n in
             ("configuration-readiness","private-research-after-eod")],
      "private_readback":[{"name":"private-one-time-real-source-readback","conclusion":"success"}],
      "resilience":[{"name":"resilience","conclusion":"success"}],
    }
    return {"branch":{"name":"main","protected":True},
            "ruleset":{"enforcement":"active",
                       "rules":[{"type":"deletion"},{"type":"non_fast_forward"}]},
            "runs":runs,"jobs":jobs}


class StartGateTests(unittest.TestCase):
    def test_ready_never_means_profitable(self):
        result=gate.final_gate(sample())
        self.assertEqual(result["research_radar_start"],"START_ARMED")
        self.assertEqual(result["scientific_review_axes"],16)
        self.assertEqual(result["strategy_alpha_release"],
                         "HOLD_UNDERPOWERED_NO_INDEPENDENT_HOLDOUT")
        self.assertFalse(result["orders"])
        self.assertFalse(result["device_receipt_proven"])

    def test_branch_protection_required(self):
        item=sample();item["branch"]["protected"]=False
        self.assertEqual(gate.final_gate(item)["research_radar_start"],"HOLD")

    def test_ruleset_required(self):
        item=sample();item["ruleset"]["rules"].pop()
        self.assertFalse(gate.final_gate(item)["checks"]["no_force_push_or_delete"])

    def test_failed_eod_blocks(self):
        item=sample();item["runs"]["eod"]["conclusion"]="failure"
        self.assertFalse(gate.final_gate(item)["checks"]["eod_workflow_completed"])

    def test_event_must_be_actual_workflow_run(self):
        item=sample();item["runs"]["a14"]["event"]="push"
        self.assertFalse(gate.final_gate(item)["checks"]["a14_triggered_by_eod"])

    def test_mixed_commit_blocks(self):
        item=sample();item["runs"]["a14"]["head_sha"]="f"*40
        self.assertFalse(gate.final_gate(item)["checks"]["a14_triggered_by_eod"])

    def test_reverse_temporal_order_blocks(self):
        item=sample();item["runs"]["a14"]["created_at"]="2026-10-28T09:50:00Z"
        self.assertFalse(gate.final_gate(item)["checks"]["a14_follows_eod_time"])

    def test_missing_private_readback_blocks(self):
        item=sample();item["jobs"]["private_readback"][0]["conclusion"]="skipped"
        self.assertFalse(gate.final_gate(item)["checks"]["private_real_source_readback"])

    def test_failed_resilience_blocks(self):
        item=sample();item["jobs"]["resilience"][0]["conclusion"]="failure"
        self.assertFalse(gate.final_gate(item)["checks"]["resilience_persist_recovered"])

    def test_unproven_rerun_blocks(self):
        item=sample();item["runs"]["resilience"]["run_attempt"]=1
        self.assertFalse(gate.final_gate(item)["checks"]["resilience_persist_recovered"])

    def test_failed_a14_job_blocks(self):
        item=sample();item["jobs"]["a14"][1]["conclusion"]="failure"
        self.assertFalse(gate.final_gate(item)["checks"]["a14_research_chain_completed"])

    def test_missing_run_evidence_blocks(self):
        item=sample();item["runs"].pop("eod")
        with self.assertRaises(gate.FinalGateError):
            gate.final_gate(item)

if __name__=="__main__":
    unittest.main()
