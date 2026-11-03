#!/usr/bin/env python3
"""Reserve first verified NASDAQ AL events in the private Google Sheet outbox.

Runs after private_sheet_writer's candidate/scan readback. This module never
sends ChatGPT/iOS messages, changes AL/STOP levels, or claims delivery. Existing
keys (including historical REQUESTED and suppressed events) are immutable.
Google Sheets lacks per-key compare-and-swap, so a single writer and repeated
readback are mandatory; exactly-once cross-provider delivery is not claimed.
"""
import argparse
import json
import os
from pathlib import Path

import alert_ledger_contract as contract
import private_sheet_writer as writer

RUN_PREFIX = 'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/'


class OutboxBlocked(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise OutboxBlocked(reason)


def normalized_price(cell):
    return writer.numeric(cell)


def price_matches(cell, engine_value):
    displayed = str(cell).replace(',', '.')
    decimals = len(displayed.split('.', 1)[1]) if '.' in displayed else 0
    tolerance = min(0.00501, 0.5 * 10 ** (-min(decimals, 3)) + 0.00001)
    return abs(normalized_price(cell) - float(engine_value)) <= tolerance


def plan(snapshot, candidates, scans, alerts, run_url):
    """Return only append-only new events. No AL, STOP or existing row mutation."""
    expected = writer.plan(snapshot, candidates, scans, run_url)
    require(not expected['candidate_rows'] and not expected['scan_rows'],
            'UPSTREAM_PRIVATE_SHEET_READBACK_REQUIRED')
    existing_candidates = writer.rows_only(candidates, writer.CANDIDATE_HEADER)
    candidate_by_key = {row[0]: row for row in existing_candidates}
    keys = [row[0] for row in existing_candidates]
    require(len(keys) == len(set(keys)), 'DUPLICATE_CANDIDATE_KEYS')
    prior = contract.parse_ledger(alerts)

    new = []
    expected_events = {}
    for row in snapshot['rows']:
        if row['decision'] != 'AL':
            continue
        symbol = row['symbol']
        asof = snapshot['asof_et']
        candidate_key = asof + '|' + symbol
        candidate = candidate_by_key.get(candidate_key)
        require(candidate is not None and len(candidate) >= 8
                and candidate[1] == asof and candidate[2] == symbol,
                'CANDIDATE_IDENTITY_MISSING')
        for col, value in ((4, row['close']),
                           (5, row['indicative_stop']),
                           (6, row['indicative_target_2r'])):
            require(price_matches(candidate[col], value),
                    'CANDIDATE_IMMUTABLE_LEVEL_DRIFT')
        active_before = any(old[2] == symbol
                            and old[1] < asof
                            and len(old) > 7
                            and str(old[7]).startswith('AÇIK')
                            for old in existing_candidates)
        status = contract.SUPPRESSED if active_before else contract.CONFIRMED_PENDING
        key = contract.event_key(asof, symbol, asof, 'AL_NEW_EPISODE', 1)
        older = prior.get(key)
        if older:
            old = older['row']
            require(len(old) > 17 and old[1] == candidate_key
                    and old[2] == asof and old[3] == symbol
                    and all(price_matches(old[col], row[value])
                            for col, value in ((7, 'close'),
                                               (8, 'indicative_stop'),
                                               (9, 'indicative_target_2r'))),
                    'EXISTING_EVENT_IMMUTABLE_LEVEL_OR_ID_DRIFT')
            valid = ({contract.SUPPRESSED} if active_before else {
                contract.CONFIRMED_PENDING, contract.REQUESTED,
                contract.UNKNOWN, contract.ACKED})
            require(older['status'] in valid, 'EXISTING_EVENT_STATUS_CONFLICT')
            expected_events[key] = tuple(old)
            continue
        payload = [
            key, candidate_key, asof, symbol, asof, 'AL_NEW_EPISODE',
            'YENİ AL BİLDİRİMİ BASKILANDI' if active_before else 'YENİ AL',
            writer.money(row['close']), writer.money(row['indicative_stop']),
            writer.money(row['indicative_target_2r']),
            '', '', '', '', '', '0/15', run_url, status, '',
            ('PRIOR_ACTIVE_EPISODE_NO_NEW_ALERT; NO_DEVICE_ACK; NO_ORDERS'
             if active_before else
             'FIRST_VERIFIED_EOD_EVENT_PENDING; CHATGPT_MESSAGE_NOT_SENT; '
             'DEVICE_ACK_UNKNOWN; NO_ORDERS')
        ]
        require(len(payload) == len(contract.EVENT_HEADER), 'EVENT_COLUMN_COUNT')
        new.append(payload)
        expected_events[key] = tuple(payload)
    require(len(new) + len(prior) < writer.MAX_ROWS, 'OUTBOX_CAPACITY_REACHED')
    return {'new_rows': new, 'original': prior, 'expected': expected_events,
            'asof_et': snapshot['asof_et'],
            'expected_al': expected['expected_count'],
            'suppressed_new': sum(r[17] == contract.SUPPRESSED for r in new),
            'pending_new': sum(r[17] == contract.CONFIRMED_PENDING for r in new)}


def verify_readback(p, observed):
    parsed = contract.parse_ledger(observed)
    old = p['original']
    require(len(parsed) == len(old) + len(p['new_rows']),
            'OUTBOX_READBACK_COUNT_OR_CONCURRENT_DRIFT')
    require(all(k in parsed and parsed[k] == v for k, v in old.items()),
            'OUTBOX_READBACK_HISTORICAL_EVENT_CHANGED')
    for key, expected in p['expected'].items():
        require(key in parsed and parsed[key]['row'] == expected,
                'OUTBOX_READBACK_NEW_EVENT_MISSING_OR_MODIFIED')
    for item in p['new_rows']:
        key = item[0]
        require(key not in old, 'OUTBOX_REPLAY_ATTEMPT')
    return {'status': 'AL_OUTBOX_PENDING_READBACK_PASS',
            'asof_et': p['asof_et'],
            'technical_al': p['expected_al'],
            'new_pending': p['pending_new'],
            'new_suppressed': p['suppressed_new'],
            'device_ack': False, 'messages_sent': 0}


class AlertApi(writer.SheetApi):
    def append_pending(self, rows):
        require(self.sheet_ids and type(self.sheet_ids.get('alerts')) is int,
                'ALERT_SHEET_METADATA_MISSING')
        if rows:
            self.request(':batchUpdate', method='POST', body={'requests':[
                writer.as_cells(rows, self.sheet_ids['alerts'])]})


def synchronize(snapshot, run_url, api):
    api.check_metadata()
    candidates = api.read('ADAY_GECMISI', 'M')
    scans = api.read('TARAMA_KAYITLARI', 'J')
    alerts = api.read('UYARI_OLAYLARI', 'T')
    p = plan(snapshot, candidates, scans, alerts, run_url)
    require(api.read('ADAY_GECMISI', 'M') == candidates
            and api.read('TARAMA_KAYITLARI', 'J') == scans
            and api.read('UYARI_OLAYLARI', 'T') == alerts,
            'OUTBOX_CONCURRENT_PRIVATE_EDIT_BLOCKED')
    api.append_pending(p['new_rows'])
    return verify_readback(p, api.read('UYARI_OLAYLARI', 'T'))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    args = parser.parse_args(argv)
    try:
        secret = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON', '')
        require(bool(secret), 'GOOGLE_SERVICE_ACCOUNT_NOT_CONFIGURED')
        run_id = os.environ.get('GITHUB_RUN_ID', '')
        require(run_id.isdigit(), 'GITHUB_RUN_ID_MISSING')
        snapshot = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
        api = AlertApi(secret)
        result = synchronize(snapshot, RUN_PREFIX + run_id, api)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # No private symbols, row content, token, provider URL, or traceback.
        print(json.dumps({'status': 'AL_OUTBOX_PENDING_BLOCKED',
                          'reason_type': type(exc).__name__,
                          'messages_sent': 0, 'device_ack': False},
                         sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
