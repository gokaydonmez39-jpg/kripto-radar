"""Synthetic-only REST pagination and data-only pilot acceptance (no network)."""
import unittest
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs

import flow_capture_a36 as c
from flow_shadow_a36 import FlowBlocked

START = "2026-10-28T14:00:00Z"
END = "2026-10-28T14:00:01Z"
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def trade(i=1, price=100.1):
    return {"t": "2026-10-28T14:00:00.100Z" if i==1 else
            "2026-10-28T14:00:00.200Z",
            "x":"V", "p":price, "s":10, "i":i, "c":["@"]}


def quote():
    return {"t":"2026-10-28T14:00:00.000Z","bp":100.0,"ap":100.1}


def provider(url, headers):
    endpoint = urlsplit(url)
    query = parse_qs(endpoint.query)
    if endpoint.path.endswith("/trades"):
        return {"trades":[trade()], "next_page_token":None}
    if endpoint.path.endswith("/quotes"):
        return {"quotes":[quote()], "next_page_token":None}
    raise AssertionError("non-data provider request")


def run(**kwargs):
    k = {"symbols":["FAKE"],"feed":"IEX","start_utc":START,
         "end_utc":END,"key":"synthetic-id","secret":"synthetic-secret",
         "now_utc":NOW,"request_json":provider}
    k.update(kwargs)
    return c.pilot(**k)


class CaptureA36(unittest.TestCase):
    def test_real_api_shape_stub_outputs_aggregates_only(self):
        r=run()
        self.assertEqual(r["symbol_count"],1)
        self.assertEqual(r["aggregate_counts"]["qualified_trade_count"],1)
        self.assertEqual(r["aggregate_counts"]["unknown_trade_count"],0)
        self.assertEqual(r["aggregate_counts"]["trade_pages"],1)
        self.assertEqual(r["aggregate_counts"]["quote_pages"],1)
        self.assertTrue(r["source_response_pagination_chain_completed"])
        self.assertFalse(r["full_market_venue_and_correction_coverage_attested"])
        self.assertFalse(r["institutional_identity_verified"])
        self.assertFalse(r["may_change_al"])
        self.assertFalse(r["may_emit_alert"])
        self.assertFalse(r["orders"])
        self.assertNotIn("FAKE",str(r))
        self.assertNotIn("synthetic-secret",str(r))

    def test_unsupported_correction_never_counts_as_buy(self):
        def corrected(url, headers):
            if urlsplit(url).path.endswith("/trades"):
                t = trade()
                t["u"] = "canceled"
                return {"trades":[t], "next_page_token":None}
            return provider(url, headers)
        r = run(request_json=corrected)
        self.assertEqual(r["aggregate_counts"]["qualified_trade_count"],0)
        self.assertEqual(r["aggregate_unknown_reasons"]["CANCELLED_OR_CORRECTED_TRADE"],1)
        self.assertEqual(r["classification_ratio"],0)

    def test_zero_prints_is_unknown_not_no_signal(self):
        def no_print(url, headers):
            if urlsplit(url).path.endswith("/trades"):
                return {"trades":[], "next_page_token":None}
            return provider(url, headers)
        r=run(request_json=no_print)
        self.assertEqual(r["pilot_outcome"],"NO_TRADES_OBSERVED_IN_BOUNDED_SAMPLE_UNKNOWN")
        self.assertEqual(r["aggregate_counts"]["observed_trade_count"],0)
        self.assertIsNone(r["classification_ratio"])

    def test_one_empty_symbol_flags_partial_coverage(self):
        def missing_one(url, headers):
            if "/MISSING/" in url and urlsplit(url).path.endswith("/trades"):
                return {"trades":[], "next_page_token":None}
            return provider(url,headers)
        r=run(symbols=["FAKE","MISSING"],request_json=missing_one)
        self.assertEqual(r["pilot_outcome"],"PARTIAL_SYMBOL_COVERAGE_UNKNOWN")
        self.assertEqual(r["aggregate_counts"]["zero_trade_symbol_count"],1)

    def test_provider_returned_other_symbol_fails_closed(self):
        def mismatch(url, headers):
            data=provider(url,headers)
            if urlsplit(url).path.endswith("/trades"):
                data["symbol"]="OTHER"
            return data
        with self.assertRaisesRegex(FlowBlocked,"PROVIDER_SYMBOL_MISMATCH"):
            run(request_json=mismatch)

    def test_request_page_budget_is_bounded(self):
        self.assertLessEqual(c.MAX_PAGES, 10)
        self.assertLessEqual(c.MAX_SYMBOLS * 2 * c.MAX_PAGES, 100)
        self.assertLessEqual(c.MAX_RECORDS, 10000)

    def test_pagination_two_pages_complete(self):
        def paging(url, headers):
            x=urlsplit(url)
            q=parse_qs(x.query)
            if x.path.endswith("/trades"):
                if "page_token" not in q:
                    return {"trades":[trade(1)], "next_page_token":"token-2"}
                self.assertEqual(q["page_token"],["token-2"])
                return {"trades":[trade(2,100.0)],"next_page_token":None}
            return {"quotes":[quote()], "next_page_token":None}
        r=run(request_json=paging)
        self.assertEqual(r["aggregate_counts"]["trade_pages"],2)
        self.assertEqual(r["aggregate_counts"]["qualified_trade_count"],2)

    def test_repeated_page_token_is_blocked(self):
        def forever(url, headers):
            return {"trades":[trade()], "next_page_token":"repeat"}
        with self.assertRaisesRegex(FlowBlocked,"BAD_OR_REPEATED_PAGE_TOKEN"):
            run(request_json=forever)

    def test_incomplete_pagination_fails_closed(self):
        old=c.MAX_PAGES
        c.MAX_PAGES=2
        try:
            def infinite(url, headers):
                return {"trades":[trade()], "next_page_token":
                        "different"+str("page_token" in parse_qs(urlsplit(url).query))}
            with self.assertRaisesRegex(FlowBlocked,"UNFINISHED_PAGINATION|BAD_OR_REPEATED"):
                run(request_json=infinite)
        finally:
            c.MAX_PAGES=old

    def test_bad_response_rejected(self):
        with self.assertRaisesRegex(FlowBlocked,"BAD_PROVIDER_PAGE"):
            run(request_json=lambda url,headers:{"trades":None})

    def test_missing_provider_fields_rejected(self):
        def incomplete(url, headers):
            if urlsplit(url).path.endswith("/trades"):
                t=trade();t.pop("i")
                return {"trades":[t],"next_page_token":None}
            return provider(url,headers)
        with self.assertRaisesRegex(FlowBlocked,"MISSING_RAW_TRADE_FIELD"):
            run(request_json=incomplete)

    def test_invalid_quote_schema_rejected(self):
        def incomplete(url, headers):
            if urlsplit(url).path.endswith("/quotes"):
                q=quote();q.pop("ap")
                return {"quotes":[q],"next_page_token":None}
            return provider(url,headers)
        with self.assertRaisesRegex(FlowBlocked,"MISSING_RAW_QUOTE_FIELD"):
            run(request_json=incomplete)

    def test_duplicate_trade_fails_closed(self):
        def duplicate(url, headers):
            if urlsplit(url).path.endswith("/trades"):
                return {"trades":[trade(1),trade(1)],"next_page_token":None}
            return provider(url,headers)
        with self.assertRaisesRegex(FlowBlocked,"DUPLICATE_TRADE_ID"):
            run(request_json=duplicate)

    def test_5_symbol_pilot_no_477_universe_claim(self):
        r=run(symbols=["FAKE","FAK2","FAK3","FAK4","FAK5"])
        self.assertEqual(r["symbol_count"],5)
        self.assertEqual(r["aggregate_counts"]["trade_pages"],5)
        self.assertFalse(r["full_market_venue_and_correction_coverage_attested"])

    def test_six_symbols_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"SCOPE_NOT_ONE_TO_FIVE"):
            run(symbols=["FAKE","A","B","C","D","E"])

    def test_duplicate_symbols_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"SCOPE_NOT_ONE_TO_FIVE"):
            run(symbols=["FAKE","FAKE"])

    def test_symbol_path_injection_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"SCOPE_NOT_ONE_TO_FIVE"):
            run(symbols=["FAKE/../orders"])

    def test_missing_credentials_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"MISSING_DATA_ONLY_CREDENTIALS"):
            run(key="")

    def test_wrong_feed_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"PILOT_FEED_NOT_EXACT"):
            run(feed="COMPOSITE")

    def test_future_window_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"PILOT_HISTORICAL_EMBARGO_NOT_MET"):
            run(now_utc=datetime(2026,10,28,14,10,tzinfo=timezone.utc))

    def test_over_60_seconds_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"PILOT_WINDOW_EXCEEDS_60"):
            run(end_utc="2026-10-28T14:02:00Z")

    def test_non_utc_now_blocked(self):
        with self.assertRaisesRegex(FlowBlocked,"INVALID_NOW_UTC"):
            run(now_utc=datetime(2026,10,29,12))

    def test_direct_host_whitelist(self):
        with self.assertRaisesRegex(FlowBlocked,"NOT_ALLOWED_DATA_ONLY_HOST"):
            c.get_page("https://broker-api.alpaca.markets/v2/orders",
                       {"X":"synthetic"},request_json=provider)

    def test_outside_rth_rejected_through_validator(self):
        with self.assertRaisesRegex(FlowBlocked,"OUTSIDE_XNAS_RTH"):
            run(start_utc="2026-10-28T12:00:00Z",
                end_utc="2026-10-28T12:00:01Z")

if __name__ == "__main__":
    unittest.main()
