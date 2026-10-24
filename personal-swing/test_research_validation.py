import unittest
import research_validation as r

CANDIDATE = {"asof_et":"2026-10-22","reference_close":100.0,"stop":90.0,"target_2r":120.0}

def bar(o=100,h=109,l=96,c=102):
    return {"open":o,"high":h,"low":l,"close":c}

class ResearchValidationTests(unittest.TestCase):
    def test_open_one_session(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                               bars={"2026-10-23":bar()})
        self.assertEqual(q["status"],"OPEN_RESEARCH_ONLY")
        self.assertFalse(q["fills_confirmed"])

    def test_stop_intraday(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                               bars={"2026-10-23":bar(l=89)})
        self.assertEqual(q["status"],"STOP_TOUCHED")

    def test_target_intraday(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                               bars={"2026-10-23":bar(h=121)})
        self.assertEqual(q["status"],"TARGET_TOUCHED")

    def test_dual_touch_never_claims_intraday_sequence(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                               bars={"2026-10-23":bar(h=121,l=89)})
        self.assertEqual(q["status"],"BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS")
        self.assertFalse(q["fills_confirmed"])

    def test_gap_below_stop(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                               bars={"2026-10-23":bar(o=88,h=104,l=85,c=101)})
        self.assertEqual(q["status"],"GAP_BELOW_STOP")
        self.assertTrue(q["gap_below_stop"])

    def test_missing_official_session_unchanged(self):
        q=r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23","2026-10-26"],
                               bars={"2026-10-26":bar()})
        self.assertEqual(q["status"],"STATUS_UNKNOWN_MISSING_SESSION")
        self.assertEqual(q["sessions"],0)

    def test_no_lookahead_reentry(self):
        with self.assertRaises(ValueError):
            r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-22"],bars={})

    def test_reject_geometry(self):
        with self.assertRaisesRegex(ValueError,"INVALID_OHLC_GEOMETRY"):
            r.research_lifecycle(CANDIDATE,verified_next_sessions=["2026-10-23"],
                                 bars={"2026-10-23":bar(o=102,h=101,l=90,c=100)})

    def test_reject_over_15_sessions(self):
        from datetime import date,timedelta
        dates=[(date(2026,10,23)+timedelta(days=i)).isoformat() for i in range(16)]
        with self.assertRaisesRegex(ValueError,"SESSION_SCOPE_INVALID"):
            r.research_lifecycle(CANDIDATE,verified_next_sessions=dates,bars={})

    def test_purged_label_end(self):
        dates=["2026-10-20","2026-10-21","2026-10-22","2026-10-23",
               "2026-10-26","2026-10-27","2026-10-28"]
        rows=[
            {"id":"A","signal_session":"2026-10-20","outcome_session":"2026-10-20"},
            {"id":"B","signal_session":"2026-10-21","outcome_session":"2026-10-23"},
            {"id":"C","signal_session":"2026-10-26","outcome_session":"2026-10-27"}]
        q=r.purged_walkforward(rows,official_sessions=dates,test_start="2026-10-26",
                                embargo_sessions=1)
        self.assertEqual(q["train_ids"],["A"])
        self.assertEqual(q["test_ids"],["C"])
        self.assertEqual(q["purged_count"],1)
        self.assertFalse(q["performance_improvement_proven"])

    def test_short_holdout_never_claims_alpha(self):
        dates=["2026-10-20","2026-10-21","2026-10-22"]
        q=r.purged_walkforward([{"id":"A","signal_session":"2026-10-22",
                                 "outcome_session":"2026-10-22"}],
                 official_sessions=dates,test_start="2026-10-22")
        self.assertEqual(q["statistical_conclusion"],"INSUFFICIENT_OOS_EVIDENCE")

    def test_duplicate_episode(self):
        dates=["2026-10-20","2026-10-21","2026-10-22"]
        row={"id":"A","signal_session":"2026-10-22","outcome_session":"2026-10-22"}
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_MISSING"):
            r.purged_walkforward([row,row],official_sessions=dates,test_start="2026-10-22")

    def test_unknown_session_rejected(self):
        dates=["2026-10-20","2026-10-21","2026-10-22"]
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_RECORD_SESSION"):
            r.purged_walkforward([{"id":"A","signal_session":"2026-10-23",
                  "outcome_session":"2026-10-23"}],official_sessions=dates,test_start="2026-10-22")

if __name__=="__main__":
    unittest.main()
