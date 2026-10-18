"""Accept only redacted connected Alpaca SIP one-day 13-RTH research metrics."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WITNESS=ROOT/"research"/"alpaca_connected_sip_three_unknown_20261018_exact13_rth_v1.json"
PRICE=ROOT/"canonical_current_price_dv30.json"
SYMS=["AAL","AAOI","AAON"]
ALLOWED_ROW_KEYS={"symbol","feed","timeframe","returned_bars","regular_rth_bars",
                  "outside_regular_rth_bars","expected_rth_bars","all_regular_volumes_positive_whole_shares",
                  "all_regular_timestamps_unique","last_reported_time_utc"}

def check(ok,msg):
    if not ok: raise ValueError("XRAY_ALPACA_3UNKNOWN_"+msg)

def validate(doc,price):
    check(type(doc) is dict and doc.get("schema")=="XRAY_ALPACA_CONNECTED_THREE_UNKNOWN_RTH13_RESEARCH_V1","SCHEMA")
    check(doc.get("asof_et")=="2026-10-16" and doc.get("asof_et")==price.get("asof_et"),"ASOF")
    check(doc.get("source_surface")=="CONNECTED_CHATGPT_ALPACA_READ_ONLY_SIP_NOT_GITHUB_RUNNER","SURFACE")
    check(doc.get("licensed_unattended_github_runner_market_data") is False,"LICENSE")
    check(doc.get("raw_vendor_prices_or_volumes_persisted") is False,"RAW_VALUES")
    check(doc.get("vendor_signed_original_bytes_or_sha_attested") is False,"RAW_SHA")
    check(doc.get("full_30_sessions_attested") is False and doc.get("full_260_sessions_attested") is False,"MISSING_HISTORY")
    check(doc.get("market_cap_independent_verified") is False and doc.get("corporate_actions_verified") is False,"MC_OR_CA")
    for k in ("may_promote_price","may_promote_history","may_promote_market_cap","may_register_r92",
              "may_notify_user","whole_542_unknown_unblocked","g9_enabled"):
        check(doc.get(k) is False,"FALSE_PASS_"+k)
    check(doc.get("registered_r92")==0 and doc.get("sent_alerts")==0,"R92_ALERT")
    check(doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO","NO_TRADE")
    check(doc.get("unknown_never_pass") is True,"UNKNOWN_POLICY")
    check(price.get("pass_count")==0 and price.get("unknown_count")==542,"CANONICAL_PRICE_COUNTS")
    rows=doc.get("rows")
    check(type(rows) is list and len(rows)==3,"ROW_COUNT")
    check([r.get("symbol") for r in rows]==SYMS,"ROW_SYMBOLS")
    for row in rows:
        check(type(row) is dict and set(row)==ALLOWED_ROW_KEYS,"NO_RAW_VALUES_SCHEMA")
        check(row["symbol"] in price["unknown_symbols"],"CANONICAL_UNKNOWN_ONLY")
        check(row["feed"]=="sip" and row["timeframe"]=="30Min","FEED")
        check(all(type(row[k]) is int for k in ("returned_bars","regular_rth_bars",
                                                      "outside_regular_rth_bars","expected_rth_bars")),"BAR_INTEGER")
        check(row["returned_bars"]==14 and row["regular_rth_bars"]==13 and row["expected_rth_bars"]==13
              and row["outside_regular_rth_bars"]==1,"RTH_13_OF_13")
        check(row["all_regular_volumes_positive_whole_shares"] is True
              and row["all_regular_timestamps_unique"] is True,"VOLUME_OR_SESSION_INTEGRITY")
        check(row["last_reported_time_utc"]=="2026-10-16T20:00:00+00:00","CLOSE_BOUND")
    return True

class TestThreeUnknownReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=json.loads(WITNESS.read_text())
        cls.price=json.loads(PRICE.read_text())

    def test_source_bound_true_one_day_only(self):
        self.assertTrue(validate(copy.deepcopy(self.doc),self.price))

    def test_source_license_cannot_be_inferred(self):
        d=copy.deepcopy(self.doc);d["licensed_unattended_github_runner_market_data"]=True
        with self.assertRaises(ValueError):validate(d,self.price)

    def test_cannot_promote_signal_or_evidence(self):
        for k in ("may_promote_price","may_promote_history","may_promote_market_cap",
                  "may_register_r92","may_notify_user","whole_542_unknown_unblocked","g9_enabled"):
            d=copy.deepcopy(self.doc);d[k]=True
            with self.subTest(field=k),self.assertRaises(ValueError):validate(d,self.price)

    def test_bars_are_not_a_thirty_day_history(self):
        for k in ("full_30_sessions_attested","full_260_sessions_attested"):
            d=copy.deepcopy(self.doc);d[k]=True
            with self.assertRaises(ValueError):validate(d,self.price)

    def test_raw_price_or_vendor_sha_cannot_be_claimed(self):
        for k in ("raw_vendor_prices_or_volumes_persisted","vendor_signed_original_bytes_or_sha_attested"):
            d=copy.deepcopy(self.doc);d[k]=True
            with self.assertRaises(ValueError):validate(d,self.price)

    def test_bad_extra_venue_bar_rejected(self):
        d=copy.deepcopy(self.doc);d["rows"][0]["regular_rth_bars"]=14
        with self.assertRaises(ValueError):validate(d,self.price)

    def test_one_missing_rth_slot_is_not_complete(self):
        d=copy.deepcopy(self.doc);d["rows"][1]["regular_rth_bars"]=12
        with self.assertRaises(ValueError):validate(d,self.price)

    def test_unverified_symbol_not_appended(self):
        d=copy.deepcopy(self.doc);d["rows"][2]["symbol"]="MSFT"
        with self.assertRaises(ValueError):validate(d,self.price)

    def test_secret_or_raw_close_in_row_rejected(self):
        d=copy.deepcopy(self.doc);d["rows"][0]["close"]=123.456
        with self.assertRaises(ValueError):validate(d,self.price)

    def test_asof_drift_rejected(self):
        d=copy.deepcopy(self.doc);d["asof_et"]="2026-10-15"
        with self.assertRaises(ValueError):validate(d,self.price)
if __name__=="__main__":unittest.main()
