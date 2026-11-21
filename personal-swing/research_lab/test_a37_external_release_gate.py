"""Negative falsification of all A37 external scientific admission gates."""
import copy
import unittest
from a37_external_release_gate import (audit_research_gate,current_public_sample,
    hypothetical_gap_loss,verify_split_sample,EvidenceBlocked,BLOCKERS)

class TestExternalFinal(unittest.TestCase):
    def deny(self,change,match):
        p=copy.deepcopy(current_public_sample());change(p)
        with self.assertRaisesRegex(EvidenceBlocked,match):
            audit_research_gate(p)

    def test_witness_pass_not_release(self):
        out=audit_research_gate(current_public_sample())
        self.assertEqual(out["state"],"RESEARCH_ENGINEERING_READY_BUT_SCIENTIFIC_FINAL_NO_GO")
        self.assertEqual(len(out["four_release_gates"]),4)
        self.assertEqual(set(out["four_release_gates"]),set(BLOCKERS))
        for key in ("may_generate_al","may_change_rules","may_send_notifications",
                    "may_write_sheets","may_trade","may_merge_to_production"):
            self.assertIs(out[key],False)
    def test_deterministic(self):
        self.assertEqual(audit_research_gate(current_public_sample()),
                         audit_research_gate(current_public_sample()))
    def test_missing_split(self):
        self.deny(lambda p:p["splits"].pop("MNST"),"SPLIT_SAMPLE_MISSING")
    def test_wrong_split_ratio(self):
        self.deny(lambda p:p["splits"]["IESC"].update(ratio=3),"WITNESS_DATE_OR_RATIO")
    def test_wrong_split_date(self):
        self.deny(lambda p:p["splits"]["MNST"].update(date="2026-08-12"),
                  "WITNESS_DATE_OR_RATIO")
    def test_fake_split_price(self):
        self.deny(lambda p:p["splits"]["MNST"].update(raw_pre="89"),"SPLIT_RATIO_RECONCILIATION")
    def test_fake_CA_pass(self):
        self.deny(lambda p:p.update(full_adjustment_provenance=True),
                  "UNVERIFIED_PROMOTION_full_adjustment")
    def test_fake_PIT_pass(self):
        self.deny(lambda p:p.update(full_pit_477_daily_universe=True),
                  "UNVERIFIED_PROMOTION_full_pit")
    def test_fake_OOS_pass(self):
        self.deny(lambda p:p.update(complete_oos=True),"UNVERIFIED_PROMOTION_complete_oos")
    def test_fake_cost_pass(self):
        self.deny(lambda p:p.update(actual_or_sourced_execution_costs=True),
                  "UNVERIFIED_PROMOTION_actual_or_sourced")
    def test_fake_tail_pass(self):
        self.deny(lambda p:p.update(full_tail_risk_results=True),
                  "UNVERIFIED_PROMOTION_full_tail")
    def test_fake_vendor_asof(self):
        self.deny(lambda p:p.update(source_asof_verification=True),
                  "UNVERIFIED_PROMOTION_source_asof")
    def test_hide_rate_limit(self):
        self.deny(lambda p:p.update(provider_access_rate_limited=False),"HIDDEN_RATE_LIMIT")
    def test_false_full_universe(self):
        self.deny(lambda p:p.update(real_500_bar_sample_count=477),"FALSE_FULL_HISTORY_CLAIM")
    def test_public_private_confusion(self):
        self.deny(lambda p:p.update(complete_closed_episode_sample_count=2),
                  "PRIVATE_EPISODE_EVIDENCE_CANNOT_BE_ATTESTED_PUBLICLY")
    def test_extra_success_field(self):
        self.deny(lambda p:p.update(production_ready=True),"MANIFEST_SCHEMA")
    def test_gap_cost_assumption(self):
        r=hypothetical_gap_loss("100","95","90")
        self.assertGreater(r["gap_open_net_pct"],-11.0)
        self.assertLess(r["gap_open_net_pct"],-10.0)
        self.assertLess(r["gap_open_net_pct"],r["stop_net_pct"])
        self.assertIs(r["fill_observed"],False)
        self.assertIs(r["may_claim_executed_pnl"],False)
    def test_not_gap(self):
        with self.assertRaisesRegex(EvidenceBlocked,"NOT_A_STOP_GAP_EXAMPLE"):
            hypothetical_gap_loss(100,95,96)
    def test_bad_cost(self):
        with self.assertRaisesRegex(EvidenceBlocked,"INVALID_COST_ASSUMPTION"):
            hypothetical_gap_loss(100,95,90,entry_bps=-1)
    def test_lookalike_bool(self):
        with self.assertRaisesRegex(EvidenceBlocked,"UNVERIFIED_PROMOTION_complete_oos"):
            p=current_public_sample();p["complete_oos"]=1;audit_research_gate(p)
    def test_zero_denominator(self):
        with self.assertRaisesRegex(EvidenceBlocked,"NONPOSITIVE_OR_NONFINITE"):
            hypothetical_gap_loss(0,95,90)

if __name__=="__main__":
    unittest.main()
