#!/usr/bin/env python3
"""Negative/positive contract tests; no imports of the four candidate packages."""
import copy
import json
import unittest
from pathlib import Path
from strong4_guard import validate

ROOT=Path(__file__).parent
class Strong4ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads((ROOT/"strong4_manifest.json").read_text(encoding="utf-8"))
    def denied(self,expected,change):
        x=copy.deepcopy(self.base)
        change(x)
        with self.assertRaisesRegex(ValueError,expected):
            validate(x)
    def test_valid_four(self):
        x=validate(self.base)
        self.assertEqual(len(x["candidates"]),4)
        self.assertEqual(x["sdk_runtime_pass_claims"],0)
        self.assertFalse(x["production_authorized"])
    def test_477_immutable(self):
        self.denied("CORE_DRIFT_universe",lambda x:x["protected_contract"].update(universe=478))
    def test_stop_immutable(self):
        self.denied("CORE_DRIFT_stop_atr",lambda x:x["protected_contract"].update(stop_atr=3))
    def test_target_immutable(self):
        self.denied("CORE_DRIFT_target_atr",lambda x:x["protected_contract"].update(target_atr=5))
    def test_15_session_watch_immutable(self):
        self.denied("CORE_DRIFT_tracking_xnas_sessions",lambda x:x["protected_contract"].update(tracking_xnas_sessions=10))
    def test_iex_immutable(self):
        self.denied("CORE_DRIFT_provider",lambda x:x["protected_contract"].update(provider="SIP"))
    def test_no_order(self):
        self.denied("FORBIDDEN_can_place_order",lambda x:x["sources"][1]["permissions"].update(can_place_order=True))
    def test_no_al(self):
        self.denied("FORBIDDEN_can_issue_al",lambda x:x["sources"][2]["permissions"].update(can_issue_al=True))
    def test_no_sheets(self):
        self.denied("FORBIDDEN_can_write_private_sheet",lambda x:x["sources"][3]["permissions"].update(can_write_private_sheet=True))
    def test_no_external_vendor(self):
        self.denied("FORBIDDEN_can_call_external_vendor",lambda x:x["sources"][0]["permissions"].update(can_call_external_vendor=True))
    def test_no_secret(self):
        self.denied("FORBIDDEN_can_access_secrets",lambda x:x["sources"][2]["permissions"].update(can_access_secrets=True))
    def test_no_new_cron(self):
        self.denied("CORE_DRIFT_new_schedule",lambda x:x["protected_contract"].update(new_schedule=True))
    def test_no_paid_provider(self):
        self.denied("CORE_DRIFT_new_paid_service",lambda x:x["protected_contract"].update(new_paid_service=True))
    def test_no_crypto_change(self):
        self.denied("CORE_DRIFT_crypto_change",lambda x:x["protected_contract"].update(crypto_change=True))
    def test_no_license_promotion(self):
        self.denied("SOURCE_IDENTITY_DRIFT",lambda x:x["sources"][2].update(license="Apache-2.0"))
    def test_no_unproven_runtime(self):
        self.denied("UNPROVEN_actual_sdk_runtime_verified",lambda x:x["sources"][0].update(actual_sdk_runtime_verified=True))
    def test_no_production(self):
        self.denied("UNPROVEN_production_authorized",lambda x:x["sources"][3].update(production_authorized=True))
    def test_no_duplicate(self):
        self.denied("UNKNOWN_OR_DUPLICATE_CANDIDATE",lambda x:x["sources"][2].update(id="quantstats"))
    def test_no_core_type_coercion(self):
        self.denied("CORE_DRIFT_universe",lambda x:x["protected_contract"].update(universe=True))
    def test_no_extra_permissions(self):
        self.denied("CAPABILITY_SET_CHANGED",lambda x:x["sources"][1]["permissions"].update(can_send_transactions=False))
    def test_no_wheel_hash_claim(self):
        self.denied("SOURCE_ATTESTATION_DRIFT",lambda x:x["sources"][0].update(review_sha_not_installed_wheel_hash=False))
    def test_no_registry_change(self):
        self.denied("BASELINE_DRIFT",lambda x:x.update(original_88_registry_sha="0"*40))
    def test_no_scope_escalation(self):
        self.denied("SCOPE_DRIFT",lambda x:x.update(scope="production"))
if __name__=="__main__":unittest.main()
