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
             read_batch=None, followups=False, neon_shadow=False):
    engine.validate_asof(asof)
    dest=Path(directory)
    dest.mkdir(parents=True,exist_ok=True)
    lockfile=dest/'daily.lock'
    with lockfile.open('a+') as h:
        try:fcntl.flock(h.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('ALREADY_RUNNING_LOCK_HELD')
        try:
            # Advisory tap reads original provider data exactly once per group.
            # Any shadow setup failure leaves the primary data path unchanged.
            neon_capture=None
            shadow_reader=read_batch
            if neon_shadow:
                try:
                    import neon_shadow_v3
                    neon_capture=neon_shadow_v3.Capture(
                        read_batch if read_batch is not None else engine.live_read,
                        symbols, asof)
                    shadow_reader=neon_capture.read
                except Exception:
                    neon_capture=None
                    shadow_reader=read_batch
            snap=runner.scan(asof,symbols,dest,batch_size=batch_size,
                             max_batches=max_batches,read_batch=shadow_reader)
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
                # A freshly provisioned GitHub runner has no durable journal.
                # The private Sheet is the source of truth for older episodes.
                # 0 changes means "checked, none changed" ONLY with evidence.
                'followups_attempted':False,
                'followup_status':'NOT_RUN_INCOMPLETE_SCAN',
                'historical_episode_coverage_verified':False,
                'history_outcome_changes':None,
            }
            if snap['valid_data_coverage_complete']:
                state=tracker.process_snapshot(dest/'latest.json',dest/'journal.json',
                                               fetch_followups=followups)
                summary['new_entries']=len(state['new_signals'])
                summary['followups_attempted']=bool(followups)
                if followups:
                    summary['followup_status']=('LOCAL_EPHEMERAL_ERRORS'
                        if state['followup_errors'] else
                        'LOCAL_EPHEMERAL_JOURNAL_NOT_FULL_HISTORY')
                    summary['history_outcome_changes']=len(state['closed_signals'])
                else:
                    summary['followup_status']='NOT_RUN_NO_PERSISTED_HISTORY'
            if neon_shadow:
                # No failure from a purely advisory calculation may suppress
                # existing EOD, AL, STOP, private Sheet or delivery contracts.
                summary['neon_shadow']={
                    'status':'NEON_SHADOW_HOLD_NO_DELIVERY',
                    'scored':0,'notification_sent':False}
                if neon_capture is not None and snap['valid_data_coverage_complete']:
                    try:
                        summary['neon_shadow']=neon_capture.finish(
                            snap,expected_policy_sha=runner.analysis_fingerprint(),
                            now_utc=datetime.now(timezone.utc),
                            source_event=os.environ.get('GITHUB_EVENT_NAME','UNKNOWN'),
                            output_file=dest/('neon_shadow_v3_'+asof+'.json'))
                    except Exception:
                        pass
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


def expired_natural_eod_window(now=None):
    """Detect a provably late, still-attributable natural EOD without market IO.

    A late scheduled run beyond close+45m+10h must not return success merely
    because the safe source window is closed. The outer 24h bound prevents
    a holiday's legitimate no-session cron from being called missing EOD.
    Beyond 24h the exact scheduled epoch is unknown: keep no-op, no replay.
    """
    from datetime import timedelta
    import exchange_calendars as ec
    instant=(now or datetime.now(timezone.utc))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('AWARE_NOW_REQUIRED')
    instant=instant.astimezone(timezone.utc)
    completed=engine.trading_asof(instant).isoformat()
    cal=ec.get_calendar('XNAS')
    cutoff=cal.session_close(completed).to_pydatetime() + timedelta(minutes=45)
    age=instant-cutoff
    return timedelta(hours=10) < age <= timedelta(hours=24)


def main(argv=None):
    p=argparse.ArgumentParser(description='Personal, read-only daily START/FINAL scan')
    p.add_argument('--dir',default='private-data')
    p.add_argument('--watchlist-file',default=str(Path(__file__).with_name('nasdaq_watchlist_477.json')))
    p.add_argument('--asof')
    p.add_argument('--batch-size',type=int,default=10)
    p.add_argument('--max-batches',type=int)
    p.add_argument('--followups',action='store_true')
    p.add_argument('--neon-shadow',action='store_true',help='Ephemeral research-only NEON audit; no delivery')
    p.add_argument('--github-safe-log',action='store_true',help='Suppress per-symbol detail')
    a=p.parse_args(argv)
    asof=a.asof if a.asof else current_completed_session()
    if asof is None:
        if (os.environ.get('GITHUB_EVENT_NAME')=='schedule'
                and expired_natural_eod_window()):
            # This is NOT a request to rescan/backfill the previous session.
            # It only prevents a missed real EOD from looking green.
            print(json.dumps({'status':'BLOCKED_NATURAL_EOD_FRESHNESS_WINDOW_EXPIRED',
                              'execution':'NONE','market_data_called':False,
                              'dispatch_requested':False},sort_keys=True))
            return 3
        print(json.dumps({'status':'SKIPPED_NO_COMPLETED_CURRENT_ET_SESSION',
                          'execution':'NONE','market_data_called':False},sort_keys=True))
        return 0
    symbols=runner.get_scope(watchlist_file=a.watchlist_file,asof=asof)
    try:
        summary=run_once(asof=asof,symbols=symbols,directory=a.dir,
                         batch_size=a.batch_size,max_batches=a.max_batches,
                         followups=a.followups,neon_shadow=a.neon_shadow)
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__,
                          'execution':'NONE'},ensure_ascii=False))
        return 3
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    return 0 if summary['final_ready'] else 2

if __name__=='__main__':sys.exit(main())
