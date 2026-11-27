"""A34 pure offline negative tests. Never requires secrets, network or broker."""
import copy
import unittest
import json
from urllib.error import HTTPError
from unittest.mock import patch
import preopen_a34 as w

ASOF = '2026-10-28'
SCOPE = '1'*64
POLICY = '2'*64
SYMBOLS = ['S%03d' % i for i in range(477)]
SCAN = [['ASOF ET','KANAL','ISTENEN','ISLENEN','GECERLI','EKSIK',
         'FINAL READY','YENI KAYIT','RUN','NOTE'],
        [ASOF,'GitHub schedule VERIFIED IEX EOD','477','477','477','0','TRUE','2',
         'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/999001',
         'scopeSHA='+SCOPE+';algorithmSHA='+POLICY+';source_event=schedule;NO_ORDERS']]
ROWS = {s:{'symbol':s,'asof_et':ASOF,'sessions':52,
           'decision':'AL' if i < 2 else 'ELE'} for i,s in enumerate(SYMBOLS)}

class A34ContractTest(unittest.TestCase):
    def test_success_477_and_immutable_count(self):
        self.assertEqual(w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,SCOPE,POLICY),2)
        out=w.validate_iex_result(SYMBOLS,ASOF,2,ROWS)
        self.assertEqual(out['covered'],477)
        self.assertFalse(out['device_ack'])
        self.assertFalse(out['writes'])
        self.assertFalse(out['orders'])

    def test_bad_scope_count(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1],SCAN,ASOF,SCOPE,POLICY)

    def test_bad_scope_duplicate(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1]+[SYMBOLS[0]],SCAN,ASOF,SCOPE,POLICY)

    def test_bad_scope_lowercase(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'EXACT_477'):
            w.validate_scope_and_scan(SYMBOLS[:-1]+['bad'],SCAN,ASOF,SCOPE,POLICY)

    def test_missing_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'SCANS_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,[],ASOF,SCOPE,POLICY)

    def test_stale_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'LATEST_COMPLETED_SCAN'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,'2026-10-27',SCOPE,POLICY)

    def test_undated_last_record_cannot_borrow_previous_valid_asof(self):
        """A trailing row with no ASOF must never borrow the prior source proof."""
        for bad_date in ('', None):
            with self.subTest(bad_date=bad_date):
                rows = copy.deepcopy(SCAN)
                rogue = copy.deepcopy(rows[-1])
                rogue[0] = bad_date
                rows.append(rogue)
                # Previously the empty date was silently omitted from 'days',
                # while the forged final row supplied all other PASS fields.
                with self.assertRaisesRegex(
                        w.PreopenBlocked, 'SCAN_ROW_ASOF_INVALID'):
                    w.validate_scope_and_scan(SYMBOLS, rows, ASOF, SCOPE, POLICY)

    def test_undated_middle_record_cannot_be_silently_skipped(self):
        rows = copy.deepcopy(SCAN)
        rogue = copy.deepcopy(rows[-1])
        rogue[0] = ''
        rows.insert(1, rogue)
        with self.assertRaisesRegex(
                w.PreopenBlocked, 'SCAN_ROW_ASOF_INVALID'):
            w.validate_scope_and_scan(SYMBOLS, rows, ASOF, SCOPE, POLICY)

    def test_duplicate_scan(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_DUPLICATE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN+[SCAN[-1]],ASOF,SCOPE,POLICY)

    def test_bad_counts(self):
        arr=copy.deepcopy(SCAN);arr[-1][4]='476'
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_NOT_FINAL'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_missing_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]='scopeSHA='+SCOPE
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_duplicate_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]+=';scopeSHA='+SCOPE
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_malformed_sha(self):
        arr=copy.deepcopy(SCAN);arr[-1][9]=arr[-1][9].replace(SCOPE,'x'*64)
        with self.assertRaisesRegex(w.PreopenBlocked,'SOURCE_PROOF_MISSING'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)

    def test_scope_sha_drift(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'CURRENT_SOURCE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,'3'*64,POLICY)

    def test_algorithm_sha_drift(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'CURRENT_SOURCE'):
            w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,SCOPE,'4'*64)

    def test_same_sha_manual_dispatch_cannot_masquerade_as_natural_eod(self):
        for kind in ('manual_origin', 'label_mismatch', 'missing_origin',
                     'duplicate_origin', 'wrong_origin', 'bad_run_url'):
            with self.subTest(kind=kind):
                s = copy.deepcopy(SCAN)
                if kind == 'manual_origin':
                    s[-1][1] = 'GitHub workflow_dispatch VERIFIED IEX EOD'
                    s[-1][9] = s[-1][9].replace(
                        'source_event=schedule', 'source_event=workflow_dispatch')
                elif kind == 'label_mismatch':
                    s[-1][1] = 'GitHub workflow_dispatch VERIFIED IEX EOD'
                elif kind == 'missing_origin':
                    s[-1][9] = s[-1][9].replace(';source_event=schedule','')
                elif kind == 'duplicate_origin':
                    s[-1][9] += ';source_event=schedule'
                elif kind == 'wrong_origin':
                    s[-1][9] = s[-1][9].replace(
                        'source_event=schedule', 'source_event=workflow_dispatch')
                elif kind == 'bad_run_url':
                    s[-1][8] = 'https://github.com/another/repo/actions/runs/999001'
                with self.assertRaisesRegex(
                        w.PreopenBlocked, 'CURRENT_SCAN_SCHEDULE_ORIGIN_UNVERIFIED'):
                    w.validate_scope_and_scan(SYMBOLS,s,ASOF,SCOPE,POLICY)

    def test_natural_schedule_origin_is_still_accepted(self):
        self.assertEqual(
            w.validate_scope_and_scan(SYMBOLS,SCAN,ASOF,SCOPE,POLICY),2)

    def test_candidate_provider_missing_one_symbol(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_PROVIDER_SCOPE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,{k:v for k,v in ROWS.items() if k!=SYMBOLS[0]})

    def test_invalid_provider_decision(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['decision']='VERI_YETERSIZ'
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_stale_provider_session(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['asof_et']='2026-10-27'
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_under_52_bars(self):
        arr=copy.deepcopy(ROWS);arr[SYMBOLS[0]]['sessions']=51
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_INCOMPLETE'):
            w.validate_iex_result(SYMBOLS,ASOF,2,arr)

    def test_false_al_count(self):
        with self.assertRaisesRegex(w.PreopenBlocked,'IEX_LIVE_AL_COUNT'):
            w.validate_iex_result(SYMBOLS,ASOF,1,ROWS)

    def test_unrecognized_numeric_scan(self):
        arr=copy.deepcopy(SCAN);arr[-1][7]='2.0'
        with self.assertRaisesRegex(w.PreopenBlocked,'SCAN_NEW_AL_COUNT'):
            w.validate_scope_and_scan(SYMBOLS,arr,ASOF,SCOPE,POLICY)


class A34MondayNovember23RealBoundaryAcceptance(unittest.TestCase):
    """No Friday 20 Nov FINAL means Monday 23 Nov preopen MUST HOLD.

    Offline reproduction of the recorded 19 Nov last FINAL; no producer
    replay, private Sheet write, external market call, or false opening PASS.
    """

    def test_20261123_0617_istanbul_uses_friday_20_xnas_not_thursday_19(self):
        import datetime as dt
        import engine
        import exchange_calendars as ec
        now=dt.datetime(2026,11,23,3,17,0,tzinfo=dt.timezone.utc)
        asof=engine.trading_asof(now).isoformat()
        self.assertEqual(asof,"2026-11-20")
        calendar=ec.get_calendar("XNAS")
        next_session=calendar.next_session(asof)
        self.assertEqual(str(next_session.date()),"2026-11-23")
        self.assertLess(now,calendar.session_open(next_session).to_pydatetime())

    def test_missing_friday_natural_source_blocks_a34_before_iex_or_github(self):
        import os
        import datetime as dt
        import engine
        from types import SimpleNamespace
        from performance_lab import private_performance_adapter as adapter
        from performance_lab import private_flight_recorder as flight

        current=dt.datetime(2026,11,23,3,17,0,tzinfo=dt.timezone.utc)
        class FixedClock:
            @staticmethod
            def now(tz=None):
                return current if tz is None else current.astimezone(tz)
        class FakePrivateSheet:
            def verify_metadata(self):
                return True
            def read(self,title,col):
                if title=="TARAMA_KAYITLARI":
                    missing=copy.deepcopy(SCAN)
                    missing[-1][0]="2026-11-19"
                    return missing
                return [["SYNTHETIC_HEADER"]]

        healthy_flight={
            "unreserved_current_eod_al":0,
            "unreserved_prior_eod_al":0,
            "panel_non_authoritative_stale":False,
            "panel_missing_asof":False,
        }
        stage={}
        with patch.object(w,"dt",SimpleNamespace(
                    datetime=FixedClock,date=dt.date,timezone=dt.timezone,
                    timedelta=dt.timedelta)),patch.object(
                    engine,"trading_asof",return_value=dt.date(2026,11,20)
                    ),patch.object(
                    adapter,"PrivateSheetReadOnly",
                    return_value=FakePrivateSheet()) as private,patch.object(
                    flight,"inspect",return_value=healthy_flight
                    ),patch.object(
                    engine,"live_read",
                    side_effect=AssertionError("IEX_NETWORK_MUST_NOT_RUN")
                    ) as iex,patch.object(
                    w,"verify_github_natural_eod_source",
                    side_effect=AssertionError("GITHUB_PROOF_MUST_NOT_RUN")
                    ) as github,patch.dict(os.environ,{
                        "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"SYNTHETIC",
                        "XRAY_PRIVATE_SPREADSHEET_ID":"SYNTHETIC",
                    },clear=True):
            with self.assertRaisesRegex(w.PreopenBlocked,
                                        "LATEST_COMPLETED_SCAN_NOT_READY"):
                w.live_entrypoint(stage)
            private.assert_called_once()
            iex.assert_not_called()
            github.assert_not_called()
        self.assertEqual(stage["current"],"SOURCE_SHA_SCOPE")

    def test_missing_friday_diagnostic_is_nonzero_and_never_claims_delivery(self):
        with patch.object(w,"live_entrypoint",side_effect=w.PreopenBlocked(
                "LATEST_COMPLETED_SCAN_NOT_READY")):
            with patch("builtins.print") as printed:
                self.assertEqual(w.main(),3)
        diagnostic=json.loads(printed.call_args_list[-1].args[0])
        self.assertEqual(diagnostic["status"],"A34_PREOPEN_BLOCKED")
        self.assertEqual(diagnostic["reason_code"],
                         "LATEST_COMPLETED_SCAN_NOT_READY")
        self.assertFalse(diagnostic["orders"])
        self.assertFalse(diagnostic["writes"])
        self.assertEqual(diagnostic["device_ack"],"UNKNOWN")
        self.assertEqual(printed.call_count,2)


class A34ExactAlIdentityTest(unittest.TestCase):
    """Same AL count must never hide a wrong ASOF|SYMBOL identity."""

    def candidates(self, *names):
        return [['ALARM KİMLİĞİ', 'ASOF ET', 'SEMBOL']] + [
            [ASOF + '|' + name, ASOF, name] for name in names]

    def test_legal_two_al_identical_set(self):
        self.assertEqual(w.validate_al_identity(
            self.candidates('S000', 'S001'), ASOF, 2, ROWS),
            'EXACT_AL_IDENTITY_PASS')

    def test_same_al_count_but_wrong_symbol_fails(self):
        # Count-only old A34 would pass: both lists contain two AL rows.
        self.assertEqual(w.validate_iex_result(SYMBOLS, ASOF, 2, ROWS)[
            'live_recomputed_al_count'], 2)
        with self.assertRaisesRegex(w.PreopenBlocked, 'AL_IDENTITY_MISMATCH'):
            w.validate_al_identity(self.candidates('S000', 'S002'), ASOF, 2, ROWS)

    def test_al_candidate_missing_fails(self):
        with self.assertRaisesRegex(w.PreopenBlocked, 'CURRENT_CANDIDATE_COUNT'):
            w.validate_al_identity(self.candidates('S000'), ASOF, 2, ROWS)

    def test_duplicate_candidate_fails(self):
        with self.assertRaisesRegex(w.PreopenBlocked, 'CANDIDATE_KEY_DUPLICATE'):
            w.validate_al_identity(self.candidates('S000', 'S000'), ASOF, 2, ROWS)

    def test_tampered_identity_fails(self):
        rows = self.candidates('S000', 'S001')
        rows[1][0] = ASOF + '|S009'
        with self.assertRaisesRegex(w.PreopenBlocked, 'CANDIDATE_IDENTITY_INVALID'):
            w.validate_al_identity(rows, ASOF, 2, ROWS)

    def test_header_drift_fails(self):
        rows = self.candidates('S000', 'S001')
        rows[0][1] = 'BAD_ASOF'
        with self.assertRaisesRegex(w.PreopenBlocked, 'CANDIDATE_HEADER_DRIFT'):
            w.validate_al_identity(rows, ASOF, 2, ROWS)

    def test_old_cohort_does_not_count_as_new(self):
        rows = self.candidates('S000', 'S001')
        rows.append(['2026-10-27|S020', '2026-10-27', 'S020'])
        self.assertEqual(w.validate_al_identity(rows, ASOF, 2, ROWS),
                         'EXACT_AL_IDENTITY_PASS')

    def test_zero_al_passes_with_no_current_candidates(self):
        none = {s: {**entry, 'decision':'ELE'} for s,entry in ROWS.items()}
        self.assertEqual(w.validate_al_identity(self.candidates(), ASOF, 0, none),
                         'EXACT_AL_IDENTITY_PASS')

    def test_live_entrypoint_must_invoke_identity_gate(self):
        import inspect
        source = inspect.getsource(w.live_entrypoint)
        self.assertIn("summary['al_identity_check'] = validate_al_identity(", source)



class A34ExactAlLevelsTest(unittest.TestCase):
    """Source-equivalent frozen levels must not be accepted when mismatched."""

    def source(self):
        records={s: {**v} for s,v in ROWS.items()}
        for symbol in ('S000', 'S001'):
            records[symbol].update(close=66.95, indicative_stop=62.405,
                                   indicative_target_2r=76.04)
        candidates=[['ALARM KİMLİĞİ', 'ASOF ET', 'SEMBOL', 'SINIF',
                     'IEX KAPANIŞ USD','STOP 2ATR','HEDEF 2R']]
        for s in ('S000','S001'):
            candidates.append([ASOF+'|'+s,ASOF,s,'TEKNİK AL ADAYI',
                               '66,95','62,405','76,04'])
        return candidates, records

    def test_identical_levels_pass(self):
        rows,computed=self.source()
        self.assertEqual(w.validate_al_levels(rows,ASOF,computed),
                         'EXACT_AL_LEVELS_PASS')

    def test_tampered_stop_rejected(self):
        rows,computed=self.source();rows[1][5]='61,405'
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_SOURCE_MISMATCH'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_tampered_target_rejected(self):
        rows,computed=self.source();rows[2][6]='76,041'
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_SOURCE_MISMATCH'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_tampered_reference_rejected(self):
        rows,computed=self.source();rows[1][4]='66,94'
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_SOURCE_MISMATCH'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_nonfinite_source_rejected(self):
        rows,computed=self.source();rows[1][4]='NaN'
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_INVALID'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_missing_level_rejected(self):
        rows,computed=self.source();rows[1]=rows[1][0:6]
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_INVALID'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_nonfinite_recomputation_rejected(self):
        rows,computed=self.source();computed['S001']['indicative_stop']=float('inf')
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_INVALID'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_out_of_epoch_levels_ignore_historical_rows(self):
        rows,computed=self.source()
        rows.append(['2026-10-27|S025','2026-10-27','S025',
                     'TEKNİK AL ADAYI','WRONG','WRONG','WRONG'])
        self.assertEqual(w.validate_al_levels(rows,ASOF,computed),
                         'EXACT_AL_LEVELS_PASS')

    def test_computed_non_al_invalid(self):
        rows,computed=self.source();computed['S000']['decision']='ELE'
        with self.assertRaisesRegex(w.PreopenBlocked,'AL_LEVEL_SOURCE_MISMATCH'):
            w.validate_al_levels(rows,ASOF,computed)

    def test_entrypoint_must_invoke_level_gate(self):
        import inspect
        self.assertIn("summary['al_level_check'] = validate_al_levels(",
                      inspect.getsource(w.live_entrypoint))


class A34ScheduleResilienceTest(unittest.TestCase):
    """8h GitHub schedule delay must not turn a normal preopen into postopen."""

    def test_upstream_eod_pr_cannot_produce_false_a34_success(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parent.parent /
                    '.github/workflows/xray-nasdaq-a34-preopen.yml').read_text(
                        encoding='utf-8')
        # Stronger allowlist: PR AND pre-session push NOOP cannot qualify.
        self.assertIn(
            "github.event_name != 'workflow_run' || "
            "github.event.workflow_run.event == 'schedule'",
            workflow)
        private_condition=workflow.split('  private-preopen:',1)[1].split(
            '    runs-on:',1)[0]
        self.assertNotIn(
            "github.event.workflow_run.event == 'workflow_dispatch'",
            private_condition)
        self.assertNotIn(
            "github.event.workflow_run.event != 'pull_request'",
            workflow)
        # The real private job must remain tied to actual EOD main source.
        self.assertIn("github.event.workflow_run.head_branch == 'main'",workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",workflow)

    def test_main_code_push_does_not_run_private_preopen(self):
        from pathlib import Path
        wf = (Path(__file__).resolve().parent.parent /
              '.github/workflows/xray-nasdaq-a34-preopen.yml').read_text(
                  encoding='utf-8')
        private_if = wf.split('  private-preopen:',1)[1].split('    runs-on:',1)[0]
        self.assertIn("github.event_name != 'push' &&",private_if)
        self.assertIn("github.event_name != 'pull_request' &&",private_if)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",private_if)

    def test_only_genuine_main_schedule_or_natural_eod_can_reach_private_a34(self):
        """P0: workflow_dispatch/manual invocation must never read private
        Sheets or IEX, including when ref=main and offline tests succeed.
        """
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent /
                  '.github/workflows/xray-nasdaq-a34-preopen.yml').read_text(
                      encoding='utf-8')
        private=workflow.split('  private-preopen:',1)[1].split(
            '    runs-on:',1)[0]
        # Do not rely on blacklist-only "not push, not pull_request";
        # workflow_dispatch satisfies both and was implicitly authorized.
        self.assertIn("github.event_name == 'schedule' ||",private)
        self.assertIn("github.event_name == 'workflow_run' &&",private)
        self.assertIn("github.run_attempt == 1",private)
        self.assertNotIn("github.event_name != 'workflow_run' ||",private)
        self.assertIn("needs: [offline-guard, parent-eod-admission]",private)
        self.assertIn("needs.offline-guard.result == 'success'",private)
        self.assertIn("(github.event_name == 'schedule' || (github.event_name == 'workflow_run' && needs.parent-eod-admission.result == 'success'))",private)
        self.assertIn("github.event.workflow_run.event == 'schedule'",private)
        self.assertIn("github.event.workflow_run.run_attempt == 1",private)
        self.assertIn(
            "github.event.workflow_run.path == '.github/workflows/xray-personal-477-eod.yml'",
            private)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",private)
        self.assertIn("github.event.workflow_run.repository.full_name == github.repository",private)

    def test_eod_safe_preopen_schedule_with_delayed_dispatch(self):
        import re
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        workflow = (Path(__file__).resolve().parent.parent /
                    '.github/workflows/xray-nasdaq-a34-preopen.yml').read_text(
                        encoding='utf-8')
        matches = re.findall(
            r"^\s+- cron: '(\d+) (\d+) \* \* 1-5'\s*$",
            workflow, flags=re.MULTILINE)
        self.assertEqual(len(matches), 1)
        minute, hour = map(int, matches[0])
        self.assertGreaterEqual(hour * 60 + minute, 180,
                                'A34 must leave 3h after the prior EOD cron')
        self.assertLess(hour * 60 + minute, 360,
                        'A34 must have dispatch-delay headroom')
        # Both US daylight and standard time: the earlier opening is 13:30Z.
        # Actual GitHub delay on 2026-11-03 exceeded 7h; test 8h.
        for market_open in (
            datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc),
            datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc),
        ):
            scheduled = market_open.replace(hour=hour, minute=minute)
            self.assertLess(scheduled + timedelta(hours=8), market_open,
                            'Observed GitHub cron delay must remain preopen')




class A34GitHubRunSourceProvenanceTest(unittest.TestCase):
    """An authentic-looking Sheet URL alone cannot certify a natural EOD."""

    @staticmethod
    def run_record():
        return {
            'id': 999001,
            'html_url': SCAN[-1][8],
            'path': '.github/workflows/xray-personal-477-eod.yml',
            'repository': {'full_name': 'gokaydonmez39-jpg/kripto-radar'},
            'event': 'schedule', 'status': 'completed',
            'conclusion': 'success', 'head_branch': 'main',
            'run_attempt': 1, 'created_at': '2026-10-29T00:00:00Z',
        }

    def test_forged_run_url_is_not_independent_source_proof(self):
        forged = copy.deepcopy(SCAN)
        forged[-1][8] = forged[-1][8].replace('999001', '999009')
        # Old code accepts a fake numeric run ID because URL shape is valid.
        self.assertEqual(
            w.validate_scope_and_scan(SYMBOLS, forged, ASOF, SCOPE, POLICY), 2)
        with self.assertRaisesRegex(
                w.PreopenBlocked, 'SOURCE_GITHUB_RUN_UNVERIFIED'):
            w.verify_github_natural_eod_source(
                ASOF, forged[-1][8],
                fetch=lambda _url: self.run_record())

    def test_exact_natural_first_attempt_is_accepted(self):
        receipt = w.verify_github_natural_eod_source(
            ASOF, SCAN[-1][8], fetch=lambda _url: self.run_record())
        self.assertEqual(receipt, 'GITHUB_NATURAL_EOD_SOURCE_VERIFIED')

    def test_cross_repo_manual_failed_retry_stale_or_wrong_job_hold(self):
        mutations = (
            {'event': 'workflow_dispatch'},
            {'status': 'in_progress', 'conclusion': None},
            {'conclusion': 'failure'},
            {'head_branch': 'test'},
            {'run_attempt': 2},
            {'run_attempt': True},
            {'run_attempt': 1.0},
            {'path': '.github/workflows/another.yml'},
            {'repository': {'full_name': 'another/repo'}},
            {'created_at': '2026-10-27T23:00:00Z'},
            {'created_at': '2026-10-30T12:00:00Z'},
            {'created_at': 'NOT_A_DATE'},
            {'html_url': 'https://github.com/another/repo/actions/runs/999001'},
            {'id': 999002},
        )
        for change in mutations:
            with self.subTest(change=change):
                row = self.run_record()
                row.update(change)
                with self.assertRaisesRegex(
                        w.PreopenBlocked, 'SOURCE_GITHUB_RUN_UNVERIFIED'):
                    w.verify_github_natural_eod_source(
                        ASOF, SCAN[-1][8], fetch=lambda _url, row=row: row)

    def test_network_error_and_untrusted_payload_fail_closed(self):
        for bad in (None, [], 'PRIVATE_TOKEN', {'id': 999001}):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(
                        w.PreopenBlocked, 'SOURCE_GITHUB_RUN_UNVERIFIED'):
                    w.verify_github_natural_eod_source(
                        ASOF, SCAN[-1][8], fetch=lambda _url, bad=bad: bad)
        def broken(_url):
            raise RuntimeError('PRIVATE_UNTRUSTED_TOKEN')
        with self.assertRaisesRegex(
                w.PreopenBlocked, 'SOURCE_GITHUB_RUN_UNVERIFIED'):
            w.verify_github_natural_eod_source(
                ASOF, SCAN[-1][8], fetch=broken)

    def test_live_entrypoint_must_call_real_source_gate_before_iex(self):
        import inspect
        code = inspect.getsource(w.live_entrypoint)
        self.assertIn('verify_github_natural_eod_source(', code)
        self.assertLess(code.index('verify_github_natural_eod_source('),
                        code.index('engine.live_read('))

    def test_real_private_runner_get_permissions_are_readonly(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parent.parent /
                '.github/workflows/xray-nasdaq-a34-preopen.yml').read_text()
        section = text.split('  private-preopen:', 1)[1]
        self.assertIn('actions: read', section)
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', section)



class A34SixJobNaturalSourceTest(unittest.TestCase):
    """A successful workflow banner cannot replace six verified real jobs."""

    @staticmethod
    def source_get(*, corrupt=None):
        import copy
        import fallback_job_receipt as receipt
        import test_fallback_job_receipt as fixture
        run,jobs=fixture.fixture()
        if corrupt=='guardian_skipped':
            jobs['jobs'][4]['conclusion']='skipped'
        elif corrupt=='writer_missing':
            jobs['jobs'][2]['steps']=[
                step for step in jobs['jobs'][2]['steps']
                if step.get('name') !=
                'Private Google Sheets writer (authorized service account only)']
        elif corrupt=='wrong_sha':
            jobs['jobs'][1]['head_sha']='f'*40
        origin={
            'id':run['id'],'created_at':run['created_at'],
            'head_branch':'main','event':'schedule',
            'path':receipt.PATH,'repository':{'full_name':receipt.REPO},
            'head_sha':run['head_sha'],'run_attempt':1,
            'status':'completed','conclusion':'success',
        }
        calls=[]
        def fetch(url):
            calls.append(url)
            if '/actions/workflows/' in url:
                listed=[origin]
                if corrupt=='duplicate_natural':
                    second=copy.deepcopy(origin)
                    second['id']+=1
                    listed.append(second)
                return {'total_count':len(listed),'workflow_runs':listed}
            if url.endswith('/jobs?per_page=100'):
                return copy.deepcopy(jobs)
            return copy.deepcopy(run)
        return fetch,calls,fixture.NOW,fixture.ASOF,receipt.EOD_RUN_BASE+str(run['id'])

    def test_six_job_real_source_positive_get_only(self):
        fetch,calls,now,asof,api_url=self.source_get()
        run_url=api_url.replace('https://api.github.com/repos/','https://github.com/').replace('/actions/runs/','/actions/runs/')
        self.assertEqual(
            w.verify_github_eod_six_job_chain(asof,run_url,now=now,fetch=fetch),
            'GITHUB_NATURAL_EOD_SIX_JOB_VERIFIED')
        self.assertEqual(len(calls),3)
        self.assertTrue(all(x.startswith('https://api.github.com/')
                            for x in calls))

    def test_skipped_guardian_missing_writer_or_bad_sha_are_hold(self):
        for issue in ('guardian_skipped','writer_missing','wrong_sha',
                      'duplicate_natural'):
            with self.subTest(issue=issue):
                fetch,calls,now,asof,api_url=self.source_get(corrupt=issue)
                run_url=api_url.replace('https://api.github.com/repos/',
                                        'https://github.com/')
                with self.assertRaisesRegex(
                        w.PreopenBlocked,'SOURCE_GITHUB_JOB_CHAIN_UNVERIFIED'):
                    w.verify_github_eod_six_job_chain(
                        asof,run_url,now=now,fetch=fetch)


    def test_friday_eod_is_valid_on_monday_preopen_without_new_dispatch(self):
        """An old-asof future Monday must not inherit fallback's 10h now limit."""
        import copy
        import fallback_job_receipt as receipt
        import test_fallback_job_receipt as fixture
        from datetime import datetime,timedelta,timezone
        run,jobs=fixture.fixture()
        shift=timedelta(days=1)
        def shift_utc(value):
            t=datetime.fromisoformat(value.replace('Z','+00:00'))
            return (t+shift).astimezone(timezone.utc).isoformat().replace(
                '+00:00','Z')
        for field in ('created_at','updated_at'):
            run[field]=shift_utc(run[field])
        for job in jobs['jobs']:
            for field in ('started_at','completed_at'):
                job[field]=shift_utc(job[field])
            for step in job['steps']:
                for field in ('started_at','completed_at'):
                    step[field]=shift_utc(step[field])
        asof='2026-11-20'
        monday=datetime(2026,11,23,12,0,tzinfo=timezone.utc)
        origin={'id':run['id'],'created_at':run['created_at'],
                'head_branch':'main','event':'schedule',
                'path':receipt.PATH,
                'repository':{'full_name':receipt.REPO},
                'head_sha':run['head_sha'],'run_attempt':1,
                'status':'completed','conclusion':'success'}
        calls=[]
        def fetch(url):
            calls.append(url)
            if '/actions/workflows/' in url:
                return {'total_count':1,'workflow_runs':[copy.deepcopy(origin)]}
            if url.endswith('/jobs?per_page=100'):
                return copy.deepcopy(jobs)
            return copy.deepcopy(run)
        url='https://github.com/'+receipt.REPO+'/actions/runs/'+str(run['id'])
        self.assertEqual(
            w.verify_github_eod_six_job_chain(
                asof,url,now=monday,fetch=fetch),
            'GITHUB_NATURAL_EOD_SIX_JOB_VERIFIED')
        self.assertEqual(len(calls),3)
        self.assertIn('2026-11-20T21',calls[0])
        self.assertNotIn('2026-11-23T',calls[0])

    def test_fake_success_wrong_run_id_cannot_pass_six_jobs(self):
        fetch,calls,now,asof,api_url=self.source_get()
        fake_url=api_url.replace('https://api.github.com/repos/',
                                 'https://github.com/').replace(
                                 str(int(api_url.rsplit('/',1)[1])),
                                 str(int(api_url.rsplit('/',1)[1])+7))
        with self.assertRaisesRegex(
                w.PreopenBlocked,'SOURCE_GITHUB_JOB_CHAIN_UNVERIFIED'):
            w.verify_github_eod_six_job_chain(
                asof,fake_url,now=now,fetch=fetch)

    def test_live_entrypoint_requires_unique_six_job_proof_before_iex(self):
        import inspect
        code=inspect.getsource(w.live_entrypoint)
        self.assertIn('verify_github_eod_six_job_chain(',code)
        self.assertLess(code.index('verify_github_eod_six_job_chain('),
                        code.index('engine.live_read('))



class A34ReviewedHistoricalQuarantineWiring(unittest.TestCase):
    def test_a34_future_research_only_count_uses_unresolved_not_raw_history(self):
        import inspect
        body=inspect.getsource(w.live_entrypoint)
        self.assertIn("flight['unresolved_quarantined_events']",body)
        self.assertIn("flight['reviewed_historical_non_emitting_events']",body)
        self.assertNotIn(
            "summary['quarantined_research_events'] = flight['quarantined_events']",
            body)

    def test_a34_any_other_unresolved_dispute_still_nonzero_exit(self):
        with patch.object(w,'live_entrypoint',return_value={
            'state':'CORE_PREOPEN_PASS_DISPUTED_EVENT_HOLD_DEVICE_ACK_UNKNOWN',
            'quarantined_research_events':1,
            'reviewed_historical_non_emitting_events':1,
            'private_data_published':False,'orders':False,
            'writes':False,'device_ack':False,
        }):
            with patch('builtins.print') as logs:
                self.assertEqual(w.main(),3)
            self.assertIn('DISPUTED_RESEARCH_EVENT_HOLD',
                          logs.call_args_list[-1].args[0])


class A34HoldExitCodeContract(unittest.TestCase):
    """GitHub job success may never attest a quarantined A34 HOLD."""

    @staticmethod
    def legal():
        return {
            'state': 'CORE_PREOPEN_PASS_DEVICE_ACK_UNKNOWN',
            'asof_et': ASOF, 'covered': 477, 'device_ack': False,
            'writes': False, 'orders': False,
            'private_data_published': False,
            'quarantined_research_events': 0,
            'pending_device_ack_events': 74,
        }

    def test_disputed_research_event_hold_must_not_exit_zero(self):
        held = self.legal()
        held.update(
            state='CORE_PREOPEN_PASS_DISPUTED_EVENT_HOLD_DEVICE_ACK_UNKNOWN',
            quarantined_research_events=1)
        with patch.object(w, 'live_entrypoint', return_value=held):
            with patch('builtins.print') as output:
                self.assertEqual(w.main(), 3)
        self.assertEqual(output.call_count, 2)
        self.assertIn('BLOCKED_NO_DATA_PUBLISHED_NO_WRITES',
                      output.call_args_list[0].args[0])
        redacted = json.loads(output.call_args_list[1].args[0])
        self.assertEqual(redacted['reason_code'],
                         'DISPUTED_RESEARCH_EVENT_HOLD')
        self.assertFalse(redacted['writes'])
        self.assertEqual(redacted['device_ack'], 'UNKNOWN')
        self.assertNotIn('quarantined_research_events',
                         str(output.call_args_list))

    def test_untrusted_receipt_cannot_turn_hold_into_success(self):
        forged = self.legal()
        forged['state'] = 'CORE_PREOPEN_PASS_PRIVATE_TICKER_TOKEN'
        with patch.object(w, 'live_entrypoint', return_value=forged):
            with patch('builtins.print') as output:
                self.assertEqual(w.main(), 3)
        code = json.loads(output.call_args_list[-1].args[0])
        self.assertEqual(code['reason_code'], 'A34_PASS_RECEIPT_UNVERIFIED')
        self.assertNotIn('PRIVATE_TICKER_TOKEN', str(output.call_args_list))

    def test_normal_readonly_pass_still_exits_zero(self):
        with patch.object(w, 'live_entrypoint', return_value=self.legal()):
            with patch('builtins.print') as output:
                self.assertEqual(w.main(), 0)
        self.assertEqual(output.call_count, 1)
        self.assertEqual(json.loads(output.call_args.args[0])['state'],
                         'CORE_PREOPEN_PASS_DEVICE_ACK_UNKNOWN')


class A34LiveFailureDiagnosticsRegression(unittest.TestCase):
    """No private values, URLs, bars, credentials, or ticker names in public stdout."""

    @staticmethod
    def response():
        from unittest.mock import call
        return None

    def test_known_a34_fail_closed_reason_is_categorical(self):
        with patch.object(w, 'live_entrypoint',
                          side_effect=w.PreopenBlocked('SCAN_NOT_FINAL_477')):
            with patch('builtins.print') as out:
                self.assertEqual(w.main(), 3)
        self.assertEqual(out.call_count, 2)
        self.assertIn('BLOCKED_NO_DATA_PUBLISHED_NO_WRITES',
                      out.call_args_list[0].args[0])
        receipt = json.loads(out.call_args_list[1].args[0])
        self.assertEqual(receipt['reason_code'], 'SCAN_NOT_FINAL_477')
        self.assertEqual(receipt['stage'], 'START')
        self.assertFalse(receipt['writes'])
        self.assertFalse(receipt['orders'])
        self.assertEqual(receipt['device_ack'], 'UNKNOWN')

    def test_http_429_at_source_read_is_categorized_not_leaked(self):
        def fail(*, stage):
            stage['current'] = 'SHEET_SOURCE_READ'
            raise HTTPError('https://private.example/SECRET_SYMBOL',
                            429, 'SECRET_MARKET_PAYLOAD', {}, None)
        with patch.object(w, 'live_entrypoint', side_effect=fail):
            with patch('builtins.print') as out:
                self.assertEqual(w.main(), 3)
        receipt = json.loads(out.call_args_list[-1].args[0])
        self.assertEqual(receipt['reason_code'], 'A34_HTTP_429')
        self.assertEqual(receipt['stage'], 'SHEET_SOURCE_READ')
        self.assertNotIn('SECRET_', str(out.call_args_list))

    def test_unknown_error_must_not_publish_private_payload(self):
        with patch.object(w, 'live_entrypoint',
                          side_effect=ValueError('SECRET_PRIVATE_ROW_AND_TOKEN')):
            with patch('builtins.print') as out:
                self.assertEqual(w.main(), 3)
        receipt = json.loads(out.call_args_list[-1].args[0])
        self.assertEqual(receipt['reason_code'], 'UNCLASSIFIED')
        self.assertEqual(receipt['stage'], 'START')
        self.assertNotIn('SECRET_PRIVATE_ROW', str(out.call_args_list))
        self.assertFalse(receipt['private_data_published'])

    def test_unrecognized_preopen_error_not_allowed_in_public_stdout(self):
        with patch.object(w, 'live_entrypoint',
                          side_effect=w.PreopenBlocked('PRIVATE_TICKER_123')):
            with patch('builtins.print') as out:
                self.assertEqual(w.main(), 3)
        receipt = json.loads(out.call_args_list[-1].args[0])
        self.assertEqual(receipt['reason_code'], 'UNCLASSIFIED')
        self.assertNotIn('PRIVATE_TICKER_123', str(out.call_args_list))



class A34FlightFailureDiagnosticTests(unittest.TestCase):
    def test_flight_recorder_static_code_is_reported_without_any_private_rows(self):
        from performance_lab.private_flight_recorder import FlightRecorderBlocked
        def fail(*, stage):
            stage['current'] = 'PRIVATE_FLIGHT_RECORDER'
            raise FlightRecorderBlocked('FLIGHT_SCAN_NOT_FULL_FINAL')
        with patch.object(w, 'live_entrypoint', side_effect=fail):
            with patch('builtins.print') as output:
                self.assertEqual(w.main(), 3)
        receipt = json.loads(output.call_args_list[-1].args[0])
        self.assertEqual(receipt['reason_code'], 'FLIGHT_SCAN_NOT_FULL_FINAL')
        self.assertEqual(receipt['stage'], 'PRIVATE_FLIGHT_RECORDER')
        self.assertFalse(receipt['private_data_published'])

    def test_a14_known_private_read_only_failure_is_a_safe_constant(self):
        from performance_lab.nasdaq_performance_guard import EvidenceBlocked
        self.assertEqual(
            w.public_preopen_failure_code(EvidenceBlocked('SHEET_TIMEZONE_CHANGED')),
            'SHEET_TIMEZONE_CHANGED')
        self.assertEqual(
            w.public_preopen_failure_code(EvidenceBlocked('PRIVATE_UNTRUSTED_TICKER_123')),
            'UNCLASSIFIED')

    def test_flight_recorder_rogue_value_is_redacted(self):
        from performance_lab.private_flight_recorder import FlightRecorderBlocked
        self.assertEqual(
            w.public_preopen_failure_code(
                FlightRecorderBlocked('PRIVATE_SYMBOL_AND_TOKEN')),
            'UNCLASSIFIED')


class A34MandatoryCiCoverage(unittest.TestCase):
    def test_required_pr_ci_includes_a34_in_normal_and_optimized_mode(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent /
                  '.github/workflows/xray-nasdaq-477-pr-required-readonly.yml'
                  ).read_text(encoding='utf-8')
        self.assertIn('python -m unittest -q test_preopen_a34', workflow)
        self.assertIn('python -O -m unittest -q test_preopen_a34', workflow)
        self.assertNotIn('continue-on-error: true', workflow)


if __name__=='__main__':unittest.main()
