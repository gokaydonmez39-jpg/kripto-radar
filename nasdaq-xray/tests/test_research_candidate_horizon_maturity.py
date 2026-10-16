#!/usr/bin/env python3
"""Official-calendar maturity synthetic regression, no paid market data."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research_candidate_horizon_maturity as maturity
from test_research_candidate_episode_provenance import EpisodeProvenanceTests

UTC=dt.timezone.utc


def proven(late=False):
    f=EpisodeProvenanceTests()
    f.setUp()
    if late:
        r=copy.deepcopy(f.run)
        r["updated_at"]="2026-10-16T14:00:00Z"
        return f.build(run_=r)
    return f.build()


class HorizonMaturityTests(unittest.TestCase):
    def test_not_completed_before_friday_official_eod(self):
        a=maturity.summarize(proven(),now_utc=dt.datetime(2026,10,16,19,59,tzinfo=UTC))
        self.assertEqual(a["eligible_episode_count"],2)
        self.assertEqual(len(a["episodes"]),2)
        for e in a["episodes"]:
            self.assertEqual(e["horizons"]["1"]["target_session"],"2026-10-16")
            self.assertEqual(e["horizons"]["1"]["earliest_label_review_utc"],
                             "2026-10-16T20:30:00+00:00")
            for h in ("1","3","5","10","20"):
                x=e["horizons"][h]
                self.assertEqual(x["status"],"NOT_YET_MATURE")
                self.assertIsNone(x["forward_return_pct"])
                self.assertIsNone(x["excess_return_pct_points"])
        self.assertFalse(a["realized_return_computed"])
        self.assertFalse(a["alpha_authority"])

    def test_first_threshold_exact_buffer_not_calendar_midnight(self):
        before=maturity.summarize(proven(),
             now_utc=dt.datetime(2026,10,16,20,29,59,tzinfo=UTC))
        after=maturity.summarize(proven(),
             now_utc=dt.datetime(2026,10,16,20,30,tzinfo=UTC))
        self.assertEqual(before["episodes"][0]["horizons"]["1"]["status"],
                         "NOT_YET_MATURE")
        self.assertEqual(after["episodes"][0]["horizons"]["1"]["status"],
                         "MATURE_BY_CALENDAR_OUTCOME_SOURCE_STILL_UNKNOWN")
        self.assertEqual(after["episodes"][0]["horizons"]["3"]["status"],
                         "NOT_YET_MATURE")

    def test_mature_twenty_sessions_is_never_return_or_alpha(self):
        x=maturity.summarize(proven(),
             now_utc=dt.datetime(2027,1,3,23,tzinfo=UTC))
        for entry in x["episodes"]:
            for h in ("1","3","5","10","20"):
                e=entry["horizons"][h]
                self.assertEqual(e["status"],
                                 "MATURE_BY_CALENDAR_OUTCOME_SOURCE_STILL_UNKNOWN")
                self.assertIsNone(e["benchmark_return_pct"])
        self.assertFalse(x["outcome_sources_verified"])
        self.assertFalse(x["model_calibrated"])
        self.assertFalse(x["model_trained"])
        self.assertFalse(x["r92_authority"])

    def test_late_evidence_never_enters_retrospective_sample(self):
        x=maturity.summarize(proven(True),
             now_utc=dt.datetime(2027,1,3,23,tzinfo=UTC))
        self.assertEqual(x["eligible_episode_count"],0)
        for entry in x["episodes"]:
            self.assertEqual(entry["horizons"]["20"]["status"],
                             "INELIGIBLE_ACCEPTED_AFTER_NEXT_OPEN")

    def test_al_and_source_forgery_rejected(self):
        for target,path,value in (
            ("root","alpha_authority",True),
            ("root","forward_return_computed",True),
            ("root","model_calibrated",True),
            ("child","alpha_authority",True),
            ("child","licensed_price_available",True),
            ("child","real_money","GO"),
        ):
            with self.subTest(target=target,path=path):
                p=proven()
                if target=="root":p[path]=value
                else:p["episodes"][0][path]=value
                with self.assertRaises(ValueError):
                    maturity.summarize(p,now_utc=dt.datetime(
                        2026,10,16,16,tzinfo=UTC))

    def test_duplicate_or_mismatched_episodes_rejected(self):
        p=proven()
        p["episodes"][1]["symbol"]=p["episodes"][0]["symbol"]
        with self.assertRaises(ValueError):
            maturity.summarize(p,now_utc=dt.datetime(2026,10,16,16,tzinfo=UTC))
        p=proven()
        p["eligible_episodes"]=1
        with self.assertRaises(ValueError):
            maturity.summarize(p,now_utc=dt.datetime(2026,10,16,16,tzinfo=UTC))

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,"MATURITY_REQUIRES_AWARE_UTC"):
            maturity.summarize(proven(),now_utc=dt.datetime(2026,10,16,16))


if __name__=="__main__":
    unittest.main()
