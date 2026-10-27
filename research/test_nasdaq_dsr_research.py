"""Systematic falsification of multiple-trial backtest selection effects."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from honest_backtest import expected_max_sharpe, deflated_sharpe_ratio
from nasdaq_dsr_research import deflated_research_confidence, InsufficientEvidence

P=dict(sr=0.15,n_obs=750,skew=0.0,kurt=3.0,var_sr=0.01)

class TestBacktestHonesty(unittest.TestCase):
    def test_more_trials_cannot_raise_credibility(self):
        a=deflated_research_confidence(**P,n_trials=2)
        b=deflated_research_confidence(**P,n_trials=20)
        c=deflated_research_confidence(**P,n_trials=500)
        self.assertGreater(a["dsr"],b["dsr"])
        self.assertGreater(b["dsr"],c["dsr"])
        self.assertGreaterEqual(a["naive_psr"],a["dsr"])
        self.assertEqual(a["naive_psr"],c["naive_psr"])

    def test_benchmark_monotonic(self):
        a=expected_max_sharpe(2,0.01)
        b=expected_max_sharpe(200,0.01)
        self.assertGreater(b,a)

    def test_tail_effect_above_multiple_trial_benchmark(self):
        # Only assert direction when observed Sharpe is ABOVE the null benchmark.
        # Below the benchmark a larger variance pushes CDF back toward 0.5.
        strong={**P,"sr":0.35}
        self.assertGreater(strong["sr"],expected_max_sharpe(20,strong["var_sr"]))
        thin=deflated_research_confidence(**strong,n_trials=20)["dsr"]
        fat=deflated_research_confidence(**{**strong,"kurt":8},n_trials=20)["dsr"]
        self.assertLess(fat,thin)

    def test_tail_effect_below_benchmark_cannot_be_claimed_monotonic_penalty(self):
        weak={**P,"sr":0.02}
        self.assertLess(weak["sr"],expected_max_sharpe(20,weak["var_sr"]))
        thin=deflated_research_confidence(**weak,n_trials=20)["dsr"]
        fat=deflated_research_confidence(**{**weak,"kurt":8},n_trials=20)["dsr"]
        self.assertGreater(fat,thin)

    def test_tiny_sample_refused(self):
        with self.assertRaises(InsufficientEvidence):
            deflated_research_confidence(**{**P,"n_obs":2},n_trials=20)

    def test_fake_search_history_refused(self):
        for trials in (0,1,-3,2.1,True,None):
            with self.subTest(trials=trials):
                with self.assertRaises(InsufficientEvidence):
                    deflated_research_confidence(**P,n_trials=trials)

    def test_negative_or_missing_variance_refused(self):
        for bad in (0,-0.01,float("nan"),float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(InsufficientEvidence):
                    deflated_research_confidence(**{**P,"var_sr":bad},n_trials=20)

    def test_no_future_alpha_guarantee(self):
        result=deflated_research_confidence(**P,n_trials=100)
        self.assertEqual(result["status"],"RESEARCH_ONLY_NOT_PROFIT_FORECAST")
        self.assertTrue(0<=result["dsr"]<=1)

if __name__=="__main__":
    unittest.main()
