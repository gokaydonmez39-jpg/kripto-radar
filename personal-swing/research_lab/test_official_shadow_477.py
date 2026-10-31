"""Adversarial, zero-network contract tests for the isolated 477 shadow."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

import official_shadow_477 as m

ROOT = Path(__file__).resolve().parents[2]
WATCH = json.loads((ROOT/"personal-swing/nasdaq_watchlist_477.json").read_text(encoding="utf-8"))
GUARD = json.loads((ROOT/"nasdaq-xray/canonical_official_source_guard.json").read_text(encoding="utf-8"))

def snapshot(day="2026-10-30"):
    symbols = m.exact_symbols(WATCH)
    return {
        "asof_et":day,
        "requested_symbols":477,
        "processed_symbols":477,
        "valid_data_symbols":477,
        "remaining_symbols":0,
        "insufficient_data_symbols":0,
        "coverage_complete":True,
        "valid_data_coverage_complete":True,
        "new_signal_publishable":True,
        "scope_sha256":m.runner.sha_symbols(symbols),
        "analysis_fingerprint_sha256":m.runner.analysis_fingerprint(),
        "not_broker":True,
        "orders_sent":0,
        "auto_trading":False,
        "failed_groups":[],
        "counts":{"START":477,"TEKNIK_AL_ADAYI":0,
                  "YAKIN_IZLE":0,"ELE":477,"VERI_YETERSIZ":0},
        "rows":[{"symbol":s,"asof_et":day,"decision":"ELE"} for s in symbols],
    }

def guard(stamp="2026-10-30T20:00:00Z"):
    result=deepcopy(GUARD)
    result["generated_at_utc"]=stamp
    return result

class Shadow477Tests(unittest.TestCase):
    def test_exact_live_repo_watchlist_no_reordering(self):
        actual=m.exact_symbols(WATCH)
        self.assertEqual(len(actual),477)
        self.assertEqual(len(set(actual)),477)
        self.assertEqual(actual[:5],["MU","NVDA","META","AAPL","TSLA"])

    def test_current_verified_veto_is_observation_never_clearance(self):
        s=snapshot();g=guard()
        before=m.sha(s);g_before=m.sha(g)
        result=m.make_shadow(s,WATCH,g)
        self.assertEqual(result["status"],m.STATUS)
        self.assertEqual(result["rows_count"],477)
        self.assertEqual([x["symbol"] for x in result["rows"]],
                         WATCH["liquidity_watch_symbols"])
        self.assertEqual(result["nasdaq_source_state"],
                         "OBSERVED_CURRENT_SAFETY_WITNESS_REVIEW_ONLY")
        expected=set(WATCH["liquidity_watch_symbols"]) & set(g["candidate_safety"]["veto_symbols"])
        self.assertEqual(result["nasdaq_veto_events_observed"],len(expected))
        for x in result["rows"]:
            self.assertEqual(x["nasdaq"]=="OBSERVED_VETO_REQUIRES_REVIEW",
                             x["symbol"] in expected)
            self.assertTrue(x["sec"].startswith("UNKNOWN"))
            self.assertTrue(x["alpaca_corporate_actions"].startswith("UNKNOWN"))
            self.assertFalse(x["market_cleared"])
            for flag in ("may_change_al","may_change_stop_or_target",
                         "may_notify","may_place_order","may_write_sheet"):
                self.assertFalse(x[flag])
        self.assertFalse(result["market_clearance_proven"])
        self.assertFalse(result["historical_pit_proven"])
        self.assertFalse(result["may_modify_al"])
        self.assertEqual(m.sha(s),before)
        self.assertEqual(m.sha(g),g_before)
        self.assertEqual(result["sec_unknown"],477)
        self.assertEqual(result["corporate_actions_unknown"],477)

    def test_future_source_must_not_backfill_old_al_decision(self):
        result=m.make_shadow(snapshot(),WATCH,guard("2026-10-31T13:07:05Z"))
        self.assertEqual(result["nasdaq_source_state"],"UNKNOWN_SOURCE_AFTER_EOD_CUTOFF")
        self.assertEqual(result["nasdaq_veto_events_observed"],0)
        self.assertEqual(result["nasdaq_unknown"],477)

    def test_stale_source_never_means_safe(self):
        result=m.make_shadow(snapshot(),WATCH,guard("2026-10-27T10:00:00Z"))
        self.assertEqual(result["nasdaq_source_state"],"UNKNOWN_SOURCE_TOO_OLD")
        self.assertEqual(result["nasdaq_veto_events_observed"],0)

    def test_no_data_around_open_close_cannot_use_holiday(self):
        with self.assertRaisesRegex(m.ShadowRejected,"INVALID_XNAS_SESSION"):
            m.make_shadow(snapshot("2026-10-31"),WATCH,guard())

    def test_corrupt_477_and_duplicate_scope_rejected(self):
        w=deepcopy(WATCH)
        w["liquidity_watch_symbols"][1]=w["liquidity_watch_symbols"][0]
        with self.assertRaisesRegex(m.ShadowRejected,"WATCHLIST_SCOPE_INVALID"):
            m.make_shadow(snapshot(),w,guard())

    def test_partial_scan_rejected_does_not_invent_477(self):
        s=snapshot();s["valid_data_symbols"]=476
        with self.assertRaisesRegex(m.ShadowRejected,"EOD_HANDOFF_REFUSED"):
            m.make_shadow(s,WATCH,guard())

    def test_analysis_fingerprint_drift_is_rejected(self):
        s=snapshot();s["analysis_fingerprint_sha256"]="0"*64
        with self.assertRaisesRegex(m.ShadowRejected,"EOD_HANDOFF_REFUSED"):
            m.make_shadow(s,WATCH,guard())

    def test_duplicate_snapshot_row_rejected(self):
        s=snapshot();s["rows"][1]=deepcopy(s["rows"][0])
        with self.assertRaisesRegex(m.ShadowRejected,"EOD_HANDOFF_REFUSED"):
            m.make_shadow(s,WATCH,guard())

    def test_guard_union_drift_rejected(self):
        g=guard();g["candidate_safety"]["veto_symbols"].pop()
        with self.assertRaisesRegex(m.ShadowRejected,"OFFICIAL_GUARD_VETO_UNION_DRIFT"):
            m.make_shadow(snapshot(),WATCH,g)

    def test_guard_false_pass_rejected(self):
        for field,value in (("status","FAILED"),("alpha_authority",True),
                            ("execution","SEND_ORDER"),("real_money","GO")):
            g=guard();g[field]=value
            with self.subTest(field=field):
                with self.assertRaisesRegex(m.ShadowRejected,
                                            "OFFICIAL_GUARD_AUTHORITY"):
                    m.make_shadow(snapshot(),WATCH,g)

    def test_guard_status_feeds_drift_rejected(self):
        g=guard();g["candidate_safety"]["halt_guard_status"]="UNKNOWN"
        with self.assertRaisesRegex(m.ShadowRejected,"OFFICIAL_GUARD_FEEDS"):
            m.make_shadow(snapshot(),WATCH,g)

    def test_missing_tz_or_invalid_format_rejected(self):
        with self.assertRaisesRegex(m.ShadowRejected,"NAIVE_OBSERVATION_TIME"):
            m.make_shadow(snapshot(),WATCH,guard("2026-10-30T20:00:00"))
        with self.assertRaisesRegex(m.ShadowRejected,"INVALID_OBSERVATION_TIME"):
            m.make_shadow(snapshot(),WATCH,guard("not-a-timestamp"))

    def test_cli_private_copy_and_no_public_signal_leak(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);sp=p/"latest.json";wp=p/"watch.json";gp=p/"guard.json";op=p/"shadow.json"
            s=snapshot()
            sp.write_text(json.dumps(s));wp.write_text(json.dumps(WATCH));gp.write_text(json.dumps(guard()))
            before=sp.read_bytes();console=io.StringIO()
            with redirect_stdout(console):
                code=m.main(["--snapshot",str(sp),"--watchlist",str(wp),
                             "--guard",str(gp),"--out",str(op)])
            self.assertEqual(code,0)
            self.assertEqual(sp.read_bytes(),before)
            saved=json.loads(op.read_text())
            self.assertEqual(saved["rows_count"],477)
            self.assertNotIn('"rows"',console.getvalue())
            self.assertNotIn('"decision"',console.getvalue())
            self.assertIn('"sec_unknown": 477',console.getvalue())

    def test_cli_cannot_overwrite_eod_or_source(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);sp=p/"latest.json";wp=p/"watch.json";gp=p/"guard.json"
            sp.write_text(json.dumps(snapshot()))
            wp.write_text(json.dumps(WATCH));gp.write_text(json.dumps(guard()))
            for illegal in (sp,wp,gp):
                with self.subTest(path=illegal.name):
                    console=io.StringIO()
                    with redirect_stdout(console):
                        result=m.main(["--snapshot",str(sp),"--watchlist",str(wp),
                                       "--guard",str(gp),"--out",str(illegal)])
                    self.assertEqual(result,4)
                    self.assertIn("SHADOW_REFUSED",console.getvalue())

    def test_cli_missing_snapshot_is_explicit_skip_not_pass(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);sp=p/"missing.json";op=p/"out.json"
            console=io.StringIO()
            with redirect_stdout(console):
                code=m.main(["--snapshot",str(sp),"--watchlist","unused",
                             "--guard","unused","--out",str(op)])
            self.assertEqual(code,0)
            self.assertIn("SKIPPED_NO_COMPLETED_SCAN",console.getvalue())
            self.assertFalse(op.exists())

if __name__=="__main__":
    unittest.main()
