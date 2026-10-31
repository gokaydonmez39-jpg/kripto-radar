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

EXPECTED_UNIVERSE = 477
HEX = re.compile(r'^[0-9a-f]{64}$')
SYMBOL = re.compile(r'^[A-Z0-9.]{1,16}$')
CATEGORIES = {'AL', 'IZLE', 'ELE'}


class PreopenBlocked(ValueError):
    pass


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


def live_entrypoint():
    # Import production modules only on the authorized GitHub runner; no
    # third-party vendor or broker SDK is imported/executed by this preflight.
    import exchange_calendars as ec
    import engine
    import runner
    from performance_lab.private_performance_adapter import PrivateSheetReadOnly
    from performance_lab.private_flight_recorder import inspect

    now = dt.datetime.now(dt.timezone.utc)
    asof = engine.trading_asof(now).isoformat()
    cal = ec.get_calendar('XNAS')
    next_session = cal.next_session(asof)
    need(now < cal.session_open(next_session).to_pydatetime(),
         'NOT_BEFORE_NEXT_XNAS_OPEN')
    symbols = runner.get_scope(watchlist_file='nasdaq_watchlist_477.json')
    secret = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON', '')
    private_id = os.environ.get('XRAY_PRIVATE_SPREADSHEET_ID', '')
    need(bool(secret) and bool(private_id), 'PRIVATE_SHEET_CREDENTIALS_MISSING')
    api = PrivateSheetReadOnly(secret, private_id)
    api.verify_metadata()
    def read_all():
        return [api.read('ADAY_GECMISI','M'), api.read('TARAMA_KAYITLARI','J'),
                api.read('UYARI_OLAYLARI','T'), api.read('PANEL','B')]
    first = read_all()
    flight = inspect(*first, expected_asof=asof)
    need(flight['unreserved_current_eod_al'] == 0
         and flight['unreserved_prior_eod_al'] == 0
         and not flight['panel_non_authoritative_stale']
         and not flight['panel_missing_asof'],
         'OUTBOX_OR_PANEL_NOT_READY')
    expected = validate_scope_and_scan(symbols, first[1], asof,
                                       runner.sha_symbols(symbols),
                                       runner.analysis_fingerprint())
    bars = engine.live_read(symbols, asof)
    results = {sym: engine.analyze(sym, bars.get(sym, []), asof)
               for sym in symbols}
    summary = validate_iex_result(symbols, asof, expected, results)
    summary['al_identity_check'] = validate_al_identity(
        first[0], asof, expected, results)
    summary['al_level_check'] = validate_al_levels(first[0], asof, results)
    need(first == read_all(), 'CONCURRENT_PRIVATE_SHEET_CHANGE')
    summary['next_xnas_session'] = str(next_session.date())
    summary['open_episodes'] = flight['open_count']
    summary['quarantined_research_events'] = flight['quarantined_events']
    if flight['quarantined_events']:
        summary['state'] = 'CORE_PREOPEN_PASS_DISPUTED_EVENT_HOLD_DEVICE_ACK_UNKNOWN'
    summary['pending_device_ack_events'] = flight['pending_device_ack']
    return summary


def main():
    try:
        result = live_entrypoint()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Never leak Google tokens, API keys, private candidate rows, HTTP
        # errors, symbol levels, exceptions or vendor payloads to public logs.
        print('XRAY_NASDAQ_A34_PREOPEN=BLOCKED_NO_DATA_PUBLISHED_NO_WRITES')
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
