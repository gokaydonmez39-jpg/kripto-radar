#!/usr/bin/env python3
"""Synthetic fixtures; no actual price/momentum or trading claims."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research_candidate_memory as mem
import research_candidate_episode_provenance as ep
from test_research_candidate_memory_admission import run,artifact,receipt


class EpisodeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.receipt=receipt()
        self.ledger,_=mem.propose(mem.empty_ledger(),self.receipt)
        self.run=run()
        self.artifact=artifact()
        self.clock=dt.datetime(2026,10,16,16,tzinfo=dt.timezone.utc)

    def build(self,*,ledger=None,receipt_=None,run_=None,artifact_=None,
              asof="2026-10-15",run_id=567):
        return ep.attest(
            self.ledger if ledger is None else ledger,
            self.receipt if receipt_ is None else receipt_,
            self.run if run_ is None else run_,
            self.artifact if artifact_ is None else artifact_,
            asof=asof,expected_run_id=run_id,now_utc=self.clock)

    def test_pit_episode_from_confirmed_run_and_next_open(self):
        x=self.build()
        self.assertEqual(x["symbolic_watch_count"],2)
        self.assertEqual(x["eligible_episodes"],2)
        self.assertEqual(x["rejected_late_episodes"],0)
        self.assertEqual(x["next_session"],"2026-10-16")
        self.assertEqual(x["next_market_open_utc"],
                         "2026-10-16T13:30:00+00:00")
        self.assertEqual(x["accepted_at_utc"],"2026-10-16T12:52:00+00:00")
        self.assertEqual([e["symbol"] for e in x["episodes"]],["MANH","WDAY"])
        for e in x["episodes"]:
            self.assertTrue(e["decision_timestamp_independently_authenticated_by_producer"])
            self.assertFalse(e["licensed_price_available"])
            self.assertFalse(e["issuer_class_identity_verified"])
            self.assertFalse(e["alpha_authority"])
            self.assertFalse(e["no_trade_or_fill"] is False)
            self.assertEqual(e["source_acceptance_sha256"],
                             mem.sha(self.receipt))
        self.assertFalse(x["forward_return_computed"])
        self.assertFalse(x["backtest_proven"])
        self.assertFalse(x["model_calibrated"])
        self.assertFalse(x["iphone_delivery_receipt_attested"])

    def test_late_acceptance_cannot_backdate_to_previous_day(self):
        r=copy.deepcopy(self.run)
        r["updated_at"]="2026-10-16T14:00:00Z"
        x=self.build(run_=r)
        self.assertEqual(x["eligible_episodes"],0)
        self.assertEqual(x["rejected_late_episodes"],2)
        self.assertEqual(x["accepted_at_utc"],"2026-10-16T14:00:00+00:00")
        for e in x["episodes"]:
            self.assertFalse(e["eligible_for_next_session_research_only"])
            self.assertEqual(e["ineligible_reason"],
                "ACCEPTED_TOO_LATE_FOR_NEXT_TRADING_SESSION")

    def test_intraday_created_forecast_blocked(self):
        r=copy.deepcopy(self.run)
        r["created_at"]="2026-10-15T20:05:00Z"
        r["updated_at"]="2026-10-15T20:20:00Z"
        with self.assertRaisesRegex(ValueError,"ACCEPTANCE_BEFORE_OFFICIAL_EOD_BUFFER"):
            self.build(run_=r)

    def test_reject_bad_source_and_fake_identity(self):
        r=copy.deepcopy(self.run)
        r["head_branch"]="some-private-fork"
        with self.assertRaises(ValueError):
            self.build(run_=r)
        a=copy.deepcopy(self.artifact)
        a["workflow_run"]["id"]=568
        with self.assertRaises(ValueError):
            self.build(artifact_=a)
        with self.assertRaisesRegex(ValueError,"RUN_ID_EVENT_MISMATCH"):
            self.build(run_id=999)

    def test_no_unpersisted_or_changed_pit_receipt(self):
        with self.assertRaisesRegex(ValueError,"EPISODE_NOT_ON_DURABLE_ACCEPTED_CHAIN"):
            self.build(ledger=mem.empty_ledger())
        modified=copy.deepcopy(self.receipt)
        modified["source_workflow_run_id"]=999
        with self.assertRaisesRegex(ValueError,"EPISODE_NOT_ON_DURABLE_ACCEPTED_CHAIN"):
            self.build(receipt_=modified)

    def test_sha_chain_tampering_rejected_before_episode(self):
        ledger=copy.deepcopy(self.ledger)
        ledger["entries"][0]["watch_count"]=9000
        with self.assertRaises(ValueError):
            self.build(ledger=ledger)

    def test_wrong_date_and_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            self.build(asof="2026-10-14")
        with self.assertRaisesRegex(ValueError,"EPISODE_CLOCK_NEEDS_UTC"):
            ep.attest(self.ledger,self.receipt,self.run,self.artifact,
                      asof="2026-10-15",expected_run_id=567,
                      now_utc=dt.datetime(2026,10,16,16))

    def test_idempotent_content_and_no_secret_prices(self):
        left=self.build()
        right=self.build()
        self.assertEqual(mem.canonical(left),mem.canonical(right))
        s=mem.canonical(left).decode()
        for forbidden in ("adjusted_close","market_cap","ohlcv",
                          "buy_signals","broker_order"):
            self.assertNotIn(forbidden,s)


if __name__=="__main__":
    unittest.main()
