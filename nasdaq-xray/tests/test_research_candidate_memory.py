#!/usr/bin/env python3
"""Independent positive/negative controls for symbolic PIT candidate memory."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_candidate_memory as m


def receipt(asof="2026-10-15", groups=None):
    groups = {"MANH": ["B", "D"], "WDAY": ["B"]} if groups is None else groups
    return {
        "schema": m.RECEIPT_SCHEMA, "asof_et": asof,
        "execution": "NONE", "real_money": "NO-GO",
        "orders": [], "registered_R92_count": 0,
        "research_all_three_artifacts_same_asof_and_sha": True,
        "research_cohort_full_symbolic_partition_checked": True,
        "operational_final_with_real_user_delivery_attested": False,
        "c417_primary_price_mc_release_attested": False,
        "source_rights_attested": False,
        "research_operational_state":
            "RESEARCH_EVIDENCE_VERIFIED_NO_RELEASE_OR_DEVICE_RECEIPT",
        "research_watch_families": groups,
        "research_watch_symbols": sorted(groups),
        "research_technical_watch_count": len(groups),
        "watch_membership_digest_sha256": m.sha({
            "asof_et": asof, "technical_setup_family_verified": groups}),
        "source_causal_digest_sha256": "1" * 64,
        "research_symbol_set_sha256": "2" * 64,
        "source_workflow_run_id": 1001,
        "technical_watch_workflow_run_id": 1002,
        "mirror_workflow_run_id": 1003,
        "rth_research_proxy_count": 416,
    }


class SymbolicMemoryTests(unittest.TestCase):
    def setUp(self):
        self.a = receipt()

    def expect_rejected(self, changed, fragment):
        with self.assertRaisesRegex(ValueError, "XRAY_MEMORY_" + fragment):
            m.propose(m.empty_ledger(), changed)

    def test_entry_idempotence_and_hash_chain(self):
        ledger, status = m.propose(m.empty_ledger(), self.a)
        self.assertEqual(status, "NEW_ACCEPTED_SESSION")
        self.assertEqual(len(ledger["entries"][0]["watch_events"]), 2)
        self.assertEqual(m.validate_ledger(ledger),
                         ledger["entries"][0]["entry_sha256"])
        again, status = m.propose(ledger, self.a)
        self.assertEqual(status, "IDEMPOTENT_NO_CHANGE")
        self.assertEqual(ledger, again)
        self.assertFalse(again["alpha_authority"])

    def test_next_session_membership_family_change_and_exit_uncertain(self):
        ledger, _ = m.propose(m.empty_ledger(), self.a)
        b = receipt("2026-10-16",
                    {"MANH": ["D"], "MSFT": ["D"], "WDAY": ["B"]})
        next_ledger, status = m.propose(ledger, b)
        self.assertEqual(status, "NEW_ACCEPTED_SESSION")
        events = next_ledger["entries"][-1]["watch_events"]
        self.assertEqual([(x["symbol"], x["event"]) for x in events], [
            ("MANH", "WATCH_FAMILY_CHANGED"),
            ("MSFT", "WATCH_FIRST_OBSERVED"),
        ])
        self.assertTrue(all(x["al"] is False and
                            x["confirmed_invalidation"] is False for x in events))
        c = receipt("2026-10-19", {"MSFT": ["D"]})
        nxt, _ = m.propose(next_ledger, c)
        gone = [x for x in nxt["entries"][-1]["watch_events"]
                if x["symbol"] == "MANH"][0]
        self.assertEqual(gone["event"],
                         "WATCH_NOT_OBSERVED_IN_NEXT_ACCEPTED_SESSION")
        self.assertFalse(gone["confirmed_invalidation"])
        self.assertEqual(m.validate_ledger(nxt),
                         nxt["entries"][-1]["entry_sha256"])

    def test_same_date_revised_source_is_fail_closed(self):
        ledger, _ = m.propose(m.empty_ledger(), self.a)
        b = copy.deepcopy(self.a)
        b["source_workflow_run_id"] = 555
        with self.assertRaisesRegex(ValueError, "SAME_ASOF_REVISED_RECEIPT"):
            m.propose(ledger, b)

    def test_out_of_order_is_fail_closed(self):
        ledger, _ = m.propose(m.empty_ledger(), self.a)
        with self.assertRaisesRegex(ValueError, "OUT_OF_ORDER_ASOF"):
            m.propose(ledger, receipt("2026-10-14"))

    def test_reject_fake_alpha_and_delivery(self):
        for key, value in (
            ("registered_R92_count", 1),
            ("execution", "BROKER"),
            ("real_money", "GO"),
            ("orders", [{"ticker": "MANH"}]),
            ("operational_final_with_real_user_delivery_attested", True),
            ("c417_primary_price_mc_release_attested", True),
            ("source_rights_attested", True),
        ):
            with self.subTest(key=key):
                b = copy.deepcopy(self.a)
                b[key] = value
                with self.assertRaises(ValueError):
                    m.propose(m.empty_ledger(), b)

    def test_reject_research_evidence_forgery(self):
        for key in ("research_all_three_artifacts_same_asof_and_sha",
                    "research_cohort_full_symbolic_partition_checked"):
            b = copy.deepcopy(self.a)
            b[key] = False
            self.expect_rejected(b, "ACCEPTANCE")

    def test_reject_forged_symbol_hash_and_family(self):
        b = copy.deepcopy(self.a)
        b["research_watch_families"]["MANH"] = ["A"]
        self.expect_rejected(b, "WATCH_MEMBERSHIP_SHA")
        b = copy.deepcopy(self.a)
        b["research_watch_symbols"] = ["MANH"]
        self.expect_rejected(b, "WATCH_SYMBOL_SET")
        b = copy.deepcopy(self.a)
        b["research_watch_families"]["MANH"] = ["B", "E"]
        self.expect_rejected(b, "FAMILY_SET")
        b = copy.deepcopy(self.a)
        b["research_symbol_set_sha256"] = "not_a_sha"
        self.expect_rejected(b, "SOURCE_HASH")

    def test_reject_tampering_and_reordering(self):
        ledger, _ = m.propose(m.empty_ledger(), self.a)
        ledger, _ = m.propose(ledger, receipt("2026-10-16", {"MSFT": ["D"]}))
        for mutation in (
            lambda x: x["entries"][0]["watch_families"].clear(),
            lambda x: x["entries"][1].update(prev_entry_sha256="0" * 64),
            lambda x: x["entries"][1].update(asof_et="2026-10-15"),
            lambda x: x["entries"][1]["watch_events"].clear(),
            lambda x: x.update(alpha_authority=True),
        ):
            b = copy.deepcopy(ledger)
            mutation(b)
            with self.assertRaises(ValueError):
                m.validate_ledger(b)

    def test_epoch_gaps_are_not_forward_filled(self):
        ledger, _ = m.propose(m.empty_ledger(), self.a)
        later, _ = m.propose(ledger, receipt("2026-10-22", {}))
        self.assertEqual(len(later["entries"]), 2)
        self.assertEqual(later["entries"][-1]["watch_count"], 0)
        self.assertNotIn("2026-10-21",
                         [x["asof_et"] for x in later["entries"]])

    def test_cli_proposes_without_mutating_source_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "receipt.json"
            out = root / "proposal.json"
            ledger = root / "ledger.json"
            inp.write_text(json.dumps(self.a), encoding="utf-8")
            ledger.write_text(json.dumps(m.empty_ledger()), encoding="utf-8")
            original = ledger.read_bytes()
            script = Path(m.__file__)
            run = subprocess.run(
                [sys.executable, str(script), "--receipt", str(inp),
                 "--ledger", str(ledger), "--out", str(out)],
                capture_output=True, text=True, check=True)
            self.assertEqual(original, ledger.read_bytes())
            self.assertFalse(json.loads(run.stdout)["persisted_to_main"])
            self.assertEqual(len(json.loads(out.read_text())["entries"]), 1)
            bad = subprocess.run(
                [sys.executable, str(script), "--receipt", str(inp),
                 "--ledger", str(ledger), "--out", str(ledger)],
                capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(original, ledger.read_bytes())


if __name__ == "__main__":
    unittest.main()
