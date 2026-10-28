"""A12: private, read-only, fail-closed source bridge to A11 scientific witness.

Called ONLY after the existing EOD producer and lifecycle job have completed.
Never writes Sheets, public artifacts, orders, notifications or rule changes.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

import exchange_calendars as ec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import daily_job
import engine
import runner
import tracker
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER
from nasdaq_performance_guard import (SOURCE, EvidenceBlocked, evaluate_episode,
                                      scorecard, integrity_alerts, drift_watch,
                                      iso, need, price)

SYMBOL_RE = re.compile(r'^[A-Z][A-Z0-9.]{0,15}$')
SCAN_SHA_RE = re.compile(r'(?:^|;)scopeSHA=([0-9a-f]{64});algorithmSHA=([0-9a-f]{64})(?:;|$)')
OPEN_RE = re.compile(r'^AÇIK • ([0-9]{1,2})/15 SEANS$')
CLOSE_RE = re.compile(r'^KAPALI • ([A-Z_]+) • ([0-9]{1,2})/15 SEANS$')
ENDPOINT = 'https://sheets.googleapis.com/v4/spreadsheets/'
MAX_PRIVATE_ROWS = 1000


def _num(value):
    """Exact decimal from the displayed Turkish-formatted private sheet cell."""
    need(type(value) in (str, int, float), 'SHEET_PRICE_TYPE')
    s = str(value).strip().replace(',', '.')
    need(bool(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', s)), 'SHEET_NUMERIC_FORMAT')
    return price(s)


def _count(value):
    need(type(value) in (str, int, float), 'SCAN_COUNT_TYPE')
    raw = str(value).strip().replace(',', '.')
    need(bool(re.fullmatch(r'[0-9]+(?:\\.0+)?', raw)), 'SCAN_COUNT_NONINTEGER')
    return Decimal(raw)


def _cohort(values, header):
    need(type(values) is list and len(values) > 0, 'MISSING_PRIVATE_SHEET_TABLE')
    need(tuple(values[0]) == header, 'PRIVATE_SHEET_HEADER_DRIFT')
    need(len(values) <= MAX_PRIVATE_ROWS, 'PRIVATE_SHEET_TOO_MANY_ROWS')
    rows = [list(r) for r in values[1:] if r and any(str(c) for c in r)]
    return rows


def _fingerprints(note):
    match = SCAN_SHA_RE.search(str(note))
    return match.groups() if match else None


def source_plan(candidate_values, scan_values, asof, universe, scope_sha, policy_sha):
    """Validate 477 universe, verified final asof, identities, every candidate.

    Incomplete/manual older issuance provenance is *explicitly excluded*;
    it cannot silently become a backfilled winner. No private rows are logged.
    """
    cal = ec.get_calendar('XNAS')
    iso(asof)
    need(cal.is_session(asof), 'AUDIT_ASOF_NOT_XNAS')
    need(type(universe) is list and len(universe) == 477 and
         len(set(universe)) == 477 and
         all(type(s) is str and SYMBOL_RE.fullmatch(s) for s in universe),
         'UNIVERSE_NOT_EXACT_477')
    need(type(scope_sha) is str and re.fullmatch(r'[0-9a-f]{64}', scope_sha),
         'SCOPE_SHA_INVALID')
    need(type(policy_sha) is str and re.fullmatch(r'[0-9a-f]{64}', policy_sha),
         'POLICY_SHA_INVALID')
    scans = _cohort(scan_values, SCAN_HEADER)
    candidates = _cohort(candidate_values, CANDIDATE_HEADER)
    scan_keys = [r[0] for r in scans]
    need(len(set(scan_keys)) == len(scan_keys), 'DUPLICATE_SCAN_DAY')
    by_day = {r[0]: r for r in scans}
    need(asof in by_day, 'MISSING_CURRENT_477_FINAL_SCAN')
    last = by_day[asof]
    need(len(last) >= 10 and
         [_count(last[x]) for x in (2,3,4,5)] ==
         [Decimal(477),Decimal(477),Decimal(477),Decimal(0)] and
         str(last[6]).upper() == 'TRUE',
         'CURRENT_SCAN_NOT_477_COMPLETE')
    need(_fingerprints(last[9]) == (scope_sha, policy_sha),
         'CURRENT_SCAN_SCOPE_OR_POLICY_MISMATCH')
    keys = set()
    verified = []
    excluded = 0
    for row in candidates:
        need(len(row) >= 13, 'CANDIDATE_ROW_INCOMPLETE')
        key = row[0]
        need(type(key) is str and key not in keys, 'DUPLICATE_OR_NONSTRING_EPISODE')
        keys.add(key)
        start, mark, symbol = key.partition('|')
        need(mark and symbol in universe and row[1] == start and row[2] == symbol,
             'CANDIDATE_IDENTITY_MISMATCH')
        iso(start)
        need(cal.is_session(start) and start <= asof, 'CANDIDATE_FUTURE_OR_NONSESSION')
        close, stop, target = (_num(row[x]) for x in (4,5,6))
        need(stop < close < target and
             abs(target - (close + 2*(close-stop))) <= Decimal('.025'),
             'CANDIDATE_STOP_TARGET_DRIFT')
        status = str(row[7])
        m = OPEN_RE.fullmatch(status)
        c = CLOSE_RE.fullmatch(status)
        need(bool(m or c), 'CANDIDATE_UNRECOGNIZED_LIFECYCLE')
        held = int((m or c).group(1 if m else 2))
        need(0 <= held <= 15 and (not m or held < 15),
             'CANDIDATE_INVALID_HELD_DAYS')
        issuance = by_day.get(start)
        fingerprints = _fingerprints(issuance[9]) if issuance and len(issuance)>=10 else None
        if fingerprints != (scope_sha,policy_sha):
            excluded += 1
            continue
        verified.append({'key': key, 'symbol': symbol, 'start': start, 'close': close,
                         'stop': stop, 'target': target, 'row': row,
                         'is_open': bool(m), 'held': held,
                         'old_outcome': None if m else c.group(1)})
    need(len(keys) <= MAX_PRIVATE_ROWS, 'CANDIDATE_CAPACITY')
    return {'asof': asof, 'verified': verified,
            'total': len(keys), 'excluded_unproven_issuance': excluded,
            'scope_sha': scope_sha, 'policy_sha': policy_sha}


def _bars_for(item, all_bars, asof):
    """Accept full raw provider history; require the signal-day baseline witness."""
    raw = all_bars.get(item['symbol'])
    need(type(raw) is list, 'PROVIDER_MISSING_SYMBOL_HISTORY')
    sessions = ec.get_calendar('XNAS')
    max_days = min(15, len(sessions.sessions_in_range(
        date.fromordinal(iso(item['start']).toordinal()+1).isoformat(), asof)))
    selected, emission_day = [], None
    for bar in raw:
        need(type(bar) is dict, 'PROVIDER_BAR_NOT_OBJECT')
        day = str(bar.get('timestamp', ''))[:10]
        if day == item['start']:
            need(emission_day is None, 'DUPLICATE_SIGNAL_DAY_BAR')
            emission_day = bar
        if item['start'] < day <= asof:
            selected.append(bar)
    need(emission_day is not None, 'MISSING_ORIGINAL_SIGNAL_DAY_IEX_BAR')
    # Historical Sheet price may be displayed to 2-3 decimals.
    need(abs(_num(emission_day['close']) - item['close']) <= Decimal('.00501'),
         'ORIGINAL_IEX_CLOSE_MISMATCH')
    # Verify chronology and provider bar count before invoking A11.
    need(len(selected) >= max_days, 'MISSING_DUE_FOLLOWUP_BAR')
    eligible = selected[:max_days]
    need(len(eligible) == max_days, 'MISSING_FULL_15_SESSION_WINDOW')
    clean = []
    for bar in eligible:
        clean.append({'date': str(bar['timestamp'])[:10],
                      **{x: bar[x] for x in ('open','high','low','close','volume')}})
    return eligible, clean


def audit_plan(plan, read_batch):
    """Cross-check A11 against untouched original tracker AND private sheet.

    All candidates are re-evaluated from original issuance, not only winners.
    Any stale sheet status or changed provider data blocks the whole audit.
    """
    need(type(plan) is dict and type(read_batch) is not str,
         'AUDIT_PLAN_SCHEMA')
    verified = plan['verified']
    if not verified:
        return {'status': 'HOLD_NO_PROVEN_ISSUANCE',
                'total_episodes': plan['total'],
                'excluded_issuance': plan['excluded_unproven_issuance'],
                'verified_episodes': 0, 'n_complete': 0,
                'rule_change': False, 'notification_delivery': False}
    symbols = sorted({i['symbol'] for i in verified})
    raw = read_batch(symbols,plan['asof'])
    need(type(raw) is dict and set(raw) == set(symbols),
         'UNEXPECTED_PROVIDER_SYMBOL_UNIVERSE')
    reports = []
    for item in verified:
        bars, normalized = _bars_for(item,raw,plan['asof'])
        legacy = {'id': item['key'], 'symbol': item['symbol'],
                  'asof_et': item['start'],
                  'reference_close': float(item['close']),
                  'stop': float(item['stop']),
                  'target_2r': float(item['target']),
                  'status': 'OPEN','processed_through': item['start'],
                  'outcome': None, 'days_held': 0, 'events': []}
        # Current legacy tracker is independent of the new next-open-cost model.
        tracker.track_symbol(legacy,bars,plan['asof'],expiry_sessions=15)
        need(legacy['days_held'] == item['held'],
             'PRIVATE_SHEET_DAY_COUNT_STALE_OR_CONFLICT')
        need((legacy['status'] == 'OPEN') == item['is_open'],
             'PRIVATE_SHEET_TERMINAL_STATE_CONFLICT')
        if not item['is_open']:
            recorded = str(item['row'][10]).strip().replace(',', '.')
            need(bool(re.fullmatch(r'-?[0-9]+(?:\\.[0-9]+)?', recorded)),
                 'PRIVATE_SHEET_TERMINAL_PCT_INVALID')
            recorded_pct = Decimal(recorded)
            need(recorded_pct.is_finite() and
                 legacy['outcome'] == item['old_outcome'] and
                 str(item['row'][8]) == legacy['closed_date'] and
                 str(item['row'][9]) == legacy['outcome'] and
                 abs(recorded_pct - Decimal(str(legacy['hypothetical_result_pct'])))
                 <= Decimal('.0051'), 'PRIVATE_SHEET_TERMINAL_OUTCOME_DRIFT')
        episode = {'episode_id': item['key'], 'symbol': item['symbol'],
                   'signal_asof': item['start'], 'data_through': plan['asof'],
                   'source': SOURCE, 'scope_sha256': plan['scope_sha'],
                   'policy_sha256': plan['policy_sha'],
                   'reference_close': str(item['close']), 'stop': str(item['stop']),
                   'target': str(item['target']), 'bars': normalized}
        reports.append(evaluate_episode(episode))
    s = scorecard(reports)
    anomalies = integrity_alerts(reports)
    drift = drift_watch(reports)
    reason = 'HOLD_UNPROVEN_HISTORICAL_COHORT' if plan['excluded_unproven_issuance'] else s['status']
    return {'status': reason, 'total_episodes': plan['total'],
            'excluded_issuance': plan['excluded_unproven_issuance'],
            'verified_episodes': len(reports),
            'n_complete': s['n_complete'],
            'n_censored': s['n_censored_or_invalidated'],
            'integrity_events': len(anomalies),
            'drift_status': drift['state'],
            'benchmark_proven': False, 'holdout_proven': False,
            'rule_change': False, 'notification_delivery': False,
            'real_fill_proven': False}


class PrivateSheetReadOnly:
    """Credential's OAuth scope is truly read-only; API exposes no write method."""

    def __init__(self, credentials_json, spreadsheet_id):
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import Request as RefreshRequest
        need(type(spreadsheet_id) is str and
             re.fullmatch('[A-Za-z0-9_-]{20,100}',spreadsheet_id),
             'PRIVATE_SPREADSHEET_ID_INVALID')
        info = json.loads(credentials_json)
        need(type(info) is dict and info.get('type') == 'service_account',
             'PRIVATE_SHEETS_SERVICE_ACCOUNT_REQUIRED')
        creds = Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        creds.refresh(RefreshRequest())
        need(bool(creds.token), 'READ_ONLY_GOOGLE_TOKEN_MISSING')
        self._token = creds.token
        self._url = ENDPOINT + spreadsheet_id

    def _get(self, path):
        req = Request(self._url + path,
                      headers={'Authorization': 'Bearer '+self._token,
                               'Accept': 'application/json'},
                      method='GET')
        with urlopen(req,timeout=25) as resp:
            return json.load(resp)

    def read(self, title, last_column):
        need((title,last_column) in
             {('ADAY_GECMISI','M'),('TARAMA_KAYITLARI','J')},
             'READ_ONLY_SHEET_WHITELIST')
        range_a1 = quote(f"'{title}'!A1:{last_column}{MAX_PRIVATE_ROWS}",safe='')
        return self._get('/values/'+range_a1+'?valueRenderOption=FORMATTED_VALUE').get('values',[])

    def verify_metadata(self):
        obj = self._get('?fields=properties(timeZone),sheets.properties(title)')
        need(obj.get('properties',{}).get('timeZone')=='Europe/Istanbul',
             'SHEET_TIMEZONE_CHANGED')
        titles = {s.get('properties',{}).get('title')
                  for s in obj.get('sheets',[])}
        need({'PANEL','ADAY_GECMISI','TARAMA_KAYITLARI','KURALLAR','UYARI_OLAYLARI'}
             <= titles, 'EXPECTED_PRIVATE_SHEET_MISSING')


def live_entrypoint():
    """Only stdout whitelist; even unexpected failure never emits private payload."""
    try:
        asof = daily_job.current_completed_session()
        need(type(asof) is str and len(asof)==10,
             'NO_COMPLETED_OFFICIAL_SESSION')
        creds = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON','')
        sheet_id = os.environ.get('XRAY_PRIVATE_SPREADSHEET_ID','')
        need(bool(creds) and bool(sheet_id),'PRIVATE_CREDENTIALS_NOT_CONFIGURED')
        api = PrivateSheetReadOnly(creds,sheet_id)
        api.verify_metadata()
        values = api.read('ADAY_GECMISI','M')
        scans = api.read('TARAMA_KAYITLARI','J')
        universe = runner.get_scope(watchlist_file=str(ROOT/'nasdaq_watchlist_477.json'))
        plan = source_plan(values,scans,asof,universe,
                           runner.sha_symbols(universe),runner.analysis_fingerprint())
        result = audit_plan(plan,engine.live_read)
        # No race-prone persisted result: readback must be bit-for-bit stable.
        need(values == api.read('ADAY_GECMISI','M') and
             scans == api.read('TARAMA_KAYITLARI','J'),
             'SHEET_CHANGED_DURING_READ_ONLY_AUDIT')
        # Public log only whitelisted integer counters/status; no symbols, prices,
        # returns, raw bars, sheet IDs, token, full exception or incident keys.
        print(json.dumps({'state':result['status'],
                          'verified':result['verified_episodes'],
                          'unproven':result['excluded_issuance'],
                          'finished':result['n_complete'],
                          'no_orders':True,'no_alert_delivery':True},
                         sort_keys=True))
        return 0
    except Exception:
        print('XRAY_PRIVATE_PERFORMANCE=BLOCKED_NO_PUBLISH_NO_WRITES')
        return 3


if __name__ == '__main__':
    raise SystemExit(live_entrypoint())
