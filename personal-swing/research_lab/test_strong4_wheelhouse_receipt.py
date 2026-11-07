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
    @staticmethod
    def as_lock(target_sdk, observed):
        from strong4_wheelhouse_receipt import TARGETS
        payload={"schema":"XRAY_STRONG4_WHEELHOUSE_IMMUTABLE_LOCK_V1","targets":{}}
        for sdk,version in TARGETS.items():
            payload["targets"][sdk]={"version":version,"inventory_digest":"unverified", "wheels":[]}
        payload["targets"][target_sdk]={"version":TARGETS[target_sdk],
          "inventory_digest":observed["full_wheel_inventory_sha256"],
          "wheels":observed["observed_packages"]}
        return payload

    def test_valid_locked_wheelhouse(self):
        p=self.folder();(p/"pydantic-2.14.3-py3-none-any.whl").write_bytes(b"synthetic fixture bytes")
        observed=witness(p,"pydantic")
        got=witness(p,"pydantic",self.as_lock("pydantic",observed))
        self.assertTrue(got["hash_lock_committed"])
        self.assertTrue(got["hash_lock_verified"])
        self.assertFalse(got["production_authorized"])

    def test_tampered_binary_rejected(self):
        p=self.folder();wheel=p/"pydantic-2.14.3-py3-none-any.whl"
        wheel.write_bytes(b"original")
        lock=self.as_lock("pydantic",witness(p,"pydantic"))
        wheel.write_bytes(b"malicious-altered")
        with self.assertRaisesRegex(ValueError,"WHEELHOUSE_HASH_LOCK_MISMATCH"):
            witness(p,"pydantic",lock)

    def test_wrong_lock_schema_rejected(self):
        p=self.folder();(p/"pydantic-2.14.3-py3-none-any.whl").write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError,"LOCK_SCHEMA_INVALID"):
            witness(p,"pydantic",{"schema":"INVALID"})

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
