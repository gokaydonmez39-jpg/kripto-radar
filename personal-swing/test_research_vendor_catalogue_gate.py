"""No-network, synthetic-negative source permission tests."""
import copy
import json
from pathlib import Path
import unittest

from research_vendor_catalogue_gate import (
    OLD, NEW, EXPECTED_OLD_PILOTS, validate_catalogues
)

HERE = Path(__file__).resolve().parent

def _read():
    return (json.loads((HERE/OLD).read_text(encoding="utf-8")),
            json.loads((HERE/NEW).read_text(encoding="utf-8")))

def _edit(new, repo):
    return next(x for x in new["sources"] if x["repository"] == repo)

class CataloguePolicyTests(unittest.TestCase):
    def check_rejected(self, change, reason):
        old, new = _read()
        change(old, new)
        with self.assertRaisesRegex(ValueError, reason):
            validate_catalogues(old, new)

    def test_actual_catalogue_review_only(self):
        old, new = _read()
        result = validate_catalogues(old, new)
        self.assertEqual(result["old_offline_pilots"], 3)
        self.assertEqual(result["incremental_unique"], 10)
        self.assertEqual(result["new_offline_synthetic_pilots"], 2)
        self.assertFalse(result["financial_actions_allowed"])
        self.assertFalse(result["market_data_retrieved"])

    def test_payment_tools_cannot_promote(self):
        self.check_rejected(
            lambda old, new: _edit(new, "stripe/ai").__setitem__("decision", "OFFLINE_SYNTHETIC_PILOT"),
            "MONEY_TOOL_PROMOTION_FORBIDDEN")

    def test_exchange_order_permission_denied(self):
        self.check_rejected(
            lambda old, new: _edit(new, "alpacahq/alpaca-mcp-server").__setitem__("may_place_order", True),
            "SOURCE_PRIVILEGE_ESCALATION")

    def test_tradingview_algorithmic_feed_cannot_promote(self):
        self.check_rejected(
            lambda old, new: _edit(new, "shner-elmo/TradingView-Screener").__setitem__("decision", "OFFLINE_SYNTHETIC_PILOT"),
            "TRADINGVIEW_NON_DISPLAY_PROHIBITION")

    def test_alpaca_trading_mcp_only_interface(self):
        self.check_rejected(
            lambda old, new: _edit(new, "alpacahq/alpaca-mcp-server").__setitem__("decision", "OFFLINE_SYNTHETIC_PILOT"),
            "TRADING_MCP_PROMOTION_FORBIDDEN")

    def test_provider_rights_cannot_be_assumed(self):
        self.check_rejected(
            lambda old, new: _edit(new, "shner-elmo/TradingView-Screener").__setitem__("source_rights_verified", True),
            "SOURCE_PRIVILEGE_ESCALATION")

    def test_openbb_double_registration_rejected(self):
        self.check_rejected(
            lambda old, new: _edit(new, "openbq-org/OpenBB").__setitem__("decision", "OFFLINE_SYNTHETIC_PILOT"),
            "OPENBB_DOUBLE_REGISTERED")

    def test_secret_use_denied(self):
        self.check_rejected(
            lambda old, new: _edit(new, "stefanoamorelli/sec-edgar-mcp").__setitem__("may_use_secrets", True),
            "SOURCE_PRIVILEGE_ESCALATION")

    def test_unsigned_revision_denied(self):
        self.check_rejected(
            lambda old, new: _edit(new, "wshobson/maverick-mcp").__setitem__("pinned_sha", "latest"),
            "UNPINNED_UPSTREAM_COMMIT")

    def test_catalogue_global_lock(self):
        self.check_rejected(
            lambda old, new: new["global_safety"].__setitem__("production_enabled", True),
            "NEW_CATALOGUE_LIVE_PERMISSION")

    def test_prior_openbb_lock(self):
        self.check_rejected(
            lambda old, new: old["global_controls"].__setitem__("may_trade", True),
            "OLD_CATALOGUE_LIVE_PERMISSION")

    def test_existing_three_research_pilots_protected(self):
        self.check_rejected(
            lambda old, new: _edit(old, "shiyu-coder/Kronos").__setitem__("decision", "REJECT_FOR_LIVE_XRAY"),
            "RESEARCH_PILOT_SCOPE_CHANGED")

    def test_sec_mcp_license_guard(self):
        self.check_rejected(
            lambda old, new: _edit(new, "stefanoamorelli/sec-edgar-mcp").__setitem__("license", "MIT"),
            "SEC_MCP_RIGHTS_OR_SCOPE_CHANGED")

    def test_missing_source_blocker(self):
        self.check_rejected(
            lambda old, new: _edit(new, "wshobson/maverick-mcp").__setitem__("blocking_reason", ""),
            "MISSING_RISK_EVIDENCE")

if __name__ == "__main__":
    unittest.main()
