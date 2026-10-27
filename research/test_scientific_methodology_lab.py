"""Adversarial evidence tests: Turing/Popper/Gauss/Lamport/Thorp/Taleb inspired."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import scientific_methodology_lab as lab

class TestIndependentLab(unittest.TestCase):
    def test_pit_valid(self):
        a=[{"date":"2026-10-26","open":10,"high":12,"low":9,"close":11}]
        self.assertEqual(len(lab.point_in_time_bars(a,"2026-10-26")),1)
    def test_pit_future_rejected(self):
        with self.assertRaisesRegex(lab.EvidenceReject,"FUTURE"):
            lab.point_in_time_bars([{"date":"2026-10-27","open":10,"high":12,"low":9,"close":11}],"2026-10-26")
    def test_pit_duplicate_rejected(self):
        x={"date":"2026-10-26","open":10,"high":12,"low":9,"close":11}
        with self.assertRaisesRegex(lab.EvidenceReject,"DUPLICATE"):
            lab.point_in_time_bars([x,x],"2026-10-26")
    def test_pit_missing_asof(self):
        with self.assertRaisesRegex(lab.EvidenceReject,"NO_EXACT_ASOF"):
            lab.point_in_time_bars([{"date":"2026-10-25","open":10,"high":11,"low":9,"close":10}],"2026-10-26")
    def test_pit_bad_ohlc(self):
        with self.assertRaises(lab.EvidenceReject):
            lab.point_in_time_bars([{"date":"2026-10-26","open":13,"high":12,"low":9,"close":11}],"2026-10-26")
    def test_purged_overlap_and_embargo(self):
        # spans based on session indices, where held-out label is 10-13.
        intervals=[(0,3),(7,9),(9,11),(10,13),(14,14),(15,16),(19,20)]
        self.assertEqual(lab.purged_train_indices(intervals,[3],2),(0,1,6))
    def test_purged_no_embargo(self):
        intervals=[(0,1),(2,4),(4,5),(6,7)]
        self.assertEqual(lab.purged_train_indices(intervals,[1]),(0,3))
    def test_purged_invalid_interval(self):
        with self.assertRaises(lab.EvidenceReject):
            lab.purged_train_indices([(4,3),(5,6)],[1])
    def test_purged_bad_test(self):
        with self.assertRaises(lab.EvidenceReject):
            lab.purged_train_indices([(0,1)],[3])
    def test_next_open_no_same_bar(self):
        with self.assertRaisesRegex(lab.EvidenceReject,"LOOKAHEAD"):
            lab.next_open_net_return(signal_index=1,entry_index=1,exit_index=2,entry_open=10,exit_open=11,entry_bps=5,exit_bps=5)
    def test_net_fee_reduces_gross(self):
        gross=lab.next_open_net_return(signal_index=0,entry_index=1,exit_index=2,entry_open=100,exit_open=110,entry_bps=0,exit_bps=0)
        net=lab.next_open_net_return(signal_index=0,entry_index=1,exit_index=2,entry_open=100,exit_open=110,entry_bps=15,exit_bps=15)
        self.assertAlmostEqual(gross,0.1)
        self.assertLess(net,gross)
    def test_gapped_stop(self):
        outcome,fill=lab.conservative_barrier_hit(entry=100,stop=95,target=110,open_=90,high=93,low=88,close=92)
        self.assertEqual((outcome,fill),("GAP_STOP",90))
    def test_double_touch_is_stop_first(self):
        outcome,fill=lab.conservative_barrier_hit(entry=100,stop=95,target=110,open_=100,high=111,low=94,close=101)
        self.assertEqual((outcome,fill),("AMBIGUOUS_STOP_FIRST",95))
    def test_target_only(self):
        self.assertEqual(lab.conservative_barrier_hit(entry=100,stop=95,target=110,open_=100,high=113,low=99,close=110),("TARGET",110))
    def test_invalid_geometry(self):
        with self.assertRaises(lab.EvidenceReject):
            lab.conservative_barrier_hit(entry=100,stop=101,target=110,open_=100,high=111,low=90,close=100)
    def test_max_drawdown(self):
        self.assertAlmostEqual(lab.max_drawdown([100,120,90,100]),-0.25)
    def test_es_tail(self):
        self.assertAlmostEqual(lab.historical_expected_shortfall([-0.4,-0.3,-0.2,0.1,0.2],0.4),-0.35)
    def test_uncertainty(self):
        self.assertEqual(lab.uncertainty_witness([0.1,0.2,0.3])["n"],3)
    def test_digest_order_independent(self):
        self.assertEqual(lab.canonical_digest({"a":1,"b":2}),lab.canonical_digest({"b":2,"a":1}))
    def test_dangerous_nan_rejected(self):
        with self.assertRaises(lab.EvidenceReject):
            lab.historical_expected_shortfall([0,float("nan")])
if __name__=="__main__":unittest.main()
