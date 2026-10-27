"""Falsifiable NASDAQ-only science gates (Popper/Turing/Kahneman/Simons)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from nasdaq_hypothesis_preregistration import register,validate_stage,HypothesisBlocked

D="a"*64
M="b"*64
SPEC={"id":"NASDAQ_SYNTH_ONLY_H1","asof":"2026-10-28","dev_end":"2016-12-31",
      "holdback_start":"2017-01-01","holdback_end":"2018-12-31",
      "wf_start":"2019-01-01","wf_end":"2021-12-31",
      "final_holdout_start":"2022-01-01","universe_asof":"2016-12-30",
      "universe_source":"SYNTHETIC_POINT_IN_TIME_UNIVERSE","dataset_sha256":D,
      "model_sha256":M,"n_trials":12}
class TestHypothesisRegister(unittest.TestCase):
    def test_canonical_immutable_fingerprint(self):
        self.assertEqual(register(SPEC),register(dict(reversed(list(SPEC.items())))))
        self.assertEqual(len(register(SPEC)),64)
    def test_stage_order_one_shot(self):
        tag=register(SPEC)
        for name,history in [
            ("DEV",()),("HOLDBACK",("DEV",)),
            ("WALK_FORWARD",("DEV","HOLDBACK")),
            ("FINAL_HOLDOUT",("DEV","HOLDBACK","WALK_FORWARD"))]:
            self.assertIn("NO_AUTOPROMOTION",validate_stage(SPEC,tag,name,history))
    def test_wrong_order_reject(self):
        with self.assertRaisesRegex(HypothesisBlocked,"OUT_OF_ORDER"):
            validate_stage(SPEC,register(SPEC),"FINAL_HOLDOUT",("DEV",))
    def test_holdout_replay_reject(self):
        with self.assertRaises(HypothesisBlocked):
            validate_stage(SPEC,register(SPEC),"FINAL_HOLDOUT",
                           ("DEV","HOLDBACK","WALK_FORWARD","FINAL_HOLDOUT"))
    def test_mutated_trial_count_hash_blocks(self):
        new={**SPEC,"n_trials":300}
        with self.assertRaisesRegex(HypothesisBlocked,"MUTATED"):
            validate_stage(new,register(SPEC),"HOLDBACK",("DEV",))
    def test_mismatched_model_sha_blocks(self):
        with self.assertRaises(HypothesisBlocked):
            validate_stage({**SPEC,"model_sha256":"c"*64},register(SPEC),
                           "WALK_FORWARD",("DEV","HOLDBACK"))
    def test_current_issuer_list_cannot_rewrite_2010_history(self):
        with self.assertRaisesRegex(HypothesisBlocked,"FUTURE_CONSTITUENTS"):
            register({**SPEC,"universe_asof":"2026-10-28"})
    def test_unknown_search_trials_not_credible(self):
        for v in (0,-1,True,1.5,None):
            with self.subTest(v=v),self.assertRaises(HypothesisBlocked):
                register({**SPEC,"n_trials":v})
    def test_holdback_overlaps_rejected(self):
        with self.assertRaises(HypothesisBlocked):
            register({**SPEC,"holdback_start":"2016-12-30"})
    def test_future_final_holdout_rejected(self):
        with self.assertRaises(HypothesisBlocked):
            register({**SPEC,"final_holdout_start":"2027-01-01"})
    def test_unpinned_source_rejected(self):
        with self.assertRaises(HypothesisBlocked):
            register({**SPEC,"dataset_sha256":"not-pinned"})
    def test_missing_universe_source_rejected(self):
        with self.assertRaises(HypothesisBlocked):
            register({**SPEC,"universe_source":""})
if __name__=="__main__":unittest.main()
