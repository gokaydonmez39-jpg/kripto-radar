#!/usr/bin/env python3
"""XRAY v47: retrospective-symbol mapping guard, OFFLINE hypothetical queries only.

Alpaca's historical trades `asof` parameter identifies the underlying entity
and may relabel historical rows with a current symbol. Therefore an output
symbol alone cannot establish the exchange where an old trade was executed.
Only the narrow 2025-10-29..2026-10-22 Fiserv FI/NYSE -> FISV/Nasdaq
transition is discussed; not a historical security master.

Sources: RT-222 https://docs.alpaca.markets/us/reference/stocktrades-1
         RT-240 https://www.sec.gov/Archives/edgar/data/798354/000119312525254670/d17957d8k.htm
         RT-263 https://www.sec.gov/Archives/edgar/data/798354/000079835426000009/fi-20251231.htm
NO NETWORK, NO DATA, NO ORDERS, NO LICENSE, NO MARKET OR SIGNAL AUTHORITY.
"""
from __future__ import annotations

from datetime import date
import re

SCHEMA = 'XRAY_V47_OFFLINE_PIT_ALIAS_RISK_V1'
TRANSITION = date(2025, 11, 11)
FIRST = date(2025, 10, 29)
LAST = date(2026, 10, 22)
RETRO_DISCLOSURE = date(2026, 2, 19)
ALLOWED = frozenset(('FI', 'FISV'))

class AliasBlocked(ValueError):
    pass


def need(x: bool, reason: str) -> None:
    if x is not True:
        raise AliasBlocked('XRAY_V47_' + reason)


def day(value: object) -> date:
    need(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None,
         'DATE_FORMAT')
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise AliasBlocked('XRAY_V47_INVALID_DATE') from exc
    need(result.isoformat() == value, 'DATE_CANONICAL')
    return result


def audit(query: object) -> dict:
    """Return a BLOCKED risk classification, NOT a vendor query or rights grant."""
    need(type(query) is dict and set(query) == {
        'schema', 'sample_type', 'issuer_cik', 'query_symbol', 'returned_label',
        'api_asof', 'window_first', 'window_last', 'decision_asof', 'feed'
    }, 'QUERY_SCHEMA')
    need(query['schema'] == SCHEMA and
         query['sample_type'] == 'OFFLINE_HYPOTHETICAL_NOT_PROVIDER_DATA',
         'SYNTHETIC_ONLY')
    need(type(query['issuer_cik']) is str and query['issuer_cik'] == '0000798354',
         'ISSUER_CIK')
    need(type(query['query_symbol']) is str and query['query_symbol'] in ALLOWED and
         type(query['returned_label']) is str and query['returned_label'] in ALLOWED,
         'SYMBOL_SCOPE')
    need(type(query['feed']) is str and query['feed'] == 'sip', 'FEED_SCOPE')
    first, last, decision = (day(query[k]) for k in
                             ('window_first', 'window_last', 'decision_asof'))
    need(FIRST <= first <= last <= LAST, 'WINDOW_SCOPE')
    need(last <= decision <= LAST, 'DECISION_SCOPE')
    asof = query['api_asof']
    need(type(asof) is str, 'ASOF_TYPE')
    no_mapping = asof == '-'
    asof_date = None if no_mapping else day(asof)
    need(asof_date is None or FIRST <= asof_date <= LAST, 'ASOF_SCOPE')

    crosses = first < TRANSITION <= last
    pre_transfer = first < TRANSITION
    after_transfer = last >= TRANSITION
    future_identity = asof_date is not None and asof_date > decision
    # A current-symbol label is NEVER venue evidence. The documented mapping
    # rule makes the label specifically risky for FI pre-transfer intervals.
    retrospective_alias_risk = (pre_transfer and not no_mapping and
                                asof_date is not None and asof_date >= TRANSITION and
                                query['query_symbol'] == 'FISV')
    # An `asof=-` request disables mapping, but that STILL does not prove
    # historical listing/venue or missing old symbols.
    if future_identity:
        status = 'FUTURE_API_ASOF_LOOKAHEAD_BLOCKED'
    elif crosses:
        status = 'CROSS_TRANSITION_VENUE_PARTITION_REQUIRED'
    elif retrospective_alias_risk:
        status = 'HISTORIC_NYSE_TRADE_MAY_BE_RELABELLED_FISV'
    elif no_mapping:
        status = 'ASOF_MAPPING_SKIPPED_VENUE_UNATTESTED'
    else:
        status = 'SEC_TRANSITION_RESEARCH_ONLY_DAILY_LISTING_UNATTESTED'
    return {
        'schema': 'XRAY_V47_HISTORICAL_SYMBOL_MAPPING_RISK_SHADOW_V1',
        'status': status,
        'window_crosses_2025_11_11_listing_transfer': crosses,
        'window_contains_pre_transfer_dates': pre_transfer,
        'window_contains_post_transfer_dates': after_transfer,
        'api_asof_is_after_historical_decision': future_identity,
        'api_asof_mapping_disabled': no_mapping,
        'retrospective_alias_risk': retrospective_alias_risk,
        'return_symbol_is_historical_listing_evidence': False,
        'sec_8k_2025_10_29_plan_is_realization_proof': False,
        'sec_10k_retrospective_confirmation_known_asof_decision': decision > RETRO_DISCLOSURE,
        'sec_filing_intraday_cutoff_attested': False,
        'historic_original_symbols_per_record_attested': False,
        'original_trade_venue_per_record_attested': False,
        'daily_venue_master_independently_checked': False,
        'a0_account_rights_verified': False,
        'a1_listing_scope_release_ready': False,
        'a2_actual_historical_pages_verified': False,
        'a3_sip_correction_volume_verified': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'broker': False,
        'orders': [],
        'execution': 'NONE',
        'real_money': 'NO-GO',
        'unknown_never_pass': True,
    }

if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('hypothetical_query', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.hypothetical_query.read_text(encoding='utf-8'))),
                     indent=2, sort_keys=True))