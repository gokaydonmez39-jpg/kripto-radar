"""Fail-closed two independent EOD source gates; offline synthetic proof tests."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rallies_source_double_gate import inspect

M={
    "schema":"XRAY_CANONICAL_MASTER_MANIFEST_VX","asof_et":"2026-10-16",
    "pass_symbols":["AAPL","TSLA"],"pass_count":2,
    "unknown_symbols":["FOO"],"unknown_count":1,
    "pass_hash":"test-exact-source-queue-sha","execution":"NONE","real_money":"NO-GO",
    "unknown_never_pass":True
}
P={
    "schema":"XRAY_CANONICAL_PRICE_DV30_V1","asof_et":"2026-10-16",
    "source_master_queue_hash":"test-exact-source-queue-sha","source_master_count":2,
    "pass_count":0,"pass_symbols":[],"unknown_count":2,"unknown_symbols":["AAPL","TSLA"],
    "blocked_count":0,"blocked_symbols":[],
    "results":{s:{"status":"UNKNOWN","info":{"reason":"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"}} for s in ["AAPL","TSLA"]},
    "c417_rallies_primary_materialized_count":0,
    "c417_rallies_primary_meta":{"status":"UNKNOWN","reason":"FileNotFoundError"},
    "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
}
G={"schema":"XRAY_PROVIDER_AUTOMATION_GOVERNANCE_V1",
"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,"no_paid_fallback":True,
"providers":{"RALLIES":{
"positive_price_dv30_promotion_allowed":False,
"passive_reader_positive_promotion_allowed":False,
"automated_non_display_runner_entitlement":"NOT_ATTESTED",
"unadjusted_official_rth_integer_volume_lineage":"NOT_ATTESTED",
"paid_top_up_allowed":False}}}
T={"asof_et":"2026-10-07","full_end_to_end_research_pass":False,
"r92_candidates":[],"execution":"NONE","real_money":"NO-GO"}

def d(x): return copy.deepcopy(x)

class TestDoubleGate(unittest.TestCase):
    def case(self,master=None,price=None,governance=None,terminal=None,primary=None):
        return inspect(master or d(M),price or d(P),governance or d(G),terminal or d(T),primary)

    def test_missing_and_no_license_are_independent_blocks(self):
        x=self.case()
        self.assertEqual(x["status"],"BLOCKED_SOURCE_EVIDENCE_OR_RIGHTS")
        self.assertIn("MISSING_SAME_ASOF_RALLIES_CLASSIFICATION",x["blockers"])
        self.assertIn("RALLIES_AUTOMATED_NONDISPLAY_ENTITLEMENT_UNATTESTED",x["blockers"])
        self.assertIn("RALLIES_RTH_INTEGER_VOLUME_NOT_ATTESTED",x["blockers"])
        self.assertEqual(x["unknown_reason_counts"],{"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED":2})
        self.assertFalse(x["may_promote_r92"])
        self.assertFalse(x["may_notify_user"])
        self.assertEqual(x["execution"],"NONE")

    def test_license_toggled_still_missing_source(self):
        g=d(G)
        p=g["providers"]["RALLIES"]
        p["positive_price_dv30_promotion_allowed"]=True
        p["passive_reader_positive_promotion_allowed"]=True
        p["automated_non_display_runner_entitlement"]="ATTESTED"
        p["unadjusted_official_rth_integer_volume_lineage"]="ATTESTED"
        x=self.case(governance=g)
        self.assertTrue(x["governance_state"]["rallies_license_and_volume_claimed"])
        self.assertIn("MISSING_SAME_ASOF_RALLIES_CLASSIFICATION",x["blockers"])
        self.assertFalse(x["may_promote_r92"])

    def test_fake_source_is_not_accepted(self):
        x=self.case(primary=b"{bad json")
        self.assertIn("INVALID_RALLIES_CLASSIFICATION_BYTES",x["blockers"])
        self.assertFalse(x["may_promote_r92"])

    def test_valid_synthetic_file_still_not_a_proven_price(self):
        raw=json.dumps({"schema":"XRAY_RALLIES_DV30_CLASSIFICATION_V1",
           "asof_et":"2026-10-16","execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True,"authority":"C4.17_RALLIES_EXACT30_PRIMARY"}).encode()
        x=self.case(primary=raw)
        self.assertNotIn("MISSING_SAME_ASOF_RALLIES_CLASSIFICATION",x["blockers"])
        self.assertFalse(x["governance_state"]["rallies_license_and_volume_claimed"])
        self.assertFalse(x["source_state"]["is_full_rallies_authority_attested"])
        self.assertFalse(x["may_promote_r92"])

    def test_cross_asof_primary_is_rejected(self):
        raw=json.dumps({"asof_et":"2026-10-15"}).encode()
        x=self.case(primary=raw)
        self.assertIn("RALLIES_CLASSIFICATION_WRONG_ASOF_OR_SCHEMA",x["blockers"])

    def test_untrusted_master_queue_binding_fails(self):
        p=d(P);p["source_master_queue_hash"]="wrong"
        with self.assertRaises(ValueError): self.case(price=p)

    def test_fabricated_price_pass_not_authorized(self):
        p=d(P);p["pass_count"]=1;p["pass_symbols"]=["AAPL"]
        p["unknown_symbols"]=["TSLA"];p["unknown_count"]=1
        p["results"]["AAPL"]={"status":"PASS_PRICE_DV30"}
        with self.assertRaises(ValueError): self.case(price=p)

    def test_unknown_partition_inconsistency_rejected(self):
        p=d(P);p["unknown_symbols"]=["AAPL"];p["unknown_count"]=1
        with self.assertRaises(ValueError): self.case(price=p)

    def test_master_identity_mismatch_rejected(self):
        m=d(M);m["pass_count"]=3
        with self.assertRaises(ValueError): self.case(master=m)

    def test_future_terminal_mixed_asof_rejected(self):
        t=d(T);t["asof_et"]="2026-10-17"
        with self.assertRaises(ValueError): self.case(terminal=t)

    def test_r92_existing_candidate_blocks_readiness(self):
        t=d(T);t["r92_candidates"]=["AAPL"]
        x=self.case(terminal=t)
        self.assertIn("TERMINAL_CLAIMS_R92_BUT_SOURCE_GATES_BLOCKED",x["blockers"])
        self.assertFalse(x["may_notify_user"])

    def test_even_without_other_blockers_no_e2e_authority(self):
        p=d(P);p["unknown_symbols"]=[];p["unknown_count"]=0
        p["pass_symbols"]=[];p["pass_count"]=0
        p["results"]={s:{"status":"FAIL_PRICE","info":{"reason":"LOW_PRICE"}} for s in ("AAPL","TSLA")}
        x=self.case(price=p)
        self.assertFalse(x["full_e2e_source_attested_by_this_audit"])
        self.assertEqual(x["buy_signals"],0)

    def test_governance_status_unexpected_cannot_enable(self):
        g=d(G);g["providers"]["RALLIES"]["automated_non_display_runner_entitlement"]="MAYBE"
        x=self.case(governance=g)
        self.assertFalse(x["governance_state"]["rallies_license_and_volume_claimed"])
        self.assertFalse(x["may_promote_r92"])

if __name__=="__main__":
    unittest.main()
