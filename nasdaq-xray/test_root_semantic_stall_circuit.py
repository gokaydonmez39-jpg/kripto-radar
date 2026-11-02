"""Watchdog no-progress circuit: positive/negative, exact market-session and no-dispatch tests."""
from __future__ import annotations

import base64
import copy
import datetime as dt
import json
from unittest import TestCase, main
from unittest.mock import patch

import root_semantic_stall_circuit as circuit
import github_native_root_watchdog as watchdog

UTC = dt.timezone.utc

def fixture():
    now=dt.datetime(2026,11,2,18,0,tzinfo=UTC)
    old="a"*40
    latest="b"*40
    source={
        "execution":"NONE", "real_money":"NO-GO",
        "status":"PARTIAL_HISTORY","asof_et":"2026-10-30",
        "history_retryable":False,
        "history_retry_reason":"NO_RETRYABLE_HISTORY_WORK_REMAINS",
        "unknown_count":215,
    }
    success={
        "id":12, "name":watchdog.NAME, "head_branch":"main",
        "head_sha":old, "status":"completed", "conclusion":"success",
        "created_at":"2026-11-02T16:30:00Z", "run_attempt":1}
    compare={
        "status":"ahead","behind_by":0,
        "base_commit":{"sha":old}, "head_commit":{"sha":latest},
        "files":[{"filename":"nasdaq-xray/canonical_current_final_gate_overlay.json"}]}
    return {
        "now":now, "last_complete_asof":"2026-10-30",
        "state":source,"last_success":success,
        "current_main_sha":latest,"comparison":compare
    }


class SemanticStallTests(TestCase):
    def test_positive_bounded_source_stall_really_suppresses(self):
        q=fixture()
        actual=circuit.evaluate(**q)
        self.assertTrue(actual["suppress"])
        self.assertEqual(actual["reason"],"SAME_ASOF_NO_RETRYABLE_HISTORY_NO_NEW_SOURCE")
        self.assertEqual(actual["max_suppression_seconds"], 14400)
        self.assertTrue(circuit.evaluate(**dict(q,comparison={
            **q["comparison"],"status":"identical","files":[]}))["suppress"])

    def test_negative_matrix_always_frees_valid_recovery(self):
        cases=[
            ("new_completed_session",lambda q:q.update(last_complete_asof="2026-11-02")),
            ("retryable_history",lambda q:q["state"].update(history_retryable=True)),
            ("missing_history",lambda q:q["state"].pop("history_retryable")),
            ("history_authority_unknown",lambda q:q["state"].update(history_retry_reason="UNKNOWN")),
            ("history_complete",lambda q:q["state"].update(unknown_count=0)),
            ("different_root_state",lambda q:q["state"].update(asof_et="2026-10-29")),
            ("new_code",lambda q:q["comparison"]["files"].append({"filename":"nasdaq-xray/github_native_root_watchdog.py"})),
            ("new_price",lambda q:q["comparison"]["files"].append({"filename":"nasdaq-xray/canonical_current_price_dv30.json"})),
            ("new_official",lambda q:q["comparison"]["files"].append({"filename":"nasdaq-xray/canonical_official_source_guard.json"})),
            ("new_g9",lambda q:q["comparison"]["files"].append({"filename":"nasdaq-xray/g9_entitlement_authority.json"})),
            ("run_failed",lambda q:q["last_success"].update(conclusion="failure")),
            ("run_queued",lambda q:q["last_success"].update(status="queued")),
            ("run_unknown_sha",lambda q:q["last_success"].update(head_sha="wrong")),
            ("main_unknown_sha",lambda q:q.update(current_main_sha="wrong")),
            ("wrong_compare_head",lambda q:q["comparison"]["head_commit"].update(sha="f"*40)),
            ("wrong_compare_base",lambda q:q["comparison"]["base_commit"].update(sha="f"*40)),
            ("diverged",lambda q:q["comparison"].update(status="diverged")),
            ("behind",lambda q:q["comparison"].update(behind_by=1)),
            ("missing_files",lambda q:q["comparison"].pop("files")),
            ("incomplete_changes",lambda q:q["comparison"].update(files=[{"filename":"X"}]*300)),
            ("invalid_time",lambda q:q.update(now=q["now"].replace(tzinfo=None))),
            ("future_run",lambda q:q["last_success"].update(created_at="2026-11-02T18:05:00Z")),
            ("old_success",lambda q:q["last_success"].update(created_at="2026-11-02T13:30:00Z")),
            ("missing_run_stamp",lambda q:q["last_success"].pop("created_at")),
            ("missing_session",lambda q:q.update(last_complete_asof=None)),
            ("unknown_safety",lambda q:q["state"].update(execution="LIVE")),
        ]
        for name,mutation in cases:
            with self.subTest(case=name):
                q=copy.deepcopy(fixture())
                mutation(q)
                result=circuit.evaluate(**q)
                self.assertFalse(result["suppress"],name)

    def test_live_wiring_with_mocked_read_only_github_gets(self):
        q=fixture()
        raw=json.dumps(q["state"]).encode()
        source={"encoding":"base64","sha":"f"*40,
                "content":base64.b64encode(raw).decode()}
        urls=[]
        def get(method,path,token,payload=None):
            self.assertEqual(method,"GET") # no dispatch, never POST
            urls.append(path)
            if path.startswith("/contents/"):
                return source
            if path.startswith("/actions/runs/12/jobs"):
                return {"jobs":[{"name":"dataplane","steps":[
                    {"name":"Run autonomous XRAY data plane","conclusion":"success"}]}]}
            if path.startswith("/compare/"):
                return q["comparison"]
            self.fail("UNEXPECTED_NETWORK_ROUTE")
        first={"decision":"STALE_ROOT_ELIGIBLE", "dispatch_allowed":True,
               "latest_root_id":12,"last_success_id":12}
        with patch.object(watchdog,"github",side_effect=get), patch.object(
            watchdog,"last_complete_session",return_value="2026-10-30"):
            r=watchdog.root_productivity_gate("test",q["now"],first,
                        [q["last_success"]],q["current_main_sha"])
        self.assertTrue(r["suppress"])
        self.assertEqual(len(urls),3)
        self.assertTrue(any("/actions/runs/12/jobs" in path for path in urls))

    def test_new_source_unblocks_even_when_old_history_still_unknown(self):
        q=fixture()
        q["comparison"]["files"].append({"filename":"nasdaq-xray/official_pit_ledger.json"})
        r=circuit.evaluate(**q)
        self.assertFalse(r["suppress"])
        self.assertEqual(r["reason"],"NEW_TRACKED_SOURCE_OR_CODE_EVIDENCE")

    def test_newer_green_no_compute_does_not_reset_real_compute_quota(self):
        q=fixture()
        real=q["last_success"]
        noop=dict(real,id=13,created_at="2026-11-02T17:30:00Z")
        refs=[noop,real]
        by_id={
            13: "skipped", 12: "success",
        }
        def api(method,path,token,payload=None):
            self.assertEqual(method,"GET")
            if path.startswith("/actions/runs/"):
                import re
                matched=re.search(r"/actions/runs/(\\d+)/jobs",path)
                self.assertIsNotNone(matched)
                value=by_id[int(matched.group(1))]
                return {"jobs":[{"name":"dataplane","steps":[
                    {"name":"Run autonomous XRAY data plane","conclusion":value}]}]}
            if path.startswith("/contents/"):
                raw=json.dumps(q["state"]).encode()
                return {"sha":"f"*40, "encoding":"base64",
                        "content":base64.b64encode(raw).decode()}
            if path.startswith("/compare/"):
                return q["comparison"]
            self.fail("UNEXPECTED_API")
        first={"dispatch_allowed":True,"latest_root_id":13,"last_success_id":13}
        with patch.object(watchdog,"github",side_effect=api), patch.object(
            watchdog,"last_complete_session",return_value="2026-10-30"):
            out=watchdog.root_productivity_gate("token",q["now"],first,
                                                refs,q["current_main_sha"])
        self.assertTrue(out["suppress"])
        self.assertEqual(out["last_success_age_seconds"],5400)

    def test_control_only_success_older_than_four_hours_frees_recovery(self):
        q=fixture()
        old=dict(q["last_success"],created_at="2026-11-02T13:30:00Z")
        green=dict(q["last_success"],id=13,created_at="2026-11-02T17:30:00Z")
        touched=[]
        def api(method,path,token,payload=None):
            touched.append(path)
            if "/actions/runs/13/jobs" in path:
                return {"jobs":[{"steps":[{
                    "name":"Run autonomous XRAY data plane","conclusion":"skipped"}]}]}
            self.fail("API_CALLED_AFTER_COMPUTE_WINDOW_EXPIRED")
        first={"dispatch_allowed":True,"latest_root_id":13,"last_success_id":13}
        with patch.object(watchdog,"github",side_effect=api):
            out=watchdog.root_productivity_gate("token",q["now"],first,
                                                [green,old],q["current_main_sha"])
        self.assertFalse(out["suppress"])
        self.assertIn("NO_RECENT_COMPUTE",out["reason"])
        self.assertEqual(len(touched),1)

    def test_newest_failed_root_is_not_suppressed(self):
        q=fixture()
        first={"decision":"STALE_ROOT_ELIGIBLE", "dispatch_allowed":True,
               "latest_root_id":13,"last_success_id":12}
        with patch.object(watchdog,"github",side_effect=AssertionError("NO_READ_EXPECTED")):
            r=watchdog.root_productivity_gate("test",q["now"],first,
                        [q["last_success"]],q["current_main_sha"])
        self.assertFalse(r["suppress"])
        self.assertEqual(r["reason"],"RECOVERY_OR_FIRST_ROOT_REQUIRED")

    def test_official_xnas_completed_session_boundary(self):
        from source_epoch_freshness_guard import last_complete_session
        def at(h,m=0):
            return dt.datetime(2026,11,2,h,m,tzinfo=UTC)
        self.assertEqual(last_complete_session(at(18)), "2026-10-30")
        self.assertEqual(last_complete_session(at(21,29)), "2026-10-30")
        self.assertEqual(last_complete_session(at(21,30)), "2026-11-02")

    def test_existing_workflow_single_cron_without_extra_task(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[1]/
              ".github/workflows/xray-github-native-root-watchdog.yml").read_text()
        self.assertEqual(text.count("  schedule:\n"),1)
        self.assertEqual(text.count('    - cron: "*/15 * * * 1-5"'),1)
        self.assertIn("root_semantic_stall_circuit.py",text)
        self.assertIn("test_root_semantic_stall_circuit.py",text)
        self.assertIn("Double-read and dispatch existing root only if stale",text)

if __name__ == "__main__":
    main()
