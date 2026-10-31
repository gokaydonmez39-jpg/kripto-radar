#!/usr/bin/env python3
"""XRAY NASDAQ: Alpaca connected-app CA sample audit, offline / no output authority.

This module NEVER fetches data, sends an alert or changes a trading decision.
Only the externally supplied connector reply is inspected. No completeness
or point-in-time first-known evidence is inferred from a sample.
"""
from datetime import date, datetime, timezone
from uuid import UUID
import math
import re

SCHEMA = 'XRAY_NASDAQ_ALPACA_CONNECTOR_SHADOW_V1'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.]{0,15}\Z')
GROUP_KIND = {'cash_dividends': 'cash_dividend'}

class SampleRejected(ValueError):
    pass

def need(condition, reason):
    if not condition:
        raise SampleRejected(reason)

def canonical_date(value):
    need(type(value) is str and len(value) == 10, 'DATE_INVALID')
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise SampleRejected('DATE_INVALID') from exc
    need(result.isoformat() == value, 'DATE_NOT_CANONICAL')
    return result

def utc_instant(value):
    need(type(value) is str and len(value) <= 40, 'OBSERVATION_TIME_INVALID')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SampleRejected('OBSERVATION_TIME_INVALID') from exc
    need(result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
         'OBSERVATION_TIME_NOT_UTC')
    return result.astimezone(timezone.utc)

def audit_connector_sample(payload, *, symbols, start, end, observed_at_utc):
    """Accept only a narrowly evidenced connector response contract.

    The expected symbols, interval and observation time must be obtained
    independently; never trust the payload to define its own reference truth.
    Currently cash dividends only: all unknown kinds fail closed.
    """
    timestamp = utc_instant(observed_at_utc)
    first, last = canonical_date(start), canonical_date(end)
    need(first <= last <= timestamp.date(), 'REQUEST_DATE_NOT_YET_AVAILABLE')
    need(type(symbols) is list and 1 <= len(symbols) <= 25, 'SYMBOL_SCOPE_INVALID')
    need(all(type(s) is str and SYMBOL.fullmatch(s) for s in symbols),
         'SYMBOL_SCOPE_INVALID')
    need(len(set(symbols)) == len(symbols), 'SYMBOL_SCOPE_DUPLICATE')
    need(type(payload) is dict and type(payload.get('request')) is dict and
         type(payload.get('announcements')) is dict, 'CONNECTOR_SHAPE_INVALID')
    request, groups = payload['request'], payload['announcements']
    need(request.get('start') == start and request.get('end') == end,
         'REQUEST_DATE_MISMATCH')
    need(type(request.get('symbols')) is list and request['symbols'] == symbols,
         'REQUEST_SYMBOL_SCOPE_MISMATCH')
    limit = request.get('limit')
    need(type(limit) is int and 1 <= limit <= 1000, 'LIMIT_INVALID')
    need(request.get('sort') in ('asc', 'desc'), 'SORT_UNKNOWN')
    need(request.get('cusips') is None and request.get('ids') is None,
         'ADDITIONAL_QUERY_FILTER_NOT_REVIEWED')
    # A grouped connected-app sample is not the raw provider HTTP envelope.
    # Treat an explicit next-page token as INCOMPLETE and an omitted token
    # as UNATTESTED, never fabricate provider pagination proof.
    page_token = payload.get('next_page_token')
    need(page_token is None or type(page_token) is str,
         'PAGINATION_TOKEN_INVALID')
    need(not page_token, 'PAGINATION_INCOMPLETE')
    need(request.get('data_quality') in (None, 'all', 'complete'),
         'DATA_QUALITY_INVALID')
    need(request.get('region') in (None, 'us', 'non_us', 'all'),
         'REGION_INVALID')
    kinds = request.get('ca_types')
    need(kinds is None or kinds == ['cash_dividend'],
         'UNVERIFIED_CORPORATE_ACTION_FILTER')
    need(set(groups).issubset(GROUP_KIND), 'UNSUPPORTED_CONNECTOR_CA_GROUP')
    events, known_ids = [], set()
    for group, items in groups.items():
        need(type(items) is list, 'GROUP_ITEMS_INVALID')
        for row in items:
            need(type(row) is dict, 'EVENT_ROW_INVALID')
            uid = row.get('id')
            need(type(uid) is str, 'EVENT_ID_INVALID')
            try:
                parsed = UUID(uid)
            except (ValueError, AttributeError, TypeError) as exc:
                raise SampleRejected('EVENT_ID_INVALID') from exc
            need(str(parsed) == uid.lower() and uid not in known_ids,
                 'EVENT_ID_DUPLICATE_OR_NONCANONICAL')
            known_ids.add(uid)
            ticker = row.get('symbol')
            need(type(ticker) is str and ticker in symbols,
                 'EVENT_SYMBOL_OUTSIDE_SCOPE')
            need(row.get('corporate_action_type') == group, 'EVENT_KIND_MISMATCH')
            processed = canonical_date(row.get('process_date'))
            need(first <= processed <= last, 'EVENT_OUTSIDE_REQUEST_WINDOW')
            need(processed <= timestamp.date(), 'FUTURE_EVENT_USE')
            ex_day = canonical_date(row.get('ex_date'))
            record_day = canonical_date(row.get('record_date'))
            payable_day = canonical_date(row.get('payable_date'))
            rate = row.get('rate')
            need(type(rate) in (float, int) and math.isfinite(rate) and rate > 0,
                 'DIVIDEND_RATE_INVALID')
            events.append({
                'id': uid, 'symbol': ticker, 'type': GROUP_KIND[group],
                'process_date': processed.isoformat(), 'ex_date': ex_day.isoformat(),
                'record_date': record_day.isoformat(),
                'payable_date': payable_day.isoformat(), 'rate': rate,
                'conclusion': 'HISTORICAL_DIVIDEND_REVIEW_ONLY'
            })
    need(len(events) <= limit, 'RESPONSE_EXCEEDS_REQUESTED_LIMIT')
    # The connector's sort convention is not proven to be process_date;
    # exposing a monotonicity observation is not evidence of completeness.
    dates = [e['process_date'] for e in events]
    sorted_by_process_date = all(
        dates[i-1] <= dates[i] for i in range(1, len(dates))) if (
        request['sort']=='asc') else all(
        dates[i-1] >= dates[i] for i in range(1, len(dates)))
    return {
        'schema': SCHEMA,
        'status': 'CAP_REACHED_COVERAGE_UNKNOWN' if len(events) == limit
                  else 'CONNECTOR_ORDER_DISPUTE_REVIEW_REQUIRED' if (
                      events and not sorted_by_process_date)
                  else 'SAMPLE_FOR_REVIEW' if events else 'NO_EVENTS_SAMPLED_NOT_CLEAR',
        'source': 'ALPACA_CONNECTED_APP_GROUPED_CORPORATE_ACTIONS',
        'requested_symbols': symbols.copy(), 'request_start': start, 'request_end': end,
        'observed_at_utc': timestamp.isoformat().replace('+00:00', 'Z'),
        'event_count': len(events), 'events': events,
        'process_date_order_matches_requested_sort': sorted_by_process_date,
        'process_date_order_semantics_verified': False,
        'connector_exposed_next_page_token': 'next_page_token' in payload,
        'connector_exposed_data_quality': request.get('data_quality') is not None,
        'default_complete_can_exclude_early_incomplete_events': True,
        'all_early_provider_events_proven': False,
        'pagination_complete_proven': False, 'provider_known_at_proven': False,
        'market_event_absence_proven': False, 'source_data_rights_proven': False,
        'historical_pit_proven': False, 'may_generate_al': False,
        'may_modify_stop_target': False, 'may_notify': False,
        'may_place_order': False, 'may_write_private_sheets': False,
        'vendor_calls_made_by_bridge': 0
    }
