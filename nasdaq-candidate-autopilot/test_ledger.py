"""Zero-Issue-write A45 rolling artifact regression and adversarial tests."""
import copy
import hashlib
import json
import unittest
from ledger import Blocked, SCHEMA, receive, reconcile

A42 = {"schema": "XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1",
       "source": "NASDAQ_RESEARCH_ONLY_NO_CRYPTO",
       "automatic_promotion": False, "orders": False,
       "private_sheet_writes": False, "registry_sha256": "a"*64,
       "asof": "2026-11-02"}
RAW = (json.dumps(A42)+"\n").encode()
A43 = {"schema": "XRAY_NASDAQ_A43_EOD_ADMISSION_V1",
       "registry_admission": "PASS_FOR_READONLY_CANDIDATE_INTAKE",
       "production_promotion": False, "asof_et": "2026-11-02",
       "scan_477": True, "sheet_readback": True,
       "lifecycle_readback": True, "panel_readback": True,
       "run_id": 123, "run_sha": "b"*64, "log_sha256": "c"*64}
A44 = {"schema": "XRAY_NASDAQ_A44_SOURCE_EVIDENCE_V1",
       "scope": "NASDAQ_RESEARCH_ONLY_NO_CRYPTO",
       "automatic_promotion": False, "network_enabled": True,
       "registry_sha256": "a"*64,
       "candidate_receipt_sha256": hashlib.sha256(RAW).hexdigest(),
       "asof_et": "2026-11-02",
       "results": [
           {"registry_id":2,"status":"PROVENANCE_RECORDED_TEST_REQUIRED",
            "promotion":"BLOCKED_PENDING_INDEPENDENT_FUNCTIONAL_AND_PIT_TEST",
            "run_upstream_code":False,"broker":False,"license_approved":False,
            "source_head_sha":"d"*40}
       ]}


class A45RollingLedgerTests(unittest.TestCase):
    def fresh(self):
        return receive(A42,A43,A44)

    def test_first_entry_explicitly_not_durable(self):
        out,status=reconcile(None,self.fresh())
        self.assertEqual(status,"NEW_SOURCE_EPOCH_ADMITTED")
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(out["history_continuity"],"UNATTESTED_FIRST_OR_EXPIRED_ARTIFACT")
        self.assertFalse(out["candidate_states"]["2"]["production_integrated"])

    def test_replay_is_idempotent(self):
        out,_=reconcile(None,self.fresh())
        out2,status=reconcile(out,self.fresh())
        self.assertEqual(status,"IDEMPOTENT_REPLAY")
        self.assertEqual(out,out2)
        self.assertEqual(out2["total_accepted_epochs"],1)

    def test_conflicting_eod_same_id_rejected(self):
        out,_=reconcile(None,self.fresh())
        other=copy.deepcopy(self.fresh())
        other["results"][0]["status"]="HOLD_LICENSE_REVIEW"
        with self.assertRaises(Blocked):
            reconcile(out,other)

    def test_rollforward_new_run(self):
        prev,_=reconcile(None,self.fresh())
        another=copy.deepcopy(self.fresh())
        another["run_id"]="124"
        another["asof_et"]="2026-11-03"
        final,status=reconcile(prev,another)
        self.assertEqual(status,"NEW_SOURCE_EPOCH_ADMITTED")
        self.assertEqual(final["total_accepted_epochs"],2)
        self.assertEqual(final["candidate_states"]["2"]["observations"],2)
        self.assertEqual(len(final["episodes"]),2)

    def test_old_asof_rejected(self):
        prev,_=reconcile(None,self.fresh())
        other=copy.deepcopy(self.fresh())
        other["run_id"]="125"
        other["asof_et"]="2026-10-30"
        with self.assertRaises(Blocked):
            reconcile(prev,other)

    def test_bad_ledger_schema_blocks(self):
        with self.assertRaises(Blocked):
            reconcile({"schema":"bad"},self.fresh())

    def test_bad_registry_blocks(self):
        previous,_=reconcile(None,self.fresh())
        previous["registry_sha256"]="e"*64
        with self.assertRaises(Blocked):
            reconcile(previous,self.fresh())

    def test_missing_477_blocks(self):
        a43=dict(A43,scan_477=False)
        with self.assertRaises(Blocked):
            receive(A42,a43,A44)

    def test_missing_sheet_blocks(self):
        with self.assertRaises(Blocked):
            receive(A42,dict(A43,sheet_readback=False),A44)

    def test_missing_panel_blocks(self):
        with self.assertRaises(Blocked):
            receive(A42,dict(A43,panel_readback=False),A44)

    def test_wrong_crypto_scope(self):
        with self.assertRaises(Blocked):
            receive(A42,A43,dict(A44,scope="CRYPTO"))

    def test_private_script_execution_approval_rejected(self):
        bad=copy.deepcopy(A44)
        bad["results"][0]["run_upstream_code"]=True
        with self.assertRaises(Blocked):
            receive(A42,A43,bad)

    def test_automatic_promotion_rejected(self):
        bad=dict(A44,automatic_promotion=True)
        with self.assertRaises(Blocked):
            receive(A42,A43,bad)

    def test_offline_snapshot_not_counted(self):
        with self.assertRaises(Blocked):
            receive(A42,A43,dict(A44,network_enabled=False))

    def test_duplicate_source_id_blocks(self):
        bad=copy.deepcopy(A44)
        bad["results"].append(bad["results"][0])
        with self.assertRaises(Blocked):
            receive(A42,A43,bad)

    def test_candidate_ledger_remembers_good_sha_across_temporary_unavailable(self):
        prev,_=reconcile(None,self.fresh())
        other=copy.deepcopy(self.fresh())
        other["run_id"]="124"
        other["asof_et"]="2026-11-03"
        other["results"][0]["status"]="SOURCE_PROBE_UNKNOWN"
        other["results"][0]["upstream_sha"]=""
        after,_=reconcile(prev,other)
        self.assertEqual(after["candidate_states"]["2"]["last_verified_sha"],"d"*40)
        self.assertEqual(after["candidate_states"]["2"]["latest_status"],"SOURCE_PROBE_UNKNOWN")

if __name__=="__main__":
    unittest.main()
