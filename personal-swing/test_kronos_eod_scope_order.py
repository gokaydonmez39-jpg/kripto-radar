"""Proves Kronos V2 must hash the EOD original-order scope, not sorted inference order."""
import unittest
from unittest.mock import patch
from pathlib import Path

import kronos_v2 as kronos
import runner
import private_sheet_writer as writer
import swing_score_daily as score

DAY="2026-11-10"
WATCH=Path(__file__).with_name("nasdaq_watchlist_477.json")
SCOPE=runner.get_scope(watchlist_file=str(WATCH),asof=DAY)
SOURCE_SHA=runner.sha_symbols(SCOPE)
POLICY_SHA=runner.analysis_fingerprint()


class AuthorityApi:
    def __init__(self,bad_source=False):
        self.bad_source=bad_source
    def check_metadata(self):
        return True
    def read(self,tab,cols):
        if (tab,cols)!=("TARAMA_KAYITLARI","J"):
            raise AssertionError("no other private data requested")
        prov="0"*64 if self.bad_source else SOURCE_SHA
        return [list(writer.SCAN_HEADER),
            [DAY,"GitHub schedule VERIFIED IEX EOD",
             "477","477","477","0","TRUE","0","private",
             "scopeSHA="+prov+";algorithmSHA="+POLICY_SHA]]


def ready_score():
    summary=[""]*len(score.HEADER)
    summary[0]=DAY+"|SUMMARY"
    summary[1]=DAY
    summary[4]="SUMMARY"
    summary[5]="27"
    summary[6]="27"
    summary[7]="0"
    summary[27]="READY_FOR_CHATGPT_DAILY_DIGEST"
    summary[30]=SOURCE_SHA
    summary[31]=POLICY_SHA
    return [list(score.HEADER),summary]


class KronosEODOrderTests(unittest.TestCase):
    def test_original_order_differs_from_sorted_hash(self):
        self.assertNotEqual(SCOPE, sorted(SCOPE))
        self.assertNotEqual(SOURCE_SHA, runner.sha_symbols(sorted(SCOPE)))

    def test_private_authority_accepts_actual_477_eod_receipt(self):
        with patch.object(score,"score_read",return_value=ready_score()):
            syms,sha,policy,asof=kronos.private_authority(AuthorityApi(),DAY)
        self.assertEqual(len(syms),477)
        self.assertEqual(syms,sorted(SCOPE))
        self.assertEqual(sha,SOURCE_SHA)
        self.assertEqual(policy,POLICY_SHA)
        self.assertEqual(asof,DAY)

    def test_mutated_eod_scope_sha_fails_closed(self):
        with patch.object(score,"score_read",return_value=ready_score()):
            with self.assertRaisesRegex(Exception,"KRONOS2_SOURCE_SHA_CONFLICT"):
                kronos.private_authority(AuthorityApi(bad_source=True),DAY)

    def test_historical_pre_cutover_scope_identity_is_not_joined(self):
        historical=runner.get_scope(watchlist_file=str(WATCH),asof="2026-11-09")
        self.assertIn("ROKU",historical)
        self.assertNotIn("GNTX",historical)
        self.assertIn("GNTX",SCOPE)
        self.assertNotIn("ROKU",SCOPE)


if __name__=="__main__":
    unittest.main()
