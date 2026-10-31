#!/usr/bin/env python3
"""XRAY 477 official-source risk SHADOW; no authority over AL or private delivery.

The Alpaca caller supplies strictly validated internal indexes produced by the
bounded raw API audit. Historical first-known timestamps remain UNPROVEN.
SEC is a ROAD-only pilot; Nasdaq probes are snapshot diagnostics, not
per-symbol halt clearance. Missing observations are NEVER 'safe'.
Nothing here reads a portfolio, places orders, writes Sheets or emits alerts.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re

from official_provider_raw_once import read_immutable_477_scope

SCHEMA = 'XRAY_PERSONAL_OFFICIAL_477_SHADOW_V1'
ALPACA_STATUS = 'ALL_477_BATCH_CHAINS_EXHAUSTED_NOT_MARKET_CLEARANCE'
SEC_STATUS = 'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE'
NAS_STATUS = 'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.]{0,14}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
GROUPS = frozenset((
    'reverse_splits', 'forward_splits', 'unit_splits', 'cash_dividends',
    'stock_dividends', 'spin_offs', 'cash_mergers', 'stock_mergers',
    'stock_and_cash_mergers', 'redemptions', 'name_changes',
    'worthless_removals', 'rights_distributions', 'partial_calls',
    'reorganizations', 'capital_gains_distributions'
))

class ShadowRefused(ValueError):
    pass

def need(ok, code):
    if not ok:
        raise ShadowRefused(code)

def utc(value):
    need(type(value) is str and 1 <= len(value) <= 40, 'ASOF_INVALID')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ShadowRefused('ASOF_INVALID') from exc
    need(dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(dt),
         'ASOF_NOT_UTC')
    return dt.astimezone(timezone.utc)

def build_477_shadow(*, asof_utc, alpaca, sec=None, halt=None, directory=None,
                     symbols=None):
    """Return private, in-memory per-symbol evidence plus public-safe summary.

    The caller must not publish 'rows' or provider event identifiers. This
    function NEVER promotes a missing event to no-risk and cannot change AL.
    """
    cutoff = utc(asof_utc)
    scope = read_immutable_477_scope()
    if symbols is not None:
        need(type(symbols) in (tuple, list) and tuple(symbols) == scope,
             'WATCHLIST_SHA_OR_ORDER_DRIFT')
    need(type(alpaca) is dict, 'ALPACA_EVIDENCE_MISSING')
    need(alpaca.get('status') == ALPACA_STATUS and
         alpaca.get('requested_symbols') == 477 and
         alpaca.get('batches') == 20 and
         type(alpaca.get('http_pages')) is int and
         20 <= alpaca['http_pages'] <= 160 and
         alpaca.get('data_quality_requested') == 'all' and
         alpaca.get('cross_batch_unique_events_proven') is True and
         alpaca.get('historical_pit_proven') is False and
         alpaca.get('may_clear_risk') is False,
         'ALPACA_SCOPE_OR_SOURCE_CONTRACT_INVALID')
    identities = alpaca.get('_internal_id_index')
    roles = alpaca.get('_internal_symbol_roles')
    need(type(identities) is dict and type(roles) is dict and
         set(identities) == set(roles) and
         len(identities) == alpaca.get('unique_event_ids_observed') and
         len(identities) <= alpaca.get('observed_query_event_occurrences', -1),
         'ALPACA_INTERNAL_INDEX_NOT_PROVEN')
    # Independently bind private event-index identity to the already-audited
    # 477-batch SHA. A valid count alone is not sufficient evidence of a join.
    id_digest = hashlib.sha256(
        ('\\n'.join(sorted(identities)) + '\\n').encode('ascii')
    ).hexdigest()
    need(alpaca.get('event_id_set_sha256') == id_digest,
         'ALPACA_EVENT_SET_DIGEST_MISMATCH')
    scope_set = set(scope)
    per_symbol = {s: {'symbol': s, 'alpaca_event_count': 0,
                      'alpaca_event_groups': {}, 'risk_status': 'UNKNOWN_NOT_CLEAR',
                      'sec': 'NOT_CHECKED', 'nasdaq_halt': 'UNMAPPED_NOT_CLEAR',
                      'nasdaq_directory': 'UNMAPPED_NOT_CLEAR'}
                  for s in scope}
    associations = 0
    for uid, fields in identities.items():
        need(type(uid) is str and re.fullmatch(
             r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', uid
             ) is not None and type(fields) is tuple and len(fields) == 3,
             'EVENT_IDENTITY_INVALID')
        group, processed, rowhash = fields
        need(group in GROUPS and type(processed) is str and
             type(rowhash) is str and SHA256.fullmatch(rowhash) is not None,
             'EVENT_FIELDS_INVALID')
        try:
            day = date.fromisoformat(processed)
        except ValueError as exc:
            raise ShadowRefused('EVENT_PROCESS_DATE_INVALID') from exc
        need(day.isoformat() == processed, 'EVENT_PROCESS_DATE_INVALID')
        # A future process date MAY be known already; that is a future action,
        # not an historical PIT proof. Never silently drop it.
        related = roles[uid]
        need(type(related) is tuple and len(related) > 0 and
             len(set(related)) == len(related) and
             all(type(s) is str and SYMBOL.fullmatch(s) for s in related) and
             tuple(sorted(related)) == related and
             bool(scope_set.intersection(related)), 'EVENT_ROLE_SCOPE_INVALID')
        for s in related:
            if s not in scope_set:
                continue
            item = per_symbol[s]
            item['alpaca_event_count'] += 1
            item['alpaca_event_groups'][group] = (
                item['alpaca_event_groups'].get(group, 0) + 1)
            item['risk_status'] = 'EVENT_REVIEW_REQUIRED'
            associations += 1
    # An SEC pilot validates only ROAD and a current submissions format.
    # Do not imply 477 issuer mapping or first-public-time clearance.
    sec_result = 'NOT_OBSERVED'
    if sec is not None:
        need(type(sec) is dict and sec.get('status') == SEC_STATUS and
             sec.get('first_public_availability_proven') is False and
             sec.get('may_modify_al') is False,
             'SEC_PILOT_EVIDENCE_INVALID')
        sec_result = 'ROAD_PILOT_FORMAT_OBSERVED'
        if 'ROAD' in scope_set:
            per_symbol['ROAD']['sec'] = 'PILOT_REVIEW_ONLY_NOT_PIT'
    nasdaq = {}
    for name, result in (('halt', halt), ('directory', directory)):
        if result is None:
            nasdaq[name] = 'NOT_OBSERVED'
            continue
        need(type(result) is dict and result.get('source') ==
             ('NASDAQ_HALTS' if name == 'halt' else 'NASDAQ_DIRECTORY') and
             result.get('may_clear_risk') is False and
             result.get('may_modify_al') is False,
             'NASDAQ_PROBE_EVIDENCE_INVALID')
        nasdaq[name] = result.get('state', 'UNKNOWN')
        if name == 'directory' and result.get('scope_status') == (
            'CURRENT_SNAPSHOT_REVIEW_ONLY'):
            n = result.get('flagged_watchlist_index_zero_based')
            if n is not None:
                need(type(n) is int and 0 <= n < 477 and
                     result.get('directory_flagged') == 1,
                     'DIRECTORY_FLAG_INDEX_INVALID')
                symbol = scope[n]
                per_symbol[symbol]['nasdaq_directory'] = 'FLAG_REVIEW_REQUIRED'
                per_symbol[symbol]['risk_status'] = 'EVENT_REVIEW_REQUIRED'
    rows = list(per_symbol.values())
    flagged = sum(row['risk_status'] == 'EVENT_REVIEW_REQUIRED' for row in rows)
    total = sum(row['alpaca_event_count'] for row in rows)
    need(total == associations and len(rows) == 477,
         'SHADOW_PARTITION_OR_DUPLICATE_ERROR')
    digest_rows = json.dumps(rows, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False)
    safe = {
        'schema': SCHEMA, 'status': '477_REVIEW_ONLY_NO_MARKET_CLEARANCE',
        'asof_utc': cutoff.isoformat().replace('+00:00', 'Z'),
        'scope_count': 477,
        'scope_sha256': hashlib.sha256(
            ('\n'.join(scope)+'\n').encode('ascii')).hexdigest(),
        'symbol_event_associations': associations,
        'unique_provider_events': len(identities),
        'symbols_requiring_review': flagged,
        'symbols_unknown_not_clear': 477 - flagged,
        'sec_pilot': sec_result,
        'nasdaq_probe_states': nasdaq,
        'rows_sha256': hashlib.sha256(digest_rows.encode('ascii')).hexdigest(),
        'source_snapshot_atomic': False,
        'provider_first_known_time_proven': False,
        'historical_pit_proven': False,
        'may_clear_risk': False, 'may_modify_al': False,
        'may_change_stop_target': False, 'may_notify': False,
        'may_place_order': False, 'may_write_sheet': False,
        'may_promote_to_daily_eod': False,
    }
    return {'summary': safe, 'rows': rows}

def run_manual_live():
    """One authorized, bounded private runner run; prints NO event details."""
    import os
    from datetime import timedelta
    from official_provider_raw_once import (
        audit_all_477, sec_raw_audit, Refused
    )
    from official_nasdaq_live_probe import probe_once
    api_key = os.environ.get('XRAY_ALPACA_DATA_KEY_ID', '')
    api_secret = os.environ.get('XRAY_ALPACA_DATA_SECRET_KEY', '')
    sec_agent = os.environ.get('XRAY_SEC_DECLARED_USER_AGENT', '')
    need(bool(api_key.strip()) and bool(api_secret.strip()) and bool(sec_agent.strip()),
         'MISSING_AUTHORIZED_SOURCE_CONFIGURATION')
    now = datetime.now(timezone.utc)
    alpaca = audit_all_477(
        key=api_key, secret=api_secret,
        start=(now.date()-timedelta(days=30)).isoformat(),
        end=now.date().isoformat(),
        include_internal_ids=True, include_internal_roles=True)
    sec = sec_raw_audit(declared_agent=sec_agent)
    halt = probe_once('NASDAQ_HALTS')
    directory = probe_once('NASDAQ_DIRECTORY')
    outcome = build_477_shadow(
        asof_utc=datetime.now(timezone.utc).isoformat(),
        alpaca=alpaca, sec=sec, halt=halt, directory=directory)
    print(json.dumps(outcome['summary'], sort_keys=True))
    # Non-PASS Nasdaq endpoints are VISIBLE but NEVER become false-clear.
    if any(value != NAS_STATUS for value in (
        halt.get('state'), directory.get('state'))):
        return 4
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(run_manual_live())
    except (ShadowRefused, ValueError) as exc:
        # Only local stable error codes; never log credentials or provider rows.
        print(json.dumps({'schema': SCHEMA, 'status': 'SOURCE_REFUSED',
                          'reason_code': str(exc) if isinstance(
                              exc, ShadowRefused) else 'INPUT_INVALID',
                          'may_clear_risk': False}, sort_keys=True))
        raise SystemExit(4)
