import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import research_evidence as r
import research_source_events as events
from research_oos_admission import assess_oos_readiness

CUT = "2026-10-23T20:00:00Z"
CIK = "0001234567"
ACCESSION = "0001234567-26-000001"


class ResearchOOSAdmissionTests(unittest.TestCase):
    def packet(self):
        from datetime import date, timedelta
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat()
                for i in range(110)]
        folds = [{"start":days[i], "end":days[i+29]} for i in (0, 35, 70)]
        rows = []
        for fi, offset in enumerate((0, 35, 70)):
            for i in range(60):
                signal = offset + i % 10
                rows.append({"id":f"episode-{fi}-{i}", "signal_session":days[signal],
                             "last_verified_session":days[signal+15],
                             "pit_coverage_proven":True,
                             "event_present":i < 30, "stop_contact":i % 3 == 0})
        return days, folds, rows

    def assess(self, days, folds, rows):
        return assess_oos_readiness(rows, official_sessions=days, folds=folds)

    def test_balanced_three_folds_is_structural_only(self):
        days, folds, rows = self.packet()
        q = self.assess(days, folds, rows)
        self.assertEqual(q["status"], "STRUCTURAL_READY_FOR_RESEARCH")
        self.assertEqual(q["eligible_episodes"], 180)
        self.assertEqual(q["necessary_unique_floor"], 180)
        self.assertEqual(q, self.assess(days, folds, list(reversed(rows))))
        self.assertFalse(q["production_eligible"])
        self.assertFalse(q["performance_improvement_proven"])

    def test_missing_provenance_or_late_outcome_cannot_fill_group(self):
        days, folds, rows = self.packet()
        rows[0]["pit_coverage_proven"] = False
        rows[-1]["last_verified_session"] = days[-1]
        q = self.assess(days, folds, rows)
        self.assertEqual(q["status"], "HOLD_INSUFFICIENT_OOS_COHORT")
        self.assertEqual(q["excluded"]["unproved_coverage"], 1)
        self.assertEqual(q["excluded"]["invalid_outcome_window"], 1)

    def test_fold_edges_purge_overlapping_outcomes(self):
        days, folds, rows = self.packet()
        rows[0].update(signal_session=days[21], last_verified_session=days[36])
        q = self.assess(days, folds, rows)
        self.assertEqual(q["excluded"]["overlapping_outcome"], 1)
        self.assertEqual(q["folds"][0]["event"], 29)
        self.assertEqual(q["status"], "HOLD_INSUFFICIENT_OOS_COHORT")

    def test_duplicate_and_overlapping_or_reordered_folds_rejected(self):
        days, folds, rows = self.packet()
        with self.assertRaisesRegex(ValueError, "OOS_DUPLICATE_EPISODE"):
            self.assess(days, folds, rows + [rows[0]])
        for f in ([folds[0], {"start":days[29], "end":days[62]}, folds[2]],
                  list(reversed(folds)), folds[:2]):
            with self.assertRaisesRegex(ValueError, "OOS_INVALID_FOLDS"):
                self.assess(days, f, rows)

    def test_event_flag_unknown_not_no_event(self):
        days, folds, rows = self.packet()
        rows[-1]["event_present"] = None
        q = self.assess(days, folds, rows)
        self.assertEqual(q["excluded"]["unproved_coverage"], 1)
        self.assertEqual(q["folds"][-1]["no_event"], 29)


class ResearchSourceClockTests(unittest.TestCase):
    def sec(self, **changes):
        return {"source":"SEC", "kind":"8-K", "item":"2.02",
                "status":"OBSERVED", "issuer_cik":"0001559720",
                "accession":"0001193125-26-449727",
                "accepted_at":"2026-11-05T21:02:09Z",
                "observed_at":"2026-11-05T21:03:00Z",
                "url":"https://www.sec.gov/Archives/edgar/data/1559720/000119312526449727/0001193125-26-449727-index.htm",
                **changes}

    def bls(self, **changes):
        return {"source":"BLS", "kind":"CPI", "event_id":"CPI-2026-10",
                "status":"SCHEDULED", "observed_at":"2026-11-09T20:00:00Z",
                "scheduled_at":"2026-11-10T13:30:00Z",
                "url":"https://www.bls.gov/schedule/2026/11_sched_list.htm",
                **changes}

    def feed(self, rows, cutoff):
        return events.event_evidence(rows, cutoff_utc=cutoff)

    def test_after_close_sec_event_not_visible_at_price_cutoff(self):
        row = self.sec()
        for cutoff in ("2026-11-05T21:00:00Z", "2026-11-05T21:02:09Z"):
            self.assertEqual(self.feed([row], cutoff)["events"], [])
        q = self.feed([row], "2026-11-05T21:03:00Z")
        self.assertEqual(q["events"][0]["label"], "SEC_EARNINGS_DISCLOSURE")
        self.assertFalse(q["events"][0]["first_publication_proven"])
        self.assertFalse(q["production_eligible"])
        self.assertFalse(q["live_source_attested"])
        self.assertFalse(q["history_complete_proven"])
        self.assertEqual(q["alerts_sent"], 0)

    def test_general_sec_form_not_automatically_earnings(self):
        q = self.feed([self.sec(item=None)], "2026-11-06T01:00:00Z")
        self.assertEqual(q["events"][0]["label"], "SEC_FILING_REVIEW")

    def test_pipeline_preserves_no_authority_and_rejects_cross_issuer(self):
        cutoff = "2026-11-06T01:00:00Z"
        record = r.build_record(symbol="ABNB", expected_cik="0001559720",
                                cutoff_utc=cutoff, source_event_rows=[self.sec()])
        self.assertEqual(len(record["official_source_events"]["events"]), 1)
        self.assertFalse(record["production_eligible"])
        self.assertIsNone(record["signal"])
        self.assertFalse(record["stop_target_modified"])
        self.assertEqual(record["alerts_sent"], 0)
        with self.assertRaisesRegex(ValueError, "SOURCE_EVENT_ISSUER_MISMATCH"):
            r.build_record(symbol="ABNB", expected_cik="0000000123",
                           cutoff_utc=cutoff, source_event_rows=[self.sec()])

    def test_calendar_and_release_are_distinct_at_each_cutoff(self):
        planned = self.bls()
        actual = self.bls(status="PUBLISHED", published_at="2026-11-10T08:30:00-05:00",
                          observed_at="2026-11-10T13:30:10Z",
                          url="https://www.bls.gov/news.release/cpi.nr0.htm")
        for cutoff in ("2026-11-10T13:29:59Z", "2026-11-10T13:30:00Z"):
            q = self.feed([actual, planned], cutoff)
            self.assertEqual(q["events"][0]["status"], "SCHEDULED")
            self.assertIsNone(q["events"][0]["published_at_utc"])
        q = self.feed([planned, actual], "2026-11-10T13:30:10Z")
        self.assertEqual(q["events"][0]["published_at_utc"], "2026-11-10T13:30:00+00:00")
        self.assertEqual(q["events"][0]["status"], "PUBLISHED")
        q = self.feed([planned, actual, self.bls(observed_at="2026-11-11T12:00:00Z")],
                      "2026-11-11T13:00:00Z")
        self.assertEqual(q["events"][0]["status"], "PUBLISHED")

    def test_reject_host_identity_future_clock_and_calendar_promotion(self):
        bad = [
            self.sec(url="https://www.sec.gov.example/Archives/edgar/data/1559720/x"),
            self.sec(issuer_cik="0000000123"),
            self.sec(url=self.sec()["url"].replace("edgar/", "edgar/../")),
            self.sec(accepted_at="2026-11-06T21:00:00Z"),
            self.sec(observed_at="2026-11-05T21:00:00"),
            self.bls(status="PUBLISHED", published_at="2026-11-09T19:00:00Z"),
            self.bls(published_at="2026-11-09T19:00:00Z"),
            self.bls(status="PUBLISHED", published_at="2026-11-10T13:30:00Z",
                     url="https://www.bls.gov/news.release/cpi.nr0.htm"),
        ]
        q = self.feed(bad, "2026-11-11T13:00:00Z")
        self.assertEqual(q["events"], [])
        self.assertEqual(q["unverifiable_rows"], len(bad))
        self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")

    def test_distinct_fomc_kinds_and_duplicate_conflict(self):
        plan = {"source":"FED", "kind":"FOMC_STATEMENT", "event_id":"meeting-2026-12",
                "status":"SCHEDULED", "observed_at":"2026-11-09T20:00:00Z",
                "scheduled_at":"2026-12-09T19:00:00Z",
                "url":"https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"}
        press = {**plan, "kind":"FOMC_PRESS_CONFERENCE",
                 "scheduled_at":"2026-12-09T19:30:00Z"}
        minutes = {**plan, "kind":"FOMC_MINUTES", "scheduled_at":"2026-12-30T19:00:00Z"}
        cutoff = "2026-11-11T00:00:00Z"
        self.assertEqual(len(self.feed([plan, plan, press, minutes], cutoff)["events"]), 3)
        disputed = {**plan, "scheduled_at":"2026-12-09T18:00:00Z"}
        a = self.feed([plan, disputed, press], cutoff)
        self.assertEqual(a, self.feed([disputed, press, plan], cutoff))
        self.assertEqual(a["quarantined_events"], 1)
        self.assertEqual([x["kind"] for x in a["events"]], ["FOMC_PRESS_CONFERENCE"])

    def test_immutable_publication_clock_cannot_be_replaced_by_later_row(self):
        a = self.bls(status="PUBLISHED", published_at="2026-11-10T13:30:00Z",
                     observed_at="2026-11-10T13:30:10Z",
                     url="https://www.bls.gov/news.release/cpi.nr0.htm")
        b = {**a, "published_at":"2026-11-10T13:30:01Z",
             "observed_at":"2026-11-10T14:30:10Z"}
        self.assertEqual(len(self.feed([a,b], "2026-11-10T13:30:10Z")["events"]), 1)
        q = self.feed([b,a], "2026-11-10T14:30:10Z")
        self.assertEqual(q["events"], [])
        self.assertEqual(q["quarantined_events"], 1)

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

    def _fred_intraday(self, rows, clock, overrides=None):
        releases = {
            "2026-09-01|2026-10-13": "2026-10-13T12:30:00Z",
            "2026-09-01|2026-11-10": "2026-11-10T13:30:00Z",
        }
        if overrides is not None:
            releases = overrides
        return r.fred_vintage_evidence(
            {"observations": rows}, series_id="SYNTHETIC",
            cutoff_utc=clock, release_times=releases)

    def _fred_intraday_rows(self):
        return [
            {"date":"2026-09-01", "realtime_start":"2026-10-13",
             "realtime_end":"2026-11-09", "value":"100"},
            {"date":"2026-09-01", "realtime_start":"2026-11-10",
             "realtime_end":"9999-12-31", "value":"101"},
        ]

    def test_fred_revision_day_last_known_before_release_and_new_at_boundary(self):
        old, new = self._fred_intraday_rows()
        for clock, expected in [("2026-11-10T13:29:59Z", 100.0),
                                ("2026-11-10T13:30:00Z", 101.0),
                                ("2026-11-10T13:30:01Z", 101.0)]:
            with self.subTest(clock=clock):
                for rows in ([old, new], [new, old]):
                    q = self._fred_intraday(rows, clock)
                    self.assertEqual([v["value"] for v in q["observations"]], [expected])
                    self.assertFalse(q["live_source_attested"])

    def test_fred_conflict_is_quarantined_in_both_orders(self):
        old, new = self._fred_intraday_rows()
        different = {**new, "value":"111"}
        a = self._fred_intraday([old,new,different], "2026-11-10T13:30:01Z")
        b = self._fred_intraday([old,different,new], "2026-11-10T13:30:01Z")
        self.assertEqual(a, b)
        self.assertEqual(a["observations"], [])
        self.assertEqual(a["coverage"], "PARTIAL_UNKNOWN")
        self.assertEqual(a["quarantined_observations"], 1)

    def test_fred_duplicate_identical_no_row_order_dependency(self):
        old, new = self._fred_intraday_rows()
        clock = "2026-11-10T13:30:01Z"
        self.assertEqual(self._fred_intraday([old,new,new], clock),
                         self._fred_intraday([new,old], clock))

    def test_fred_conflict_cannot_hide_in_float_rounding(self):
        old, new = self._fred_intraday_rows()
        a = {**new, "value":"101.00000000000000000001"}
        b = {**new, "value":"101.00000000000000000002"}
        for rows in ([old,a,b], [b,a,old]):
            q = self._fred_intraday(rows, "2026-11-10T13:30:01Z")
            self.assertEqual(q["observations"], [])
            self.assertEqual(q["quarantined_observations"], 1)

    def test_fred_signed_zero_is_order_independent(self):
        old, new = self._fred_intraday_rows()
        a, b = {**new, "value":"-0.0"}, {**new, "value":"0"}
        clock = "2026-11-10T13:30:01Z"
        q = self._fred_intraday([old,a,b], clock)
        self.assertEqual(q, self._fred_intraday([b,a,old], clock))
        self.assertEqual([v["value"] for v in q["observations"]], [0.0])
        self.assertNotIn("-0.0", json.dumps(q))

    def test_fred_never_extends_previous_vintage_across_unproved_boundary(self):
        old, new = self._fred_intraday_rows()
        clock = "2026-11-10T13:29:59Z"
        q = self._fred_intraday([old,new], clock,
               {"2026-09-01|2026-10-13":"2026-10-13T12:30:00Z"})
        self.assertEqual(q["observations"], [])
        self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")
        q = self._fred_intraday([{**old,"realtime_end":"2026-11-08"},new], clock)
        self.assertEqual(q["observations"], [])
        self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")
        q = self._fred_intraday([old], clock)
        self.assertEqual(q["observations"], [])
        self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")
        q = self._fred_intraday([old], "2026-11-12T13:30:00Z")
        self.assertEqual(q["observations"], [])
        self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")

    def test_fred_stale_missing_value_and_overlapping_versions_do_not_restore_old(self):
        old, new = self._fred_intraday_rows()
        clock = "2026-11-10T13:30:01Z"
        for rows in ([old,{**new,"value":"."}],
                     [{**old,"realtime_end":"2026-11-10"},new],
                     [old,{**new,"realtime_end":"2026-11-09"}]):
            with self.subTest(rows=rows):
                q = self._fred_intraday(rows, clock)
                self.assertEqual(q["observations"], [])
                self.assertEqual(q["coverage"], "PARTIAL_UNKNOWN")

    def test_fred_unavailable_conflict_does_not_change_pre_release_selection(self):
        old, new = self._fred_intraday_rows()
        q = self._fred_intraday([old,new,{**new,"value":"111"}],
                                 "2026-11-10T13:29:59Z")
        self.assertEqual([v["value"] for v in q["observations"]], [100.0])

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

    def test_49_source_policy_manifest_closed_by_default(self):
        path = Path(__file__).with_name("research_sources_v1.json")
        d = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(d["schema"], "XRAY_49_SOURCE_POLICY_MANIFEST_V1")
        self.assertEqual(d["source_count"], len(d["sources"]))
        self.assertEqual(len(d["sources"]), 49)
        self.assertEqual([s["no"] for s in d["sources"]], list(range(1, 50)))
        from collections import Counter
        self.assertEqual(Counter(s["priority"] for s in d["sources"]),
                         {"P0":1, "P1":7, "P2":24, "P3":17})
        self.assertTrue(all(not s["unattended_collection_enabled"] for s in d["sources"]))
        self.assertTrue(all(not s["can_generate_buy_signal"] for s in d["sources"]))
        self.assertTrue(all(not s["can_override_r92_gates"] for s in d["sources"]))
        self.assertFalse(d["global_controls"]["enabled_for_production"])

    def test_form4_transaction_date_is_not_filing_date(self):
        x=r.form4_transaction_evidence(form4_sample(),
                  expected_cik=CIK,accepted_utc="2026-10-23T15:00:00Z",cutoff_utc=CUT)
        self.assertEqual(x[0]["transaction_date"],"2026-10-22")
        self.assertEqual(x[0]["accepted_utc"],"2026-10-23T15:00:00+00:00")

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
