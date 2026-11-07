"""Offline standalone wheel receipt regression tests."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from strong4_wheelhouse_receipt import witness

class WheelTests(unittest.TestCase):
    def folder(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return Path(self.tmp.name)
    def test_records_real_sha_and_closed_claims(self):
        p=self.folder();(p/"pydantic-2.14.3-py3-none-any.whl").write_bytes(b"synthetic fixture bytes")
        r=witness(p,"pydantic")
        self.assertEqual(r["observed_binary_wheels"],1)
        self.assertEqual(r["observed_packages"][0]["sha256"],hashlib.sha256(b"synthetic fixture bytes").hexdigest())
        self.assertFalse(r["hash_lock_committed"])
        self.assertFalse(r["production_authorized"])
    def test_requires_exact_direct_version(self):
        p=self.folder();(p/"vectorbt-1.1.9-py3-none-any.whl").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError,"DIRECT_VERSION_MISSING"):witness(p,"vectorbt")
    def test_no_source_distribution(self):
        p=self.folder();(p/"quantstats-0.0.86.tar.gz").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError,"NON_BINARY_OR_SYMLINK_ARTIFACT"):witness(p,"quantstats")
    def test_empty_wheelhouse(self):
        p=self.folder()
        with self.assertRaisesRegex(ValueError,"WHEELHOUSE_EMPTY_OR_TOO_LARGE"):witness(p,"duckdb")
    def test_unknown_sdk(self):
        p=self.folder()
        with self.assertRaisesRegex(ValueError,"UNKNOWN_SDK_TARGET"):witness(p,"qbot")
    def test_symlink_rejected(self):
        p=self.folder();target=p/"duckdb-2.0.0-py3-none-any.whl";target.write_bytes(b"xyz")
        (p/"other-1.0.0-py3-none-any.whl").symlink_to(target)
        with self.assertRaisesRegex(ValueError,"NON_BINARY_OR_SYMLINK_ARTIFACT"):witness(p,"duckdb")
    def test_duplicate_name_version_rejected(self):
        p=self.folder()
        (p/"pydantic-2.14.3-py3-none-any.whl").write_bytes(b"x")
        (p/"pydantic-2.14.3-cp313-cp313-linux_x86_64.whl").write_bytes(b"y")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_DISTRIBUTION_VERSION"):witness(p,"pydantic")
if __name__=="__main__":unittest.main()
