#!/usr/bin/env python3
"""Independent ephemeral 477-official-source shadow; never an AL, Sheet or broker input."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner
import handoff_guard
import official_provider_raw_once as provider

SCHEMA = 'XRAY_477_OFFICIAL_SHADOW_V1'
NO_AUTHORITY = {'may_modify_al': False, 'may_modify_stop': False,
                'may_notify': False, 'may_write_sheet': False,
                'may_place_order': False, 'market_clearance_proven': False,
                'historical_pit_proven': False,
                'first_public_availability_proven': False}

class ShadowRefused(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise ShadowRefused(reason)

def utc(value):
    require(type(value) is str and 0 < len(value) <= 50, 'TIME_INVALID')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ShadowRefused('TIME_INVALID') from None
    require(dt.tzinfo is not None, 'TIME_NAIVE')
    return dt.astimezone(timezone.utc)

def validate_eod_snapshot(snapshot, symbols):
    require(type(snapshot) is dict, 'SNAPSHOT_INVALID')
    require(type(symbols) is list and len(symbols) == 477 and
            len(set(symbols)) == 477, 'SCOPE_NOT_477')
    handoff_guard.validate_snapshot(
        snapshot, symbols, scope_sha=runner.sha_symbols(symbols),
        policy_sha=runner.analysis_fingerprint())
    try:
        d = date.fromisoformat(snapshot['asof_et'])
    except (ValueError, TypeError, KeyError):
        raise ShadowRefused('ASOF_INVALID') from None
    today = datetime.now(timezone.utc).date()
    require(d.isoformat() == snapshot['asof_et'] and
            today >= d >= today - timedelta(days=7), 'ASOF_STALE_OR_FUTURE')
    return d

def read_nasdaq_witness(path, observed_at):
    """A repository snapshot is NOT a live clean-halt certificate."""
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
        stamp, now = utc(doc['generated_at_utc']), utc(observed_at)
        require(stamp <= now and doc['alpha_authority'] is False,
                'NASDAQ_WITNESS_INVALID')
        veto = doc['candidate_safety']['veto_symbols']
        require(type(veto) is list and len(veto) == len(set(veto)) and
                all(type(s) is str for s in veto), 'NASDAQ_VETO_INVALID')
        age = (now - stamp).total_seconds()
        return {'status': 'SNAPSHOT_RECENT_REVIEW_ONLY' if age <= 3600
                else 'SNAPSHOT_STALE_UNKNOWN',
                'veto_symbols': frozenset(veto),
                'generated_at_utc': stamp.isoformat(), 'may_clear_risk': False}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            ShadowRefused):
        return {'status': 'SNAPSHOT_REFUSED_UNKNOWN',
                'veto_symbols': frozenset(),
                'generated_at_utc': None, 'may_clear_risk': False}

def compose_shadow(snapshot, symbols, *, observed_at, alpaca, sec, nasdaq):
    """Full exact-identity join. Absence is UNKNOWN; positive records require review."""
    utc(observed_at)
    require(type(alpaca) is dict and type(sec) is dict and
            type(nasdaq) is dict, 'SOURCES_INVALID')
    links = alpaca.get('links')
    require(type(links) is dict and len(links) == 477 and
            set(links) == set(symbols), 'ALPACA_SYMBOL_JOIN_INVALID')
    require(alpaca.get('status') ==
            'ALL_477_BATCH_CHAINS_EXHAUSTED_NOT_MARKET_CLEARANCE' and
            alpaca.get('requested_symbols') == 477 and
            alpaca.get('cross_batch_unique_events_proven') is True,
            'ALPACA_UNVERIFIED')
    require(sec.get('status') in (
        'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE', 'SOURCE_REFUSED',
        'SKIPPED_NO_AUTHORIZED_INPUT'), 'SEC_STATUS_INVALID')
    require(type(nasdaq.get('veto_symbols')) is frozenset,
            'NASDAQ_VETO_INVALID')
    require(date.fromisoformat(snapshot['asof_et']) <=
            utc(observed_at).date(), 'OBSERVED_BEFORE_EOD')
    records, linked_count = [], 0
    for symbol in symbols:
        events = links[symbol]
        require(type(events) in (tuple, list), 'ALPACA_LINK_TYPE_INVALID')
        groups, seen = Counter(), set()
        for row in events:
            require(type(row) in (tuple, list) and len(row) == 3,
                    'ALPACA_LINK_INVALID')
            uid, group, processed = row
            require(type(uid) is str and uid not in seen and
                    group in provider.ALLOWED_GROUPS and
                    type(processed) is str, 'ALPACA_LINK_INVALID')
            seen.add(uid)
            try:
                day = date.fromisoformat(processed)
            except ValueError:
                raise ShadowRefused('ALPACA_EVENT_DATE_INVALID') from None
            require(day.isoformat() == processed and
                    day <= date.fromisoformat(snapshot['asof_et']),
                    'ALPACA_EVENT_AFTER_ASOF')
            groups[group] += 1
        linked_count += len(events)
        sec_pilot = symbol == 'ROAD'
        sec_ok = sec_pilot and sec['status'] == (
            'SEC_RAW_FORMAT_OBSERVED_NOT_PIT_CLEARANCE')
        nasdaq_flag = symbol in nasdaq['veto_symbols']
        review = bool(events) or nasdaq_flag or (
            sec_ok and sec.get('parser_status') == 'SEC_EVENTS_REVIEW')
        records.append({
            'symbol': symbol,
            'state': 'REVIEW_REQUIRED' if review else 'UNKNOWN',
            'alpaca': {'status': 'OBSERVED_EVENT_REVIEW_ONLY' if events else
                       'UNKNOWN_NO_EVENT_ABSENCE_PROOF',
                       'linked_events': len(events),
                       'groups': dict(sorted(groups.items()))},
            'sec': {'status': 'PILOT_OBSERVED_NOT_PIT' if sec_ok else
                    'PILOT_REFUSED_UNKNOWN' if sec_pilot else
                    'UNKNOWN_NO_477_CIK_COVERAGE',
                    'parser_status': sec.get('parser_status') if sec_ok else None},
            'nasdaq': {'status': 'HISTORICAL_FLAG_REVIEW' if nasdaq_flag
                       else 'UNKNOWN_NO_CURRENT_CLEARANCE',
                       'witness_status': nasdaq['status']},
            'may_modify_al': False,
        })
    require(len(records) == 477 and
            len({r['symbol'] for r in records}) == 477,
            'SHADOW_JOIN_INCOMPLETE')
    counts = Counter(r['state'] for r in records)
    require(set(counts).issubset({'REVIEW_REQUIRED', 'UNKNOWN'}),
            'UNSAFE_CLEAR_STATE')
    return {
        'schema': SCHEMA, 'status': 'SOURCE_REVIEW_ONLY_NO_CLEARANCE',
        'asof_et': snapshot['asof_et'], 'observed_at_utc': observed_at,
        'scope_sha256': snapshot['scope_sha256'],
        'analysis_fingerprint_sha256':
            snapshot['analysis_fingerprint_sha256'],
        'records_count': 477, 'records': records,
        'states': dict(sorted(counts.items())),
        'alpaca_unique_events_observed': alpaca['unique_event_ids_observed'],
        'alpaca_symbol_links': linked_count,
        'alpaca_http_pages': alpaca['http_pages'],
        'sec_pilot_status': sec['status'],
        'nasdaq_witness_status': nasdaq['status'],
        **NO_AUTHORITY,
    }

def write_private(path, manifest):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.tmp')
    require(not target.is_symlink() and not temp.exists(),
            'UNSAFE_SHADOW_OUTPUT_PATH')
    raw = (json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + '\n').encode('utf-8')
    try:
        with temp.open('xb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    observed = target.read_bytes()
    require(hashlib.sha256(observed).digest() ==
            hashlib.sha256(raw).digest(), 'SHADOW_READBACK_HASH_MISMATCH')
    doc = json.loads(observed)
    require(doc['records_count'] == len(doc['records']) == 477 and
            doc['scope_sha256'] == manifest['scope_sha256'],
            'SHADOW_READBACK_SCOPE_INVALID')

def main(argv=None):
    cli = argparse.ArgumentParser()
    cli.add_argument('--snapshot', required=True)
    cli.add_argument('--output', required=True)
    cli.add_argument('--nasdaq-witness', required=True)
    args = cli.parse_args(argv)
    input_path = Path(args.snapshot)
    if not input_path.is_file():
        print(json.dumps({'status': 'SKIPPED_NO_VERIFIED_PRIVATE_EOD',
                          **NO_AUTHORITY}, sort_keys=True))
        return 0
    try:
        before = input_path.read_bytes()
        snapshot = json.loads(before)
        symbols = list(provider.read_immutable_477_scope())
        asof = validate_eod_snapshot(snapshot, symbols)
        key = os.environ.get('XRAY_ALPACA_DATA_KEY_ID', '')
        secret = os.environ.get('XRAY_ALPACA_DATA_SECRET_KEY', '')
        require(bool(key and secret), 'ALPACA_KEYS_MISSING')
        fetched = provider.audit_all_477(
            key=key, secret=secret,
            start=(asof - timedelta(days=30)).isoformat(), end=asof.isoformat(),
            scope=tuple(symbols), include_internal_symbol_links=True)
        links = fetched.pop('_internal_symbol_links')
        fetched['links'] = links
        contact = os.environ.get('XRAY_SEC_DECLARED_USER_AGENT', '')
        if contact:
            try:
                sec = provider.sec_raw_audit(declared_agent=contact)
            except provider.Refused:
                sec = {'status': 'SOURCE_REFUSED'}
        else:
            sec = {'status': 'SKIPPED_NO_AUTHORIZED_INPUT'}
        observed = datetime.now(timezone.utc).isoformat()
        nasdaq = read_nasdaq_witness(args.nasdaq_witness, observed)
        manifest = compose_shadow(snapshot, symbols, observed_at=observed,
                                  alpaca=fetched, sec=sec, nasdaq=nasdaq)
        write_private(args.output, manifest)
        require(hashlib.sha256(input_path.read_bytes()).digest() ==
                hashlib.sha256(before).digest(),
                'PRODUCTION_SNAPSHOT_MODIFIED')
        # Only counts enter public GitHub logs; no symbol, event ID, AL or secret.
        print(json.dumps({
            'status': manifest['status'], 'records_count': 477,
            'states': manifest['states'],
            'alpaca_http_pages': manifest['alpaca_http_pages'],
            'alpaca_unique_events_observed':
                manifest['alpaca_unique_events_observed'],
            'sec_pilot_status': manifest['sec_pilot_status'],
            'nasdaq_witness_status': manifest['nasdaq_witness_status'],
            'production_snapshot_unchanged': True, **NO_AUTHORITY
        }, sort_keys=True))
        return 0
    except (ShadowRefused, provider.Refused, ValueError, OSError,
            TypeError, KeyError, handoff_guard.HandoffInvalid):
        print(json.dumps({'status': 'SOURCE_REFUSED_UNKNOWN',
                          'source_evidence_accepted': False,
                          **NO_AUTHORITY}, sort_keys=True))
        return 4

if __name__ == '__main__':
    raise SystemExit(main())
