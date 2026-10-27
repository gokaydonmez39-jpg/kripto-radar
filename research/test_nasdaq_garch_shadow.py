"""Independent isolated NASDAQ volatility magnitude tests. No market network and NO AL decisions."""
from __future__ import annotations
import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

EXTERNAL = Path(__file__).resolve().parents[1]/"external_garch_source"/"scripts"
if not (EXTERNAL/"garch_forecast.py").is_file():
    raise RuntimeError("MISSING_PINNED_GARCH_SOURCE")
sys.path.insert(0,str(EXTERNAL))
from garch_forecast import walkforward_garch, HONESTY_NOTE

def synthetic_equity_prices(n=555):
    if n < 3:
        raise ValueError("INSUFFICIENT_SYNTHETIC_POINTS")
    i=np.arange(n,dtype=float)
    # Deterministic varying returns, strictly positive, no random lookahead.
    daily=0.00015+0.009*np.sin(i*0.19)+0.004*np.cos(i*0.41)
    close=100*np.exp(np.cumsum(daily))
    return pd.DataFrame({"date":pd.bdate_range("2023-01-02",periods=n),
                         "close":close})

class TestNasdaqGarchRiskOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices=synthetic_equity_prices()
        cls.out=walkforward_garch(cls.prices,periods_per_year=252,
                                  min_train=500,refit_every=35)

    def test_produces_finite_positive_one_day_vol(self):
        p=self.out["fcast_vol"].dropna()
        self.assertGreater(len(p),20)
        self.assertTrue(np.isfinite(p).all())
        self.assertTrue((p>0).all())

    def test_nasdaq_252day_annualization_not_other_calendar(self):
        z=self.out.dropna(subset=["fcast_vol"]).iloc[-1]
        self.assertAlmostEqual(float(z["fcast_vol_ann"]),
                               float(z["fcast_vol"])*math.sqrt(252),places=10)

    def test_future_perturbation_cannot_rewrite_past_forecast(self):
        altered=self.prices.copy()
        altered.loc[altered.index[-12:],"close"]*=1.35
        forecast=walkforward_garch(altered,periods_per_year=252,
                                   min_train=500,refit_every=35)
        earlier=self.out.iloc[:-13]["fcast_vol"].dropna()
        other=forecast.iloc[:-13]["fcast_vol"].dropna()
        np.testing.assert_allclose(earlier.to_numpy(),other.to_numpy(),
                                   rtol=1e-8,atol=1e-8)

    def test_52_session_data_not_sufficient_for_500day_fit(self):
        with self.assertRaises(SystemExit):
            walkforward_garch(synthetic_equity_prices(52),
                              periods_per_year=252,min_train=500)

    def test_output_does_not_claim_direction_or_buy(self):
        self.assertIn("not direction",HONESTY_NOTE.lower())
        self.assertNotIn("signal",set(self.out.columns))
        self.assertNotIn("stop",set(self.out.columns))
        self.assertNotIn("buy",set(self.out.columns))

if __name__ == "__main__":
    unittest.main()
