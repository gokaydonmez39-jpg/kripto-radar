#!/usr/bin/env python3
"""NASDAQ ONLY A34: preopening private 477 IEX + Sheet acceptance. READ ONLY.

Never writes Sheets, public raw bars, signals, outbox or notifications; no orders.
All exceptions are redacted in public CI logs. Device ACK is always unknown.
"""
import datetime as dt
import json
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
