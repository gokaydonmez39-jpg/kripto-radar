#!/usr/bin/env python3
"""Real byte-level hash and record controls; all input data are synthetic."""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_numeric_source_bytes_shadow as guard


def fixture():
    row = {"id": "OBS1", "symbol": "AAPL",
           "field": "close_usd", "value": "125.25",
           "unit": "USD", "asof_et": "2026-10-16"}
    src = {"schema": guard.SCHEMA, "asof_et": "2026-10-16",
           "observations": [row]}
    data = json.dumps(src, sort_keys=True, separators=(",", ":")).encode()
    sha = guard.git_sha(data)
    claim = dict(row, source_blob_sha=sha)
    claims = {"schema": guard.base.SCHEMA, "asof_et": src["asof_et"],
              "execution": "NONE", "real_money": "NO-GO",
              "unknown_never_pass": True, "observations": [claim],
              "claims": [{**claim, "id": "C1", "observation_id": "OBS1"}]}
    return claims, data, sha


class SourceByteEvidenceTests(unittest.TestCase):
    def test_real_bytes_match_sha_and_full_row_no_al(self):
        claims, src, sha = fixture()
        r = guard.inspect(claims, src, sha)
        self.assertEqual(r["status"], "SOURCE_FILE_BYTES_AND_CLAIMS_MATCH_UNATTESTED")
        self.assertTrue(r["source_bytes_match_independent_operator_pin"])
        self.assertEqual(r["record_count"], 1)
        self.assertEqual(r["bound_count"], 1)
        self.assertEqual(r["source_git_blob_sha"], sha)
        for field in (
            "operator_pin_origin_independently_authenticated",
            "publisher_signed_data_verified", "market_truth_verified",
            "vendor_entitlement_verified", "exchange_rth_complete_verified",
            "can_create_PRIMARY", "can_create_PRICE_PASS",
            "can_create_HISTORY_PASS", "can_create_MC_PRIMARY",
            "can_register_R92", "can_send_notification", "alpha_authority",
            "vendor_raw_data_exported",
        ):
            self.assertIs(r[field], False, field)
        self.assertNotIn("125.25", str(r))
        self.assertNotIn("AAPL", str(r))

    def test_changed_byte_rejected_at_sha_boundary(self):
        claims, src, sha = fixture()
        changed = src.replace(b"125.25", b"125.26")
        with self.assertRaisesRegex(ValueError, "BYTE_HASH_MISMATCH"):
            guard.inspect(claims, changed, sha)

    def test_stored_observation_tampering_even_with_new_valid_sha(self):
        claims, src, _ = fixture()
        obj = json.loads(src)
        obj["observations"][0]["value"] = "125.26"
        changed = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        newsha = guard.git_sha(changed)
        claims["observations"][0]["source_blob_sha"] = newsha
        claims["claims"][0]["source_blob_sha"] = newsha
        with self.assertRaisesRegex(ValueError, "OBSERVATION_BYTES_NOT_EQUAL_SOURCE"):
            guard.inspect(claims, changed, newsha)

    def test_forged_claim_price_reports_unsupported(self):
        claims, src, sha = fixture()
        claims["claims"][0]["value"] = "135.25"
        r = guard.inspect(claims, src, sha)
        self.assertEqual(r["status"], "DATA_BLOCKED_UNSUPPORTED_NUMERIC_CLAIMS")
        self.assertEqual(r["reason_counts"], {"NUMERIC_VALUE_NOT_OBSERVED": 1})
        self.assertFalse(r["can_register_R92"])

    def test_missing_claim_evidence_never_upgrades(self):
        claims, src, sha = fixture()
        claims["claims"][0]["observation_id"] = "MISSING"
        r = guard.inspect(claims, src, sha)
        self.assertEqual(r["status"], "DATA_BLOCKED_UNSUPPORTED_NUMERIC_CLAIMS")
        self.assertEqual(r["reason_counts"], {"NO_REFERENCED_OBSERVATION": 1})

    def test_source_sha_claim_mismatch(self):
        claims, src, sha = fixture()
        claims["observations"][0]["source_blob_sha"] = "a" * 40
        with self.assertRaisesRegex(ValueError, "CLAIMED_SOURCE_HASH_MISMATCH"):
            guard.inspect(claims, src, sha)

    def test_wrong_external_pin_not_accepted(self):
        claims, src, sha = fixture()
        for invalid in ("a"*39, "bad", "A"*40):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,"PIN_UNFORMED"):
                guard.inspect(claims, src, invalid)
        with self.assertRaisesRegex(ValueError, "BYTE_HASH_MISMATCH"):
            guard.inspect(claims, src, "b"*40)

    def test_claimed_missing_record_cannot_fabricate(self):
        claims, src, sha = fixture()
        claims["observations"][0]["id"] = "UNSEEN"
        claims["claims"][0]["observation_id"] = "UNSEEN"
        with self.assertRaisesRegex(ValueError, "OBSERVATION_ID_NOT_IN_SOURCE"):
            guard.inspect(claims, src, sha)

    def test_extra_source_record_not_silently_dropped(self):
        claims, src, _ = fixture()
        obj = json.loads(src)
        obj["observations"].append({**obj["observations"][0], "id":"OBS2"})
        data = json.dumps(obj,sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "SOURCE_SCOPE_COUNT"):
            guard.inspect(claims, data, guard.git_sha(data))

    def test_source_duplicate_records_not_accepted(self):
        claims, src, _ = fixture()
        obj = json.loads(src)
        obj["observations"].append(dict(obj["observations"][0]))
        data=json.dumps(obj,sort_keys=True).encode()
        claims["observations"].append(dict(claims["observations"][0]))
        sha=guard.git_sha(data)
        for obs in claims["observations"]: obs["source_blob_sha"]=sha
        claims["claims"][0]["source_blob_sha"]=sha
        with self.assertRaises(ValueError):
            guard.inspect(claims,data,sha)

    def test_future_date_and_unit_mismatch(self):
        for badname,bad in [("asof_et","2026-10-17"),("unit","shares"),("symbol","MSFT")]:
            claims,src,sha=fixture()
            claims["observations"][0][badname]=bad
            with self.subTest(badname=badname),self.assertRaises(ValueError):
                guard.inspect(claims,src,sha)

    def test_source_duplicate_json_property_fails(self):
        claims,_,_=fixture()
        corrupt=b'{"schema":"X","schema":"X","asof_et":"2026-10-16","observations":[]}'
        with self.assertRaisesRegex(ValueError,"INVALID_SOURCE_JSON"):
            guard.inspect(claims,corrupt,guard.git_sha(corrupt))

    def test_source_strict_row_no_extra_fields(self):
        claims,src,_=fixture()
        obj=json.loads(src)
        obj["observations"][0]["injected"]="not an authorized row"
        data=json.dumps(obj,sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError,"SOURCE_ROW_SCHEMA"):
            guard.inspect(claims,data,guard.git_sha(data))

    def test_nonfinite_json_and_garbage_fails_closed(self):
        claims,_,_=fixture()
        for data in (b'{', b'{"a":NaN}', b'{"a":Infinity}', b'\xff', b''):
            with self.subTest(data=data),self.assertRaises(ValueError):
                guard.inspect(claims,data,guard.git_sha(data))

    def test_private_path_rejects_public_repo_and_symlink(self):
        with self.assertRaisesRegex(ValueError,"PUBLIC_REPOSITORY_PATH_FORBIDDEN"):
            guard.private_bytes(ROOT/"research_numeric_provenance_shadow.py")
        with tempfile.TemporaryDirectory() as t:
            parent=pathlib.Path(t)
            actual=parent/"data.json"
            actual.write_text('{"test":true}')
            symlink=parent/"symlink.json"
            symlink.symlink_to(actual)
            with self.assertRaisesRegex(ValueError,"PRIVATE_INPUT_UNAVAILABLE"):
                guard.private_bytes(symlink)

    def test_cli_private_end_to_end_reports_only_aggregates(self):
        claims,src,sha=fixture()
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            srcfile=root/"input.json"
            cfile=root/"claims.json"
            report=root/"report.json"
            srcfile.write_bytes(src)
            cfile.write_text(json.dumps(claims))
            self.assertEqual(guard.private_bytes(srcfile),src)
            result=guard.inspect(guard.strict_json(guard.private_bytes(cfile)),
                                 guard.private_bytes(srcfile),sha)
            report.write_text(json.dumps(result,sort_keys=True))
            recorded=json.loads(report.read_text())
            self.assertEqual(recorded["status"],"SOURCE_FILE_BYTES_AND_CLAIMS_MATCH_UNATTESTED")
            self.assertNotIn("AAPL",report.read_text())
            self.assertNotIn("125.25",report.read_text())


if __name__ == "__main__":
    unittest.main()
