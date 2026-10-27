"""NASDAQ-only independent vectorbt numerical execution parity.
Synthetic observations ONLY. No real candidate data, no broker, no AL, no private files.
"""
import unittest
import math
import pandas as pd
import vectorbt as vbt

class TestVectorbtShadowAccounting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices=pd.Series([100.0,100.0,110.0,110.0,110.0],
                            index=pd.date_range("2026-10-20",periods=5),name="SYNTHETIC")
        # t0 signal discovered, first allowed synthetic order on t1 (not t0).
        cls.orders=pd.Series([0.0,1.0,0.0,0.0,-1.0],index=cls.prices.index)
    def _pf(self,fees):
        return vbt.Portfolio.from_orders(
            close=self.prices, size=self.orders, size_type="amount",
            direction="longonly", fees=fees, init_cash=1000.0,
            freq="1D"
        )
    def test_next_bar_not_same_signal_bar(self):
        pf=self._pf(0.0)
        orders=pf.orders.records_readable
        self.assertEqual(len(orders),2)
        self.assertNotEqual(str(orders.iloc[0]["Timestamp"])[:10],"2026-10-20")
        self.assertEqual(str(orders.iloc[0]["Timestamp"])[:10],"2026-10-21")
    def test_independent_no_fee_cash_profit_parity(self):
        pf=self._pf(0.)
        self.assertAlmostEqual(float(pf.total_profit()),10.0,places=7)
        self.assertAlmostEqual(float(pf.value().iloc[-1]),1010.0,places=7)
    def test_symmetric_fees_reduce_profit(self):
        pf=self._pf(.01)
        self.assertAlmostEqual(float(pf.total_profit()),7.9,places=6)
        self.assertAlmostEqual(float(pf.value().iloc[-1]),1007.9,places=6)
        self.assertLess(float(pf.total_profit()),float(self._pf(0.0).total_profit()))
    def test_flat_no_entry_yields_zero_pnl(self):
        flat=pd.Series([0.]*len(self.prices),index=self.prices.index)
        pf=vbt.Portfolio.from_orders(self.prices,size=flat,size_type="amount",
                                      init_cash=1000.0,freq="1D")
        self.assertEqual(int(pf.orders.count()),0)
        self.assertAlmostEqual(float(pf.total_profit()),0.)
    def test_no_real_trade_or_financial_forecast(self):
        self.assertEqual(self.prices.name,"SYNTHETIC")
        self.assertTrue(all(math.isfinite(float(x)) for x in self.prices))
if __name__=="__main__":unittest.main()
