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
                with urllib.request.urlopen(url,timeout=3) as response:
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

if __name__=='__main__':unittest.main()
