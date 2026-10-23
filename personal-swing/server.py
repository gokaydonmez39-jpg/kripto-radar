#!/usr/bin/env python3
"""Private auto-updating local web radar: browser polls JSON, server refreshes after EOD.
Default loopback only; no arbitrary shell actions and no remote trading.
"""
import argparse
from datetime import datetime,timezone
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
from pathlib import Path
import threading
import time
import urllib.parse
import engine
import runner
import tracker

BASE=Path(__file__).resolve().parent

def cycle(data_dir,watchlist_file=None,repo_watchlist=False):
    asof=engine.trading_asof().isoformat()
    syms=runner.get_scope(watchlist_file=watchlist_file,repo_watchlist=repo_watchlist)
    data_dir=Path(data_dir)
    snap=runner.scan(asof,syms,data_dir)
    if snap['valid_data_coverage_complete']:
        tracker.process_snapshot(data_dir/'latest.json',data_dir/'journal.json',fetch_followups=True)
    return snap


def make_handler(directory):
    root=Path(directory).resolve()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route=urllib.parse.urlsplit(self.path).path
            if route in ('/','/index.html'):p=BASE/'private_index.html';mime='text/html; charset=utf-8'
            elif route=='/api/latest':p=root/'latest.json';mime='application/json; charset=utf-8'
            elif route=='/api/journal':p=root/'journal.json';mime='application/json; charset=utf-8'
            elif route=='/api/progress':p=root/'progress.json';mime='application/json; charset=utf-8'
            elif route=='/api/health':
                self._send_json({'running':True,'read_only':True,'broker':False,
                        'orders':False,'last_session_target':safe_session()});return
            else:self.send_error(404);return
            if not p.is_file():
                self._send_json({'ready':False,'reason':'DATA_NOT_YET_AVAILABLE'},status=503);return
            b=p.read_bytes()
            self.send_response(200);self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def _send_json(self,ob,status=200):
            b=json.dumps(ob,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)))
            self.end_headers();self.wfile.write(b)
        def log_message(self,*args):pass
    return Handler


def safe_session():
    try:return engine.trading_asof().isoformat()
    except Exception:return 'CALENDAR_UNKNOWN'


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--host',default='127.0.0.1')
    a.add_argument('--port',type=int,default=8765)
    a.add_argument('--dir',default='private-data')
    a.add_argument('--watchlist-file')
    a.add_argument('--repo-watchlist',action='store_true')
    a.add_argument('--poll-seconds',type=int,default=600)
    z=a.parse_args()
    if z.host not in ('127.0.0.1','localhost','::1'):
        raise ValueError('PRIVATE_LOCAL_BIND_ONLY_NO_PUBLIC_HTTP')
    if z.poll_seconds<60:raise ValueError('POLL_FREQUENCY_TOO_HIGH')
    root=Path(z.dir).resolve();root.mkdir(parents=True,exist_ok=True)
    def auto_refresh():
        while True:
            try:
                # Safe offline on errors: last available data remains date-labelled.
                cp=root/'checkpoint.json'
                ready=False
                if (root/'latest.json').exists():
                    d=json.loads((root/'latest.json').read_text())
                    ready=d.get('valid_data_coverage_complete') is True and d.get('asof_et')==safe_session()
                if not ready:
                    cycle(root,z.watchlist_file,z.repo_watchlist)
            except Exception as ex:
                print('REFRESH_BLOCKED:',type(ex).__name__,str(ex)[:180],flush=True)
            time.sleep(z.poll_seconds)
    threading.Thread(target=auto_refresh,daemon=True).start()
    host=ThreadingHTTPServer((z.host,z.port),make_handler(root))
    print('XRAY personal local UI: http://'+z.host+':'+str(z.port),flush=True)
    host.serve_forever()

if __name__=='__main__':main()
