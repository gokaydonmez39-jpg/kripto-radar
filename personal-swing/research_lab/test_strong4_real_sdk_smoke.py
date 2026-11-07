#!/usr/bin/env python3
"""Offline guard test for SDK smoke runner (does not import third parties)."""
import os
import unittest
from unittest.mock import patch
from strong4_real_sdk_smoke import run,VERSIONS
class TestStrong4RuntimeGate(unittest.TestCase):
    def test_package_targets_frozen(self):
        self.assertEqual(VERSIONS,{"pydantic":"2.14.3","quantstats":"0.0.86",
                                   "vectorbt":"1.2.0","duckdb":"2.0.0"})
    def test_unknown_sdk_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"UNKNOWN_SDK"):
            run("ccxt")
    def test_no_sandbox_denied(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,"MISSING_NETWORK_BOUNDARY"):
                run("duckdb")
    def test_no_secrets_boundary_denied(self):
        with patch.dict(os.environ,{"XRAY_DOCKER_NO_NETWORK":"1"},clear=True):
            with self.assertRaisesRegex(RuntimeError,"MISSING_SECRET_BOUNDARY"):
                run("pydantic")
    def test_explicit_credential_denied(self):
        with patch.dict(os.environ,{"XRAY_DOCKER_NO_NETWORK":"1",
                                     "XRAY_DOCKER_NO_SECRETS":"1",
                                     "GITHUB_TOKEN":"fake-secret"},clear=True):
            with self.assertRaisesRegex(RuntimeError,"CREDENTIAL_PRESENT"):
                run("quantstats")
if __name__=="__main__":unittest.main()
