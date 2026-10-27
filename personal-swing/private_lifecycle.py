#!/usr/bin/env python3
"""Independent read-only-IEX follow-up of immutable private NASDAQ episodes.

Google Sheets is the durable authority. This job never creates buy/sell orders,
never sends a notification, and never changes an episode's reference/stop/target.
The existing single ChatGPT task remains the event-notification coordinator.
"""
import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
import re

import exchange_calendars as ec
import daily_job
import engine
import tracker
from private_sheet_writer import SheetApi, HandoffBlocked, numeric, require, CANDIDATE_HEADER

OPEN_RE = re.compile(r'^AÇIK • ([0-9]{1,2})/15 SEANS$')
MAX_EPISODES = 4770
CALENDAR = 'XNAS'


def decode_open_episodes(values, asof):
    """Validate all identities before any API request or private mutation."""
    require(isinstance(values,list) and values and
            tuple(values[0])==CANDIDATE_HEADER,'LIFECYCLE_HEADER_DRIFT')
    cal=ec.get_calendar(CALENDAR)
    ids=set()
    decoded=[]
    for offset, row in enumerate(values[1:],start=1):
        if not row or not any(str(v) for v in row):
            continue
        require(len(row)>=8 and len(row)>=3,'LIFECYCLE_INCOMPLETE_ROW')
        key=str(row[0])
        require(key not in ids,'LIFECYCLE_DUPLICATE_ID')
        ids.add(key)
        require(len(ids)<=MAX_EPISODES,'LIFECYCLE_TOO_MANY_EPISODES')
        asof_signal,sep,symbol=key.partition('|')
        require(bool(sep) and symbol and symbol.isascii() and
                symbol.isupper() and key==str(row[1])+'|'+str(row[2]),
                'LIFECYCLE_IDENTITY_CONFLICT')
        try:
            start=date.fromisoformat(asof_signal).isoformat()
            require(cal.is_session(start),'LIFECYCLE_INVALID_START_SESSION')
        except (ValueError,TypeError,OverflowError):
            raise HandoffBlocked('LIFECYCLE_INVALID_START_DATE') from None
        raw_status=str(row[7])
        match=OPEN_RE.fullmatch(raw_status)
        if not match:
            require(raw_status.startswith('KAPALI'),
                    'LIFECYCLE_UNKNOWN_STATUS')
            continue
        held=int(match.group(1))
        require(0<=held<15,'LIFECYCLE_OPEN_COUNT_OUTSIDE_RANGE')
        processed=cal.session_offset(cal.date_to_session(start),held).date().isoformat()
        require(start<=processed<=asof,'LIFECYCLE_FUTURE_OR_UNVERIFIED_COUNT')
        require(len(row)>=7,'LIFECYCLE_MISSING_LEVELS')
        close=numeric(row[4]);stop=numeric(row[5]);target=numeric(row[6])
        require(all(math.isfinite(v) and v>0 for v in (close,stop,target)) and
                0<stop<close<target,'LIFECYCLE_INVALID_PRICE_GEOMETRY')
        # Prices are historical precision-rounded sheet values. Preserve them.
        require(abs(target-(close+2*(close-stop)))<=0.025,
                'LIFECYCLE_NON_2R_OR_TAMPERED_LEVEL')
        decoded.append({
            'sheet_row_index':offset,'id':key,'symbol':symbol,
            'asof_et':start,'processed_through':processed,'days_held':held,
            'reference_close':close,'stop':stop,'target_2r':target,
            'status':'OPEN','events':[],'outcome':None,
            'original_row':list(row)
        })
    return decoded


def build_updates(values, asof, read_batch):
    """Pure plan: no writes, all symbol data fetched once, no partial advance."""
    require(isinstance(asof,str),'LIFECYCLE_ASOF_REQUIRED')
    cal=ec.get_calendar(CALENDAR)
    require(cal.is_session(asof),'LIFECYCLE_ASOF_NOT_SESSION')
    episode_list=decode_open_episodes(values,asof)
    due=[e for e in episode_list if e['processed_through']<asof]
    if not due:
        return {'updates':[],'total_open':len(episode_list),
                'evaluated':0,'closed':0,'asof_et':asof}
    syms=sorted({e['symbol'] for e in due})
    require(all(s.isascii() and s.isupper() for s in syms),'LIFECYCLE_BAD_SYMBOL')
    bars_by_symbol=read_batch(syms,asof)
    require(isinstance(bars_by_symbol,dict),'LIFECYCLE_PROVIDER_RESPONSE_INVALID')
    updates=[]
    for episode in due:
        symbol=episode['symbol']
        require(symbol in bars_by_symbol and isinstance(bars_by_symbol[symbol],list),
                'LIFECYCLE_MISSING_SYMBOL_BARS')
        item=dict(episode)
        # Feynman/Popper: tracker validates daily OHLCV, every consecutive
        # XNAS session, same-day dual-touch ambiguity and gap semantics.
        tracker.track_symbol(item,bars_by_symbol[symbol],asof,expiry_sessions=15)
        held=item['days_held']
        if item['status']=='OPEN':
            status='AÇIK • %d/15 SEANS'%held
            cells=[status,
                   episode['original_row'][8] if len(episode['original_row'])>8 else '',
                   episode['original_row'][9] if len(episode['original_row'])>9 else '',
                   episode['original_row'][10] if len(episode['original_row'])>10 else '']
        else:
            require(item['status']=='CLOSED' and 'closed_date' in item,
                    'LIFECYCLE_TERMINAL_INCONSISTENT')
            status='KAPALI • '+item['outcome']+' • %d/15 SEANS'%held
            cells=[status,item['closed_date'],item['outcome'],
                   str(item['hypothetical_result_pct']).replace('.',',')]
        updates.append({
            'sheet_row_index':episode['sheet_row_index'],
            'id':episode['id'],
            'original_row':episode['original_row'],
            'new_cells':cells,
            'terminal':item['status']=='CLOSED',
            'asof_et':asof
        })
    return {'updates':updates,'total_open':len(episode_list),
            'evaluated':len(due),'closed':sum(int(u['terminal']) for u in updates),
            'asof_et':asof}


def to_batch_requests(plan, sheet_id):
    """Change only H-K. A-G original stop/target/price are NEVER written."""
    return [{'updateCells':{
        'start':{'sheetId':sheet_id,'rowIndex':u['sheet_row_index'],
                 'columnIndex':7},
        'rows':[{'values':[{'userEnteredValue':{'stringValue':str(v)}}
                            for v in u['new_cells']]}],
        'fields':'userEnteredValue'}}
        for u in plan['updates']]


def verify_readback(plan, after):
    require(isinstance(after,list) and after,'LIFECYCLE_READBACK_EMPTY')
    require(tuple(after[0])==CANDIDATE_HEADER,'LIFECYCLE_READBACK_HEADER_CHANGED')
    keys=[r[0] for r in after[1:] if r and r[0]]
    require(len(keys)==len(set(keys)),'LIFECYCLE_READBACK_DUPLICATE_ID')
    for u in plan['updates']:
        index=u['sheet_row_index']
        require(index<len(after),'LIFECYCLE_READBACK_ROW_MISSING')
        current=list(after[index])
        original=u['original_row']
        require(len(current)>=11 and current[:7]==original[:7] and
                current[0]==u['id'],'LIFECYCLE_READBACK_ORIGINAL_MODIFIED')
        require(current[7:11]==u['new_cells'],
                'LIFECYCLE_READBACK_FIELDS_CHANGED')
        # Notification state must not be changed by the GitHub updater.
        if len(original)>11:
            require(len(current)>11 and current[11]==original[11],
                    'LIFECYCLE_READBACK_NOTIFICATION_CHANGED')
    return True


def synchronize(api, asof, read_batch):
    api.check_metadata()
    before=api.read('ADAY_GECMISI','M')
    plan=build_updates(before,asof,read_batch)
    require(api.read('ADAY_GECMISI','M')==before,
            'LIFECYCLE_CONCURRENT_MODIFICATION')
    if plan['updates']:
        require(isinstance(api.sheet_ids,dict) and
                type(api.sheet_ids.get('candidate')) is int,
                'LIFECYCLE_SHEET_ID_NOT_VERIFIED')
        request={'requests':to_batch_requests(plan,api.sheet_ids['candidate'])}
        api.request(':batchUpdate',method='POST',body=request)
        verify_readback(plan,api.read('ADAY_GECMISI','M'))
    return {'status':'LIFECYCLE_READBACK_PASS',
            'asof_et':asof,
            'evaluated':plan['evaluated'],'terminal_updates':plan['closed'],
            'open_episodes_before':plan['total_open'],
            'device_ack':False,
            'notification_delivery':'NOT_ATTEMPTED_BY_GITHUB'}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--asof',default='')
    args=parser.parse_args(argv)
    try:
        # Public workflow runs before US close may not process the current day.
        eligible=daily_job.current_completed_session()
        if eligible is None:
            print(json.dumps({'status':'LIFECYCLE_NO_COMPLETED_SESSION',
                              'market_data_called':False,'execution':'NONE'}))
            return 0
        require(not args.asof or args.asof==eligible,
                'LIFECYCLE_DISPATCH_ASOF_OUTSIDE_SAFE_WINDOW')
        credential=os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON','')
        require(bool(credential),'LIFECYCLE_GOOGLE_AUTH_NOT_CONFIGURED')
        api=SheetApi(credential)
        result=synchronize(api,eligible,engine.live_read)
        # Aggregate safe data only. Never print symbol IDs or reference levels.
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'LIFECYCLE_BLOCKED',
                          'reason_type':type(exc).__name__,
                          'device_ack':False,'execution':'NONE'},sort_keys=True))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
