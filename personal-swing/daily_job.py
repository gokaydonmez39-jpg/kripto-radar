#!/usr/bin/env python3
"""One EOD research pass. Never trades, never pushes, never exports market bars.

Use a persistent private --dir for restart-safe local operation. A GitHub Actions
runner is ephemeral: a later workflow run cannot resume without persisted storage.
"""
import argparse
import json
import sys
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import fcntl
from pathlib import Path
import engine
import runner
import tracker


def run_once(*, asof, symbols, directory, batch_size=10, max_batches=None,
             read_batch=None, followups=False):
    engine.validate_asof(asof)
    dest=Path(directory)
    dest.mkdir(parents=True,exist_ok=True)
    lockfile=dest/'daily.lock'
    with lockfile.open('a+') as h:
        try:fcntl.flock(h.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('ALREADY_RUNNING_LOCK_HELD')
        try:
            snap=runner.scan(asof,symbols,dest,batch_size=batch_size,
                             max_batches=max_batches,read_batch=read_batch)
            summary={
                'asof_et':asof,'universe':len(symbols),
                'processed':snap['processed_symbols'],
                'valid':snap['valid_data_symbols'],
                'invalid_or_missing':snap['insufficient_data_symbols'],
                'remaining':snap['remaining_symbols'],
                'final_ready':snap['valid_data_coverage_complete'],
                # Safe public diagnostics: identity and policy hashes, NEVER bars/signals.
                # Downstream private Sheet writer must independently recompute the
                # exact scope and session; these hashes are correlation witnesses.
                'scope_sha256':snap['scope_sha256'],
                'analysis_fingerprint_sha256':snap['analysis_fingerprint_sha256'],
                'no_execution':True,
            }
            if snap['valid_data_coverage_complete']:
                state=tracker.process_snapshot(dest/'latest.json',dest/'journal.json',
                                               fetch_followups=followups)
                summary['new_entries']=len(state['new_signals'])
                summary['history_outcome_changes']=len(state['closed_signals'])
            return summary
        finally:
            fcntl.flock(h.fileno(),fcntl.LOCK_UN)


def current_completed_session(now=None):
    """Last official XNAS EOD only within a bounded close+45m freshness window.

    A GitHub schedule may run after 00:00 New York time yet still belong to
    yesterday's completed session. Reject pre-close scans, holidays, weekends
    and old recycled epochs; NEVER choose an unfinished trading day.
    """
    from datetime import timedelta
    import exchange_calendars as ec
    instant = (now or datetime.now(timezone.utc))
    if instant.tzinfo is None:
        raise ValueError('AWARE_NOW_REQUIRED')
    instant = instant.astimezone(timezone.utc)
    completed = engine.trading_asof(instant).isoformat()
    cal = ec.get_calendar('XNAS')
    ready_at = cal.session_close(completed).to_pydatetime() + timedelta(minutes=45)
    # A short after-midnight schedule delay must not erase the prior EOD scan.
    # By the next opening this is safely outside the last-session window.
    return completed if ready_at <= instant <= ready_at + timedelta(hours=10) else None


def main(argv=None):
    p=argparse.ArgumentParser(description='Personal, read-only daily START/FINAL scan')
    p.add_argument('--dir',default='private-data')
    p.add_argument('--watchlist-file',default=str(Path(__file__).with_name('nasdaq_watchlist_477.json')))
    p.add_argument('--asof')
    p.add_argument('--batch-size',type=int,default=10)
    p.add_argument('--max-batches',type=int)
    p.add_argument('--followups',action='store_true')
    p.add_argument('--github-safe-log',action='store_true',help='Suppress per-symbol detail')
    a=p.parse_args(argv)
    asof=a.asof if a.asof else current_completed_session()
    if asof is None:
        print(json.dumps({'status':'SKIPPED_NO_COMPLETED_CURRENT_ET_SESSION',
                          'execution':'NONE','market_data_called':False},sort_keys=True))
        return 0
    symbols=runner.get_scope(watchlist_file=a.watchlist_file)
    try:
        summary=run_once(asof=asof,symbols=symbols,directory=a.dir,
                         batch_size=a.batch_size,max_batches=a.max_batches,
                         followups=a.followups)
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__,
                          'execution':'NONE'},ensure_ascii=False))
        return 3
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    return 0 if summary['final_ready'] else 2

if __name__=='__main__':sys.exit(main())
