"""Self-contained CI regression: no market network, public personal-swing repo safe."""
import json
import tempfile
import unittest
from pathlib import Path
import exchange_calendars as ec
import engine,runner,tracker,daily_job

ASOF='2026-10-22'

def synthetic_bars(day=ASOF,symbols=('CVLT',)):
    cal=ec.get_calendar('XNAS')
    dates=[str(x.date()) for x in cal.sessions_in_range('2026-06-01',day)][-55:]
    d={}
    for s in symbols:
        rows=[]
        for i,date in enumerate(dates):
            c=90+i*.22
            rows.append({'timestamp':date+'T04:00:00+00:00','open':c-.3,
                         'high':c+.7,'low':c-.9,'close':c,'volume':20000+i*100})
        d[s]=rows
    return d

class OfflineCIPipeline(unittest.TestCase):
    def test_52_sessions_are_contiguous_and_deterministic(self):
        data=synthetic_bars()['CVLT']
        a=engine.analyze('CVLT',data,ASOF)
        b=engine.analyze('CVLT',data,ASOF)
        self.assertEqual(a,b)
        self.assertIn(a['decision'],['AL','ELE','IZLE'])
        self.assertEqual(a['asof_et'],ASOF)
    def test_missing_daily_bar_cannot_be_candidate(self):
        bars=synthetic_bars()['CVLT']
        bars.pop(-10)
        self.assertEqual(engine.analyze('CVLT',bars,ASOF)['decision'],'VERI_YETERSIZ')
    def test_old_asof_is_not_new_signal(self):
        bars=synthetic_bars()['CVLT'][:-1]
        self.assertEqual(engine.analyze('CVLT',bars,ASOF)['decision'],'VERI_YETERSIZ')
    def test_workflow_scope_exact_477_distinct(self):
        syms=runner.get_scope(watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')))
        self.assertEqual(len(syms),477)
        self.assertEqual(len(set(syms)),477)
    def test_partial_resume_completes_and_preserves_previous_work(self):
        with tempfile.TemporaryDirectory() as out:
            symbols=['CVLT','AAPL','AMD']
            first=runner.scan(ASOF,symbols,out,batch_size=1,max_batches=1,read_batch=lambda g,a:synthetic_bars(a,g))
            self.assertEqual(first['processed_symbols'],1)
            self.assertFalse(first['new_signal_publishable'])
            ran=[]
            def fetch(g,a):
                ran.extend(g);return synthetic_bars(a,g)
            last=runner.scan(ASOF,symbols,out,batch_size=1,read_batch=fetch)
            self.assertEqual(ran,['AAPL','AMD'])
            self.assertTrue(last['valid_data_coverage_complete'])
            self.assertEqual(last['processed_symbols'],3)
    def test_provider_data_missing_not_elected(self):
        with tempfile.TemporaryDirectory() as out:
            s=runner.scan(ASOF,['CVLT','AAPL'],out,read_batch=lambda g,a:{})
            self.assertEqual(s['insufficient_data_symbols'],2)
            self.assertFalse(s['new_signal_publishable'])
            self.assertFalse((Path(out)/'latest.json').exists())
    def test_cli_exit_rejects_all_rows_present_with_invalid_data(self):
        """An all-processed but invalid IEX response is NEVER shell success."""
        from unittest.mock import patch
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as out:
            with patch.object(engine,'validate_asof'), patch.object(engine,'live_read',return_value={}):
                with redirect_stdout(io.StringIO()):
                    code=runner.main(['--symbols','CVLT','--asof',ASOF,'--dir',out])
            self.assertEqual(code,2)
            cp=json.loads((Path(out)/'checkpoint.json').read_text())
            self.assertEqual(len(cp['rows']),1)
            self.assertEqual(cp['rows']['CVLT']['decision'],'VERI_YETERSIZ')
            self.assertFalse((Path(out)/'latest.json').exists())

    def test_same_asof_computation_change_invalidates_checkpoint(self):
        """Changed analysis must never reuse successful old AL/IZLE/ELE rows."""
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as out:
            symbols=['CVLT','AAPL']
            calls=[]
            def reader(group,day):
                calls.append(tuple(group))
                return synthetic_bars(day,group)
            with patch.object(runner,'analysis_fingerprint',return_value='f'*64):
                first=runner.scan(ASOF,symbols,out,read_batch=reader)
            self.assertEqual(len(calls),1)
            self.assertEqual(first['analysis_fingerprint_sha256'],'f'*64)
            calls.clear()
            with patch.object(runner,'analysis_fingerprint',return_value='a'*64):
                second=runner.scan(ASOF,symbols,out,read_batch=reader)
            self.assertEqual(len(calls),1)
            self.assertEqual(second['analysis_fingerprint_sha256'],'a'*64)
            archives=list(Path(out).glob('checkpoint_*.json'))
            self.assertEqual(len(archives),1)
            self.assertEqual(json.loads(archives[0].read_text())['analysis_fingerprint_sha256'],'f'*64)

    def test_old_checkpoint_without_policy_hash_cannot_be_reused(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as out:
            with patch.object(runner,'analysis_fingerprint',return_value='b'*64):
                runner.scan(ASOF,['CVLT'],out,read_batch=lambda group,day:synthetic_bars(day,group))
            cp=Path(out)/'checkpoint.json'
            state=json.loads(cp.read_text())
            state.pop('analysis_fingerprint_sha256')
            cp.write_text(json.dumps(state))
            calls=[]
            def reader(group,day):
                calls.append(group)
                return synthetic_bars(day,group)
            with patch.object(runner,'analysis_fingerprint',return_value='b'*64):
                result=runner.scan(ASOF,['CVLT'],out,read_batch=reader)
            self.assertEqual(calls,[['CVLT']])
            self.assertTrue(result['valid_data_coverage_complete'])

    def test_missing_response_retains_previous_final(self):
        with tempfile.TemporaryDirectory() as out:
            p=Path(out)/'latest.json'
            p.write_text('{"asof_et":"2026-10-21"}\n')
            runner.scan(ASOF,['CVLT'],out,read_batch=lambda g,a:{})
            self.assertIn('2026-10-21',p.read_text())
    def test_journal_dedup_same_date_symbol(self):
        with tempfile.TemporaryDirectory() as out:
            snap=runner.scan(ASOF,['CVLT'],out,read_batch=lambda g,a:synthetic_bars(a,g))
            row=snap['rows'][0]
            row.update(decision='AL',close=101.,atr14=2.,indicative_stop=97.,indicative_target_2r=109.)
            j=tracker.base_journal()
            self.assertEqual(tracker.append_signals(snap,j),['2026-10-22|CVLT'])
            self.assertEqual(tracker.append_signals(snap,j),[])
            self.assertEqual(len(j['signals']),1)
    def test_no_signal_on_partial_history(self):
        with tempfile.TemporaryDirectory() as out:
            snap=runner.scan(ASOF,['CVLT'],out,read_batch=lambda g,a:{})
            with self.assertRaisesRegex(ValueError,'PARTIAL_OR_UNSAFE'):
                tracker.append_signals(snap,tracker.base_journal())
    def test_stop_target_same_candle_is_ambiguous(self):
        sig={'symbol':'CVLT','status':'OPEN','asof_et':'2026-10-22','processed_through':'2026-10-22',
             'stop':95.,'target_2r':110.,'reference_close':100.,'days_held':0,'events':[]}
        bar={'timestamp':'2026-10-23T04:00:00Z','open':103.,'high':111.,'low':94.,'close':105.,'volume':10000}
        tracker.track_symbol(sig,[bar],'2026-10-23')
        self.assertEqual(sig['outcome'],'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS')
    def test_missing_followup_intermediate_session_is_rejected(self):
        sig={'symbol':'CVLT','status':'OPEN','asof_et':'2026-10-20','processed_through':'2026-10-20',
             'stop':95.,'target_2r':110.,'reference_close':100.,'days_held':0,'events':[]}
        bar={'timestamp':'2026-10-22T04:00:00Z','open':103.,'high':104.,'low':98.,'close':102.,'volume':10000}
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_MISSING'):
            tracker.track_symbol(sig,[bar],'2026-10-22')
    def test_private_html_server_responds_only_to_loopback(self):
        import threading, urllib.request
        from http.server import ThreadingHTTPServer
        import server
        with tempfile.TemporaryDirectory() as out:
            srv=ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(out))
            thr=threading.Thread(target=srv.serve_forever,daemon=True)
            thr.start()
            try:
                url='http://127.0.0.1:'+str(srv.server_address[1])+'/'
                # CI runners may define an HTTP proxy; loopback must never route through it.
                direct=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with direct.open(url,timeout=3) as response:
                    self.assertEqual(response.status,200)
                    self.assertIn(b'XRAY',response.read())
                    self.assertIn('no-store',response.headers['Cache-Control'])
            finally:
                srv.shutdown();srv.server_close();thr.join(3)
    def test_daily_job_no_keys_wont_be_reported_as_success(self):
        with tempfile.TemporaryDirectory() as out:
            summary=daily_job.run_once(asof=ASOF,symbols=['CVLT'],directory=out,
                read_batch=lambda group,asof:{},batch_size=1)
            self.assertFalse(summary['final_ready'])

class OfficialExchangeDSTTransition(unittest.TestCase):
    """Real NY IANA timezone and XNAS calendar; never fixed UTC offsets."""
    def test_october_26_normal_close_turkey_2300(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        close=datetime(2026,10,26,16,0,tzinfo=ZoneInfo('America/New_York'))
        tr=close.astimezone(ZoneInfo('Europe/Istanbul'))
        self.assertEqual((tr.hour,tr.minute,tr.date().isoformat()),(23,0,'2026-10-26'))
        self.assertEqual(close.utcoffset().total_seconds(),-4*3600)

    def test_november_2_normal_close_turkey_next_midnight(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        close=datetime(2026,11,2,16,0,tzinfo=ZoneInfo('America/New_York'))
        tr=close.astimezone(ZoneInfo('Europe/Istanbul'))
        self.assertEqual((tr.hour,tr.minute,tr.date().isoformat()),(0,0,'2026-11-03'))
        self.assertEqual(close.utcoffset().total_seconds(),-5*3600)

    def test_november_2_not_complete_before_45min(self):
        from datetime import datetime,timezone
        self.assertEqual(engine.trading_asof(datetime(2026,11,2,21,44,tzinfo=timezone.utc)).isoformat(),'2026-10-30')
        self.assertEqual(engine.trading_asof(datetime(2026,11,2,21,46,tzinfo=timezone.utc)).isoformat(),'2026-11-02')

    def test_fixed_2315_utc_workflow_after_close_in_both_seasons(self):
        from datetime import datetime,timedelta,timezone
        import exchange_calendars as ec
        cal=ec.get_calendar('XNAS')
        for d in ('2026-10-26','2026-11-02'):
            finish=cal.session_close(d).to_pydatetime()+timedelta(minutes=45)
            scheduler=datetime.fromisoformat(d+'T23:15:00+00:00')
            self.assertGreaterEqual(scheduler,finish)

class DailyHolidayAndFreshnessGuard(unittest.TestCase):
    """Scheduled runs cannot recycle a previous session as today's new signal."""
    def test_monday_before_close_never_reuses_friday(self):
        from datetime import datetime, timezone
        self.assertIsNone(daily_job.current_completed_session(
            datetime(2026,10,26,19,30,tzinfo=timezone.utc)))
    def test_monday_after_45_minutes_is_accepted(self):
        from datetime import datetime, timezone
        self.assertEqual(daily_job.current_completed_session(
            datetime(2026,10,26,21,0,tzinfo=timezone.utc)),'2026-10-26')
    def test_november_standard_time_preclose_is_not_fresh(self):
        from datetime import datetime, timezone
        self.assertIsNone(daily_job.current_completed_session(
            datetime(2026,11,2,20,45,tzinfo=timezone.utc)))
        self.assertEqual(daily_job.current_completed_session(
            datetime(2026,11,2,23,15,tzinfo=timezone.utc)),'2026-11-02')
    def test_november_thanksgiving_holiday_skipped(self):
        from datetime import datetime, timezone
        self.assertIsNone(daily_job.current_completed_session(
            datetime(2026,11,26,23,15,tzinfo=timezone.utc)))
    def test_saturday_skipped(self):
        from datetime import datetime, timezone
        self.assertIsNone(daily_job.current_completed_session(
            datetime(2026,10,24,23,15,tzinfo=timezone.utc)))

if __name__=='__main__':unittest.main()
