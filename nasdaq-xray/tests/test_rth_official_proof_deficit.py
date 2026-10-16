#!/usr/bin/env python3
"""Adversarial tests against independently authenticated real same-run symbols.

Tests require env pointing at GitHub-downloaded **symbolic** evidence. No
vendor data is loaded. Positive cohort proves consistency, NEVER market PASS.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rth_official_proof_deficit as mod

UTC=dt.timezone.utc


class AuthenticSymbolicEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths=[os.environ.get(k) for k in (
            "XRAY_TEST_CROSS","XRAY_TEST_SIX","XRAY_TEST_JOINT")]
        if not all(paths) or not all(Path(x).is_file() for x in paths):
            raise RuntimeError("XRAY_AUTHENTICATED_TEST_FIXTURES_MISSING")
        cls.c=json.loads(Path(paths[0]).read_bytes())
        cls.s=json.loads(Path(paths[1]).read_bytes())
        cls.raw=Path(paths[2]).read_bytes()
        cls.j=json.loads(cls.raw)
        cls.now=dt.datetime(2026,10,16,18,tzinfo=UTC)

    def run_case(self,c=None,s=None,j=None,raw=None,now=None,run_id=38940917676):
        return mod.reconcile(
            self.c if c is None else c,
            self.s if s is None else s,
            self.j if j is None else j,
            self.raw if raw is None else raw,
            now_utc=self.now if now is None else now,
            upstream_run_id=run_id)

    def test_real_497_partition_does_not_pretend_primary_pass(self):
        result=self.run_case()
        self.assertEqual(result["rth_exact_30session_research_cohort"],497)
        self.assertEqual(result["rth_complete_slot_research_high_count"],415)
        self.assertEqual(result["rth_auction_volume_ambiguous_count"],78)
        self.assertEqual(result["rth_incomplete_slot_count"],4)
        self.assertEqual(result["outside_complete_rth_cohort_unknown_count"],51)
        self.assertEqual(len(result["rth_proof_denied_per_symbol"]),497)
        self.assertEqual(len(result["outside_rth_safe_actions"]),51)
        self.assertEqual(result["canonical_price_dv30_unknown_count"],548)
        self.assertEqual(result["partial_high_bar_low_is_not_true_price_floor_count"],1)
        self.assertFalse(result["primary_c417_price_dv30_proven"])
        self.assertFalse(result["alpha_authority"])
        self.assertFalse(result["iphone_delivery_receipt_attested"])
        self.assertEqual(result["source_market_api_calls"],0)

    def test_all_symbol_rows_strictly_nonpromotable(self):
        result=self.run_case()
        for row in result["rth_proof_denied_per_symbol"].values():
            self.assertEqual(set(row),{
                "rth_source_class","safe_next_evidence_action",
                "partial_slot_proxy","official_auction_and_corrections_proven",
                "official_trade_condition_eligible_volume_proven",
                "same_issuer_corporate_action_and_legal_rights_proven",
                "eligible_for_c417_price_pass","alpha_authority"})
            for key in ("official_auction_and_corrections_proven",
                        "official_trade_condition_eligible_volume_proven",
                        "same_issuer_corporate_action_and_legal_rights_proven",
                        "eligible_for_c417_price_pass","alpha_authority"):
                self.assertFalse(row[key])

    def test_same_run_bytes_sha_tampering_rejected(self):
        raw=self.raw+b" "
        with self.assertRaisesRegex(ValueError,"EXACT_SAME_RUN_RTH_SOURCE_BYTES_SHA"):
            self.run_case(raw=raw)
        s=copy.deepcopy(self.s)
        s["input_report_sha256"]["rth"]="f"*64
        with self.assertRaisesRegex(ValueError,"EXACT_SAME_RUN_RTH_SOURCE_BYTES_SHA"):
            self.run_case(s=s)

    def test_false_official_market_rights_never_accepted(self):
        for key,bad in (
            ("official_c417_primary_dv30_attested",True),
            ("official_RTH_close_auction_volume_attested",True),
            ("official_RTH_corrections_attested",True),
            ("same_issuer_corporate_action_adjustment_attested",True),
            ("source_rights_not_inferred",False),
            ("vendor_ohlcv_persisted",True),
            ("registered_R92_count",1),
        ):
            with self.subTest(key=key):
                j=copy.deepcopy(self.j)
                j[key]=bad
                bb=json.dumps(j,sort_keys=True).encode()
                s=copy.deepcopy(self.s)
                s["input_report_sha256"]["rth"]=__import__("hashlib").sha256(bb).hexdigest()
                c=copy.deepcopy(self.c)
                c["six_gate_input_report_sha256"]=copy.deepcopy(s["input_report_sha256"])
                with self.assertRaisesRegex(ValueError,"RTH_NO_PRIMARY_EVIDENCE"):
                    self.run_case(c=c,s=s,j=j,raw=bb)

    def test_rth_action_mismatch_never_silently_maps_high(self):
        c=copy.deepcopy(self.c)
        symbol=next(iter(self.j["classifications"]))
        c["canonical_unknown_symbolic_repair_worklist"][symbol]["safe_next_evidence_action"]="ASSUME_PASS"
        with self.assertRaisesRegex(ValueError,"CANONICAL_UNKNOWN_VS_RTH_ACTION_DRIFT"):
            self.run_case(c=c)

    def test_no_missing_or_foreign_cohort_member(self):
        j=copy.deepcopy(self.j)
        j["classifications"].pop(next(iter(j["classifications"])))
        bb=json.dumps(j,sort_keys=True).encode()
        s=copy.deepcopy(self.s)
        s["input_report_sha256"]["rth"]=__import__("hashlib").sha256(bb).hexdigest()
        c=copy.deepcopy(self.c)
        c["six_gate_input_report_sha256"]=copy.deepcopy(s["input_report_sha256"])
        with self.assertRaises(ValueError):
            self.run_case(c=c,s=s,j=j,raw=bb)

    def test_partial_bar_low_is_not_trade_price_floor(self):
        j=copy.deepcopy(self.j)
        j["partial_notional_proxy_not_mathematical_trade_floor"]=False
        bb=json.dumps(j,sort_keys=True).encode()
        s=copy.deepcopy(self.s)
        s["input_report_sha256"]["rth"]=__import__("hashlib").sha256(bb).hexdigest()
        c=copy.deepcopy(self.c)
        c["six_gate_input_report_sha256"]=copy.deepcopy(s["input_report_sha256"])
        with self.assertRaisesRegex(ValueError,"PARTIAL_BARLOW_NOT_A_TRADE_PRICE_FLOOR"):
            self.run_case(c=c,s=s,j=j,raw=bb)

    def test_wrong_epoch_forged_run_and_naive_clock(self):
        c=copy.deepcopy(self.c)
        c["asof_et"]="2026-10-14"
        with self.assertRaisesRegex(ValueError,"LATEST_OFFICIAL_SAME_ASOF"):
            self.run_case(c=c)
        with self.assertRaisesRegex(ValueError,"EXTERNALLY_AUTHENTICATED_RUN_ID_REQUIRED"):
            self.run_case(run_id=0)
        with self.assertRaisesRegex(ValueError,"UTC_REQUIRED"):
            self.run_case(now=dt.datetime(2026,10,16,18))

    def test_issuer_and_vendor_market_claim_forgery_blocked(self):
        c=copy.deepcopy(self.c)
        c["canonical_price_primary_evidence_independently_verified_here"]=True
        with self.assertRaisesRegex(ValueError,"CROSS_PLANE_AUTHORITY_AND_SCOPE"):
            self.run_case(c=c)
        s=copy.deepcopy(self.s)
        s["c417_price_dv30_primary_attested"]=True
        with self.assertRaisesRegex(ValueError,"SIX_GATE_RESEARCH_ONLY"):
            self.run_case(s=s)


if __name__=="__main__":
    unittest.main()
