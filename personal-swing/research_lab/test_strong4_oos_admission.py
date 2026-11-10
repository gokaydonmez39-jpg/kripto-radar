"""Synthetic-only OOS negative tests; never vendor data or real strategy results."""
import copy
import hashlib
import unittest
from datetime import timedelta, timezone
import exchange_calendars as xc
from strong4_oos_admission import inspect, POLICY, SCHEMA, WATCHLIST_GIT_SHA, SESSIONS_REQUIRED

class OOSPreAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = xc.get_calendar("XNAS")
        cls.days = cls.cal.sessions_in_range("2024-04-01", "2026-11-06")[:SESSIONS_REQUIRED]
        assert len(cls.days) == SESSIONS_REQUIRED

    def data(self, claimed=0):
        rows = []
        for idx, ts in enumerate(self.days):
            previous = self.cal.previous_session(ts)
            prior_close = self.cal.session_close(previous).to_pydatetime()
            known = prior_close + timedelta(minutes=15)
            decision = prior_close + timedelta(minutes=35)
            session = ts.strftime("%Y-%m-%d")
            rows.append({
                "session": session,
                "decision_asof_et": previous.strftime("%Y-%m-%d"),
                "decision_at_utc": decision.astimezone(timezone.utc).isoformat(),
                "feature_first_known_at_utc": known.astimezone(timezone.utc).isoformat(),
                "decision_receipt_sha256": hashlib.sha256(session.encode()).hexdigest(),
                "strategy_gross_daily_return": 0.002 if idx % 2 == 0 else -0.001,
                "baseline_daily_return": 0.0001,
                "turnover_fraction": 0.01,
                "claimed_al_signals": claimed if 515 <= idx < 608 else 0,
            })
        return {
            "schema": SCHEMA, "watchlist_git_blob": WATCHLIST_GIT_SHA,
            "policy": copy.deepcopy(POLICY),
            "receipts": {key: hashlib.sha256(key.encode()).hexdigest() for key in (
                "historical_decision_journal_sha256", "issuer_lineage_sha256",
                "data_rights_sha256")}, "rows": rows,
        }

    def rejected(self, message, update):
        doc = self.data()
        update(doc)
        with self.assertRaisesRegex(ValueError, message):
            inspect(doc)

    def test_no_signals_no_alpha(self):
        answer = inspect(self.data())
        self.assertEqual(answer["out_of_sample_test_sessions"], 93)
        self.assertEqual(answer["first_fold_usable_training_sessions"], 500)
        self.assertTrue(answer["no_claimed_signals_hold"])
        self.assertFalse(answer["real_oos_alpha_verified"])
        self.assertFalse(answer["production_authorized"])

    def test_profitable_fabricated_series_still_never_alpha(self):
        answer = inspect(self.data(claimed=1))
        self.assertEqual(answer["claimed_oos_al_signals"], 93)
        self.assertFalse(answer["signed_contemporaneous_decision_records_verified"])
        self.assertFalse(answer["real_oos_alpha_verified"])
        self.assertFalse(answer["production_authorized"])

    def test_expanding_purged_train(self):
        answer = inspect(self.data())
        self.assertEqual([f["usable_train_sessions"] for f in answer["folds"]],
                         [500, 531, 562])

    def test_incomplete_window(self):
        self.rejected("REQUIRES_EXACTLY_623_SESSIONS", lambda x: x["rows"].pop())

    def test_calendar_missing_date(self):
        self.rejected("INCOMPLETE_XNAS_WINDOW|NONCONSECUTIVE_XNAS_SESSIONS",
                      lambda x: x["rows"][150].update(session="2024-09-28"))

    def test_duplicate_decision_receipt(self):
        self.rejected("REUSED_DECISION_RECEIPT", lambda x: x["rows"][50].update(
            decision_receipt_sha256=x["rows"][49]["decision_receipt_sha256"]))

    def test_unexpected_production_field(self):
        self.rejected("DOCUMENT_SCHEMA_INVALID", lambda x: x.update(may_place_order=True))

    def test_wrong_fixed_universe(self):
        self.rejected("WATCHLIST_DRIFT", lambda x: x.update(watchlist_git_blob="0" * 40))

    def test_stop_change(self):
        self.rejected("POLICY_DRIFT_stop_atr", lambda x: x["policy"].update(stop_atr=3))

    def test_purge_change(self):
        self.rejected("POLICY_DRIFT_purge_sessions", lambda x: x["policy"].update(purge_sessions=0))

    def test_waived_fees(self):
        self.rejected("POLICY_DRIFT_fee_bps", lambda x: x["policy"].update(fee_bps=0.0))

    def test_hindsight_baseline(self):
        self.rejected("POLICY_DRIFT_baseline", lambda x: x["policy"].update(
            baseline="WINNERS_ONLY"))

    def test_future_lookahead(self):
        self.rejected("LOOKAHEAD_OR_LATE_DECISION", lambda x: x["rows"][30].update(
            feature_first_known_at_utc="2026-11-19T00:00:00+00:00"))

    def test_wrong_decision_date(self):
        self.rejected("LOOKAHEAD_DECISION_DATE", lambda x: x["rows"][30].update(
            decision_asof_et=x["rows"][30]["session"]))

    def test_decision_after_open(self):
        self.rejected("LOOKAHEAD_OR_LATE_DECISION", lambda x: x["rows"][30].update(
            decision_at_utc="2026-11-20T20:00:00+00:00"))

    def test_nan_gross(self):
        self.rejected("INVALID_GROSS_RETURN", lambda x: x["rows"][30].update(
            strategy_gross_daily_return=float("nan")))

    def test_bool_gross(self):
        self.rejected("INVALID_GROSS_RETURN", lambda x: x["rows"][30].update(
            strategy_gross_daily_return=True))

    def test_negative_illogical_baseline(self):
        self.rejected("INVALID_BASELINE_RETURN", lambda x: x["rows"][30].update(
            baseline_daily_return=-2.0))

    def test_turnover_excess(self):
        self.rejected("INVALID_TURNOVER", lambda x: x["rows"][30].update(
            turnover_fraction=4.0))

    def test_fake_receipt(self):
        self.rejected("INVALID_SELF_DECLARED_RECEIPT_data_rights_sha256",
                      lambda x: x["receipts"].update(data_rights_sha256="a" * 64))

    def test_noninteger_claims(self):
        self.rejected("INVALID_CLAIMED_AL_COUNT", lambda x: x["rows"][30].update(
            claimed_al_signals=True))

if __name__ == "__main__":
    unittest.main()