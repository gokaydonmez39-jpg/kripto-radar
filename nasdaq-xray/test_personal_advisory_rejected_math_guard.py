#!/usr/bin/env python3
"""Offline fail-closed math/provenance regression; synthetic symbols only."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import personal_research_advisory_ledger_guard as guard


def case():
    return {
        "schema": guard.DIGEST, "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True, "certified_C417_AL_signal_count": 0,
        "registered_r92_count": 0, "candidate_setup_is_not_R92": True,
        "automated_alert_authority": False, "iphone_receipt_attested": False,
        "no_raw_ohlcv_or_levels_exported": True,
        "source_confidence": {"grade": "LOW"},
        "source_epoch_blobs": {
            "root": "a" * 40, "master": "b" * 40, "price": "c" * 40},
        "asof_et": "2026-11-02",
        "research_setup_candidate_symbols": [],
        "research_setup_candidate_count": 0,
        "recent_technical_trigger_count": 1,
        "recent_technical_triggers": [
            {"symbol": "SYN", "status": "TRIGGER_OBSERVED_NOT_APPROVED",
             "not_a_trade_or_R92": True,
             "technical_source_confidence": "LIMITED_SECONDARY_EOD",
             "math_formula_audited": False,
             "unresolved_or_rejected": [
                 "UNRESOLVED_OR_UNAPPROVED_TECHNICAL_EVIDENCE"]}],
        "status": "PERSONAL_LIQUIDITY_WATCH_AND_REJECTED_TRIGGERS",
    }


class RejectedMathContract(unittest.TestCase):
    def test_rejected_unaudited_math_is_safe_hold_not_fatal(self):
        self.assertIsNone(guard.stable_key(case()))

    def test_unaudited_trigger_must_have_explicit_unresolved_blocker(self):
        d = case()
        d["recent_technical_triggers"][0]["unresolved_or_rejected"] = ["EVENT_UNKNOWN"]
        with self.assertRaisesRegex(ValueError, "UNAUDITED_TRIGGER_NOT_FLAGGED"):
            guard.stable_key(d)

    def test_rejected_trigger_must_not_be_promoted_to_setup(self):
        d = case()
        d["recent_technical_triggers"][0]["status"] = "RESEARCH_SETUP_CANDIDATE"
        d["recent_technical_triggers"][0]["unresolved_or_rejected"] = []
        d["research_setup_candidate_symbols"] = ["SYN"]
        d["research_setup_candidate_count"] = 1
        d["status"] = "PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE"
        with self.assertRaisesRegex(ValueError, "CANDIDATE_MATH_REQUIRED"):
            guard.stable_key(d)

    def test_audited_candidate_has_stable_key_not_delivery(self):
        d = case()
        d["recent_technical_triggers"][0]["status"] = "RESEARCH_SETUP_CANDIDATE"
        d["recent_technical_triggers"][0]["math_formula_audited"] = True
        d["recent_technical_triggers"][0]["unresolved_or_rejected"] = []
        d["research_setup_candidate_symbols"] = ["SYN"]
        d["research_setup_candidate_count"] = 1
        d["status"] = "PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE"
        value = guard.stable_key(d)
        self.assertRegex(value, r"^[a-f0-9]{64}$")
        self.assertFalse(d["iphone_receipt_attested"])
        self.assertFalse(d["automated_alert_authority"])

    def test_type_and_provenance_mutations_still_fail(self):
        base = case()
        for key, value in [
            ("math_formula_audited", "FALSE"),
            ("not_a_trade_or_R92", False),
            ("technical_source_confidence", "PRIMARY"),
            ("unresolved_or_rejected", "text")]:
            d = deepcopy(base)
            d["recent_technical_triggers"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.stable_key(d)

    def test_current_digest_still_cannot_claim_delivery(self):
        raw = json.loads(
            (Path(__file__).resolve().parent /
             "personal_research_signal_digest.json").read_text())
        k = guard.stable_key(raw)
        if raw["research_setup_candidate_count"] == 0:
            self.assertIsNone(k)
        else:
            self.assertRegex(k, r"^[a-f0-9]{64}$")
        self.assertEqual(raw["registered_r92_count"], 0)
        self.assertFalse(raw["automated_alert_authority"])


if __name__ == "__main__":
    unittest.main()
