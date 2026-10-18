"""Actual pinned Docling-Slim vs MarkItDown, offline synthetic SEC 8-K fixtures."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sec_docling_offline_comparison_shadow import compare_html, MAX_SIZE

HTML = b"""<!DOCTYPE html><html><head><title>SEC Exhibit</title></head><body>
<h1>Form 8-K</h1><p>Accession: 0000000000-26-000042</p>
<p>Filed date: 2026-10-16</p><p>Revenue: 12,345,678 USD</p>
<table><tr><th>Metric</th><th>USD</th></tr>
<tr><td>Cash</td><td>9,876,543</td></tr></table>
</body></html>"""
TOKENS = ["0000000000-26-000042", "2026-10-16", "12,345,678", "9,876,543"]

class TestOfflineDoclingComparison(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "filing.html"
        self.path.write_bytes(HTML)
        self.sha = hashlib.sha256(HTML).hexdigest()

    def go(self, *, path=None, digest=None, expected=None):
        return compare_html(
            path or self.path,
            source_sha256=self.sha if digest is None else digest,
            required_literals=TOKENS if expected is None else expected)

    def test_real_two_parsers_preserve_identical_sec_literals(self):
        x = self.go()
        self.assertEqual(x["status"],"COMPARABLE_LOCAL_HTML_RESEARCH_ONLY")
        self.assertEqual(x["docling_version"],"2.140.0")
        self.assertEqual(x["markitdown_version"],"0.1.8")
        self.assertEqual(x["source_sha256"],self.sha)
        self.assertEqual(x["required_literal_count"],4)
        self.assertTrue(x["both_preserved_required_literals"])
        self.assertNotEqual(x["docling_markdown_sha256"],"")
        self.assertNotEqual(x["markitdown_markdown_sha256"],"")
        for k in ("official_sec_document_verified", "asof_acceptance_verified",
                  "market_data_licensed","price_pass","mc_pass",
                  "r92_authority","may_notify_user"):
            self.assertIs(x[k], False, k)
        self.assertEqual(x["execution"],"NONE")
        self.assertEqual(x["real_money"],"NO-GO")

    def test_digest_tamper_rejected(self):
        with self.assertRaises(ValueError):
            self.go(digest="0"*64)

    def test_missing_expected_literal_rejected(self):
        with self.assertRaises(ValueError):
            self.go(expected=["UNVERIFIED-INVENTED-NUMBER"])

    def test_unsafe_literal_set_rejected(self):
        for bad in ([],["dupe","dupe"],["xx"],["abc\nxyz"],["z"*101]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.go(expected=bad)

    def test_extension_and_symlink_rejected(self):
        p=Path(self.temp.name)/"secret.txt"
        p.write_bytes(HTML)
        with self.assertRaises(ValueError):
            self.go(path=p)
        symlink=Path(self.temp.name)/"alias.html"
        symlink.symlink_to(self.path)
        with self.assertRaises(ValueError):
            self.go(path=symlink)

    def test_changed_bytes_fail_even_with_valid_old_sha(self):
        self.path.write_bytes(HTML+b"<p>injection</p>")
        with self.assertRaises(ValueError):
            self.go()

    def test_oversize_rejected_before_parser(self):
        self.path.write_bytes(b"<p>"+b"0"*(MAX_SIZE+1)+b"</p>")
        with self.assertRaises(ValueError):
            self.go(digest=hashlib.sha256(self.path.read_bytes()).hexdigest())

if __name__=="__main__":
    unittest.main()
