"""Offline security tests for the independently scoped Kronos V2 writer."""
import io
import json
import unittest
from unittest.mock import patch
import kronos_research_transport as t
import kronos_v2 as v
import kronos_shadow as k
import private_sheet_writer as w
import research_epoch_binding as binding

ASOF="2026-11-23"
SCOPE="a"*64
POLICY="b"*64
SID=777881123
PARENT=binding.Parent(890123,"a"*40)


def rows():
    out=[]
    for h in (1,5,12):
        row=[""]*20
        row[0]=f"{ASOF}|SYNA|H{h}"
        row[1:4]=[ASOF,"SYNA",str(h)]
        row[4:7]=["100.000000","101.000000","1.000000"]
        row[7:11]=[k.MODEL_ID,k.MODEL_REV,k.TOKENIZER_REV,k.KRONOS_CODE_REV]
        row[11:17]=[SCOPE,POLICY,ASOF,"c"*64,"d"*64,v.VERSION_V2]
        row[17]="RESEARCH_ONLY"
        row[18]="IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY"
        row[19]=k.canonical_sha(row[:19])
        out.append(row)
    return out


def fixture():
    a=t.KronosV2ResearchApi.__new__(t.KronosV2ResearchApi)
    a._authenticated_production_client=True
    a._research_parent=PARENT
    a._research_scope=(ASOF,frozenset(("SYNA",)),SCOPE,POLICY,ASOF)
    a._post_scope={"scan":1,"candidate":2,"alerts":3,"panel":4,"score":5,"neon":6}
    a.base="https://sheets.googleapis.com/v4/spreadsheets/TEST_NOT_REAL"
    a.token="PRIVATE_SYNTHETIC_TEST_TOKEN"
    return a


def meta(month=True):
    sheets=[{"properties":{"sheetId":1,"title":"PANEL"}}]
    if month:
        sheets.append({"properties":{"sheetId":SID,"title":"KRONOS2_2026_11"}})
    return {"properties":{"timeZone":"Europe/Istanbul"},"sheets":sheets}


def fake_response(value):
    return io.BytesIO(json.dumps(value).encode())


class NarrowKronosWriterTest(unittest.TestCase):
    def test_existing_core_writer_refuses_monthly_research_post(self):
        a=fixture()
        payload={"requests":[w.as_cells(rows(),SID)]}
        with patch.object(w,"urlopen",side_effect=AssertionError("INVALID_GOOGLE")) as http:
            with self.assertRaisesRegex(w.HandoffBlocked,"GOOGLE_SHEETS_POST_SCOPE_INVALID"):
                w.SheetApi.request(a,":batchUpdate",method="POST",body=payload)
            http.assert_not_called()

    def test_separately_scoped_monthly_append_one_post_only(self):
        a=fixture();payload={"requests":[w.as_cells(rows(),SID)]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",return_value=fake_response(meta())) as get,
              patch.object(t,"urlopen",return_value=fake_response({"replies":[{}]})) as post):
            self.assertEqual(a.request(":batchUpdate",method="POST",body=payload),
                             {"replies":[{}]})
            self.assertEqual(get.call_count,1)
            self.assertEqual(post.call_count,1)

    def test_payload_mutations_stop_before_google_post(self):
        import copy
        canonical={"requests":[w.as_cells(rows(),SID)]}
        bad=[]
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["sheetId"]=2;bad.append(x)
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["fields"]="*";bad.append(x)
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["rows"][0]["values"][1]["userEnteredValue"]["stringValue"]="2026-11-19";bad.append(x)
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["rows"][0]["values"][4]["userEnteredValue"]={"formulaValue":"=1+1"};bad.append(x)
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["rows"][0]["values"][19]["userEnteredValue"]["stringValue"]="f"*64;bad.append(x)
        x=copy.deepcopy(canonical);x["requests"][0]["appendCells"]["rows"].pop();bad.append(x)
        bad.append({"requests":[{"deleteSheet":{"sheetId":SID}}]})
        for body in bad:
            with self.subTest(case=len(str(body))):
                a=fixture()
                with (patch.object(a,"_last_mile",return_value=a._research_scope),
                      patch.object(w,"urlopen",return_value=fake_response(meta())),
                      patch.object(t,"urlopen",side_effect=AssertionError("UNAUTHORIZED_POST")) as post):
                    with self.assertRaises(w.HandoffBlocked):
                        a.request(":batchUpdate",method="POST",body=body)
                    post.assert_not_called()

    def test_exact_month_creation_only(self):
        a=fixture();name=v.month_sheet(ASOF);sid=v.choose_sheet_id(name,{1})
        payload={"requests":[
            {"addSheet":{"properties":{"sheetId":sid,"title":name,
                "gridProperties":{"rowCount":2,"columnCount":20,"frozenRowCount":1}}}},
            w.as_cells([list(k.HEADERS)],sid)]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",return_value=fake_response(meta(False))),
              patch.object(t,"urlopen",return_value=fake_response({"replies":[{},{}]})) as post):
            a.request(":batchUpdate",method="POST",body=payload)
            self.assertEqual(post.call_count,1)
        bad=json.loads(json.dumps(payload))
        bad["requests"][0]["addSheet"]["properties"]["gridProperties"]["frozenRowCount"]=2
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",return_value=fake_response(meta(False))),
              patch.object(t,"urlopen",side_effect=AssertionError("POST_ESCAPE")) as post):
            with self.assertRaises(w.HandoffBlocked):
                a.request(":batchUpdate",method="POST",body=bad)
            post.assert_not_called()

    def test_connection_reset_is_redacted_and_never_reposted(self):
        a=fixture();payload={"requests":[w.as_cells(rows(),SID)]}
        with (patch.object(a,"_last_mile",return_value=a._research_scope),
              patch.object(w,"urlopen",return_value=fake_response(meta())),
              patch.object(t,"urlopen",side_effect=ConnectionResetError("PRIVATE_TOKEN")) as post):
            with self.assertRaisesRegex(w.HandoffBlocked,
                                        "KRONOS2_RESEARCH_POST_UNCERTAIN") as outcome:
                a.request(":batchUpdate",method="POST",body=payload)
            self.assertNotIn("PRIVATE_TOKEN",str(outcome.exception))
            self.assertEqual(post.call_count,1)

    def test_wrong_event_and_incomplete_github_parent_hold(self):
        a=fixture()
        with (patch.object(binding,"scheduled_parent",return_value=PARENT),
              patch.object(k,"eligible_shadow_asof",return_value=ASOF),
              patch.dict(t.os.environ,{
                  "GITHUB_REF":"refs/heads/main",
                  "GITHUB_WORKFLOW_REF":t.WORKFLOW_REF,
                  "GITHUB_RUN_ATTEMPT":"1",
                  "GITHUB_EVENT_NAME":"push"})):
            with self.assertRaises(w.HandoffBlocked):
                a.arm(ASOF,["SYNA"]*477,SCOPE,POLICY,ASOF)
        with (patch.object(binding,"scheduled_parent",return_value=PARENT),
              patch.object(k,"eligible_shadow_asof",return_value=ASOF),
              patch.object(v,"private_authority",
                          return_value=(["SYNA"],SCOPE,POLICY,ASOF)),
              patch("preopen_a34.verify_github_natural_eod_source",
                    return_value="GITHUB_NATURAL_EOD_SOURCE_VERIFIED"),
              patch("preopen_a34.verify_github_eod_six_job_chain",
                    return_value="NOT_PROVEN")):
            with self.assertRaisesRegex(w.HandoffBlocked,t.ERR):
                a._last_mile()


if __name__=="__main__":
    unittest.main()
