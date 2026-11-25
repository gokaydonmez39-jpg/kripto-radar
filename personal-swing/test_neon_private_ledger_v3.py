"""No network, no real sheet writes, no trading; all 477 keys are exact PIT master."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import runner
import neon_shadow_v3 as neon
import neon_private_ledger_v3 as ledger
import private_sheet_writer as writer

ASOF="2026-11-19"
RUN="https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/44671232964"
POLICY="0c137ecbdaf0eb68dbab3a642cfd501e4af61641b52367607fe616713af32523"
MASTER=runner.get_scope(watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),asof=ASOF)
SCOPE=neon.scope_digest(MASTER)


def fixture():
    rows=[]
    for i,s in enumerate(MASTER,1):
        rows.append({"symbol":s,"rank":i,"score":"80.00",
                     "factors":{k:80.0 for k in neon.WEIGHTS},
                     "bar_asof":ASOF,
                     "last_valid_bar_time":ASOF+"T21:00:00+00:00",
                     "source_decision":"ELE","signal_status":"NO_NEW_AL",
                     "decision_corridor":"YAKINDAN_IZLE",
                     "liquidity":"PASS_IEX_SINGLE_VENUE",
                     "spread":"UNKNOWN","gap":"UNKNOWN","orders_sent":0})
    return {"schema":"XRAY_NASDAQ_NEON_V3_EPHEMERAL_SHADOW_V1",
            "asof_et":ASOF,"source_event":"schedule",
            "scope_sha256":SCOPE,"policy_sha256":POLICY,
            "notification_sent":False,"chatgpt_card_written":False,
            "orders_sent":0,
            "counts":{"master":477,"scored":477,"na":0},"rows":rows}


def scans():
    row=[""]*len(writer.SCAN_HEADER)
    row[0]=ASOF
    row[1]="GitHub schedule VERIFIED IEX EOD"
    for index,value in {2:"477",3:"477",4:"477",5:"0",6:"TRUE",7:"1",8:RUN}.items():
        row[index]=value
    row[9]="scopeSHA="+SCOPE+";algorithmSHA="+POLICY+";source_event=schedule;NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK"
    return [list(writer.SCAN_HEADER),row]


class NeonNaturalCurrentAsOfGate(unittest.TestCase):
    """Production NEON may not append a historic scanned ASOF as a new day."""

    def live_env(self):
        return {
            "GITHUB_EVENT_NAME":"schedule",
            "GITHUB_RUN_ID":"999001",
            "GITHUB_RUN_ATTEMPT":"1",
            "GITHUB_REPOSITORY":writer.EXPECTED_EOD_REPOSITORY,
            "GITHUB_REF":"refs/heads/main",
            "GITHUB_SHA":"a"*40,
            "GITHUB_WORKFLOW_REF":writer.EXPECTED_EOD_WORKFLOW_REF,
            "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"synthetic-test-token",
        }

    def test_old_snapshot_must_hold_before_google_even_when_natural(self):
        src={
            "asof_et":ASOF, "scope_sha256":SCOPE,
            "valid_data_coverage_complete":True,
            "new_signal_publishable":True,
            "analysis_fingerprint_sha256":runner.analysis_fingerprint(),
        }
        for current in ("2026-11-23",None,"2026-11-20"):
            with self.subTest(current=current):
                with tempfile.TemporaryDirectory() as folder:
                    path=Path(folder)/"old.json"
                    path.write_text(json.dumps(src),encoding="utf-8")
                    with patch.dict(os.environ,self.live_env(),clear=True):
                        with patch("daily_job.current_completed_session",
                                   return_value=current):
                            with patch.object(ledger.original,"SheetApi",
                                  side_effect=AssertionError("OLD_NEON_GOOGLE_API_STARTED")
                            ) as api, contextlib.redirect_stdout(io.StringIO()) as out:
                                rc=ledger.main(["--snapshot",str(path),
                                                "--shadow",str(path)])
                    result=json.loads(out.getvalue())
                    self.assertEqual(rc,3)
                    self.assertEqual(result["status"],"NEON_PRIVATE_LEDGER_HOLD")
                    self.assertEqual(
                        result["reason_code"],"NEON_ASOF_NOT_CURRENT_NATURAL_SESSION")
                    api.assert_not_called()

    def test_weekend_late_same_asof_cannot_backfill_neon(self):
        # Even when Friday remains the most recent official session on
        # Saturday, a run after its XNAS close+45m+10h is stale.
        friday="2026-11-20"
        master=runner.get_scope(
            watchlist_file=str(Path(__file__).with_name("nasdaq_watchlist_477.json")),
            asof=friday)
        src={
            "asof_et":friday,
            "scope_sha256":neon.scope_digest(master),
            "valid_data_coverage_complete":True,
            "new_signal_publishable":True,
            "analysis_fingerprint_sha256":runner.analysis_fingerprint(),
        }
        late=datetime(2026,11,21,12,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"friday.json"
            path.write_text(json.dumps(src),encoding="utf-8")
            with patch.dict(os.environ,self.live_env(),clear=True):
                with patch("daily_job.current_completed_session",
                           return_value=friday):
                    with patch.object(
                        ledger,"datetime",
                        SimpleNamespace(now=lambda *_:late)):
                        with patch.object(
                            ledger.original,"SheetApi",
                            side_effect=AssertionError("STALE_NEON_GOOGLE_STARTED")
                        ) as api,contextlib.redirect_stdout(io.StringIO()) as out:
                            rc=ledger.main(["--snapshot",str(path),
                                            "--shadow",str(path)])
            result=json.loads(out.getvalue())
            self.assertEqual(rc,3)
            self.assertEqual(result["reason_code"],
                             "NEON_ASOF_NOT_CURRENT_NATURAL_SESSION")
            api.assert_not_called()


    def test_current_natural_asof_passes_fake_477_readback_without_signal(self):
        # Positive control: the safety gate must not kill the next real EOD.
        src={
            "asof_et":ASOF,"scope_sha256":SCOPE,
            "valid_data_coverage_complete":True,
            "new_signal_publishable":True,
            "analysis_fingerprint_sha256":runner.analysis_fingerprint(),
        }
        api=FakeApi()
        api.scans[1][8]=(
            "https://github.com/gokaydonmez39-jpg/kripto-radar/"
            "actions/runs/999001")
        current_policy=runner.analysis_fingerprint()
        api.scans[1][9]=api.scans[1][9].replace(POLICY,current_policy)
        shadow=fixture()
        shadow["policy_sha256"]=current_policy
        observation=datetime(2026,11,19,23,16,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            snapshot_path=Path(folder)/"snapshot.json"
            shadow_path=Path(folder)/"shadow.json"
            snapshot_path.write_text(json.dumps(src),encoding="utf-8")
            shadow_path.write_text(json.dumps(shadow),encoding="utf-8")
            with patch.dict(os.environ,self.live_env(),clear=True):
                with patch("daily_job.current_completed_session",
                           return_value=ASOF):
                    with patch.object(
                        ledger,"datetime",
                        SimpleNamespace(now=lambda *_:observation,
                                        fromisoformat=datetime.fromisoformat)):
                        with patch.object(
                            ledger.original,"SheetApi",return_value=api):
                            with contextlib.redirect_stdout(io.StringIO()) as output:
                                rc=ledger.main([
                                    "--snapshot",str(snapshot_path),
                                    "--shadow",str(shadow_path)])
        result=json.loads(output.getvalue())
        self.assertEqual(rc,0,result)
        self.assertEqual(result["status"],"NEON_PRIVATE_477_NEW_SOURCE_VERIFIED")
        self.assertEqual((result["scored"],result["na"]),(477,0))
        self.assertEqual((api.posts,len(api.tab)),(1,478))
        self.assertFalse(result["notification_sent"])
        self.assertEqual(result["orders_sent"],0)


class NeonSourceIdentityIsolation(unittest.TestCase):
    def test_cross_workflow_schedule_never_reads_private_source(self):
        import private_sheet_writer as writer
        env={
            'GITHUB_EVENT_NAME':'schedule',
            'GITHUB_RUN_ID':'999001',
            'GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':writer.EXPECTED_EOD_REPOSITORY,
            'GITHUB_REF':'refs/heads/main',
            'GITHUB_SHA':'a'*40,
            'GITHUB_WORKFLOW_REF':
                writer.EXPECTED_EOD_REPOSITORY+'/'
                '.github/workflows/unrelated-schedule.yml@refs/heads/main',
            'XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON':'fake-offline-token',
        }
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'synthetic.json'
            src.write_text('{}')
            with patch.dict(os.environ,env,clear=True):
                with patch.object(ledger.runner,'get_scope',
                    side_effect=AssertionError('SCOPE_CONSUMED_BEFORE_IDENTITY')
                ) as provider,contextlib.redirect_stdout(io.StringIO()) as output:
                    rc=ledger.main(['--snapshot',str(src),
                                    '--shadow',str(src)])
        result=json.loads(output.getvalue())
        self.assertEqual(rc,3)
        self.assertEqual(result['status'],'NEON_PRIVATE_LEDGER_HOLD')
        provider.assert_not_called()


class FakeApi:
    def __init__(self):
        self.tab=[list(ledger.HEADER)]
        self.scans=scans()
        self.posts=0
    def check_metadata(self):
        return None
    def read(self, name, col):
        self.assert_known(name, col)
        if name==ledger.TAB and len(self.tab)>writer.MAX_ROWS:
            raise writer.HandoffBlocked("SHEET_READ_CAPACITY_REACHED")
        return copy.deepcopy(self.tab if name==ledger.TAB else self.scans)
    def assert_known(self,name,col):
        if name==ledger.TAB:
            if col!="W":raise AssertionError("wrong column")
        elif name=="TARAMA_KAYITLARI":
            if col!="J":raise AssertionError("wrong column")
        else:raise AssertionError("wrong tab")
    def request(self,path,*,method="GET",body=None):
        if path.startswith("/values/") and method=="GET":
            from urllib.parse import unquote
            import re
            encoded=path.partition("?valueRenderOption=FORMATTED_VALUE")[0]
            name=unquote(encoded.removeprefix("/values/"))
            match=re.fullmatch(r"'NEON_477_GUNLUK'!A([1-9][0-9]*):W([1-9][0-9]*)",name)
            if match is None:raise AssertionError("UNAPPROVED_NEON_RANGE")
            lo,hi=map(int,match.groups())
            if hi<lo or hi-lo>10000:raise AssertionError("NEON_PAGE_UNBOUNDED")
            return {"values":copy.deepcopy(self.tab[lo-1:hi])}
        if path.startswith("?fields="):
            return {"properties":{"timeZone":"Europe/Istanbul"},
                    "sheets":[{"properties":{
                        "title":ledger.TAB,"sheetId":903477,
                        "gridProperties":{"rowCount":max(1000,len(self.tab))}
                    }}]}
        if path==":batchUpdate" and method=="POST":
            self.posts+=1
            req=body["requests"]
            if len(req)!=1 or req[0]["appendCells"]["sheetId"]!=903477:
                raise AssertionError("unsafe append")
            for row in req[0]["appendCells"]["rows"]:
                self.tab.append([v["userEnteredValue"]["stringValue"] for v in row["values"]])
            return {"replies":[{}]}
        raise AssertionError("unexpected API call")


class PrivateNeonLedgerTests(unittest.TestCase):
    def setUp(self):
        self.snap=fixture()
        self.api=FakeApi()

    def calculate(self,payload=None,old=None,scans_data=None,asof=ASOF,url=RUN):
        return ledger.plan(asof,url,MASTER,POLICY,scans_data or scans(),
                           old if old is not None else [list(ledger.HEADER)],
                           self.snap if payload is None else payload)

    def test_477_full_source_and_no_al_notification(self):
        result=self.calculate()
        self.assertEqual(result["status"],"NEON_PRIVATE_477_NEW_SOURCE_VERIFIED")
        self.assertEqual(result["scored"],477)
        self.assertEqual(result["na"],0)
        self.assertEqual(len({r[2] for r in result["rows"]}),477)
        self.assertEqual(result["rows"][0][4],"80.00")
        self.assertTrue(all(len(r)==23 and r[14]=="RESEARCH_SCORE_UNVALIDATED"
                            and r[15][:10]==ASOF and r[17]=="UNKNOWN" and
                            r[18]=="UNKNOWN" for r in result["rows"]))

    def test_no_shadow_generates_477_na_not_zero(self):
        result=ledger.plan(ASOF,RUN,MASTER,POLICY,scans(),
                           [list(ledger.HEADER)],None)
        self.assertEqual((result["scored"],result["na"]),(0,477))
        self.assertTrue(all(r[4]=="N/A" and r[12]=="HOLD" and
                            r[14]=="HOLD_SHADOW_RESULT_MISSING" for r in result["rows"]))

    def test_synchronize_one_atomic_write_and_readback(self):
        r=ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(r["scored"],477)
        self.assertEqual(len(self.api.tab),478)
        self.assertEqual(self.api.posts,1)
        again=ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(again["status"],"NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY")
        self.assertEqual(self.api.posts,1)

    def test_neon_full_history_over_20000_rows_is_read_by_bounded_pages(self):
        """42 x 477 rows exceed the shared scan/outbox safety cap.
        No premature Sheet POST, no silently truncated historical proof.
        """
        api=FakeApi()
        api.tab=[list(ledger.HEADER)]+[["historical"]*23 for _ in range(42*477)]
        observed=[]
        def inspect(asof,url,master,policy,scans,old,shadow):
            observed.append(len(old))
            self.assertEqual(len(old),42*477+1)
            self.assertEqual(old[0],list(ledger.HEADER))
            self.assertEqual(old[-1],["historical"]*23)
            return {"status":"NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY",
                    "asof":asof,"rows":[],"scored":0,"na":477}
        with patch.object(ledger,"plan",side_effect=inspect):
            result=ledger.synchronize(api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(result["status"],"NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY")
        self.assertEqual(observed,[42*477+1])
        self.assertEqual(api.posts,0)

    def test_neon_read_malformed_provider_page_fails_closed_before_post(self):
        api=FakeApi()
        original=api.request
        def malformed(path,*,method="GET",body=None):
            if path.startswith("/values/"):
                return {"values":"TRUNCATED_NOT_A_LIST"}
            return original(path,method=method,body=body)
        api.request=malformed
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"NEON_ARCHIVE_PAGE_INVALID"):
            ledger.synchronize(api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(api.posts,0)

    def test_neon_archive_capacity_limit_is_checked_before_atomic_post(self):
        api=FakeApi()
        with patch.object(ledger,"MAX_NEON_ARCHIVE_ROWS",477):
            with self.assertRaisesRegex(
                    ledger.NeonLedgerHold,"NEON_ARCHIVE_CAPACITY_HOLD"):
                ledger.synchronize(api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(api.posts,0)

    def test_row_source_run_matches_authenticated_sheet(self):
        r=self.calculate()
        self.assertTrue(all(v[19]==RUN and v[20]==SCOPE and
                            v[21]==POLICY for v in r["rows"]))

    def test_snapshot_reject_wrong_run_url(self):
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SCAN_NOT_FINAL_477_OR_WRONG_RUN"):
            self.calculate(url=RUN+"2")

    def test_snapshot_reject_forged_repository(self):
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"INVALID_NASDAQ_RUN_URL"):
            self.calculate(url="https://github.com/attacker/repo/actions/runs/100")

    def test_neon_rejects_undated_last_row_before_private_post(self):
        """A valid old scan must not hide a corrupted final source row."""
        for bad_day in ('', None):
            with self.subTest(bad_day=bad_day):
                api=FakeApi()
                rogue=copy.deepcopy(api.scans[-1])
                rogue[0]=bad_day
                api.scans.append(rogue)
                # Previously this invalid row was silently filtered and
                # a full 477-row append could be committed.
                with self.assertRaisesRegex(
                        ledger.NeonLedgerHold,'SCAN_ROW_ASOF_INVALID'):
                    ledger.synchronize(api,ASOF,RUN,MASTER,POLICY,self.snap)
                self.assertEqual(api.posts,0)

    def test_neon_rejects_undated_middle_source_record(self):
        api=FakeApi()
        rogue=copy.deepcopy(api.scans[-1])
        rogue[0]=''
        api.scans.insert(1,rogue)
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,'SCAN_ROW_ASOF_INVALID'):
            ledger.synchronize(api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(api.posts,0)

    def test_snapshot_reject_stale_scan(self):
        old=scans();old[1][0]="2026-11-18"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"LATEST_SCAN_ASOF_MISMATCH"):
            self.calculate(scans_data=old)

    def test_scan_rejects_out_of_order_future_epoch_before_valid_tail(self):
        # A trailing valid ASOF cannot hide a newer epoch inserted earlier.
        forged=scans()
        future=copy.deepcopy(forged[1])
        future[0]="2026-11-20"
        forged.insert(1,future)
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"SCAN_DATE_ORDER_OR_DUPLICATE"):
            self.calculate(scans_data=forged)

    def test_archive_rejects_reverse_complete_day_blocks(self):
        # Each block has 477 rows: uniqueness alone is insufficient.
        today=self.calculate()["rows"]
        old=copy.deepcopy(today)
        for row in old:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
        data=[list(ledger.HEADER)]+today+old
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_ASOF_ORDER_OR_NONCONTIGUOUS"):
            self.calculate(old=data)

    def test_archive_rejects_interleaved_complete_day_blocks(self):
        today=self.calculate()["rows"]
        old=copy.deepcopy(today)
        for row in old:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
        data=[list(ledger.HEADER)]+old[:200]+today+old[200:]
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_ASOF_ORDER_OR_NONCONTIGUOUS"):
            self.calculate(old=data)

    def test_scan_requires_single_exact_natural_source_event(self):
        for origin in (
            "source_event=scheduled",
            "source_event=schedule_recovered",
            "source_event=schedule;source_event=workflow_dispatch",
            "source_event=workflow_dispatch;source_event=schedule",
        ):
            with self.subTest(origin=origin):
                forged=scans()
                forged[1][9]=forged[1][9].replace("source_event=schedule",origin)
                with self.assertRaisesRegex(
                    ledger.NeonLedgerHold,"SCAN_POLICY_OR_EVENT_PROOF_DRIFT"
                ):
                    self.calculate(scans_data=forged)

    def test_scan_requires_exact_natural_source_label(self):
        forged=scans()
        forged[1][1]="GitHub workflow_dispatch VERIFIED IEX EOD"
        with self.assertRaisesRegex(
            ledger.NeonLedgerHold,"SCAN_POLICY_OR_EVENT_PROOF_DRIFT"
        ):
            self.calculate(scans_data=forged)

    def test_shadow_malformed_missing_symbol(self):
        p=copy.deepcopy(self.snap);p["rows"]=p["rows"][:-1]
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_NOT_477_FULLY_SCORED"):
            self.calculate(payload=p)

    def test_shadow_duplicate_symbol(self):
        p=copy.deepcopy(self.snap);p["rows"][1]["symbol"]=p["rows"][0]["symbol"]
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_DUPLICATE_OR_BAR_ASOF"):
            self.calculate(payload=p)

    def test_shadow_score_must_equal_factors(self):
        p=copy.deepcopy(self.snap);p["rows"][0]["score"]="99.00"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_SCORE_MATH_DRIFT"):
            self.calculate(payload=p)

    def test_al_does_not_gain_delivery_authority(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["source_decision"]="AL"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"AL_CANNOT_GAIN_NEON_DELIVERY_AUTHORITY"):
            self.calculate(payload=p)

    def test_na_cannot_turn_into_number_on_retry(self):
        existing=ledger.plan(ASOF,RUN,MASTER,POLICY,scans(),
                             [list(ledger.HEADER)],None)["rows"]
        p=self.calculate(old=[list(ledger.HEADER)]+existing)
        self.assertEqual((p["rows"],p["scored"],p["na"]),([],0,477))

    def test_same_asof_changed_policy_rejected(self):
        existing=self.calculate()["rows"]
        for row in existing:
            row[21]="f"*64
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SAME_ASOF_DIFFERENT_RUN_OR_POLICY"):
            self.calculate(old=[list(ledger.HEADER)]+existing)

    def test_partial_prior_asof_rejected(self):
        earlier=self.calculate()["rows"][:-1]
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"LEDGER_PARTIAL_ASOF"):
            self.calculate(old=[list(ledger.HEADER)]+earlier)

    def test_corrupt_archived_score_factor_math_is_hold(self):
        # Immutable old 477 rows can silently distort the NEXT score delta.
        rows=copy.deepcopy(self.calculate()["rows"])
        rows[0][4]="99.00"
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_SCORE_FACTOR_DRIFT"):
            self.calculate(old=[list(ledger.HEADER)]+rows)

    def test_corrupt_archived_rank_permutation_is_hold(self):
        rows=copy.deepcopy(self.calculate()["rows"])
        rows[1][3]=rows[0][3]
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_RANK_IDENTITY_DRIFT"):
            self.calculate(old=[list(ledger.HEADER)]+rows)

    def test_corrupt_archived_score_rank_is_hold(self):
        rows=copy.deepcopy(self.calculate()["rows"])
        # Keep factor math consistent, but make rank 2 strictly beat rank 1.
        rows[1][4]="90.00"
        for i in range(7,12):
            rows[1][i]="90.00"
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_RANK_SCORE_ORDER_DRIFT"):
            self.calculate(old=[list(ledger.HEADER)]+rows)

    def test_archived_na_and_numeric_mixed_day_is_hold(self):
        scored=copy.deepcopy(self.calculate()["rows"])
        missing=ledger.plan(ASOF,RUN,MASTER,POLICY,scans(),
                 [list(ledger.HEADER)],None)["rows"][0]
        scored[0]=missing
        with self.assertRaisesRegex(
                ledger.NeonLedgerHold,"LEDGER_MIXED_SCORE_STATUS"):
            self.calculate(old=[list(ledger.HEADER)]+scored)

    def test_duplicate_prior_identity_rejected(self):
        earlier=self.calculate()["rows"]
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"LEDGER_IDENTITY_OR_DUPLICATE"):
            self.calculate(old=[list(ledger.HEADER)]+earlier+[earlier[0]])

    def test_missing_previous_score_delta_na(self):
        r=self.calculate()
        self.assertTrue(all(row[5]=="N/A" and row[6]=="N/A" for row in r["rows"]))

    def test_delta_only_on_previously_valid_score(self):
        old=self.calculate()["rows"]
        older=copy.deepcopy(old)
        for row in older:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
            row[4]="70.00"
            for j in range(7,12):
                row[j]="70.00"
        p=self.calculate(old=[list(ledger.HEADER)]+older)
        self.assertEqual(p["rows"][0][5],"2026-11-18")
        self.assertEqual(p["rows"][0][6],"10.00")

    def test_prior_pit_changed_member_is_not_rejoined(self):
        old=copy.deepcopy(self.calculate()["rows"])
        for row in old:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
            row[4]="70.00"
            for j in range(7,12):
                row[j]="70.00"
            row[20]="a"*64
        old[0][2]="OLDPIT"
        old[0][0]="2026-11-18|OLDPIT"
        rows=self.calculate(old=[list(ledger.HEADER)]+old)["rows"]
        self.assertEqual(rows[0][5],"2026-11-18")
        self.assertEqual(rows[0][6],"N/A")
        self.assertEqual(rows[1][6],"10.00")

    def two_valid_epochs(self):
        older=copy.deepcopy(self.calculate()["rows"])
        for row in older:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
            row[4]="70.00"
            for j in range(7,12):
                row[j]="70.00"
        first=[list(ledger.HEADER)]+older
        return first+self.calculate(old=first)["rows"]

    def test_stored_two_epoch_deltas_exact_and_idempotent(self):
        self.api.tab=self.two_valid_epochs()
        result=ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)
        self.assertEqual(result["status"],"NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY")
        self.assertEqual(self.api.posts,0)
        self.assertEqual(len(self.api.tab),955)

    def test_mutated_historical_delta_or_prior_day_is_hold_before_post(self):
        for index,column,value,reason in (
            (1,5,"2026-11-17","LEDGER_PRIOR_ASOF_DRIFT"),
            (1,6,"0.00","LEDGER_DELTA_MISSING_BASELINE"),
            (478,5,"2026-11-17","LEDGER_PRIOR_ASOF_DRIFT"),
            (478,6,"10.01","LEDGER_DELTA_MATH_DRIFT"),
            (478,6,"N/A","LEDGER_DELTA_MATH_DRIFT"),
        ):
            with self.subTest(index=index,column=column,value=value):
                self.api.tab=self.two_valid_epochs()
                self.api.tab[index][column]=value
                with self.assertRaisesRegex(ledger.NeonLedgerHold,reason):
                    ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)
                self.assertEqual(self.api.posts,0)

    def test_stored_deltas_preserve_policy_and_na_boundaries(self):
        for mode in ("policy","missing_shadow","missing_symbol"):
            with self.subTest(mode=mode):
                older=copy.deepcopy(self.calculate()["rows"])
                if mode=="missing_shadow":
                    older=ledger.plan(ASOF,RUN,MASTER,POLICY,scans(),
                        [list(ledger.HEADER)],None)["rows"]
                for row in older:
                    row[0]="2026-11-18|"+row[2]
                    row[1]="2026-11-18"
                    if mode=="policy":
                        row[21]="a"*64
                if mode=="missing_symbol":
                    older[0][2]="OLDPIT"
                    older[0][0]="2026-11-18|OLDPIT"
                first=[list(ledger.HEADER)]+older
                current=self.calculate(old=first)["rows"]
                self.assertEqual(current[0][6],"N/A")
                self.api.tab=first+current
                self.assertEqual(ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)["status"],
                                 "NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY")
                self.api.tab[478][6]="0.00"
                with self.assertRaisesRegex(ledger.NeonLedgerHold,"LEDGER_DELTA_MISSING_BASELINE"):
                    ledger.synchronize(self.api,ASOF,RUN,MASTER,POLICY,self.snap)
                self.assertEqual(self.api.posts,0)

    def test_old_factor_policy_change_yields_na_delta(self):
        old=copy.deepcopy(self.calculate()["rows"])
        for row in old:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
            row[4]="70.00"
            for j in range(7,12):
                row[j]="70.00"
            row[21]="a"*64
        rows=self.calculate(old=[list(ledger.HEADER)]+old)["rows"]
        self.assertTrue(all(row[6]=="N/A" for row in rows))

    def test_same_asof_wrong_master_sha_rejected(self):
        old=self.calculate()["rows"]
        for row in old: row[20]="a"*64
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SAME_ASOF_DIFFERENT_RUN_OR_POLICY"):
            self.calculate(old=[list(ledger.HEADER)]+old)

    def test_prior_mixed_source_day_rejected(self):
        old=copy.deepcopy(self.calculate()["rows"])
        for row in old:
            row[0]="2026-11-18|"+row[2]
            row[1]="2026-11-18"
        old[0][19]=RUN+"2"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"LEDGER_MIXED_DAY_SOURCE"):
            self.calculate(old=[list(ledger.HEADER)]+old)

    def test_no_earlier_backfill_when_latest_same_day(self):
        old=self.calculate()["rows"]
        earlier=copy.deepcopy(old)
        for row in earlier:
            row[0]="2026-11-20|"+row[2]
            row[1]="2026-11-20"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"NO_REPLAY_OR_BACKFILL"):
            self.calculate(old=[list(ledger.HEADER)]+earlier)

    def test_wrong_model_sha_rejected(self):
        p=copy.deepcopy(self.snap);p["policy_sha256"]="1"*64
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"NEON_SHADOW_PROVENANCE_DRIFT"):
            self.calculate(payload=p)

    def test_raw_al_or_high_score_not_signal(self):
        p=copy.deepcopy(self.snap)
        for r in p["rows"]:
            r["score"]="99.00"
            for key in r["factors"]:
                r["factors"][key]=99.0
        out=self.calculate(payload=p)
        self.assertEqual(len(out["rows"]),477)
        self.assertTrue(all(x[12]=="YAKINDAN_IZLE" and x[13]=="ELE" for x in out["rows"]))

    def test_invalid_spread_pass_rejected(self):
        p=copy.deepcopy(self.snap);p["rows"][0]["spread"]="PASS"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"RISK_UNKNOWN_CANNOT_BECOME_PASS"):
            self.calculate(payload=p)

    def test_reordered_rank_score_is_not_authoritative(self):
        # A valid-looking 477 list may contain internally contradictory ranks.
        p=copy.deepcopy(self.snap)
        p["rows"][0]["score"]="70.00"
        p["rows"][0]["factors"]={key:70.0 for key in neon.WEIGHTS}
        # Keep the first row's corridor consistent: isolate rank ordering.
        p["rows"][0]["decision_corridor"]="BEKLE"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_RANK_SCORE_OUT_OF_ORDER"):
            self.calculate(payload=p)

    def test_high_score_in_wait_corridor_is_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["decision_corridor"]="BEKLE"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_SCORE_CORRIDOR_DRIFT"):
            self.calculate(payload=p)

    def test_low_score_in_watch_corridor_is_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][-1]["score"]="70.00"
        p["rows"][-1]["factors"]={key:70.0 for key in neon.WEIGHTS}
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_SCORE_CORRIDOR_DRIFT"):
            self.calculate(payload=p)

    def test_malformed_daily_bar_timestamp_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["last_valid_bar_time"]=ASOF+"TFAKE"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_BAR_TIMESTAMP_INVALID"):
            self.calculate(payload=p)

    def test_naive_daily_bar_timestamp_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["last_valid_bar_time"]=ASOF+"T00:00:00"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_BAR_TIMESTAMP_INVALID"):
            self.calculate(payload=p)

    def test_timezone_shifted_bar_date_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["last_valid_bar_time"]=ASOF+"T23:30:00-05:00"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_BAR_TIMESTAMP_INVALID"):
            self.calculate(payload=p)

    def test_unrecognized_liquidity_proof_rejected(self):
        p=copy.deepcopy(self.snap)
        p["rows"][0]["liquidity"]="PASS_TOTAL_MARKET_UNVERIFIED"
        with self.assertRaisesRegex(ledger.NeonLedgerHold,"SHADOW_LIQUIDITY_STATUS_INVALID"):
            self.calculate(payload=p)

    def test_local_private_run_no_extra_network_via_plan(self):
        p=self.calculate()
        self.assertEqual(len(p["rows"]),477)
        self.assertTrue(all(x[19].startswith("https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/")
                            for x in p["rows"]))


if __name__=="__main__":
    unittest.main()
