#!/usr/bin/env python3
"""No signal promotion even when historic terminal source is readable."""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manual_source_drift_forensics as f


def fixture(day="2026-10-15"):
    terminal={"asof_et":"2026-10-07","execution":"NONE","real_money":"NO-GO",
              "compiled_policy_version":"C4.17",
              "evidence":{"master":{
                  "path":"nasdaq-xray/canonical_current_master_manifest.json",
                  "blob_sha":"a"*40}}}
    master={"asof_et":day,"execution":"NONE","real_money":"NO-GO"}
    policy={"parent_policy_version":"C4.17","execution":"NONE",
            "real_money":"NO-GO","alpha_thresholds_unchanged":True,
            "parent_pipeline_unchanged":True,
            "broker_trade_access_allowed":False,"unknown_never_pass":True}
    data=b'{"asof_et":"'+day.encode()+b'","execution":"NONE","real_money":"NO-GO"}'
    return terminal,master,policy,data


class ManualSourceDriftTests(unittest.TestCase):
    def test_oct15_master_oct7_terminal_is_blocked(self):
        a,b,c,d=fixture()
        j=f.audit(a,b,c,d)
        self.assertEqual(j["day_delta_master_minus_terminal"],8)
        self.assertEqual(j["status"],"SOURCE_INTEGRITY_BLOCKED")
        self.assertFalse(j["archival_replay_allowed_by_existing_guard"])
        self.assertFalse(j["alpha_authority"])
        self.assertFalse(j["r92_authority"])
        self.assertFalse(j["repair_autonomously_authorized"])
        self.assertFalse(j["manual_workflow_failure_suppressed"])
        self.assertEqual(j["signal_count"],0)

    def test_seven_day_archival_exception_is_never_live(self):
        a,b,c,d=fixture("2026-10-14")
        j=f.audit(a,b,c,d)
        self.assertTrue(j["archival_replay_allowed_by_existing_guard"])
        self.assertEqual(j["status"],
                         "ARCHIVAL_TERMINAL_SOURCE_ALLOWED_NOT_CURRENT_RELEASE")
        self.assertFalse(j["current_terminal_master_binding_exact"])
        self.assertFalse(j["alpha_authority"])

    def test_exact_master_binding_does_not_certify_other_gates(self):
        a,b,c,d=fixture("2026-10-07")
        a["evidence"]["master"]["blob_sha"]=f.blob(d)
        j=f.audit(a,b,c,d)
        self.assertEqual(j["status"],"EXACT_TERMINAL_MASTER_SOURCE_BINDING_ONLY")
        self.assertTrue(j["source_blob_exact"])
        self.assertFalse(j["alpha_authority"])
        self.assertTrue(j["reporting_cannot_establish_current_c417_release"])

    def test_one_day_ahead_future_and_backward_source_rejected_for_archival(self):
        for day in ("2026-10-06","2026-10-20"):
            with self.subTest(day=day):
                a,b,c,d=fixture(day)
                self.assertEqual(f.audit(a,b,c,d)["status"],
                                 "SOURCE_INTEGRITY_BLOCKED")

    def test_mismatched_bound_path_and_sha_must_fail(self):
        for key,val in (("path","nasdaq-xray/other.json"),
                        ("blob_sha","not40hex")):
            a,b,c,d=fixture()
            a["evidence"]["master"][key]=val
            with self.assertRaisesRegex(ValueError,"TERMINAL_MASTER_BINDING"):
                f.audit(a,b,c,d)

    def test_fail_open_policy_and_real_money_never_accepted(self):
        for where,key,val in (
            ("policy","alpha_thresholds_unchanged",False),
            ("policy","broker_trade_access_allowed",True),
            ("policy","unknown_never_pass",False),
            ("master","real_money","GO"),
            ("terminal","execution","TRADE"),
        ):
            with self.subTest(where=where,key=key):
                a,b,c,d=fixture()
                target={"terminal":a,"master":b,"policy":c}[where]
                target[key]=val
                with self.assertRaisesRegex(ValueError,"SAFETY_POLICY"):
                    f.audit(a,b,c,d)

    def test_output_only_control_proof_no_price_or_orders(self):
        a,b,c,d=fixture()
        j=f.audit(a,b,c,d)
        self.assertNotIn("adjusted_close",str(j))
        self.assertNotIn("market_data_bars",str(j))
        self.assertNotIn("trade_orders",str(j))
        self.assertEqual(j["real_money"],"NO-GO")
        self.assertFalse(j["device_delivery_attested"])


if __name__=="__main__":
    unittest.main()
