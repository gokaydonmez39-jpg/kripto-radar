#!/usr/bin/env python3
"""Synthetic fixtures only. No forecasts or future price facts are claimed."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research_candidate_memory as m
import research_candidate_outcome_audit as o
from test_research_candidate_memory import receipt
from test_research_candidate_memory_admission import run,artifact
import research_candidate_episode_provenance as ep_source

ASOF="2026-10-15"
AFTER="2026-12-05T00:00:00Z"


def build_provenance(ledger):
    # Authenticated-GitHub-shaped TEST FIXTURES ONLY. No actual API proof.
    r=receipt(ASOF,{"MANH":["B","D"]})
    return ep_source.attest(
        ledger,r,run(),artifact(),asof=ASOF,expected_run_id=567,
        now_utc=dt.datetime(2026,12,5,tzinfo=dt.timezone.utc))


def fixture():
    r=receipt(ASOF,{"MANH":["B","D"]})
    ledger,_=m.propose(m.empty_ledger(),r)
    ep=build_provenance(ledger)["episodes"][0]
    future,close,_=o.session_schedule(ASOF)
    def rows(identity,delta):
        return [{
            "issuer_class_key":identity,"session":day,
            "source_authorized":True,"regular_session_complete":True,
            "split_adjustment_verified":True,
            "source_sha256":"e"*64,
            "adjusted_close":100*(1+delta*(i+1)),
            "available_at_utc":(close[day]+dt.timedelta(minutes=35)).isoformat(),
        } for i,day in enumerate(future)]
    source={
        "schema":"XRAY_RESEARCH_AUTHORIZED_OUTCOME_BARS_V1",
        "symbol":"MANH","asof_et":ASOF,
        "rights_derived_metrics_permitted":True,
        "historical_universe_includes_delisted":True,
        "issuer_class_identity_verified":True,
        "corporate_action_adjustment_verified":True,
        "execution":"NONE","real_money":"NO-GO",
        "issuer_class_key":"CIK:MANH-FIXTURE",
        "benchmark_class_key":"ETF:QQQ-FIXTURE",
        "market_data_source_sha256":"f"*64,
        "reference_session":ASOF,
        "benchmark_reference_session":ASOF,
        "reference_adjusted_close":100,
        "benchmark_reference_adjusted_close":100,
        "reference_available_at_utc":"2026-10-15T20:30:00Z",
        "benchmark_reference_available_at_utc":"2026-10-15T20:30:00Z",
        "stock_future_bars":rows("CIK:MANH-FIXTURE",0.01),
        "benchmark_future_bars":rows("ETF:QQQ-FIXTURE",0.005)
    }
    return ledger,ep,source


class OutcomeDiagnosticsTests(unittest.TestCase):
    def run_audit(self,ledger=None,ep=None,source=None,**kwargs):
        a,b,c=fixture()
        return o.audit(a if ledger is None else ledger,
                       b if ep is None else ep,
                       c if source is None else source,
                       kwargs.get("provenance") if "provenance" in kwargs
                           else build_provenance(a),
                       observed_at_utc=kwargs.get("now",AFTER))

    def test_all_five_horizons_mathematically_exact(self):
        r=self.run_audit()
        self.assertEqual(set(r["horizons"]),{"1","3","5","10","20"})
        for n in (1,3,5,10,20):
            h=r["horizons"][str(n)]
            self.assertTrue(h["status"].startswith("COMPLETED"))
            self.assertAlmostEqual(h["forward_return_pct"],float(n))
            self.assertAlmostEqual(h["benchmark_return_pct"],n/2)
            self.assertAlmostEqual(h["excess_return_pct_points"],n/2)
        self.assertFalse(r["model_calibrated"])
        self.assertFalse(r["backtest_proven"])
        self.assertFalse(r["primary_alpha_authority"])
        self.assertFalse(r["raw_prices_persisted"])
        self.assertNotIn("adjusted_close",str(r))

    def test_backdated_episode_decision_is_rejected(self):
        l,e,s=fixture()
        e["candidate_decision_at_utc"]="2026-10-15T21:00:00Z"
        with self.assertRaisesRegex(ValueError,
                    "EPISODE_NOT_IDENTICAL_TO_BOUND_PROVENANCE"):
            self.run_audit(l,e,s)

    def test_provenance_must_be_supplied_not_assumed(self):
        l,e,s=fixture()
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_EPISODE_PROVENANCE_HEADER"):
            self.run_audit(l,e,s,provenance=None)

    def test_exact_durable_hash_and_acceptance_run_enforced(self):
        l,e,s=fixture()
        p=build_provenance(l)
        p["durable_ledger_entry_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_EPISODE_PROVENANCE_HEADER"):
            self.run_audit(l,e,s,provenance=p)
        p=build_provenance(l)
        p["acceptance_workflow_run_id"]=999
        with self.assertRaisesRegex(ValueError,"FORGED_PROVENANCE_EPISODE_ROW"):
            self.run_audit(l,e,s,provenance=p)

    def test_source_after_next_open_never_produces_retrospective_return(self):
        l,e,s=fixture()
        p=build_provenance(l)
        p["accepted_at_utc"]="2026-10-16T15:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"PROVENANCE_OFFICIAL_TIME_DRIFT_OR_LATE"):
            self.run_audit(l,e,s,provenance=p)

    def test_provenance_forged_price_and_identity_status_rejected(self):
        for key in ("licensed_price_available",
                    "issuer_class_identity_verified","alpha_authority",
                    "github_run_api_identity_authenticated_inside_module"):
            with self.subTest(key=key):
                l,e,s=fixture()
                p=build_provenance(l)
                p["episodes"][0][key]=True
                with self.assertRaisesRegex(ValueError,
                        "FORGED_PROVENANCE_EPISODE_ROW"):
                    self.run_audit(l,e,s,provenance=p)

    def test_future_bar_before_eod_buffer_rejected(self):
        l,e,s=fixture()
        d,closes,_=o.session_schedule(ASOF)
        s["stock_future_bars"][0]["available_at_utc"]=(
            closes[d[0]]+dt.timedelta(minutes=10)).isoformat()
        with self.assertRaisesRegex(ValueError,"LEAKED_OR_FUTURE_STOCK"):
            self.run_audit(l,e,s)

    def test_missing_future_is_unknown_and_not_zero(self):
        l,e,s=fixture()
        s["stock_future_bars"].pop(1)
        r=self.run_audit(l,e,s)
        self.assertTrue(r["horizons"]["1"]["status"].startswith("COMPLETED"))
        for h in ("3","5","10","20"):
            x=r["horizons"][h]
            self.assertEqual(x["status"],
                "UNKNOWN_MISSING_COMPLETE_COMPARABLE_SESSION")
            self.assertIsNone(x["forward_return_pct"])

    def test_reference_must_match_exact_asof(self):
        l,e,s=fixture()
        s["reference_session"]="2026-10-14"
        with self.assertRaisesRegex(ValueError,"REFERENCE_ASOF_SESSION_MISMATCH"):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        s["benchmark_reference_session"]="2026-10-14"
        with self.assertRaisesRegex(ValueError,"REFERENCE_ASOF_SESSION_MISMATCH"):
            self.run_audit(l,e,s)

    def test_future_reference_leakage(self):
        l,e,s=fixture()
        e["candidate_decision_at_utc"]="2026-10-16T15:00:00Z"
        with self.assertRaisesRegex(ValueError,"DECISION_LOOKAHEAD"):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        s["reference_available_at_utc"]="2026-10-16T13:00:00Z"
        with self.assertRaisesRegex(ValueError,"REFERENCE_KNOWN_AFTER_DECISION"):
            self.run_audit(l,e,s)

    def test_future_bar_unavailable_or_timestamp_forced(self):
        l,e,s=fixture()
        future,close,_=o.session_schedule(ASOF)
        s["stock_future_bars"][0]["available_at_utc"]=(
            close[future[0]]-dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"LEAKED_OR_FUTURE_STOCK"):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        with self.assertRaisesRegex(ValueError,"LEAKED_OR_FUTURE_STOCK"):
            self.run_audit(l,e,s,now="2026-10-16T14:00:00Z")

    def test_no_survivorship_or_permission_bypass(self):
        for key in ("rights_derived_metrics_permitted",
                    "historical_universe_includes_delisted",
                    "issuer_class_identity_verified",
                    "corporate_action_adjustment_verified"):
            with self.subTest(key=key):
                l,e,s=fixture()
                s[key]=False
                with self.assertRaises(ValueError):
                    self.run_audit(l,e,s)
        l,e,s=fixture()
        s["execution"]="BROKER"
        with self.assertRaises(ValueError):
            self.run_audit(l,e,s)

    def test_corporate_action_wrong_security_and_bar_conflict(self):
        l,e,s=fixture()
        s["stock_future_bars"][0]["split_adjustment_verified"]=False
        with self.assertRaises(ValueError):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        s["stock_future_bars"][0]["issuer_class_key"]="ANOTHER_SHARE_CLASS"
        with self.assertRaises(ValueError):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        s["stock_future_bars"].pop(-1)
        s["stock_future_bars"].append(copy.deepcopy(s["stock_future_bars"][0]))
        with self.assertRaises(ValueError):
            self.run_audit(l,e,s)

    def test_episode_forgery_not_from_accepted_source(self):
        l,e,s=fixture()
        e["source_acceptance_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"EPISODE_NOT_IN_ACCEPTED"):
            self.run_audit(l,e,s)
        l,e,s=fixture()
        e["families"]=["A"]
        with self.assertRaisesRegex(ValueError,"EPISODE_FAMILY_DRIFT"):
            self.run_audit(l,e,s)

    def test_calendar_holidays_are_official_sessions_only(self):
        dates,_,_=o.session_schedule(ASOF)
        self.assertEqual(dates[0],"2026-10-16")
        self.assertEqual(len(dates),20)
        self.assertNotIn("2026-10-17",dates)
        self.assertNotIn("2026-11-26",dates)


if __name__=="__main__":
    unittest.main()
