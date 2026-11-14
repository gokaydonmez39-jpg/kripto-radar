from datetime import timedelta
from unittest import TestCase

import test_xray406_witness_acceptance as fixtures
from test_xray406_witness_session_window import ExactCalendar
from xray406_witness_acceptance import Rejected
from xray406_witness_session_window import window
from xray406_witness_ingress import SOURCE_PATH, preflight


class IngressTests(TestCase):
    def setUp(self):
        f = self.f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.w = window("2026-11-16", ExactCalendar())
        self.run = {"repo": "gokaydonmez39-jpg/kripto-radar",
                    "ref": "refs/heads/main", "event": "schedule",
                    "path": SOURCE_PATH, "attempt": 1, "run_id": 20,
                    "checkout": f.base, "started_at": f.generated - timedelta(seconds=30)}

    def check(self, run=None, now=None):
        f = self.f
        return preflight(f.root, f.base, f.head, self.run if run is None else run,
                         self.w, f.generated if now is None else now)

    def test_exact_post_close_source(self):
        x = self.check()
        self.assertEqual((x.run_id,x.head,x.deadline),(20,self.f.head,self.w.cutoff))

    def test_no_manual_rerun_wrong_repo_or_foreign_base(self):
        for change in ({"event":"workflow_dispatch"},{"attempt":2},
                       {"repo":"other/fork"},{"ref":"refs/heads/test"},
                       {"path":".github/workflows/other.yml"},{"checkout":"b"*40},
                       {"run_id":True}):
            with self.subTest(change=change), self.assertRaises(Rejected):
                self.check({**self.run, **change})

    def test_no_reuse_of_pre_run_generated_data(self):
        with self.assertRaisesRegex(Rejected, "SOURCE_GENERATION_ORDER"):
            self.check({**self.run,"started_at":self.f.generated + timedelta(seconds=1)},
                       self.f.generated + timedelta(seconds=2))

    def test_post_close_budget_and_started_at(self):
        with self.assertRaisesRegex(Rejected,"NOT_POST_CLOSE_SOURCE"):
            self.check({**self.run,"started_at":self.w.closes-timedelta(seconds=1)})
        with self.assertRaisesRegex(Rejected,"INGRESS_WINDOW_CLOSED"):
            self.check(now=self.w.cutoff-timedelta(minutes=2))

    def test_active_main_base_can_advance_from_checkout(self):
        f=self.f
        f.run_git("checkout","--detach",f.base)
        original=f.base
        f.write("unrelated.json", {"revision": 1})
        f.base=f.commit("other writer")
        f.write("nasdaq-xray/canonical_official_source_guard.json",f.guard)
        f.write("nasdaq-xray/official_pit_ledger.json",f.ledger)
        f.head=f.commit("candidate from refreshed base")
        self.assertNotEqual(original,f.base)
        self.assertEqual(self.check().base,f.base)

    def test_shared_writer_changing_guard_after_checkout_blocks_restage(self):
        f=self.f
        from xray406_witness_acceptance import GUARD, LEDGER
        f.run_git("checkout","--detach",f.base)
        f.write(GUARD, {**f.guard, "generated_at_utc":
                        (f.generated + timedelta(seconds=1)).isoformat()})
        f.base=f.commit("another writer publishes a newer guard")
        f.write(GUARD,f.guard)
        f.write(LEDGER,f.ledger)
        f.head=f.commit("old guard on newer base")
        with self.assertRaisesRegex(Rejected,"SOURCE_INPUT_BLOBS_MOVED"):
            self.check(now=f.generated+timedelta(seconds=2))
