"""Synthetic adversarial QA: no external data, no orders."""
import copy
import math
import unittest
from qlib_pit_readiness_shadow import (NO_AUTHORITY,check_fixture,synthetic_rows,
    purged_chronological_split,train_only_scaler,report)
class TestQlibAdmission(unittest.TestCase):
    def setUp(self):
        self.rows=synthetic_rows()
    def rejected(self,fn,reason):
        with self.assertRaisesRegex(ValueError,reason):fn()
    def test_contract_and_zero_authority(self):
        self.assertEqual(check_fixture(self.rows),520)
        r=report()
        self.assertEqual(r["result"],"SYNTHETIC_CONTRACT_ONLY_REAL_DATA_NO_GO")
        self.assertFalse(any(NO_AUTHORITY.values()))
        self.assertEqual(r["historical_xnas_sessions_verified"],0)
        self.assertEqual(r["external_requests"],0)
        self.assertFalse(r["qlib_executed"])
    def test_52_sessions_never_pass_500_gate(self):
        self.rejected(lambda:check_fixture(self.rows[:52]),"INSUFFICIENT_HISTORY")
    def test_cannot_lower_minimum(self):
        self.rejected(lambda:check_fixture(self.rows[:52],minimum=52),"MINIMUM_MUST_NOT_BE_WEAKENED")
    def test_future_first_seen_denied(self):
        self.rows[18]["first_known_at_utc"]="2025-01-02T00:00:00Z"
        self.rejected(lambda:check_fixture(self.rows),"PIT_LOOKAHEAD")
    def test_missing_first_seen_denied(self):
        del self.rows[30]["first_known_at_utc"]
        self.rejected(lambda:check_fixture(self.rows),"BAD_KNOWN_AT")
    def test_source_basis_mismatch_denied(self):
        self.rows[0]["basis"]="SPLIT_ADJUSTED"
        self.rejected(lambda:check_fixture(self.rows),"SOURCE_CONTRACT_DRIFT")
    def test_rights_missing_denied(self):
        self.rows[0]["data_rights_attested"]=False
        self.rejected(lambda:check_fixture(self.rows),"RIGHTS_NOT_ATTESTED")
    def test_duplicate_session_denied(self):
        self.rows[1]["session"]=self.rows[0]["session"]
        self.rejected(lambda:check_fixture(self.rows),"DUPLICATE_OR_BAD_SESSION")
    def test_unordered_session_denied(self):
        self.rows[2]["session"]="2022-12-31"
        self.rejected(lambda:check_fixture(self.rows),"SESSION_ORDER_DRIFT")
    def test_bad_values_denied(self):
        for v in (float("nan"),float("inf"),True):
            x=copy.deepcopy(self.rows);x[20]["feature"]=v
            self.rejected(lambda:check_fixture(x),"NONFINITE_FEATURE")
    def test_missing_identity_denied(self):
        self.rows[0]["issuer_id"]=""
        self.rejected(lambda:check_fixture(self.rows),"MISSING_ISSUER_IDENTITY")
    def test_15_session_purge(self):
        train,test=purged_chronological_split(self.rows)
        self.assertEqual((len(train),train[-1],len(test),test[0]),(385,384,120,400))
        self.assertTrue(all(self.rows[i]["label_end_index"]<400 for i in train))
    def test_short_label_denied(self):
        self.rows[10]["label_end_index"]=11
        self.rejected(lambda:purged_chronological_split(self.rows),"LABEL_HORIZON_UNDERSPECIFIED")
    def test_short_test_window_denied(self):
        self.rejected(lambda:purged_chronological_split(self.rows,train_end=510),"INSUFFICIENT_TEST_WINDOW")
    def test_holdout_outlier_does_not_leak_into_scaler(self):
        train,test=purged_chronological_split(self.rows)
        before=train_only_scaler(self.rows,train,test)
        self.rows[-1]["feature"]=1e8
        after=train_only_scaler(self.rows,train,test)
        self.assertEqual((before["train_mean"],before["train_std"]),
                         (after["train_mean"],after["train_std"]))
        self.assertNotEqual(before["test_transformed"][-1],after["test_transformed"][-1])
    def test_leaky_scaler_indices_denied(self):
        self.rejected(lambda:train_only_scaler(self.rows,(0,1,2),(2,3)),"UNSAFE_FEATURE_SPLIT")
    def test_constant_feature_denied(self):
        for row in self.rows: row["feature"]=2
        tr,te=purged_chronological_split(self.rows)
        self.rejected(lambda:train_only_scaler(self.rows,tr,te),"ZERO_VARIANCE")
    def test_naive_or_non_utc_timestamp_denied(self):
        self.rows[0]["first_known_at_utc"]="2023-01-01T10:00:00"
        self.rejected(lambda:check_fixture(self.rows),"NON_UTC_PROVENANCE")
if __name__=="__main__":unittest.main()
