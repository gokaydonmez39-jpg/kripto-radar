"""Synthetic-only ROKU merger lifecycle: no user episode data or real OHLC."""
import copy
import unittest

import alert_ledger_contract as events
import private_lifecycle as life
from performance_lab import private_flight_recorder as flight
from test_private_lifecycle import FakeApi, row
from private_sheet_writer import CANDIDATE_HEADER
import runner
from pathlib import Path

NEW_ASOF = "2026-11-10"
OLD_LAST = "2026-11-06"
ACTION_DAY = "2026-11-09"
SOURCE_RUN = "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/123456"
SOURCE_SCOPE = runner.get_scope(
    watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
    asof=NEW_ASOF)
SOURCE_NOTE = ("scopeSHA=" + runner.sha_symbols(SOURCE_SCOPE)
               + ";algorithmSHA=" + runner.analysis_fingerprint()
               + ";source_event=schedule;NO_ORDERS")


def fixture():
    api=FakeApi()
    # This example's 2026-11-05 synthetic AL and round prices are not user data.
    api.rows=[list(CANDIDATE_HEADER),row("2026-11-05",100.,90.,120.,1,symbol="ROKU")]
    api.scans=[list(api.scans[0]),[
        NEW_ASOF,"GitHub schedule VERIFIED IEX EOD",
        "477","477","477","0","TRUE","0",SOURCE_RUN,SOURCE_NOTE
    ]]
    return api


class ROKUCorporateLifecycleTests(unittest.TestCase):
    def test_new_type_is_known_event_and_terminal_with_no_fill(self):
        self.assertIn("CORPORATE_ACTION_REVIEW", events.TYPES)
        self.assertIn("CORPORATE_ACTION_REVIEW", flight.TERMINAL_CODES)

    def test_review_closes_synthetic_old_episode_without_roku_bar(self):
        api=fixture()
        def no_roku_request(symbols, day):
            self.assertNotIn("ROKU",symbols)
            self.assertEqual(day, NEW_ASOF)
            return {}
        result=life.synchronize(api,NEW_ASOF,no_roku_request)
        self.assertEqual(result["status"],"LIFECYCLE_READBACK_PASS")
        self.assertEqual(result["terminal_updates"],1)
        self.assertEqual(api.rows[1][:7],fixture().rows[1][:7])
        self.assertIn("CORPORATE_ACTION_REVIEW",api.rows[1][7])
        self.assertEqual(api.rows[1][8],ACTION_DAY)
        self.assertEqual(api.rows[1][9],"CORPORATE_ACTION_REVIEW")
        self.assertEqual(api.rows[1][10],"")
        self.assertEqual(len(api.alert_rows),2)
        entry=api.alert_rows[1]
        self.assertEqual(entry[4],ACTION_DAY)
        self.assertEqual(entry[5],"CORPORATE_ACTION_REVIEW")
        self.assertEqual(entry[7],"")
        self.assertEqual(entry[17],life.EVENT_PENDING)
        self.assertFalse(result["device_ack"])
        self.assertIn("eca2026-806",entry[19])

    def test_replay_is_idempotent_no_double_event_or_write(self):
        api=fixture()
        life.synchronize(api,NEW_ASOF,lambda symbols,day:{})
        writes=api.writes
        status=life.synchronize(api,NEW_ASOF,
                lambda s,d: (_ for _ in ()).throw(AssertionError("rerun not needed")))
        self.assertEqual(status["evaluated"],0)
        self.assertEqual(api.writes,writes)
        self.assertEqual(len(api.alert_rows),2)

    def test_missing_verified_current_eod_blocks_entire_transaction(self):
        api=fixture()
        api.scans[-1][4]="476"
        with self.assertRaisesRegex(ValueError,"LIFECYCLE_EOD_NOT_FINAL_477"):
            life.synchronize(api,NEW_ASOF,lambda s,d:{})
        self.assertEqual(api.writes,0)

    def test_earlier_unverified_roku_sessions_fail_closed(self):
        api=fixture()
        api.rows[1][7]="AÇIK • 0/15 SEANS"
        with self.assertRaisesRegex(ValueError,"CORPORATE_ACTION"):
            life.synchronize(api,NEW_ASOF,lambda s,d:{})
        self.assertEqual(api.writes,0)

    def test_original_roku_levels_and_notification_fields_immutable(self):
        api=fixture()
        before=copy.deepcopy(api.rows[1])
        life.synchronize(api,NEW_ASOF,lambda s,d:{})
        self.assertEqual(api.rows[1][:7],before[:7])
        self.assertEqual(api.rows[1][11:],before[11:])

    def test_event_key_is_valid_and_not_duplicate_on_replay(self):
        api=fixture()
        life.synchronize(api,NEW_ASOF,lambda s,d:{})
        self.assertEqual(set(events.parse_ledger(api.alert_rows)),
                         {api.alert_rows[1][0]})
        with self.assertRaisesRegex(events.LedgerRefused,
                                    "EVENT_ALREADY_RECORDED"):
            events.verify_first_reservation(api.alert_rows,
                                            api.alert_rows,[api.alert_rows[1][0]])

    def test_no_policy_backfill_to_9_nov(self):
        api=fixture()
        with self.assertRaises(ValueError):
            life.build_updates(api.rows,ACTION_DAY,lambda s,d:{})
        self.assertEqual(api.writes,0)

    def test_issuer_ambiguity_cannot_join_roku_with_foxa_or_gntx(self):
        api=fixture()
        seen=[]
        def strict_reader(symbols,day):
            seen.extend(symbols)
            return {}
        life.build_updates(api.rows,NEW_ASOF,strict_reader)
        self.assertNotIn("ROKU",seen)
        self.assertNotIn("FOXA",seen)
        self.assertNotIn("GNTX",seen)


if __name__=="__main__":
    unittest.main()
