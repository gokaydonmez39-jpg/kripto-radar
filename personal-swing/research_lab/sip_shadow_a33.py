#!/usr/bin/env python3
"""XRAY A33: offline-only IEX/SIP comparison; no API, Sheets, push or trades.

Only uses *supplied* authenticated-elsewhere raw bar snapshots; report is aggregates
without identities/levels. Input cannot attest distribution rights or original PIT.
Never modify 477 EOD signals, historical stops/targets, lifecycle or notifications.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as ec

SCHEMA = 'XRAY_A33_SIP_SHADOW_INPUT_V1'
TICKER_CHARS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.')
CAL = ec.get_calendar('XNAS')

class ComparisonBlocked(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise ComparisonBlocked(code)


def timestamp(s):
    require(isinstance(s, str) and s.endswith('Z'), 'UTC_TIMESTAMP_REQUIRED')
    try:
        val = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        raise ComparisonBlocked('MALFORMED_UTC_TIMESTAMP') from None
    require(val.utcoffset() == timedelta(0), 'UTC_TIMESTAMP_REQUIRED')
    return val


def number(v, positive=True):
    require(type(v) in (int, float) and math.isfinite(v) and (v>0 if positive else v>=0),
            'INVALID_NUMERIC_BAR')
    return float(v)


def validate_bars(values, sessions, asof):
    require(isinstance(values, list), 'MISSING_PROVIDER_SERIES')
    days=[]
    data=[]
    for item in values:
        require(isinstance(item, dict), 'INVALID_BAR_OBJECT')
        day=item.get('session')
        require(isinstance(day, str), 'BAD_BAR_SESSION')
        try:
            require(date.fromisoformat(day).isoformat() == day, 'BAD_BAR_SESSION')
        except ValueError:
            raise ComparisonBlocked('BAD_BAR_SESSION') from None
        require(day <= asof, 'FUTURE_BAR_FORBIDDEN')
        vals={k:number(item.get(k)) for k in ('open','high','low','close','volume')}
        require(vals['low'] <= vals['open'] <= vals['high'] and
                vals['low'] <= vals['close'] <= vals['high'], 'INVALID_OHLC_GEOMETRY')
        days.append(day)
        data.append(vals)
    require(len(days)==len(set(days)), 'DUPLICATE_PROVIDER_SESSION')
    require(days == sorted(days), 'UNSORTED_PROVIDER_SESSIONS')
    require(len(days)>=52, 'INCOMPLETE_HISTORY')
    require(days[-52:] == sessions, 'MISSING_OR_EXTRA_XNAS_SESSION')
    return data


def mean(xs):
    return sum(xs)/len(xs)


def indicators(bars):
    # Mirrors the pinned 2026-10-29 personal-swing/engine.py math, without
    # copying its misleading IEX-only provenance label onto SIP observations.
    closes=[x['close'] for x in bars]
    last=bars[-1]
    ma20=mean(closes[-20:]); ma50=mean(closes[-50:])
    hi20=max(x['high'] for x in bars[-21:-1])
    v20=mean([x['volume'] for x in bars[-21:-1]])
    rv=last['volume']/v20
    gains=losses=0.0
    ranges=[]
    for i in range(len(bars)-14,len(bars)):
        delta=closes[i]-closes[i-1]
        gains+=max(delta,0); losses+=max(-delta,0)
        x=bars[i]; previous=closes[i-1]
        ranges.append(max(x['high']-x['low'],abs(x['high']-previous),
                          abs(x['low']-previous)))
    rsi=100.0 if losses==0 else 100.0-100.0/(1.0+gains/losses)
    atr=mean(ranges)
    price=last['close']; risk=2*atr/price
    failed=[]
    if price<5:failed.append('PRICE_LT5')
    if not price>ma20>ma50:failed.append('TREND')
    if not price>hi20:failed.append('BREAKOUT')
    if rv<1.3:failed.append('RVOL_LT1_30')
    if not 45<=rsi<=75:failed.append('RSI')
    if risk>.08:failed.append('RISK_GT8')
    if price*v20<500000:failed.append('LIQUIDITY')
    return {'decision': 'SHADOW_AL' if not failed else 'SHADOW_NOT_AL',
            'failed': failed,
            'rvol':round(rv,3), 'rsi14':round(rsi,2),
            'atr14':round(atr,3), 'risk_percent':round(100*risk,2)}


def evaluate(doc):
    require(type(doc) is dict and doc.get('schema')==SCHEMA, 'WRONG_SCHEMA')
    asof=doc.get('asof_et')
    try:
        canonical = date.fromisoformat(asof).isoformat() if isinstance(asof,str) else None
    except (TypeError,ValueError,OverflowError):
        raise ComparisonBlocked('BAD_ASOF') from None
    require(canonical == asof, 'BAD_ASOF')
    require(CAL.is_session(asof), 'ASOF_NOT_XNAS_SESSION')
    cutoff=timestamp(doc.get('cutoff_utc'))
    require(cutoff >= CAL.session_close(asof).to_pydatetime()+timedelta(minutes=15),
            'SIP_15_MINUTE_EMBARGO_NOT_OVER')
    scope=doc.get('symbols')
    require(isinstance(scope,list) and bool(scope) and len(scope)==len(set(scope)) and
            all(isinstance(s,str) and 1<=len(s)<=16 and
                all(ch in TICKER_CHARS for ch in s) for s in scope), 'INVALID_SCOPE')
    for feed in ('iex','sip'):
        meta=doc.get(feed)
        require(isinstance(meta,dict) and meta.get('provider')=='ALPACA' and
                meta.get('feed')==feed.upper() and meta.get('basis')=='RAW',
                'PROVIDER_FEED_OR_BASIS_MISMATCH')
        require(isinstance(meta.get('bars'),dict), 'MISSING_PROVIDER_SERIES')
        require(set(meta['bars'])==set(scope),'SYMBOL_SCOPE_COVERAGE_MISMATCH')
    recent=CAL.sessions_window(CAL.date_to_session(asof),-52)
    sessions=[str(t.date()) for t in recent]
    agree=conflicts=iex_signal=sip_signal=0
    failures={}
    max_rvol_abs_delta=0.0
    for symbol in scope:
        l=indicators(validate_bars(doc['iex']['bars'][symbol], sessions,asof))
        r=indicators(validate_bars(doc['sip']['bars'][symbol], sessions,asof))
        iex_signal+=int(l['decision']=='SHADOW_AL')
        sip_signal+=int(r['decision']=='SHADOW_AL')
        if l['decision']==r['decision']:
            agree+=1
        else:
            conflicts+=1
            key='|'.join(r['failed']) if l['decision']=='SHADOW_AL' else 'IEX_'+ '|'.join(l['failed'])
            failures[key]=failures.get(key,0)+1
        max_rvol_abs_delta=max(max_rvol_abs_delta,abs(l['rvol']-r['rvol']))
    return {'schema':'XRAY_A33_SIP_SHADOW_REPORT_V1','asof_et':asof,
            'matched_symbols':len(scope),'sessions_per_symbol':52,
            'paired_bar_count':52*len(scope)*2,
            'decisions_agree':agree,'decisions_disagree':conflicts,
            'iex_shadow_al_count':iex_signal,'sip_shadow_al_count':sip_signal,
            'disagreement_reasons_aggregated':failures,
            'max_abs_rvol_difference':round(max_rvol_abs_delta,3),
            'point_in_time_originality':'NOT_PROVEN_BY_OFFLINE_SNAPSHOT',
            'provider_rights':'NOT_ATTESTED_BY_INPUT',
            'scope_sha_verification':'NOT_ATTESTED_BY_INPUT',
            'universe_full_477_attested':False,
            'may_issue_production_al':False,'may_write_sheet':False,
            'may_change_stops':False,'may_send_alert':False,
            'may_place_order':False, 'execution':'NONE',
            'status':'SOURCE_DISAGREEMENT' if conflicts else 'RESEARCH_AGREEMENT_ONLY'}


def main(argv=None):
    parser=argparse.ArgumentParser(description='XRAY A33 offline, aggregate-only SIP shadow QA')
    parser.add_argument('--input',type=Path,required=True,
                        help='private authenticated-elsewhere JSON; never commit it')
    args=parser.parse_args(argv)
    report=evaluate(json.loads(args.input.read_text(encoding='utf-8')))
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))

if __name__=='__main__':main()
