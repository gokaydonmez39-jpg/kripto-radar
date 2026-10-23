#!/usr/bin/env python3
"""Private technical swing signal journal, with no trading/execution interfaces.

Entries are hypothetical close-reference research signals, not filled trades.
Each exit decision starts at the NEXT session to avoid look-ahead bias.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import engine
from runner import dump_atomic

JOURNAL_SCHEMA='XRAY_PERSONAL_SWING_JOURNAL_V1'


def base_journal():
    return {'schema':JOURNAL_SCHEMA,'signals':{},'alerts_prepared':{},
            'metadata':{'execution':'NONE','broker':False,'orders':False}}


def load(path):
    p=Path(path)
    x=json.loads(p.read_text(encoding='utf-8')) if p.exists() else base_journal()
    if x.get('schema')!=JOURNAL_SCHEMA or not isinstance(x.get('signals'),dict):
        raise ValueError('INVALID_JOURNAL')
    return x


def validate_snapshot(snap):
    if (snap.get('schema')!='XRAY_PERSONAL_SWING_V3' or
        snap.get('coverage_complete') is not True or snap.get('partial_scan') is not False or
        snap.get('valid_data_coverage_complete') is not True or
        snap.get('new_signal_publishable') is not True or
        snap.get('requested_symbols')!=snap.get('processed_symbols') or
        snap.get('requested_symbols')!=snap.get('counts',{}).get('START') or
        snap.get('not_broker') is not True or snap.get('orders_sent')!=0):
        raise ValueError('PARTIAL_OR_UNSAFE_SCAN_NO_SIGNAL_JOURNAL')
    symbols=[r.get('symbol') for r in snap['rows']]
    if len(symbols)!=len(set(symbols)) or len(symbols)!=snap['requested_symbols']:
        raise ValueError('DUPLICATE_OR_INCOMPLETE_SCAN_SCOPE')
    if any(r.get('decision') not in ('AL','IZLE','ELE') or r.get('asof_et')!=snap['asof_et'] for r in snap['rows']):
        raise ValueError('UNQUALIFIED_OR_MIXED_EPOCH_ROWS')


def append_signals(snap,journal):
    validate_snapshot(snap)
    asof=snap['asof_et']; created=[]
    for row in snap['rows']:
        if row['decision']!='AL':continue
        if row.get('asof_et')!=asof:raise ValueError('MIXED_EPOCH_SIGNAL')
        key=asof+'|'+row['symbol']
        if key in journal['signals']:continue
        for f in ('close','atr14','indicative_stop','indicative_target_2r'):
            if not isinstance(row.get(f),(float,int)) or row[f]<=0:
                raise ValueError('INVALID_SIGNAL_LEVEL_'+f)
        journal['signals'][key]={
            'id':key,'symbol':row['symbol'],'asof_et':asof,
            'price_source':'IEX_EOD_SINGLE_EXCHANGE','kind':'TECHNICAL_AL_CANDIDATE_ONLY',
            'reference_close':row['close'],'stop':row['indicative_stop'],
            'target_2r':row['indicative_target_2r'],
            'atr14':row['atr14'],'status':'OPEN','processed_through':asof,
            'outcome':None,'days_held':0,'events':[],
            'execution':'NONE','filled':False}
        journal['alerts_prepared'][key]={
            'kind':'NEW_TECHNICAL_AL_CANDIDATE','asof_et':asof,'symbol':row['symbol'],
            'status':'PREPARED_NOT_DELIVERED','delivery_ack':False}
        created.append(key)
    return created


def track_symbol(signal,bars,asof,expiry_sessions=15):
    """Consecutive-session, no-look-ahead, OHLC-only shadow follow-up.

    Missing intermediate completed sessions must not silently advance stop/target.
    A contiguous validated prefix may advance; an observed later bar after a gap
    causes an explicit failure without changing the original signal object.
    """
    if signal['status']!='OPEN':return signal
    import copy
    import math
    import exchange_calendars as ec
    start=signal['asof_et']; done=signal.get('processed_through',start)
    existing={}
    for bar in bars:
        day=str(bar.get('timestamp',''))[:10]
        if not (start<day<=asof and day>done):continue
        if day in existing:raise ValueError('DUPLICATE_FOLLOWUP_BAR')
        vals=[bar.get(z) for z in ('open','high','low','close','volume')]
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in vals):
            raise ValueError('INVALID_FOLLOWUP_OHLCV')
        if not bar['low']<=min(bar['open'],bar['close']) or not max(bar['open'],bar['close'])<=bar['high']:
            raise ValueError('INVALID_FOLLOWUP_BAR_RANGE')
        existing[day]=bar
    ordered=sorted(existing)
    if ordered:
        cal=ec.get_calendar('XNAS')
        from datetime import date,timedelta
        expected=[str(x.date()) for x in cal.sessions_in_range((date.fromisoformat(done)+timedelta(days=1)).isoformat(),ordered[-1])]
        if ordered!=expected:raise ValueError('FOLLOWUP_MISSING_INTERMEDIATE_SESSION')
    draft=copy.deepcopy(signal)
    for day in ordered:
        bar=existing[day]
        hit_stop=bar['low']<=draft['stop']
        hit_target=bar['high']>=draft['target_2r']
        draft['days_held']+=1
        draft['processed_through']=day
        event={'date':day,'stop_hit':hit_stop,'target_hit':hit_target,
               'gap_below_stop':bar['open']<draft['stop'],
               'no_intraday_path_or_fill_proof':True}
        if hit_stop and hit_target:
            draft.update(status='CLOSED',outcome='BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS',closed_date=day)
            event['conservative_order']='STOP_FIRST_AMBIGUOUS'
        elif hit_stop:
            draft.update(status='CLOSED',outcome='STOP_TOUCHED',closed_date=day)
        elif hit_target:
            draft.update(status='CLOSED',outcome='TARGET_TOUCHED',closed_date=day)
        elif draft['days_held']>=expiry_sessions:
            draft.update(status='CLOSED',outcome='TIME_EXIT_AT_CLOSE',closed_date=day,exit_reference_close=bar['close'])
        draft['events'].append(event)
        if draft['status']=='CLOSED':
            shadow_exit=(draft['stop'] if hit_stop else draft['target_2r'] if hit_target else bar['close'])
            draft['hypothetical_result_pct']=round(100*(shadow_exit/draft['reference_close']-1),3)
            draft['result_is_hypothetical_not_executable_fill']=True
            break
    signal.clear();signal.update(draft)
    return signal

def update_followups(journal,asof,read_batch):
    """Only scan OPEN historical signals; on failed fetch, leave them OPEN/UNKNOWN."""
    changes=[]; errors=[]
    for key,signal in list(journal['signals'].items()):
        if signal['status']!='OPEN' or signal['asof_et']>=asof:continue
        try:
            bars=read_batch([signal['symbol']],asof)
            if signal['symbol'] not in bars:raise ValueError('SYMBOL_MISSING')
            old=signal['status']
            track_symbol(signal,bars[signal['symbol']],asof)
            if old!=signal['status']:
                alert_id=key+'|'+signal['outcome']
                journal['alerts_prepared'].setdefault(alert_id,{
                    'kind':'FOLLOWUP','signal_id':key,'symbol':signal['symbol'],
                    'date':signal['closed_date'],'status':'PREPARED_NOT_DELIVERED',
                    'delivery_ack':False,'outcome':signal['outcome']})
                changes.append(alert_id)
        except Exception as ex:
            errors.append({'signal_id':key,'type':type(ex).__name__,'reason':str(ex)[:120]})
    return changes,errors


def process_snapshot(snapshot_path,journal_path,*,fetch_followups=False):
    snap=json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    validate_snapshot(snap)
    journal=load(journal_path)
    made=append_signals(snap,journal)
    changes,errors=update_followups(journal,snap['asof_et'],engine.live_read) if fetch_followups else ([],[])
    # Visible diagnostic only: incomplete follow-up never becomes a closed trade.
    journal['followup_errors']=errors
    journal['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    dump_atomic(journal_path,journal)
    return {'new_signals':made,'closed_signals':changes,'followup_errors':errors,
            'signal_count':len(journal['signals']), 'prepared_not_delivered_count':sum(
                x.get('status')=='PREPARED_NOT_DELIVERED' for x in journal['alerts_prepared'].values())}


if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument('snapshot');a.add_argument('--journal',default='private-data/journal.json')
    a.add_argument('--fetch-followups',action='store_true')
    z=a.parse_args()
    print(json.dumps(process_snapshot(z.snapshot,z.journal,fetch_followups=z.fetch_followups),ensure_ascii=False))
