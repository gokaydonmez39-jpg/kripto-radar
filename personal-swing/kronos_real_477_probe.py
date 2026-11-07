#!/usr/bin/env python3
"""One-off NO-WRITE real 477 personal XNAS IEX Kronos cohort audit.

Research diagnostics only. NO private data export, predictions, Sheet writes,
GitHub artifacts, orders, alerts, new cron or changes to core 477 decisions.
"""
from collections import Counter
import json
import os
from pathlib import Path
import resource
import time

import kronos_shadow as k

MAX_REAL_PROBE_SECONDS = 1300
MAX_REAL_RSS_MB = 8192
EXPECTED = 477


def evaluate_cohort(symbols, asof, read_batch, predictor_factory,
                    *, clock=time.perf_counter, mem_mb=None):
    import engine
    require = k.require
    require(isinstance(symbols,list) and len(symbols)==EXPECTED and
            len(set(symbols))==EXPECTED, 'KRONOS_477_INVALID_SCOPE')
    begin=clock()
    histories=read_batch(symbols,asof)
    require(isinstance(histories,dict) and set(histories)==set(symbols),
            'KRONOS_477_PROVIDER_SCOPE_DRIFT')
    predictor=predictor_factory()
    future=k.future_xnas_days(asof)
    qc=Counter()
    valid=0
    for symbol in symbols:
        bars=k.validate_candles(histories[symbol],asof)
        analyzed=engine.analyze(symbol,bars,asof)
        require(analyzed.get('sessions',0)>=52 and
                analyzed.get('decision') in ('AL','IZLE','ELE'),
                'KRONOS_477_SOURCE_NOT_ANALYZABLE')
        try:
            k.predict_one(predictor,bars,future)
            valid+=1
        except k.ShadowHold as ex:
            reason=str(ex)
            if reason not in k.FORECAST_QC_CODES:
                raise
            qc[reason]+=1
        require(clock()-begin <= MAX_REAL_PROBE_SECONDS,
                'KRONOS_477_REAL_CPU_BUDGET_EXCEEDED')
    rss = mem_mb() if mem_mb else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    require(0<rss<=MAX_REAL_RSS_MB,'KRONOS_477_REAL_RSS_BUDGET_EXCEEDED')
    require(valid+sum(qc.values())==EXPECTED,'KRONOS_477_INCOMPLETE_PROBE')
    elapsed=clock()-begin
    return {
        'status':('KRONOS_REAL_477_QC_HOLD' if qc
                  else 'KRONOS_REAL_477_QC_OBSERVATION_PASS'),
        'asof_et':asof,'scope':'PERSONAL_477',
        'processed':EXPECTED,'valid_forecast_symbols':valid,
        'qc_hold_symbols':sum(qc.values()),'qc_categories':dict(sorted(qc.items())),
        'elapsed_seconds':round(elapsed,2),'peak_rss_mb':round(rss,2),
        'model_decision_influence':'NO_GO',
        'sheet_rows_written':0,'orders':False,'new_alerts':0,
        'private_market_data_emitted':False,
        'live_477_persistent_readback':'NOT_TESTED',
        'financial_alpha':'NOT_PROVEN',
    }


def main():
    import engine
    import runner
    import private_sheet_writer as writer
    try:
        asof=k.eligible_shadow_asof()
        require=k.require
        if asof is None:
            print(json.dumps({'status':'KRONOS_477_NOT_DUE','execution':'NONE'},
                             sort_keys=True))
            return 0
        credential=os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON')
        require(bool(credential),'KRONOS_477_PRIVATE_AUTH_MISSING')
        api=writer.SheetApi(credential)
        # Source proof must match official completed 477 scan and exact score.
        k.current_authority(api,asof)
        symbols=runner.get_scope(watchlist_file=str(Path(__file__).with_name(
            'nasdaq_watchlist_477.json')),asof=asof)
        out=evaluate_cohort(symbols,asof,engine.live_read,k.load_predictor)
        print(json.dumps(out,sort_keys=True))
        return 3 if out['qc_hold_symbols'] else 0
    except Exception as ex:
        reason=str(ex) if isinstance(ex,k.ShadowHold) else 'KRONOS_477_UNCLASSIFIED'
        # Only audited categorical codes, never exception/provider details.
        print(json.dumps({'status':'KRONOS_REAL_477_HOLD','reason_code':reason,
                          'execution':'NONE'},sort_keys=True))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
