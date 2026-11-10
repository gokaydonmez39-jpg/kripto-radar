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
import runner
import tracker
from private_sheet_writer import (SheetApi, HandoffBlocked, numeric, require,
                                  CANDIDATE_HEADER, SCAN_HEADER, as_cells,
                                  scan_source_proof, RUN_EVENT_LABELS,
                                  public_failure_code)

ALERT_HEADER = (
    'OLAY_ANAHTARI','ADAY_ANAHTARI','AL_ASOF_ET','SEMBOL',
    'OLAY_ASOF_ET','OLAY_KODU','ONCELIK','IEX_KAPANIS_USD',
    'ORIJINAL_STOP_USD','ORIJINAL_HEDEF_USD','SMA20','SMA50',
    'DESTEK_20','DIRENC_20','TEPE_52','TAKIP_SEANSI',
    'BIRINCIL_KANIT_URL','BILDIRIM_DURUMU','BILDIRIM_ZAMANI_TR','NOT')
EVENT_PENDING = 'EVENT_CONFIRMED_PENDING_DELIVERY_REQUEST'

# Only source-defined, constant lifecycle failure identifiers may appear in
# public GitHub logs. Unknown exception messages are never echoed.
_PUBLIC_LIFECYCLE_CODES = frozenset({
    'LIFECYCLE_ALERT_DUPLICATE_OR_INVALID',
    'LIFECYCLE_ALERT_HEADER_DRIFT',
    'LIFECYCLE_ALERT_READBACK_DUPLICATE',
    'LIFECYCLE_ALERT_READBACK_HEADER',
    'LIFECYCLE_ALERT_READBACK_MISSING_OR_CHANGED',
    'LIFECYCLE_ASOF_NOT_SESSION',
    'LIFECYCLE_ASOF_REQUIRED',
    'LIFECYCLE_BAD_SYMBOL',
    'LIFECYCLE_CONCURRENT_MODIFICATION',
    'LIFECYCLE_CURRENT_FINAL_SCAN_MISSING',
    'LIFECYCLE_DISPATCH_ASOF_OUTSIDE_SAFE_WINDOW',
    'LIFECYCLE_DUPLICATE_ID',
    'LIFECYCLE_EOD_NOT_FINAL_477',
    'LIFECYCLE_EOD_SCAN_MISSING',
    'LIFECYCLE_EVENT_CONFLICT',
    'LIFECYCLE_FUTURE_OR_UNVERIFIED_COUNT',
    'LIFECYCLE_GOOGLE_AUTH_NOT_CONFIGURED',
    'LIFECYCLE_HEADER_DRIFT',
    'LIFECYCLE_IDENTITY_CONFLICT',
    'LIFECYCLE_INCOMPLETE_ROW',
    'LIFECYCLE_INVALID_EOD_RUN_URL',
    'LIFECYCLE_INVALID_PRICE_GEOMETRY',
    'LIFECYCLE_INVALID_START_DATE',
    'LIFECYCLE_INVALID_START_SESSION',
    'LIFECYCLE_MISSING_LEVELS',
    'LIFECYCLE_MISSING_SYMBOL_BARS',
    'LIFECYCLE_NON_2R_OR_TAMPERED_LEVEL',
    'LIFECYCLE_OPEN_COUNT_OUTSIDE_RANGE',
    'LIFECYCLE_PROVIDER_RESPONSE_INVALID',
    'LIFECYCLE_READBACK_DUPLICATE_ID',
    'LIFECYCLE_READBACK_EMPTY',
    'LIFECYCLE_READBACK_FIELDS_CHANGED',
    'LIFECYCLE_READBACK_HEADER_CHANGED',
    'LIFECYCLE_READBACK_NOTIFICATION_CHANGED',
    'LIFECYCLE_READBACK_ORIGINAL_MODIFIED',
    'LIFECYCLE_READBACK_ROW_MISSING',
    'LIFECYCLE_SCAN_ASOF_DUPLICATE',
    'LIFECYCLE_SCAN_HEADER_DRIFT',
    'LIFECYCLE_SHEET_ID_NOT_VERIFIED',
    'LIFECYCLE_SOURCE_EVENT_DRIFT',
    'LIFECYCLE_SOURCE_SHA_MISMATCH',
    'LIFECYCLE_SUPPRESSED_OPENING_IDENTITY_CONFLICT',
    'LIFECYCLE_TERMINAL_BAR_NOT_UNIQUE',
    'LIFECYCLE_TERMINAL_INCONSISTENT',
    'LIFECYCLE_TOO_MANY_EPISODES',
    'LIFECYCLE_CORPORATE_ACTION_LAST_TRADE_NOT_VERIFIED',
    'LIFECYCLE_UNKNOWN_STATUS',
})


def lifecycle_public_failure_code(exc):
    """Map an exception to an allowlisted code without leaking private data."""
    shared_code = public_failure_code(exc)
    if shared_code != 'UNCLASSIFIED':
        return shared_code
    if isinstance(exc, HandoffBlocked) and str(exc) in _PUBLIC_LIFECYCLE_CODES:
        return str(exc)
    return 'UNCLASSIFIED'

OPEN_RE = re.compile(r'^AÇIK • ([0-9]{1,2})/15 SEANS$')
MAX_EPISODES = 4770
CALENDAR = 'XNAS'
# Source-anchored issuer lifecycle: 9 Nov ROKU has NO exchange daily bar.
# GNTX is a NEW issuer in the prospective scope, never a ROKU alias.
_ROKU_LAST_TRADING = '2026-11-06'
_ROKU_DELIST_EFFECTIVE = '2026-11-09'
_ROKU_FIRST_NEW_PIT = '2026-11-10'
_ROKU_NASDAQ_NOTICE = 'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-806'

VERIFIED_RUN_URL = re.compile(
    r'^https://github[.]com/gokaydonmez39-jpg/kripto-radar/actions/runs/[1-9][0-9]*$')

def verified_terminal_eod_run(scans, asof):
    """Verify unique current EOD source provenance before reserving terminal events."""
    require(isinstance(scans,list) and scans and tuple(scans[0])==SCAN_HEADER,
            'LIFECYCLE_SCAN_HEADER_DRIFT')
    rows=[r for r in scans[1:] if r and r[0]]
    require(bool(rows),'LIFECYCLE_EOD_SCAN_MISSING')
    dates=[r[0] for r in rows]
    require(len(dates)==len(set(dates)),'LIFECYCLE_SCAN_ASOF_DUPLICATE')
    latest=[r for r in rows if r[0]==asof]
    require(len(latest)==1 and dates[-1]==asof,
            'LIFECYCLE_CURRENT_FINAL_SCAN_MISSING')
    row=latest[0]
    require(len(row)>=10 and row[2:7]==['477','477','477','0','TRUE'],
            'LIFECYCLE_EOD_NOT_FINAL_477')
    url=row[8]
    require(isinstance(url,str) and VERIFIED_RUN_URL.fullmatch(url) is not None,
            'LIFECYCLE_INVALID_EOD_RUN_URL')
    proof=scan_source_proof(row[9])
    scope=runner.get_scope(
        watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),
        asof=asof)
    require(len(scope)==477 and
            proof['scopeSHA']==runner.sha_symbols(scope) and
            proof['algorithmSHA']==runner.analysis_fingerprint(),
            'LIFECYCLE_SOURCE_SHA_MISMATCH')
    src=[v[len('source_event='):] for v in str(row[9]).split(';')
         if v.startswith('source_event=')]
    require(len(src)==1 and src[0] in RUN_EVENT_LABELS and
            row[1]==RUN_EVENT_LABELS[src[0]],
            'LIFECYCLE_SOURCE_EVENT_DRIFT')
    return url


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
    # Non-market corporate termination must not query a fabricated ROKU bar.
    # It is allowed ONLY after the verified historical episode was already
    # followed through ROKU's actual final 6 Nov trading session.
    corporate=set()
    for episode in due:
        if episode['symbol']=='ROKU' and asof>=_ROKU_FIRST_NEW_PIT:
            require(episode['processed_through']==_ROKU_LAST_TRADING and
                    episode['asof_et']<=_ROKU_LAST_TRADING,
                    'LIFECYCLE_CORPORATE_ACTION_LAST_TRADE_NOT_VERIFIED')
            corporate.add(episode['id'])
    syms=sorted({e['symbol'] for e in due if e['id'] not in corporate})
    require(all(s.isascii() and s.isupper() for s in syms),'LIFECYCLE_BAD_SYMBOL')
    bars_by_symbol=read_batch(syms,asof) if syms else {}
    require(isinstance(bars_by_symbol,dict),'LIFECYCLE_PROVIDER_RESPONSE_INVALID')
    updates=[]
    for episode in due:
        if episode['id'] in corporate:
            held=episode['days_held']
            code='CORPORATE_ACTION_REVIEW'
            day=_ROKU_DELIST_EFFECTIVE
            event={
                'event_key':episode['id']+'|'+day+'|'+code+'|1',
                'episode_id':episode['id'],
                'original_asof':episode['asof_et'],
                'symbol':'ROKU','event_day':day,'event_code':code,
                'iex_close':'',  # No official 9 Nov ROKU candle; no price/fill.
                'stop':episode['stop'],'target':episode['target_2r'],
                'days_held':held,'gap':False,'source_notice':_ROKU_NASDAQ_NOTICE,
            }
            updates.append({
                'event':event,'sheet_row_index':episode['sheet_row_index'],
                'id':episode['id'],'original_row':episode['original_row'],
                'new_cells':['KAPALI • '+code+' • %d/15 SEANS'%held,
                             day,code,''],
                'terminal':True,'asof_et':asof
            })
            continue
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
        event=None
        if item['status']=='CLOSED':
            day=item['closed_date']
            observed=[b for b in bars_by_symbol[symbol]
                      if str(b.get('timestamp',''))[:10]==day]
            require(len(observed)==1,'LIFECYCLE_TERMINAL_BAR_NOT_UNIQUE')
            last=item['events'][-1]
            event={
                'event_key':episode['id']+'|'+day+'|'+item['outcome']+'|1',
                'episode_id':episode['id'],
                'original_asof':episode['asof_et'],'symbol':symbol,
                'event_day':day,'event_code':item['outcome'],
                'iex_close':observed[0]['close'],
                'stop':episode['stop'],'target':episode['target_2r'],
                'days_held':held,'gap':bool(last.get('gap_below_stop')),
            }
        updates.append({
            'event':event,
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


def plan_outbox_events(plan, alert_values, verified_run_url):
    require(isinstance(alert_values,list) and alert_values and
            tuple(alert_values[0])==ALERT_HEADER,'LIFECYCLE_ALERT_HEADER_DRIFT')
    existing={}
    for row in alert_values[1:]:
        if not row or not any(str(x) for x in row):
            continue
        require(len(row)>=18 and row[0] not in existing,
                'LIFECYCLE_ALERT_DUPLICATE_OR_INVALID')
        existing[row[0]]=list(row)
    new_rows=[]
    expected={}
    for update in plan['updates']:
        event=update['event']
        if event is None:
            continue
        # A later independently tracked observation must not send a STOP/2R
        # alert if its opening AL alert was deliberately suppressed.
        # Preserve any terminal event already in the historical ledger.
        opening_key=(event['original_asof']+'|'+event['symbol']+'|'+
                     event['original_asof']+'|AL_NEW_EPISODE|1')
        opening=existing.get(opening_key)
        if opening is not None and opening[17]=='DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT':
            require(opening[1]==event['episode_id'],
                    'LIFECYCLE_SUPPRESSED_OPENING_IDENTITY_CONFLICT')
            if event['event_key'] not in existing:
                continue
        kind=event['event_code']
        priority=('KURUMSAL_ISLEM' if kind=='CORPORATE_ACTION_REVIEW'
                  else 'KRITIK' if kind in ('STOP_TOUCHED','BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS')
                  else 'HEDEF' if kind=='TARGET_TOUCHED' else 'SURE_SONU')
        note=('Corporate action: ROKU delisted; no IEX closing bar, no '
              'theoretical exit-price or fill; independently review cash/share '
              'consideration; Nasdaq '+event['source_notice'])
             if kind=='CORPORATE_ACTION_REVIEW' else
             'Verified historical Alpaca IEX daily bar; theoretical contact only; '
             'gap_below_stop='+str(event['gap'])+'; never executable fill')
        row=[event['event_key'],event['episode_id'],event['original_asof'],
             event['symbol'],event['event_day'],kind,priority,
             str(event['iex_close']),str(event['stop']),str(event['target']),
             '','','','','',str(event['days_held'])+'/15',verified_run_url,
             EVENT_PENDING,'',note]
        old=existing.get(event['event_key'])
        if old is not None:
            require(len(old)>=20 and old[:10]==row[:10] and
                    old[15]==row[15] and
                    old[17] in (EVENT_PENDING,'ALERT_REQUESTED_NOT_DEVICE_ACK'),
                    'LIFECYCLE_EVENT_CONFLICT')
            expected[event['event_key']]=list(old)
        else:
            new_rows.append(row)
            expected[event['event_key']]=row
    return {'new_rows':new_rows,'expected':expected}


def to_batch_requests(plan, sheet_id):
    """Change only H-K. A-G original stop/target/price are NEVER written."""
    return [{'updateCells':{
        'start':{'sheetId':sheet_id,'rowIndex':u['sheet_row_index'],
                 'columnIndex':7},
        'rows':[{'values':[{'userEnteredValue':{'stringValue':str(v)}}
                            for v in u['new_cells']]}],
        'fields':'userEnteredValue'}}
        for u in plan['updates']]


def verify_outbox_readback(outbox, observed):
    require(observed and tuple(observed[0])==ALERT_HEADER,
            'LIFECYCLE_ALERT_READBACK_HEADER')
    rows=[r for r in observed[1:] if r and r[0]]
    keys=[r[0] for r in rows]
    require(len(keys)==len(set(keys)),'LIFECYCLE_ALERT_READBACK_DUPLICATE')
    keyed={r[0]:list(r) for r in rows}
    for key,original in outbox['expected'].items():
        require(key in keyed and keyed[key]==original,
                'LIFECYCLE_ALERT_READBACK_MISSING_OR_CHANGED')
    return True


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
    alert_before=api.read('UYARI_OLAYLARI','T')
    scans=api.read('TARAMA_KAYITLARI','J')
    source_url=verified_terminal_eod_run(scans,asof)
    outbox=plan_outbox_events(plan,alert_before,source_url)
    require(api.read('ADAY_GECMISI','M')==before and
            api.read('UYARI_OLAYLARI','T')==alert_before and
            api.read('TARAMA_KAYITLARI','J')==scans,
            'LIFECYCLE_CONCURRENT_MODIFICATION')
    if plan['updates']:
        require(isinstance(api.sheet_ids,dict) and
                type(api.sheet_ids.get('candidate')) is int and
                type(api.sheet_ids.get('alerts')) is int,
                'LIFECYCLE_SHEET_ID_NOT_VERIFIED')
        reqs=to_batch_requests(plan,api.sheet_ids['candidate'])
        if outbox['new_rows']:
            reqs.extend(as_cells(outbox['new_rows'],
                                 api.sheet_ids['alerts']) for _ in (0,))
        # One atomic Google batch: terminal candidate row and event outbox
        # either commit together or are both rejected by the Sheets API.
        api.request(':batchUpdate',method='POST',body={'requests':reqs})
        verify_readback(plan,api.read('ADAY_GECMISI','M'))
        verify_outbox_readback(outbox,api.read('UYARI_OLAYLARI','T'))
    return {'status':'LIFECYCLE_READBACK_PASS',
            'asof_et':asof,
            'evaluated':plan['evaluated'],'terminal_updates':plan['closed'],
            'terminal_events_reserved':len(outbox['new_rows']),
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
                          'reason_code':lifecycle_public_failure_code(exc),
                          'device_ack':False,'execution':'NONE'},sort_keys=True))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
