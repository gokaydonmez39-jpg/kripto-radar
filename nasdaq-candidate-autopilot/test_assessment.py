"""Offline positive/adversarial A44 tests; no requests, no third-party execution."""
import json
import unittest
from assessment import AdmissionError, build_assessment, github_repo_url, source_classification

RAW = b'{"receipt":"synthetic"}'
BASE = {"schema":"XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1",
        "source":"NASDAQ_RESEARCH_ONLY_NO_CRYPTO","automatic_promotion":False,
        "orders":False,"private_sheet_writes":False,"registry_sha256":"a"*64,
        "asof":"2026-11-02",
        "findings":[{"registry_id":2,"name":"Test","tier":"P1-ENGINEERING-TEST",
                     "url":"https://github.com/example/test",
                     "integration_status":"NOT_INTEGRATED"}]}


def metadata(path):
    if path == "/repos/example/test":
        return {"id": 42, "full_name": "example/test", "private":False,
                "archived":False,"disabled":False,"fork":False,
                "default_branch":"main","license":{"key":"mit"}}
    if path == "/repos/example/test/commits/main":
        return {"sha":"c"*40}
    raise AdmissionError("unexpected request")


class A44SafetyTests(unittest.TestCase):
    def test_valid_metadata_proves_only_reviewable_provenance(self):
        row = source_classification(BASE["findings"][0], fetcher=metadata)
        self.assertEqual(row["status"],"PROVENANCE_RECORDED_TEST_REQUIRED")
        self.assertEqual(row["source_head_sha"],"c"*40)
        self.assertFalse(row["license_approved"])
        self.assertFalse(row["run_upstream_code"])
        self.assertIn("BLOCKED",row["promotion"])

    def test_offline_no_probe_and_no_claim(self):
        outcome = build_assessment(BASE,RAW,network=False,fetcher=lambda p: 1/0)
        self.assertEqual(outcome["results"][0]["status"],"OFFLINE_UNPROBED")
        self.assertFalse(outcome["automatic_promotion"])

    def test_trusted_github_url_exactly(self):
        self.assertEqual(github_repo_url("https://github.com/Org/Repo"),
                         ("Org","Repo"))
        self.assertEqual(github_repo_url("https://github.com/Org/Repo/tree/main"),
                         ("Org","Repo"))

    def test_ssrf_and_private_url_red(self):
        for url in ("http://github.com/u/r","https://github.com.evil.test/u/r",
                    "https://127.0.0.1/a/b","file:///etc/passwd",
                    "https://github.com@evil.test/a/b",
                    "https://github.com:444/a/b",
                    "https://github.com/a/b?token=x",
                    "https://github.com/a/b#fragment"):
            self.assertIsNone(github_repo_url(url),url)

    def test_no_license_is_hold(self):
        def fetch(path):
            out = metadata(path)
            if path == "/repos/example/test":
                out["license"] = None
            return out
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                         ["status"],"HOLD_LICENSE_REVIEW")

    def test_gpl_is_hold_not_auto_installed(self):
        def fetch(path):
            out = metadata(path)
            if path == "/repos/example/test":
                out["license"] = {"key":"agpl-3.0"}
            return out
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                         ["status"],"HOLD_LICENSE_REVIEW")

    def test_forks_hold_parent_review(self):
        def fetch(path):
            out = metadata(path)
            if path == "/repos/example/test":
                out["fork"] = True
            return out
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                         ["status"],"HOLD_FORK_PARENT_NOT_VERIFIED")

    def test_archived_hold(self):
        def fetch(path):
            out = metadata(path)
            if path == "/repos/example/test":
                out["archived"] = True
            return out
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                         ["status"],"HOLD_ARCHIVED_DISABLED_OR_UNVERIFIED")

    def test_wrong_repo_or_private_is_unknown(self):
        for change in ({"full_name":"other/other"},{"private":True}):
            def fetch(path):
                out = metadata(path)
                if path == "/repos/example/test":
                    out.update(change)
                return out
            self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                             ["status"],"SOURCE_PROBE_UNKNOWN")

    def test_source_sha_bad_blocks_provenance(self):
        def fetch(path):
            out = metadata(path)
            if path.endswith("/commits/main"):
                return {"sha":"1234"}
            return out
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fetch)
                         ["status"],"SOURCE_PROBE_UNKNOWN")

    def test_network_failure_does_not_upgrade(self):
        def fail(path):
            raise AdmissionError("GITHUB_API_UNAVAILABLE_HTTPError")
        self.assertEqual(source_classification(BASE["findings"][0],fetcher=fail)
                         ["status"],"SOURCE_PROBE_UNKNOWN")

    def test_external_url_manual_provenance(self):
        row = dict(BASE["findings"][0],url="https://www.sec.gov/files")
        self.assertEqual(source_classification(row,fetcher=metadata)
                         ["status"],"NON_GITHUB_OR_MISSING_URL_MANUAL_PROVENANCE")

    def test_no_implicit_integration(self):
        bad = json.loads(json.dumps(BASE))
        bad["findings"][0]["integration_status"]="INTEGRATED"
        with self.assertRaises(AdmissionError):
            build_assessment(bad,RAW,network=True,fetcher=metadata)

    def test_duplicate_candidate_ban(self):
        bad = json.loads(json.dumps(BASE))
        bad["findings"] = bad["findings"]*2
        with self.assertRaises(AdmissionError):
            build_assessment(bad,RAW,network=True,fetcher=metadata)

    def test_max_seven_not_eight(self):
        bad = json.loads(json.dumps(BASE))
        bad["findings"] = [{**BASE["findings"][0],"registry_id":i}
                           for i in range(1,9)]
        with self.assertRaises(AdmissionError):
            build_assessment(bad,RAW,network=True,fetcher=metadata)

    def test_crypto_scope_rejected(self):
        bad = dict(BASE,source="CRYPTO")
        with self.assertRaises(AdmissionError):
            build_assessment(bad,RAW,network=False,fetcher=metadata)


if __name__=="__main__":
    unittest.main()
