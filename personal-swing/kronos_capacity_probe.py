#!/usr/bin/env python3
"""No-secrets 477-series CPU budget probe for Kronos-small.

Synthetic OHLCV only: DOES NOT prove 477 live IEX availability,
prediction validity, financial performance or private Sheet capacity.
"""
from __future__ import annotations

import json
import math
import resource
import time

from kronos_shadow import ShadowHold, load_predictor, predict_one

COUNT = 477
MAX_INFERENCE_SECONDS = 1300
MAX_PEAK_RSS_MB = 8192


def synthetic_history(i, asof_dates):
    base = 15.0 + i * 0.25
    result=[]
    for j, stamp in enumerate(asof_dates):
        open_ = base + 0.06*j + math.sin((j+i) / 7)
        close = open_ + 0.38 * math.sin(j / 4 + i / 11)
        result.append({
            'timestamp': stamp,
            'open':open_, 'high':max(open_,close)+0.52,
            'low':min(open_,close)-0.52,
            'close':close, 'volume':1500000+i*1000+j*30})
    return result


def capacity_contract(n, elapsed_s, rss_mb):
    return {
        'status': ('KRONOS_477_SYNTHETIC_CPU_BUDGET_PASS' if
                   n == COUNT and 0 <= elapsed_s <= MAX_INFERENCE_SECONDS
                   and 0 < rss_mb <= MAX_PEAK_RSS_MB
                   else 'KRONOS_477_SYNTHETIC_CPU_BUDGET_HOLD'),
        'processed':n,
        'expected':COUNT,
        'elapsed_seconds':round(elapsed_s,2),
        'peak_rss_mb':round(rss_mb,2),
        'real_iex_symbols_tested':0,
        'live_477_coverage':'NOT_PROVEN',
        'private_sheet_capacity':'NOT_PROVEN',
        'financial_alpha':'NOT_PROVEN',
        'orders':False,
    }


def main():
    import pandas as pd
    dates=[x.date().isoformat() for x in pd.bdate_range('2026-04-01',periods=52)]
    future=[x.date().isoformat() for x in
            pd.bdate_range(pd.Timestamp(dates[-1])+pd.offsets.BDay(1),periods=12)]
    model=load_predictor()
    start=time.perf_counter()
    processed=0
    failed_qc=0
    for i in range(COUNT):
        try:
            predict_one(model,synthetic_history(i,dates),future)
        except ShadowHold as exc:
            if str(exc).startswith(('KRONOS_INVALID_FORECAST_', 'KRONOS_WRONG_PRED_LENGTH')):
                failed_qc += 1
            else:
                raise
        processed += 1
        if time.perf_counter()-start > MAX_INFERENCE_SECONDS:
            break
    sec=time.perf_counter()-start
    mem=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    out=capacity_contract(processed,sec,mem)
    out['qc_hold_symbols']=failed_qc
    print(json.dumps(out,sort_keys=True,allow_nan=False))
    return 0 if out['status']=='KRONOS_477_SYNTHETIC_CPU_BUDGET_PASS' else 3


if __name__=='__main__':
    raise SystemExit(main())
