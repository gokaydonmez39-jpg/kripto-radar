#!/usr/bin/env python3
"""XRAY personal 477 Kronos research sidecar V1.

Runs only after authenticated completed EOD. No AL/STOP/order/alert changes.
No private market data or symbols are printed to public GitHub logs.
Historical forecast rows are immutable; each ASOF+symbol+horizon is unique.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

VERSION = 'XRAY_KRONOS_SHADOW_V1_20261107'
MODEL_ID = 'NeoQuasar/Kronos-small'
TOKENIZER_ID = 'NeoQuasar/Kronos-Tokenizer-base'
MODEL_REV = '901c26c1332695a2a8f243eb2f37243a37bea320'
TOKENIZER_REV = '0e0117387f39004a9016484a186a908917e22426'
KRONOS_CODE_REV = '67b630e67f6a18c9e9be918d9b4337c960db1e9a'
TAB = 'KRONOS_TAHMIN_GUNLUK'
HEADERS = (
    'KAYIT_KIMLIGI', 'ASOF_ET', 'SEMBOL', 'UFUK_SEANS',
    'SON_IEX_KAPANIS_USD', 'TAHMIN_KAPANIS_USD', 'TAHMIN_GETIRI_PCT',
    'MODEL_ID', 'MODEL_REVIZYON', 'TOKENIZER_REVIZYON', 'KRONOS_KOD_REVIZYON',
    'EVREN_SHA256', 'POLITIKA_SHA256', 'TARAMA_KAYIT_KIMLIGI',
    'GIRDI_SHA256', 'TAHMIN_SHA256', 'MODUL_SURUMU', 'DURUM',
    'VERI_POLITIKASI', 'KAYIT_SHA256',
)
HORIZONS = (1, 5, 12)
LOOKBACK = 40
PRED_LEN = 12
MAX_OPEN_SYMBOLS = 32
MAX_ROWS = 20000


class ShadowHold(ValueError):
    """Fixed-category redacted error; never include symbols or data in the message."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ShadowHold(code)


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def normalize_existing(matrix):
    require(isinstance(matrix, list) and bool(matrix), 'KRONOS_TAB_MISSING')
    require(tuple(matrix[0]) == HEADERS, 'KRONOS_HEADER_DRIFT')
    rows = []
    for r in matrix[1:]:
        if r and r[0]:
            require(len(r) <= len(HEADERS), 'KRONOS_ROW_TOO_WIDE')
            rows.append(list(r) + [''] * (len(HEADERS) - len(r)))
    require(len(rows) <= MAX_ROWS, 'KRONOS_LEDGER_CAPACITY')
    require(len({r[0] for r in rows}) == len(rows), 'KRONOS_DUPLICATE_ID')
    return rows


def assert_existing(rows, asof: str, symbols: list[str], scope_sha: str,
                    policy_sha: str) -> bool:
    """Do not regenerate or revise a previously recorded ASOF, even with a new model."""
    matching = [r for r in rows if r[1] == asof]
    if not matching:
        return False
    expected = {f'{asof}|{s}|H{h}' for s in symbols for h in HORIZONS}
    require({r[0] for r in matching} == expected, 'KRONOS_EXISTING_ASOF_PARTIAL_OR_SCOPE_DRIFT')
    for r in matching:
        require(r[7:13] == [MODEL_ID, MODEL_REV, TOKENIZER_REV, KRONOS_CODE_REV,
                            scope_sha, policy_sha], 'KRONOS_EXISTING_MODEL_OR_SOURCE_DRIFT')
        require(r[16] == VERSION and
                (r[17] == 'RESEARCH_ONLY' or r[17].startswith('HOLD_QC_')) and
                r[19] == canonical_sha(r[:19]), 'KRONOS_EXISTING_ROW_TAMPERED')
        if r[17].startswith('HOLD_QC_'):
            require(r[5] == '' and r[6] == '' and r[15] == '',
                    'KRONOS_EXISTING_QC_ROW_HAS_FORECAST')
    return True


def validate_candles(bars: list[dict], asof: str) -> list[dict]:
    require(isinstance(bars, list) and len(bars) >= 52, 'KRONOS_SOURCE_INSUFFICIENT')
    ordered = sorted((b for b in bars if isinstance(b, dict) and
                      str(b.get('timestamp', ''))[:10] <= asof),
                     key=lambda b: b['timestamp'])
    require(len(ordered) >= 52 and str(ordered[-1]['timestamp'])[:10] == asof,
            'KRONOS_SOURCE_ASOF_DRIFT')
    tail = ordered[-52:]
    dates = [str(b['timestamp'])[:10] for b in tail]
    require(len(set(dates)) == 52 and dates == sorted(dates),
            'KRONOS_DUPLICATE_OR_UNSORTED_SESSIONS')
    for b in tail:
        try:
            o, hi, lo, c, volume = (float(b[k]) for k in
                                    ('open', 'high', 'low', 'close', 'volume'))
        except (KeyError, ValueError, TypeError):
            raise ShadowHold('KRONOS_INVALID_SOURCE_OHLCV') from None
        require(all(math.isfinite(v) for v in (o, hi, lo, c, volume)) and
                lo > 0 and lo <= min(o, c) <= max(o, c) <= hi and volume >= 0,
                'KRONOS_INVALID_SOURCE_OHLCV')
    return tail


FORECAST_QC_CODES = frozenset({
    'KRONOS_WRONG_PRED_LENGTH',
    'KRONOS_INVALID_FORECAST_SCHEMA',
    'KRONOS_INVALID_FORECAST_NONFINITE',
    'KRONOS_INVALID_FORECAST_PRICE',
    'KRONOS_INVALID_FORECAST_VOLUME',
    'KRONOS_INVALID_FORECAST_GEOMETRY',
})


def validate_prediction(df, actual_close: float) -> list[float]:
    """Reject unphysical predicted candles; never autocorrect their price/volume.

    Distinct constant classifications permit cohort-safe aggregate diagnostics
    without disclosing model outputs, private symbols, or provider market data.
    """
    require(hasattr(df, 'iterrows') and len(df) == PRED_LEN,
            'KRONOS_WRONG_PRED_LENGTH')
    closes = []
    for _, row in df.iterrows():
        try:
            o, hi, lo, c, vol = (float(row[k]) for k in
                                  ('open', 'high', 'low', 'close', 'volume'))
        except (KeyError, ValueError, TypeError):
            raise ShadowHold('KRONOS_INVALID_FORECAST_SCHEMA') from None
        require(all(math.isfinite(x) for x in (o, hi, lo, c, vol)),
                'KRONOS_INVALID_FORECAST_NONFINITE')
        require(lo > 0 and o > 0 and c > 0 and hi > 0,
                'KRONOS_INVALID_FORECAST_PRICE')
        require(vol >= 0, 'KRONOS_INVALID_FORECAST_VOLUME')
        require(lo <= min(o, c) <= max(o, c) <= hi,
                'KRONOS_INVALID_FORECAST_GEOMETRY')
        closes.append(c)
    require(actual_close > 0, 'KRONOS_BAD_REFERENCE_CLOSE')
    return closes


def build_rows(symbol: str, asof: str, scope_sha: str, policy_sha: str,
               scan_id: str, candles: list[dict], pred_closes: list[float]) -> list[list[str]]:
    require(re.fullmatch(r'[A-Z0-9.]+', symbol) is not None, 'KRONOS_INVALID_SYMBOL')
    require(len(pred_closes) == PRED_LEN, 'KRONOS_WRONG_PRED_LENGTH')
    source = [{k: b[k] for k in ('timestamp', 'open', 'high', 'low', 'close', 'volume')}
              for b in candles[-LOOKBACK:]]
    input_sha = canonical_sha(source)
    forecast_sha = canonical_sha([round(float(x), 6) for x in pred_closes])
    last_close = float(candles[-1]['close'])
    rows = []
    for h in HORIZONS:
        predicted = float(pred_closes[h - 1])
        require(math.isfinite(predicted) and predicted > 0, 'KRONOS_BAD_FORECAST_CLOSE')
        row = [
            f'{asof}|{symbol}|H{h}', asof, symbol, str(h),
            f'{last_close:.6f}', f'{predicted:.6f}',
            f'{(predicted / last_close - 1) * 100:.6f}',
            MODEL_ID, MODEL_REV, TOKENIZER_REV, KRONOS_CODE_REV,
            scope_sha, policy_sha, scan_id, input_sha, forecast_sha,
            VERSION, 'RESEARCH_ONLY', 'IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY',
        ]
        rows.append(row + [canonical_sha(row)])
    return rows



def build_qc_hold_rows(symbol: str, asof: str, scope_sha: str, policy_sha: str,
                       scan_id: str, candles: list[dict], code: str) -> list[list[str]]:
    """Immutable research-only empty forecasts; cannot be mistaken for AL or AI PASS."""
    require(code in FORECAST_QC_CODES, 'KRONOS_INVALID_QC_REASON')
    require(re.fullmatch(r'[A-Z0-9.]+', symbol) is not None, 'KRONOS_INVALID_SYMBOL')
    source = [{k: b[k] for k in ('timestamp', 'open', 'high', 'low', 'close', 'volume')}
              for b in candles[-LOOKBACK:]]
    input_sha = canonical_sha(source)
    last_close = float(candles[-1]['close'])
    result = []
    for horizon in HORIZONS:
        row = [
            f'{asof}|{symbol}|H{horizon}', asof, symbol, str(horizon),
            f'{last_close:.6f}', '', '',
            MODEL_ID, MODEL_REV, TOKENIZER_REV, KRONOS_CODE_REV,
            scope_sha, policy_sha, scan_id, input_sha, '',
            VERSION, 'HOLD_QC_' + code.replace('KRONOS_INVALID_FORECAST_', '')
                                 .replace('KRONOS_WRONG_PRED_LENGTH', 'LENGTH'),
            'IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY',
        ]
        result.append(row + [canonical_sha(row)])
    return result


def future_xnas_days(asof: str) -> list[str]:
    import exchange_calendars as ec
    cal = ec.get_calendar('XNAS')
    first = date.fromisoformat(asof) + timedelta(days=1)
    end = first + timedelta(days=35)
    sessions = cal.sessions_in_range(first.isoformat(), end.isoformat())
    result = [str(x.date()) for x in sessions]
    require(len(result) >= PRED_LEN, 'KRONOS_INSUFFICIENT_FUTURE_SESSIONS')
    return result[:PRED_LEN]


def predict_one(predictor, candles: list[dict], future_sessions: list[str]) -> list[float]:
    import pandas as pd
    recent = candles[-LOOKBACK:]
    x = pd.DataFrame([{k: float(b[k]) for k in ('open', 'high', 'low', 'close', 'volume')}
                      for b in recent])
    # IEX provides volume but not consolidated traded amount. Derived proxy only.
    x['amount'] = x['volume'] * x[['open', 'high', 'low', 'close']].mean(axis=1)
    x_dates = pd.Series(pd.to_datetime([str(b['timestamp'])[:10] for b in recent]))
    y_dates = pd.Series(pd.to_datetime(future_sessions))
    predicted = predictor.predict(df=x, x_timestamp=x_dates, y_timestamp=y_dates,
                                  pred_len=PRED_LEN, T=0.6, top_k=0, top_p=0.90,
                                  sample_count=1, verbose=False)
    return validate_prediction(predicted, float(recent[-1]['close']))


def load_predictor():
    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor
    torch.manual_seed(123)
    torch.set_num_threads(2)
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID, revision=TOKENIZER_REV)
    model = Kronos.from_pretrained(MODEL_ID, revision=MODEL_REV)
    tokenizer.eval()
    model.eval()
    return KronosPredictor(model, tokenizer, device='cpu', max_context=512)


def current_authority(api, asof: str):
    import runner
    import swing_score_daily as score
    import private_sheet_writer as writer
    import private_lifecycle as life
    api.check_metadata()
    scans = writer.rows_only(api.read('TARAMA_KAYITLARI', 'J'), writer.SCAN_HEADER)
    require(scans and scans[-1][0] == asof and sum(r[0] == asof for r in scans) == 1,
            'KRONOS_LAST_SCAN_ASOF_DRIFT')
    scan = scans[-1]
    require([writer.numeric(scan[i]) for i in (2, 3, 4, 5)] == [477,477,477,0]
            and str(scan[6]).upper() == 'TRUE', 'KRONOS_NOT_FINAL_477')
    scope = runner.get_scope(watchlist_file=str(Path(__file__).with_name(
        'nasdaq_watchlist_477.json')), asof=asof)
    require(len(scope) == 477, 'KRONOS_SCOPE_NOT_477')
    scope_sha, policy_sha = runner.sha_symbols(scope), runner.analysis_fingerprint()
    proof = writer.scan_source_proof(scan[9])
    require(proof['scopeSHA'] == scope_sha and proof['algorithmSHA'] == policy_sha,
            'KRONOS_SOURCE_SHA_DRIFT')
    scores = score.normalize_rows(score.score_read(api))
    require(scores and tuple(scores[0]) == score.HEADER,
            'KRONOS_SWING_SCORE_HEADER_DRIFT')
    summary = [r for r in scores[1:] if r and r[0] == asof + '|SUMMARY']
    require(len(summary) == 1 and str(summary[0][27]) in
            ('READY_FOR_CHATGPT_DAILY_DIGEST', 'REQUESTED_NOT_DEVICE_ACK') and summary[0][30] == scope_sha and summary[0][31] == policy_sha,
            'KRONOS_SCORE_SUMMARY_MISSING_OR_SCOPE_DRIFT')
    candidates = api.read('ADAY_GECMISI', 'M')
    episodes = life.decode_open_episodes(candidates, asof)
    unique_symbols = sorted({ep['symbol'] for ep in episodes})
    require(all(s in scope for s in unique_symbols), 'KRONOS_EPISODE_NOT_IN_SCOPE')
    require(len(unique_symbols) <= MAX_OPEN_SYMBOLS, 'KRONOS_COHORT_OVER_CAP')
    require(int(summary[0][5]) == len(episodes) and
            int(summary[0][6]) == len(episodes) and int(summary[0][7]) == 0,
            'KRONOS_SCORE_NOT_FULLY_READY')
    return unique_symbols, scope_sha, policy_sha, scan[0]


def synchronize(api, asof: str, read_batch, predictor_factory=load_predictor):
    import private_sheet_writer as writer
    require(re.fullmatch(r'20\d\d-\d\d-\d\d', asof) is not None and
            date.fromisoformat(asof).isoformat() == asof, 'KRONOS_BAD_ASOF')
    symbols, scope_sha, policy_sha, scan_id = current_authority(api, asof)
    metadata = api.request('?fields=properties(timeZone),sheets.properties(sheetId,title)')
    require(metadata.get('properties', {}).get('timeZone') == 'Europe/Istanbul',
            'KRONOS_TIMEZONE_DRIFT')
    tabs = [s['properties']['sheetId'] for s in metadata.get('sheets', [])
            if s.get('properties', {}).get('title') == TAB]
    require(len(tabs) == 1 and type(tabs[0]) is int, 'KRONOS_TAB_MISSING_OR_DUPLICATE')
    before_matrix = api.read(TAB, 'T')
    before = normalize_existing(before_matrix)
    if assert_existing(before, asof, symbols, scope_sha, policy_sha):
        hold_symbols = len({r[2] for r in before if r[1] == asof and
                            r[17].startswith('HOLD_QC_')})
        return {'status':('KRONOS_SHADOW_IDEMPOTENT_QC_HOLD'
                          if hold_symbols else 'KRONOS_SHADOW_IDEMPOTENT_READBACK_PASS'),
                'asof_et':asof,'scope':'ACTIVE_OPEN_ONLY',
                'symbols':len(symbols),'qc_hold_symbols':hold_symbols,
                'rows':0,'execution':'NONE'}
    if not symbols:
        return {'status':'KRONOS_SHADOW_NO_OPEN_EPISODES', 'asof_et':asof,
                'scope':'ACTIVE_OPEN_ONLY','symbols':0,'rows':0,'execution':'NONE'}
    require(len(before) + len(symbols) * len(HORIZONS) < MAX_ROWS,
            'KRONOS_LEDGER_CAPACITY')
    require(not before or max(row[1] for row in before) < asof,
            'KRONOS_HISTORICAL_BACKFILL_REJECTED')
    bars = read_batch(symbols, asof)
    require(isinstance(bars, dict) and set(bars) == set(symbols),
            'KRONOS_PROVIDER_SCOPE_DRIFT')
    future = future_xnas_days(asof)
    predictor = predictor_factory()
    created = []
    qc_counts = {}
    for symbol in symbols:
        candles = validate_candles(bars[symbol], asof)
        # Actual IEX source drift is fatal; only model-output QC is isolated.
        import engine
        analyzed = engine.analyze(symbol, candles, asof)
        require(analyzed.get('sessions', 0) >= 52 and
                analyzed.get('decision') in ('AL', 'IZLE', 'ELE'),
                'KRONOS_SOURCE_NOT_ANALYZABLE')
        try:
            predicted = predict_one(predictor, candles, future)
        except ShadowHold as exc:
            reason = str(exc)
            if reason not in FORECAST_QC_CODES:
                raise
            created += build_qc_hold_rows(symbol, asof, scope_sha, policy_sha,
                                          scan_id, candles, reason)
            qc_counts[reason] = qc_counts.get(reason, 0) + 1
            continue
        created += build_rows(symbol, asof, scope_sha, policy_sha,
                              scan_id, candles, predicted)
    require(len(created) == len(symbols) * len(HORIZONS) and
            len({r[0] for r in created}) == len(created),
            'KRONOS_RESULT_INCOMPLETE')
    require(api.read(TAB, 'T') == before_matrix,
            'KRONOS_CONCURRENT_EDIT_BLOCKED')
    # One POST, no automatic retries. Unknown server outcome fails closed.
    api.request(':batchUpdate', method='POST',
                body={'requests':[writer.as_cells(created, tabs[0])]})
    after = normalize_existing(api.read(TAB, 'T'))
    require(after[:len(before)] == before and after[len(before):] == created,
            'KRONOS_READBACK_MISMATCH')
    return {'status':('KRONOS_SHADOW_QC_HOLD_READBACK'
                      if qc_counts else 'KRONOS_SHADOW_PRIVATE_READBACK_PASS'),
            'asof_et':asof, 'scope':'ACTIVE_OPEN_ONLY', 'symbols':len(symbols),
            'qc_hold_symbols':sum(qc_counts.values()),
            'qc_categories':dict(sorted(qc_counts.items())),
            'rows':len(created), 'execution':'NONE'}


def main(argv=None):
    import daily_job
    import engine
    import private_sheet_writer as writer
    parser = argparse.ArgumentParser()
    parser.add_argument('--asof', default='')
    args = parser.parse_args(argv)
    try:
        current = daily_job.current_completed_session()
        if current is None:
            print(json.dumps({'status':'KRONOS_SHADOW_NO_COMPLETED_SESSION',
                              'execution':'NONE'}))
            return 0
        asof = args.asof or current
        require(asof == current, 'KRONOS_REQUESTED_ASOF_NOT_CURRENT')
        credential = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON')
        require(bool(credential), 'KRONOS_SHEET_AUTH_MISSING')
        api = writer.SheetApi(credential)
        out = synchronize(api, asof, engine.live_read)
        print(json.dumps(out, sort_keys=True))
        return 3 if out['status'] in ('KRONOS_SHADOW_QC_HOLD_READBACK',
                                      'KRONOS_SHADOW_IDEMPOTENT_QC_HOLD') else 0
    except Exception as ex:
        code = str(ex) if isinstance(ex, ShadowHold) else 'KRONOS_UNCLASSIFIED'
        # No secrets, symbols, URLs, exceptions, inputs, predictions, or tracebacks.
        print(json.dumps({'status':'KRONOS_SHADOW_HOLD','reason_code':code,
                          'execution':'NONE'}, sort_keys=True))
        return 3


if __name__ == '__main__':
    sys.exit(main())
