#!/usr/bin/env python3
"""Source-bound research figure contract: synthetic evidence, no actual quotes."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_numeric_provenance_shadow as m


def fixture():
    base={"symbol":"AAPL","field":"close_usd","value":"123.4500",
          "unit":"USD","asof_et":"2026-10-16","source_blob_sha":"a"*40}
    return {"schema":m.SCHEMA,"asof_et":"2026-10-16",
            "execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,
            "observations":[{"id":"OBS1",**base}],
            "claims":[{"id":"CLAIM1","observation_id":"OBS1",**base}]}


class EvidenceGuardTests(unittest.TestCase):
    def test_exact_observation_stays_unattested(self):
        r=m.audit(fixture())
        self.assertEqual(r["status"],"STRUCTURALLY_BOUND_UNATTESTED")
        self.assertEqual(r["structurally_bound_count"],1)
        self.assertEqual(r["rejected_count"],0)
        for name in ("observation_source_bytes_verified","vendor_entitlement_verified",
                     "claim_market_truth_verified","can_create_PRIMARY",
                     "can_create_PRICE_PASS","can_create_HISTORY_PASS",
                     "can_create_MC_PRIMARY","can_register_R92",
                     "can_send_notification","alpha_authority","raw_vendor_data_exported"):
            self.assertIs(r[name],False,name)
        self.assertNotIn("123.4500",str(r))
        self.assertNotIn("AAPL",str(r))

    def test_decimal_equivalence_without_float_roundoff(self):
        d=fixture()
        d["claims"][0]["value"]="123.45"
        self.assertEqual(m.audit(d)["structurally_bound_count"],1)

    def test_numeric_hallucination_cannot_pass(self):
        d=fixture()
        d["claims"][0]["value"]="123.46"
        r=m.audit(d)
        self.assertEqual(r["status"],"UNSUPPORTED_NUMERIC_CLAIMS")
        self.assertEqual(r["reason_counts"],{"NUMERIC_VALUE_NOT_OBSERVED":1})

    def test_missing_evidence_rejected(self):
        d=fixture()
        d["claims"][0]["observation_id"]="NOWHERE"
        self.assertEqual(m.audit(d)["reason_counts"],{"NO_REFERENCED_OBSERVATION":1})

    def test_cross_symbol_wrong_field_or_sha_rejected(self):
        for field,bad in (("symbol","MSFT"),("field","market_cap_usd"),
                          ("source_blob_sha","b"*40)):
            d=fixture()
            d["claims"][0][field]=bad
            if field=="field":
                d["claims"][0]["unit"]="USD"
            with self.subTest(field=field):
                self.assertEqual(m.audit(d)["reason_counts"],
                                 {"EVIDENCE_IDENTITY_OR_FIELD_MISMATCH":1})

    def test_wrong_currency_not_accepted(self):
        d=fixture()
        d["claims"][0]["unit"]="EUR"
        with self.assertRaisesRegex(ValueError,"FIELD_UNIT_INVALID"):
            m.audit(d)

    def test_no_future_or_stale_asof(self):
        for field in ("claims","observations"):
            d=fixture()
            d[field][0]["asof_et"]="2026-10-19"
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"EPOCH_MISMATCH"):
                m.audit(d)

    def test_noncanonical_numerics_rejected(self):
        for v in (float("nan"), float("inf"), 123.45, True, None,
                  "1e3","1,000","-1","0","01.0","0.0","9999999999999999999999","0.0000000000001"):
            d=fixture()
            d["claims"][0]["value"]=v
            with self.subTest(v=str(v)),self.assertRaises(ValueError):
                m.audit(d)

    def test_duplicate_or_untyped_observations_not_ok(self):
        d=fixture()
        d["observations"].append(copy.deepcopy(d["observations"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OBSERVATION_ID"):
            m.audit(d)
        d=fixture()
        d["observations"].append(123)
        with self.assertRaisesRegex(ValueError,"ROW_NOT_OBJECT"):
            m.audit(d)

    def test_invalid_source_blob_rejected(self):
        d=fixture()
        d["observations"][0]["source_blob_sha"]="0"
        with self.assertRaisesRegex(ValueError,"SOURCE_SHA_INVALID"):
            m.audit(d)

    def test_no_trade_constraints(self):
        for field,bad in (("execution","LIVE"),("real_money","GO"),
                          ("unknown_never_pass",False)):
            d=fixture()
            d[field]=bad
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"NO_TRADE_POLICY_INVALID"):
                m.audit(d)

    def test_no_claim_does_not_invent_success(self):
        d=fixture()
        d["claims"]=[]
        self.assertEqual(m.audit(d)["status"],"UNSUPPORTED_NUMERIC_CLAIMS")

    def test_missing_claim_id_rejected(self):
        d=fixture()
        del d["claims"][0]["id"]
        with self.assertRaisesRegex(ValueError,"ROW_MISSING_ID"):
            m.audit(d)


if __name__=="__main__":
    unittest.main()
