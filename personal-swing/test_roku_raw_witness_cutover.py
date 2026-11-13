"""Synthetic ROKU historical raw-IEX witness: do not fabricate post-delisting bar."""
import copy
import unittest
import exchange_calendars as ec

import raw_corporate_action_witness as witness
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER

ASOF="2026-11-10"
OPENED="2026-11-05"
LAST="2026-11-06"
DELIST="2026-11-09"
CAL=ec.get_calendar("XNAS")
START=CAL.session_offset(CAL.date_to_session(OPENED),-51)
DAYS=[str(x.date()) for x in CAL.sessions_in_range(START,LAST)]


def fixture(kind="approved"):
    status="KAPALI • CORPORATE_ACTION_REVIEW • 1/15 SEANS"
    event_date,code=DELIST,"CORPORATE_ACTION_REVIEW"
    if kind=="open":status="AÇIK • 1/15 SEANS";event_date,code="",""
    if kind=="wrongdate":event_date=ASOF
    if kind=="wrongcode":code="STOP_TOUCHED"
    candidates=[list(CANDIDATE_HEADER),
       [OPENED+"|ROKU",OPENED,"ROKU","TEKNIK AL",
        "100","95","110",status,event_date,code,
        "","PRESERVE","PRESERVE_NOTE"]]
    scans=[list(SCAN_HEADER),
      [ASOF,"GitHub schedule VERIFIED IEX EOD","477","477",
       "477","0","TRUE","0","https://github.com/example/example/actions/runs/123","source proof synthetic"]]
    bars={"ROKU":[{"timestamp":d+"T04:00:00+00:00",
                   "open":100.,"high":102.,"low":98.,
                   "close":100.,"volume":1200.} for d in DAYS]}
    return candidates,scans,bars


class RawROKUPITTests(unittest.TestCase):
    def test_last_real_roku_day_is_audit_end_and_not_current_price(self):
        c,s,b=fixture()
        old=copy.deepcopy(b)
        out=witness.inspect(c,s,b,ASOF)
        self.assertEqual(out["state"],witness.HISTORICAL_TERMINAL_CENSORED)
        self.assertEqual(witness.exit_for_state(out["state"]),3)
        self.assertFalse(out["independent_vendor_corporate_action_confirmed"])
        self.assertGreaterEqual(out["corporate_action_review_count"],1)
        self.assertFalse(out["corporate_action_cleared"])
        self.assertFalse(out["sheet_writes"])
        self.assertEqual(b,old)

    def test_open_roku_after_delisting_is_not_silently_accepted(self):
        c,s,b=fixture("open")
        with self.assertRaisesRegex(witness.ActionWitnessBlocked,
                                    "UNREVIEWED_DELISTED_ISSUER_EPISODE"):
            witness.inspect(c,s,b,ASOF)

    def test_wrong_corporate_action_day_blocks(self):
        c,s,b=fixture("wrongdate")
        with self.assertRaisesRegex(witness.ActionWitnessBlocked,
                                    "UNREVIEWED_DELISTED_ISSUER_EPISODE"):
            witness.inspect(c,s,b,ASOF)

    def test_wrong_corporate_action_code_blocks(self):
        c,s,b=fixture("wrongcode")
        with self.assertRaisesRegex(witness.ActionWitnessBlocked,
                                    "UNREVIEWED_DELISTED_ISSUER_EPISODE"):
            witness.inspect(c,s,b,ASOF)

    def test_fake_roku_9_nov_bar_cannot_be_accepted(self):
        c,s,b=fixture()
        b["ROKU"].append(dict(timestamp=DELIST+"T05:00:00+00:00",
                              open=100.,high=103.,low=98.,
                              close=101.,volume=1000.))
        with self.assertRaisesRegex(witness.ActionWitnessBlocked,
                                    "DELISTED_ISSUER_POST_LAST_TRADE_BAR_REVIEW"):
            witness.inspect(c,s,b,ASOF)


if __name__=="__main__":
    unittest.main()
