#!/usr/bin/env python3
"""Synthetic readiness fixtures: review is not model release."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research_learning_readiness as r

def calibration(n=0):
    rows=[{
      "asof_et":(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat(),
      "comparable_to_current_c417":True,
      "full_end_to_end_research_pass":True,
      "compiled_policy_version":"C4.17"}
      for i in range(n)]
    return {
      "schema":"XRAY_ALPHA_CALIBRATION_AUDIT_V1",
      "current_policy_version":"C4.17",
      "execution":"NONE","real_money":"NO-GO",
      "alpha_authority":False,"no_threshold_change":True,
      "observed_terminal_snapshots":rows,
      "observed_snapshot_count":n,
      "target_comparable_sessions":60,
      "comparable_current_policy_session_count":n,
      "calibration_pass":n>=60}

def report(i=0,complete=True):
    return {
      "schema":"XRAY_RESEARCH_FORWARD_OUTCOME_DIAGNOSTICS_V1",
      "asof_et":"2026-10-15","symbol":"TEST"+str(i),
      "accepted_receipt_sha256":str(i).zfill(64),
      "source_market_data_sha256":"a"*64,
      "execution":"NONE","real_money":"NO-GO",
      "primary_alpha_authority":False,"backtest_proven":False,
      "model_calibrated":False,"raw_prices_persisted":False,
      "sample_comparability_externally_attested":False,
      "horizons":{str(k):{
          "status":("COMPLETED_RESEARCH_FORWARD_CLOSE_MOVE_NOT_TRADE"
                    if complete else
                    "UNKNOWN_MISSING_COMPLETE_COMPARABLE_SESSION"),
          "forward_return_pct":0.0 if complete else None,
          "benchmark_return_pct":0.0 if complete else None,
          "excess_return_pct_points":0.0 if complete else None,
      } for k in (1,3,5,10,20)}
    }


class ReadinessTests(unittest.TestCase):
    def test_live_zero_sample_is_blocked(self):
        o=r.check(calibration(),[])
        self.assertEqual(o["status"],"INSUFFICIENT_COMPARABLE_LEARNING_EVIDENCE")
        self.assertEqual(o["comparable_current_policy_sessions"],0)
        self.assertFalse(o["shadow_dataset_review_candidate"])
        self.assertFalse(o["model_calibrated"])
        self.assertFalse(o["alpha_authority"])
        self.assertIsNone(o["brier_score"])

    def test_review_gate_reachable_but_never_release(self):
        good=r.check(calibration(60),[report(i) for i in range(100)])
        self.assertTrue(good["shadow_dataset_review_candidate"])
        self.assertEqual(good["status"],"DATASET_REVIEW_CANDIDATE_NOT_MODEL_AUTHORIZED")
        self.assertFalse(good["model_trained"])
        self.assertFalse(good["r92_authority"])
        self.assertFalse(good["iphone_delivery_receipt_attested"])
        self.assertIn("INDEPENDENT_EPISODE_TIME_AND_SOURCE_ATTESTATION_NOT_PROVEN",
                      good["blockers"])

    def test_borderlines_and_censoring(self):
        self.assertFalse(r.check(calibration(59),[report(i) for i in range(100)])[
            "shadow_dataset_review_candidate"])
        self.assertFalse(r.check(calibration(60),[report(i) for i in range(99)])[
            "shadow_dataset_review_candidate"])
        self.assertFalse(r.check(calibration(60),[report(i,False) for i in range(100)])[
            "shadow_dataset_review_candidate"])

    def test_forged_calibration_source_rejected(self):
        for field,value in (
            ("calibration_pass",True),
            ("comparable_current_policy_session_count",60),
            ("observed_snapshot_count",1),
            ("alpha_authority",True),
            ("current_policy_version","C4.14"),
            ("execution","LIVE"),
        ):
            with self.subTest(field=field):
                obj=calibration()
                obj[field]=value
                with self.assertRaises(ValueError):
                    r.check(obj,[])

    def test_duplicate_epoch_and_false_complete_session(self):
        x=calibration(60)
        x["observed_terminal_snapshots"][1]["asof_et"]=x["observed_terminal_snapshots"][0]["asof_et"]
        with self.assertRaises(ValueError):
            r.check(x,[])
        x=calibration(60)
        x["observed_terminal_snapshots"][1]["full_end_to_end_research_pass"]=False
        with self.assertRaises(ValueError):
            r.check(x,[])

    def test_forged_reports_and_duplicates_rejected(self):
        s=calibration()
        for mutate in (
            lambda x: x.update(alpha_authority=True),
            lambda x: x.update(model_calibrated=True),
            lambda x: x.update(raw_prices_persisted=True),
            lambda x: x["horizons"].pop("20"),
            lambda x: x["horizons"]["10"].update(status="AL"),
        ):
            x=report(1)
            mutate(x)
            with self.assertRaises(ValueError):
                r.check(s,[x])
        x=report(1)
        with self.assertRaises(ValueError):
            r.check(s,[x,copy.deepcopy(x)])


if __name__=="__main__":
    unittest.main()
