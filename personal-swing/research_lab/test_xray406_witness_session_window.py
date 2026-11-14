from datetime import datetime, timedelta, timezone
import os
import unittest

from xray406_witness_acceptance import Rejected
from xray406_witness_session_window import window, pick_latest_safe_slot

U = timezone.utc
def t(day, hour, minute, sec=0):
    return datetime(2026, 11, day, hour, minute, sec, tzinfo=U)


class ExactCalendar:
    """Frozen NASDAQ 2026 calendar facts for the two relevant sessions."""
    dates = {"2026-11-16": (16, 21), "2026-11-27": (27, 18)}

    def is_session(self, date):
        return date in self.dates

    class Stamp:
        def __init__(self, value):
            self.value = value

        def to_pydatetime(self):
            return self.value

    def session_open(self, date):
        d, _ = self.dates[date]
        return self.Stamp(t(d, 14, 30))

    def session_close(self, date):
        d, h = self.dates[date]
        return self.Stamp(t(d, h, 0))


class CalendarWindowTests(unittest.TestCase):
    def test_real_session_holiday_early_close_and_weekend(self):
        self.assertEqual(window("2026-11-16", ExactCalendar()).cutoff, t(16, 21, 45))
        self.assertEqual(window("2026-11-27", ExactCalendar()).cutoff, t(27, 18, 45))
        for d in ("2026-11-14", "2026-11-26"):
            with self.subTest(d=d), self.assertRaisesRegex(Rejected, "NOT_XNAS_SESSION"):
                window(d, ExactCalendar())

    def test_47_after_close_too_late_and_previous_slot_expires_early(self):
        w = window("2026-11-16", ExactCalendar())
        with self.assertRaisesRegex(Rejected, "WITNESS_OUTSIDE_XNAS_WINDOW"):
            w.publication_deadline(t(16, 21, 47))
        self.assertEqual(w.publication_deadline(t(16, 20, 47)), t(16, 21, 2))
        self.assertEqual(w.publication_deadline(t(16, 21, 30)), t(16, 21, 45))

    def test_slot_must_be_on_same_session_and_leave_budget(self):
        w = window("2026-11-16", ExactCalendar())
        candidates = [t(16, 20, 47), t(16, 21, 30), t(16, 21, 40),
                      t(16, 21, 47), t(17, 21, 30)]
        self.assertEqual(pick_latest_safe_slot(w, candidates, timedelta(minutes=10)), t(16, 21, 30))
        self.assertIsNone(pick_latest_safe_slot(w, [t(16, 21, 47)], timedelta(minutes=10)))

    def test_no_bad_clock_or_budget(self):
        w = window("2026-11-16", ExactCalendar())
        for t0 in (t(16, 21, 30).replace(tzinfo=None), t(16, 14, 29), t(16, 21, 45)):
            with self.subTest(t=t0), self.assertRaises(Rejected):
                w.publication_deadline(t0)
        with self.assertRaises(Rejected):
            pick_latest_safe_slot(w, [t(16, 21, 30)], timedelta())

    @unittest.skipUnless(os.environ.get("XRAY406_VERIFY_CALENDAR_LIBRARY") == "1",
                         "optional calendar package cross-check")
    def test_calendar_library_matches_official_examples(self):
        self.assertEqual(window("2026-11-16").cutoff, t(16, 21, 45))
        self.assertEqual(window("2026-11-27").cutoff, t(27, 18, 45))
        for d in ("2026-11-14", "2026-11-26"):
            with self.subTest(d=d), self.assertRaisesRegex(Rejected, "NOT_XNAS_SESSION"):
                window(d)
