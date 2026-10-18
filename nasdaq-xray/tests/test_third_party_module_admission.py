#!/usr/bin/env python3
"""Offline, fail-closed selection checks for external RESEARCH patterns only.

This checks XRAY integration eligibility, NOT external package test suites,
source license grants, licensed 260-session feed access or live R92 readiness.
No network, secrets, orders, imports of outside repos, provider calls or alerts.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INVENTORY = ROOT / "research/third_party_module_admission_20261018_v1.json"
VALID_DECISIONS = {
    "REUSE_EXISTING_DESIGN",
    "SHADOW_ADAPTER_RESEARCH",
    "OFFLINE_COMPARISON_CANDIDATE",
    "OFFLINE_ANALYST_SHADOW_CANDIDATE",
    "REFERENCE_ONLY_NO_CODE_IMPORT",
    "REJECT_CORE_INTEGRATION",
}
REQUIRED = {
    "AI_HEDGE_FUND", "OPENBB", "QLIB", "TRADINGAGENTS",
    "OPENSTOCK", "FREQTRADE",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def admit(doc: object) -> dict:
    if type(doc) is not dict or doc.get("schema") != "XRAY_THIRD_PARTY_RESEARCH_ADMISSION_V1":
        raise ValueError("EXTERNAL_ADMISSION_SCHEMA")
    frozen = {
        "effective_policy": "C4.17",
        "activation": "PROPOSAL_ONLY_NOT_CONNECTED",
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
        "all_vendor_rights_verified": False,
        "primary_price_creation_allowed": False,
        "primary_mc_creation_allowed": False,
        "history_pass_creation_allowed": False,
        "r92_creation_allowed": False,
        "notifications_allowed": False,
        "third_party_code_imported": False,
        "credentials_or_market_data_fetched": False,
        "independent_external_suite_executed": False,
    }
    if any(doc.get(k) != v or type(doc.get(k)) is not type(v) for k, v in frozen.items()):
        raise ValueError("EXTERNAL_ADMISSION_FORGED_AUTHORITY")
    if not SHA.fullmatch(str(doc.get("review_base_sha", ""))):
        raise ValueError("EXTERNAL_ADMISSION_UNPINNED_REVIEW")
    rows = doc.get("decisions")
    if type(rows) is not list or len(rows) != len(REQUIRED):
        raise ValueError("EXTERNAL_ADMISSION_ROW_COUNT")
    ids = {r.get("id") for r in rows if type(r) is dict}
    if ids != REQUIRED or len(ids) != len(rows):
        raise ValueError("EXTERNAL_ADMISSION_IDS")
    for row in rows:
        if (row.get("decision") not in VALID_DECISIONS
                or type(row.get("repository")) is not str
                or "/" not in row["repository"]
                or type(row.get("blockers")) is not list
                or not row["blockers"]
                or type(row.get("reuse")) is not list
                or type(row.get("existing")) is not list
                or type(row.get("production_import")) is not bool
                or row["production_import"]
                or type(row.get("independent_runtime_test")) is not bool
                or row["independent_runtime_test"]):
            raise ValueError("EXTERNAL_ADMISSION_ROW_PROMOTION")
        sha = row.get("commit_sha")
        if sha is not None and (type(sha) is not str or not SHA.fullmatch(sha)):
            raise ValueError("EXTERNAL_ADMISSION_BAD_SHA")
        if sha is None:
            raise ValueError("EXTERNAL_ADMISSION_MISSING_PIN")
        for path in row["existing"]:
            if type(path) is not str or path.startswith("/") or ".." in Path(path).parts:
                raise ValueError("EXTERNAL_ADMISSION_PATH")
            if not (ROOT / path).is_file():
                raise ValueError("EXTERNAL_ADMISSION_EXISTING_REUSE_MISSING")
    by_id = {r["id"]: r for r in rows}
    if (by_id["FREQTRADE"]["decision"] != "REJECT_CORE_INTEGRATION"
            or by_id["OPENSTOCK"]["decision"] != "REFERENCE_ONLY_NO_CODE_IMPORT"
            or by_id["AI_HEDGE_FUND"]["decision"] != "REUSE_EXISTING_DESIGN"
            or by_id["OPENBB"]["repository"] != "openbq-org/OpenBB"
            or by_id["OPENBB"]["license"] != "Apache-2.0"):
        raise ValueError("EXTERNAL_ADMISSION_UNSAFE_LICENSE_OR_ROLE")
    return doc


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_six_pinned_candidate_decisions_fail_closed(self):
        self.assertEqual(len(admit(self.doc)["decisions"]), 6)

    def test_root_research_policy_is_research_only(self):
        p = json.loads((ROOT / "manual_decision_policy_v1.json").read_text())
        self.assertEqual(p["parent_policy_version"], "C4.17")
        self.assertEqual(p["mode"], "RESEARCH_ONLY_MANUAL_DECISION")
        self.assertEqual(p["execution"], "NONE")
        self.assertEqual(p["real_money"], "NO-GO")
        self.assertTrue(p["unknown_never_pass"])
        self.assertFalse(p["delivery"]["enabled_in_this_shadow"])
        self.assertTrue(p["hard_gates"]["mc_fallback_watch_cannot_promote"])

    def test_phone_delivery_remains_single_channel_and_unverified(self):
        p = json.loads((ROOT / "notification_channel_policy_v1.json").read_text())
        self.assertEqual(p["user_preference"], "CHATGPT_ONLY")
        self.assertTrue(p["registered_r92_required"])
        self.assertTrue(p["dedup_required"])
        self.assertFalse(p["platform_iphone_receipt_attested"])
        self.assertFalse(p["github_issue_creation_enabled"])

    def test_existing_memory_replay_already_has_hard_gate(self):
        import research_candidate_memory as mem
        d = mem.empty_ledger()
        self.assertFalse(d["alpha_authority"])
        self.assertTrue(d["unknown_never_pass"])
        self.assertEqual(d["entries"], [])
        self.assertEqual(mem.validate_ledger(d), "0" * 64)

    def test_missing_260_history_must_not_be_promoted(self):
        import c418_history_exact_session_shadow_guard as hist
        denied = hist.audit(None, ["AAPL"], "2026-10-16", "SHADOW_TEST", ())
        self.assertEqual(denied["status"], "DATA_BLOCKED")
        self.assertFalse(denied["can_create_HISTORY_PASS"])
        self.assertFalse(denied["can_register_R92"])
        for value in (True, 0.5, float("inf"), float(2**53)):
            self.assertFalse(hist.exact_positive_share_count(value))

    def test_shadow_router_cannot_activate_primary(self):
        import c418_shadow_resilience_guard as routing
        d = routing.advisory_route({}, {}, "MC", "2026-10-16", "2026-10-18T16:00:00Z")
        self.assertEqual(d["status"], "DATA_BLOCKED")
        self.assertFalse(d["can_create_PRIMARY"])
        self.assertFalse(d["can_register_R92"])

    def test_all_authority_mutations_rejected(self):
        for field in (
            "all_vendor_rights_verified",
            "primary_price_creation_allowed",
            "primary_mc_creation_allowed",
            "history_pass_creation_allowed",
            "r92_creation_allowed",
            "notifications_allowed",
            "third_party_code_imported",
            "credentials_or_market_data_fetched",
            "independent_external_suite_executed",
        ):
            x = copy.deepcopy(self.doc)
            x[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "FORGED_AUTHORITY"):
                admit(x)

    def test_candidate_import_and_test_claims_rejected(self):
        for field in ("production_import", "independent_runtime_test"):
            x = copy.deepcopy(self.doc)
            x["decisions"][0][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                admit(x)

    def test_external_unpinned_and_license_promotion_rejected(self):
        for key, value in (
            ("commit_sha", "garbage"), ("decision", "PRIMARY"),
        ):
            x = copy.deepcopy(self.doc)
            x["decisions"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                admit(x)
        x = copy.deepcopy(self.doc)
        next(r for r in x["decisions"] if r["id"] == "FREQTRADE")["decision"] = "SHADOW_ADAPTER_RESEARCH"
        with self.assertRaisesRegex(ValueError, "UNSAFE_LICENSE_OR_ROLE"):
            admit(x)


if __name__ == "__main__":
    unittest.main()
