#!/usr/bin/env python3
"""XRAY A2: synthetic-only historical Alpaca SIP pagination contract.

Enforces API *shape*, not API availability, source completeness, entitlements,
canonical price, or R92. No network, vendor data, credentials or orders.
Reference: https://docs.alpaca.markets/us/reference/stocktrades-1 (RT-222)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any

SCHEMA = 'XRAY_V46_A2_SYNTHETIC_STOCK_TRADES_PAGINATION_V1'
SYNTHETIC = 'OFFLINE_SYNTHETIC_FIXTURE_NOT_PROVIDER_DATA'
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})\Z')
SYMBOL = re.compile(r'[A-Z][A-Z0-9]{0,6}\Z')
TOKEN = re.compile(r'[a-z][a-z0-9_]{0,31}\Z')

class PaginationBlocked(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if ok is not True:
        raise PaginationBlocked('XRAY_V46_' + code)


def time_ns(value: Any) -> int:
    need(type(value) is str, 'TIMESTAMP_TYPE')
    match = TIMESTAMP.fullmatch(value)
    need(match is not None, 'TIMESTAMP_RFC3339')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        need(dt.tzinfo is not None and dt.utcoffset() is not None,
             'TIMESTAMP_TZ')
        utc = dt.astimezone(timezone.utc).replace(microsecond=0)
        delta = utc - datetime(1970, 1, 1, tzinfo=timezone.utc)
        sec = delta.days * 86400 + delta.seconds
    except (ValueError, OverflowError) as exc:
        raise PaginationBlocked('XRAY_V46_TIMESTAMP_INVALID') from exc
    sub = int((match.group(1) or '').ljust(9, '0') or '0')
    return sec * 1_000_000_000 + sub


def audit(document: Any) -> dict:
    need(type(document) is dict and set(document) ==
         {'schema', 'sample_type', 'source_reference', 'query', 'pages'},
         'DOC_SCHEMA')
    need(document['schema'] == SCHEMA and document['sample_type'] == SYNTHETIC and
         document['source_reference'] ==
         'https://docs.alpaca.markets/us/reference/stocktrades-1',
         'SYNTHETIC_SOURCE_ONLY')
    q = document['query']
    need(type(q) is dict and set(q) ==
         {'symbols', 'start', 'end', 'asof', 'feed', 'sort', 'limit'},
         'QUERY_SCHEMA')
    symbols = q['symbols']
    need(type(symbols) is list and 1 <= len(symbols) <= 10 and
         all(type(s) is str and SYMBOL.fullmatch(s) for s in symbols) and
         symbols == sorted(set(symbols)), 'SYMBOL_SCOPE')
    need(q['feed'] == 'sip' and q['sort'] == 'asc', 'FEED_SORT')
    need(type(q['limit']) is int and 1 <= q['limit'] <= 10000, 'PAGE_LIMIT')
    start, end = time_ns(q['start']), time_ns(q['end'])
    need(start < end, 'TIME_RANGE')
    need(type(q['asof']) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',q['asof'])
         is not None, 'ASOF')
    try:
        parsed_asof = date.fromisoformat(q['asof'])
    except ValueError as exc:
        raise PaginationBlocked('XRAY_V46_ASOF_INVALID') from exc
    need(parsed_asof.isoformat() == q['asof'], 'ASOF_CANONICAL')
    pages = document['pages']
    need(type(pages) is list and 1 <= len(pages) <= 1000, 'PAGE_COUNT')
    token = None
    used_tokens: set[str] = set()
    seen_ids: set[str] = set()
    counts = {symbol: 0 for symbol in symbols}
    previous: tuple[int, int] | None = None
    total = 0
    positions = {s: n for n, s in enumerate(symbols)}
    for index, page in enumerate(pages):
        need(type(page) is dict and set(page) ==
             {'requested_page_token','next_page_token','query','synthetic_rows'},
             'PAGE_SCHEMA')
        need(page['query'] == q and type(page['query']) is dict,
             'QUERY_DRIFT')
        need(page['requested_page_token'] == token, 'TOKEN_CHAIN_BROKEN')
        rows = page['synthetic_rows']
        need(type(rows) is list and 0 < len(rows) <= q['limit'],
             'ROW_COUNT_OR_PAGE_LIMIT')
        for row in rows:
            need(type(row) is dict and set(row) == {'S','t','synthetic_key'},
                 'ROW_SCHEMA_NO_VENDOR_PAYLOAD')
            symbol, key = row['S'], row['synthetic_key']
            need(type(symbol) is str and symbol in positions, 'UNEXPECTED_SYMBOL')
            need(type(key) is str and re.fullmatch(r'syn_[a-z0-9_]{1,32}', key)
                 is not None and key not in seen_ids, 'SYNTHETIC_ID_DUPLICATE')
            when = time_ns(row['t'])
            need(start <= when <= end, 'ROW_OUTSIDE_QUERY')
            marker = (positions[symbol], when)
            need(previous is None or marker >= previous,
                 'SYMBOL_FIRST_NANO_ORDER')
            previous = marker
            counts[symbol] += 1
            total += 1
            seen_ids.add(key)
        nxt = page['next_page_token']
        if nxt is not None:
            need(type(nxt) is str and TOKEN.fullmatch(nxt) is not None and
                 nxt not in used_tokens, 'TOKEN_CYCLE_OR_FORMAT')
            need(index < len(pages) - 1, 'MISSING_REQUEST_FOR_NEXT_TOKEN')
            used_tokens.add(nxt)
        else:
            need(index == len(pages) - 1, 'EARLY_TERMINAL_PAGE')
        token = nxt
    need(token is None, 'UNCONSUMED_PAGE_TOKEN')
    # The hash is over our synthetic fixture only, never actual market data.
    digest = hashlib.sha256(json.dumps(document,ensure_ascii=False,sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()
    return {
        'schema': 'XRAY_V46_SYNTHETIC_A2_PAGINATION_SHADOW_RESULT_V1',
        'source_reference_id': 'RT-222',
        'synthetic_page_contract_checked': True,
        'fixture_page_count': len(pages),
        'fixture_synthetic_rows_count': total,
        'fixture_symbol_counts': counts,
        'synthetic_page_tokens_exhausted': True,
        'synthetic_fixture_sha256': digest,
        'actual_provider_request_performed': False,
        'actual_sip_pages_attested': False,
        'provider_entitlements_attested': False,
        'real_session_volume_reconciled': False,
        'a0_release_ready': False,
        'a2_release_ready': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'broker': False,
        'execution': 'NONE',
        'real_money': 'NO-GO',
        'unknown_never_pass': True,
        'status': 'SYNTHETIC_PAGINATION_ONLY_NO_PROVIDER_AUTHORITY',
    }


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('synthetic_fixture', type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.synthetic_fixture.read_text(encoding='utf-8')))
    print(json.dumps(result, sort_keys=True, indent=2))