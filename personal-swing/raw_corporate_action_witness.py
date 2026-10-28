#!/usr/bin/env python3
"""Isolated private NASDAQ raw-IEX discontinuity and issuance-price witness.

A split/merger can distort unadjusted daily bars. This source-integrity witness
can detect LARGE suspicious discontinuities and historical IEX reference drift,
but it CANNOT certify the absence of corporate actions. Requires independent
issuer/CA evidence for final clearance. No broker, Sheet mutation, or push.
"""
from datetime import date
import json
import math
import os
from pathlib import Path
import re
import sys

import exchange_calendars as ec
import daily_job
import engine
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER, rows_only, numeric
from performance_lab.private_performance_adapter import PrivateSheetReadOnly

CAL = 'XNAS'
MIN_RATIO = 0.78
MAX_RATIO = 1.27
MAX_ROWS = 1000
SYM = re.compile(r'^[A-Z][A-Z0-9.]{0,15}$')


class ActionWitnessBlocked(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise ActionWitnessBlocked(reason)


def _bar_day(bar):
    need(type(bar) is dict and type(bar.get('timestamp')) is str
         and len(bar['timestamp'])>=10, 'BAD_RAW_DATE')
    return bar['timestamp'][:10]


def inspect(candidate_values, scan_values, bars, asof):
    """Pure read-only audit: aggregate counters only; suppress identities/levels."""
    cal=ec.get_calendar(CAL)
    need(type(asof) is str and cal.is_session(asof), 'BAD_ASOF')
    need(type(candidate_values) is list and len(candidate_values)<=MAX_ROWS,
         'CANDIDATE_BOUNDS')
    need(type(scan_values) is list and len(scan_values)<=MAX_ROWS,
         'SCAN_BOUNDS')
    episodes=rows_only(candidate_values,CANDIDATE_HEADER)
    scans=rows_only(scan_values,SCAN_HEADER)
    need(bool(scans) and scans[-1][0]==asof, 'CURRENT_EOD_SCAN_NOT_PUBLISHED')
    s=scans[-1]
    need(len(s)>=10 and [numeric(s[i]) for i in (2,3,4,5)]==
         [477.,477.,477.,0.] and str(s[6]).upper()=='TRUE',
         'EOD_SCAN_NOT_FULL_FINAL')
    need(type(bars) is dict, 'RAW_PROVIDER_SHAPE')
    keys=set()
    issuances={}
    for r in episodes:
        need(len(r)>=13, 'INCOMPLETE_EPISODE')
        key=str(r[0]); d=str(r[1]); sym=str(r[2])
        need(key==d+'|'+sym and SYM.fullmatch(sym) is not None
             and key not in keys and d<=asof and cal.is_session(d),
             'EPISODE_IDENTITY')
        keys.add(key)
        close=numeric(r[4]); stop=numeric(r[5]); target=numeric(r[6])
        need(0<stop<close<target and
             abs(target-(close+2*(close-stop)))<=.025,
             'CORRUPT_HISTORICAL_PRICE_GEOMETRY')
        issuances.setdefault(sym,[]).append((d,close))
    need(set(bars)==set(issuances), 'RAW_SYMBOL_SCOPE_DRIFT')
    large_gap_count=0
    issuance_drift_count=0
    raw_bars_reviewed=0
    for sym in sorted(issuances):
        rows=bars[sym]
        need(type(rows) is list and len(rows)>0, 'MISSING_RAW_BARS')
        byday={}
        for b in rows:
            day=_bar_day(b)
            if day>asof:
                continue
            need(day not in byday, 'DUPLICATE_RAW_BAR')
            vals=[b.get(field) for field in ('open','high','low','close','volume')]
            need(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in vals),
                 'INVALID_RAW_OHLCV')
            need(b['low']<=min(b['open'],b['close'])<=
                 max(b['open'],b['close'])<=b['high'],
                 'INVALID_RAW_PRICE_RANGE')
            byday[day]=b
        needed_start=min(d for d,_ in issuances[sym])
        # AL metrics consume 52 contiguous daily bars INCLUDING 51 sessions
        # preceding the original signal. Start reviewing that exact original
        # indicator window; looking only AFTER the AL misses earlier splits.
        first=cal.session_offset(cal.date_to_session(needed_start),-51)
        expected=[str(x.date()) for x in cal.sessions_in_range(first,asof)]
        need(all(d in byday for d in expected), 'RAW_MISSING_XNAS_SESSION')
        raw_bars_reviewed+=len(expected)
        previous=None
        for day in expected:
            b=byday[day]
            if previous is not None:
                ratio=b['open']/previous['close']
                if ratio<MIN_RATIO or ratio>MAX_RATIO:
                    large_gap_count+=1
            previous=b
        for issuance_day,original in issuances[sym]:
            actual=byday[issuance_day]['close']
            # Spreadsheet levels can have 2/3 decimals; > 1 cent is not rounding.
            if abs(actual-original)>.00501:
                issuance_drift_count+=1
    return {
       'schema':'XRAY_NASDAQ_RAW_CA_WITNESS_V1',
       'asof_et':asof,
       'candidate_count':len(episodes),
       'unique_symbol_count':len(issuances),
       'raw_session_bars_checked':raw_bars_reviewed,
       'large_raw_open_gap_count':large_gap_count,
       'historical_issuance_close_mismatches':issuance_drift_count,
       'state':('REVIEW_REQUIRED' if large_gap_count or issuance_drift_count
                else 'NO_LARGE_RAW_DISCONTINUITY_CA_STATUS_UNVERIFIED'),
       'corporate_action_cleared':False,
       'independent_vendor_corporate_action_confirmed':False,
       'device_ack':False,
       'orders':False,
       'sheet_writes':False,
       'auto_strategy_change':False
    }


def live_entrypoint():
    try:
        eligible=daily_job.current_completed_session()
        if eligible is None:
            print(json.dumps({'state':'NO_COMPLETED_XNAS_SESSION',
                              'corporate_action_cleared':False,
                              'sheet_writes':False, 'orders':False}))
            return 0
        secret=os.getenv('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON','')
        id_=os.getenv('XRAY_PRIVATE_SPREADSHEET_ID','')
        need(bool(secret) and bool(id_), 'MISSING_PRIVATE_READONLY_AUTH')
        api=PrivateSheetReadOnly(secret,id_)
        api.verify_metadata()
        candidates=api.read('ADAY_GECMISI','M')
        scans=api.read('TARAMA_KAYITLARI','J')
        cohort=rows_only(candidates,CANDIDATE_HEADER)
        symbols=sorted({r[2] for r in cohort})
        need(bool(symbols), 'NO_CANDIDATE_COHORT')
        bars=engine.live_read(symbols,eligible)
        status=inspect(candidates,scans,bars,eligible)
        # Protect against a concurrent sheet edit while vendor data are fetched.
        need(candidates==api.read('ADAY_GECMISI','M') and
             scans==api.read('TARAMA_KAYITLARI','J'),
             'CONCURRENT_PRIVATE_SOURCE_CHANGE')
        print(json.dumps(status,sort_keys=True))
        return 3 if status['state']=='REVIEW_REQUIRED' else 0
    except Exception as exc:
        # No exception string: could carry symbol, vendor data, secret or prices.
        print(json.dumps({'state':'BLOCKED_NO_RAW_DATA_PUBLISHED',
                          'reason_type':type(exc).__name__,
                          'corporate_action_cleared':False,
                          'device_ack':False, 'orders':False,
                          'sheet_writes':False}))
        return 3


if __name__=='__main__':
    raise SystemExit(live_entrypoint())
