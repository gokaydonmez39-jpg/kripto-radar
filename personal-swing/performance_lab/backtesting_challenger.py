"""XRAY NASDAQ A35: optional, offline, read-only Backtesting.py discrepancy witness.

No broker, Sheets, network, notifications, strategy optimization, or production imports.
Results are per-signal execution-model comparisons, NEVER portfolio P&L or alpha.
All bars must be caller-supplied with authentic lineage; tests use synthetic fixtures.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import importlib
import math
import warnings

import exchange_calendars as ec

from nasdaq_performance_guard import EvidenceBlocked, evaluate_episode, need, price

PINNED_VERSION = '0.6.6'
PASS = 'REFERENCE_MATCH_ONLY_NOT_PORTFOLIO_ALPHA'
HOLD = 'HOLD_EXECUTION_MODEL_DIVERGENCE'
SCOPE = 'XRAY_NASDAQ_OFFLINE_READONLY_CHALLENGER'
NO_EXECUTION = {'orders': False, 'sheet_writes': False,
                'notifications': False, 'rule_changes': False,
                'real_fills_proven': False}


def _valid_prior_bars(witness):
    need(type(witness) is dict and set(witness) ==
         {'episode', 'previous_bar', 'signal_bar'}, 'CHALLENGER_SCHEMA')
    e = witness['episode']
    # Validate immutable source, policy, XNAS chronology and all completed OHLC.
    source = evaluate_episode(e, entry_cost_bps=0, exit_cost_bps=0)
    cal = ec.get_calendar('XNAS')
    sig = date.fromisoformat(e['signal_asof'])
    previous = cal.session_offset(e['signal_asof'], -1).date().isoformat()
    out = []
    for row, expected in ((witness['previous_bar'], previous),
                          (witness['signal_bar'], sig.isoformat())):
        need(type(row) is dict and set(row) ==
             {'date', 'open', 'high', 'low', 'close', 'volume'},
             'CHALLENGER_PRIOR_BAR_SCHEMA')
        need(row['date'] == expected, 'CHALLENGER_PRIOR_BAR_TIME')
        v = {k: price(row[k]) for k in ('open', 'high', 'low', 'close')}
        need(v['low'] <= min(v['open'], v['close']) and
             v['high'] >= max(v['open'], v['close']), 'CHALLENGER_PRIOR_BAR_OHLC')
        need(type(row['volume']) in (int, float) and
             math.isfinite(row['volume']) and row['volume'] > 0,
             'CHALLENGER_PRIOR_BAR_VOLUME')
        out.append(row)
    need(price(out[-1]['close']) == price(e['reference_close']),
         'CHALLENGER_SIGNAL_CLOSE_DRIFT')
    return source, out


def _engine(witness, commission_bps):
    """Only ONE synthetic paper-unit. Never calls private vendor or broker APIs."""
    need(type(commission_bps) in (int, float) and
         math.isfinite(commission_bps) and 0 <= commission_bps <= 100,
         'CHALLENGER_COST_BPS_INVALID')
    try:
        backtesting = importlib.import_module('backtesting')
        pandas = importlib.import_module('pandas')
    except ImportError as exc:
        raise EvidenceBlocked('BACKTESTING_OPTIONAL_DEPENDENCY_MISSING') from exc
    need(backtesting.__version__ == PINNED_VERSION,
         'BACKTESTING_UNPINNED_VERSION')
    e = witness['episode']
    rows = [witness['previous_bar'], witness['signal_bar'], *e['bars']]
    frame = pandas.DataFrame([{
        'Date': r['date'], 'Open': float(price(r['open'])),
        'High': float(price(r['high'])), 'Low': float(price(r['low'])),
        'Close': float(price(r['close'])), 'Volume': float(r['volume'])}
        for r in rows]).set_index('Date')
    frame.index = pandas.to_datetime(frame.index)
    target_date = e['signal_asof']
    stop, target = float(price(e['stop'])), float(price(e['target']))

    class _SingleFrozenEpisode(backtesting.Strategy):
        def init(self):
            pass

        def next(self):
            # Strategy.next runs at close; market order executes at NEXT open.
            if self.data.index[-1].date().isoformat() == target_date:
                self.buy(size=1, sl=stop, tp=target)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        run = backtesting.Backtest(
            frame, _SingleFrozenEpisode, cash=1_000_000,
            spread=0.0, commission=commission_bps / 10_000,
            margin=1.0, trade_on_close=False, hedging=False,
            exclusive_orders=True, finalize_trades=False).run()
    trade_frame = run['_trades']
    trades = []
    for _, r in trade_frame.iterrows():
        trades.append({'entry_date': r['EntryTime'].date().isoformat(),
                       'exit_date': r['ExitTime'].date().isoformat(),
                       'entry': float(r['EntryPrice']),
                       'exit': float(r['ExitPrice']),
                       'return_pct': float(r['ReturnPct'] * 100)})
    bad_warnings = [str(w.message) for w in captured if
                    ('dubious' in str(w.message).lower() or
                     'contingent' in str(w.message).lower() or
                     'cancel' in str(w.message).lower())]
    return trades, bool(bad_warnings)


def compare_episode(witness):
    """Return redacted, fail-closed execution parity. NO strategy quality verdict."""
    source, _ = _valid_prior_bars(witness)
    output = {'scope': SCOPE, 'status': None,
              'reference_status': source['status'],
              'reference_event': source['event'],
              'source_proof_hash': source['proof_hash'],
              'engine': 'backtesting.py==' + PINNED_VERSION,
              'note': 'SYNTHETIC_EXECUTION_COMPARISON_NOT_ALPHA', **NO_EXECUTION}
    if source['status'] == 'ENTRY_INVALIDATED_BY_GAP':
        output['status'] = 'HOLD_ENTRY_GAP_INVALIDATED_NO_FILL'
        return output
    if source['status'] == 'OPEN_CENSORED':
        output['status'] = 'HOLD_CENSORED_NO_CLOSED_TRADE'
        return output
    if source['event'] == 'TIME_EXIT_AT_CLOSE':
        # Engine's manual close on next bar differs from EXACT session-15 close.
        output['status'] = 'HOLD_15TH_CLOSE_MODEL_NOT_EQUIVALENT'
        return output
    need(source['status'] == 'COMPLETE' and len(witness['episode']['bars']) > 0,
         'CHALLENGER_SOURCE_NOT_COMPARABLE')
    bars = witness['episode']['bars']
    first_open = float(price(bars[0]['open']))
    trades, uncertain = _engine(witness, 0)
    output['engine_completed_trades'] = len(trades)
    if len(trades) != 1:
        output['status'] = HOLD
        return output
    trade = trades[0]
    event = source['event']
    exit_bar = next((r for r in bars if r['date'] == source['exit_date']), None)
    need(exit_bar is not None, 'CHALLENGER_EXIT_BAR_NOT_FOUND')
    expected_exit = (float(price(exit_bar['open']))
                     if event in {'STOP_GAP_OPEN', 'TARGET_GAP_OPEN'}
                     else float(price(witness['episode']['stop']))
                     if event in {'STOP_TOUCHED', 'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS'}
                     else float(price(witness['episode']['target'])))
    observed_return = (trade['exit'] / trade['entry'] - 1) * 100
    ok = (trade['entry_date'] == bars[0]['date'] and
          trade['exit_date'] == source['exit_date'] and
          math.isclose(trade['entry'], first_open, rel_tol=0, abs_tol=1e-7) and
          math.isclose(trade['exit'], expected_exit, rel_tol=0, abs_tol=1e-7) and
          math.isclose(observed_return, source['next_open_net_pct'],
                       rel_tol=0, abs_tol=1e-6))
    output['entry_matches'] = math.isclose(trade['entry'], first_open,
                                           rel_tol=0, abs_tol=1e-7)
    output['exit_matches'] = math.isclose(trade['exit'], expected_exit,
                                          rel_tol=0, abs_tol=1e-7)
    output['dates_match'] = (trade['entry_date'] == bars[0]['date'] and
                             trade['exit_date'] == source['exit_date'])
    output['return_delta_percentage_points'] = round(
        observed_return - source['next_open_net_pct'], 9)
    if event == 'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS' or uncertain:
        output['status'] = 'HOLD_INTRABAR_PATH_AMBIGUOUS'
    else:
        output['status'] = PASS if ok else HOLD
    return output


def cost_stress(witness):
    """External-library commission sensitivity; NEVER equate its PnL to XRAY fees."""
    source, _ = _valid_prior_bars(witness)
    need(source['status'] == 'COMPLETE' and source['event'] not in
         {'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS', 'TIME_EXIT_AT_CLOSE'},
         'COST_STRESS_UNCOMPARABLE')
    levels = (0, 15, 40)
    trade_returns = []
    for bps in levels:
        trades, uncertain = _engine(witness, bps)
        need(not uncertain and len(trades) == 1,
             'COST_STRESS_MODEL_DIVERGENCE')
        trade_returns.append(trades[0]['return_pct'])
    need(all(math.isfinite(x) for x in trade_returns), 'COST_STRESS_NONFINITE')
    return {'status': 'SCENARIO_ONLY_NO_ALPHA',
            'commission_each_side_bps': list(levels),
            'engine_trade_return_pct': [round(x, 7) for x in trade_returns],
            'monotonically_nonincreasing': all(a >= b for a,b in zip(
                trade_returns, trade_returns[1:])),
            'not_equal_to_xray_cost_model_by_default': True, **NO_EXECUTION}
