#!/usr/bin/env python3
"""XRAY v31: three-symbol 30-session historical SIP AUCTION presence +
AAPL last-close raw-trade UPDATE flag sample. READ-ONLY RESEARCH.

No primary market-data authority, RTH DV30 or buy/notification permission.
Vendor rows only in-process; no raw OHLCV/trades, symbols, trade IDs, prices,
volumes or credentials in saved report. No broker/trading APIs.
"""
from __future__ import annotations
import argparse, copy, datetime as dt, json, math, os, re
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from xray_v30_sip_exact30_three_canary import official, SYMBOLS, NY, UTC

BASE='https://data.alpaca.markets/v2/stocks'
SCHEMA='XRAY_V31_HISTORICAL_SIP_AUCTIONS_CORRECTION_SHADOW_V1'
MAX_AUCTION_PAGES_PER_SYMBOL=3
MAX_TRADE_PAGES=3
MAX_HTTP_PAGES=3*MAX_AUCTION_PAGES_PER_SYMBOL+MAX_TRADE_PAGES
MAX_BODY=3_000_000

class SourceFailure(Exception):pass

def need(flag,code):
    if not flag:raise SourceFailure('XRAY_V31_'+code)

def timestamp(t):
    need(type(t) is str,'TIME_FORMAT')
    try:k=dt.datetime.fromisoformat(t.replace('Z','+00:00'))
    except ValueError:raise SourceFailure('XRAY_V31_TIME_FORMAT')
    need(k.tzinfo is not None,'TIMEZONE_MISSING')
    return k.astimezone(UTC)

def fetch(path,params,key,secret,*,opener=urllib.request.urlopen,max_pages=3):
    need(bool(key and secret),'CREDENTIALS_MISSING')
    need(type(max_pages) is int and 1<=max_pages<=MAX_AUCTION_PAGES_PER_SYMBOL,'PAGE_CAP')
    tok=None; used=set(); rows=[]
    for page in range(max_pages):
        p=dict(params)
        if tok:p['page_token']=tok
        req=urllib.request.Request(BASE+path+'?'+urllib.parse.urlencode(p),headers={
          'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
          'Accept':'application/json','User-Agent':'xray-v31-auction-research/1.0'})
        with opener(req,timeout=22) as resp:
            raw=resp.read(MAX_BODY+1)
        need(len(raw)<=MAX_BODY,'RESPONSE_BYTE_LIMIT')
        j=json.loads(raw)
        need(type(j) is dict,'RESPONSE_OBJECT')
        field='trades' if path.endswith('/trades') else 'auctions'
        need(type(j.get(field)) is list,'RESPONSE_LIST')
        if 'symbol' in j:need(j['symbol']==path.split('/')[1],'SOURCE_SYMBOL_MISMATCH')
        rows.extend(j[field])
        nxt=j.get('next_page_token')
        need(nxt is None or (type(nxt) is str and 1<=len(nxt)<=2048 and nxt not in used),'PAGE_CURSOR')
        if nxt is None:return rows,page+1
        used.add(nxt);tok=nxt
    raise SourceFailure('XRAY_V31_PAGE_LIMIT_EXHAUSTED')

def assess_auctions(rows,days,close_schedule,symbol):
    need(type(rows) is list,'AUCTIONS_NOT_LIST')
    all_days=set(days); seen=set(); found=set(); six=set(); unknown=0
    for day in rows:
        need(type(day) is dict,'DAILY_AUCTION_NOT_OBJECT')
        d=day.get('d');need(type(d) is str and d in all_days and d not in seen,'AUCTION_DATE_SCOPE_OR_DUP')
        seen.add(d)
        c=day.get('c');need(type(c) is list,'CLOSE_AUCTION_MISSING_ARRAY')
        if c:found.add(d)
        for x in c:
            need(type(x) is dict and type(x.get('s')) is int and x['s']>0 and
                 type(x.get('p')) in (int,float) and math.isfinite(x['p']) and x['p']>0,
                 'AUCTION_PRICE_OR_SIZE')
            moment=timestamp(x.get('t'))
            need(abs((moment-close_schedule[d]).total_seconds())<=180,'NOT_NEAR_EXCHANGE_CLOSE')
            condition=x.get('c');need(type(condition) is str and condition,'AUCTION_CONDITION_NOT_SET')
            if condition=='6' and x.get('x')=='Q':six.add(d)
            else:unknown+=1
    return {'days_returned':len(seen),'days_with_any_close_entry':len(found),
            'days_with_Q6_close_entry':len(six),'unmapped_condition_count':unknown,
            'coverage_days':len(days),'all_official_dates_returned':len(seen)==len(days)}

def assess_trades(rows,close,*,bound_seconds=3):
    need(type(rows) is list,'TRADES_NOT_LIST')
    ids=set(); counts={'close_6':0,'afterhours_T':0,'other_condition':0,
                        'canceled':0,'incorrect':0,'corrected':0,'unknown_update':0}
    for x in rows:
        need(type(x) is dict and type(x.get('s')) is int and x['s']>0 and
             type(x.get('p')) in (int,float) and math.isfinite(x['p']) and x['p']>0,
             'TRADE_FIELDS')
        t=timestamp(x.get('t'))
        need(close-dt.timedelta(seconds=1)<=t<=close+dt.timedelta(seconds=bound_seconds),
             'TRADE_WINDOW_SCOPE')
        k=(x.get('x'),x.get('i'));need(k not in ids and type(k[1]) is int,'TRADE_ID_DUP_OR_INVALID');ids.add(k)
        c=x.get('c');need(type(c) is list and all(type(y) is str for y in c),'TRADE_CONDITIONS')
        if '6' in c and x.get('x')=='Q':counts['close_6']+=1
        elif 'T' in c:counts['afterhours_T']+=1
        else:counts['other_condition']+=1
        update=x.get('u')
        if update is not None:
            k=update if update in ('canceled','incorrect','corrected') else 'unknown_update'
            counts[k]+=1
    return {'trade_window_records':len(rows),'counts':counts,
            'all_returned_trades_checked':True}

def report(asof,auction_stats=None,trade_stats=None,status='BLOCKED'):
    auctions=auction_stats or {}
    return {'schema':SCHEMA,'asof_et':asof,'sample_size':3,'official_sessions':30,
      'source':'ALPACA_HISTORICAL_SIP_GITHUB_RUNNER_AUCTIONS',
      'auction_endpoint':'/v2/stocks/{symbol}/auctions','trade_sample_symbol_count':1,
      'auction_counts':auctions,'trade_last_close_counts':trade_stats or {},
      'status':status,'api_page_limit':MAX_HTTP_PAGES,
      'historical_closing_auction_coverage_witness':bool(auctions and all(
         x.get('days_with_Q6_close_entry')==30 for x in auctions.values())),
      'correction_full_day_or_30_sessions_proven':False,
      'complete_trade_30_session_history_proven':False,
      'exact_rth_volume_verified':False,'market_data_usage_rights_attested':False,
      'canonical_price_pass_authority':False,'mc_authority':False,'g9_pass':False,
      'r92':False,'iphone_receipt':False,'broker':False,
      'execution':'NONE','real_money':'NO-GO','unknown_never_pass':True,
      'canonical_files_mutated':False,'vendor_trades_or_ohlcv_persisted':False,
      'credentials_persisted':False}

def selftest():
    dates,sessions=official('2026-10-22')
    closes={d:v[-1]+dt.timedelta(minutes=30) for d,v in sessions.items()}
    def a(d):return {'d':d,'o':[],'c':[{'t':(closes[d]+dt.timedelta(milliseconds=30)).isoformat(),
                           'x':'Q','p':112.0,'s':100,'c':'6'}]}
    good=[a(d) for d in dates]
    positive=assess_auctions(good,dates,closes,'AAPL')
    assert positive['days_with_Q6_close_entry']==30
    close=closes[dates[-1]]
    trades=[{'t':(close+dt.timedelta(milliseconds=20)).isoformat(),'x':'Q',
              'i':101,'p':112.0,'s':200,'c':['@','6','X'],'u':'corrected'},
            {'t':(close+dt.timedelta(milliseconds=40)).isoformat(),'x':'D',
              'i':102,'p':112.0,'s':100,'c':['@','T'],'u':'canceled'}]
    z=assess_trades(trades,close)
    assert z['counts']['close_6']==1 and z['counts']['canceled']==1
    out=report('2026-10-22',{'AAPL':positive,'MSFT':positive,'NVDA':positive},z,'SHADOW_COMPLETE')
    assert out['historical_closing_auction_coverage_witness'] and not out['exact_rth_volume_verified']
    negatives=[
      lambda x:x.append(a(dates[0])),
      lambda x:x.pop(0),
      lambda x:x[0]['c'][0].update(s=1.3),
      lambda x:x[0]['c'][0].update(c='?'),
      lambda x:x[0]['c'][0].update(t='2026-10-01T21:00:00Z'),
      lambda x:x[0].update(d='2026-10-25'),
      lambda x:x[0].update(c='not_list')]
    rejected=0
    for mutate in negatives:
        x=copy.deepcopy(good);mutate(x)
        try:
            o=assess_auctions(x,dates,closes,'AAPL')
            need(o['days_with_Q6_close_entry']==30 and o['days_returned']==30,'NOT_FULL_AUCTION_30')
        except SourceFailure:rejected+=1
        else:raise AssertionError('BAD_AUCTION_ACCEPTED')
    badtrades=[lambda x:x.append(copy.deepcopy(x[0])),
               lambda x:x[0].update(i='bad'),lambda x:x[0].update(s=2.1),
               lambda x:x[0].update(t=(close+dt.timedelta(seconds=10)).isoformat())]
    for mutate in badtrades:
        x=copy.deepcopy(trades);mutate(x)
        try:assess_trades(x,close)
        except SourceFailure:rejected+=1
        else:raise AssertionError('BAD_TRADE_ACCEPTED')
    assert rejected==11
    assert MAX_HTTP_PAGES==12
    print('XRAY_V31_AUCTION_CORRECTION_OFFLINE=PASS_2_POSITIVE_11_NEGATIVE_NO_ALPHA')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--selftest',action='store_true')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.selftest:return selftest()
    if args.out is None:parser.error('Need --out')
    from source_epoch_freshness_guard import last_complete_session
    now=dt.datetime.now(UTC);asof=last_complete_session(now)
    p=Path(__file__).resolve().parent
    root=json.loads((p/'orchestrator_state.json').read_text())
    price=json.loads((p/'canonical_current_price_dv30.json').read_text())
    master=json.loads((p/'canonical_current_master_manifest.json').read_text())
    if not all(x.get('asof_et')==asof for x in (root,price,master)):
        obj=report(asof,status='BLOCKED_STALE_OR_MIXED_ASOF_NO_HTTP')
    else:
        keys=(os.getenv('XRAY_ALPACA_DATA_KEY_ID') or os.getenv('XRAY_ALPACA_API_KEY_ID') or '',
              os.getenv('XRAY_ALPACA_DATA_SECRET_KEY') or os.getenv('XRAY_ALPACA_API_SECRET_KEY') or '')
        if not all(keys):obj=report(asof,status='BLOCKED_NO_RUNNER_SECRETS')
        else:
            days,sessions=official(asof)
            closes={d:v[-1]+dt.timedelta(minutes=30) for d,v in sessions.items()}
            end=closes[asof]+dt.timedelta(minutes=5)
            if end>now-dt.timedelta(minutes=15):obj=report(asof,status='BLOCKED_SIP_DELAY_WINDOW_NO_HTTP')
            else:
                stats={};phase='AUCTIONS'
                try:
                    for sym in SYMBOLS:
                        rows,pages=fetch('/'+sym+'/auctions',{'start':days[0],'end':end.isoformat(),
                            'asof':asof,'feed':'sip','limit':1000},*keys,max_pages=MAX_AUCTION_PAGES_PER_SYMBOL)
                        stats[sym]=assess_auctions(rows,days,closes,sym)
                    phase='TRADE_LAST_SESSION'
                    trades,pages=fetch('/AAPL/trades',{'start':(closes[asof]-dt.timedelta(seconds=1)).isoformat(),
                        'end':(closes[asof]+dt.timedelta(seconds=3)).isoformat(),
                        'asof':asof,'feed':'sip','limit':10000},*keys,max_pages=MAX_TRADE_PAGES)
                    assessed=assess_trades(trades,closes[asof])
                    obj=report(asof,stats,assessed,status='RESEARCH_AUCTION_CLOSING_SAMPLE_ONLY')
                except urllib.error.HTTPError as ex:
                    code=('401_AUTH' if ex.code==401 else '403_POLICY_OR_WINDOW' if ex.code==403 else
                          '429_RATE_LIMIT' if ex.code==429 else 'HTTP_OTHER')
                    obj=report(asof,status='BLOCKED_'+phase+'_'+code)
                except (SourceFailure,OSError,TimeoutError,urllib.error.URLError,ValueError,TypeError):
                    obj=report(asof,status='BLOCKED_'+phase+'_DATA_OR_PAGINATION_UNKNOWN')
    # Do not persist symbol names or size/price from vendor.
    if obj['auction_counts']:
        agg={k:sum(x[k] for x in obj['auction_counts'].values()) for k in
             ('days_returned','days_with_any_close_entry','days_with_Q6_close_entry','unmapped_condition_count')}
        obj['auction_counts']=agg
    assert obj['canonical_price_pass_authority'] is False and obj['r92'] is False
    args.out.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
    print('XRAY_V31_AUCTION_COUNTS_ONLY='+json.dumps({k:obj[k] for k in
       ('asof_et','status','historical_closing_auction_coverage_witness',
        'correction_full_day_or_30_sessions_proven','exact_rth_volume_verified')},sort_keys=True))

if __name__=='__main__':main()