"""Entirely synthetic bar data — no market-provider access."""
import copy
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import exchange_calendars as xc
from strong4_history_qa import inspect, market_identity, WATCHLIST_GIT_BLOB

class HistoryQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols=["AAPL","INDV","CRWV"]+[f"Z{i:04d}" for i in range(474)]
        cal=xc.get_calendar("XNAS")
        cls.sessions=[d.strftime("%Y-%m-%d") for d in cal.sessions_in_range("2024-09-03","2026-11-06")]
    def fixture(self):
        def rows(days):
            return [{"timestamp": datetime.strptime(d,"%Y-%m-%d").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc).isoformat(),
                     "open":100.0,"high":102.0,"low":99.0,"close":101.0,"volume":1000} for d in days]
        return {"schema":"XRAY_STRONG4_PRIVATE_HISTORY_INPUT_V1",
                "source":"Alpaca","feed":"iex","timeframe":"1Day","basis":"RAW",
                "asof_et":"2026-11-06","universe_git_blob":WATCHLIST_GIT_BLOB,
                "bars":{"AAPL":rows(self.sessions),
                        "INDV":rows([d for d in self.sessions if d<="2026-11-02"]),
                        "CRWV":rows([d for d in self.sessions if d>="2025-03-28"])}}
    def rejected(self,code,edit):
        obj=self.fixture()
        edit(obj)
        with self.assertRaisesRegex(ValueError,code): inspect(obj,self.symbols)
    def test_realshape_synthetic_477(self):
        r=inspect(self.fixture(),self.symbols)
        self.assertEqual(r["counts"]["DATE_SHAPE_500_ONLY"],1)
        self.assertEqual(r["counts"]["KNOWN_CORPORATE_ACTION_IDENTITY_HOLD"],1)
        self.assertEqual(r["counts"]["SHORT_HISTORY_HOLD"],1)
        self.assertEqual(r["counts"]["MISSING_HISTORY_HOLD"],474)
        self.assertFalse(r["production_authorized"])
        self.assertFalse(r["oos_performance_verified"])
    def test_indv_successor_policy(self):
        self.assertEqual(market_identity("INDV",datetime(2026,11,2).date())[0],"INDV")
        self.assertEqual(market_identity("INDV",datetime(2026,11,3).date()),
                         ("SUPN","SUCCESSOR_OF_INDVIOR_NOT_LEGACY_SUPN"))
        self.assertEqual(market_identity("SUPN",datetime(2026,11,2).date())[1],
                         "LEGACY_SUPN_DISTINCT_ISSUER")
    def test_no_legacy_supn_join(self):
        self.rejected("UNDECLARED_PRICE_SYMBOL",lambda x:x["bars"].update(SUPN=x["bars"]["AAPL"]))
    def test_no_extra_symbol(self):
        self.rejected("UNDECLARED_PRICE_SYMBOL",lambda x:x["bars"].update(FAKE=x["bars"]["AAPL"]))
    def test_no_sip(self):
        self.rejected("SOURCE_SCOPE_INVALID_feed",lambda x:x.update(feed="sip"))
    def test_no_adjusted(self):
        self.rejected("SOURCE_SCOPE_INVALID_basis",lambda x:x.update(basis="SPLIT"))
    def test_no_unreviewed_future(self):
        self.rejected("FUTURE_OR_UNREVIEWED_ASOF",lambda x:x.update(asof_et="2026-11-09"))
    def test_duplicate_bar_rejected(self):
        self.rejected("DUPLICATE_OR_UNSORTED_BARS",lambda x:x["bars"]["CRWV"].insert(1,copy.deepcopy(x["bars"]["CRWV"][0])))
    def test_out_of_order_rejected(self):
        self.rejected("DUPLICATE_OR_UNSORTED_BARS",lambda x:x["bars"]["CRWV"].reverse())
    def test_nan_rejected(self):
        self.rejected("PRICE_INVALID_AAPL",lambda x:x["bars"]["AAPL"][7].update(close=float("nan")))
    def test_negative_price_rejected(self):
        self.rejected("PRICE_INVALID_AAPL",lambda x:x["bars"]["AAPL"][7].update(close=-1))
    def test_bad_ohlc_rejected(self):
        self.rejected("BAR_OHLC_CONTRADICTION_AAPL",lambda x:x["bars"]["AAPL"][7].update(high=98))
    def test_volume_bool_rejected(self):
        self.rejected("VOLUME_INVALID_AAPL",lambda x:x["bars"]["AAPL"][7].update(volume=True))
    def test_extra_bar_field_rejected(self):
        self.rejected("BAR_SCHEMA_INVALID_AAPL",lambda x:x["bars"]["AAPL"][7].update(pnl=100))
    def test_future_bar_rejected(self):
        self.rejected("NON_XNAS_OR_FUTURE_BAR_AAPL",lambda x:x["bars"]["AAPL"].append({**x["bars"]["AAPL"][-1],"timestamp":"2026-11-09T05:00:00+00:00"}))
    def test_trailing_missing_becomes_stale(self):
        x=self.fixture();x["bars"]["AAPL"].pop()
        self.assertEqual(inspect(x,self.symbols)["counts"]["STALE_HISTORY_HOLD"],1)
    def test_internal_missing_becomes_gapped(self):
        x=self.fixture();x["bars"]["AAPL"].pop(8)
        self.assertEqual(inspect(x,self.symbols)["counts"]["GAPPED_HISTORY_HOLD"],1)
    def test_identity_requires_existing_watchlist(self):
        x=self.fixture();bad=self.symbols.copy();bad[0]="SUPN"
        with self.assertRaisesRegex(ValueError,"NOT_FIXED_477"): inspect(x,bad)

if __name__=="__main__":unittest.main()
