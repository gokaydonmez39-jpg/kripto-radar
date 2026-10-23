#!/usr/bin/env python3
"""XRAY v30: bounded historical SIP 3-symbol 30-session RTH presence witness.

RESEARCH ONLY; no broker, no orders, no market signal, no C4.17 promotion.
Does not persist, return, or log vendor OHLCV. Auction/corrections NOT attested.
Provider permission for unattended production / any downstream use is NOT inferred.
"""
from __future__ import annotations
import argparse, collections, copy, datetime as dt, hashlib, json, math, os, re
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
NY=ZoneInfo('America/New_York')
UTC=dt.timezone.utc
SYMBOLS=('AAPL','MSFT','NVDA')
SCHEMA='XRAY_SIP_EXACT30_THREE_SYMBOL_SHADOW_V1'
MAX_PAGES_PER_LEG=5
MAX_HTTP_REQUESTS=10
MAX_BYTES_PER_RESPONSE=4_000_000
ENDPOINT='https://data.alpaca.markets/v2/stocks/bars'

class GateError(Exception): pass

def need(pred, reason):
    if not pred: raise GateError('XRAY_V30_'+reason)

def official(asof):
    day=dt.date.fromisoformat(asof)
    start=day-dt.timedelta(days=70)
    sched=mcal.get_calendar('NASDAQ').schedule(start_date=start,end_date=day)
    need(len(sched)>=30,'CALENDAR_HAS_FWER_THAN_30')
    recent=sched.iloc[-30:]
    days=[str(d.date()) for d in recent.index]
    need(len(days)==30 and len(set(days))==30 and days[-1]==asof,'CALENDAR_ASOF_INVALID')
    sessions={}
    for (date,row) in recent.iterrows():
        open_=row['market_open'].to_pydatetime().astimezone(UTC)
        close=row['market_close'].to_pydatetime().astimezone(UTC)
        minutes=int((close-open_).total_seconds()//60)
        need(minutes>0 and minutes%30==0,'NON_30_MINUTE_SESSION')
        sessions[str(date.date())]=[open_+dt.timedelta(minutes=30*i) for i in range(minutes//30)]
    return days,sessions

def utc(t):
    need(type(t) is str,'TIMESTAMP_TYPE')
    try: x=dt.datetime.fromisoformat(t.replace('Z','+00:00'))
    except ValueError: raise GateError('XRAY_V30_TIMESTAMP_INVALID')
    need(x.tzinfo is not None,'TIMESTAMP_UNZONED')
    return x.astimezone(UTC)

def valid_bar(row):
    if type(row) is not dict: return False
    try:
        vals=[row[k] for k in ('o','h','l','c')]
        vol=row['v']
    except KeyError:return False
    if not (all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in vals)
        and type(vol) is int and vol>0): return False
    op,hi,lo,cl=vals
    return lo<=min(op,cl)<=max(op,cl)<=hi

def summarize(days,sessions,daily,intraday,*,source_is_sip=True):
    need(source_is_sip is True,'FEED_NOT_SIP')
    need(type(daily) is dict and type(intraday) is dict and
         set(daily).issubset(SYMBOLS) and set(intraday).issubset(SYMBOLS),'SCOPE_INVALID')
    daily_counts={}; slots_counts={}; invalid_counts={}; outside_counts={}
    all_30=0; all_intraday=0
    slots={d:set(sessions[d]) for d in days}
    expected=sum(map(len,slots.values()))
    for sym in SYMBOLS:
        by_date=collections.Counter(); by_slot=collections.Counter(); bad=0; outside=0
        for bar in daily.get(sym,[]):
            need(type(bar) is dict,'DAILY_ROW_NOT_OBJECT')
            day=str(utc(bar['t']).astimezone(NY).date())
            if day not in slots: continue
            by_date[day]+=1
            if not valid_bar(bar):bad+=1
        for bar in intraday.get(sym,[]):
            need(type(bar) is dict,'RTH_ROW_NOT_OBJECT')
            stamp=utc(bar['t'])
            day=str(stamp.astimezone(NY).date())
            if day not in slots or stamp not in slots[day]:
                outside+=1
                continue
            by_slot[(day,stamp)]+=1
            if not valid_bar(bar):bad+=1
        all_d=all(by_date[d]==1 for d in days)
        all_i=all(by_slot[(d,t)]==1 for d in days for t in sessions[d])
        all_30+=int(all_d and bad==0)
        all_intraday+=int(all_i and bad==0)
        daily_counts[sym]=sum(by_date[d]==1 for d in days)
        slots_counts[sym]=sum(by_slot[(d,t)]==1 for d in days for t in sessions[d])
        invalid_counts[sym]=bad+sum(max(0,by_date[d]-1) for d in days)+sum(
            max(0,by_slot[(d,t)]-1) for d in days for t in sessions[d])
        outside_counts[sym]=outside
    return {'asof_et':days[-1], 'official_sessions':30,
            'expected_halfhour_slots_per_symbol':expected,
            'daily_complete_symbol_count':all_30,
            'rth_30min_complete_symbol_count':all_intraday,
            'per_symbol_daily_presence':daily_counts,
            'per_symbol_rth_30m_presence':slots_counts,
            'per_symbol_integrity_issues':invalid_counts,
            'outside_rth_vendor_bars_excluded':outside_counts}

def build_report(measured,*,pages,request_status):
    return {'schema':SCHEMA,'status':request_status,'asof_et':measured.get('asof_et'),
      'research_only':True,'source':'ALPACA_HISTORICAL_SIP_GITHUB_RUNNER',
      'sample_size':3,'official_sessions':measured.get('official_sessions',0),
      'expected_halfhour_slots_per_symbol':measured.get('expected_halfhour_slots_per_symbol',0),
      'daily_complete_symbol_count':measured.get('daily_complete_symbol_count',0),
      'rth_30min_complete_symbol_count':measured.get('rth_30min_complete_symbol_count',0),
      'daily_presence_total':sum(measured.get('per_symbol_daily_presence',{}).values()),
      'rth_30m_presence_total':sum(measured.get('per_symbol_rth_30m_presence',{}).values()),
      'integrity_issue_total':sum(measured.get('per_symbol_integrity_issues',{}).values()),
      'outside_rth_vendor_bars_excluded_total':sum(measured.get('outside_rth_vendor_bars_excluded',{}).values()),
      'page_requests':pages,'max_page_requests':MAX_HTTP_REQUESTS,
      'feed_sip_selected':True,'adjustment_raw_selected':True,
      'closing_auction_and_trade_corrections_attested':False,
      'exact_daily_RTH_integer_volume_attested':False,
      'full_c417_price_dv30_authority':False,'market_data_usage_rights_attested':False,
      'canonical_files_changed':False,'history260_52_attested':False,
      'g9_pass':False,'registered_r92':False,'iphone_receipt_attested':False,
      'execution':'NONE','real_money':'NO-GO','unknown_never_pass':True,
      'no_vendor_ohlcv_persisted':True,'no_credentials_persisted':True}

def pages(symbols,timeframe,start,end,asof,key,secret):
    need(bool(key and secret),'NO_RUNNER_CREDENTIALS')
    base={'symbols':','.join(symbols),'timeframe':timeframe,'start':start,
          'end':end,'asof':asof,'feed':'sip','adjustment':'raw',
          'sort':'asc','limit':10000}
    all_={x:[] for x in symbols};token=None;seen=set()
    for i in range(MAX_PAGES_PER_LEG):
        q=dict(base)
        if token is not None:q['page_token']=token
        req=urllib.request.Request(ENDPOINT+'?'+urllib.parse.urlencode(q),headers={
            'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
            'Accept':'application/json','User-Agent':'xray-personal-exact30-three-canary/1.0'})
        with urllib.request.urlopen(req,timeout=30) as resp:
            raw=resp.read(MAX_BYTES_PER_RESPONSE+1)
        need(len(raw)<=MAX_BYTES_PER_RESPONSE,'VENDOR_BODY_TOO_LARGE')
        body=json.loads(raw)
        need(type(body) is dict and type(body.get('bars')) is dict,'VENDOR_SCHEMA_INVALID')
        need(set(body['bars']).issubset(all_),'VENDOR_FOREIGN_SYMBOL')
        nrows=0
        for sym,bars in body['bars'].items():
            need(type(bars) is list,'VENDOR_BARS_NOT_LIST')
            for b in bars:
                need(type(b) is dict and type(b.get('t')) is str,'VENDOR_BAR_INVALID')
                k=(sym,b['t']);need(k not in seen,'VENDOR_DUPLICATE_BAR_TIMESTAMP')
                seen.add(k); nrows+=1
            all_[sym].extend(bars)
        nxt=body.get('next_page_token')
        if nxt is None: return all_,i+1
        need(type(nxt) is str and len(nxt)<2000 and nxt and nxt!=token,
             'CURSOR_INVALID')
        need(nrows>0,'PAGE_NO_PROGRESS')
        token=nxt
    raise GateError('XRAY_V30_PAGE_BUDGET_EXHAUSTED')

def run(root, master, price, *,asof,key,secret,now):
    need(type(now) is dt.datetime and now.tzinfo is not None,'CURRENT_TIME_INVALID')
    need(root.get('asof_et')==master.get('asof_et')==price.get('asof_et')==asof,
         'CANONICAL_EPOCH_MISMATCH')
    need(all(v.get('execution')=='NONE' and v.get('real_money')=='NO-GO'
             for v in (root,master,price)),'EXECUTION_POLICY_INVALID')
    need(master.get('unknown_never_pass') is True and
         price.get('unknown_never_pass') is True,'UNKNOWN_POLICY_INVALID')
    need(all(s in price.get('unknown_symbols',[]) for s in SYMBOLS),'EXACT_UNKNOWN_SCOPE_INVALID')
    days,sessions=official(asof)
    need(price.get('expected30')==days,'EXPECTED30_CANONICAL_DATES_DIFFER')
    need((now.astimezone(UTC)-max(s[-1] for s in sessions.values()))>=dt.timedelta(minutes=46),
         'SIP_15MIN_DELAY_NOT_MATURE')
    # Caller is restricted by actual canonical epoch, not an arbitrary stale ASOF.
    from source_epoch_freshness_guard import last_complete_session
    need(last_complete_session(now)==asof,'STALE_CURRENT_SOURCE_ASOF')
    if not key or not secret:
        return build_report({'asof_et':asof,'official_sessions':30,
            'expected_halfhour_slots_per_symbol':sum(map(len,sessions.values()))},
            pages=0,request_status='RUNNER_CREDENTIALS_NOT_CONFIGURED')
    start=dt.datetime.fromisoformat(days[0]+'T00:00:00').replace(tzinfo=NY)
    end=dt.datetime.fromisoformat((dt.date.fromisoformat(asof)+dt.timedelta(days=1)).isoformat()+'T00:00:00').replace(tzinfo=NY)
    try:
        ds,np1=pages(SYMBOLS,'1Day',start.astimezone(UTC).isoformat(),
                      end.astimezone(UTC).isoformat(),asof,key,secret)
        first=min(s[0] for s in sessions.values())
        last=max(s[-1] for s in sessions.values())+dt.timedelta(minutes=30)
        ins,np2=pages(SYMBOLS,'30Min',first.isoformat(),last.isoformat(),asof,key,secret)
        result=summarize(days,sessions,ds,ins)
        complete=result['daily_complete_symbol_count']==3 and result['rth_30min_complete_symbol_count']==3
        return build_report(result,pages=np1+np2,
          request_status='EXACT30_THIRTEEN_SLOTS_PER_SESSION_SHADOW_ONLY' if complete
                else 'EXACT30_MISSING_OR_INTEGRITY_UNKNOWN_SHADOW')
    except urllib.error.HTTPError as ex:
        status='RUNNER_SIP_HTTP_AUTH_DENIED' if ex.code in (401,403) else (
               'RUNNER_SIP_RATE_LIMITED' if ex.code==429 else 'RUNNER_SIP_HTTP_UNKNOWN')
    except (urllib.error.URLError,GateError,OSError,TimeoutError,ValueError,TypeError,json.JSONDecodeError):
        status='RUNNER_SIP_TRANSPORT_OR_PROVENANCE_UNKNOWN'
    return build_report({'asof_et':asof,'official_sessions':30,
        'expected_halfhour_slots_per_symbol':sum(map(len,sessions.values()))},
        pages=0,request_status=status)

def selftest():
    import copy
    days,sessions=official('2026-10-22')
    assert len(days)==30 and days[0]=='2026-09-11'
    assert all(len(v)==13 for v in sessions.values())
    def bar(t):return {'t':t.isoformat(),'o':10,'h':11,'l':9,'c':10.5,'v':1100}
    ds={s:[bar(dt.datetime.fromisoformat(d+'T04:00:00+00:00')) for d in days] for s in SYMBOLS}
    # Sep timezone has EDT UTC offset -4 for 2026 dates in fixture.
    ins={s:[bar(t) for d in days for t in sessions[d]] for s in SYMBOLS}
    ans=summarize(days,sessions,ds,ins)
    assert ans['daily_complete_symbol_count']==ans['rth_30min_complete_symbol_count']==3
    assert ans['expected_halfhour_slots_per_symbol']==390
    n=1
    mut=[]
    def attempt(change):
        nonlocal n
        d,i=copy.deepcopy(ds),copy.deepcopy(ins)
        change(d,i)
        z=summarize(days,sessions,d,i)
        assert z['daily_complete_symbol_count']!=3 or z['rth_30min_complete_symbol_count']!=3,z
        n+=1
    attempt(lambda d,i: d['AAPL'].pop())
    attempt(lambda d,i: i['NVDA'].pop())
    attempt(lambda d,i: i['NVDA'].append(copy.deepcopy(i['NVDA'][0])))
    attempt(lambda d,i: d['MSFT'][1].update(v=1.3))
    attempt(lambda d,i: i['AAPL'][14].update(v=0))
    attempt(lambda d,i: i['MSFT'][0].update(h=-1))
    attempt(lambda d,i: i['AAPL'][20].update(t='2026-10-01T09:30:00Z'))
    try:summarize(days,sessions,ds,ins,source_is_sip=False)
    except GateError:n+=1
    else:raise AssertionError('IEX_FALSE_SIP_ACCEPTED')
    try:official('2026-10-24')
    except GateError:n+=1
    else:raise AssertionError('SATURDAY_ACCEPTED')
    proof=build_report(ans,pages=2,request_status='EXACT30_THIRTEEN_SLOTS_PER_SESSION_SHADOW_ONLY')
    assert proof['full_c417_price_dv30_authority'] is False and proof['registered_r92'] is False
    assert proof['closing_auction_and_trade_corrections_attested'] is False
    assert all(k not in proof for k in ('bars','ohlcv','quotes','prices','volumes','credentials'))
    print('XRAY_V30_THREE_30_SESSION_OFFLINE_TESTS=PASS_'+str(n)+'_CASES_NO_ALPHA')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');p.add_argument('--out',type=Path);arg=p.parse_args()
    if arg.selftest:selftest();raise SystemExit
    if not arg.out:p.error('--out required')
    now=dt.datetime.now(UTC)
    root=json.loads((ROOT/'orchestrator_state.json').read_text())
    master=json.loads((ROOT/'canonical_current_master_manifest.json').read_text())
    price=json.loads((ROOT/'canonical_current_price_dv30.json').read_text())
    asof=root.get('asof_et')
    creds=(os.getenv('XRAY_ALPACA_DATA_KEY_ID') or os.getenv('XRAY_ALPACA_API_KEY_ID') or '',
        os.getenv('XRAY_ALPACA_DATA_SECRET_KEY') or os.getenv('XRAY_ALPACA_API_SECRET_KEY') or '')
    try: report=run(root,master,price,asof=asof,key=creds[0],secret=creds[1],now=now)
    except (GateError,ValueError,KeyError,TypeError):
        report=build_report({'asof_et':asof},pages=0,request_status='CANONICAL_ASOF_OR_SCOPE_BLOCKED_NO_REQUEST')
    arg.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('XRAY_V30_BOUNDED_THREE_30_SESSION_COUNTS='+json.dumps(report,sort_keys=True))