#!/usr/bin/env python3
"""NASDAQ ONLY A34: preopening private 477 IEX + Sheet acceptance. READ ONLY.

Never writes Sheets, public raw bars, signals, outbox or notifications; no orders.
All exceptions are redacted in public CI logs. Device ACK is always unknown.
"""
import datetime as dt
import json
import math
import os
import re
from urllib.error import HTTPError, URLError

EXPECTED_UNIVERSE = 477
HEX = re.compile(r'^[0-9a-f]{64}$')
SYMBOL = re.compile(r'^[A-Z0-9.]{1,16}$')
CATEGORIES = {'AL', 'IZLE', 'ELE'}


class PreopenBlocked(ValueError):
    pass


# Public A34 logs may contain ONLY fixed, source-reviewed failure identifiers.
# Never serialize tokens, private rows, symbols, vendor errors, HTTP URLs,
# response bodies or untrusted exception strings.
_SAFE_PREOPEN_CODES = frozenset({
    'SOURCE_PROOF_ABSENT',
    'SOURCE_PROOF_MISSING_DUPLICATE_OR_MALFORMED',
    'EXACT_477_SCOPE_MISMATCH',
    'SCANS_MISSING',
    'SCAN_DUPLICATE_OR_NONMONOTONIC',
    'LATEST_COMPLETED_SCAN_NOT_READY',
    'SCAN_NOT_FINAL_477',
    'SCAN_NEW_AL_COUNT_INVALID',
    'CURRENT_SOURCE_OR_POLICY_SHA_CONFLICT',
    'IEX_PROVIDER_SCOPE_MISMATCH',
    'IEX_INCOMPLETE_OR_STALE_SESSION',
    'IEX_LIVE_AL_COUNT_VS_PRIVATE_SCAN_CONFLICT',
    'CANDIDATE_HEADER_DRIFT',
    'AL_IDENTITY_INPUT_INVALID',
    'CANDIDATE_IDENTITY_INVALID',
    'CANDIDATE_KEY_DUPLICATE',
    'CURRENT_CANDIDATE_COUNT_MISMATCH',
    'AL_IDENTITY_RECOMPUTE_INVALID',
    'AL_IDENTITY_MISMATCH',
    'AL_LEVEL_INPUT_INVALID',
    'AL_LEVEL_INVALID',
    'AL_LEVEL_SOURCE_MISMATCH',
    'NOT_BEFORE_NEXT_XNAS_OPEN',
    'PRIVATE_SHEET_CREDENTIALS_MISSING',
    'OUTBOX_OR_PANEL_NOT_READY',
    'CONCURRENT_PRIVATE_SHEET_CHANGE',
})
_SAFE_FLIGHT_CODES = frozenset({
    'FLIGHT_BAD_OPEN_STATUS',
    'FLIGHT_BAD_OR_DUPLICATE_EPISODE',
    'FLIGHT_CLOSED_MISSING_EVIDENCE',
    'FLIGHT_CURRENT_SCAN_SHA_MISSING',
    'FLIGHT_DUPLICATE_EVENT',
    'FLIGHT_EPISODE_INCOMPLETE',
    'FLIGHT_EPISODE_LEVEL_GEOMETRY',
    'FLIGHT_EPISODE_NOT_LINKED_TO_SCAN',
    'FLIGHT_EVENT_DEDUP_KEY_INVALID',
    'FLIGHT_EVENT_INCOMPLETE',
    'FLIGHT_EVENT_WRONG_EPISODE_OR_DAY',
    'FLIGHT_EXPECTED_COMPLETED_EOD_MISSING',
    'FLIGHT_HEADER_DRIFT',
    'FLIGHT_HISTORICAL_ISSUANCE_SHA_DRIFT',
    'FLIGHT_LEVEL_NOT_VALID',
    'FLIGHT_MISSING_TERMINAL_EVENT',
    'FLIGHT_NEW_AL_COUNT_NONINTEGER',
    'FLIGHT_NO_SCAN',
    'FLIGHT_ORIGINAL_LEVELS_CHANGED',
    'FLIGHT_ORPHAN_EVENT',
    'FLIGHT_PARTIAL_SHA_PROVENANCE',
    'FLIGHT_PRIVATE_CREDENTIALS_MISSING',
    'FLIGHT_SCAN_AL_CANDIDATE_COUNT_MISMATCH',
    'FLIGHT_SCAN_DATE_ORDER_OR_DUPLICATE',
    'FLIGHT_SCAN_NOT_FULL_FINAL',
    'FLIGHT_SILENT_MISSING_PRIOR_AL_EVENT',
    'FLIGHT_SUPPRESSION_WITHOUT_PRIOR_ACTIVE_EPISODE',
    'FLIGHT_TABLE_MISSING_OR_TOO_LARGE',
    'FLIGHT_TERMINAL_EVENT_INVALID',
    'FLIGHT_TORN_PRIVATE_READ',
    'FLIGHT_UNATTESTED_DELIVERY_STATE',
    'FLIGHT_UNKNOWN_EPISODE_STATUS',
    'FLIGHT_UNPAIRED_GAP_STOP_EVENT',
})
_SAFE_READONLY_EVIDENCE_CODES = frozenset({
    'EXPECTED_PRIVATE_SHEET_MISSING',
    'PRIVATE_SHEETS_SERVICE_ACCOUNT_REQUIRED',
    'PRIVATE_SPREADSHEET_ID_INVALID',
    'READ_ONLY_GOOGLE_TOKEN_MISSING',
    'READ_ONLY_SHEET_WHITELIST',
    'SHEET_TIMEZONE_CHANGED',
})

_SAFE_STAGES = frozenset({
    'START',
    'MARKET_CALENDAR',
    'SOURCE_SCOPE',
    'PRIVATE_AUTH_AND_METADATA',
    'SHEET_SOURCE_READ',
    'PRIVATE_FLIGHT_RECORDER',
    'SOURCE_SHA_SCOPE',
    'IEX_RECOMPUTE',
    'AL_IDENTITY',
    'AL_LEVELS',
    'READBACK',
    'SUMMARY',
})


def public_preopen_failure_code(exc):
    """No user-controlled details can become a public diagnostic identifier."""
    if type(exc) is PreopenBlocked and str(exc) in _SAFE_PREOPEN_CODES:
        return str(exc)
    # External read-only modules raise their own classes. Match only class
    # name plus explicit allowlisted constant; no vendor messages escape.
    if type(exc).__name__ == 'FlightRecorderBlocked' and str(exc) in _SAFE_FLIGHT_CODES:
        return str(exc)
    if type(exc).__name__ == 'EvidenceBlocked' and str(exc) in _SAFE_READONLY_EVIDENCE_CODES:
        return str(exc)
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return 'A34_HTTP_429'
        if exc.code in (401, 403, 404):
            return 'A34_HTTP_' + str(exc.code)
        if exc.code in (500, 502, 503, 504):
            return 'A34_HTTP_5XX'
        return 'A34_HTTP_OTHER'
    if isinstance(exc, (URLError, TimeoutError)):
        return 'A34_TRANSPORT_ERROR'
    return 'UNCLASSIFIED'


def need(ok, reason):
    if not ok:
        raise PreopenBlocked(reason)


def source_proof(note):
    """Independent implementation; never trust the production writer's parser."""
    need(type(note) is str, 'SOURCE_PROOF_ABSENT')
    fields = [part.strip() for part in note.split(';')]
    pairs = {}
    for key in ('scopeSHA', 'algorithmSHA'):
        hits = [p[len(key) + 1:] for p in fields if p.startswith(key + '=')]
        need(len(hits) == 1 and bool(HEX.fullmatch(hits[0])),
             'SOURCE_PROOF_MISSING_DUPLICATE_OR_MALFORMED')
        pairs[key] = hits[0]
    return pairs


def validate_scope_and_scan(symbols, scans, asof, scope_sha, algorithm_sha):
    need(type(symbols) is list and len(symbols) == EXPECTED_UNIVERSE
         and len(set(symbols)) == EXPECTED_UNIVERSE
         and all(type(s) is str and SYMBOL.fullmatch(s) for s in symbols),
         'EXACT_477_SCOPE_MISMATCH')
    need(type(scans) is list and len(scans) >= 2,
         'SCANS_MISSING')
    days = [str(row[0]) for row in scans[1:] if row and row[0]]
    need(days == sorted(set(days)), 'SCAN_DUPLICATE_OR_NONMONOTONIC')
    need(days[-1] == asof, 'LATEST_COMPLETED_SCAN_NOT_READY')
    latest = scans[-1]
    need(len(latest) >= 10 and latest[2:7] ==
         ['477', '477', '477', '0', 'TRUE'],
         'SCAN_NOT_FINAL_477')
    count = str(latest[7])
    need(re.fullmatch(r'(?:0|[1-9][0-9]*)', count),
         'SCAN_NEW_AL_COUNT_INVALID')
    proof = source_proof(latest[9])
    need(proof['scopeSHA'] == scope_sha and
         proof['algorithmSHA'] == algorithm_sha,
         'CURRENT_SOURCE_OR_POLICY_SHA_CONFLICT')
    return int(count)


def validate_iex_result(symbols, asof, count, rows):
    need(type(rows) is dict and set(rows) == set(symbols),
         'IEX_PROVIDER_SCOPE_MISMATCH')
    n_al = 0
    for symbol in symbols:
        entry = rows[symbol]
        need(type(entry) is dict and entry.get('symbol') == symbol
             and entry.get('asof_et') == asof
             and type(entry.get('sessions')) is int
             and entry['sessions'] >= 52
             and entry.get('decision') in CATEGORIES,
             'IEX_INCOMPLETE_OR_STALE_SESSION')
        n_al += entry['decision'] == 'AL'
    need(n_al == count, 'IEX_LIVE_AL_COUNT_VS_PRIVATE_SCAN_CONFLICT')
    return {'state': 'CORE_PREOPEN_PASS_DEVICE_ACK_UNKNOWN',
            'asof_et': asof, 'covered': len(symbols),
            'live_recomputed_al_count': n_al, 'device_ack': False,
            'private_data_published': False, 'writes': False,
            'orders': False, 'source': 'ALPACA_IEX_RAW_1DAY'}


def validate_al_identity(candidate_table, asof, count, results):
    """Reject same-count but different-symbol AL sets.

    This pure, private-only check has no I/O and never emits ticker details.
    The existing flight recorder checks the full Sheet header and event ledger;
    we independently verify identities and compare the exact current AL set.
    """
    need(type(candidate_table) is list and bool(candidate_table)
         and type(candidate_table[0]) is list
         and tuple(candidate_table[0][:3]) ==
         ('ALARM KİMLİĞİ', 'ASOF ET', 'SEMBOL'),
         'CANDIDATE_HEADER_DRIFT')
    need(type(asof) is str and type(count) is int and count >= 0
         and type(results) is dict, 'AL_IDENTITY_INPUT_INVALID')
    seen_keys = set()
    recorded_current = set()
    for row in candidate_table[1:]:
        if not row or all(value in ('', None) for value in row):
            continue
        need(type(row) is list and len(row) >= 3 and
             all(type(v) is str for v in row[:3]),
             'CANDIDATE_IDENTITY_INVALID')
        key, start, symbol = row[:3]
        need(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', start)) and
             bool(SYMBOL.fullmatch(symbol)) and key == start + '|' + symbol,
             'CANDIDATE_IDENTITY_INVALID')
        need(key not in seen_keys, 'CANDIDATE_KEY_DUPLICATE')
        seen_keys.add(key)
        if start == asof:
            recorded_current.add(symbol)
    need(len(recorded_current) == count,
         'CURRENT_CANDIDATE_COUNT_MISMATCH')
    need(all(type(v) is dict for v in results.values()),
         'AL_IDENTITY_RECOMPUTE_INVALID')
    computed_current = {symbol for symbol, value in results.items()
                        if value.get('decision') == 'AL'}
    need(recorded_current == computed_current, 'AL_IDENTITY_MISMATCH')
    return 'EXACT_AL_IDENTITY_PASS'


def validate_al_levels(candidate_table, asof, results):
    """Independently compare source IEX AL levels to private Sheet rows.

    Current-ASOF only, read-only, never exposes price/symbol in exceptions.
    Call only after validate_iex_result and validate_al_identity PASS.
    """
    need(type(candidate_table) is list and candidate_table
         and type(results) is dict and type(asof) is str,
         'AL_LEVEL_INPUT_INVALID')
    columns = ((4, 'close'), (5, 'indicative_stop'),
               (6, 'indicative_target_2r'))
    for row in candidate_table[1:]:
        if not row or all(value in ('', None) for value in row):
            continue
        need(type(row) is list and len(row) >= 3,
             'AL_LEVEL_INVALID')
        if row[1] != asof:
            continue
        need(len(row) >= 7 and type(row[2]) is str,
             'AL_LEVEL_INVALID')
        entry = results.get(row[2])
        need(type(entry) is dict and entry.get('decision') == 'AL',
             'AL_LEVEL_SOURCE_MISMATCH')
        for i, key in columns:
            raw = row[i]
            need(type(raw) is str and
                 bool(re.fullmatch(r'(?:0|[1-9][0-9]*)(?:[.,][0-9]{1,3})?',
                                   raw.strip())), 'AL_LEVEL_INVALID')
            level = float(raw.strip().replace(',', '.'))
            actual = entry.get(key)
            need(type(actual) in (float, int) and
                 math.isfinite(actual) and actual > 0 and level > 0,
                 'AL_LEVEL_INVALID')
            need(abs(level - actual) <= 0.0005,
                 'AL_LEVEL_SOURCE_MISMATCH')
    return 'EXACT_AL_LEVELS_PASS'


def live_entrypoint(stage=None):
    # Import production modules only on the authorized GitHub runner; no
    # third-party vendor or broker SDK is imported/executed by this preflight.
    import exchange_calendars as ec
    import engine
    import runner
    from performance_lab.private_performance_adapter import PrivateSheetReadOnly
    from performance_lab.private_flight_recorder import inspect

    stage = {} if stage is None else stage
    stage['current'] = 'MARKET_CALENDAR'
    now = dt.datetime.now(dt.timezone.utc)
    asof = engine.trading_asof(now).isoformat()
    cal = ec.get_calendar('XNAS')
    next_session = cal.next_session(asof)
    need(now < cal.session_open(next_session).to_pydatetime(),
         'NOT_BEFORE_NEXT_XNAS_OPEN')
    stage['current'] = 'SOURCE_SCOPE'
    symbols = runner.get_scope(watchlist_file='nasdaq_watchlist_477.json',asof=asof)
    stage['current'] = 'PRIVATE_AUTH_AND_METADATA'
    secret = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON', '')
    private_id = os.environ.get('XRAY_PRIVATE_SPREADSHEET_ID', '')
    need(bool(secret) and bool(private_id), 'PRIVATE_SHEET_CREDENTIALS_MISSING')
    api = PrivateSheetReadOnly(secret, private_id)
    api.verify_metadata()
    def read_all():
        return [api.read('ADAY_GECMISI','M'), api.read('TARAMA_KAYITLARI','J'),
                api.read('UYARI_OLAYLARI','T'), api.read('PANEL','B')]
    stage['current'] = 'SHEET_SOURCE_READ'
    first = read_all()
    stage['current'] = 'PRIVATE_FLIGHT_RECORDER'
    flight = inspect(*first, expected_asof=asof)
    need(flight['unreserved_current_eod_al'] == 0
         and flight['unreserved_prior_eod_al'] == 0
         and not flight['panel_non_authoritative_stale']
         and not flight['panel_missing_asof'],
         'OUTBOX_OR_PANEL_NOT_READY')
    stage['current'] = 'SOURCE_SHA_SCOPE'
    expected = validate_scope_and_scan(symbols, first[1], asof,
                                       runner.sha_symbols(symbols),
                                       runner.analysis_fingerprint())
    stage['current'] = 'IEX_RECOMPUTE'
    bars = engine.live_read(symbols, asof)
    results = {sym: engine.analyze(sym, bars.get(sym, []), asof)
               for sym in symbols}
    summary = validate_iex_result(symbols, asof, expected, results)
    stage['current'] = 'AL_IDENTITY'
    summary['al_identity_check'] = validate_al_identity(
        first[0], asof, expected, results)
    stage['current'] = 'AL_LEVELS'
    summary['al_level_check'] = validate_al_levels(first[0], asof, results)
    stage['current'] = 'READBACK'
    need(first == read_all(), 'CONCURRENT_PRIVATE_SHEET_CHANGE')
    summary['next_xnas_session'] = str(next_session.date())
    summary['open_episodes'] = flight['open_count']
    summary['quarantined_research_events'] = flight['quarantined_events']
    if flight['quarantined_events']:
        summary['state'] = 'CORE_PREOPEN_PASS_DISPUTED_EVENT_HOLD_DEVICE_ACK_UNKNOWN'
    summary['pending_device_ack_events'] = flight['pending_device_ack']
    stage['current'] = 'SUMMARY'
    return summary


def main():
    stage = {'current': 'START'}
    try:
        result = live_entrypoint(stage=stage)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Keep existing fail-closed sentinel for upstream consumers, and add
        # one static categorical diagnostic. No private data is exposed.
        print('XRAY_NASDAQ_A34_PREOPEN=BLOCKED_NO_DATA_PUBLISHED_NO_WRITES')
        current = stage.get('current')
        print(json.dumps({
            'schema': 'XRAY_NASDAQ_A34_SAFE_DIAGNOSTIC_V1',
            'status': 'A34_PREOPEN_BLOCKED',
            'stage': current if current in _SAFE_STAGES else 'UNKNOWN',
            'reason_code': public_preopen_failure_code(exc),
            'writes': False, 'orders': False,
            'private_data_published': False, 'device_ack': 'UNKNOWN',
            'execution': 'NONE',
        }, sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
