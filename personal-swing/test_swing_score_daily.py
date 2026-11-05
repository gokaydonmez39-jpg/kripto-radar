"""Synthetic-only XRAY 477 swing score V1 regressions, NO IEX API/Sheets."""
import copy
import re
import unittest
from unittest.mock import patch

import exchange_calendars as ec

import private_lifecycle as life
import private_sheet_writer as writer
import swing_score_daily as score

ASOF = "2026-11-04"
SHA = "a" * 64
POLICY = "b" * 64
RUN = "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/41935261378"

def candidate(day, symbol, held):
    return [day + "|" + symbol, day, symbol, "TEKNİK AL ADAYI",
            "100", "90", "120", "AÇIK • %d/15 SEANS" % held,
            "", "", "", "TEST", "SYNTHETIC_ONLY"]

def inputs():
    candidates = [
        list(writer.CANDIDATE_HEADER),
        candidate("2026-11-03", "AAA", 1),
        candidate("2026-11-04", "AAA", 0),
        candidate("2026-11-04", "BBB", 0),
    ]
    scan = [ASOF, "GitHub auto VERIFIED IEX EOD", "477", "477", "477",
            "0", "TRUE", "3", RUN,
            "scopeSHA=" + SHA + ";algorithmSHA=" + POLICY + ";NO_ORDERS"]
    scans = [list(writer.SCAN_HEADER), scan]
    alert = [""] * len(life.ALERT_HEADER)
    alert[0:6] = ["2026-11-04|BBB|2026-11-04|AL_NEW_EPISODE|1",
                  "2026-11-04|BBB", ASOF, "BBB", ASOF, "AL_NEW_EPISODE"]
    alert[17] = "DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT"
    return candidates, scans, [list(life.ALERT_HEADER), alert]

def bars(price_shift=0., count=52):
    days=[str(s.date()) for s in ec.get_calendar("XNAS").sessions_in_range(
        "2026-08-01", ASOF)][-count:]
    return [
        {"timestamp": day + "T05:00:00+00:00",
         "open": 49.+i+price_shift, "high": 49.75+i+price_shift,
         "low": 48.75+i+price_shift, "close": 49.5+i+price_shift,
         "volume": 10000+i*25}
        for i,day in enumerate(days)
    ]

class FakeAPI:
    def __init__(self):
        self.candidates, self.scans, self.alerts=inputs()
        self.scored=[list(score.HEADER)]
        self.writes=0
        self.tabid=678912343
    def check_metadata(self):
        return None
    def request(self,path,*,method="GET",body=None):
        if path.startswith("?fields="):
            return {"properties":{"timeZone":"Europe/Istanbul"},
                    "sheets":[{"properties":{"title":score.TAB,
                                             "sheetId":self.tabid}}]}
        if path.startswith("/values/"):
            rows=copy.deepcopy(self.scored)
            return {"values":[row[:max([i+1 for i,v in enumerate(row)
                                          if v != ""] or [0])] for row in rows]}
        if path==":batchUpdate":
            assert method=="POST" and self.writes==0
            self.writes+=1
            requests=body["requests"]
            assert len(requests)==1 and requests[0]["appendCells"]["sheetId"]==self.tabid
            for row in requests[0]["appendCells"]["rows"]:
                self.scored.append([cell["userEnteredValue"]["stringValue"]
                                    for cell in row["values"]])
            return {"replies":[{}]}
        raise AssertionError("Unexpected request")
    def read(self,name,last_col):
        if name==score.TAB: return copy.deepcopy(self.scored)
        if name=="ADAY_GECMISI":return copy.deepcopy(self.candidates)
        if name=="TARAMA_KAYITLARI":return copy.deepcopy(self.scans)
        if name=="UYARI_OLAYLARI":return copy.deepcopy(self.alerts)
        raise AssertionError(name)

class SwingScoreTests(unittest.TestCase):
    def setUp(self):
        self.patches=[
            patch.object(score.runner,"get_scope",return_value=["AAA","BBB"]),
            patch.object(score.runner,"sha_symbols",return_value=SHA),
            patch.object(score.runner,"analysis_fingerprint",return_value=POLICY)
        ]
        for p in self.patches:p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.api=FakeAPI()

    def read_batch(self,syms,asof):
        self.assertEqual(asof,ASOF)
        self.assertEqual(syms,["AAA","BBB"])
        return {"AAA":bars(), "BBB":bars(1.)}

    def test_all_open_episodes_ranked_with_duplicate_symbol_counted_once(self):
        rows=score.build(*inputs(),ASOF,self.read_batch)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0][4],"SUMMARY")
        self.assertEqual(rows[0][5],"3")
        self.assertEqual(rows[0][6],"3")
        self.assertEqual(rows[0][8],"2")
        self.assertEqual(len({r[2] for r in rows[1:]}),3)
        self.assertEqual([int(r[5]) for r in rows[1:]], [1,2,3])
        aaa=[r for r in rows[1:] if r[3]=="AAA"]
        self.assertEqual(len(aaa),2)
        self.assertEqual(aaa[0][6],aaa[1][6])
        self.assertLessEqual(abs(sum(float(x) for x in aaa[0][7:14])-
                                 float(aaa[0][6])),0.35)
        self.assertTrue(all(0<=float(r[6])<=100 for r in rows[1:]))
        self.assertTrue(all(r[16]=="90.000" and r[17]=="120.000"
                            for r in rows[1:]))
        self.assertTrue(all(re.fullmatch("[0-9a-f]{64}",r[29]) for r in rows))
        self.assertTrue(any("ONCEKI_AL_BASKILANDI" in r[25] for r in rows[1:]))

    def test_missing_symbol_is_hold_not_fabricated(self):
        def missing(syms,asof):
            return {"AAA":bars(),"BBB":[]}
        rows=score.build(*inputs(),ASOF,missing)
        self.assertEqual(rows[0][6],"2")
        self.assertEqual(rows[0][7],"1")
        self.assertEqual(rows[-1][5],"HOLD")
        self.assertEqual(rows[-1][6],"")
        self.assertIn("HOLD_VERI_YETERSIZ",rows[-1][25])

    def test_wrong_provenance_is_refused_before_provider(self):
        c,s,a=inputs()
        s[1][9]=s[1][9].replace(SHA,"c"*64)
        def prohibited(syms,asof):
            raise AssertionError("Provider must not be called")
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_SOURCE_SHA_DRIFT"):
            score.build(c,s,a,ASOF,prohibited)

    def test_broken_final_coverage_fails_closed(self):
        c,s,a=inputs()
        s[1][4]="476"
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_SCAN_NOT_FINAL_477"):
            score.build(c,s,a,ASOF,self.read_batch)

    def test_no_duplicate_daily_write_and_request_preserved(self):
        original=copy.deepcopy(self.api.candidates)
        out=score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(out["status"],"SWING_SCORE_PRIVATE_READBACK_PASS")
        self.assertEqual(self.api.writes,1)
        self.assertEqual(self.api.candidates,original)
        self.api.scored[1][27]=score.REQUESTED
        self.api.scored[1][28]="2026-11-05 09:57 TRT"
        result=score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(result["status"],"SWING_SCORE_IDEMPOTENT_READBACK_PASS")
        self.assertEqual(self.api.writes,1)
        self.assertEqual(self.api.scored[1][27],score.REQUESTED)

    def test_replay_detects_modified_stop_level(self):
        score.synchronize(self.api,ASOF,self.read_batch)
        self.api.scored[2][16]="0.001"
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_EXISTING_DAY_CONTENT_DRIFT"):
            score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(self.api.writes,1)

    def test_missing_episode_bar_fails_closed_or_marks_hold(self):
        def bad(syms,asof):
            x=bars()
            x[-1]["timestamp"]="2026-11-03T05:00:00+00:00"
            return {"AAA":x,"BBB":bars(1.)}
        with self.assertRaises((ValueError,writer.HandoffBlocked)):
            score.build(*inputs(),ASOF,bad)

if __name__=="__main__":
    unittest.main()
