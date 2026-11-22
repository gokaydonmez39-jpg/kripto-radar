"""NASDAQ Personal 477: future XNAS boundary and missed 2026-11-20 incident tests.

OFFLINE ONLY: no network, market data, Sheet, tag/ref, workflow dispatch or alert.
Pin real official close instants and fail closed against replay/holiday drift.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import exchange_calendars as ec

import daily_job
import epoch_lease
import schedule_failover


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class November2026NaturalBoundaryRegression(unittest.TestCase):
    def setUp(self):
        self.cal = ec.get_calendar("XNAS")

    def test_official_sessions_and_early_close_not_weekday_arithmetic(self):
        expected = {
            "2026-11-20": "2026-11-20T21:00:00Z",
            "2026-11-23": "2026-11-23T21:00:00Z",
            "2026-11-25": "2026-11-25T21:00:00Z",
            "2026-11-27": "2026-11-27T18:00:00Z",
        }
        for day, close in expected.items():
            with self.subTest(day=day):
                self.assertTrue(self.cal.is_session(day))
                self.assertEqual(self.cal.session_close(day).to_pydatetime(), utc(close))
        self.assertFalse(self.cal.is_session("2026-11-21"))
        self.assertFalse(self.cal.is_session("2026-11-22"))
        self.assertFalse(self.cal.is_session("2026-11-26"))

    def test_2026_11_20_gap_is_detected_but_never_dispatched(self):
        calls = []
        def read():
            calls.append("get")
            return {"total_count": 0, "workflow_runs": []}
        def dispatch(day):
            calls.append(("POST", day))
            return True
        observed = utc("2026-11-21T07:31:58Z")
        outcome = schedule_failover.run(
            now=observed, read_runs=read, request_dispatch=dispatch,
            trigger_event="schedule",
        )
        self.assertEqual(outcome["status"], "BLOCKED_DISPATCH_NOT_CONFIRMED")
        self.assertEqual(outcome["reason_code"], "NATURAL_FALLBACK_POLICY_LOCKED")
        self.assertEqual(outcome["asof_et"], "2026-11-20")
        self.assertIs(outcome["dispatch_requested"], False)
        self.assertEqual(calls, ["get", "get"])
        self.assertEqual(schedule_failover.exit_code_for_result(outcome, "schedule"), 3)

    def test_missing_20_nov_just_after_ten_hours_is_hard_red_without_io(self):
        called = []
        outcome = schedule_failover.run(
            now=utc("2026-11-21T07:45:01Z"),
            read_runs=lambda: called.append("read"),
            request_dispatch=lambda s: called.append(("POST", s)),
            trigger_event="schedule",
        )
        self.assertEqual(outcome["status"], "BLOCKED_NATURAL_FALLBACK_EXPIRED")
        self.assertEqual(outcome["asof_et"], "2026-11-20")
        self.assertIs(outcome["dispatch_requested"], False)
        self.assertEqual(called, [])
        self.assertEqual(schedule_failover.exit_code_for_result(outcome, "schedule"), 3)

    def test_23_nov_close_plus_45m_boundary(self):
        before = utc("2026-11-23T21:44:59Z")
        ready = utc("2026-11-23T21:45:00Z")
        self.assertIsNone(daily_job.current_completed_session(before))
        self.assertEqual(daily_job.current_completed_session(ready), "2026-11-23")
        self.assertEqual(
            schedule_failover.decision(ready, []),
            ("DISPATCH_ONE_MISSING_SCHEDULE", "2026-11-23"),
        )

    def test_23_nov_ten_hour_expiry_boundary(self):
        last = utc("2026-11-24T07:45:00Z")
        expired = last + timedelta(seconds=1)
        self.assertEqual(daily_job.current_completed_session(last), "2026-11-23")
        self.assertIsNone(daily_job.current_completed_session(expired))
        self.assertTrue(daily_job.expired_natural_eod_window(expired))
        self.assertEqual(
            schedule_failover.decision(expired, []),
            ("NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW", "2026-11-23"),
        )

    def test_thanksgiving_has_no_synthetic_eod(self):
        when = utc("2026-11-26T23:16:00Z")
        self.assertIsNone(daily_job.current_completed_session(when))
        self.assertFalse(daily_job.expired_natural_eod_window(when))
        self.assertEqual(
            schedule_failover.decision(when, []),
            ("NOOP_OUTSIDE_SAFE_FALLBACK_WINDOW", "2026-11-25"),
        )

    def test_black_friday_early_close_plus_45m(self):
        before = utc("2026-11-27T18:44:59Z")
        ready = utc("2026-11-27T18:45:00Z")
        self.assertIsNone(daily_job.current_completed_session(before))
        self.assertEqual(daily_job.current_completed_session(ready), "2026-11-27")
        self.assertEqual(
            schedule_failover.decision(ready, []),
            ("DISPATCH_ONE_MISSING_SCHEDULE", "2026-11-27"),
        )

    def test_black_friday_ten_hour_expiry(self):
        last = utc("2026-11-28T04:45:00Z")
        expired = last + timedelta(seconds=1)
        self.assertEqual(daily_job.current_completed_session(last), "2026-11-27")
        self.assertIsNone(daily_job.current_completed_session(expired))
        self.assertTrue(daily_job.expired_natural_eod_window(expired))

    def test_old_friday_epoch_cannot_claim_monday_producer(self):
        natural = {
            "GITHUB_REPOSITORY": epoch_lease.REPO,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": (
                epoch_lease.REPO + "/" + epoch_lease.WORKFLOW + "@refs/heads/main"
            ),
            "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "12345",
        }
        with self.assertRaises(epoch_lease.LeaseHold):
            epoch_lease.verified_natural_owner(
                natural, "2026-11-20", utc("2026-11-23T21:45:00Z")
            )
        owner = epoch_lease.verified_natural_owner(
            natural, "2026-11-23", utc("2026-11-23T21:45:00Z")
        )
        self.assertEqual(owner["asof_et"], "2026-11-23")
        self.assertEqual(owner["source_event"], "schedule")


if __name__ == "__main__":
    unittest.main()
