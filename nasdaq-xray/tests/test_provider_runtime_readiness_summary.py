#!/usr/bin/env python3
"""No-network runner prerequisite states; all credentials are invented fixtures."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provider_runner_access_audit as underlying
import provider_runtime_readiness_summary as subject

RAW = underlying.INVENTORY.read_bytes()
INVENTORY = json.loads(RAW)


def analysis(env=None):
    return underlying.analyze(INVENTORY, env or {}, RAW)


def synthetic_credentials():
    return {
        "XRAY_ALPACA_API_KEY_ID": "SYNTH_ALPACA_ID_001_TEST",
        "XRAY_ALPACA_API_SECRET_KEY": "SYNTH_ALPACA_SECRET_002_TEST",
        "XRAY_MASSIVE_API_KEY": "SYNTH_MASSIVE_003_TEST",
        "XRAY_BQ_API_KEY": "SYNTH_BQ_004_TEST",
    }


def synthetic_complete():
    env = synthetic_credentials()
    for cfg in underlying.EXPLICIT.values():
        env[cfg["grant"]] = "true"
        env[cfg["evidence"]] = "f" * 64
    return env


class RuntimePrerequisitesTests(unittest.TestCase):
    def test_exact_12_empty_runner_no_authority(self):
        result = subject.summarize(analysis())
        self.assertEqual(result["provider_count"], 12)
        x = {p["id"]: p for p in result["providers"]}
        self.assertEqual(set(x), underlying.PROVIDERS)
        for sid in underlying.EXPLICIT:
            self.assertEqual(x[sid]["status"], "CONFIGURATION_BLOCKED")
            self.assertEqual(len(x[sid]["blockers"]), 3)
        self.assertEqual(result["external_http_calls"], 0)
        self.assertFalse(result["primary_created"])
        self.assertFalse(result["r92_created"])

    def test_keys_alone_never_enable_research_probe(self):
        r = subject.summarize(analysis(synthetic_credentials()))
        x = {p["id"]: p for p in r["providers"]}
        for sid in underlying.EXPLICIT:
            self.assertEqual(x[sid]["status"], "CONFIGURATION_BLOCKED")
            self.assertEqual(x[sid]["blockers"], [
                "OPERATOR_RESEARCH_GRANT_NOT_CLAIMED",
                "LICENSE_EVIDENCE_SHA256_NOT_CONFIGURED",
            ])
            self.assertFalse(x[sid]["safe_to_attempt_research_api_flag_only"])

    def test_prerequisite_complete_is_not_independent_entitlement(self):
        r = subject.summarize(analysis(synthetic_complete()))
        self.assertEqual(r["status_counts"].get("CONFIGURED_OPERATOR_PREREQUISITES_ONLY"), 3)
        for p in r["providers"]:
            self.assertFalse(p["independent_license_entitlement_verified"])
            self.assertFalse(p["can_create_PRIMARY"])
            self.assertFalse(p["can_create_HISTORY_PASS"])
            self.assertFalse(p["can_register_R92"])
        self.assertFalse(r["independently_verified_vendor_license"])

    def test_license_claim_without_evidence_remains_blocked(self):
        env = synthetic_credentials()
        for c in underlying.EXPLICIT.values():
            env[c["grant"]] = "true"
        r = subject.summarize(analysis(env))
        self.assertTrue(all("LICENSE_EVIDENCE_SHA256_NOT_CONFIGURED" in p["blockers"]
                            for p in r["providers"] if p["id"] in underlying.EXPLICIT))

    def test_evidence_digest_without_claim_remains_blocked(self):
        env = synthetic_credentials()
        for c in underlying.EXPLICIT.values():
            env[c["evidence"]] = "f"*64
        r = subject.summarize(analysis(env))
        self.assertTrue(all("OPERATOR_RESEARCH_GRANT_NOT_CLAIMED" in p["blockers"]
                            for p in r["providers"] if p["id"] in underlying.EXPLICIT))

    def test_alpaca_requires_both_key_halves(self):
        env = synthetic_complete()
        env.pop("XRAY_ALPACA_API_SECRET_KEY")
        r = subject.summarize(analysis(env))
        x = {p["id"]: p for p in r["providers"]}
        self.assertIn("MISSING_GITHUB_RUNNER_KEY", x["ALPACA"]["blockers"])
        self.assertEqual(x["MASSIVE"]["status"], "CONFIGURED_OPERATOR_PREREQUISITES_ONLY")

    def test_no_secret_value_in_summary_even_with_full_synthetic_env(self):
        env = synthetic_complete()
        r = subject.summarize(analysis(env))
        txt = json.dumps(r, ensure_ascii=False)
        for k, v in env.items():
            self.assertNotIn(v, txt, k)
            self.assertNotIn(k, txt, k)
        self.assertNotIn("USD", txt)
        self.assertNotIn("AAPL", txt)

    def test_injected_primary_or_market_claim_rejected(self):
        for field, fake in (
            ("can_create_primary", True), ("can_register_r92", True),
            ("licensed_non_display_derivative_rights_independently_verified", True),
            ("no_external_http", False), ("api_calls", 1),
            ("price_not_read", False), ("execution", "TRADE"),
        ):
            x = analysis()
            x[field] = fake
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject.summarize(x)

    def test_bad_provider_count_and_ids_rejected(self):
        x = analysis()
        x["providers"].pop()
        with self.assertRaisesRegex(ValueError, "EXACT_TWELVE_PROVIDER_SCOPE"):
            subject.summarize(x)
        x = analysis()
        x["providers"][0]["id"] = "EVIL"
        with self.assertRaises(ValueError):
            subject.summarize(x)

    def test_forged_provider_rights_rejected(self):
        for field in ("production_primary_authority", "independently_verified_legal_rights",
                      "price_source_pass", "current_mc_primary_pass"):
            x = analysis()
            x["providers"][0][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "SOURCE_FORGED_AUTHORITY"):
                subject.summarize(x)

    def test_forged_safe_to_attempt_rejected(self):
        for fake in (True, 1, "true"):
            x = analysis()
            x["providers"][0]["safe_to_attempt_research_api"] = fake
            with self.subTest(fake=fake), self.assertRaises(ValueError):
                subject.summarize(x)

    def test_mapped_bad_enum_rejected(self):
        for field in ("runner_key_presence", "operator_unattended_research_claim",
                      "operator_evidence_hash_format"):
            x = analysis()
            item = next(p for p in x["providers"] if p["id"] == "BUSINESSQUANT")
            item[field] = "APPROVED"
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject.summarize(x)

    def test_unmapped_provider_cannot_be_promoted(self):
        x = analysis()
        item = next(p for p in x["providers"] if p["id"] == "OPENBB")
        item["safe_to_attempt_research_api"] = True
        with self.assertRaisesRegex(ValueError, "UNMAPPED_SOURCE_CANNOT_PROMOTE"):
            subject.summarize(x)

    def test_inventory_sha_malformed_rejected(self):
        x = analysis()
        x["source_inventory_git_blob_sha"] = "0"*39
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA"):
            subject.summarize(x)

    def test_scope_is_pinned_to_c417(self):
        x = analysis()
        x["policy"] = "C4.18"
        with self.assertRaisesRegex(ValueError, "AUDIT_SCHEMA_POLICY"):
            subject.summarize(x)

    def test_provider_status_does_not_claim_runtime_validation(self):
        x = subject.summarize(analysis(synthetic_complete()))
        self.assertFalse(x["live_vendor_data_fetched"])
        self.assertFalse(x["independently_verified_vendor_license"])
        self.assertFalse(x["notifications_sent"])
        self.assertTrue(x["unknown_never_pass"])
        self.assertEqual(x["execution"], "NONE")
        self.assertEqual(x["real_money"], "NO-GO")


if __name__ == "__main__":
    unittest.main()
