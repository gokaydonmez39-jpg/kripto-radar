#!/usr/bin/env python3
"""Unit tests for the real-SDK smoke gate; do NOT require SDK imports."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from candidate_sdk_runtime_smoke import CANDIDATES, smoke


class CandidateSdkSmokeGateTests(unittest.TestCase):
    def test_exact_four_sdk_targets(self):
        self.assertEqual(set(CANDIDATES), {"pydantic-ai", "mcp-use", "qlib", "openbb-v5"})

    def test_frozen_versions(self):
        for package, version in CANDIDATES.values():
            self.assertTrue(package)
            self.assertEqual(len(version.split(".")), 3)

    def test_reject_unknown_candidate(self):
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_CANDIDATE"):
            smoke("alpaca-mcp")

    def test_no_network_claim_no_import(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "NETWORK_ISOLATION_NOT_ASSERTED"):
                smoke("qlib")

    def test_no_secretless_claim_no_import(self):
        with patch.dict(os.environ, {"XRAY_CONTAINER_NO_NETWORK": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRETLESS_RUNTIME_NOT_ASSERTED"):
                smoke("pydantic-ai")

    def test_reject_present_sensitive_env(self):
        with patch.dict(os.environ, {
                "XRAY_CONTAINER_NO_NETWORK": "1",
                "XRAY_NO_SECRETS": "1",
                "GITHUB_TOKEN": "test-do-not-use"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SENSITIVE_ENV_PRESENT"):
                smoke("mcp-use")

    def test_sdk_smoke_never_confers_production(self):
        import inspect
        source = inspect.getsource(smoke)
        self.assertIn('"production_authorized": False', source)
        self.assertIn('"pit_477x500_verified": False', source)
        self.assertIn('"may_place_order": False', source)


if __name__ == "__main__":
    unittest.main()
