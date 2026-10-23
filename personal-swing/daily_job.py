#!/usr/bin/env python3
"""One EOD research pass. Never trades, never pushes, never exports market bars.

Use a persistent private --dir for restart-safe local operation. A GitHub Actions
runner is ephemeral: a later workflow run cannot resume without persisted storage.
"""
import argparse
import json
import sys
import os
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
    asof=a.asof or engine.trading_asof().isoformat()
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
