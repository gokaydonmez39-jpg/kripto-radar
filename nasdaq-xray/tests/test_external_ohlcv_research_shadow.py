#!/usr/bin/env python3
"""Negative and synthetic positive OpenBB/Qlib interoperability guards.

Synthetic rows are NOT real vendor bars or license evidence.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import external_ohlcv_research_shadow as bridge
import c418_history_exact_session_shadow_guard as hist

ASOF = "2026-10-16"
CLOCK = dt.datetime(2026, 10, 18, 16, 0, tzinfo=dt.timezone.utc)


class ExternalOHLCVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = hist.official(ASOF)
        assert len(cls.sessions) == 260
        assert cls.sessions[-1] == ASOF

    def setUp(self):
        self.master = {
            "asof_et": ASOF, "pass_symbols": ["AAPL"], "pass_count": 1,
            "unknown_symbols": [], "unknown_count": 0,
            "unknown_never_pass": True, "execution": "NONE", "real_money": "NO-GO",
        }
        self.master_blob = json.dumps(self.master, sort_keys=True).encode()
        self.master_sha = bridge.git_blob_sha(self.master_blob)
        self.openbb = {
            "schema": bridge.SCHEMA, "format": "OPENBB_EQUITY_HISTORICAL",
            "upstream_vendor": "SYNTHETIC_TEST_NOT_A_FEED",
            "symbol": "AAPL", "asof_et": ASOF, "interval": "1d",
            "adjustment": "RAW",
            "rows": [{"date": day, "open": 10, "high": 11,
                      "low": 9, "close": 10.5, "volume": 100_000}
                     for day in self.sessions],
        }

    def result(self, export):
        return bridge.inspect(export, self.master, self.master_blob,
                              self.master_sha, now=CLOCK)

    def test_openbb_exact_260_numeric_only_no_authority(self):
        v = self.result(self.openbb)
        self.assertEqual(v["numeric_exact_260_count"], 1)
        self.assertEqual(v["status"], "RESEARCH_NUMERIC_260X52_COMPLETE_UNATTESTED")
        for key in ("license_rights_proven", "source_feed_entitlement_proven",
                    "exchange_and_RTH_basis_proven",
                    "adjustments_corporate_actions_proven",
                    "source_independence_proven", "data_quality_promotable_to_c417",
                    "can_create_PRIMARY", "can_create_PRICE_PASS",
                    "can_create_HISTORY_PASS", "can_create_MC_PRIMARY",
                    "can_register_R92", "can_send_notification",
                    "alpha_authority", "raw_vendor_rows_exported"):
            self.assertIs(v[key], False, key)
        self.assertNotIn("rows", v)
        self.assertNotIn("volume", v)
        self.assertEqual(v["execution"], "NONE")

    def test_qlib_exact_260_from_real_documented_column_names(self):
        x = copy.deepcopy(self.openbb)
        x["format"] = "QLIB_FEATURES_DAILY"
        x["rows"] = [
            {"instrument": "AAPL", "datetime": d, "$open": 10.0,
             "$high": 11.0, "$low": 9.0, "$close": 10.5, "$volume": 100_000.0}
            for d in self.sessions
        ]
        self.assertEqual(self.result(x)["numeric_exact_260_count"], 1)
        self.assertFalse(self.result(x)["can_register_R92"])

    def test_missing_a_session_stays_incomplete(self):
        x = copy.deepcopy(self.openbb)
        x["rows"].pop(20)
        r = self.result(x)
        self.assertEqual(r["status"], "RESEARCH_NUMERIC_INCOMPLETE_UNATTESTED")
        self.assertIn("MISSING_OFFICIAL_SESSION", r["reason_codes"])

    def test_duplicate_bar_detected_not_silently_deduplicated(self):
        x = copy.deepcopy(self.openbb)
        x["rows"].append(dict(x["rows"][0]))
        r = self.result(x)
        self.assertEqual(r["numeric_exact_260_count"], 0)
        self.assertIn("DUPLICATE_SESSION", r["reason_codes"])

    def test_future_bar_rejected(self):
        x = copy.deepcopy(self.openbb)
        x["rows"].append({**x["rows"][0], "date": "2026-10-19"})
        r = self.result(x)
        self.assertEqual(r["numeric_exact_260_count"], 0)
        self.assertIn("FUTURE_DATED_BAR", r["reason_codes"])

    def test_empty_and_malformed_not_interpreted_as_valid(self):
        for rows in ([], None, [{}], [None], [1]):
            x = copy.deepcopy(self.openbb)
            x["rows"] = rows
            with self.subTest(rows=str(rows)), self.assertRaises(ValueError):
                self.result(x)

    def test_fractional_adjusted_volume_never_passes(self):
        for number in (0.5, 1.25, float(2**53), True, 0, -1, float("inf")):
            x = copy.deepcopy(self.openbb)
            x["rows"][0]["volume"] = number
            with self.subTest(v=number), self.assertRaises(ValueError):
                self.result(x)

    def test_wrong_symbol_or_missing_vendor(self):
        for field, bad in (("symbol", "NVDA"), ("upstream_vendor", ""),
                           ("interval", "1m"), ("adjustment", "UNKNOWN"),
                           ("format", "FRAUD_PRIMARY_FORMAT"), ("asof_et", "2026-10-15")):
            x = copy.deepcopy(self.openbb)
            x[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.result(x)

    def test_wrong_row_symbol_and_qlib_instrument(self):
        x = copy.deepcopy(self.openbb)
        x["rows"][0]["symbol"] = "NVDA"
        with self.assertRaisesRegex(ValueError, "SYMBOL_MISMATCH"):
            self.result(x)
        x = copy.deepcopy(self.openbb)
        x["format"] = "QLIB_FEATURES_DAILY"
        x["rows"] = [{"datetime": ASOF, "instrument": "QQQ", "$open": 10,
                      "$high": 11, "$low": 9, "$close": 10, "$volume": 100}]
        with self.assertRaisesRegex(ValueError, "INSTRUMENT_MISMATCH"):
            self.result(x)

    def test_master_sha_and_epoch_fence(self):
        with self.assertRaisesRegex(ValueError, "MASTER_GIT_BLOB_MISMATCH"):
            bridge.inspect(self.openbb, self.master, self.master_blob,
                           "0" * 40, now=CLOCK)
        future = dt.datetime(2026, 10, 20, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, "MASTER_ASOF_NOT_LATEST_COMPLETED"):
            bridge.inspect(self.openbb, self.master, self.master_blob,
                           self.master_sha, now=future)

    def test_private_raw_export_cannot_be_placed_in_public_repo(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_FILE_INSIDE_PUBLIC_REPO"):
            bridge.read_private(bridge.ROOT / "canonical_current_master_manifest.json")

    def test_ohlc_inconsistent_is_rejected(self):
        x = copy.deepcopy(self.openbb)
        x["rows"][0]["high"] = 9.5
        with self.assertRaisesRegex(ValueError, "OHLC_CONTRADICTION"):
            self.result(x)

    def test_bad_json_nan_infinity_rejected_at_input(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "private.json"
            for text in ('{"rows":[NaN]}', '{"rows":[Infinity]}', "{"):
                p.write_text(text)
                with self.subTest(text=text), self.assertRaisesRegex(
                        ValueError, "PRIVATE_EXPORT_INVALID"):
                    bridge.read_private(p)


if __name__ == "__main__":
    unittest.main()
