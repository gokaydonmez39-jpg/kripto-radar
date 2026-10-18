"""Actual optional MarkItDown 0.1.8 offline conversion and negative safety tests."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sec_markitdown_offline_shadow import convert_local_html, MAX_SIZE

HTML = b"""<!DOCTYPE html><html lang="en"><head><title>SEC 8-K</title></head><body>
<h1>Form 8-K</h1><p>Accession: 0000000000-26-000042</p>
<p>Reporting period: 2026-10-16</p><p>Revenue: 12,345,678 USD.</p>
</body></html>"""
LITERALS = ["0000000000-26-000042", "2026-10-16", "12,345,678"]

class TestMarkItDownSECShadow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "filing.html"
        self.path.write_bytes(HTML)
        self.sha = hashlib.sha256(HTML).hexdigest()

    def go(self, path=None, sha=None, literals=None):
        return convert_local_html(
            path or self.path,
            source_sha256=self.sha if sha is None else sha,
            required_literals=LITERALS if literals is None else literals)

    def test_real_markitdown_keeps_original_accession_date_and_numbers(self):
        x = self.go()
        for t in LITERALS:
            self.assertIn(t, x["markdown_text"])
        self.assertEqual(x["source_sha256"], self.sha)
        self.assertTrue(x["required_literals_preserved"])
        self.assertEqual(x["status"], "CONVERTED_LOCAL_HTML_RESEARCH_ONLY")
        for k in ["official_sec_document_verified","sec_acceptance_time_verified",
                  "lookahead_safe","primary_market_data","source_rights_attested",
                  "can_create_price_pass","can_register_r92","can_notify_user"]:
            self.assertIs(x[k],False,k)
        self.assertEqual(x["real_money"],"NO-GO")

    def test_forged_digest_fails_closed(self):
        with self.assertRaises(ValueError):
            self.go(sha="0"*64)

    def test_source_changed_after_digest_fails_closed(self):
        self.path.write_bytes(HTML+b"<p>tampered</p>")
        with self.assertRaises(ValueError):
            self.go()

    def test_secret_or_nonlocal_nonsense_file_not_accepted(self):
        txt = Path(self.temp.name)/"secret.txt"
        txt.write_bytes(HTML)
        with self.assertRaises(ValueError):
            self.go(path=txt)

    def test_missing_literal_fails_closed(self):
        with self.assertRaises(ValueError):
            self.go(literals=["NONEXISTENT-TRUSTED-NUMBER"])

    def test_duplicate_or_bad_literal_contract_fails(self):
        for v in [[],["abc","abc"],["a"],["valid\nnewline"],["x"*101]]:
            with self.subTest(v=v),self.assertRaises(ValueError):
                self.go(literals=v)

    def test_oversize_document_fails_before_converter(self):
        self.path.write_bytes(b"<p>"+b"0"*(MAX_SIZE+10)+b"</p>")
        with self.assertRaises(ValueError):
            self.go(sha=hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_symlink_rejected(self):
        alias=Path(self.temp.name)/"alias.html"
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            self.go(path=alias)

if __name__=="__main__":
    unittest.main()
