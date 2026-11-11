"""P0 recovery regression: reproduce live receipt issues before changing implementation.

No credentials, private market data, network, replay, order, or Sheet writes.
"""
import contextlib
from datetime import date
import io
import unittest
from unittest.mock import patch

import cove_shadow
import cove_private_shadow
import kronos_v2
import runner
from test_cove_shadow import ASOF as COVE_ASOF, bundle as cove_bundle
from test_cove_private_shadow import FakeApi as CoveFakeApi
from test_kronos_v2 import ASOF as KRONOS_ASOF, FakeApi as KronosFakeApi
from test_kronos_v2 import SYMS, SCOPE, POLICY


class ProductionFailureRegression(unittest.TestCase):
    def test_cove_original_scope_order_is_the_source_sha(self):
        """Current EOD signs the original 477 PIT order, never sorted inference."""
        source_order=runner.get_scope(
            watchlist_file="nasdaq_watchlist_477.json",asof=COVE_ASOF)
        self.assertEqual(len(source_order),477)
        self.assertNotEqual(source_order,sorted(source_order))
        src=cove_bundle()
        src["scope_sha256"]=runner.sha_symbols(source_order)
        out=cove_shadow.run_bundle(src)
        self.assertEqual(out["scope"],477)
        self.assertFalse(out["orders"])
        self.assertFalse(out["writes"])

    def test_cove_stage_identifies_flight_failure_without_private_content(self):
        stages=[]
        api=CoveFakeApi()
        with patch.object(cove_private_shadow.kronos_v2,"private_authority",
                return_value=(sorted(runner.get_scope(
                    watchlist_file="nasdaq_watchlist_477.json",asof=COVE_ASOF)),
                    runner.sha_symbols(runner.get_scope(
                    watchlist_file="nasdaq_watchlist_477.json",asof=COVE_ASOF)),
                    runner.analysis_fingerprint(),COVE_ASOF)), \
             patch.object(cove_private_shadow.flight,"inspect",
                          side_effect=RuntimeError("SECRET_EVIDENCE")):
            with self.assertRaises(RuntimeError):
                cove_private_shadow.build_private_bundle(
                    api,COVE_ASOF,lambda symbols,asof:{},stage=stages.append)
        self.assertEqual(stages[-1],"FLIGHT_RECORDER")

    def test_kronos_readonly_stage_identifies_provider_scope_failure(self):
        stages=[]
        api=KronosFakeApi()
        with patch.object(kronos_v2,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,KRONOS_ASOF)):
            with self.assertRaisesRegex(kronos_v2.k.ShadowHold,
                                        "KRONOS2_PROVIDER_SCOPE_DRIFT"):
                kronos_v2.synchronize(
                    api,KRONOS_ASOF,lambda symbols,asof:{},
                    stage=stages.append)
        self.assertEqual(stages[-1],"IEX_SOURCE")
        self.assertEqual(api.writes,0)

    def test_kronos_main_redacts_exception_and_reports_safe_stage(self):
        with patch.object(kronos_v2.k,"eligible_shadow_asof",
                          return_value=KRONOS_ASOF), \
             patch.dict(kronos_v2.os.environ,
                        {"XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"MASKED"},clear=True), \
             patch("private_sheet_writer.SheetApi",
                   side_effect=RuntimeError("SECRET_PRIVATE_TOKEN_DO_NOT_LOG")), \
             contextlib.redirect_stdout(io.StringIO()) as printed:
            status=kronos_v2.main()
        output=printed.getvalue()
        self.assertEqual(status,3)
        self.assertIn('"stage": "SHEET_AUTH"',output)
        self.assertIn('"status": "KRONOS2_HOLD"',output)
        self.assertNotIn("SECRET_PRIVATE_TOKEN",output)
        self.assertNotIn("MASKED",output)

    def test_shadowhold_message_must_never_expose_private_text(self):
        # A dynamically constructed error can carry a secret in its reason.
        with patch.object(kronos_v2.k,"eligible_shadow_asof",
                          return_value=KRONOS_ASOF), \
             patch.dict(kronos_v2.os.environ,
                        {"XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"MASKED"},clear=True), \
             patch("private_sheet_writer.SheetApi",
                   side_effect=kronos_v2.k.ShadowHold(
                       "KRONOS2_SECRET_PRIVATE_TOKEN")), \
             contextlib.redirect_stdout(io.StringIO()) as printed:
            status=kronos_v2.main()
        output=printed.getvalue()
        self.assertEqual(status,3)
        self.assertIn('"reason_code": "KRONOS2_UNCLASSIFIED"',output)
        self.assertNotIn("SECRET_PRIVATE_TOKEN",output)

    def test_kronos_model_load_has_separate_static_stage(self):
        stages=[]
        api=KronosFakeApi()
        from test_kronos_v2 import candles
        def source(symbols,asof):
            return {symbol:candles() for symbol in symbols}
        def failing_model():
            raise RuntimeError("SECRET_MODEL_CONTENT")
        with patch.object(kronos_v2,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,KRONOS_ASOF)), \
             patch.object(kronos_v2.k,"future_xnas_days",
                          return_value=[KRONOS_ASOF]*12):
            with self.assertRaisesRegex(RuntimeError,"SECRET_MODEL_CONTENT"):
                kronos_v2.synchronize(
                    api,KRONOS_ASOF,source,
                    predictor_factory=failing_model,stage=stages.append)
        self.assertEqual(stages[-1],"MODEL_LOAD")
        self.assertEqual(api.writes,0)

if __name__=="__main__":
    unittest.main()
