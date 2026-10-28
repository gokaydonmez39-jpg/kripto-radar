"""XRAY personal NASDAQ: independent, offline, read-only signal outcome witness.

No network, Google Sheets, broker, order, alert, AI agent or production imports.
All inputs are an explicit synthetic/external audit contract; no fabricated live PnL.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import random
import re
from statistics import NormalDist

import exchange_calendars as ec

SOURCE = 'IEX_EOD_SINGLE_EXCHANGE'
IDENT = re.compile(r'^[A-Z][A-Z0-9.]{0,15}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


class EvidenceBlocked(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise EvidenceBlocked(code)


def price(value):
    need(type(value) in (str, int, float, Decimal), 'PRICE_TYPE')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EvidenceBlocked('PRICE_PARSE') from exc
    need(result.is_finite() and result > 0, 'PRICE_NONFINITE_OR_NONPOSITIVE')
    return result


def decimal_bps(value):
    n = price(value) if value != 0 else Decimal(0)
    need(Decimal(0) <= n <= Decimal(500), 'UNBOUNDED_COST_BPS')
    return n / Decimal(10000)


def iso(value):
    need(type(value) is str, 'DATE_TYPE')
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceBlocked('DATE_FORMAT') from exc
    need(d.isoformat() == value, 'DATE_NOT_CANONICAL')
    return d


def canonical_hash(record):
    """Hash metadata and bars; do not put any private records in public logs."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _validate_contract(episode):
    need(type(episode) is dict, 'EPISODE_OBJECT')
    keys = {'episode_id', 'symbol', 'signal_asof', 'data_through', 'source',
            'scope_sha256', 'policy_sha256', 'reference_close', 'stop', 'target', 'bars'}
    need(set(episode) == keys, 'SCHEMA_DRIFT_OR_UNEXPECTED_INPUT')
    symbol = episode['symbol']
    need(type(symbol) is str and IDENT.fullmatch(symbol), 'SYMBOL_INVALID')
    signal = iso(episode['signal_asof'])
    cutoff = iso(episode['data_through'])
    need(episode['episode_id'] == signal.isoformat() + '|' + symbol, 'EPISODE_KEY_CONFLICT')
    need(episode['source'] == SOURCE, 'UNAUTHORIZED_PRICE_SOURCE')
    need(all(type(episode[k]) is str and SHA.fullmatch(episode[k])
             for k in ('scope_sha256', 'policy_sha256')), 'MISSING_SOURCE_POLICY_SHA')
    close, stop, target = (price(episode[k]) for k in ('reference_close', 'stop', 'target'))
    need(stop < close < target, 'ORIGINAL_LEVEL_GEOMETRY')
    need(abs(target - (close + Decimal(2) * (close - stop))) <= Decimal('.025'),
         'ORIGINAL_2R_LEVEL_CHANGED')
    need(type(episode['bars']) is list and len(episode['bars']) <= 15, 'BARS_LIST_LIMIT')
    cal = ec.get_calendar('XNAS')
    need(cal.is_session(signal.isoformat()), 'SIGNAL_NOT_XNAS_SESSION')
    need(cutoff >= signal, 'CUTOFF_BEFORE_SIGNAL')
    seen = set()
    clean = []
    for idx, bar in enumerate(episode['bars'], 1):
        need(type(bar) is dict and set(bar) == {'date', 'open', 'high', 'low', 'close', 'volume'},
             'BAR_SCHEMA')
        day = iso(bar['date'])
        expected = cal.session_offset(cal.date_to_session(signal.isoformat()), idx).date()
        need(day == expected, 'MISSING_OR_OUT_OF_ORDER_XNAS_SESSION')
        need(day <= cutoff, 'FUTURE_BAR_AFTER_CUTOFF')
        need(day not in seen, 'DUPLICATE_BAR')
        seen.add(day)
        values = {k: price(bar[k]) for k in ('open', 'high', 'low', 'close')}
        need(values['low'] <= min(values['open'], values['close']) and
             values['high'] >= max(values['open'], values['close']), 'OHLC_RANGE')
        v = bar['volume']
        need(type(v) in (int, float) and math.isfinite(v) and v > 0,
             'VOLUME_BAD_OR_ILLQUID')
        clean.append({'date': day.isoformat(), **values})
    return close, stop, target, clean


def evaluate_episode(episode, *, entry_cost_bps='15', exit_cost_bps='15'):
    """Two entirely hypothetical views: close-reference and next-IEX-open.

    No valid inference of a real executable fill from IEX EOD alone.
    No same-day close fill; no intrabar ordering assumptions; STOP-FIRST.
    """
    entry_fee = decimal_bps(entry_cost_bps)
    exit_fee = decimal_bps(exit_cost_bps)
    close, stop, target, bars = _validate_contract(episode)
    result = {'episode_id': episode['episode_id'], 'signal_asof': episode['signal_asof'],
              'source': SOURCE, 'source_policy_hash': canonical_hash({
                  'scope_sha256': episode['scope_sha256'],
                  'policy_sha256': episode['policy_sha256']}),
              'proof_hash': canonical_hash(episode), 'session_count': len(bars),
              'status': 'OPEN_CENSORED', 'event': None, 'ambiguous': False,
              'gap': False, 'reference_pct': None, 'next_open_net_pct': None,
              'risk_r': None, 'cost_scenario_bps': [str(entry_cost_bps), str(exit_cost_bps)],
              'real_fill_proven': False, 'notification_sent': False,
              'classification': 'HYPOTHETICAL_IEX_EOD_RESEARCH_ONLY'}
    # At a declared complete data cutoff every finished XNAS session must be
    # observed (until an early terminal touch), or the missing-price witness is
    # BLOCKED, not silently counted as an open/censored outcome.
    cal = ec.get_calendar('XNAS')
    asof = iso(episode['signal_asof'])
    cutoff = iso(episode['data_through'])
    required = min(15, len(cal.sessions_in_range(
        date.fromordinal(asof.toordinal() + 1).isoformat(), cutoff.isoformat())))
    if not bars:
        need(required == 0, 'MISSING_MATURED_XNAS_SESSIONS')
        return result
    first = bars[0]
    entry_open = first['open']
    if not stop < entry_open < target:
        result.update(status='ENTRY_INVALIDATED_BY_GAP', event='NO_ENTRY_OPEN_OUTSIDE_LEVELS',
                      gap=True)
        return result
    effective_entry = entry_open * (Decimal(1) + entry_fee)
    for bar in bars:
        opn, high, low = bar['open'], bar['high'], bar['low']
        hit_s = low <= stop
        hit_t = high >= target
        gap = opn < stop or opn > target
        event = None
        if opn <= stop:
            event, exit_ref = 'STOP_GAP_OPEN', opn
        elif opn >= target:
            event, exit_ref = 'TARGET_GAP_OPEN', opn
        elif hit_s and hit_t:
            event, exit_ref = 'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS', stop
        elif hit_s:
            event, exit_ref = 'STOP_TOUCHED', stop
        elif hit_t:
            event, exit_ref = 'TARGET_TOUCHED', target
        elif len(bars) == 15 and bar is bars[-1]:
            event, exit_ref = 'TIME_EXIT_AT_CLOSE', bar['close']
        if event is None:
            continue
        effective_exit = exit_ref * (Decimal(1) - exit_fee)
        base_profit = (exit_ref / close - 1) * 100
        net_profit = (effective_exit / effective_entry - 1) * 100
        risk = effective_entry - stop
        result.update(status='COMPLETE', event=event, exit_date=bar['date'],
                      days_held=bars.index(bar) + 1,
                      ambiguous=(event == 'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS'),
                      gap=bool(gap), reference_pct=float(base_profit),
                      next_open_net_pct=float(net_profit),
                      risk_r=float((effective_exit - effective_entry) / risk) if risk > 0 else None)
        return result
    need(len(bars) == required, 'MISSING_MATURED_XNAS_SESSIONS')
    return result


def _block_means(items, *, trials=999, seed=20261028):
    """Cluster bootstrap by signal day, preventing same-day episodes as independent draws."""
    groups = defaultdict(list)
    for r in items:
        groups[r['signal_asof']].append(r['next_open_net_pct'])
    dates = sorted(groups)
    rng = random.Random(seed)
    observed = sum(sum(v) for v in groups.values()) / sum(map(len, groups.values()))
    sims = []
    for _ in range(trials):
        sample = [groups[dates[rng.randrange(len(dates))]] for __ in dates]
        sims.append(sum(sum(v) for v in sample) / sum(len(v) for v in sample))
    sims.sort()
    return observed, (sims[int(.025 * (trials - 1))], sims[int(.975 * (trials - 1))])


def scorecard(reports, *, control_net_returns=None, phase='RESEARCH',
              holdout_registration_proven=False):
    """Never auto-promote. Only review when independently registered holdout is proven.

    `control_net_returns` must be independently sourced, matched by episode ID,
    next-open, and same holding span; this function cannot authenticate it.
    """
    need(type(reports) is list, 'REPORTS_LIST')
    keys = [r['episode_id'] for r in reports]
    need(len(set(keys)) == len(keys), 'DUPLICATE_EPISODE_COUNTS')
    good = [r for r in reports if r['status'] == 'COMPLETE']
    censored = len(reports) - len(good)
    n = len(good)
    days = len(set(r['signal_asof'] for r in good))
    score = {'status': 'HOLD_INSUFFICIENT_EVIDENCE', 'execution': 'NONE',
             'automated_rule_change': False, 'n_total': len(reports),
             'n_complete': n, 'n_censored_or_invalidated': censored,
             'n_distinct_signal_days': days, 'min_complete': 60, 'min_days': 20,
             'mean_net_pct': None, 'block_bootstrap_95_pct': None,
             'wilson_win_95': None, 'bayes_win_posterior_mean': None,
             'worst_5pct_trade_mean_pct': None, 'ambiguous_count': sum(r['ambiguous'] for r in good),
             'gap_count': sum(r['gap'] for r in good), 'paired_control': False,
             'relative_edge_mean_pct': None, 'why': [], 'proposals': []}
    if not n:
        score['why'].append('NO_COMPLETED_EPISODES')
        return score
    need(all(type(r['next_open_net_pct']) in (float, int) and math.isfinite(r['next_open_net_pct'])
             for r in good), 'INVALID_NET_RETURN')
    wins = sum(r['next_open_net_pct'] > 0 for r in good)
    phat = wins / n
    z = NormalDist().inv_cdf(.975)
    denom = 1 + z*z/n
    center = (phat + z*z/(2*n)) / denom
    radius = z*math.sqrt(phat*(1-phat)/n + z*z/(4*n*n))/denom
    score['wilson_win_95'] = [round(max(0, center-radius), 6), round(min(1, center+radius), 6)]
    score['bayes_win_posterior_mean'] = round((wins+1)/(n+2), 6)
    m, bounds = _block_means(good)
    score['mean_net_pct'] = round(m, 6)
    score['block_bootstrap_95_pct'] = [round(x, 6) for x in bounds]
    tails = sorted(r['next_open_net_pct'] for r in good)
    score['worst_5pct_trade_mean_pct'] = round(sum(tails[:max(1, math.ceil(n*.05))]) / max(1, math.ceil(n*.05)), 6)
    if n < 60 or days < 20:
        score['why'].append('SAMPLE_OR_DATE_COHORT_TOO_SMALL')
        score['proposals'].append('CONTINUE_READ_ONLY_OBSERVATION')
    if len(reports) and censored / len(reports) > .10:
        score['why'].append('EXCESSIVE_CENSORING_OR_GAP_INVALIDATION')
        score['proposals'].append('AUDIT_MISSING_BAR_AND_ENTRY_GAP')
    if score['ambiguous_count'] / n > .10:
        score['why'].append('INTRADAY_STOP_TARGET_ORDER_UNRESOLVED')
        score['proposals'].append('REQUEST_LICENSED_INTRADAY_ORDER_WITNESS')
    if bounds[1] <= 0:
        score['why'].append('NONPOSITIVE_EDGE_EVEN_AT_UPPER_CI')
        score['proposals'].append('PREREGISTER_FALSIFIABLE_CHALLENGER_NO_AL_CHANGE')
    if phase != 'HOLDOUT' or not holdout_registration_proven:
        score['why'].append('UNPROVEN_FROZEN_INDEPENDENT_HOLDOUT')
    if control_net_returns is None:
        score['why'].append('NO_MATCHED_NEXT_OPEN_CONTROL')
    else:
        need(type(control_net_returns) is dict and set(control_net_returns) == set(keys),
             'CONTROL_MATCHED_EPISODES_REQUIRED')
        need(all(type(v) in (int,float) and math.isfinite(v)
                 for v in control_net_returns.values()), 'CONTROL_NONFINITE')
        score['paired_control'] = True
        score['relative_edge_mean_pct'] = round(sum(r['next_open_net_pct'] -
              control_net_returns[r['episode_id']] for r in good)/n, 6)
        score['why'].append('CONTROL_PROVENANCE_NOT_AUTHENTICATED_BY_FUNCTION')
    # Never production PASS; provenance + registration are external proof obligations.
    score['status'] = 'HOLD_HUMAN_SCIENTIFIC_REVIEW'
    return score


def integrity_alerts(reports):
    """Silent diagnostic events, not ChatGPT notifications. Stable dedup keys."""
    need(type(reports) is list, 'REPORTS_LIST')
    output = []
    for r in reports:
        for code, triggered in (
            ('INCOMPLETE_15_SESSION_WITNESS', r['status'] == 'OPEN_CENSORED'),
            ('ENTRY_GAP_INVALIDATED', r['status'] == 'ENTRY_INVALIDATED_BY_GAP'),
            ('STOP_TARGET_PATH_AMBIGUOUS', r['ambiguous']),
            ('STOP_GAP_SLIPPAGE_EXPOSURE', r.get('event') == 'STOP_GAP_OPEN'),
        ):
            if triggered:
                key = hashlib.sha256((r['episode_id'] + '|' + code + '|' +
                                      r['proof_hash']).encode()).hexdigest()
                output.append({'key': key, 'episode_id': r['episode_id'],
                               'code': code, 'delivery': 'NOT_REQUESTED',
                               'remediation': 'REVIEW_ONLY'})
    return output


def drift_watch(reports, *, deterioration_pp=0.5):
    """Early-vs-late suspicion only; no sequential significance claim."""
    need(type(reports) is list, 'REPORTS_LIST')
    complete = [r for r in reports if r['status'] == 'COMPLETE']
    grouped = defaultdict(list)
    for r in complete:
        need(type(r.get('signal_asof')) is str and
             type(r.get('next_open_net_pct')) in (int, float) and
             math.isfinite(r['next_open_net_pct']), 'DRIFT_BAD_RETURN')
        grouped[r['signal_asof']].append(r['next_open_net_pct'])
    days = sorted(grouped)
    if len(complete) < 40 or len(days) < 20:
        return {'state': 'HOLD_UNDERPOWERED', 'alert': False,
                'rule_change_authorized': False}
    halfway = len(days) // 2
    left = [v for day in days[:halfway] for v in grouped[day]]
    right = [v for day in days[halfway:] for v in grouped[day]]
    early = sum(left) / len(left)
    recent = sum(right) / len(right)
    alert = (early - recent) >= deterioration_pp
    return {'state': 'DRIFT_SUSPECTED_REVIEW_ONLY' if alert else 'NO_FIXED_THRESHOLD_DRIFT',
            'alert': alert, 'early_mean_net_pct': round(early, 6),
            'recent_mean_net_pct': round(recent, 6),
            'deterioration_pp_threshold': deterioration_pp,
            'rule_change_authorized': False,
            'statistical_significance_proven': False}


CHALLENGER_LEVERS = frozenset((
    'RSI_BAND_RESEARCH', 'RVOL_RESEARCH', 'ATR_RISK_RESEARCH',
    'LIQUIDITY_RESEARCH', 'ENTRY_TIME_RESEARCH'))


def challenger_card(score, *, hypothesis_id, lever, proposed_falsifier, baseline_sha):
    """Machine-verifiable pre-registration draft, NEVER actual strategy code."""
    need(type(hypothesis_id) is str and re.fullmatch(r'XRAY-H-[0-9]{4}', hypothesis_id),
         'HYPOTHESIS_ID')
    need(lever in CHALLENGER_LEVERS, 'UNSAFE_OR_UNREGISTERED_LEVER')
    need(type(proposed_falsifier) is str and 20 <= len(proposed_falsifier) <= 400,
         'EXPLICIT_FALSIFIER_REQUIRED')
    need(type(baseline_sha) is str and SHA.fullmatch(baseline_sha), 'FROZEN_BASELINE_SHA')
    need(type(score) is dict and score.get('execution') == 'NONE' and
         score.get('automated_rule_change') is False, 'SCORE_NOT_RESEARCH_ONLY')
    return {'hypothesis_id': hypothesis_id, 'lever': lever,
            'falsifier': proposed_falsifier,
            'baseline_sha': baseline_sha, 'research_status': 'PROPOSED_NOT_TESTED',
            'next_gate': 'PREREGISTER_THEN_NEW_SESSIONS_AND_WALK_FORWARD_HOLDOUT',
            'release': 'NO_GO', 'main_merge_authorized': False,
            'AL_CHANGE': False, 'trading_order_authorized': False,
            'source_evidence_required': True}
