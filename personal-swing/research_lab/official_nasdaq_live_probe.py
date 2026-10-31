#!/usr/bin/env python3
"""One-shot, two-source Nasdaq HTTP research probe. No SEC identity spoofing.

Never logs raw responses, securities, halt events, credentials or private data.
No cron, persistent receipts, market decisions, Sheets writes, orders or alerts.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler, HTTPSHandler, Request, build_opener
)
import ssl

from official_source_evidence_gate import (
    EvidenceRejected, audit_capture, expected_url, MAX_BYTES
)

SCHEMA = 'XRAY_NASDAQ_LIVE_SOURCE_DIAGNOSTIC_V1'
SOURCES = ('NASDAQ_HALTS', 'NASDAQ_DIRECTORY')
USER_AGENT = 'XRAY-NASDAQ-Research-Source-Diagnostic/1.0 (+public GitHub repository)'
TIMEOUT_SECONDS = 12

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def new_opener():
    return build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

def safe_record(source, state, **values):
    return {
        'schema': SCHEMA, 'source': source, 'state': state,
        'real_http_origin_attested': False,
        'full_event_coverage_proven': False,
        'first_public_availability_proven': False,
        'may_clear_risk': False, 'may_modify_al': False,
        'may_send_alert': False, 'may_write_sheet': False,
        'may_place_order': False, **values,
    }

def evaluate_response(source, *, raw, status, response_url, content_type,
                      observed_at_utc):
    """Verify bytes through the existing fail-closed gate without exposing payload."""
    if source not in SOURCES:
        raise ValueError('SOURCE_NOT_ALLOWED')
    url = expected_url(source, None)
    raw = bytes(raw)
    if not 0 < len(raw) <= MAX_BYTES[source]:
        return safe_record(source, 'BODY_SIZE_REJECTED')
    capture = {
        'source': source,
        'method': 'GET',
        'request_url': url,
        'final_url': response_url,
        'status_code': status,
        'content_type': content_type,
        'content_encoding': 'identity',
        'body_base64': base64.b64encode(raw).decode('ascii'),
        'body_bytes': len(raw),
        'body_sha256': hashlib.sha256(raw).hexdigest(),
        'observed_at_utc': observed_at_utc,
    }
    try:
        result = audit_capture(
            capture, source=source, ticker='AAPL', asof_utc=observed_at_utc
        )
    except EvidenceRejected as exc:
        return safe_record(
            source, 'READER_REJECTED',
            body_bytes=len(raw), body_sha256=capture['body_sha256'],
            refusal_code=str(exc),
        )
    # Everything here is only an observation of one public snapshot, not
    # production source clearance, full feed completeness or historical PIT.
    return safe_record(
        source, 'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE',
        http_status=status,
        body_bytes=len(raw),
        body_sha256=capture['body_sha256'],
        observed_at_utc=observed_at_utc,
        parser_status=result['parser_status'],
        directory_stale=result['directory_over_72h_old'],
        gate_status=result['status'],
    )

def compare_current_directory_scope(raw, watchlist):
    """Only current snapshot identity counts. NEVER evidence of historical PIT."""
    if type(watchlist) is not dict:
        raise ValueError('SCOPE_FILE_INVALID')
    symbols = watchlist.get('liquidity_watch_symbols')
    if type(symbols) is not list or len(symbols) != 477 or (
        type(watchlist.get('source_count')) is not int or
        watchlist['source_count'] != 477
    ):
        raise ValueError('SCOPE_477_COUNT_MISMATCH')
    if any(type(s) is not str or
           re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}',s) is None
           for s in symbols) or len(set(symbols)) != 477:
        raise ValueError('SCOPE_SYMBOL_INVALID_OR_DUPLICATE')
    try:
        body = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('DIRECTORY_NOT_UTF8') from exc
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) < 3 or not lines[-1].startswith('File Creation Time:'):
        raise ValueError('DIRECTORY_FOOTER_INVALID')
    header = lines[0].split('|')
    if len(set(header)) != len(header) or any(
        k not in header for k in ('Symbol', 'Test Issue', 'Financial Status', 'ETF')
    ):
        raise ValueError('DIRECTORY_HEADER_INVALID')
    positions = {name:i for i,name in enumerate(header)}
    entries = {}
    for line in lines[1:-1]:
        row = line.split('|')
        if len(row) != len(header):
            raise ValueError('DIRECTORY_ROW_DRIFT')
        key = row[positions['Symbol']]
        if key in entries:
            raise ValueError('DIRECTORY_DUPLICATE_SYMBOL')
        entries[key] = row
    matching = 0
    flagged = 0
    missing = 0
    for s in symbols:
        row = entries.get(s)
        if row is None:
            missing += 1
        elif any(row[positions[k]] != 'N' for k in
                 ('Test Issue', 'Financial Status', 'ETF')):
            flagged += 1
        else:
            matching += 1
    if matching + flagged + missing != 477:
        raise ValueError('SCOPE_PARTITION_INVALID')
    return {
        'scope_count': 477, 'directory_basic_flag_match': matching,
        'directory_flagged': flagged, 'directory_missing': missing,
        'scope_sha256': hashlib.sha256(
            '\n'.join(symbols).encode('utf-8')).hexdigest(),
        'historical_membership_proven': False, 'may_clear_risk': False,
    }

def local_watchlist():
    location = Path(__file__).resolve().parents[1] / 'nasdaq_watchlist_477.json'
    with location.open('r', encoding='utf-8') as stream:
        return json.load(stream)

def probe_once(source, opener=None):
    if source not in SOURCES:
        raise ValueError('SOURCE_NOT_ALLOWED')
    opener = new_opener() if opener is None else opener
    url = expected_url(source, None)
    request = Request(
        url, method='GET',
        headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            final_url = response.geturl()
            mime = response.headers.get('Content-Type', '')
            encoding = response.headers.get('Content-Encoding', 'identity')
            # Bound memory before any parser sees network data.
            raw = response.read(MAX_BYTES[source] + 1)
            observed = datetime.now(timezone.utc).isoformat()
    except HTTPError as exc:
        return safe_record(source, 'HTTP_REFUSED',
                           http_status=exc.code)
    except (URLError, TimeoutError, OSError) as exc:
        return safe_record(source, 'TRANSPORT_ERROR',
                           exception_type=type(exc).__name__)
    if encoding not in ('identity', None):
        return safe_record(source, 'CONTENT_ENCODING_REFUSED')
    result = evaluate_response(
        source, raw=raw, status=status, response_url=final_url,
        content_type=mime, observed_at_utc=observed,
    )
    if source == 'NASDAQ_DIRECTORY' and result['state'] == (
        'HTTP_AND_FORMAT_OBSERVED_NOT_LIVE_ACCEPTANCE'
    ) and result.get('directory_stale') is False:
        try:
            result.update(compare_current_directory_scope(raw, local_watchlist()))
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            result['scope_status'] = 'SCOPE_FAIL_CLOSED'
            result['scope_error_type'] = type(exc).__name__
        else:
            result['scope_status'] = 'CURRENT_SNAPSHOT_REVIEW_ONLY'
    return result

def main():
    # No provider records, raw bytes, company filing data, private candidates,
    # secrets, or response headers appear in public Actions logs.
    print(json.dumps(safe_record(
        'SEC_EDGAR', 'SKIPPED_NO_DECLARED_SEC_USER_AGENT',
    ), sort_keys=True))
    for source in SOURCES:
        print(json.dumps(probe_once(source), sort_keys=True))

if __name__ == '__main__':
    main()
