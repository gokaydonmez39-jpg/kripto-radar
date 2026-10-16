#!/usr/bin/env python3
"""Offline safety tests: terminal R92 registration must be a BIJECTION.

These use made-up synthetic symbols, synthetic data and no network, trading,
device notifications or market data. unittest assertions run under python -O.
"""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from e2e_production_readiness import (
    TASK_ID, REQUIRED_LOCAL_CHECKS, registered_research_candidate_exact,
)

ASOF="2026-10-16"
T_SHA="synthetic-terminal-content-sha-not-from-production"

def base():
    t={
        "asof_et":ASOF,"candidate_local_research_pass":True,
        "candidate_delivery_safety":{"status":"PASS"},
        "checks":{name:True for name in REQUIRED_LOCAL_CHECKS},
        "r92_candidates":["AAA|B"],
        "sets":{"pre_g9_tech_pass":["AAA|B"]}
    }
    row={
        "schema":"XRAY_RESEARCH_CANDIDATE_R92_V1",
        "delivery_key":"synthetic-key-1","symbol":"AAA","setup":"B",
        "asof_et":ASOF,"mc_class":"MC_PASS_PRIMARY",
        "execution":"NONE","real_money":"NO-GO",
        "entry_low":20.0,"entry_high":21.0,"chase_limit":22.0,
        "stop":19.5,"r1":26.5,"rr_basic":2.5,"rr_severe":1.7,
        "dv30":100_000_000.0,
        "regime":"synthetic","event_status":"synthetic",
        "mc_source":"synthetic","liquidity":"synthetic",
        "pass_reason":"synthetic","g9_status":"synthetic",
        "account_status":"synthetic","registered_at_utc":"synthetic"}
    p={
        "schema":"XRAY_GITHUB_DURABLE_STATE_V3",
        "authority":"GITHUB_CURRENT_POINTER",
        "execution":"NONE","real_money":"NO-GO",
        "state_json":{
            "task_id":TASK_ID,"asof_et":ASOF,
            "deep_final_evidence":{
                "terminal_path":"nasdaq-xray/canonical_current_terminal.json",
                "terminal_blob_sha":T_SHA},
            "delivery_keys":["synthetic-key-1"],"r92":[row]}
    }
    return t,p

def add_second(t,p):
    t["r92_candidates"].append("BBB|D")
    t["sets"]["pre_g9_tech_pass"].append("BBB|D")
    second=copy.deepcopy(p["state_json"]["r92"][0])
    second.update(symbol="BBB",setup="D",delivery_key="synthetic-key-2")
    p["state_json"]["r92"].append(second)
    p["state_json"]["delivery_keys"].append("synthetic-key-2")

class TestExactRegistrationBijection(unittest.TestCase):
    def check(self,t,p):
        return registered_research_candidate_exact(t,p,ASOF,T_SHA)

    def test_one_exact_synthetic_candidate_positive(self):
        t,p=base()
        self.assertTrue(self.check(t,p))

    def test_two_exact_synthetic_candidates_positive(self):
        t,p=base()
        add_second(t,p)
        self.assertTrue(self.check(t,p))

    def test_three_exact_synthetic_candidates_positive(self):
        t,p=base()
        add_second(t,p)
        t["r92_candidates"].append("CCC|A")
        t["sets"]["pre_g9_tech_pass"].append("CCC|A")
        x=copy.deepcopy(p["state_json"]["r92"][0])
        x.update(symbol="CCC",setup="A",delivery_key="synthetic-key-3")
        p["state_json"]["r92"].append(x)
        p["state_json"]["delivery_keys"].append("synthetic-key-3")
        self.assertTrue(self.check(t,p))

    def test_one_pointer_cannot_cover_two_terminal_candidates(self):
        t,p=base()
        t["r92_candidates"].append("BBB|D")
        t["sets"]["pre_g9_tech_pass"].append("BBB|D")
        self.assertFalse(self.check(t,p))

    def test_one_terminal_cannot_cover_two_pointer_rows(self):
        t,p=base()
        add_second(t,p)
        t["r92_candidates"].pop()
        t["sets"]["pre_g9_tech_pass"].pop()
        self.assertFalse(self.check(t,p))

    def test_extra_delivery_key_is_not_a_real_registration(self):
        t,p=base()
        p["state_json"]["delivery_keys"].append("unreferenced")
        self.assertFalse(self.check(t,p))

    def test_missing_delivery_key_cannot_be_overlooked(self):
        t,p=base()
        add_second(t,p)
        p["state_json"]["delivery_keys"].pop()
        self.assertFalse(self.check(t,p))

    def test_duplicate_terminal_member_set_cannot_hide_duplication(self):
        t,p=base()
        t["r92_candidates"].append("AAA|B")
        t["sets"]["pre_g9_tech_pass"].append("AAA|B")
        self.assertFalse(self.check(t,p))

    def test_duplicate_pointer_setup_row_cannot_impersonate_second(self):
        t,p=base()
        add_second(t,p)
        p["state_json"]["r92"][1]["symbol"]="AAA"
        p["state_json"]["r92"][1]["setup"]="B"
        self.assertFalse(self.check(t,p))

    def test_swapped_or_casefolded_key_cannot_pass(self):
        t,p=base()
        for tweak in (
            lambda t,p:p["state_json"]["r92"][0].update(symbol="aaa"),
            lambda t,p:p["state_json"]["r92"][0].update(setup="b"),
            lambda t,p:t["r92_candidates"].__setitem__(0,"aaa|B"),
            lambda t,p:p["state_json"]["delivery_keys"].__setitem__(0," synthetic-key-1"),
            lambda t,p:t["r92_candidates"].__setitem__(0,"ААА|B"),
        ):
            with self.subTest(tweak=str(tweak)):
                a,b=copy.deepcopy(t),copy.deepcopy(p)
                tweak(a,b)
                self.assertFalse(self.check(a,b))

    def test_over_registered_four_candidates_rejected(self):
        t,p=base()
        add_second(t,p)
        for sym,k,setup in (("CCC","3","A"),("DDD","4","B")):
            t["r92_candidates"].append(sym+"|"+setup)
            t["sets"]["pre_g9_tech_pass"].append(sym+"|"+setup)
            x=copy.deepcopy(p["state_json"]["r92"][0])
            x.update(symbol=sym,setup=setup,delivery_key="synthetic-key-"+k)
            p["state_json"]["r92"].append(x)
            p["state_json"]["delivery_keys"].append("synthetic-key-"+k)
        self.assertFalse(self.check(t,p))

    def test_missing_final_provenance_never_promotes(self):
        t,p=base()
        p["state_json"]["deep_final_evidence"]["terminal_blob_sha"]="drift"
        self.assertFalse(self.check(t,p))

    def test_broker_trading_flag_never_promotes(self):
        t,p=base()
        p["state_json"]["r92"][0]["execution"]="ORDER"
        self.assertFalse(self.check(t,p))

if __name__=="__main__":
    unittest.main()
