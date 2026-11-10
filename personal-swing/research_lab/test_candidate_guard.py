#!/usr/bin/env python3
import copy
import json
import unittest
from pathlib import Path
from candidate_guard import validate

ROOT = Path(__file__).parent

class CandidateContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((ROOT / "candidate_manifest.json").read_text(encoding="utf-8"))

    def rejects(self, code, change):
        doc = copy.deepcopy(self.base)
        change(doc)
        with self.assertRaisesRegex(ValueError, code):
            validate(doc)

    def test_valid_manifest(self):
        x = validate(self.base)
        self.assertEqual(x["strong"], 4)
        self.assertEqual(x["helper"], 4)
        self.assertEqual(x["production_approved"], 0)
        self.assertEqual(x["orders"], 0)
        self.assertEqual(x["vendor_calls"], 0)
        self.assertEqual(x["new_schedules"], 0)

    def test_no_package_install(self):
        self.rejects("FORBIDDEN_may_install_packages",
                     lambda x: x["candidates"][0]["policy"].update(
                         may_install_packages=True))

    def test_no_order_tool(self):
        self.rejects("FORBIDDEN_may_place_order",
                     lambda x: x["candidates"][6]["policy"].update(
                         may_place_order=True))

    def test_no_external_data(self):
        self.rejects("FORBIDDEN_may_fetch_external_data",
                     lambda x: x["candidates"][1]["policy"].update(
                         may_fetch_external_data=True))

    def test_no_paid_service(self):
        self.rejects("CORE_SIDE_EFFECT_paid_new_services",
                     lambda x: x["core_policy"].update(paid_new_services=True))

    def test_no_changed_signal(self):
        self.rejects("FORBIDDEN_may_issue_al",
                     lambda x: x["candidates"][2]["policy"].update(may_issue_al=True))

    def test_no_stop_rewrite(self):
        self.rejects("FORBIDDEN_may_change_stop_or_target",
                     lambda x: x["candidates"][3]["policy"].update(
                         may_change_stop_or_target=True))

    def test_no_sheet_write(self):
        self.rejects("FORBIDDEN_may_write_private_sheet",
                     lambda x: x["candidates"][4]["policy"].update(
                         may_write_private_sheet=True))

    def test_no_secrets(self):
        self.rejects("FORBIDDEN_may_read_secrets",
                     lambda x: x["candidates"][6]["policy"].update(
                         may_read_secrets=True))

    def test_no_alert(self):
        self.rejects("FORBIDDEN_may_emit_alert",
                     lambda x: x["candidates"][0]["policy"].update(may_emit_alert=True))

    def test_no_new_schedule(self):
        self.rejects("CORE_SIDE_EFFECT_new_schedules",
                     lambda x: x["core_policy"].update(new_schedules=True))

    def test_no_crypto_or_canonical_changes(self):
        self.rejects("CORE_SIDE_EFFECT_crypto_or_canonical_change",
                     lambda x: x["core_policy"].update(crypto_or_canonical_change=True))

    def test_duplicate_rejected(self):
        self.rejects("DUPLICATE_OR_MISSING_ID",
                     lambda x: x["candidates"][1].update(id=x["candidates"][0]["id"]))

    def test_missing_rejected(self):
        self.rejects("CANDIDATE_COUNT", lambda x: x["candidates"].pop())

    def test_unknown_repo_rejected(self):
        self.rejects("UNRECOGNIZED_SOURCE",
                     lambda x: x["candidates"][0].update(url="https://evil.invalid"))

    def test_wrong_group_rejected(self):
        self.rejects("INVALID_GROUP",
                     lambda x: x["candidates"][4].update(group="STRONG"))

    def test_existing_alias_not_duplicated(self):
        self.rejects("REGISTRY_ALIAS_DRIFT",
                     lambda x: x["candidates"][3].update(existing_registry_key=None))

    def test_no_false_vendor_pit_pass(self):
        self.rejects("UNPROVEN_SUCCESS_real_provider_pit_verified",
                     lambda x: x["candidates"][2].update(real_provider_pit_verified=True))

    def test_no_false_production_permission(self):
        self.rejects("UNPROVEN_SUCCESS_production_authorized",
                     lambda x: x["candidates"][5].update(production_authorized=True))

    def test_no_real_dependency_claim(self):
        self.rejects("UNPROVEN_SUCCESS_external_dependencies_installed",
                     lambda x: x["candidates"][0].update(
                         external_dependencies_installed=True))

    def test_no_extra_capability(self):
        self.rejects("CAPABILITY_POLICY_DRIFT",
                     lambda x: x["candidates"][0]["policy"].update(
                         may_call_undocumented_api=False))

    def test_pin_sha_mismatch_denied(self):
        self.rejects("UPSTREAM_SHA_MISMATCH",
                     lambda x: x["candidates"][0].update(upstream_snapshot_sha="0"*40))

    def test_false_status_promotion_denied(self):
        self.rejects("UNVERIFIED_STATE_PROMOTION",
                     lambda x: x["candidates"][2].update(current_state="PRODUCTION_PASS"))

    def test_fake_runtime_claim_denied(self):
        self.rejects("UNAUTHORIZED_PIN_ROLE",
                     lambda x: x["candidates"][1].update(pin_role="PACKAGE_EXECUTED"))

    def test_baseline_hash_mismatch_denied(self):
        self.rejects("BASELINE_REPOSITORY_PROVENANCE_DRIFT",
                     lambda x: x.update(baseline_repo_main_sha="0"*40))

    def test_core_universe_immutable(self):
        self.rejects("CORE_CONTRACT_DRIFT",
                     lambda x: x["core_policy"].update(universe=519))

if __name__ == "__main__":
    unittest.main()
