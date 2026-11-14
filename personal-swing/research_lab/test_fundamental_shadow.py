"""Offline TDD regression for SEC-backed, non-authoritative fundamentals shadow."""
import copy
import json
import tempfile
from pathlib import Path
import unittest

from fundamental_shadow import ShadowHold, analyze, load_watchlist


CIK = "0001559720"
ACC = "0001559720-26-000011"
ACCEPT = "2026-02-13T21:03:15+00:00"


def fixture():
    annual_periods = [
        ("2024-01-01", "2024-12-31"),
        ("2025-01-01", "2025-12-31"),
    ]

    def series(vals):
        return {"units": {"USD": [
            {"accn": ACC, "form": "10-K", "filed": "2026-02-13",
             "start": start, "end": end, "val": value}
            for (start, end), value in zip(annual_periods, vals)
        ]}}

    return {
        "schema": "XRAY_FUNDAMENTAL_SEC_INPUT_V1",
        "ticker": "ABNB",
        "cik": CIK,
        "asof_utc": "2026-11-08T19:15:00+00:00",
        "observed_at_utc": "2026-11-08T19:00:00+00:00",
        "submissions": {
            "cik": 1559720, "tickers": ["ABNB"],
            "filings": {"recent": {
                "accessionNumber": [ACC], "form": ["10-K"],
                "filingDate": ["2026-02-13"],
                "acceptanceDateTime": ["2026-02-14T01:03:15Z"],
            }},
        },
        "companyfacts": {
            "cik": 1559720,
            "facts": {"us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": series([500, 625]),
                "NetCashProvidedByUsedInOperatingActivities": series([125, 150]),
                "PaymentsToAcquirePropertyPlantAndEquipment": series([20, 35]),
                "NetIncomeLoss": series([70, 100]),
            }},
        },
        "filing_headers": {
            ACC: {"raw": ("ACCESSION NUMBER:  " + ACC + "\n"
                           + "CENTRAL INDEX KEY: 1559720\n"
                           + "<ACCEPTANCE-DATETIME>20260213160315\n"),
                  "observed_at_utc": "2026-11-08T18:59:00+00:00"}
        },
    }


class TestFundamentalShadow(unittest.TestCase):
    def setUp(self):
        self.allowed = {"ABNB"}

    def check_hold(self, data, reason):
        with self.assertRaises(ShadowHold) as context:
            analyze(data, self.allowed)
        self.assertEqual(str(context.exception), reason)

    def test_positive_synthetic_provenance_and_arithmetic(self):
        out = analyze(fixture(), self.allowed)
        self.assertEqual(out["status"], "OFFLINE_STRUCTURE_PASS_NOT_LIVE")
        self.assertEqual(out["authority"], "RESEARCH_ONLY")
        self.assertEqual(out["filing_accession"], ACC)
        self.assertEqual(out["annual_periods"], ["2024-12-31", "2025-12-31"])
        self.assertEqual(out["metrics_usd"]["2024-12-31"]["fcf_proxy"], 105)
        self.assertEqual(out["metrics_usd"]["2025-12-31"]["fcf_proxy"], 115)
        self.assertEqual(out["growth_pct"]["revenue"], 25.0)
        self.assertEqual(out["growth_pct"]["operating_cash_flow"], 20.0)
        self.assertEqual(out["growth_pct"]["capex"], 75.0)
        self.assertFalse(out["independent_sec_origin_proven"])
        self.assertFalse(out["historical_pit_proven"])
        self.assertFalse(out["may_change_al"])
        self.assertFalse(out["may_trade"])
        self.assertEqual(out, analyze(fixture(), self.allowed))
        self.assertTrue(all(c["filing_accession"] == ACC for c in out["claims"]))

    def test_empty_or_outside_universe_holds(self):
        self.check_hold({}, "INPUT_SCHEMA_INVALID")
        with self.assertRaisesRegex(ShadowHold, "TICKER_NOT_IN_APPROVED_477"):
            analyze(fixture(), {"MSFT"})

    def test_cik_mismatch_holds(self):
        d = fixture(); d["companyfacts"]["cik"] = 1234
        self.check_hold(d, "COMPANYFACTS_CIK_MISMATCH")

    def test_current_ticker_mismatch_holds(self):
        d = fixture(); d["submissions"]["tickers"] = ["MSFT"]
        self.check_hold(d, "CURRENT_TICKER_CIK_MISMATCH")

    def test_missing_header_holds(self):
        d = fixture(); d["filing_headers"] = {}
        self.check_hold(d, "ACCEPTANCE_HEADER_MISSING")

    def test_wrong_accession_in_header_holds(self):
        d = fixture(); d["filing_headers"][ACC]["raw"] = d["filing_headers"][ACC]["raw"].replace(ACC, "0001559720-26-000012")
        self.check_hold(d, "HEADER_ACCESSION_MISMATCH")

    def test_future_acceptance_holds(self):
        d = fixture(); d["asof_utc"] = "2026-02-13T20:00:00+00:00"
        d["observed_at_utc"] = "2026-02-13T19:59:00+00:00"
        d["filing_headers"][ACC]["observed_at_utc"] = "2026-02-13T19:59:00+00:00"
        self.check_hold(d, "FILING_NOT_ACCEPTED_BY_CUTOFF")

    def test_historical_retrieval_after_cutoff_holds(self):
        d = fixture(); d["asof_utc"] = "2026-11-06T21:00:00+00:00"
        self.check_hold(d, "SOURCE_OBSERVED_AFTER_CUTOFF")

    def test_missing_xbrl_metric_holds(self):
        d = fixture(); del d["companyfacts"]["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
        self.check_hold(d, "REQUIRED_ANNUAL_FACT_MISSING")

    def test_mixed_accession_holds(self):
        d = fixture()
        d["companyfacts"]["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"][0]["accn"] = "0001559720-26-000012"
        self.check_hold(d, "REQUIRED_ANNUAL_FACT_MISSING")

    def test_conflicting_duplicate_xbrl_holds(self):
        d = fixture()
        arr = d["companyfacts"]["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
        duplicate = copy.deepcopy(arr[-1]); duplicate["val"] = 999
        arr.append(duplicate)
        self.check_hold(d, "CONFLICTING_XBRL_FACT")

    def test_filing_date_after_cutoff_holds(self):
        d = fixture(); d["submissions"]["filings"]["recent"]["filingDate"][0] = "2026-11-09"
        self.check_hold(d, "NO_ANNUAL_FILING_BY_CUTOFF")

    def test_amendment_unresolved_holds(self):
        d = fixture(); rec = d["submissions"]["filings"]["recent"]
        rec["accessionNumber"].append("0001559720-26-000012")
        rec["form"].append("10-K/A")
        rec["filingDate"].append("2026-03-01")
        rec["acceptanceDateTime"].append("2026-03-01T17:00:00Z")
        self.check_hold(d, "UNRESOLVED_10K_AMENDMENT")

    def test_negative_capex_holds(self):
        d = fixture(); d["companyfacts"]["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"][1]["val"] = -1
        self.check_hold(d, "NEGATIVE_REVENUE_OR_CAPEX")

    def test_boolean_fact_holds(self):
        d = fixture(); d["companyfacts"]["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"][1]["val"] = True
        self.check_hold(d, "NON_INTEGER_SEC_FACT")

    def test_date_only_asof_holds(self):
        d = fixture(); d["asof_utc"] = "2026-11-08"
        self.check_hold(d, "TIMESTAMP_MISSING_OFFSET")

    def test_exact_477_watchlist_contract(self):
        symbols = [f"X{i:04d}" for i in range(477)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "symbols.json"
            path.write_text(json.dumps({"liquidity_watch_symbols": symbols}), encoding="utf-8")
            self.assertEqual(len(load_watchlist(path)), 477)
            path.write_text(json.dumps({"liquidity_watch_symbols": symbols[:-1]}), encoding="utf-8")
            with self.assertRaisesRegex(ShadowHold, "WATCHLIST_NOT_477"):
                load_watchlist(path)
            symbols[-1] = symbols[0]
            path.write_text(json.dumps({"liquidity_watch_symbols": symbols}), encoding="utf-8")
            with self.assertRaisesRegex(ShadowHold, "WATCHLIST_DUPLICATE"):
                load_watchlist(path)

    def test_ignored_sec_submissions_clock_is_not_pit_authority(self):
        d = fixture()
        d["submissions"]["filings"]["recent"]["acceptanceDateTime"][0] = "2100-01-01T00:00:00Z"
        out = analyze(d, self.allowed)
        self.assertTrue(out["sec_submissions_clock_not_used_for_pit"])

    def test_recent_10q_and_8k_index_only_research_flags(self):
        d = fixture()
        recent = d["submissions"]["filings"]["recent"]
        for accession, form in (("0001559720-26-000032", "10-Q"),
                                ("0001193125-26-449727", "8-K")):
            recent["accessionNumber"].append(accession)
            recent["form"].append(form)
            recent["filingDate"].append("2026-11-05")
            recent["acceptanceDateTime"].append("2026-11-05T21:02:09Z")
        out = analyze(d, self.allowed)
        events = out["recent_disclosures_index_only"]
        self.assertEqual(len(events), 2)
        self.assertEqual({e["form"] for e in events}, {"10-Q", "8-K"})
        self.assertTrue(all(e["filing_date"] == "2026-11-05" for e in events))
        self.assertTrue(all(e["pit_accepted_timestamp_proven"] is False for e in events))
        self.assertTrue(all(e["research_only"] for e in events))
        self.assertFalse(out["may_change_al"])

    def test_older_future_and_unrelated_filings_do_not_claim_current_event(self):
        d = fixture()
        rec = d["submissions"]["filings"]["recent"]
        for day, form, accession in (("2026-10-01", "8-K", "0001559720-26-000030"),
                                     ("2099-01-01", "10-Q", "0001559720-99-000001"),
                                     ("2026-11-05", "4", "0001559720-26-000031")):
            rec["accessionNumber"].append(accession)
            rec["form"].append(form)
            rec["filingDate"].append(day)
            rec["acceptanceDateTime"].append(day + "T12:00:00Z")
        self.assertEqual(analyze(d, self.allowed)["recent_disclosures_index_only"], [])

    def test_duplicate_recent_disclosure_id_fails_closed(self):
        d = fixture()
        rec = d["submissions"]["filings"]["recent"]
        for _ in range(2):
            rec["accessionNumber"].append("0001193125-26-449727")
            rec["form"].append("8-K")
            rec["filingDate"].append("2026-11-05")
            rec["acceptanceDateTime"].append("2026-11-05T21:02:09Z")
        self.check_hold(d, "RECENT_DISCLOSURE_ACCESSION_DUPLICATE")

    def test_no_replay_backfill_trade_or_sheet_modules(self):
        import fundamental_shadow
        content = fundamental_shadow.__file__
        with open(content, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("alpaca_trade_api", "subprocess", "requests.post", "googleapiclient", "schedule", "sqlite3.connect"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
