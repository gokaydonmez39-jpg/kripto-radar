from unittest import TestCase

import test_xray406_witness_acceptance as fixtures
from xray406_witness_acceptance import GUARD, Rejected
from xray406_witness_race_readback import OVERLAY, classify


class RaceReadbackTests(TestCase):
    def setUp(self):
        f = self.f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        self.addCleanup(f.doCleanups)
        f.setUp()

    def evaluate(self, tip, other=None, outcome="confirmed_non_fast_forward"):
        f = self.f
        verdict = classify(f.root, f.base, f.head, tip, other or tip, outcome)
        self.assertFalse(verdict.retry_allowed)
        self.assertFalse(verdict.first_visibility_proven)
        return verdict.status

    def advance(self, ref, path, value):
        f = self.f
        f.run_git("checkout", "--quiet", "--detach", ref)
        f.write(path, value)
        return f.commit("concurrent fixture commit")

    def test_exact_overlay_race_protects_witness_and_never_retries(self):
        tip = self.advance(self.f.base, OVERLAY, {"research_only": True})
        self.assertEqual(self.evaluate(tip), "HOLD_OVERLAY_ADVANCED_WITNESS_INTACT")

    def test_overlay_with_unknown_ack_is_not_confirmed_rejection(self):
        tip = self.advance(self.f.base, OVERLAY, {"research_only": True})
        self.assertEqual(self.evaluate(tip, outcome="unknown"),
                         "HOLD_TARGET_ADVANCED_NO_ACCEPTANCE")

    def test_witness_concurrent_write_is_distinct(self):
        tip = self.advance(self.f.base, GUARD, {"concurrent": True})
        self.assertEqual(self.evaluate(tip), "HOLD_CONCURRENT_WITNESS_CHANGE")

    def test_drifting_reads_are_unknown(self):
        self.assertEqual(self.evaluate(self.f.base, self.f.head),
                         "HOLD_REF_MOVED_DURING_READBACK")

    def test_unchanged_main_is_no_acceptance(self):
        self.assertEqual(self.evaluate(self.f.base), "HOLD_TARGET_AT_BASE_NO_ACCEPTANCE")

    def test_reachable_candidate_does_not_establish_first_visibility(self):
        tip = self.advance(self.f.head, OVERLAY, {"research_only": True})
        self.assertEqual(self.evaluate(tip, outcome="unknown"),
                         "CANDIDATE_REACHABLE_VISIBILITY_UNPROVEN")
        self.assertEqual(self.evaluate(tip), "HOLD_REJECTION_AND_CANDIDATE_REACHABLE")

    def test_candidate_then_subsequent_witness_change(self):
        tip = self.advance(self.f.head, GUARD, {"concurrent": True})
        self.assertEqual(self.evaluate(tip, outcome="unknown"),
                         "HOLD_CANDIDATE_REACHABLE_WITNESS_PATHS_MOVED")

    def test_wrong_object_and_outcome_rejected(self):
        with self.assertRaises(Rejected):
            self.evaluate("f"*40)
        with self.assertRaisesRegex(Rejected, "OUTCOME_NOT_IN_SCOPE"):
            self.evaluate(self.f.base, outcome="success")
