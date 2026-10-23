#!/usr/bin/env python3
"""XRAY v36 read-only, OFFLINE SIP trade cancellation/correction replay.

Processes ALPACA's documented streaming events (T=t/c/x) only when a
caller has a genuinely complete, authorized stream with original trade IDs.
It CANNOT reconstruct 30 historical sessions from REST 'u' flags alone.
This program makes NO HTTP calls, uses NO broker, writes NO vendor records,
and NEVER gives canonical PRICE/MC/G9/C4.17/R92 authority.
References: https://docs.alpaca.markets/us/v1.1/docs/real-time-stock-pricing-data
            https://www.utpplan.com/DOC/UtpBinaryOutputSpec.pdf
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
from decimal import Decimal, InvalidOperation
from typing import Any

SCHEMA = 'XRAY_V36_OFFLINE_SIP_TRADE_EVENT_REPLAY_V1'
ET = ZoneInfo('America/New_York')

class EvidenceBlocked(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise EvidenceBlocked('XRAY_V36_' + code)


def price(value: Any) -> Decimal:
    require(type(value) in (int, float, str), 'PRICE_TYPE')
    try:
        p = Decimal(str(value))
    except InvalidOperation as exc:
        raise EvidenceBlocked('XRAY_V36_PRICE_PARSE') from exc
    require(p.is_finite() and p > 0, 'PRICE_INVALID')
    return p


def _identity(ev: dict, trade_id: Any) -> tuple[str, int]:
    require(type(ev.get('x')) is str and len(ev['x']) == 1, 'EXCHANGE')
    require(type(trade_id) is int and trade_id > 0, 'TRADE_ID')
    return (ev['x'], trade_id)


def _time(ev: dict) -> int:
    # Alpaca SIP timestamps can have nanosecond resolution. datetime alone
    # truncates the last three digits and can miss a backwards event.
    raw = ev.get('t')
    require(type(raw) is str, 'TIMESTAMP')
    match = re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        r'(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})', raw)
    require(match is not None, 'TIMESTAMP_RFC3339_NANO')
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError as exc:
        raise EvidenceBlocked('XRAY_V36_TIMESTAMP_INVALID') from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            'TIMESTAMP_NAIVE')
    utc_sec = parsed.astimezone(timezone.utc).replace(microsecond=0)
    delta = utc_sec - datetime(1970, 1, 1, tzinfo=timezone.utc)
    seconds = delta.days * 86400 + delta.seconds
    nanos = int((match.group(1) or '').ljust(9, '0') or '0')
    return seconds * 1_000_000_000 + nanos


def _et_civil_day(nanos: int) -> str:
    # A conservative fail-closed scope, not a proof of an official market
    # session. Overnight corrections belong to the original trade's scope.
    return datetime.fromtimestamp(nanos // 1_000_000_000, tz=timezone.utc)\
        .astimezone(ET).date().isoformat()


def _conditions(c: Any) -> tuple[str, ...]:
    require(type(c) is list and 1 <= len(c) <= 4 and
            all(type(v) is str and len(v) == 1 for v in c), 'CONDITION_FORMAT')
    require(len(set(c)) == len(c), 'DUPLICATE_CONDITION')
    return tuple(c)


def _size(s: Any) -> int:
    require(type(s) is int and s > 0, 'SIZE_INVALID')
    return s


def _trade(ev: dict) -> dict:
    return {'x': ev['x'], 'i': ev['i'], 'p': price(ev['p']),
            's': _size(ev['s']), 'c': _conditions(ev['c']),
            'economic_time': _time(ev)}


def _same_old(old: dict, ev: dict, prefix: str) -> bool:
    return (old['p'] == price(ev[prefix+'p']) and
            old['s'] == _size(ev[prefix+'s']) and
            old['c'] == _conditions(ev[prefix+'c']))



# Fixed, published provider incident. The interval is an operational observation,
# NOT proof that the historical repaired dataset is still missing trades.
# Source: https://status.alpaca.markets/incidents/8tvqz47bxs2v
KNOWN_CORE_INCIDENT = {
    'id': 'ALPACA_VENDOR_MARKET_DATA_2026_10_15',
    'et_date': '2026-10-15',
    'start_et': '13:32',
    'resolved_et': '14:46',
    'feeds': ('SIP', 'IEX'),
    'source_url': 'https://status.alpaca.markets/incidents/8tvqz47bxs2v',
}


def historical_session_incident_audit(session_days: list[str],
                                      feed: str = 'SIP') -> dict:
    """Offline session risk overlay. Never attests provider replay or access.

    This accepts *claimed* session dates; it does not verify the NYSE calendar.
    Use a licensed, independently reconciled completed historical dataset
    before changing downstream market-data status. BOATS overnight issues
    are NOT evidence of SIP regular-session loss.
    """
    require(type(session_days) is list and 1 <= len(session_days) <= 30,
            'INCIDENT_SESSION_COUNT')
    require(type(feed) is str and feed in ('SIP', 'IEX', 'BOATS'),
            'INCIDENT_FEED_SCOPE')
    dates = []
    for raw in session_days:
        require(type(raw) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw)
                is not None, 'INCIDENT_DATE_FORMAT')
        try:
            parsed = datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError as exc:
            raise EvidenceBlocked('XRAY_V36_INCIDENT_DATE_INVALID') from exc
        require(parsed.isoformat() == raw and parsed.weekday() < 5,
                'INCIDENT_NON_TRADING_WEEKDAY')
        dates.append(raw)
    require(dates == sorted(set(dates)), 'INCIDENT_SESSION_DUP_OR_ORDER')
    matched = (feed in KNOWN_CORE_INCIDENT['feeds'] and
               KNOWN_CORE_INCIDENT['et_date'] in dates)
    return {
        'schema': 'XRAY_V40_ALPACA_INCIDENT_QUARANTINE_SHADOW_V1',
        'claimed_session_dates_count': len(dates),
        'feed': feed,
        'documented_core_session_incident': matched,
        'documented_incident_id': KNOWN_CORE_INCIDENT['id'] if matched else None,
        'incident_evidence_url': KNOWN_CORE_INCIDENT['source_url'] if matched else None,
        'status': ('INCIDENT_BACKFILL_RECONCILIATION_REQUIRED' if matched
                   else 'NO_DOCUMENTED_INCIDENT_MATCH_NOT_COMPLETENESS_PROOF'),
        'official_calendar_verified': False,
        'provider_recovery_backfill_verified': False,
        'trade_cancel_correction_coverage_verified': False,
        'settled_daily_rth_volume_verified': False,
        'feed_subscription_entitlement_verified': False,
        'market_data_usage_rights_verified': False,
        'canonical_price_pass': False,
        'registered_r92_count': 0,
        'execution': 'NONE', 'real_money': 'NO-GO',
        'unknown_never_pass': True,
    }


def replay(events: list[dict], symbol: str, *, source_complete: bool = False,
           provider_rights_attested: bool = False) -> dict:
    """Deterministic integrity check of GIVEN events, not proof of stream coverage.

    The truth of the provided 'source_complete' claim cannot be independently
    established here. It is NEVER upgraded to certified market-data authority.
    """
    require(type(symbol) is str and re.fullmatch(r'[A-Z][A-Z0-9]{0,6}', symbol)
            is not None, 'SYMBOL_SCOPE')
    require(type(events) is list and 0 < len(events) <= 100000,
            'SAMPLE_SIZE')
    require(type(source_complete) is bool and
            type(provider_rights_attested) is bool, 'EVIDENCE_FLAG_TYPES')
    active: dict[tuple[str, int], dict] = {}
    retired: set[tuple[str, int]] = set()
    seen_ids: set[tuple[str, int]] = set()
    counts = Counter()
    last_received: int | None = None
    first_trade_et_civil_day: str | None = None

    for event in events:
        require(type(event) is dict, 'EVENT_OBJECT')
        require(event.get('S') == symbol and event.get('z') == 'C',
                'SYMBOL_OR_TAPE')
        typ = event.get('T')
        require(typ in ('t', 'c', 'x'), 'UNKNOWN_EVENT_TYPE')
        when = _time(event)
        require(last_received is None or when >= last_received,
                'EVENT_ORDER')
        last_received = when
        require(event.get('u') is None, 'REST_U_IS_NOT_STREAM_EVENT')
        if typ == 't':
            # Feed/participant trade IDs may legitimately repeat in another
            # session. This single-stream function MUST NOT roll across days:
            # a genuine 30-session replay requires isolated daily partitions.
            et_day = _et_civil_day(when)
            if first_trade_et_civil_day is None:
                first_trade_et_civil_day = et_day
            require(et_day == first_trade_et_civil_day,
                    'MULTI_SESSION_TRADE_SCOPE_UNSUPPORTED')
            key = _identity(event, event.get('i'))
            require(key not in seen_ids, 'DUPLICATE_OR_REUSED_ID')
            seen_ids.add(key)
            active[key] = _trade(event)
            counts['trades'] += 1
        elif typ == 'c':
            orig = _identity(event, event.get('oi'))
            new = _identity(event, event.get('ci'))
            require(orig in active, 'ORPHAN_CORRECTION')
            require(new not in seen_ids, 'CORRECTION_ID_REUSED')
            old = active[orig]
            require(_same_old(old, event, 'o'), 'CORRECTION_OLD_MISMATCH')
            replacement = {'x': event['x'], 'i': event['ci'],
                           'p': price(event['cp']), 's': _size(event['cs']),
                           'c': _conditions(event['cc']),
                           'economic_time': old['economic_time']}
            # Correction event timestamp is the message time. It is not the
            # corrected execution time and must not alter RTH classification.
            del active[orig]
            retired.add(orig)
            active[new] = replacement
            seen_ids.add(new)
            counts['corrections'] += 1
        else:
            key = _identity(event, event.get('i'))
            require(key in active, 'ORPHAN_OR_REPEAT_CANCEL')
            require(event.get('a') in ('C', 'E'), 'CANCEL_ACTION')
            require(active[key]['p'] == price(event.get('p')) and
                    active[key]['s'] == _size(event.get('s')),
                    'CANCEL_ORIGINAL_MISMATCH')
            del active[key]
            retired.add(key)
            counts['cancels_errors'] += 1

    # NO prices, volumes, trade IDs, raw provider rows or secrets in output.
    return {'schema': SCHEMA, 'symbol': symbol,
            'source_events_seen': len(events),
            'original_trades_seen': counts['trades'],
            'corrections_seen': counts['corrections'],
            'cancels_errors_seen': counts['cancels_errors'],
            'active_trade_count_research_only': len(active),
            'event_ids_unique_and_linked_in_supplied_sample': True,
            'single_et_civil_date_of_original_trades_enforced': True,
            'official_session_calendar_partition_attested': False,
            'full_participant_and_reporting_facility_scope_proven': False,
            'complete_source_stream_caller_claim': source_complete,
            'provider_rights_caller_claim': provider_rights_attested,
            'independently_attested_full_stream': False,
            'historic_30_session_correction_lineage_verified': False,
            'official_closing_auction_volume_reconciled': False,
            'independent_sip_rth_volume_matched': False,
            'source_pagination_and_session_boundaries_proven': False,
            'market_data_usage_rights_independently_verified': False,
            'canonical_price_pass': False, 'issuer_mc_pass': False,
            'g9_pass': False, 'c417_pass': False, 'registered_r92_count': 0,
            'iphone_receipt_attested': False, 'broker': False,
            'execution': 'NONE', 'real_money': 'NO-GO',
            'raw_provider_data_persisted': False,
            'unknown_never_pass': True,
            'status': ('RESEARCH_SAMPLE_ONLY' if source_complete and
                       provider_rights_attested else 'SOURCE_INCOMPLETE')}