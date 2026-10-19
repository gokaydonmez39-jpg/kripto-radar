"""Regression: HTTP 429/403 must retain a complete, truthful PRICE research report.

Offline fixtures. No Alpaca HTTP, no vendor OHLCV, no broker or signal.
"""
import datetime as dt
import json
import tempfile
import urllib.error
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpaca_personal_price_current_exact30 as price

ASOF="2026-10-16"
DATES=["2026-10-16"]

def fake_census(halfway):
    with tempfile.TemporaryDirectory() as temp_input, tempfile.TemporaryDirectory() as temp_output:
        p=Path(temp_input)/"repo"/"nasdaq-xray"
        p.mkdir(parents=True)
        (p/"canonical_current_master_manifest.json").write_text("{}")
        (p/"canonical_current_price_dv30.json").write_text("{}")
        output=Path(temp_output)/"price_cliff.json"
        n=[0]
        def fake_fetch(block,dates,credentials,counter,asof):
            n[0]+=1
            counter[0]+=1
            if halfway and n[0]==1:
                return {},{}
            raise urllib.error.HTTPError("https://example.invalid",429,
                                          "Too many requests",None,None)
        with patch.object(price,"ROOT",p),patch.object(price,"BATCH",1),patch.object(
                price,"scope",return_value=(ASOF,["AAPL","MSFT"],DATES)),patch.object(
                price,"dynamic_analyze",side_effect=lambda block,*args:
                {block[0]:price.INTEGRITY_UNKNOWN}):
            result=price.census(dt.datetime(2026,10,19,12,tzinfo=dt.timezone.utc),
                                ("OFFLINE","OFFLINE"),output,fetcher=fake_fetch)
        assert output.is_file()
        persisted=json.loads(output.read_text())
        assert persisted==result
        return result

class AlpacaPriceCliffReportContract(TestCase):
    def test_report_fields_present_even_before_recheck(self):
        report=price.empty_report(ASOF,["AAPL"],DATES,"a"*40,"b"*40)
        self.assertEqual(report["integrity_recheck_unresolved_reason_counts"],{})
        self.assertEqual(report["integrity_recheck_detail_counts"],{})

    def test_mid_census_rate_cliff_keeps_gap_and_epoch(self):
        report=fake_census(True)
        self.assertEqual(report["provider_cliff"],"RATE_LIMIT_OR_BUDGET")
        self.assertEqual(report["integrity_recheck_status"],"SKIPPED_PROVIDER_CLIFF")
        self.assertEqual(report["integrity_recheck_candidate_count"],1)
        self.assertEqual(report["integrity_recheck_unresolved"],1)
        self.assertEqual(report["integrity_recheck_unresolved_reason_counts"],
                         {"UNATTEMPTED_BUDGET_OR_LIMIT":1})
        self.assertEqual(report["counts"],{
            "UNKNOWN_HTTP_429":1,
            "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW":1})
        self.assertEqual(report["asof_et"],ASOF)
        self.assertEqual(report["price_primary_pass_count"],0)
        self.assertFalse(report["registered_R92_created"])
        self.assertFalse(report["canonical_price_promoted"])

    def test_first_batch_cliff_never_fabricates_recheck(self):
        report=fake_census(False)
        self.assertEqual(report["provider_cliff"],"RATE_LIMIT_OR_BUDGET")
        self.assertEqual(report["integrity_recheck_status"],"SKIPPED_PROVIDER_CLIFF")
        self.assertEqual(report["integrity_recheck_candidate_count"],0)
        self.assertEqual(report["integrity_recheck_unresolved"],0)
        self.assertEqual(report["integrity_recheck_unresolved_reason_counts"],{})
        self.assertEqual(report["counts"],{
            "UNKNOWN_HTTP_429":1,
            "UNKNOWN_NOT_ATTEMPTED":1})
        self.assertEqual(report["classified_count"],1)
        self.assertEqual(report["scope_total"],2)
        self.assertFalse(report["all_symbols_classified"])
        self.assertEqual(report["price_primary_pass_count"],0)
        self.assertFalse(report["registered_R92_created"])

if __name__=="__main__":
    import unittest
    unittest.main()
