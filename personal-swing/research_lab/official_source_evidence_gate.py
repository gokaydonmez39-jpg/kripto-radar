#!/usr/bin/env python3
"""XRAY NASDAQ: zero-network, read-only gate for externally captured official bytes.

Passing is NOT proof of live HTTP origin, rights, complete coverage, point-in-time
availability, trading safety, or AL. No network, files, Sheets, alerts or orders.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from zoneinfo import ZoneInfo

import official_event_risk_shadow as shadow

SCHEMA = 'XRAY_NASDAQ_OFFICIAL_CAPTURE_EVIDENCE_V1'
SOURCES = frozenset(('SEC_EDGAR', 'NASDAQ_HALTS', 'NASDAQ_DIRECTORY'))
MAX_BYTES = {'SEC_EDGAR': 4_000_000, 'NASDAQ_HALTS': 2_000_000,
             'NASDAQ_DIRECTORY': 2_000_000}
HEX_SHA = re.compile(r'[0-9a-f]{64}\Z')
CIK_PATTERN = re.compile(r'[0-9]{10}\Z')

class EvidenceRejected(ValueError):
    pass

def demand(ok, reason):
    if not ok:
        raise EvidenceRejected(reason)

def utc(value):
    demand(type(value) is str and 1 <= len(value) <= 40, 'TIME_INVALID')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise EvidenceRejected('TIME_INVALID') from exc
    demand(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
           'TIME_NOT_UTC')
    return parsed.astimezone(timezone.utc)

def expected_url(source, cik):
    if source == 'SEC_EDGAR':
        demand(type(cik) is str and CIK_PATTERN.fullmatch(cik) is not None,
               'CIK_SCOPE_INVALID')
        return f'https://data.sec.gov/submissions/CIK{cik}.json'
    demand(cik is None, 'EXTRANEOUS_CIK')
    if source == 'NASDAQ_HALTS':
        return 'https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts'
    if source == 'NASDAQ_DIRECTORY':
        return 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt'
    raise EvidenceRejected('SOURCE_UNSUPPORTED')

def no_duplicate_keys(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EvidenceRejected('JSON_DUPLICATE_KEY')
        result[key] = value
    return result

def reject_nonfinite(value):
    raise EvidenceRejected('JSON_NONFINITE')

def audit_capture(capture, *, source, ticker, asof_utc, cik=None):
    """Audit self-reported collector metadata; SHA does not attest source origin."""
    demand(source in SOURCES, 'SOURCE_UNSUPPORTED')
    shadow.symbol(ticker)
    cutoff = utc(asof_utc)
    url = expected_url(source, cik)
    demand(type(capture) is dict, 'CAPTURE_MISSING')
    demand(capture.get('source') == source, 'SOURCE_MISMATCH')
    demand(capture.get('method') == 'GET', 'METHOD_INVALID')
    demand(capture.get('request_url') == url and
           capture.get('final_url') == url, 'URL_OR_REDIRECT_MISMATCH')
    demand(type(capture.get('status_code')) is int and
           capture['status_code'] == 200, 'HTTP_NOT_200')
    mime = capture.get('content_type')
    demand(type(mime) is str, 'MIME_INVALID')
    normalized_mime = mime.lower().split(';', 1)[0].strip()
    expected_mimes = {
        'SEC_EDGAR': frozenset(('application/json', 'application/octet-stream')),
        'NASDAQ_HALTS': frozenset(('text/xml', 'application/xml', 'application/rss+xml')),
        'NASDAQ_DIRECTORY': frozenset(('text/plain', 'application/octet-stream')),
    }
    demand(normalized_mime in expected_mimes[source], 'MIME_INVALID')
    demand(capture.get('content_encoding') in (None, 'identity'),
           'ENCODED_TRANSPORT_UNVERIFIED')
    observed = utc(capture.get('observed_at_utc'))
    demand(observed <= cutoff, 'CAPTURE_AFTER_DECISION_CUTOFF')
    token = capture.get('body_base64')
    demand(type(token) is str and len(token) <= (MAX_BYTES[source] * 4 // 3 + 16),
           'BODY_MISSING_OR_TOO_LARGE')
    try:
        raw = base64.b64decode(token, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceRejected('BASE64_INVALID') from exc
    demand(0 < len(raw) <= MAX_BYTES[source], 'BODY_SIZE_INVALID')
    demand(type(capture.get('body_bytes')) is int and
           capture['body_bytes'] == len(raw), 'BODY_LENGTH_MISMATCH')
    claimed_hash = capture.get('body_sha256')
    demand(type(claimed_hash) is str and HEX_SHA.fullmatch(claimed_hash) is not None,
           'HASH_INVALID')
    digest = hashlib.sha256(raw).hexdigest()
    demand(hmac.compare_digest(digest, claimed_hash), 'HASH_MISMATCH')
    try:
        body = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise EvidenceRejected('BODY_NOT_UTF8') from exc
    # XML 1.0 permits a UTF-8 BOM; preserve the ORIGINAL raw-byte SHA
    # and strip only that exact three-byte marker for the XML parser.
    # JSON and Symbol Directory remain strict and refuse it.
    if body.startswith('\ufeff'):
        demand(source == 'NASDAQ_HALTS' and raw.startswith(b'\\xef\\xbb\\xbf'),
               'UTF8_BOM_UNSUPPORTED')
        body = body[1:]
    if source == 'SEC_EDGAR':
        try:
            doc = json.loads(body, object_pairs_hook=no_duplicate_keys,
                             parse_constant=reject_nonfinite)
        except EvidenceRejected:
            raise
        except (ValueError, TypeError) as exc:
            raise EvidenceRejected('JSON_INVALID') from exc
        try:
            assessment = shadow.inspect_sec(doc, cik, ticker,
                asof_utc=asof_utc, observed_at_utc=observed.isoformat())
        except (shadow.SourceRefused, KeyError, TypeError, AttributeError) as exc:
            raise EvidenceRejected('SEC_READER_REFUSED') from exc
    elif source == 'NASDAQ_HALTS':
        try:
            assessment = shadow.inspect_nasdaq_halts(body, ticker,
                asof_utc=asof_utc, observed_at_utc=observed.isoformat())
        except (shadow.SourceRefused, KeyError, TypeError, AttributeError) as exc:
            raise EvidenceRejected('RSS_READER_REFUSED') from exc
    else:
        try:
            assessment = shadow.inspect_nasdaq_directory(body, ticker,
                asof_utc=asof_utc, observed_at_utc=observed.isoformat())
        except (shadow.SourceRefused, KeyError, TypeError, AttributeError) as exc:
            raise EvidenceRejected('DIRECTORY_READER_REFUSED') from exc
    age_stale = None
    if source == 'NASDAQ_DIRECTORY':
        stamp = assessment['snapshot_creation_local_et']
        generated = datetime.strptime(stamp.replace(':', ''), '%m%d%Y%H%M')
        generated = generated.replace(tzinfo=ZoneInfo('America/New_York'))
        age_stale = (cutoff - generated.astimezone(timezone.utc)).total_seconds() > 72 * 3600
        demand(generated.astimezone(timezone.utc) <= observed,
               'DIRECTORY_GENERATED_AFTER_CAPTURE')
    return {
        'schema': SCHEMA, 'source': source, 'symbol': ticker,
        'status': 'STALE_SNAPSHOT_NOT_ACCEPTED' if age_stale else
                  'FORMAT_REVIEW_ONLY_ORIGIN_NOT_ATTESTED',
        'parser_status': assessment['status'],
        'event_count': assessment.get('event_count'),
        'content_sha256': digest,
        'observed_at_utc': observed.isoformat(),
        'directory_over_72h_old': age_stale,
        'http_origin_independently_proven': False,
        'completeness_proven': False,
        'first_public_availability_proven': False,
        'may_clear_risk': False, 'may_change_al': False,
        'may_send_alert': False, 'may_write_sheet': False,
        'may_place_order': False, 'network_calls_made': 0,
    }
