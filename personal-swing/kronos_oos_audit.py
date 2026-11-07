#!/usr/bin/env python3
"""Independent, read-only Kronos versus last-close benchmark audit.

Forecasts are frozen per original ASOF. No future outcomes are used until
their official XNAS session is completed; no AL, stop, Sheets or orders written.
Public CI output contains aggregates/status only, never private symbols.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
import math
import os
import re

import kronos_shadow as k

MIN_UNIQUE_PAIRS = 60
MIN_DISTINCT_ASOFS = 4


def require(ok, reason):
    k.require(ok, reason)


def validate_ledger(matrix):
    rows = k.normalize_existing(matrix)
    by_pair = defaultdict(list)
    for row in rows:
        require(len(row) == 20 and row[19] == k.canonical_sha(row[:19]),
                'KRONOS_OOS_ROW_TAMPERED')
        asof, symbol, horizon = row[1], row[2], row[3]
        require(re.fullmatch(r'20\d{2}-\d{2}-\d{2}', asof) and
                date.fromisoformat(asof).isoformat() == asof and
                re.fullmatch(r'[A-Z0-9.]+', symbol) and
                horizon in ('1', '5', '12') and
                row[0] == f'{asof}|{symbol}|H{horizon}',
                'KRONOS_OOS_INVALID_ROW_IDENTITY')
        require(row[7:11] == [k.MODEL_ID, k.MODEL_REV,
                              k.TOKENIZER_REV, k.KRONOS_CODE_REV] and
                row[16] == k.VERSION and
                row[17] in ('RESEARCH_ONLY',) or False,
                'KRONOS_OOS_INVALID_MODEL_OR_STATUS') if not row[17].startswith('HOLD_QC_') else require(
                row[7:11] == [k.MODEL_ID, k.MODEL_REV,
                               k.TOKENIZER_REV, k.KRONOS_CODE_REV] and
                row[16] == k.VERSION,
                'KRONOS_OOS_INVALID_MODEL_OR_STATUS')
        require(all(re.fullmatch(r'[0-9a-f]{64}', row[i]) for i in (11,12,14))
                and bool(row[13]),
                'KRONOS_OOS_INVALID_PROVENANCE')
        if row[17] == 'RESEARCH_ONLY':
            require(bool(row[15]) and re.fullmatch(r'[0-9a-f]{64}', row[15])
                    and all(math.isfinite(float(row[i])) for i in (4,5,6))
                    and float(row[4]) > 0 and float(row[5]) > 0,
                    'KRONOS_OOS_INVALID_FORECAST_ENTRY')
        else:
            require(row[17].startswith('HOLD_QC_') and
                    row[5] == row[6] == row[15] == '',
                    'KRONOS_OOS_QC_HOLD_HAS_FORECAST')
        by_pair[(asof, symbol)].append(row)
    require(all(len(pair)==3 and {v[3] for v in pair}=={'1','5','12'}
                and len({v[17] for v in pair})==1 for pair in by_pair.values()),
            'KRONOS_OOS_PARTIAL_PAIR')
    return rows


def select_matured(rows, completed_asof):
    """No data provider calls unless expected future XNAS session is completed."""
    require(date.fromisoformat(completed_asof).isoformat() == completed_asof,
            'KRONOS_OOS_BAD_COMPLETED_ASOF')
    matured, pending, qc_holds = [], 0, 0
    calendar_cache = {}
    for row in rows:
        asof, symbol, horizon = row[1], row[2], int(row[3])
        require(asof <= completed_asof, 'KRONOS_OOS_FUTURE_SOURCE_ROW')
        if row[17].startswith('HOLD_QC_'):
            qc_holds += 1
            continue
        if asof not in calendar_cache:
            calendar_cache[asof] = k.future_xnas_days(asof)
        target = calendar_cache[asof][horizon-1]
        if target > completed_asof:
            pending += 1
        else:
            matured.append((row, target))
    return matured, pending, qc_holds


def score_matured(matured, completed_asof, read_batch):
    """Reference-close baseline, same reference and target as model."""
    symbols = sorted({r[2] for r, _ in matured})
    bars = read_batch(symbols, completed_asof) if symbols else {}
    require(isinstance(bars, dict) and set(bars) == set(symbols),
            'KRONOS_OOS_PROVIDER_SCOPE_DRIFT')
    by_symbol_date = {}
    for symbol in symbols:
        seq = bars[symbol]
        require(isinstance(seq, list), 'KRONOS_OOS_PROVIDER_BARS_NOT_LIST')
        for bar in seq:
            dt = str(bar.get('timestamp',''))[:10]
            if dt <= completed_asof:
                key = (symbol, dt)
                require(key not in by_symbol_date,
                        'KRONOS_OOS_PROVIDER_DUPLICATE_DATE')
                try:
                    value = float(bar['close'])
                except (TypeError, ValueError, KeyError):
                    raise k.ShadowHold('KRONOS_OOS_BAD_OUTCOME_PRICE') from None
                require(math.isfinite(value) and value > 0,
                        'KRONOS_OOS_BAD_OUTCOME_PRICE')
                by_symbol_date[key] = value
    evidence = defaultdict(list)
    for row, target in matured:
        symbol, h, asof = row[2], int(row[3]), row[1]
        key = (symbol, target)
        require(key in by_symbol_date, 'KRONOS_OOS_MISSING_TARGET_CLOSE')
        actual = by_symbol_date[key]
        reference = float(row[4])
        predicted = float(row[5])
        actual_move = actual-reference
        predicted_move = predicted-reference
        evidence[h].append({
            'asof': asof,
            'model_pct_error':100*abs(predicted-actual)/actual,
            'baseline_pct_error':100*abs(reference-actual)/actual,
            'direction_correct': (predicted_move > 0 and actual_move > 0) or
                                 (predicted_move < 0 and actual_move < 0),
        })
    return evidence


def summarize(evidence, pending, qc_holds):
    out = {
        'status':'KRONOS_OOS_RESEARCH_NOT_READY',
        'execution':'NONE', 'orders':False,
        'pending_horizon_rows':pending,'qc_hold_rows':qc_holds,
        'benchmark':'PERSIST_LAST_IEX_CLOSE',
        'sufficient_for_decision':False,'decision_influence':'NO_GO',
        'horizons':{},
    }
    for h in (1,5,12):
        rows = evidence.get(h, [])
        n = len(rows)
        distinct_asofs = len({r['asof'] for r in rows})
        if n:
            model = sum(x['model_pct_error'] for x in rows)/n
            baseline = sum(x['baseline_pct_error'] for x in rows)/n
            hit = sum(x['direction_correct'] for x in rows)/n
        else: model = baseline = hit = None
        out['horizons'][str(h)] = {
            'samples':n,'distinct_asofs':distinct_asofs,
            'model_mape_pct':round(model,5) if model is not None else None,
            'persistence_mape_pct':round(baseline,5) if baseline is not None else None,
            'direction_hit_rate':round(hit,5) if hit is not None else None,
            'preliminary_sample_gate': n >= MIN_UNIQUE_PAIRS and
                distinct_asofs >= MIN_DISTINCT_ASOFS,
        }
    # Sample sufficiency is only a PRELIMINARY metric gate: no costs,
    # bootstrap/embargo, impact test or market beta here. Never assert alpha.
    if all(out['horizons'][str(h)]['preliminary_sample_gate'] for h in (1,5,12)):
        out['status'] = 'KRONOS_OOS_SAMPLE_REVIEW_REQUIRED'
    return out


def audit(api, completed_asof, read_batch):
    rows = validate_ledger(api.read(k.TAB,'T'))
    mature, pending, holds = select_matured(rows,completed_asof)
    evidence = score_matured(mature,completed_asof,read_batch)
    return summarize(evidence,pending,holds)


def main():
    import engine
    import private_sheet_writer as writer
    try:
        completed = k.eligible_shadow_asof()
        if completed is None:
            print(json.dumps({'status':'KRONOS_OOS_NOT_DUE','execution':'NONE'},
                             sort_keys=True))
            return 0
        credential = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON')
        require(bool(credential),'KRONOS_OOS_AUTH_MISSING')
        api = writer.SheetApi(credential)
        # The latest 477/477 readback and score summary are an independent
        # temporal authority before using completed session IEX data.
        k.current_authority(api,completed)
        out = audit(api,completed,engine.live_read)
        print(json.dumps(out,sort_keys=True,allow_nan=False))
        return 0
    except Exception as ex:
        reason = str(ex) if isinstance(ex,k.ShadowHold) else 'KRONOS_OOS_UNCLASSIFIED'
        print(json.dumps({'status':'KRONOS_OOS_HOLD','reason_code':reason,
                          'execution':'NONE'},sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
