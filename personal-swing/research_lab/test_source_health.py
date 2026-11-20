"""Synthetic RED/GREEN source-health cases. No private inputs or network."""
from copy import deepcopy
import json
import unittest

from source_health import EOD, REPOSITORY, WORKFLOWS
from test_private_research_readback import fixture
from test_unified_evidence_bridge import run as decision_view
from unified_evidence_bridge import compose_source_health


ASOF, RUN, HEAD = "2026-01-02", 100, "a" * 40


def receipt(source, outcome, metrics):
    canonical = WORKFLOWS[source] == EOD
    return {"source": source, "asof": ASOF, "eod_run_id": RUN,
            "eod_head_sha": HEAD,
            "run": {"id": RUN if canonical else (101 if source == "KRONOS_V2" else 102),
                    "path": WORKFLOWS[source], "repository": REPOSITORY,
                    "branch": "main", "head_sha": HEAD, "attempt": 1,
                    "event": "schedule" if canonical else "workflow_run",
                    "status": "completed", "conclusion": "success"},
            "result": outcome, "metrics": metrics}


def example():
    return [receipt("CORE", "CORE_EOD_READBACK_VERIFIED", {
                "requested": 477, "processed": 477, "valid": 477, "missing": 0,
                "history_sessions": 52, "feed": "ALPACA_IEX_RAW_1DAY", "calendar": "XNAS",
                "final_ready": True, "guardian_verified": True, "score_verified": True}),
            receipt("KRONOS_V2", "KRONOS2_PRIVATE_READBACK_CLOSE_ONLY", {
                "symbols": 477, "rows": 1431, "horizons": [1, 5, 12],
                "full_geometry": 377, "close_only": 100, "qc_hold": 0}),
            receipt("COVE", "READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS", {}),
            receipt("OFFICIAL_477", "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE",
                    {"rows": 477, "pit_verified": False, "market_clearance": False})]


def health(receipts):
    return compose_source_health(asof=ASOF, eod_run_id=RUN, eod_head_sha=HEAD,
                                 receipts=receipts)


class SourceHealthTest(unittest.TestCase):
    def test_matches_four_lanes_without_authority(self):
        view = health(example())
        self.assertEqual([x["state"] for x in view["sources"].values()], [
            "MATCHED_CORE_RECEIPT", "MATCHED_CLOSE_ONLY", "MATCHED_RESEARCH_READONLY",
            "MATCHED_RESEARCH_NO_MARKET_CLEARANCE"])
        self.assertEqual(view["source_authentication"], "CALLER_WITNESS_NOT_ATTESTED")
        self.assertEqual(view["decision_influence"], "NO_GO")
        self.assertTrue(all(x is False for k, x in view.items() if k.startswith("may_")))

    def test_every_single_source_absence_is_isolated(self):
        inp = example()
        before = health(inp)["sources"]
        for idx, entry in enumerate(inp):
            with self.subTest(source=entry["source"]):
                after = health(inp[:idx] + inp[idx+1:])["sources"]
                self.assertEqual(after.pop(entry["source"])["state"], "UNKNOWN")
                self.assertEqual(after, {k: v for k, v in before.items() if k != entry["source"]})

    def test_mismatched_epoch_isolated(self):
        baseline = health(example())["sources"]
        for key, value in [("asof", "2026-01-05"), ("asof", "2026-01-01"),
                           ("eod_head_sha", "b"*40), ("eod_run_id", 999)]:
            with self.subTest(key=key, value=value):
                inp = example()
                inp[1][key] = value
                actual = health(inp)["sources"]
                self.assertEqual(actual.pop("KRONOS_V2"),
                                 {"state": "HOLD", "reason": "SOURCE_EPOCH_MISMATCH"})
                self.assertEqual(actual, {k: v for k, v in baseline.items() if k != "KRONOS_V2"})

    def test_wrong_workflow_branch_repo_event_attempt_and_head_fail(self):
        for key, value in [("id", RUN), ("path", EOD), ("attempt", True), ("attempt", 2),
                           ("event", "workflow_dispatch"), ("branch", "test"),
                           ("repository", "other/repo"), ("head_sha", "c"*40)]:
            with self.subTest(key=key, value=value):
                inp = example()
                inp[2]["run"][key] = value
                self.assertEqual(health(inp)["sources"]["COVE"]["reason"], "RUN_IDENTITY_MISMATCH")

    def test_failed_or_queued_jobs_not_promoted(self):
        for key, value in [("conclusion", "failure"), ("status", "in_progress")]:
            inp = example()
            inp[2]["run"][key] = value
            self.assertEqual(health(inp)["sources"]["COVE"]["reason"], "RUN_NOT_SUCCESSFUL")

    def test_green_job_alone_does_not_admit_receipt(self):
        inp = example()
        inp[2]["result"] = "success"
        inp[3]["result"] = "SKIP_NONMATCHING_CLOSE"
        out = health(inp)["sources"]
        self.assertEqual(out["COVE"]["state"], "HOLD")
        self.assertEqual(out["OFFICIAL_477"]["state"], "HOLD")

    def test_no_candle_quality_substitution(self):
        inp = example()
        inp[1]["result"] = "KRONOS2_PRIVATE_READBACK_FULL_GEOMETRY"
        self.assertEqual(health(inp)["sources"]["KRONOS_V2"]["reason"],
                         "KRONOS_RECEIPT_QUALITY_MISMATCH")
        inp[1]["metrics"].update(full_geometry=477, close_only=0)
        self.assertEqual(health(inp)["sources"]["KRONOS_V2"]["state"], "MATCHED_FULL_GEOMETRY")

    def test_invalid_kronos_shapes_and_qc(self):
        for edits, expected in [({"rows": 1430}, "KRONOS_SCOPE_COUNT"),
                                 ({"horizons": [True, 5, 12]}, "KRONOS_SCOPE_COUNT"),
                                 ({"close_only": -1}, "KRONOS_QUALITY_COUNTS"),
                                 ({"full_geometry": 376, "qc_hold": 1}, "KRONOS_QC_HOLD")]:
            inp = example()
            inp[1]["metrics"].update(edits)
            self.assertEqual(health(inp)["sources"]["KRONOS_V2"]["reason"], expected)

    def test_duplicate_only_holds_duplicated_source(self):
        inp = example()
        inp.append(deepcopy(inp[2]))
        out = health(inp)["sources"]
        self.assertEqual(out["COVE"]["reason"], "DUPLICATE_RECEIPT")
        self.assertEqual(out["CORE"]["state"], "MATCHED_CORE_RECEIPT")

    def test_private_fields_and_unknown_entries_are_not_echoed(self):
        inp = example()
        inp[2]["metrics"]["private"] = "SENSITIVE_FIXTURE_SENTINEL"
        inp.append({"source": "SENSITIVE_FIXTURE_SENTINEL"})
        out = health(inp)
        self.assertEqual(out["ignored_receipt_count"], 1)
        self.assertEqual(out["sources"]["COVE"]["state"], "HOLD")
        self.assertNotIn("SENSITIVE_FIXTURE_SENTINEL", json.dumps(out))

    def test_private_decision_output_unchanged_and_inputs_not_mutated(self):
        f = fixture()
        digest = lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"))
        canonical = digest(decision_view(f))
        inp = example()
        before = deepcopy(inp)
        health(inp)
        self.assertEqual(inp, before)
        for idx in range(len(inp)):
            health(inp[:idx] + inp[idx+1:])
            self.assertEqual(digest(decision_view(f)), canonical)

    def test_invalid_expected_epoch_and_input_limits_fail(self):
        for overrides, cause in [({"asof": "2026-01-32"}, "INVALID_EXPECTED_EPOCH"),
                                  ({"eod_run_id": True}, "INVALID_EXPECTED_EPOCH"),
                                  ({"eod_head_sha": "xx"}, "INVALID_EXPECTED_EPOCH"),
                                  ({"receipts": [{}]*33}, "RECEIPT_INPUT_LIMIT")]:
            args = {"asof": ASOF, "eod_run_id": RUN, "eod_head_sha": HEAD, "receipts": []}
            with self.assertRaisesRegex(ValueError, cause):
                compose_source_health(**(args | overrides))
