"""A37 synthetic negative controls; never load real securities or credentials."""
from __future__ import annotations

import copy
import unittest
from a37_anchored_walkforward_shadow import (
    SCHEMA, admission, strictly_synthetic_fixture,
)


class A37WalkForward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = strictly_synthetic_fixture()

    def case(self):
        return copy.deepcopy(self.base)

    def test_three_anchored_folds_exact_15_label_purge(self):
        r = admission(self.case())
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["holdout_coverage_count"], 120)
        self.assertEqual([f["test_start_index"] for f in r["folds"]], [500, 540, 580])
        self.assertEqual([f["usable_training_rows"] for f in r["folds"]], [485, 525, 565])
        self.assertEqual([f["purged_training_rows"] for f in r["folds"]], [15, 15, 15])
        self.assertTrue(all(f["test_rows"] == 40 for f in r["folds"]))
        self.assertFalse(r["out_of_sample_alpha_proven"])
        self.assertFalse(r["may_execute_order"])

    def test_future_data_does_not_change_previous_scaler(self):
        rows = self.case()
        before = admission(rows)
        rows[520]["feature"] = 1_000_000.0  # First fold HOLDOUT, second fold TRAIN after label maturity.
        after = admission(rows)
        self.assertEqual(before["folds"][0]["training_scaler_sha256"],
                         after["folds"][0]["training_scaler_sha256"])
        self.assertNotEqual(before["folds"][1]["training_scaler_sha256"],
                            after["folds"][1]["training_scaler_sha256"])

    def test_future_first_seen_denied(self):
        rows = self.case()
        rows[510]["first_known_at_utc"] = "2029-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "PIT_LOOKAHEAD"):
            admission(rows)

    def test_cross_issuer_interleaving_denied(self):
        rows = self.case()
        rows[150]["issuer_id"] = "OTHER_ISSUER"
        with self.assertRaisesRegex(ValueError, "CROSS_ISSUER_SERIES_MIXING"):
            admission(rows)

    def test_decision_cutoff_stale_or_future_day_denied(self):
        rows = self.case()
        rows[300]["decision_cutoff_utc"] = "2025-11-01T23:00:00Z"
        with self.assertRaisesRegex(ValueError, "DECISION_CUTOFF_SESSION_DRIFT"):
            admission(rows)

    def test_bad_label_horizon_denied(self):
        rows = self.case()
        rows[200]["label_end_index"] = 201
        with self.assertRaisesRegex(ValueError, "LABEL_HORIZON_UNDERSPECIFIED"):
            admission(rows)

    def test_invalid_cutoff_and_feature_provenance_denied(self):
        rows = self.case()
        rows[200]["first_known_at_utc"] = rows[200]["session"] + "T23:30:00Z"
        with self.assertRaisesRegex(ValueError, "PIT_LOOKAHEAD"):
            admission(rows)

    def test_incomplete_trailing_holdout_denied(self):
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_UNEVALUATED_TAIL"):
            admission(strictly_synthetic_fixture(659))

    def test_short_sample_denied(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_FOLD_HISTORY"):
            admission(self.case()[:500])

    def test_no_looser_horizon_or_fewer_folds(self):
        for overrides in ({"horizon": 14}, {"min_folds": 2},
                          {"test_size": 15}, {"train_min": True}):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, "PARAMETER_CONTRACT"):
                    admission(self.case(), **overrides)

    def test_nonfinite_feature_denied(self):
        rows = self.case()
        rows[510]["feature"] = float("inf")
        with self.assertRaisesRegex(ValueError, "NONFINITE_FEATURE"):
            admission(rows)

    def test_wrong_source_or_rights_denied(self):
        for key, val, reason in (("venue", "SIP", "SOURCE_CONTRACT_DRIFT"),
                                  ("basis", "SPLIT", "SOURCE_CONTRACT_DRIFT"),
                                  ("data_rights_attested", False, "RIGHTS_NOT_ATTESTED")):
            with self.subTest(key=key):
                rows = self.case()
                rows[1][key] = val
                with self.assertRaisesRegex(ValueError, reason):
                    admission(rows)

    def test_deterministic_no_input_mutation(self):
        rows = self.case()
        frozen = copy.deepcopy(rows)
        a, b = admission(rows), admission(rows)
        self.assertEqual(a, b)
        self.assertEqual(rows, frozen)
        self.assertFalse(a["real_provider_provenance_verified"])
        self.assertFalse(a["official_xnas_calendar_verified"])


if __name__ == "__main__":
    unittest.main()
