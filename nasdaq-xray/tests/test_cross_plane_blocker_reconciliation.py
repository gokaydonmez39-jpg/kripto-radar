#!/usr/bin/env python3
"""Synthetic cross-plane non-equivalence, provenance and replay negatives."""
import copy
from collections import Counter
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cross_plane_blocker_reconciliation as p

NOW=dt.datetime(2026,10,16,17,tzinfo=dt.timezone.utc)
NAMES=["AAAA","BBBB","CCCC","DDDD"]
SHA=hashlib.sha256("\n".join(NAMES).encode()).hexdigest()


def fixture():
    root={"schema":"XRAY_ORCHESTRATOR_V1","asof_et":"2026-10-15",
          "execution":"NONE","real_money":"NO-GO","queue_total":4,
          "queue_hash":SHA,"unknown_reason_partition_exact":True,
          "unknown_count":2,"status":"PARTIAL_HISTORY","g9_status":"BLOCKED",
          "history_unknown_reason_counts":{
              "EXACT30_SESSIONS_INCOMPLETE":1,
              "PROVIDER_EXCEPTION_RETRY_EXHAUSTED":1}}
    state={"AAAA":"UNKNOWN","BBBB":"FAIL_PRICE",
           "CCCC":"UNKNOWN","DDDD":"FAIL_DV30"}
    price={"schema":"XRAY_CANONICAL_PRICE_DV30_V1",
           "asof_et":"2026-10-15","execution":"NONE",
           "real_money":"NO-GO","unknown_never_pass":True,
           "results":{k:{"status":state[k]} for k in NAMES},
           "source_master_count":4,"source_master_queue_hash":SHA,
           "counts":dict(sorted(Counter(state.values()).items())),
           "unknown_count":2,"unknown_symbols":["AAAA","CCCC"],
           "pass_count":0,"pass_symbols":[]}
    routes={
        "AAAA":{"first_unresolved_gate":"SOURCE",
                "causal_class":"LATEST_ASOF_BAR_UNPROVEN",
                "next_safe_evidence_action":"RETRY_DELAYED_SIP_DAILY_ON_OFFICIAL_SESSION",
                "parallel_research_only":"NONE"},
        "BBBB":{"first_unresolved_gate":"HISTORY",
                "causal_class":"ZERO_OR_NEGATIVE_RECORDED_VOLUME",
                "next_safe_evidence_action":"RECHECK_EXACT_ZERO_VOLUME_HISTORICAL_SESSIONS",
                "parallel_research_only":"DAILY30_SHADOW_CAN_BE_RESEARCHED_INDEPENDENTLY"},
        "CCCC":{"first_unresolved_gate":"PRICE_DV30",
                "causal_class":"RTH_30MIN_LOWER_BOUND_ONLY",
                "next_safe_evidence_action":"PROVE_OFFICIAL_RTH_AUCTION_CORRECTIONS_SPLITS_AND_RIGHTS",
                "parallel_research_only":"VERIFY_SEC_ISSUER_CLASS_MC_2B_INDEPENDENTLY"},
        "DDDD":{"first_unresolved_gate":"PRICE_DV30",
                "causal_class":"SHADOW_DAILY_30_OBSERVED_CURRENT_PRICE_LT5_NOT_RTH",
                "next_safe_evidence_action":"RECHECK_CURRENT_COMPLETED_RTH_PRICE_GE5",
                "parallel_research_only":"NONE"},
    }
    six={"schema":"XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1",
         "asof_et":"2026-10-15","execution":"NONE","real_money":"NO-GO",
         "scope_count":4,"exact_root_identity_scope_sha256":SHA,
         "first_unresolved_gate_counts":
             dict(sorted(Counter(x["first_unresolved_gate"]
                                 for x in routes.values()).items())),
         "next_safe_evidence_action_counts":
             dict(sorted(Counter(x["next_safe_evidence_action"]
                                 for x in routes.values()).items())),
         "input_report_sha256":{k:char*64 for k,char in
             [("bridge","a"),("daily","b"),("history","c"),("rth","d")]},
         "six_gate_dependency_order":
             ["SOURCE","HISTORY","PRICE_DV30","MC","TECH","R92_DELIVERY"],
         "research_only_causal_next_action":True,
         "c417_price_dv30_primary_attested":False,
         "issuer_class_mc_current_attested":False,
         "technical_a_b_d_r1_event_regime_attested":False,
         "registered_r92_count":0,"iphone_device_delivery_attested":False,
         "no_vendor_ohlcv_persisted":True,"no_canonical_mutations":True,
         "source_rights_not_inferred":True,
         "history260_52_observed":2,"source_day_observed":3,
         "joint260_daily30_research_scope":1,
         "per_symbol_causal_routing":routes}
    return root,price,six


class CrossPlaneTests(unittest.TestCase):
    def check(self,root=None,price=None,six=None,now=NOW):
        a,b,c=fixture()
        return p.reconcile(a if root is None else root,
                           b if price is None else price,
                           c if six is None else six,now_utc=now)

    def test_distinct_counts_and_exact_cross_tabs(self):
        x=self.check()
        self.assertEqual(x["universe_count"],4)
        self.assertEqual(x["canonical_root_history_unknown_count"],2)
        self.assertEqual(x["independent_research_history_260_52_unproven_count"],2)
        self.assertEqual(x["canonical_price_dv30_unknown_count"],2)
        self.assertEqual(x["personal_sip_first_unresolved_gate_counts"],
                         {"HISTORY":1,"PRICE_DV30":2,"SOURCE":1})
        self.assertEqual(x["canonical_price_unknown_by_personal_first_gate"],
                         {"SOURCE":1,"HISTORY":0,"PRICE_DV30":1})
        self.assertEqual(list(x["canonical_unknown_symbolic_repair_worklist"]),
                         ["AAAA","CCCC"])
        self.assertFalse(x["canonical_price_primary_evidence_independently_verified_here"])
        self.assertFalse(x["alpha_authority"])
        self.assertFalse(x["r92_authority"])
        self.assertFalse(x["iphone_delivery_attested"])
        self.assertNotIn("adjusted_close",str(x))
        for row in x["canonical_unknown_symbolic_repair_worklist"].values():
            self.assertEqual(
                set(row),
                {"canonical_price_state","research_first_unresolved_gate",
                 "research_causal_class","safe_next_evidence_action",
                 "alpha_authority"})
            self.assertFalse(row["alpha_authority"])
        self.assertTrue(x["no_raw_market_prices_or_volume_in_output"])
        self.assertIn("2 root historical unresolved",x["count_semantics"])
        self.assertIn("2 independent 260/52",x["count_semantics"])
        self.assertIn("2 canonical price UNKNOWN",x["count_semantics"])
        self.assertNotIn("223 root historical",x["count_semantics"])
        self.assertNotIn("548 canonical price",x["count_semantics"])

    def test_official_session_drift_or_naive_clock_refused(self):
        root,price,six=fixture()
        six["asof_et"]="2026-10-14"
        with self.assertRaisesRegex(ValueError,"CURRENT_OFFICIAL_SAME_ASOF"):
            self.check(six=six)
        with self.assertRaisesRegex(ValueError,"UTC_CLOCK_REQUIRED"):
            self.check(now=dt.datetime(2026,10,16,17))

    def test_symbol_scope_and_issuer_universe_sha_rejected(self):
        root,price,six=fixture()
        six["exact_root_identity_scope_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"EXACT_UNIVERSE_SHA"):
            self.check(six=six)
        root,price,six=fixture()
        del price["results"]["BBBB"]
        with self.assertRaisesRegex(ValueError,"SYMBOL_SCOPE_COUNT"):
            self.check(price=price)

    def test_repaired_price_unknown_without_partition_replay_refused(self):
        root,price,six=fixture()
        price["results"]["AAAA"]["status"]="PASS"
        with self.assertRaisesRegex(ValueError,"CANONICAL_PRICE_PARTITION_DRIFT"):
            self.check(price=price)
        root,price,six=fixture()
        price["unknown_symbols"]=["AAAA","AAAA"]
        with self.assertRaisesRegex(ValueError,"CANONICAL_PRICE_PARTITION_DRIFT"):
            self.check(price=price)

    def test_root_unknown_count_proven_not_summed_into_personal(self):
        root,price,six=fixture()
        root["unknown_count"]=223
        with self.assertRaisesRegex(ValueError,"ROOT_HISTORY_UNKNOWN_REASON_PARTITION"):
            self.check(root=root)
        root,price,six=fixture()
        root["unknown_reason_partition_exact"]=False
        with self.assertRaisesRegex(ValueError,"ROOT_HISTORY_UNKNOWN_REASON_PARTITION"):
            self.check(root=root)

    def test_personal_gate_and_action_partitions_cannot_be_forged(self):
        root,price,six=fixture()
        six["first_unresolved_gate_counts"]["PRICE_DV30"]=3
        with self.assertRaisesRegex(ValueError,"SIX_GATE_PARTITION_REPLAY_DRIFT"):
            self.check(six=six)
        root,price,six=fixture()
        six["next_safe_evidence_action_counts"].clear()
        with self.assertRaisesRegex(ValueError,"SIX_GATE_PARTITION_REPLAY_DRIFT"):
            self.check(six=six)

    def test_false_primary_rights_delivery_and_r92_never_promote(self):
        for key,bad in (
            ("c417_price_dv30_primary_attested",True),
            ("issuer_class_mc_current_attested",True),
            ("technical_a_b_d_r1_event_regime_attested",True),
            ("registered_r92_count",1),
            ("iphone_device_delivery_attested",True),
            ("no_vendor_ohlcv_persisted",False),
            ("source_rights_not_inferred",False),
        ):
            with self.subTest(key=key):
                root,price,six=fixture()
                six[key]=bad
                with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_GATE_OR_SOURCE_PROMOTION"):
                    self.check(six=six)

    def test_untrusted_four_input_digests_blocked(self):
        root,price,six=fixture()
        six["input_report_sha256"]["rth"]="thisisnotasha"
        with self.assertRaisesRegex(ValueError,"FOUR_SOURCE_REPORT_DIGESTS"):
            self.check(six=six)

    def test_unknown_new_gate_must_fail_closed(self):
        root,price,six=fixture()
        six["per_symbol_causal_routing"]["CCCC"]["first_unresolved_gate"]="MC"
        with self.assertRaisesRegex(ValueError,"UNKNOWN_SYMBOL_GATE_OR_PRICE_CLASS"):
            self.check(six=six)


if __name__=="__main__":
    unittest.main()
