"""Offline, no-secrets V2 close-only and month-partition readback tests."""
import math
from datetime import date,timedelta
import sys
import types
import unittest
from unittest.mock import patch

import kronos_shadow as k
import kronos_v2 as v

ASOF="2026-11-09"
SCOPE="a"*64
POLICY="b"*64
SYMS=[f"T{i:03}" for i in range(477)]


def candles():
    days=[(date.fromisoformat(ASOF)-timedelta(days=i)).isoformat()
          for i in range(51,-1,-1)]
    return [dict(timestamp=d,open=100.,high=103.,low=99.,
                 close=101.,volume=10000.) for d in days]


class Frame:
    def __init__(self,bad_geometry=False,bad_close=False):
        self.rows=[dict(open=100.,high=(99. if bad_geometry else 103.),
                        low=98.,close=(float("nan") if bad_close else 101.),
                        volume=10000.) for _ in range(12)]
    def __len__(self):
        return len(self.rows)
    def iterrows(self):
        return enumerate(self.rows)


class FakeApi:
    def __init__(self):
        self.rows=[]
        self.created=False
        self.writes=0
        self.raise_after=None
        self.month=v.month_sheet(ASOF)
        self.sid=123456789
    def request(self,path,*,method="GET",body=None):
        if method=="GET" and path.startswith("?"):
            tabs=[dict(sheetId=100,title="PANEL",
                       gridProperties=dict(rowCount=10,columnCount=10))]
            if self.created:
                tabs.append(dict(sheetId=self.sid,title=self.month,
                                 gridProperties=dict(rowCount=len(self.rows)+1,columnCount=20)))
            return dict(properties=dict(timeZone="Europe/Istanbul"),
                        sheets=[dict(properties=x) for x in tabs])
        if method=="GET" and path.startswith("/values/"):
            return dict(values=[list(k.HEADERS)]+[list(x) for x in self.rows])
        if method=="POST" and path==":batchUpdate":
            self.writes+=1
            if self.raise_after is not None and self.writes==self.raise_after:
                raise k.ShadowHold("FAKE_POST_INTERRUPTED")
            for req in body["requests"]:
                if "addSheet" in req:
                    self.created=True
                    self.sid=req["addSheet"]["properties"]["sheetId"]
                if "appendCells" in req:
                    parsed=[[x["userEnteredValue"]["stringValue"] for x in row["values"]]
                            for row in req["appendCells"]["rows"]]
                    if parsed==[list(k.HEADERS)]:
                        continue
                    self.rows.extend(parsed)
            return dict()
        raise AssertionError("Unexpected private API path")


def as_cells(rows, sheet_id):
    return {"appendCells":{
        "sheetId":sheet_id,"rows":[{"values":[
            {"userEnteredValue":{"stringValue":str(x)}} for x in row]}
            for row in rows],"fields":"userEnteredValue"}}


class V2Tests(unittest.TestCase):
    def test_close_only_geometry_not_falsely_repaired(self):
        closes,state,policy=v.forecast_classification(Frame(bad_geometry=True))
        self.assertEqual(state,v.MODEL_STATUS_CLOSE)
        self.assertEqual(len(closes),12)
        self.assertIn("GEOMETRY_INVALID",policy)
        self.assertEqual(closes,[101.]*12)
        normal=v.forecast_classification(Frame())
        self.assertEqual(normal[1],v.MODEL_STATUS_FULL)

    def test_nonfinite_closing_kept_out(self):
        closes,status,_=v.forecast_classification(Frame(bad_geometry=True,
                                                       bad_close=True))
        self.assertIsNone(closes)
        self.assertTrue(status.startswith("HOLD_QC_"))

    def test_month_rows_and_immutable_hash(self):
        rows=v.build_v2_rows("AAPL",ASOF,SCOPE,POLICY,ASOF,
                             candles(),[101.]*12,v.MODEL_STATUS_CLOSE,
                             "RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID")
        self.assertEqual(len(rows),3)
        self.assertEqual([x[3] for x in rows],["1","5","12"])
        self.assertEqual({x[17] for x in rows},{"RESEARCH_CLOSE_ONLY"})
        self.assertTrue(all(x[19]==k.canonical_sha(x[:19]) for x in rows))
        self.assertEqual(v.month_sheet(ASOF),"KRONOS2_2026_11")
        with self.assertRaisesRegex(k.ShadowHold,"BAD_ASOF"):
            v.month_sheet("2026-11-99")

    def test_partition_rejects_tampered_row_and_history(self):
        api=FakeApi()
        api.created=True
        raw=v.build_v2_rows("AAPL",ASOF,SCOPE,POLICY,ASOF,
                             candles(),[101.]*12,v.MODEL_STATUS_FULL,
                             "IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY")
        api.rows=raw
        self.assertEqual(len(v.read_partition(api,api.month)),3)
        api.rows[0][5]="9999"
        with self.assertRaisesRegex(k.ShadowHold,"TAMPERED"):
            v.read_partition(api,api.month)

    def test_exact_477_month_partition_readback_and_idempotency(self):
        api=FakeApi()
        fake_writer=types.ModuleType("private_sheet_writer")
        fake_writer.as_cells=as_cells
        forecast=[]
        for sym in SYMS:
            forecast+=v.build_v2_rows(sym,ASOF,SCOPE,POLICY,ASOF,
                         candles(),[100.]*12,v.MODEL_STATUS_CLOSE,
                         "RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID")
        def no_fetch(*args):
            raise AssertionError("No model/provider call should occur")
        with patch.dict(sys.modules,{"private_sheet_writer":fake_writer}), \
             patch.object(v,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,ASOF)), \
             patch.object(v,"make_predictions",
                          return_value=(forecast,{"RESEARCH_CLOSE_ONLY":477})) as mk:
            first=v.synchronize(api,ASOF,no_fetch)
            self.assertEqual(first["status"],
                             "KRONOS2_PRIVATE_READBACK_CLOSE_ONLY")
            self.assertEqual(first["scope"],477)
            self.assertEqual(first["rows_written"],1431)
            self.assertEqual(first["close_only"],477)
            self.assertFalse(first["model_quality_full_pass"])
            self.assertEqual(len(api.rows),1431)
            self.assertEqual(len({r[0] for r in api.rows}),1431)
            self.assertEqual(api.writes,9)
            second=v.synchronize(api,ASOF,no_fetch)
            self.assertEqual(second["status"],"KRONOS2_IDEMPOTENT_READBACK")
            self.assertEqual(second["rows_written"],0)
            self.assertEqual(api.writes,9)
            self.assertEqual(mk.call_count,1)

    def test_interrupted_chunk_resumes_without_history_replay(self):
        api=FakeApi()
        api.raise_after=3
        fake_writer=types.ModuleType("private_sheet_writer")
        fake_writer.as_cells=as_cells
        forecast=[]
        for s in SYMS:
            forecast+=v.build_v2_rows(s,ASOF,SCOPE,POLICY,ASOF,
                          candles(),[102.]*12,v.MODEL_STATUS_FULL,
                          "IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY")
        with patch.dict(sys.modules,{"private_sheet_writer":fake_writer}), \
             patch.object(v,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,ASOF)), \
             patch.object(v,"make_predictions",
                          return_value=(forecast,{"RESEARCH_ONLY":477})):
            with self.assertRaisesRegex(k.ShadowHold,"FAKE_POST_INTERRUPTED"):
                v.synchronize(api,ASOF,lambda *_:None)
            self.assertEqual(len(api.rows),180)
            api.raise_after=None
            second=v.synchronize(api,ASOF,lambda *_:None)
            self.assertEqual(second["rows_written"],1251)
            self.assertEqual(len(api.rows),1431)
            self.assertEqual(len({row[0] for row in api.rows}),1431)

    def test_drift_holds_even_after_valid_readback(self):
        api=FakeApi()
        api.created=True
        api.rows=v.build_v2_rows("T000",ASOF,SCOPE,POLICY,ASOF,
                  candles(),[101.]*12,v.MODEL_STATUS_FULL,
                  "IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY")
        newer=[]
        for symbol in SYMS:
            newer.extend(v.build_v2_rows(symbol,ASOF,SCOPE,POLICY,ASOF,
                        candles(),[102.]*12,v.MODEL_STATUS_FULL,
                        "IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY"))
        with patch.object(v,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,ASOF)), \
             patch.object(v,"make_predictions",
                          return_value=(newer,{"RESEARCH_ONLY":477})):
            with self.assertRaisesRegex(k.ShadowHold,
                                        "RESTART_NONDETERMINISTIC"):
                v.synchronize(api,ASOF,lambda *_:None)
        self.assertEqual(len(api.rows),3)
        self.assertEqual(api.writes,0)

    def test_older_incomplete_asof_blocks_new_month_append(self):
        api=FakeApi()
        api.created=True
        api.rows=v.build_v2_rows("T000","2026-11-06",SCOPE,POLICY,
                  "2026-11-06",candles(),[101.]*12,
                  v.MODEL_STATUS_FULL,
                  "IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY")
        with patch.object(v,"private_authority",
                          return_value=(SYMS,SCOPE,POLICY,ASOF)), \
             patch.object(v,"make_predictions",
                          side_effect=AssertionError("No model call with partial history")):
            with self.assertRaisesRegex(k.ShadowHold,
                                        "PRIOR_ASOF_PARTIAL_HOLD"):
                v.synchronize(api,ASOF,lambda *_:None)
        self.assertEqual(api.writes,0)

    def test_capacity_explicit_fail_closed(self):
        api=FakeApi()
        api.created=True
        with patch.object(v,"MAX_GRID_CELLS",100):
            with self.assertRaisesRegex(k.ShadowHold,"GLOBAL_CAPACITY"):
                v.metadata_and_sheet(api,ASOF)


if __name__=="__main__":
    unittest.main()
