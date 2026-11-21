#!/usr/bin/env python3
"""XRAY A1: Offline, fixed-epoch calendar consistency witness (NOT price or A1 GO).

Consumes a specific saved Alpaca calendar response for 2026-09-01..2026-10-22.
Cross-checks *weekday/holiday structure* using official Nasdaq 2026 holiday list.
Does not prove symbol listing venue, live hours, historical SIP, any rights or release.
No provider calls, file writes, broker, orders, or signed attestation.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
import hashlib
import json

SCHEMA = 'XRAY_A1_ALPACA_CALENDAR_SNAPSHOT_20261022_RESEARCH_V1'
RANGE_START = date(2026, 9, 1)
ASOF = date(2026, 10, 22)
OFFICIAL_HOLIDAYS_IN_WINDOW = {date(2026, 9, 7)}
DOC = 'https://www.nasdaqtrader.com/trader.aspx?id=Calendar'
ALPACA_DOC = 'https://docs.alpaca.markets/us/v1.1/reference/getcalendar-1'

class ScopeBlocked(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if condition is not True:
        raise ScopeBlocked('XRAY_A1_' + reason)


def expected_days() -> list[str]:
    current = RANGE_START
    result = []
    while current <= ASOF:
        if current.weekday() < 5 and current not in OFFICIAL_HOLIDAYS_IN_WINDOW:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def audit(payload: dict) -> dict:
    need(type(payload) is dict, 'OBJECT')
    need(payload.get('schema') == SCHEMA, 'SCHEMA')
    need(payload.get('range_start') == RANGE_START.isoformat() and
         payload.get('asof_et') == ASOF.isoformat(), 'EPOCH')
    need(payload.get('source_type') == 'CONNECTED_ALPACA_CALENDAR_READ' and
         payload.get('provider_reference') == ALPACA_DOC and
         payload.get('official_holiday_reference') == DOC, 'PROVENANCE')
    rows = payload.get('calendar')
    need(type(rows) is list and len(rows) == len(expected_days()), 'FULL_ROW_COUNT')
    names = []
    for row in rows:
        need(type(row) is dict and set(row) == {'date', 'open', 'close'}, 'ROW_SHAPE')
        d, opening, closing = row['date'], row['open'], row['close']
        need(all(type(x) is str for x in (d, opening, closing)), 'ROW_STRING')
        try:
            day = date.fromisoformat(d)
            op = datetime.fromisoformat(opening)
            cl = datetime.fromisoformat(closing)
        except ValueError as exc:
            raise ScopeBlocked('XRAY_A1_TIMESTAMP_INVALID') from exc
        need(day.isoformat() == d and
             opening == d + 'T09:30:00' and closing == d + 'T16:00:00' and
             op.date() == cl.date() == day and op < cl, 'CLOCK_OR_EARLY_CLOSE')
        names.append(d)
    expected = expected_days()
    need(names == expected, 'DAY_SET_ORDER_HOLIDAY_GAP')
    need(expected[-30] == '2026-09-11' and expected[-1] == ASOF.isoformat(), 'LAST30')
    need({'2026-10-07', '2026-10-15'} <= set(expected[-30:]), 'KNOWN_INCIDENT_DATES')
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {
        'schema': 'XRAY_V43_A1_CALENDAR_PARTIAL_SHADOW_V1',
        'asof_et': ASOF.isoformat(),
        'sample_source': 'SAVED_CONNECTED_ALPACA_CALENDAR_ROWS',
        'independent_official_holiday_rule_corroborated': True,
        'calendar_rows_checked': len(rows),
        'last_30_trading_dates_first': expected[-30],
        'last_30_trading_dates_last': expected[-1],
        'last_30_trading_dates_count': 30,
        'sessions_with_early_close_in_sample': 0,
        'requires_post_backfill_recheck': ['2026-10-07', '2026-10-15'],
        'calendar_rows_canonical_sha256': digest,
        'a1_calendar_date_time_subscope_checked': True,
        'official_symbol_venue_listing_scope_attested': False,
        'official_session_exceptions_exhaustive_attested': False,
        'historical_trade_or_quote_data_checked': False,
        'a1_release_ready': False,
        'a0_account_rights_attested': False,
        'a2_pagination_complete': False,
        'a3_sip_settled_volume_pass': False,
        'canonical_price_pass': False,
        'issuer_mc_pass': False,
        'g9_pass': False,
        'c417_pass': False,
        'registered_r92_count': 0,
        'iphone_receipt_attested': False,
        'execution': 'NONE',
        'real_money': 'NO-GO',
        'broker': False,
        'orders': [],
        'unknown_never_pass': True,
        'status': 'CALENDAR_DATE_TIME_SUBSCOPE_ONLY_NOT_RELEASE',
    }


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.snapshot.read_text(encoding='utf-8'))), sort_keys=True, indent=2))