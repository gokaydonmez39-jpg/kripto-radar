"""Isolated private research adapter tests; zero OAuth, data API or Sheet access."""
import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import cove_private_shadow as priv
import private_sheet_writer as writer
import runner
from test_cove_shadow import ASOF, ENTRY, SCOPE, SYMBOL, baseline_bars


def candidate():
    return [ENTRY+"|"+SYMBOL,ENTRY,SYMBOL,"TEKNIK AL",
            "100","95","110","AÇIK • 0/15 SEANS","","","","","private"]


class FakeApi:
    def __init__(self):
        self.rows={
            "ADAY_GECMISI":[list(writer.CANDIDATE_HEADER),candidate()],
            "TARAMA_KAYITLARI":[list(writer.SCAN_HEADER),
                [ASOF,"schedule","477","477","477","0","TRUE","1",
                 "private-run-url","source private"]],
            "UYARI_OLAYLARI":[["private header"]],
            "PANEL":[["PANEL","B"]]}
        self.calls=[]
        self.rewrite_after=None
    def read(self,tab,last):
        self.calls.append((tab,last))
        if self.rewrite_after is not None and len(self.calls)>self.rewrite_after and tab=="PANEL":
            return [["CHANGED","B"]]
        return copy.deepcopy(self.rows[tab])
    def apply(self,*args):
        raise AssertionError("Sheet write not allowed")
    def request(self,*args,**kw):
        raise AssertionError("No direct network from test")


def flight_ok():
    return dict(latest_verified_scan_asof=ASOF,
                unreserved_current_eod_al=0,unreserved_prior_eod_al=0,
                panel_non_authoritative_stale=False,panel_missing_asof=False)


class PrivateReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeApi()
        self.read_calls=[]
        a=patch.object(priv.kronos_v2,"private_authority",
            return_value=(SCOPE,runner.sha_symbols(SCOPE),
                          runner.analysis_fingerprint(),ASOF))
        b=patch.object(priv.flight,"inspect",return_value=flight_ok())
        a.start();b.start()
        self.addCleanup(a.stop);self.addCleanup(b.stop)
    def reader(self,syms,asof):
        self.read_calls.append((list(syms),asof))
        return {s:baseline_bars() for s in syms}

    def test_authenticated_readonly_paper_bundle(self):
        result=priv.run_private(ASOF,self.api,self.reader)
        self.assertEqual(result["scope"],477)
        self.assertEqual(result["alpha_claim"],"HOLD_UNVERIFIED_PIT_OOS")
        self.assertFalse(result["orders"]);self.assertFalse(result["writes"])
        self.assertEqual(self.read_calls,[([SYMBOL],ASOF)])
        self.assertEqual(len(self.api.calls),8)

    def test_oauth_proxy_refuses_post_and_apply(self):
        api=priv.ReadOnlySheetApi.__new__(priv.ReadOnlySheetApi)
        with self.assertRaisesRegex(priv.CovePrivateHold,"READ_ONLY_WRITE_FORBIDDEN"):
            api.request(":batchUpdate",method="POST",body={"requests":[]})
        with self.assertRaisesRegex(priv.CovePrivateHold,"READ_ONLY_WRITE_FORBIDDEN"):
            api.apply({})

    def test_incomplete_477_source_fails_before_vendor(self):
        self.api.rows["TARAMA_KAYITLARI"][1][4]="476"
        with self.assertRaisesRegex(priv.CovePrivateHold,"SOURCE_NOT_477"):
            priv.build_private_bundle(self.api,ASOF,self.reader)
        self.assertFalse(self.read_calls)

    def test_duplicate_candidate_blocks_without_provider(self):
        self.api.rows["ADAY_GECMISI"].append(candidate())
        with self.assertRaisesRegex(priv.CovePrivateHold,"DUPLICATE_EPISODE_ROW"):
            priv.build_private_bundle(self.api,ASOF,self.reader)
        self.assertFalse(self.read_calls)

    def test_missing_provider_response_blocks(self):
        with self.assertRaisesRegex(priv.CovePrivateHold,"PROVIDER_SYMBOL_SCOPE_MISMATCH"):
            priv.build_private_bundle(self.api,ASOF,lambda syms,asof:{})
        self.assertFalse(self.read_calls)

    def test_stale_source_flight_blocks(self):
        with patch.object(priv.flight,"inspect",
                          return_value={**flight_ok(),"unreserved_current_eod_al":1}):
            with self.assertRaisesRegex(priv.CovePrivateHold,"FLIGHT_RECORDER_NOT_READY"):
                priv.build_private_bundle(self.api,ASOF,self.reader)
        self.assertFalse(self.read_calls)

    def test_private_sheet_race_detected(self):
        self.api.rewrite_after=4
        with self.assertRaisesRegex(priv.CovePrivateHold,"CONCURRENT_PRIVATE_SOURCE_DRIFT"):
            priv.build_private_bundle(self.api,ASOF,self.reader)
        self.assertEqual(len(self.read_calls),1)

    def test_wrong_authority_cohort_blocks(self):
        with patch.object(priv.kronos_v2,"private_authority",
                          return_value=(SCOPE[:-1],"bad","bad",ASOF)):
            with self.assertRaisesRegex(priv.CovePrivateHold,"AUTHORITY_ASOF_OR_SCOPE_MISMATCH"):
                priv.build_private_bundle(self.api,ASOF,self.reader)
        self.assertFalse(self.api.calls)

    def test_no_episode_no_provider_no_alpha(self):
        self.api.rows["ADAY_GECMISI"]=[list(writer.CANDIDATE_HEADER)]
        out=priv.run_private(ASOF,self.api,self.reader)
        self.assertEqual(out["baseline"]["status"],"HOLD_NO_EPISODES")
        self.assertFalse(self.read_calls)

    def test_log_redaction_on_exception(self):
        with patch.dict(priv.os.environ,{
                "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"secret",
                "XRAY_PRIVATE_SPREADSHEET_ID":"private"},clear=True), \
             patch.object(priv,"ReadOnlySheetApi",
                 side_effect=RuntimeError("SECRET_PRIVATE_TOKEN_AND_SYMBOL")), \
             redirect_stdout(io.StringIO()) as buf:
            exit_code=priv.main()
        self.assertEqual(exit_code,3)
        self.assertIn("HOLD_NO_DATA_PUBLISHED_NO_WRITES",buf.getvalue())
        self.assertNotIn("SECRET_PRIVATE",buf.getvalue())

    def test_readonly_scope_in_source_and_no_apply_call(self):
        from pathlib import Path
        source=Path(priv.__file__).read_text(encoding="utf-8")
        self.assertIn("spreadsheets.readonly",source)
        self.assertNotIn("api.apply(",source)


if __name__=="__main__":
    unittest.main()
