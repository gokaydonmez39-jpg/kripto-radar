"""Old ROKU corporate closure cannot be a live Cove price input (synthetic)."""
import copy
import unittest
from unittest.mock import patch

import cove_private_shadow as priv
import private_sheet_writer as writer
import runner
from pathlib import Path
from test_cove_private_shadow import FakeApi, flight_ok
from test_cove_shadow import ASOF, SYMBOL, baseline_bars

DAY="2026-11-10"
SCOPE=sorted(runner.get_scope(
    watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
    asof=DAY))


def api_fixture(*,kind="corporate"):
    api=FakeApi()
    api.rows["TARAMA_KAYITLARI"][1][0]=DAY
    old=["2026-11-05|ROKU","2026-11-05","ROKU","TEKNIK AL",
         "100","95","110",
         "KAPALI • CORPORATE_ACTION_REVIEW • 1/15 SEANS",
         "2026-11-09","CORPORATE_ACTION_REVIEW","",
         "PRESERVE_NOTIFICATION","PRESERVE_NOTE"]
    if kind=="open":old[7]="AÇIK • 1/15 SEANS";old[8:11]=["","",""]
    elif kind=="wrongdate":old[8]="2026-11-10"
    elif kind=="wrongcode":old[9]="STOP_TOUCHED"
    api.rows["ADAY_GECMISI"].append(old)
    return api


class FormerROKUCoveTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.a=patch.object(priv.kronos_v2,"private_authority",
            return_value=(SCOPE,runner.sha_symbols(runner.get_scope(
                watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
                asof=DAY)),
                          runner.analysis_fingerprint(),DAY))
        self.b=patch.object(priv.flight,"inspect",
            return_value={**flight_ok(),"latest_verified_scan_asof":DAY})
        self.a.start();self.b.start()
        self.addCleanup(self.a.stop);self.addCleanup(self.b.stop)
    def reader(self,syms,day):
        self.calls.append((list(syms),day))
        return {s:baseline_bars() for s in syms}

    def test_historical_roku_corporate_event_is_not_mapped_to_new_issuer(self):
        api=api_fixture()
        before=copy.deepcopy(api.rows)
        bundle=priv.build_private_bundle(api,DAY,self.reader)
        self.assertEqual(len(bundle["episodes"]),1)
        self.assertTrue(all(x["symbol"]!="ROKU" for x in bundle["episodes"]))
        self.assertNotIn("ROKU",bundle["bars_by_symbol"])
        self.assertNotIn("GNTX",bundle["bars_by_symbol"])
        self.assertEqual(api.rows,before)
        self.assertEqual(self.calls,[([SYMBOL],DAY)])

    def test_unclosed_roku_ep_is_never_silently_excluded(self):
        with self.assertRaisesRegex(priv.CovePrivateHold,"UNREVIEWED_PIT_EPISODE"):
            priv.build_private_bundle(api_fixture(kind="open"),DAY,self.reader)
        self.assertEqual(self.calls,[])

    def test_wrong_corporate_action_date_refused(self):
        with self.assertRaisesRegex(priv.CovePrivateHold,"UNREVIEWED_PIT_EPISODE"):
            priv.build_private_bundle(api_fixture(kind="wrongdate"),DAY,self.reader)
        self.assertEqual(self.calls,[])

    def test_wrong_corporate_action_kind_refused(self):
        with self.assertRaisesRegex(priv.CovePrivateHold,"UNREVIEWED_PIT_EPISODE"):
            priv.build_private_bundle(api_fixture(kind="wrongcode"),DAY,self.reader)
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    unittest.main()
