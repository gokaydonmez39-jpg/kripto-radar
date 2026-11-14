from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from xray406_witness_acceptance import (
    ACTIONS_APP, CHECK, GUARD, LEDGER, CheckReceipt, MainReceipt,
    Rejected, check_acceptance, check_candidate,
)


class WitnessAcceptanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.run_git("config", "user.name", "Offline fixture")
        self.generated = datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc)
        flags = {"execution": "NONE", "real_money": "NO-GO", "alpha_authority": False}
        feeds = {"security_status": {"status": "PASS"}, "trade_halts": {"status": "UNKNOWN"}}
        safety = {"halt_guard_status": "UNKNOWN", "security_status_guard_status": "PASS"}
        self.guard = {**flags, "schema": "XRAY_OFFICIAL_SOURCE_GUARD_V1",
                      "generated_at_utc": self.generated.isoformat(), "status": "DEGRADED",
                      "sources": feeds, "candidate_safety": safety}
        initial = {"source": "prior", "payload_sha256": "0" * 64}
        entries = [{"source": k, "payload_sha256": hashlib.sha256(json.dumps(
            v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()}
            for k, v in {**feeds, "candidate_safety": safety}.items()]
        self.ledger = {**flags, "schema": "XRAY_OFFICIAL_PIT_LEDGER_V1",
                       "append_only_semantics": True, "unknown_never_pass": True,
                       "snapshots": [initial, *entries], "snapshot_count": 1 + len(entries)}
        self.write(GUARD, {**self.guard, "generated_at_utc": (self.generated - timedelta(minutes=1)).isoformat()})
        self.write(LEDGER, {**self.ledger, "snapshots": [initial], "snapshot_count": 1})
        self.base = self.commit("baseline")
        self.write(GUARD, self.guard)
        self.write(LEDGER, self.ledger)
        self.head = self.commit("candidate")
        self.check = CheckReceipt(self.head, CHECK, ACTIONS_APP, "success",
                                  self.generated + timedelta(minutes=1))
        self.readback = MainReceipt(self.head, self.generated + timedelta(minutes=2),
                                   self.run_git("rev-parse", f"{self.head}:{GUARD}"),
                                   self.run_git("rev-parse", f"{self.head}:{LEDGER}"))
        self.cutoff = self.generated + timedelta(minutes=3)

    def run_git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args],
                                       text=True).strip()

    def write(self, path, value):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(value), encoding="utf-8")

    def commit(self, message):
        self.run_git("add", ".")
        self.run_git("commit", "-qm", message)
        return self.run_git("rev-parse", "HEAD")

    def accept(self, **kwargs):
        values = dict(root=self.root, base=self.base, head=self.head,
                      check=self.check, readback=self.readback, cutoff=self.cutoff)
        return check_acceptance(**{**values, **kwargs})

    def alternate(self, guard=None, ledger=None, extra=False, message="candidate v2"):
        self.run_git("reset", "--hard", self.base)
        self.write(GUARD, self.guard if guard is None else guard)
        self.write(LEDGER, self.ledger if ledger is None else ledger)
        if extra:
            self.write("unrelated.json", {})
        return self.commit(message)

    def test_positive_exact_check_and_timely_readback(self):
        self.assertEqual(self.accept(), "WITNESS_ACCEPTANCE_PASS")

    def test_failing_check_and_wrong_actor_and_sha(self):
        for change in ({"conclusion": "failure"}, {"app_id": 7}, {"head": self.base},
                       {"name": "another-check"}):
            with self.subTest(change=change), self.assertRaisesRegex(Rejected, "EXACT_CI"):
                self.accept(check=replace(self.check, **change))

    def test_wrong_readback_sha_or_blob(self):
        for change in ({"head": self.base}, {"guard_blob": "0" * 40}, {"ledger_blob": "1" * 40}):
            with self.subTest(change=change), self.assertRaisesRegex(Rejected, "EXACT_MAIN"):
                self.accept(readback=replace(self.readback, **change))

    def test_cutoff_equality_passes_and_one_microsecond_late_fails(self):
        self.assertEqual(self.accept(cutoff=self.readback.observed_at), "WITNESS_ACCEPTANCE_PASS")
        with self.assertRaisesRegex(Rejected, "PIT_VISIBILITY"):
            self.accept(cutoff=self.readback.observed_at - timedelta(microseconds=1))

    def test_receipt_before_ci_fails(self):
        with self.assertRaisesRegex(Rejected, "PIT_VISIBILITY"):
            self.accept(readback=replace(self.readback, observed_at=self.generated))

    def test_expired_witness_fails_even_with_late_cutoff(self):
        later = self.generated + timedelta(minutes=15, microseconds=1)
        with self.assertRaisesRegex(Rejected, "STALE_AT_READBACK"):
            self.accept(readback=replace(self.readback, observed_at=later), cutoff=later)

    def test_race_wrong_base_fails(self):
        with self.assertRaisesRegex(Rejected, "STALE_BASE"):
            check_candidate(self.root, self.head, self.head)

    def test_wrong_path_fails(self):
        with self.assertRaisesRegex(Rejected, "PATHS_MISMATCH"):
            check_candidate(self.root, self.base, self.alternate(extra=True))

    def test_skip_ci_fails(self):
        for msg in ("candidate [skip ci]", "candidate\n\nskip-checks: true"):
            with self.subTest(msg=msg), self.assertRaisesRegex(Rejected, "PUSH_CI_SKIPPED"):
                check_candidate(self.root, self.base, self.alternate(message=msg))

    def test_rewriting_ledger_fails(self):
        bad = {**self.ledger, "snapshots": self.ledger["snapshots"][1:],
               "snapshot_count": self.ledger["snapshot_count"] - 1}
        with self.assertRaisesRegex(Rejected, "NOT_APPEND_ONLY"):
            check_candidate(self.root, self.base, self.alternate(ledger=bad))

    def test_unbound_payload_fails(self):
        bad = {**self.guard, "sources": {**self.guard["sources"],
               "trade_halts": {"status": "UNKNOWN", "extra": True}}}
        with self.assertRaisesRegex(Rejected, "NOT_LEDGER_BOUND"):
            check_candidate(self.root, self.base, self.alternate(guard=bad))


if __name__ == "__main__":
    unittest.main()
