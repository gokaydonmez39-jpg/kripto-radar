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
        [ASOF,'GitHub','477','477','477','0','TRUE','2','https://example.invalid',
         'scopeSHA='+SCOPE+';algorithmSHA='+POLICY+';NO_ORDERS']]
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
        self.assertIn(
            "github.event_name != 'workflow_run' || "
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
