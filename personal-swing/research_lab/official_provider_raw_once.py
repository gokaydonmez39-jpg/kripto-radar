#!/usr/bin/env python3
"""Manual, read-only raw-provider acceptance probe; NEVER a market-risk clearance.

Use only on the protected default branch. No scheduler, trade, Sheet or alerts.
Never print/commit credentials, HTTP response bodies or issuer event details.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import time
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

from official_source_evidence_gate import audit_capture, EvidenceRejected

ALPACA_URL = 'https://data.alpaca.markets/v1/corporate-actions'
SEC_URL = 'https://data.sec.gov/submissions/CIK0001718227.json'
ALLOWED_GROUPS = frozenset((
    'reverse_splits', 'forward_splits', 'unit_splits', 'cash_dividends',
    'stock_dividends', 'spin_offs', 'cash_mergers', 'stock_mergers',
    'stock_and_cash_mergers', 'redemptions', 'name_changes',
    'worthless_removals', 'rights_distributions', 'partial_calls',
    'reorganizations', 'capital_gains_distributions'
))
ALPACA_SCOPE = ('GILD', 'LNT', 'BTSG')
EVENT_SYMBOL_KEYS = ('symbol', 'source_symbol', 'old_symbol', 'new_symbol',
                     'acquirer_symbol', 'acquiree_symbol')

SEC_AGENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._\-]{2,100} [^\s@]+@[A-Za-z0-9._\-]+\.[A-Za-z]{2,24}$')

class Refused(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Refused(message)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def default_opener():
    return build_opener(HTTPSHandler(context=ssl.create_default_context()),
                        NoRedirect())

def read_json_once(url, *, headers, opener=None, size_limit=4_000_000):
    """One HTTPS GET. Caller controls exact allowlisted URL; strict no redirects."""
    require(type(url) is str and
            (url == SEC_URL or url.startswith(ALPACA_URL + '?')),
            'URL_NOT_ALLOWLISTED')
    require(type(headers) is dict, 'HEADERS_INVALID')
    opener = default_opener() if opener is None else opener
    request = Request(url, method='GET', headers={
        **headers, 'Accept': 'application/json', 'Accept-Encoding': 'identity'
    })
    try:
        with opener.open(request, timeout=12) as response:
            require(response.geturl() == url, 'REDIRECT_REFUSED')
            require(type(response.getcode()) is int and
                    response.getcode() == 200, 'HTTP_NOT_200')
            mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            require(mime == 'application/json', 'JSON_MIME_INVALID')
            require(response.headers.get('Content-Encoding', 'identity') == 'identity',
                    'ENCODING_UNVERIFIED')
            raw = response.read(size_limit + 1)
    except HTTPError as exc:
        raise Refused('HTTP_' + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise Refused('TRANSPORT_FAILED') from None
    require(0 < len(raw) <= size_limit, 'BODY_SIZE_INVALID')
    require(not raw.startswith(b'\xef\xbb\xbf'), 'JSON_BOM_REFUSED')
    try:
        payload = json.loads(raw.decode('utf-8', errors='strict'),
                             object_pairs_hook=unique_object,
                             parse_constant=reject_nonfinite)
    except Refused:
        raise
    except (UnicodeError, ValueError, TypeError):
        raise Refused('JSON_UNREADABLE') from None
    return payload, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'raw': raw, 'content_type': mime}

def unique_object(items):
    result = {}
    for k, v in items:
        require(k not in result, 'JSON_DUPLICATE_KEY')
        result[k] = v
    return result

def reject_nonfinite(_):
    raise Refused('JSON_NONFINITE')

def alpaca_raw_audit(*, key, secret, start, end, opener=None, limit=100, max_pages=8,
                     symbols=ALPACA_SCOPE, before_request=None):
    """Walk all RAW corporate-action response pages for fixed public sample scope.

    Exhaustion is a transport-page result, not a proof of data freshness/PIT.
    """
    require(type(key) is str and bool(key.strip()) and
            type(secret) is str and bool(secret.strip()), 'ALPACA_KEYS_MISSING')
    require(type(start) is str and type(end) is str and
            re.fullmatch(r'\d{4}-\d{2}-\d{2}', start) is not None and
            re.fullmatch(r'\d{4}-\d{2}-\d{2}', end) is not None,
            'DATE_INVALID')
    try:
        begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise Refused('DATE_INVALID') from None
    require(begin <= finish <= datetime.now(timezone.utc).date(),
            'DATE_INVALID')
    require(type(limit) is int and 1 <= limit <= 1000 and
            type(max_pages) is int and 1 <= max_pages <= 20, 'BUDGET_INVALID')
    require(type(symbols) in (tuple, list) and
            1 <= len(symbols) <= 25 and len(set(symbols)) == len(symbols) and
            all(type(s) is str and
                re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', s) is not None
                for s in symbols), 'ALPACA_SYMBOL_BATCH_INVALID')
    require(before_request is None or callable(before_request),
            'PACE_CALLBACK_INVALID')
    headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
    known_ids, tokens = {}, set()
    pages, page = 0, None
    sizes = []
    for _ in range(max_pages):
        query = {'symbols': ','.join(symbols), 'start': start,
                 'end': end, 'data_quality': 'all', 'region': 'us',
                 'limit': str(limit), 'sort': 'asc'}
        if page is not None:
            query['page_token'] = page
        url = ALPACA_URL + '?' + urlencode(query)
        if before_request is not None:
            before_request()
        data, receipt = read_json_once(url, headers=headers, opener=opener)
        require(type(data) is dict, 'ALPACA_ROOT_INVALID')
        pages += 1
        sizes.append(receipt['bytes'])
        unknown = set(data) - ALLOWED_GROUPS - {'next_page_token'}
        require(not unknown, 'ALPACA_NEW_SCHEMA_REVIEW_REQUIRED')
        require('next_page_token' in data, 'ALPACA_PAGE_METADATA_MISSING')
        item_count = 0
        for group, rows in data.items():
            if group == 'next_page_token':
                continue
            require(type(rows) is list, 'ALPACA_GROUP_INVALID')
            item_count += len(rows)
            require(item_count <= limit, 'ALPACA_PAGE_EXCEEDS_LIMIT')
            for row in rows:
                require(type(row) is dict, 'ALPACA_ROW_INVALID')
                present_symbols = [row[k] for k in EVENT_SYMBOL_KEYS if k in row]
                require(bool(present_symbols) and all(
                    type(s) is str and
                    re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', s) is not None
                    for s in present_symbols), 'ALPACA_EVENT_SYMBOL_INVALID')
                require(any(s in symbols for s in present_symbols),
                        'ALPACA_EVENT_OUTSIDE_REQUEST_SCOPE')
                if group == 'cash_dividends':
                    require(type(row.get('symbol')) is str and
                            row['symbol'] in symbols,
                            'ALPACA_CASH_DIVIDEND_SYMBOL_REQUIRED')
                if group == 'stock_and_cash_mergers':
                    require('acquirer_symbol' in row and
                            'acquiree_symbol' in row,
                            'ALPACA_MERGER_IDENTITY_MISSING')
                rid = row.get('id')
                when = row.get('process_date')
                require(type(rid) is str, 'ALPACA_EVENT_ID_INVALID')
                try:
                    canonical_id = str(UUID(rid))
                except (ValueError, TypeError, AttributeError):
                    raise Refused('ALPACA_EVENT_ID_INVALID') from None
                require(canonical_id == rid.lower(), 'ALPACA_EVENT_ID_INVALID')
                require(type(when) is str and
                        re.fullmatch(r'\d{4}-\d{2}-\d{2}', when) is not None,
                        'ALPACA_PROCESS_DATE_INVALID')
                try:
                    when_date = date.fromisoformat(when)
                except ValueError:
                    raise Refused('ALPACA_PROCESS_DATE_INVALID') from None
                require(when_date.isoformat() == when and start <= when <= end,
                        'ALPACA_PROCESS_DATE_INVALID')
                require(canonical_id not in known_ids,
                        'ALPACA_DUPLICATE_EVENT_ACROSS_PAGES')
                known_ids[canonical_id] = (group, when)
        nxt = data['next_page_token']
        require(nxt is None or (type(nxt) is str and
                0 < len(nxt) <= 512 and '\n' not in nxt),
                'ALPACA_PAGE_TOKEN_INVALID')
        if nxt is None:
            return {
                'status': 'RAW_PAGE_CHAIN_EXHAUSTED_NOT_MARKET_CLEARANCE',
                'pages': pages, 'event_ids_observed': len(known_ids),
                'symbols_requested_count': len(symbols),
                'raw_bytes_per_page': sizes, 'data_quality_requested': 'all',
                'page_chain_exhausted': True,
                'provider_latency_bounded': False, 'first_known_time_proven': False,
                'historical_pit_proven': False, 'all_corporate_events_proven': False,
                'may_clear_risk': False, 'may_modify_al': False,
                'may_place_order': False, 'may_notify': False,
                'may_write_sheet': False,
            }
        require(nxt not in tokens, 'ALPACA_PAGE_TOKEN_CYCLE')
        tokens.add(nxt)
        page = nxt
    raise Refused('ALPACA_PAGE_BUDGET_EXCEEDED')

def read_immutable_477_scope():
    """Existing production watchlist read only, never updated or reprioritized."""
    path = Path(__file__).resolve().parents[1] / 'nasdaq_watchlist_477.json'
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        raise Refused('WATCHLIST_UNREADABLE') from None
    require(type(document) is dict and
            type(document.get('source_count')) is int and
            document['source_count'] == 477,
            'WATCHLIST_COUNT_INVALID')
    scope = document.get('liquidity_watch_symbols')
    require(type(scope) is list and len(scope) == 477 and
            all(type(s) is str and
                re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', s) is not None
                for s in scope) and len(set(scope)) == 477,
            'WATCHLIST_NOT_477_UNIQUE')
    return tuple(scope)

def audit_all_477(*, key, secret, start, end, scope=None, opener=None,
                  before_request=None):
    """Bounded 20-batch raw REST proof for existing 477 scope; no event detail logs.

    Counts are response records PER QUERY; corporate events appearing in more
    than one symbol batch are not proven independent events. Never deduce no risk.
    """
    symbols = read_immutable_477_scope() if scope is None else scope
    require(type(symbols) in (list,tuple) and len(symbols) == 477 and
            len(set(symbols)) == 477 and all(
                type(s) is str and
                re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}',s) is not None
                for s in symbols), 'WATCHLIST_NOT_477_UNIQUE')
    if before_request is None:
        before_request = lambda: time.sleep(1.05)
    requests = 0
    record_occurrences = 0
    for index in range(0, 477, 25):
        batch = symbols[index:index+25]
        sample = alpaca_raw_audit(
            key=key,secret=secret,start=start,end=end,
            opener=opener, symbols=batch,limit=100,max_pages=8,
            before_request=before_request)
        require(sample['symbols_requested_count']==len(batch) and
                sample['page_chain_exhausted'] is True,
                'ALPACA_BATCH_UNVERIFIED')
        requests += sample['pages']
        record_occurrences += sample['event_ids_observed']
    require(requests <= 160, 'ALPACA_REQUEST_BUDGET_EXCEEDED')
    return {
        'status':'ALL_477_BATCH_CHAINS_EXHAUSTED_NOT_MARKET_CLEARANCE',
        'requested_symbols':477, 'batches':20, 'http_pages':requests,
        'observed_query_event_occurrences':record_occurrences,
        'cross_batch_unique_events_proven':False,
        'provider_latency_bounded':False, 'historical_pit_proven':False,
        'market_event_absence_proven':False, 'may_clear_risk':False,
        'may_modify_al':False, 'may_place_order':False,
        'may_notify':False, 'may_write_sheet':False,
    }

def sec_raw_audit(*, declared_agent, opener=None):
    """Require real separately provisioned declared organization and contact email."""
    require(type(declared_agent) is str and
            SEC_AGENT.fullmatch(declared_agent) is not None,
            'SEC_DECLARED_CONTACT_MISSING_OR_INVALID')
    payload, raw = read_json_once(
        SEC_URL, headers={'User-Agent': declared_agent}, opener=opener)
    timestamp = datetime.now(timezone.utc).isoformat()
    receipt = {
        'source': 'SEC_EDGAR', 'method': 'GET', 'request_url': SEC_URL,
        'final_url': SEC_URL, 'status_code': 200,
        'content_type': raw['content_type'], 'content_encoding': 'identity',
        'body_base64': base64.b64encode(raw['raw']).decode('ascii'),
        'body_bytes': raw['bytes'], 'body_sha256': raw['sha256'],
        'observed_at_utc': timestamp,
    }
    try:
        evaluated = audit_capture(receipt, source='SEC_EDGAR', ticker='ROAD',
                                  cik='0001718227', asof_utc=timestamp)
    except EvidenceRejected:
        raise Refused('SEC_FORMAT_REQUIRES_REVIEW') from None
    require(type(payload) is dict, 'SEC_ROOT_INVALID')
    return {
        'status': 'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE',
        'bytes': raw['bytes'], 'sha256': raw['sha256'],
        'parser_status': evaluated['parser_status'],
        'declared_contact_present': True,
        'http_origin_independently_attested': False,
        'first_public_availability_proven': False,
        'filing_history_exhaustiveness_proven': False,
        'may_clear_risk': False, 'may_modify_al': False,
        'may_place_order': False, 'may_notify': False,
        'may_write_sheet': False,
    }

def main():
    # No secrets or raw payloads are ever logged; actual network is opt-in only.
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()
    sec_agent = os.environ.get('XRAY_SEC_DECLARED_USER_AGENT', '')
    key = os.environ.get('XRAY_ALPACA_DATA_KEY_ID', '')
    secret = os.environ.get('XRAY_ALPACA_DATA_SECRET_KEY', '')
    scope_mode = os.environ.get('XRAY_SOURCE_SCOPE','pilot3')
    if scope_mode not in ('pilot3','all477'):
        raise Refused('SOURCE_SCOPE_INVALID')
    if scope_mode == 'all477':
        alpaca_fn = lambda: audit_all_477(
            key=key,secret=secret,start=start,end=end)
    else:
        alpaca_fn = lambda: alpaca_raw_audit(
            key=key,secret=secret,start=start,end=end)
    for source, enabled, fn in (
        ('SEC_EDGAR', bool(sec_agent), lambda: sec_raw_audit(declared_agent=sec_agent)),
        ('ALPACA_CORPORATE_ACTIONS', bool(key and secret), alpaca_fn),
    ):
        if not enabled:
            print(json.dumps({'source': source, 'status': 'SKIPPED_NO_AUTHORIZED_INPUT',
                              'may_clear_risk': False}))
            continue
        try:
            value = fn()
        except (Refused, ValueError) as exc:
            # All expected errors are constant refusal codes. No exception text
            # from HTTP libraries, external JSON, emails, secrets or URLs.
            code = str(exc) if isinstance(exc, Refused) else 'INPUT_INVALID'
            value = {'status': 'SOURCE_REFUSED', 'reason_code': code,
                     'may_clear_risk': False}
        print(json.dumps({'source': source, **value}, sort_keys=True))

if __name__ == '__main__':
    main()
