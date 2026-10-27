"""Isolated GS Quant v2.2.2 purely local statistical cross-check.
No GS Marquee sign-in, endpoints, requests, account, market data, signals or broker.
"""
import math
from statistics import mean, stdev
import unittest
import pandas as pd
from gs_quant.timeseries.statistics import std, mean as gs_mean

class GSQuantNumericalParity(unittest.TestCase):
    def test_three_point_std_and_mean(self):
        data=pd.Series([1.0, 2.0, 3.0],index=pd.date_range("2026-10-20",periods=3))
        self.assertAlmostEqual(float(std(data,3).iloc[-1]),stdev(data.tolist()),places=8)
        self.assertAlmostEqual(float(gs_mean(data,3).iloc[-1]),mean(data.tolist()),places=8)
    def test_constant_series_std_zero(self):
        data=pd.Series([100.,100.,100.,100.],index=pd.date_range("2026-10-20",periods=4))
        self.assertAlmostEqual(float(std(data,4).iloc[-1]),0.0,places=8)
    def test_shock_increases_volatility(self):
        a=pd.Series([1.,1.01,1.02,1.03],index=pd.date_range("2026-10-20",periods=4))
        b=pd.Series([1.,1.01,1.02,2.03],index=a.index)
        self.assertGreater(float(std(b,4).iloc[-1]),float(std(a,4).iloc[-1]))
    def test_no_marquee_credentials_required_for_local_series(self):
        # Any accidental remote session/data call should cause a fail-closed CI failure;
        # the test job has no secrets and no institutional API client id.
        data=pd.Series([2.,3.,4.],index=pd.date_range("2026-10-20",periods=3))
        self.assertTrue(math.isfinite(float(std(data,3).iloc[-1])))
if __name__=="__main__":unittest.main()
