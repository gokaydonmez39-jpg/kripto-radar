"""Adversarial checks: a late natural EOD must never silently become green.

All tests are pure offline, no GitHub dispatch, network request, or Sheet write.
"""
import contextlib
import io
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import daily_job


def utc(stamp):
    return datetime.fromisoformat(stamp.replace("Z","+00:00"))


class NaturalEodWindowTests(unittest.TestCase):
    def test_just_inside_window_not_expired(self):
        self.assertFalse(daily_job.expired_natural_eod_window(
            utc("2026-11-21T07:45:00Z")))

    def test_one_second_after_window_is_expired(self):
        self.assertTrue(daily_job.expired_natural_eod_window(
            utc("2026-11-21T07:45:01Z")))

    def test_natural_delay_over_10_hours_is_explicitly_a_failure(self):
        self.assertTrue(daily_job.expired_natural_eod_window(
            utc("2026-11-21T08:15:00Z")))

    def test_one_day_from_cutoff_is_last_unambiguous_prior_epoch(self):
        self.assertTrue(daily_job.expired_natural_eod_window(
            utc("2026-11-21T21:45:00Z")))
        self.assertFalse(daily_job.expired_natural_eod_window(
            utc("2026-11-21T21:45:01Z")))

    def test_thanksgiving_holiday_does_not_claim_missing_session(self):
        self.assertFalse(daily_job.expired_natural_eod_window(
            utc("2026-11-26T23:16:00Z")))

    def test_normal_natural_on_time_does_not_fail(self):
        self.assertFalse(daily_job.expired_natural_eod_window(
            utc("2026-11-23T23:16:00Z")))

    def test_early_close_respects_real_xnas_calendar(self):
        # Friday 27 November has an 18:00Z XNAS close; safe cutoff=18:45Z.
        self.assertFalse(daily_job.expired_natural_eod_window(
            utc("2026-11-28T04:45:00Z")))
        self.assertTrue(daily_job.expired_natural_eod_window(
            utc("2026-11-28T04:45:01Z")))


class NaturalEodMainExitTests(unittest.TestCase):
    def call(self,event,expired):
        buf=io.StringIO()
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME":event}), \
             patch.object(daily_job,"current_completed_session",return_value=None), \
             patch.object(daily_job,"expired_natural_eod_window",return_value=expired), \
             patch.object(daily_job.engine,"live_read",side_effect=AssertionError("PROVIDER_IO_FORBIDDEN")):
            with contextlib.redirect_stdout(buf):
                rc=daily_job.main([])
        return rc,json.loads(buf.getvalue().strip())

    def test_expired_schedule_exits_nonzero_without_io(self):
        rc,event=self.call("schedule",True)
        self.assertEqual(rc,3)
        self.assertEqual(event["status"],"BLOCKED_NATURAL_EOD_FRESHNESS_WINDOW_EXPIRED")
        self.assertFalse(event["market_data_called"])
        self.assertEqual(event["execution"],"NONE")
        self.assertFalse(event["dispatch_requested"])

    def test_no_session_outside_natural_window_keeps_noop(self):
        rc,event=self.call("schedule",False)
        self.assertEqual(rc,0)
        self.assertEqual(event["status"],"SKIPPED_NO_COMPLETED_CURRENT_ET_SESSION")
        self.assertFalse(event["market_data_called"])

    def test_manual_no_asof_never_gets_synthetic_eod_failure(self):
        rc,event=self.call("workflow_dispatch",True)
        self.assertEqual(rc,0)
        self.assertEqual(event["status"],"SKIPPED_NO_COMPLETED_CURRENT_ET_SESSION")
        self.assertFalse(event["market_data_called"])

    def test_push_no_market_call_and_no_false_expiry(self):
        rc,event=self.call("push",True)
        self.assertEqual(rc,0)
        self.assertEqual(event["status"],"SKIPPED_NO_COMPLETED_CURRENT_ET_SESSION")
        self.assertFalse(event["market_data_called"])


class ExplicitAsOfBoundaryTests(unittest.TestCase):
    """GitHub manual recovery cannot bypass the natural-session freshness gate."""

    def blocked(self, event, requested, eligible):
        output=io.StringIO()
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME":event}), \
             patch.object(daily_job,"current_completed_session",return_value=eligible), \
             patch.object(daily_job.runner,"get_scope",
                          side_effect=AssertionError("SCOPE_IO_FORBIDDEN")), \
             patch.object(daily_job.engine,"live_read",
                          side_effect=AssertionError("PROVIDER_IO_FORBIDDEN")), \
             contextlib.redirect_stdout(output):
            rc=daily_job.main(["--asof",requested])
        return rc,json.loads(output.getvalue().strip())

    def test_old_manual_asof_is_rejected_before_any_scope_or_vendor_io(self):
        rc,output=self.blocked("workflow_dispatch","2026-11-20","2026-11-23")
        self.assertEqual(rc,3)
        self.assertEqual(output["status"],
                         "BLOCKED_EXPLICIT_ASOF_OUTSIDE_CURRENT_XNAS_FRESHNESS_WINDOW")
        self.assertFalse(output["market_data_called"])
        self.assertFalse(output["dispatch_requested"])

    def test_future_manual_asof_is_rejected(self):
        rc,output=self.blocked("workflow_dispatch","2026-11-24","2026-11-23")
        self.assertEqual(rc,3)
        self.assertFalse(output["market_data_called"])

    def test_manual_explicit_asof_after_freshness_expiry_is_rejected(self):
        rc,output=self.blocked("workflow_dispatch","2026-11-20",None)
        self.assertEqual(rc,3)
        self.assertFalse(output["market_data_called"])

    def test_scheduled_explicit_asof_cannot_bypass_freshness(self):
        rc,output=self.blocked("schedule","2026-11-20","2026-11-23")
        self.assertEqual(rc,3)
        self.assertFalse(output["market_data_called"])

    def test_same_fresh_completed_asof_keeps_existing_research_path(self):
        output=io.StringIO()
        with patch.dict(os.environ,{"GITHUB_EVENT_NAME":"workflow_dispatch"}), \
             patch.object(daily_job,"current_completed_session",
                          return_value="2026-11-23"), \
             patch.object(daily_job.runner,"get_scope",return_value=["TEST"]), \
             patch.object(daily_job,"run_once",return_value={
                "asof_et":"2026-11-23","final_ready":True,"no_execution":True}), \
             contextlib.redirect_stdout(output):
            rc=daily_job.main(["--asof","2026-11-23"])
        self.assertEqual(rc,0)
        self.assertEqual(json.loads(output.getvalue())["asof_et"],"2026-11-23")


if __name__=="__main__":
    unittest.main()
