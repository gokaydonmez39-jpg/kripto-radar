#!/usr/bin/env python3
"""Bounded AAON 2026-10-12 SIP bar-reconciliation feasibility pilot.

No full-universe fetch, new cron, canonical promotion or vendor values saved.
Research-only: hourly/half-hour volume identity and close auction sample.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import urllib.request
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

NY=ZoneInfo('America/New_York')
UTC=dt.timezone.utc
SYMBOL='AAON'
ASOF='2026-10-12'
MAX_CALLS=4
SCHEMA='XRAY_HOURLY_30MIN_RTH_CLOSE_AUCTION_PILOT_V1'


def require(ok, code):
    if not ok: raise ValueError('XRAY_RTH_PILOT_'+code)


def day_hour_key(row):
    require(type(row) is dict and type(row.get('t')) is str,'TIMESTAMP')
    t=dt.datetime.fromisoformat(row['t'].replace('Z','+00:00'))
    require(t.tzinfo is not None,'TIMEZONE')
    return t.astimezone(NY).strftime('%Y-%m-%d %H:%M')


def volume(row):
    x=row.get('v')
    require(type(x) is int and x>0,'VOLUME_NOT_INTEGRAL_POSITIVE')
    return x


def index_bars(rows):
    require(type(rows) is list,'BAR_LIST')
    result={}
    for x in rows:
        k=day_hour_key(x)
        require(k not in result,'DUPLICATE_BAR')
        result[k]=volume(x)
    return result


def summarize(daily,hourly,halfhour,trades,*,official_close_utc):
    require(len(daily)==1,'DAILY_BAR_COUNT')
    day=day_hour_key(daily[0])
    require(day.startswith(ASOF),'ASOF_MISMATCH')
    dv=volume(daily[0])
    h=index_bars(hourly)
    hh=index_bars(halfhour)
    require(all(x.startswith(ASOF) for x in [*h,*hh]),'MIXED_SESSION')
    # Each 1Hour bar must equal the sum of the two same-clock 30Min bars.
    groups={}
    for k,v in hh.items():
        stamp=dt.datetime.strptime(k,'%Y-%m-%d %H:%M')
        groups[stamp.replace(minute=0).strftime('%Y-%m-%d %H:%M')]=groups.get(
            stamp.replace(minute=0).strftime('%Y-%m-%d %H:%M'),0)+v
    full_day_consistent=(sum(h.values())==dv and groups==h)
    regular_prefix=ASOF+' '
    mandatory=[regular_prefix+f'{hour:02d}:00' for hour in range(10,16)]
    opening=regular_prefix+'09:30'
    regular_bar_coverage=(opening in hh and all(k in h for k in mandatory))
    # All validated timestamps at the close must have recognized sale conditions.
    close=official_close_utc
    require(type(trades) is list and trades,'NO_CLOSING_SAMPLE')
    categories={'AUCTION_6':0,'EXTENDED_T':0,'OFFICIAL_M':0}
    auction_shares=0
    auction_px=None
    seen=set()
    for t in trades:
        require(type(t) is dict,'TRADE_SHAPE')
        stamp=dt.datetime.fromisoformat(str(t.get('t','')).replace('Z','+00:00'))
        require(stamp.tzinfo is not None,'TRADE_CLOCK')
        when=stamp.astimezone(UTC)
        require(close<=when<close+dt.timedelta(seconds=4),'TRADE_TIME_OUTSIDE')
        cond=t.get('c')
        require(type(cond) is list and all(type(s) is str for s in cond),'CONDITIONS')
        flags=set(cond)
        ident=(t.get('x'),t.get('i'))
        require(type(ident[1]) is int and ident not in seen,'DUPLICATE_ID')
        seen.add(ident)
        v=t.get('s')
        require(type(v) is int and v>0,'TRADE_SIZE')
        if '6' in flags:
            require(t.get('x')=='Q' and flags.issubset({'@','6','X','F'}),'AUCTION_SEMANTICS')
            categories['AUCTION_6']+=1
            auction_shares+=v
            auction_px=t.get('p')
        elif 'T' in flags:
            require(flags.issubset({'@','T','I','F'}),'EXTENDED_SEMANTICS')
            categories['EXTENDED_T']+=1
        elif 'M' in flags:
            require(flags.issubset({'@','M','I'}),'OFFICIAL_SEMANTICS')
            categories['OFFICIAL_M']+=1
        else:
            raise ValueError('XRAY_RTH_PILOT_UNCLASSIFIED_TRADE')
    require(sum(categories.values())==len(trades),'TRADE_PARTITION')
    close_px=daily[0].get('c')
    close_agrees=(type(close_px) in (int,float) and math.isfinite(close_px)
                  and close_px==auction_px)
    rth_research_units=(hh[opening]+sum(h[k] for k in mandatory)+auction_shares
                        if regular_bar_coverage else None)
    reconciled=(full_day_consistent and regular_bar_coverage and
                categories['AUCTION_6']>=1 and close_agrees and
                rth_research_units is not None and
                0<rth_research_units<=dv)
    return {'schema':SCHEMA,'asof_et':ASOF,'symbol':SYMBOL,
            'daily_hourly_volume_identity':sum(h.values())==dv,
            'hourly_halfhour_volume_identity':groups==h,
            'rth_hours_with_valid_bar_coverage':regular_bar_coverage,
            'closing_auction_trade_count':categories['AUCTION_6'],
            'afterhours_trade_count_in_four_seconds':categories['EXTENDED_T'],
            'official_market_close_reference_count':categories['OFFICIAL_M'],
            'daily_close_matches_closing_auction':close_agrees,
            'one_session_reconciliation_complete':reconciled,
            'vendor_ohlcv_persisted':False,'rth_volume_units_persisted':False,
            'dv30_primary_created':False,'r92_created':False,
            'execution':'NONE','real_money':'NO-GO',
            'status':('SHADOW_ONE_DAY_RTH_FORMULA_RECONCILED' if reconciled
                      else 'BLOCKED_ONE_DAY_BAR_OR_AUCTION_RECONCILIATION')}


def selftest():
    start=dt.datetime(2026,10,12,0,tzinfo=NY)
    day=[{'t':start.isoformat(),'v':24000,'c':25}]
    hour=[{'t':(start+dt.timedelta(hours=i)).isoformat(),'v':1000} for i in range(24)]
    half=[{'t':(start+dt.timedelta(minutes=i*30)).isoformat(),'v':500} for i in range(48)]
    closing=dt.datetime(2026,10,12,16,tzinfo=NY).astimezone(UTC)
    def trade(secs,flags,ix,size=50):
        return {'t':(closing+dt.timedelta(seconds=secs)).isoformat(),
                'c':flags,'x':'Q','i':ix,'s':size,'p':25}
    tx=[trade(.3,['@','6','X'],1),trade(.5,['@','T'],2),trade(.6,['@','M'],3)]
    x=summarize(day,hour,half,tx,official_close_utc=closing)
    require(x['one_session_reconciliation_complete'],'POSITIVE')
    import copy
    changes=[
        lambda a,b,c,d:a[0].update(v=24001),
        lambda a,b,c,d:b.pop(10),
        lambda a,b,c,d:c.pop(19),
        lambda a,b,c,d:d[0].update(c=['@','6','T']),
        lambda a,b,c,d:d[0].update(x='D'),
        lambda a,b,c,d:d[0].update(p=26),
        lambda a,b,c,d:d[0].update(s=1.1),
        lambda a,b,c,d:d[1].update(c=['@']),
        lambda a,b,c,d:d[1].update(i=1),
        lambda a,b,c,d:a[0].update(t='2026-10-13T00:00:00-04:00'),
    ]
    for mutate in changes:
        aa,bb,cc,dd=[copy.deepcopy(t) for t in (day,hour,half,tx)]
        mutate(aa,bb,cc,dd)
        try:
            result=summarize(aa,bb,cc,dd,official_close_utc=closing)
        except (ValueError,KeyError,TypeError):
            pass
        else:
            require(not result['one_session_reconciliation_complete'],'FALSE_PASS')
    print('XRAY_RTH_HOURLY_RECONCILIATION_SELFTEST=PASS_10_NEGATIVES_NO_VENDOR')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--selftest',action='store_true')
    p.add_argument('--probe',action='store_true')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest();return
    require(args.probe and args.out is not None,'EXPLICIT_ONE_SHOT_ONLY')
    require(os.getenv('XRAY_ALPACA_PERSONAL_BASIC_SHADOW_ENABLED','').lower()=='true',
            'PERSONAL_OPT_IN')
    key=os.getenv('XRAY_ALPACA_DATA_KEY_ID','')
    secret=os.getenv('XRAY_ALPACA_DATA_SECRET_KEY','')
    require(key and secret,'NO_API_CREDENTIALS')
    require(not args.out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),
            'PRIVATE_ARTIFACT_ONLY')
    base='https://data.alpaca.markets/v2/stocks'
    start='2026-10-12T00:00:00-04:00'
    # The historical endpoint accepts an inclusive end; never include
    # next trading day's 00:00 timestamp in an ASOF-one-day proof.
    end='2026-10-12T23:59:59-04:00'
    total=0
    def fetch(path,params):
        nonlocal total
        require(total<MAX_CALLS,'CALL_BUDGET')
        total+=1
        url=base+path+'?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={
            'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
            'Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as resp:
            raw=resp.read(1000000)
        require(len(raw)<1000000,'RESPONSE_SIZE')
        result=json.loads(raw)
        require(not result.get('next_page_token'),'PAGINATION_INCOMPLETE')
        return result
    bars={}
    for tf in ('1Day','1Hour','30Min'):
        result=fetch('/AAON/bars',{'timeframe':tf,'feed':'sip',
            'start':start,'end':end,'adjustment':'raw','limit':10000})
        bars[tf]=result.get('bars')
        if tf=='1Day':
            require(type(bars[tf]) is list and len(bars[tf])==1,
                    'ONE_DAY_ASOF_BAR_SCOPE')
    trade_response=fetch('/AAON/trades',{
         'feed':'sip','start':'2026-10-12T16:00:00-04:00',
         'end':'2026-10-12T16:00:04-04:00','limit':10000,'sort':'asc'})
    closing=dt.datetime(2026,10,12,16,tzinfo=NY).astimezone(UTC)
    result=summarize(bars['1Day'],bars['1Hour'],bars['30Min'],
                     trade_response.get('trades'),official_close_utc=closing)
    result['api_calls']=total
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print('XRAY_RTH_HOURLY_PILOT='+result['status'])
    print('XRAY_RTH_HOURLY_IDENTITY='+json.dumps({
        'daily_hourly':result['daily_hourly_volume_identity'],
        'hourly_halfhour':result['hourly_halfhour_volume_identity'],
        'auction':result['closing_auction_trade_count'],
        'reconciled':result['one_session_reconciliation_complete'],
        'api_calls':total},sort_keys=True))

if __name__=='__main__':main()
