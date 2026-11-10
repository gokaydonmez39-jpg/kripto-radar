"""A36 unit/negative tests: fully synthetic, no API, accounts, Sheets, push."""
import copy
import unittest

import exchange_calendars as ec
import flow_shadow_a36 as f

CAL = ec.get_calendar("XNAS")
ASOF = "2026-10-28"
DAYS = [str(x.date()) for x in CAL.sessions_window(CAL.date_to_session(ASOF), -52)]


def eod():
    bars = []
    for i, day in enumerate(DAYS):
        bars.append({"session": day, "open": 100+i*.1,
                     "high": 101+i*.1, "low": 99+i*.1,
                     "close": 100+i*.1, "volume": 1000})
    bars[-1]["volume"] = 2000
    bars[-1]["close"] = bars[-1]["high"]
    return {"schema": f.SCHEMA_EOD, "symbol": "FAKE", "provider": "ALPACA",
            "feed": "IEX", "basis": "RAW", "asof_et": ASOF,
            "cutoff_utc": "2026-10-28T21:00:00Z", "bars": bars}


def ticks():
    return {
        "schema": f.SCHEMA_TICK, "symbol": "FAKE", "provider": "ALPACA",
        "feed": "IEX", "basis": "RAW",
        "window_start_utc": "2026-10-28T14:00:00Z",
        "window_end_utc": "2026-10-28T14:00:05Z",
        "cutoff_utc": "2026-10-28T14:00:06Z",
        "quotes": [
            {"timestamp": "2026-10-28T14:00:01.000Z",
             "bid_price": 100.00, "ask_price": 100.10},
            {"timestamp": "2026-10-28T14:00:02.000Z",
             "bid_price": 100.00, "ask_price": 100.10},
        ],
        "trades": [
            {"timestamp": "2026-10-28T14:00:01.100Z",
             "price": 100.10, "size": 10, "exchange": "V",
             "id": 1, "conditions": ["@"]},
            {"timestamp": "2026-10-28T14:00:02.100Z",
             "price": 100.00, "size": 8, "exchange": "V",
             "id": 2, "conditions": ["@"]},
        ],
    }


class A36Research(unittest.TestCase):
    def fails(self, mode, modify, why, **kwargs):
        d = eod() if mode == "eod" else ticks()
        modify(d)
        with self.assertRaisesRegex(f.FlowBlocked, why):
            (f.evaluate_eod(d) if mode == "eod"
             else f.evaluate_ticks(d, **kwargs))

    def test_eod_positive_and_no_market_side_effects(self):
        result = f.evaluate_eod(eod())
        self.assertEqual(result["sessions"], 52)
        self.assertEqual(result["rvol20"], 2.0)
        self.assertEqual(result["source_feed"], "IEX")
        self.assertEqual(result["research_tag"], "EOD_UP_VOLUME_PROXY")
        self.assertEqual(result["signed_order_flow"], "UNAVAILABLE_FROM_OHLCV")
        for deny in f.DENIAL:
            self.assertIs(result[deny], False)

    def test_eod_mixed_not_buy_pressure(self):
        d = eod()
        d["bars"][-1]["close"] = 105.1
        r = f.evaluate_eod(d)
        self.assertEqual(r["research_tag"], "EOD_MIXED_OR_UNINFORMATIVE")

    def test_eod_zero_range(self):
        d = eod()
        c = d["bars"][-1]["close"]
        d["bars"][-1].update(open=c, high=c, low=c)
        self.assertEqual(f.evaluate_eod(d)["research_tag"], "ZERO_RANGE_UNKNOWN")

    def test_eod_missing_52(self):
        self.fails("eod", lambda d: d["bars"].pop(), "EXACT_52")
    def test_eod_duplicate_day(self):
        self.fails("eod", lambda d: d["bars"][-1].update(
            session=d["bars"][-2]["session"]), "NONCONTIGUOUS")
    def test_eod_out_of_order(self):
        self.fails("eod", lambda d: d["bars"].reverse(), "NONCONTIGUOUS")
    def test_eod_nan(self):
        self.fails("eod", lambda d: d["bars"][-1].update(volume=float("nan")),
                   "INVALID_NUMERIC")
    def test_eod_zero_volume(self):
        self.fails("eod", lambda d: d["bars"][-1].update(volume=0),
                   "INVALID_NUMERIC")
    def test_eod_bad_geometry(self):
        self.fails("eod", lambda d: d["bars"][-1].update(high=1),
                   "BAD_OHLC")
    def test_eod_preclose(self):
        self.fails("eod", lambda d: d.update(
            cutoff_utc="2026-10-28T20:05:00Z"), "EOD_NOT_YET_FINAL")
    def test_eod_future_asof(self):
        self.fails("eod", lambda d: d.update(asof_et="2026-10-29"),
                   "EOD_NOT_YET_FINAL")
    def test_eod_holiday(self):
        self.fails("eod", lambda d: d.update(asof_et="2026-10-25"),
                   "NOT_XNAS_SESSION")
    def test_eod_nonraw_basis(self):
        self.fails("eod", lambda d: d.update(basis="SPLIT_ADJUSTED"),
                   "NOT_RAW")
    def test_eod_fake_provider(self):
        self.fails("eod", lambda d: d.update(provider="UNKNOWN"),
                   "PROVIDER_OR_FEED")
    def test_eod_wrong_feed(self):
        self.fails("eod", lambda d: d.update(feed="IEX_AND_SIP"),
                   "PROVIDER_OR_FEED")
    def test_eod_wrong_schema(self):
        self.fails("eod", lambda d: d.update(schema="PRODUCTION_AL"),
                   "BAD_SCHEMA")

    def test_ticks_two_inferences_never_whale(self):
        x = f.evaluate_ticks(ticks())
        self.assertEqual(x["inferred_buy_trades"], 1)
        self.assertEqual(x["inferred_sell_trades"], 1)
        self.assertEqual(x["inferred_buy_shares"], 10)
        self.assertEqual(x["inferred_sell_shares"], 8)
        self.assertEqual(x["whale_activity"], "UNKNOWN_NOT_IDENTIFIABLE")
        self.assertEqual(x["sample_pagination_and_venue_completeness"],
                         "NOT_ATTESTED")
        for deny in f.DENIAL:
            self.assertIs(x[deny], False)

    def test_ticks_unknown_nonstandard_oddlot(self):
        d = ticks()
        d["trades"][0]["conditions"] = ["@", "I"]
        x = f.evaluate_ticks(d)
        self.assertEqual(x["unknown_reasons"]["NONSTANDARD_CONDITION"], 1)
        self.assertEqual(x["unclassified_count"], 1)
    def test_ticks_unknown_no_quote(self):
        d = ticks()
        d["quotes"].clear()
        self.assertEqual(f.evaluate_ticks(d)["unknown_reasons"]["NO_PRIOR_QUOTE"], 2)
    def test_ticks_unknown_stale(self):
        d = ticks()
        d["quotes"] = d["quotes"][:1]
        self.assertEqual(f.evaluate_ticks(d)["unknown_reasons"]["STALE_QUOTE"], 1)
    def test_ticks_unknown_wide_spread(self):
        d = ticks()
        d["quotes"][0]["ask_price"] = 150
        self.assertEqual(f.evaluate_ticks(d)["unknown_reasons"]["WIDE_OR_INVALID_SPREAD"], 1)
    def test_ticks_unknown_mid(self):
        d = ticks()
        d["trades"][0]["price"] = 100.05
        self.assertEqual(f.evaluate_ticks(d)["unknown_reasons"]["TRADE_AT_MID"], 1)
    def test_ticks_dup_trade(self):
        self.fails("ticks", lambda d: d["trades"][1].update(id=1),
                   "DUPLICATE_TRADE")
    def test_ticks_reversed_trade(self):
        self.fails("ticks", lambda d: d["trades"].reverse(),
                   "UNSORTED_TRADES")
    def test_ticks_reversed_quote(self):
        self.fails("ticks", lambda d: d["quotes"].reverse(),
                   "UNSORTED_QUOTES")
    def test_ticks_future_window(self):
        self.fails("ticks", lambda d: d.update(
            cutoff_utc="2026-10-28T14:00:04Z"),
            "INVALID_OR_FUTURE_SAMPLE")
    def test_ticks_non_utc(self):
        self.fails("ticks", lambda d: d["quotes"][0].update(
            timestamp="2026-10-28T10:00:01-04:00"), "UTC_NANOSECOND_TIMESTAMP_REQUIRED")
    def test_ticks_zero_price(self):
        self.fails("ticks", lambda d: d["trades"][0].update(price=0),
                   "INVALID_NUMERIC")
    def test_ticks_nan_size(self):
        self.fails("ticks", lambda d: d["trades"][0].update(size=float("nan")),
                   "INVALID_NUMERIC")
    def test_ticks_missing_conditions(self):
        self.fails("ticks", lambda d: d["trades"][0].pop("conditions"),
                   "BAD_TRADE_CONDITIONS")
    def test_ticks_policy_guards(self):
        with self.assertRaisesRegex(f.FlowBlocked, "BAD_AGE_POLICY"):
            f.evaluate_ticks(ticks(), max_age_ms=2000)
        with self.assertRaisesRegex(f.FlowBlocked, "BAD_SPREAD_POLICY"):
            f.evaluate_ticks(ticks(), max_spread_pct=5)
    def test_ticks_outside_spread_is_unknown_not_sell(self):
        d = ticks()
        d["trades"][0]["price"] = 99.0
        r = f.evaluate_ticks(d)
        self.assertEqual(r["unknown_reasons"]["PRICE_OUTSIDE_QUOTED_SPREAD"], 1)
        self.assertEqual(r["inferred_sell_trades"], 1)
        self.assertEqual(r["inferred_buy_trades"], 0)

    def test_ticks_premarket_is_blocked(self):
        d = ticks()
        d["window_start_utc"] = "2026-10-28T12:00:00Z"
        d["window_end_utc"] = "2026-10-28T12:00:05Z"
        d["cutoff_utc"] = "2026-10-28T12:00:06Z"
        with self.assertRaisesRegex(f.FlowBlocked, "OUTSIDE_XNAS_RTH"):
            f.evaluate_ticks(d)

    def test_ticks_holiday_is_blocked(self):
        d = ticks()
        for row in d["trades"] + d["quotes"]:
            row["timestamp"] = row["timestamp"].replace("2026-10-28", "2026-10-25")
        d["window_start_utc"] = "2026-10-25T14:00:00Z"
        d["window_end_utc"] = "2026-10-25T14:00:05Z"
        d["cutoff_utc"] = "2026-10-25T14:00:06Z"
        with self.assertRaisesRegex(f.FlowBlocked, "NOT_XNAS_RTH"):
            f.evaluate_ticks(d)

    def test_nanosecond_future_quote_cannot_classify_past_trade(self):
        d = ticks()
        d["trades"] = [dict(d["trades"][0],
                            timestamp="2026-10-28T14:00:01.000000100Z")]
        d["quotes"] = [dict(d["quotes"][0],
                            timestamp="2026-10-28T14:00:01.000000900Z")]
        r = f.evaluate_ticks(d)
        self.assertEqual(r["unknown_reasons"]["NO_PRIOR_QUOTE"], 1)
        self.assertEqual(r["classified_count"], 0)

    def test_exact_nanosecond_ordered_quote_is_eligible(self):
        d = ticks()
        d["trades"] = [dict(d["trades"][0],
                            timestamp="2026-10-28T14:00:01.000000900Z")]
        d["quotes"] = [dict(d["quotes"][0],
                            timestamp="2026-10-28T14:00:01.000000100Z")]
        r = f.evaluate_ticks(d)
        self.assertEqual(r["inferred_buy_trades"], 1)
        self.assertEqual(r["unclassified_count"], 0)

    def test_exact_simultaneous_quote_not_causal(self):
        d = ticks()
        d["trades"] = [dict(d["trades"][0],
                            timestamp="2026-10-28T14:00:01.000000500Z")]
        d["quotes"] = [dict(d["quotes"][0],
                            timestamp="2026-10-28T14:00:01.000000500Z")]
        r = f.evaluate_ticks(d)
        self.assertEqual(r["unknown_reasons"]["NO_PRIOR_QUOTE"], 1)

    def test_trade_correction_cancel_or_incorrect_is_unknown(self):
        for update in ("cancelled", "incorrect", "corrected"):
            with self.subTest(update=update):
                d = ticks()
                d["trades"][0]["update"] = update
                r = f.evaluate_ticks(d)
                self.assertEqual(
                    r["unknown_reasons"]["CANCELLED_OR_CORRECTED_TRADE"], 1
                )
                self.assertEqual(r["inferred_buy_trades"], 0)

    def test_ticks_sample_not_complete_even_if_caller_claims(self):
        d=ticks()
        d["pagination_complete"]=True
        d["market_coverage_attested"]=True
        r=f.evaluate_ticks(d)
        self.assertEqual(r["sample_pagination_and_venue_completeness"],
                         "NOT_ATTESTED")
        self.assertFalse(r["whole_market_buy_sell_proven"])


    def test_cohort_complete_synthetic_research_only(self):
        import hashlib
        names = ["FAKE%03d" % n for n in range(477)]
        digest = hashlib.sha256(("\n".join(names)+"\n").encode()).hexdigest()
        d = {"schema": "XRAY_NASDAQ_A36_COHORT_RESEARCH_INPUT_V1",
             "watchlist": names, "expected_scope_sha256": digest,
             "snapshots": []}
        base = eod()
        for name in names:
            row = copy.deepcopy(base)
            row["symbol"] = name
            d["snapshots"].append(row)
        x = f.evaluate_cohort(d)
        self.assertEqual(x["supplied_symbols_validated"], 477)
        self.assertEqual(x["supplied_sessions_validated"], 52)
        self.assertFalse(x["live_provider_collection_proven"])
        self.assertFalse(x["may_change_production_al"])
        d["snapshots"].pop()
        with self.assertRaisesRegex(f.FlowBlocked, "COHORT_COVERAGE"):
            f.evaluate_cohort(d)

    def test_cohort_wrong_scope_or_feed_fails(self):
        import hashlib
        names = ["FAKE%03d" % n for n in range(477)]
        digest = hashlib.sha256(("\n".join(names)+"\n").encode()).hexdigest()
        base = eod()
        d = {"schema": "XRAY_NASDAQ_A36_COHORT_RESEARCH_INPUT_V1",
             "watchlist": names, "expected_scope_sha256": digest,
             "snapshots": []}
        for name in names:
            row = dict(base)
            row["symbol"] = name
            d["snapshots"].append(row)
        d["expected_scope_sha256"] = "f"*64
        with self.assertRaisesRegex(f.FlowBlocked, "COHORT_SCOPE_SHA"):
            f.evaluate_cohort(d)
        d["expected_scope_sha256"] = digest
        d["snapshots"][0] = dict(d["snapshots"][0], feed="SIP")
        with self.assertRaisesRegex(f.FlowBlocked, "COHORT_PRODUCTION_SOURCE"):
            f.evaluate_cohort(d)

if __name__ == "__main__":
    unittest.main()
