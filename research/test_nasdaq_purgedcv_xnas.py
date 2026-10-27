"""NASDAQ-only isolated PIT/CPCV/XNAS contract tests.
No credentials, no live OHLCV, no trading, no signal creation, no notifications.
This is NOT a profitability test or a production strategy modification.
"""
import math
import unittest
from datetime import date
import pandas as pd
import exchange_calendars as xcals
from purgedcv import CombinatorialPurgedCV, make_t1

N = 360
HORIZON = 15

class TestNasdaqPurging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic index for event-position CV. Not asserted as a real XNAS calendar.
        cls.index = pd.bdate_range("2025-01-02", periods=N)
        cls.features = pd.DataFrame({"synthetic_feature": list(range(N))}, index=cls.index)
        cls.t1 = make_t1(cls.index, horizon=HORIZON)

    def _splits(self, embargo):
        cv = CombinatorialPurgedCV(
            n_groups=6, n_test_groups=2, embargo_pct=embargo,
            t1=self.t1, min_train_size=1,
        )
        return list(cv.split(self.features))

    def test_exact_fifteen_combinatorial_folds(self):
        folds = self._splits(0.0)
        self.assertEqual(len(folds), math.comb(6, 2))
        self.assertEqual(len(set(tuple(test) for _, test in folds)), 15)
        self.assertTrue(all(len(train) > 0 and len(test) == 120 for train,test in folds))

    def test_no_label_overlap_with_holdout(self):
        # Direct quadratic oracle (no use of purgedcv's internal vectorization).
        for train,test in self._splits(0.0):
            test_idx = [int(i) for i in test]
            for i in train:
                i = int(i)
                iend = min(i + HORIZON, N-1)
                self.assertFalse(any(
                    i <= min(j + HORIZON, N-1) and j <= iend
                    for j in test_idx
                ), msg=f"LEAKAGE train={i} test_groups={test_idx[0]}..")

    def test_independent_purge_oracle_exact_zero_embargo(self):
        for train,test in self._splits(0.0):
            test_indices = [int(j) for j in test]
            independent = tuple(i for i in range(N)
                if i not in set(test_indices) and
                not any(i <= min(j+HORIZON,N-1) and
                            j <= min(i+HORIZON,N-1)
                            for j in test_indices))
            self.assertEqual(tuple(int(z) for z in train),independent)

    def test_embargo_cannot_increase_train_set(self):
        pure=self._splits(0.0)
        embargo=self._splits(0.02)
        for (train0,test0),(train1,test1) in zip(pure,embargo):
            self.assertEqual(list(test0),list(test1))
            self.assertTrue(set(train1).issubset(set(train0)))
            self.assertLessEqual(len(train1),len(train0))

    def test_deterministic_replay(self):
        a=self._splits(0.02)
        b=self._splits(0.02)
        self.assertEqual([(tuple(x),tuple(y)) for x,y in a],
                         [(tuple(x),tuple(y)) for x,y in b])

    def test_misaligned_t1_after_downsample_must_fail(self):
        cv=CombinatorialPurgedCV(6,2,t1=self.t1)
        with self.assertRaises(ValueError):
            list(cv.split(self.features.iloc[::2]))

    def test_empty_train_must_fail_closed(self):
        t1=make_t1(self.features.index, horizon=300)
        cv=CombinatorialPurgedCV(6,2,t1=t1,min_train_size=340)
        with self.assertRaises(ValueError):
            list(cv.split(self.features))

    def test_cpcv_does_not_claim_returns_or_trade_fills(self):
        cv=CombinatorialPurgedCV(6,2,t1=self.t1)
        self.assertFalse(hasattr(cv,"place_order"))
        self.assertFalse(hasattr(cv,"execute_trade"))

class TestXNASCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xnas=xcals.get_calendar("XNAS")

    def test_thanksgiving_is_not_session(self):
        self.assertFalse(self.xnas.is_session(pd.Timestamp("2026-11-26")))

    def test_black_friday_2026_is_early_close(self):
        self.assertTrue(self.xnas.is_session(pd.Timestamp("2026-11-27")))
        close=self.xnas.session_close(pd.Timestamp("2026-11-27"))
        self.assertEqual(close.tz_convert("America/New_York").hour,13)

    def test_dst_regular_close_times(self):
        pre=self.xnas.session_close(pd.Timestamp("2026-03-06"))
        post=self.xnas.session_close(pd.Timestamp("2026-03-09"))
        self.assertEqual(pre.hour,21)
        self.assertEqual(post.hour,20)

    def test_one_session_after_friday_is_monday_not_saturday(self):
        sessions=self.xnas.sessions_in_range("2026-10-23","2026-10-26")
        self.assertEqual([str(x.date()) for x in sessions],["2026-10-23","2026-10-26"])

    def test_real_52_session_count(self):
        sessions=self.xnas.sessions_in_range("2026-08-14","2026-10-27")
        self.assertEqual(len(sessions),52)

if __name__ == "__main__":
    unittest.main()
