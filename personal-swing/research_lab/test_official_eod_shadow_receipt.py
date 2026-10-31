"""Synthetic zero-network acceptance and falsification for EOD shadow receipts."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

import official_eod_shadow_receipt as m


def fixture(source_at="2026-10-30T20:15:00+00:00"):
    symbols = [f"SYM{i:03d}" for i in range(477)]
    snapshot = {
        "asof_et": "2026-10-30",
        "scope_sha256": "a" * 64,
        "analysis_fingerprint_sha256": "b" * 64,
        "rows": [{"symbol": s} for s in symbols],
    }
    guard = {"status": "PASS", "alpha_authority": False}
    rows = [{
        "symbol": s,
        "nasdaq": "UNKNOWN_NOT_A_MARKET_CLEARANCE",
        "sec": "UNKNOWN_NOT_477_PIT_PROVEN",
        "alpaca_corporate_actions": "UNKNOWN_NO_PER_SYMBOL_TIMELY_LEDGER",
        **{flag: False for flag in m.ROW_FLAGS},
    } for s in symbols]
    receipt = {
        "schema": m.SCHEMA,
        "status": m.STATUS,
        "asof_et": "2026-10-30",
        "rows_count": 477,
        "rows": rows,
        "scope_sha256": snapshot["scope_sha256"],
        "analysis_fingerprint_sha256": snapshot["analysis_fingerprint_sha256"],
        "private_eod_snapshot_sha256": m.digest(snapshot),
        "nasdaq_witness_sha256": m.digest(guard),
        "market_clearance_proven": False,
        "historical_pit_proven": False,
        "first_public_availability_proven": False,
        "may_modify_al": False,
        "may_write_sheet": False,
        "may_notify": False,
        "may_place_order": False,
        "no_network_calls": True,
        "sec_unknown": 477,
        "corporate_actions_unknown": 477,
        "decision_cutoff_utc": "2026-10-30T20:45:00+00:00",
        "source_observed_at_utc": source_at,
        "nasdaq_source_state": m.CURRENT,
        "nasdaq_veto_events_observed": 0,
        "nasdaq_unknown": 477,
    }
    return snapshot, receipt, guard


class EodShadowReceiptTests(unittest.TestCase):
    def test_valid_477_receipt_never_grants_market_authority(self):
        self.assertEqual(m.verify(*fixture()),
                         "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")

    def test_future_source_cannot_appear_current_at_old_decision(self):
        s, r, g = fixture("2026-10-31T15:28:02+00:00")
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "SOURCE_TIME_CLASSIFICATION_DRIFT"):
            m.verify(s, r, g)
        r["nasdaq_source_state"] = m.AFTER
        self.assertEqual(m.verify(s, r, g),
                         "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")

    def test_stale_source_never_implies_clearance(self):
        s, r, g = fixture("2026-10-27T09:00:00+00:00")
        r["nasdaq_source_state"] = m.STALE
        self.assertEqual(m.verify(s, r, g),
                         "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")

    def test_future_or_stale_event_flags_refused(self):
        for state, observed_at in ((m.AFTER, "2026-10-31T14:00:00Z"),
                                   (m.STALE, "2026-10-27T14:00:00Z")):
            with self.subTest(state=state):
                s, r, g = fixture(observed_at)
                r["nasdaq_source_state"] = state
                r["rows"][0]["nasdaq"] = "OBSERVED_VETO_REQUIRES_REVIEW"
                r["nasdaq_veto_events_observed"] = 1
                r["nasdaq_unknown"] = 476
                with self.assertRaisesRegex(m.ReceiptRefused,
                                            "NASDAQ_REVIEW_COUNT_OR_ASOF_DRIFT"):
                    m.verify(s, r, g)

    def test_scope_order_and_partial_477_rejected(self):
        s, r, g = fixture()
        r["rows"][0], r["rows"][1] = r["rows"][1], r["rows"][0]
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "SHADOW_SYMBOL_ORDER_OR_SCOPE_DRIFT"):
            m.verify(s, r, g)
        s, r, g = fixture()
        r["rows"].pop()
        with self.assertRaisesRegex(m.ReceiptRefused, "SHADOW_ROWS_INVALID"):
            m.verify(s, r, g)

    def test_private_snapshot_or_guard_hash_mutation_rejected(self):
        s, r, g = fixture()
        s["rows"][0]["decision"] = "ALTERED"
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "SHADOW_SOURCE_DIGEST_MISMATCH"):
            m.verify(s, r, g)
        s, r, g = fixture()
        g["status"] = "CHANGED"
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "SHADOW_GUARD_DIGEST_MISMATCH"):
            m.verify(s, r, g)

    def test_risk_clearance_or_side_effect_authority_rejected(self):
        for field in m.TOP_FLAGS:
            s, r, g = fixture()
            r[field] = True
            with self.subTest(field=field):
                with self.assertRaisesRegex(m.ReceiptRefused,
                                            "UNAUTHORIZED_SHADOW_AUTHORITY"):
                    m.verify(s, r, g)
        s, r, g = fixture()
        r["rows"][0]["may_place_order"] = True
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "ROW_RISK_OR_AUTHORITY_DRIFT"):
            m.verify(s, r, g)

    def test_unproven_sec_and_alpaca_cannot_be_declared_clean(self):
        s, r, g = fixture()
        r["rows"][0]["alpaca_corporate_actions"] = "NO_EVENTS_CLEAR"
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "ROW_RISK_OR_AUTHORITY_DRIFT"):
            m.verify(s, r, g)
        s, r, g = fixture()
        r["sec_unknown"] = 476
        with self.assertRaisesRegex(m.ReceiptRefused,
                                    "UNPROVEN_SOURCE_INCORRECTLY_CLEARED"):
            m.verify(s, r, g)

    def test_skip_only_without_snapshot_and_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.assertEqual(m.evaluate(p/"missing", p/"out", p/"guard"),
                             "SKIPPED_NO_COMPLETED_SCAN")
            (p/"out").write_text("{}")
            with self.assertRaisesRegex(m.ReceiptRefused,
                                        "ORPHAN_SHADOW_WITHOUT_COMPLETED_EOD"):
                m.evaluate(p/"missing", p/"out", p/"guard")

    def test_missing_ledger_refused_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/"snap").write_text("{}")
            with self.assertRaisesRegex(m.ReceiptRefused,
                                        "MISSING_SHADOW_OUTPUT"):
                m.evaluate(p/"snap", p/"out", p/"guard")

    def test_duplicate_json_key_and_nonfinite_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"bad.json"
            p.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(m.ReceiptRefused,
                                        "DUPLICATE_JSON_KEY"):
                m.read_private(p)
            p.write_text('{"x":NaN}')
            with self.assertRaisesRegex(m.ReceiptRefused, "NONFINITE_JSON"):
                m.read_private(p)

    def test_cli_readback_and_public_log_without_private_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            s, r, g = fixture()
            for name, obj in (("snap", s), ("receipt", r), ("guard", g)):
                (p/name).write_text(json.dumps(obj), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = m.main(["--snapshot", str(p/"snap"),
                               "--receipt", str(p/"receipt"),
                               "--guard", str(p/"guard")])
            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["official_shadow_receipt"],
                             "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE")
            self.assertFalse(result["market_clearance_proven"])
            self.assertNotIn("SYM000", stdout.getvalue())
            self.assertNotIn("rows", stdout.getvalue())

    def test_workflow_requires_distinct_skip_readback_and_refusal(self):
        root = Path(__file__).resolve().parents[2]
        content = (root / ".github/workflows/xray-personal-477-eod.yml").read_text()
        marker = "name: Optional official 477 PIT-aware shadow ledger"
        self.assertIn(marker, content)
        block = content.split(marker, 1)[1].split(
            "  private-sheets-auth-preflight:", 1)[0]
        self.assertIn("OFFICIAL_SHADOW=SKIPPED_NO_COMPLETED_SCAN", block)
        self.assertIn("official_eod_shadow_receipt.py", block)
        self.assertIn("OFFICIAL_SHADOW=FAILED_INDEPENDENT_NOT_MARKET_CLEARANCE",
                      block)
        self.assertIn("OFFICIAL_SHADOW=RECEIPT_VERIFIED_RESEARCH_ONLY", block)
        self.assertLess(block.index("OFFICIAL_SHADOW=SKIPPED_NO_COMPLETED_SCAN"),
                        block.index("python research_lab/official_shadow_477.py"))
        self.assertIn("continue-on-error: true", block)


if __name__ == "__main__":
    unittest.main()
