from datetime import datetime, timezone
import json
import unittest
from urllib.parse import parse_qs, urlsplit

import official_guard_cutoff_select as select


def point(stamp, commit="2026-11-12T17:44:29Z", status="PASS"):
    return commit, json.dumps({"generated_at_utc": stamp, "status": status})


class CutoffTests(unittest.TestCase):
    cutoff = datetime(2026, 11, 12, 21, 45, tzinfo=timezone.utc)

    def test_nov12_latest_file_is_late_but_prior_record_is_timely(self):
        current = point("2026-11-13T02:10:51Z", "2026-11-13T02:10:56Z")
        late = point("2026-11-12T22:52:07Z", "2026-11-12T22:52:11Z")
        timely = point("2026-11-12T17:44:26Z")
        self.assertEqual(select.choose([current, late, timely], self.cutoff), timely[1])

    def test_no_backdated_document_committed_after_cutoff(self):
        late = point("2026-11-12T21:44:58Z", "2026-11-12T21:46:00Z")
        self.assertIsNone(select.choose([late], self.cutoff))

    def test_most_recent_eligible_degraded_is_not_hidden_by_prior_pass(self):
        degraded = point("2026-11-12T19:00:00Z", "2026-11-12T19:01:00Z", "DEGRADED")
        older = point("2026-11-12T17:44:26Z")
        self.assertEqual(select.choose([degraded, older], self.cutoff), degraded[1])

    def test_stale_is_not_eligible_and_invalid_clock_fails_closed(self):
        stale = point("2026-11-11T20:00:00Z", "2026-11-11T20:01:00Z")
        reversed_clock = point("2026-11-12T17:44:30Z")
        self.assertIsNone(select.choose([stale], self.cutoff))
        with self.assertRaisesRegex(ValueError, "WITNESS_CLOCK_AFTER_COMMIT"):
            select.choose([reversed_clock, point("2026-11-12T17:44:26Z")],
                          self.cutoff)

    def test_equal_clock_conflicting_witness_fails_closed(self):
        ok = point("2026-11-12T17:44:26Z")
        bad = point("2026-11-12T17:44:26Z", status="DEGRADED")
        with self.assertRaises(ValueError):
            select.choose([ok, bad], self.cutoff)

    def test_corrupt_pre_cutoff_history_cannot_fall_through_to_older_pass(self):
        with self.assertRaises(ValueError):
            select.choose([("2026-11-12T19:01:00Z", "{}"),
                           point("2026-11-12T17:44:26Z")], self.cutoff)

    def test_api_is_anchored_to_checkout_and_reads_exact_guard_versions(self):
        anchor, on_time, late = "a" * 40, "b" * 40, "c" * 40
        timely = point("2026-11-12T21:00:27Z", "2026-11-12T21:00:30Z")
        calls = []

        def read(path, raw=False):
            calls.append((path, raw))
            if raw:
                self.assertEqual(path, "/contents/" + select.GUARD + "?ref=" + on_time)
                return timely[1]
            return json.dumps([
                {"sha": late, "commit": {"committer": {"date": "2026-11-12T22:00:00Z"}}},
                {"sha": on_time, "commit": {"committer": {"date": timely[0]}}},
            ])

        self.assertEqual(select.archived_guard(anchor, self.cutoff, read), timely[1])
        self.assertEqual(len(calls), 2)
        query = parse_qs(urlsplit(calls[0][0]).query)
        self.assertEqual(query, {"sha": [anchor], "path": [select.GUARD],
                                 "until": [self.cutoff.isoformat()],
                                 "since": ["2026-11-11T21:45:00+00:00"],
                                 "per_page": [str(select.MAX_VERSIONS + 1)]})

    def test_truncated_history_and_nonimmutable_ref_fail_closed(self):
        def read(_path):
            return json.dumps([{}] * (select.MAX_VERSIONS + 1))

        with self.assertRaisesRegex(ValueError, "GITHUB_HISTORY_UNCERTAIN"):
            select.archived_guard("a" * 40, self.cutoff, read)
        with self.assertRaisesRegex(ValueError, "BAD_CHECKOUT_SHA"):
            select.archived_guard("main", self.cutoff, read)


if __name__ == "__main__":
    unittest.main()
