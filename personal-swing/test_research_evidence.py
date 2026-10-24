import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import research_evidence as r

CUT = "2026-10-23T20:00:00Z"
CIK = "0001234567"
ACCESSION = "0001234567-26-000001"

def sec_sample(when="2026-10-23T19:10:00Z", cik=1234567, sym="CVLT", form="8-K"):
    return {"cik": cik, "tickers": [sym], "exchanges": ["Nasdaq"],
            "filings": {"recent": {"form": [form], "accessionNumber": [ACCESSION],
            "acceptanceDateTime": [when], "filingDate": ["2026-10-23"],
            "primaryDocument": ["example.htm"]}}}

def form4_sample(code="P", cik="0001234567"):
    return f"""<?xml version="1.0"?>
<ownershipDocument><issuer><issuerCik>{cik}</issuerCik></issuer>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-10-22</value></transactionDate>
<transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""

class ResearchEvidenceTests(unittest.TestCase):
    def test_sec_good(self):
        q = r.sec_submission_evidence(sec_sample(), symbol="CVLT",
                                     expected_cik=CIK, cutoff_utc=CUT)
        self.assertEqual(q["filings"][0]["risk_hint"], "ISSUER_EVENT_REVIEW")
        self.assertTrue(q["filings"][0]["official_url"].startswith("https://www.sec.gov/Archives/"))
        self.assertFalse(q["live_source_attested"])

    def test_sec_future_filing_never_leaks(self):
        q = r.sec_submission_evidence(sec_sample("2026-10-23T20:00:01Z"),
                                     symbol="CVLT", expected_cik=CIK, cutoff_utc=CUT)
        self.assertEqual(q["filings"], [])

    def test_sec_reject_mismatched_cik(self):
        with self.assertRaisesRegex(ValueError, "SEC_CIK_MISMATCH"):
            r.sec_submission_evidence(sec_sample(cik=7), symbol="CVLT",
                                      expected_cik=CIK, cutoff_utc=CUT)

    def test_sec_reject_mismatched_ticker(self):
        with self.assertRaisesRegex(ValueError, "SEC_TICKER_MISMATCH"):
            r.sec_submission_evidence(sec_sample(sym="LOGI"), symbol="CVLT",
                                      expected_cik=CIK, cutoff_utc=CUT)

    def test_sec_reject_naive_cutoff(self):
        with self.assertRaisesRegex(ValueError, "NAIVE_TIMESTAMP"):
            r.sec_submission_evidence(sec_sample(), symbol="CVLT",
                                      expected_cik=CIK, cutoff_utc="2026-10-23T20:00:00")

    def test_sec_untrusted_document(self):
        d = sec_sample()
        d["filings"]["recent"]["primaryDocument"][0] = "../exfiltrate"
        q = r.sec_submission_evidence(d, symbol="CVLT", expected_cik=CIK, cutoff_utc=CUT)
        self.assertEqual(q["filings"], [])
        self.assertEqual(q["unverifiable_rows"], 1)

    def test_sec_malformed_accession(self):
        d=sec_sample()
        d["filings"]["recent"]["accessionNumber"][0]="bogus"
        self.assertEqual(r.sec_submission_evidence(d,symbol="CVLT",expected_cik=CIK,
                         cutoff_utc=CUT)["unverifiable_rows"],1)

    def test_form4_purchase_only_research(self):
        x=r.form4_transaction_evidence(form4_sample(), expected_cik=CIK,
                   accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)
        self.assertEqual(x[0]["classification"],"PURCHASE_MARKET_OR_PRIVATE_REVIEW")
        self.assertEqual(x[0]["action"],"MANUAL_REVIEW_ONLY")
        self.assertEqual(x[0]["planned_10b5_1"],"UNKNOWN_REQUIRES_FULL_FILING_REVIEW")

    def test_form4_s_m_distinct(self):
        for code,expect in [("S","SALE_REVIEW"),
                            ("M","OPTION_EXERCISE_NOT_OPEN_MARKET_PURCHASE")]:
            with self.subTest(code=code):
                x=r.form4_transaction_evidence(form4_sample(code),expected_cik=CIK,
                      accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)
                self.assertEqual(x[0]["classification"],expect)

    def test_form4_amendment_is_not_fresh_insider_purchase(self):
        x=r.form4_transaction_evidence(form4_sample(),expected_cik=CIK,amended=True,
                 accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)
        self.assertTrue(x[0]["classification"].startswith("AMENDED_"))

    def test_form4_future_file_hidden(self):
        self.assertEqual(r.form4_transaction_evidence(form4_sample(),expected_cik=CIK,
            accepted_utc="2026-10-23T21:00:00Z",cutoff_utc=CUT),[])

    def test_form4_wrong_issuer(self):
        with self.assertRaisesRegex(ValueError,"FORM4_ISSUER_MISMATCH"):
            r.form4_transaction_evidence(form4_sample(cik="0007777777"),
                   expected_cik=CIK,accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)

    def test_form4_dtd_forbidden(self):
        with self.assertRaisesRegex(ValueError,"XML_ENTITY"):
            r.form4_transaction_evidence("<!DOCTYPE foo><ownershipDocument/>",
                expected_cik=CIK,accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)

    def test_fred_release_after_close_never_leaks(self):
        d={"observations":[{"date":"2026-10-22","realtime_start":"2026-10-23",
                            "realtime_end":"9999-12-31","value":"3.2"}]}
        q=r.fred_vintage_evidence(d,series_id="GDP",cutoff_utc=CUT,
             release_times={"2026-10-22|2026-10-23":"2026-10-23T20:00:01Z"})
        self.assertEqual(q["observations"],[])

    def test_fred_requires_explicit_release_time(self):
        d={"observations":[{"date":"2026-10-22","realtime_start":"2026-10-23",
                            "realtime_end":"9999-12-31","value":"3.2"}]}
        q=r.fred_vintage_evidence(d,series_id="GDP",cutoff_utc=CUT,release_times={})
        self.assertEqual(q["unverifiable_rows"],1)
        self.assertEqual(q["coverage"],"PARTIAL_UNKNOWN")

    def test_fred_missing_data_is_unknown(self):
        d={"observations":[{"date":"2026-10-22","realtime_start":"2026-10-23",
                            "realtime_end":"9999-12-31","value":"."}]}
        q=r.fred_vintage_evidence(d,series_id="GDP",cutoff_utc=CUT,release_times={})
        self.assertEqual(q["unverifiable_rows"],1)

    def test_fred_valid_vintage(self):
        d={"observations":[{"date":"2026-10-22","realtime_start":"2026-10-23",
                            "realtime_end":"9999-12-31","value":"3.2"}]}
        q=r.fred_vintage_evidence(d,series_id="GDP",cutoff_utc=CUT,
             release_times={"2026-10-22|2026-10-23":"2026-10-23T15:00:00Z"})
        self.assertEqual(q["observations"][0]["value"],3.2)
        self.assertFalse(q["live_source_attested"])

    def test_fred_negative_revision_guard(self):
        d={"observations":[{"date":"2026-10-22","realtime_start":"2026-10-23",
            "realtime_end":"2026-10-23","value":"2.5"},
            {"date":"2026-10-22","realtime_start":"2026-10-24",
            "realtime_end":"9999-12-31","value":"8.9"}]}
        q=r.fred_vintage_evidence(d,series_id="GDP",cutoff_utc=CUT,
             release_times={"2026-10-22|2026-10-23":"2026-10-23T15:00:00Z"})
        self.assertEqual([v["value"] for v in q["observations"]],[2.5])

    def test_13f_quarter_end_not_publication(self):
        x=r.holdings_13f_evidence(accession=ACCESSION,report_period="2026-09-30",
              accepted_utc="2026-11-10T18:00:00Z",cutoff_utc=CUT)
        self.assertFalse(x["available_asof_cutoff"])

    def test_default_record_never_produces_al(self):
        x=r.build_record(symbol="CVLT", expected_cik=CIK, cutoff_utc=CUT,
                         sec_payload=sec_sample())
        self.assertFalse(x["production_eligible"])
        self.assertIsNone(x["signal"])
        self.assertEqual(x["alerts_sent"],0)
        self.assertFalse(x["stop_target_modified"])

    def test_unprovided_sources_are_unknown(self):
        x=r.build_record(symbol="LOGI", expected_cik=CIK,cutoff_utc=CUT)
        self.assertEqual(x["sec"]["coverage"],"NOT_SUPPLIED")
        self.assertEqual(x["macro"]["coverage"],"NOT_SUPPLIED")

    def test_cli_fails_on_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"evidence.json"
            args=["--symbol","CVLT","--cik",CIK,"--cutoff-utc",CUT,"--output",str(path)]
            r.main(args)
            x=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(x["schema"], r.SCHEMA)
            with self.assertRaisesRegex(RuntimeError,"NO_OVERWRITE"):
                r.main(args)

if __name__=="__main__":
    unittest.main()
