#!/usr/bin/env python3
"""XRAY A3: Alpaca-specific, TAPE-C, synthetic trade-condition bar logic.

Reference: https://docs.alpaca.markets/us/docs/market-data-faq (RT-098)
IMPORTANT: this is not official UTP consolidated-volume accounting, not a
correction/cancel replay, and cannot attest any actual provider data coverage.
No network, vendor calls, secrets, account data, orders, or real market prices.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

SCHEMA = 'XRAY_V49_ALPACA_TAPE_C_CONDITION_SYNTHETIC_ONLY_V1'
SOURCE = 'https://docs.alpaca.markets/us/docs/market-data-faq'
SAMPLE = 'ILLUSTRATIVE_SYNTHETIC_TRADES_NO_MARKET_AUTHORITY'

# open/close: 0 never, 1 only if field has not been set, 2 always eligible
# high/low: 0 never, 1 eligible; volume: 0 never, 1 eligible
# Small, explicitly checked subset of Alpaca's provider implementation.
# These are NOT the complete raw UTP/CTS sale-condition tables.
RULES = {
    '@': {'M': (2, 1, 1), 'D': (2, 1, 1)},
    'I': {'M': (0, 0, 1), 'D': (0, 0, 1)},
    'R': {'M': (0, 0, 1), 'D': (0, 0, 1)},
    'W': {'M': (0, 0, 1), 'D': (0, 0, 1)},
    '4': {'M': (0, 0, 1), 'D': (1, 1, 1)},
    'P': {'M': (0, 0, 1), 'D': (1, 1, 1)},
    'Z': {'M': (0, 0, 1), 'D': (1, 1, 1)},
    'T': {'M': (2, 1, 1), 'D': (0, 0, 1)},
    '9': {'M': (0, 0, 0), 'D': (2, 1, 0)},
    'M': {'M': (0, 0, 0), 'D': (0, 0, 0)},
    'Q': {'M': (0, 0, 0), 'D': (0, 0, 0)},
    'Y': {'M': (2, 1, 1), 'D': (2, 1, 1)},
    '6': {'M': (2, 1, 1), 'D': (2, 1, 1)},
}

class ConditionBlocked(ValueError):
    pass


def need(b: bool, reason: str) -> None:
    if b is not True:
        raise ConditionBlocked('XRAY_V49_' + reason)


def eligibility(conditions: Any, bar_kind: str) -> tuple[int, int, int]:
    need(bar_kind in ('M', 'D'), 'BAR_KIND')
    need(type(conditions) is list and 1 <= len(conditions) <= 4 and
         all(type(c) is str and len(c) == 1 and c in RULES for c in conditions),
         'UNKNOWN_OR_EMPTY_SALE_CONDITION')
    need(len(set(conditions)) == len(conditions), 'DUPLICATE_SALE_CONDITION')
    return tuple(min(RULES[c][bar_kind][n] for c in conditions) for n in range(3))


def parse_price(p: Any) -> Decimal:
    need(type(p) is str and 0 < len(p) <= 24 and 'e' not in p.lower(),
         'SYNTHETIC_PRICE_STRING')
    try:
        d = Decimal(p)
    except InvalidOperation as e:
        raise ConditionBlocked('XRAY_V49_SYNTHETIC_PRICE_PARSE') from e
    need(d.is_finite() and d > 0 and d <= 100000, 'SYNTHETIC_PRICE_BOUND')
    return d


def synth_bar(rows: Any, kind: str) -> dict:
    """Internal hypothetical arithmetic; explicitly excludes real market-data use."""
    need(type(rows) is list and 1 <= len(rows) <= 32, 'SYNTHETIC_ROW_COUNT')
    need(kind in ('M', 'D'), 'SYNTHETIC_BAR_KIND')
    op = hi = lo = cl = None
    volume = vwap_basis = 0
    price_volume = Decimal(0)
    for row in rows:
        need(type(row) is dict and set(row) == {'conditions', 'synthetic_price', 'synthetic_size'},
             'SYNTHETIC_ROW_SCHEMA')
        conditions = row['conditions']
        oc, hl, v = eligibility(conditions, kind)
        size = row['synthetic_size']
        need(type(size) is int and 0 <= size <= 100000, 'SYNTHETIC_SIZE')
        # The corrected-consolidated-close report may carry zero volume.
        need(size > 0 or conditions == ['9'], 'ZERO_SIZE_NOT_CORRECTED_CLOSE')
        p = parse_price(row['synthetic_price'])
        if oc and op is None:
            op = p
        if oc == 2 or (oc == 1 and cl is None):
            cl = p
        if hl:
            hi = p if hi is None else max(hi, p)
            lo = p if lo is None else min(lo, p)
        if v:
            volume += size
        if hl and v:
            vwap_basis += size
            price_volume += p * size
    emitted = all(v is not None and v != 0 for v in (op, hi, lo, cl)) and volume > 0
    return {
        'synthetic_open': op, 'synthetic_high': hi, 'synthetic_low': lo,
        'synthetic_close': cl, 'synthetic_bar_volume': volume,
        'synthetic_vwap_basis': vwap_basis,
        'synthetic_vwap': price_volume / vwap_basis if vwap_basis else None,
        'synthetic_bar_emitted': emitted,
    }


def audit(document: Any) -> dict:
    need(type(document) is dict and set(document) ==
         {'schema', 'sample_type', 'reference', 'tape', 'cases'}, 'SCHEMA')
    need(document['schema'] == SCHEMA and document['sample_type'] == SAMPLE and
         document['reference'] == SOURCE and document['tape'] == 'C', 'SOURCE_SCOPE')
    cases = document['cases']
    need(type(cases) is list and len(cases) == 3, 'THREE_REQUIRED_CASES')
    by_name = {}
    for case in cases:
        need(type(case) is dict and set(case) == {'name', 'synthetic_trades'},
             'CASE_SCHEMA')
        need(type(case['name']) is str and case['name'] not in by_name,
             'CASE_UNIQUE_NAME')
        by_name[case['name']] = case['synthetic_trades']
    need(set(by_name) == {'ODDLOT_ONLY','ODDLOT_AND_REGULAR','DAILY_CORRECTED_CLOSE'},
         'EXPECTED_CASES')
    odd_m = synth_bar(by_name['ODDLOT_ONLY'], 'M')
    odd_d = synth_bar(by_name['ODDLOT_ONLY'], 'D')
    need(not odd_m['synthetic_bar_emitted'] and not odd_d['synthetic_bar_emitted'] and
         odd_m['synthetic_bar_volume'] > 0, 'ODDLOT_BAR_EMISSION_CONTRADICTION')
    mixed_m = synth_bar(by_name['ODDLOT_AND_REGULAR'], 'M')
    mixed_d = synth_bar(by_name['ODDLOT_AND_REGULAR'], 'D')
    need(mixed_m['synthetic_bar_emitted'] and mixed_d['synthetic_bar_emitted'] and
         mixed_d['synthetic_bar_volume'] > mixed_d['synthetic_vwap_basis'],
         'BAR_VOLUME_AND_VWAP_DENOMINATOR_DIFFERENCE')
    corrected_m = synth_bar(by_name['DAILY_CORRECTED_CLOSE'], 'M')
    corrected_d = synth_bar(by_name['DAILY_CORRECTED_CLOSE'], 'D')
    need(corrected_d['synthetic_bar_emitted'] and corrected_m['synthetic_bar_emitted'] and
         corrected_d['synthetic_close'] != corrected_m['synthetic_close'] and
         corrected_d['synthetic_bar_volume'] == corrected_m['synthetic_bar_volume'],
         'CORRECTED_CLOSE_VOLUME_SEPARATION')
    serialized = json.dumps(document,sort_keys=True,separators=(',', ':'),ensure_ascii=False)
    return {
        'schema': 'XRAY_V49_A3_CONDITION_RISK_SHADOW_V1',
        'synthetic_cases_checked': 3,
        'provider_specific_partial_table_only': True,
        'oddlot_only_bar_may_be_absent_despite_trades': True,
        'synthetic_bar_volume_and_vwap_denominator_can_differ': True,
        'corrected_close_can_move_daily_close_without_increasing_volume': True,
        'synthetic_fixture_sha256': sha256(serialized.encode()).hexdigest(),
        'complete_sale_condition_table_verified': False,
        'actual_sip_trade_cancel_correction_replayed': False,
        'official_settled_consolidated_volume_reconciled': False,
        'closing_auction_volume_reconciled': False,
        'rth_vs_extended_hours_partition_attested': False,
        'a0_rights_attested': False,
        'a1_venue_session_attested': False,
        'a2_live_pages_attested': False,
        'a3_release_ready': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'execution': 'NONE', 'real_money': 'NO-GO', 'broker': False,
        'orders': [], 'unknown_never_pass': True,
        'status': 'OFFLINE_CONDITION_COUNTEREXAMPLES_ONLY_NO_MARKET_AUTHORITY',
    }


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('synthetic_fixture', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.synthetic_fixture.read_text(encoding='utf-8'))),indent=2,sort_keys=True))