import unittest
from datetime import date
from confidence_lab import evaluate, purged_split, wilson, concentration

def row(i, p=.6, outcome="TARGET", gross=2., cost=.05):
    return dict(key=f"synthetic-{i}", start=i*20, end=i*20+15,
                available=i*20, probability=p, outcome=outcome,
                gross_r=gross, cost_r=cost, quality="NATIVE")

class ConfidenceLabTest(unittest.TestCase):
    def test_binary_calibration_and_net_r(self):
        a=[row(1), row(2,.2,"STOP",-1)]
        r=evaluate(a, baseline_probability=.5)
        self.assertAlmostEqual(r["brier"],(.16+.04)/2)
        self.assertAlmostEqual(r["net_mean_r"],.45)
        self.assertEqual(r["decision_influence"],"NO_GO")
    def test_timeout_is_not_binary_loss(self):
        r=evaluate([row(1),row(2,.3,"TIMEOUT",.2)],baseline_probability=.5)
        self.assertEqual(r["binary_n"],2)
        self.assertAlmostEqual(r["brier"],(.16+.09)/2)
        self.assertAlmostEqual(r["net_mean_r"],1.05)
    def test_censor_not_zero_return(self):
        r=evaluate([row(1),row(2,None,"CORPORATE_ACTION",None,None)],baseline_probability=.5)
        self.assertEqual(r["censored"],1)
        self.assertEqual(r["resolved_n"],1)
        self.assertAlmostEqual(r["net_mean_r"],1.95)
    def test_ambiguous_excluded(self):
        r=evaluate([row(1,None,"AMBIGUOUS",None,None)],baseline_probability=.5)
        self.assertIsNone(r["net_mean_r"])
        self.assertIsNone(r["brier"])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): evaluate([row(1),row(1)],baseline_probability=.5)
    def test_future_feature_rejected(self):
        x=row(1);x["available"]=x["start"]+1
        with self.assertRaises(ValueError): evaluate([x],baseline_probability=.5)
    def test_nan_and_bool_rejected(self):
        for p in [float("nan"),True,-.1,1.1]:
            with self.subTest(p=p),self.assertRaises(ValueError): evaluate([row(1,p)],baseline_probability=.5)
    def test_bad_outcome_rejected(self):
        for x in [row(1,.5,"MYSTERY",0),row(1,.5,"TARGET",-1),row(1,.5,"STOP",2),row(1,.5,"TARGET",2,-1)]:
            with self.subTest(x=x),self.assertRaises(ValueError): evaluate([x],baseline_probability=.5)
    def test_close_only_cannot_claim_bracket(self):
        x=row(1);x["quality"]="CLOSE_ONLY"
        with self.assertRaises(ValueError):evaluate([x],baseline_probability=.5)
    def test_small_sample_and_overlap(self):
        a=row(1);b=row(2);b.update(start=21,end=36,available=21)
        r=evaluate([a,b],baseline_probability=.5)
        self.assertEqual(r["overlap_clusters"],1)
        self.assertEqual(r["statistical_status"],"HOLD_SMALL_OR_DEPENDENT_SAMPLE")
    def test_purge_embargo(self):
        a=[row(i) for i in range(1,6)]
        train,test=purged_split(a,test_start=80,test_end=100,embargo=15)
        self.assertEqual([x["start"] for x in train],[20,40])
        self.assertEqual([x["start"] for x in test],[80,100])
    def test_wilson_known(self):
        lo,hi=wilson(5,10)
        self.assertAlmostEqual(lo,.236593,places=5)
        self.assertAlmostEqual(hi,.763407,places=5)
        self.assertIsNone(wilson(0,0))
    def test_concentration(self):
        r=concentration({"a":[1,2,3],"b":[2,4,6],"c":[3,2,1]})
        self.assertAlmostEqual(r["max_abs_correlation"],1)
        self.assertEqual(r["pairs"],3)
    def test_constant_or_misaligned(self):
        for x in [{"a":[1,1,1],"b":[1,2,3]},{"a":[1,2,3],"b":[1,2]}]:
            with self.assertRaises(ValueError):concentration(x)
    def test_invalid_baseline(self):
        with self.assertRaises(ValueError):evaluate([row(1)],baseline_probability=float("inf"))
    def test_reject_empty_and_bad_horizon(self):
        with self.assertRaises(ValueError):evaluate([],baseline_probability=.5)
        x=row(1);x["end"]=x["start"]+16
        with self.assertRaises(ValueError):evaluate([x],baseline_probability=.5)
if __name__=="__main__": unittest.main()
