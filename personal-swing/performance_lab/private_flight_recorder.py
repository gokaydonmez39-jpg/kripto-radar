"""XRAY A21 private flight recorder: READ-ONLY Sheet→outbox reliability proof.

No signal decisions, broker calls, Sheet changes, mobile notifications or device
ACK inference. Real operational status is based on exact private row readback.
Public GitHub logs expose aggregate counters only, never identities or prices.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from private_sheet_writer import CANDIDATE_HEADER, SCAN_HEADER
from private_lifecycle import ALERT_HEADER, EVENT_PENDING
from performance_lab.private_performance_adapter import PrivateSheetReadOnly

CANDIDATE_KEY = re.compile(r'^([0-9]{4}-[0-9]{2}-[0-9]{2})\\|([A-Z][A-Z0-9.]{0,15})$')
PENDING = frozenset((EVENT_PENDING, 'ALERT_REQUESTED_NOT_DEVICE_ACK'))
EVENT_CODES = frozenset((
    'AL_NEW_EPISODE', 'STOP_TOUCHED', 'TARGET_TOUCHED',
    'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS', 'TIME_EXIT_AT_CLOSE'
))
MAX_ROWS = 1000


class FlightRecorderBlocked(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise FlightRecorderBlocked(reason)


def rows(values, header):
    need(type(values) is list and 1 <= len(values) <= MAX_ROWS,
         'FLIGHT_TABLE_MISSING_OR_TOO_LARGE')
    need(tuple(values[0]) == header, 'FLIGHT_HEADER_DRIFT')
    return [list(row) for row in values[1:]
            if row and any(str(cell).strip() for cell in row)]


def value(row, idx):
    return str(row[idx]).strip() if len(row) > idx else ''


def price(text):
    need(bool(re.fullmatch(r'[0-9]+(?:[,.][0-9]+)?', text)),
         'FLIGHT_LEVEL_NOT_VALID')
    try:
        v = Decimal(text.replace(',', '.'))
    except InvalidOperation:
        raise FlightRecorderBlocked('FLIGHT_LEVEL_NOT_VALID') from None
    need(v.is_finite() and v > 0, 'FLIGHT_LEVEL_NOT_VALID')
    return v


def inspect(candidate_table, scan_table, event_table, panel_table):
    """No writes. Delivery ACK is NEVER accepted from a Sheet status."""
    candidates = rows(candidate_table, CANDIDATE_HEADER)
    scans = rows(scan_table, SCAN_HEADER)
    alerts = rows(event_table, ALERT_HEADER)
    need(scans, 'FLIGHT_NO_SCAN')
    days = [value(s,0) for s in scans]
    need(days == sorted(set(days)), 'FLIGHT_SCAN_DATE_ORDER_OR_DUPLICATE')
    last = scans[-1]
    # Scan log's 477/477/477/0 final is the only known production witness.
    need(all(value(last, i) == n for i,n in
             ((2,'477'),(3,'477'),(4,'477'),(5,'0'))) and
         value(last, 6).upper() == 'TRUE', 'FLIGHT_SCAN_NOT_FULL_FINAL')
    cutoff = days[-1]
    keys = set()
    episodes = {}
    open_n = closed_n = 0
    for row in candidates:
        key = value(row,0)
        match = CANDIDATE_KEY.fullmatch(key)
        need(match is not None and key not in keys, 'FLIGHT_BAD_OR_DUPLICATE_EPISODE')
        start, symbol = match.groups()
        need(start == value(row,1) and symbol == value(row,2) and
             start <= cutoff and start in days, 'FLIGHT_EPISODE_NOT_LINKED_TO_SCAN')
        need(len(row) >= 13, 'FLIGHT_EPISODE_INCOMPLETE')
        close, stop, target = (price(value(row,i)) for i in (4,5,6))
        need(stop < close < target, 'FLIGHT_EPISODE_LEVEL_GEOMETRY')
        status = value(row,7)
        if status.startswith('AÇIK • '):
            need(re.fullmatch(r'AÇIK • (?:[0-9]|1[0-5])/15 SEANS',status)
                 is not None, 'FLIGHT_BAD_OPEN_STATUS')
            open_n += 1
        elif status.startswith('KAPALI • '):
            need(value(row,8) != '' and value(row,9) != '',
                 'FLIGHT_CLOSED_MISSING_EVIDENCE')
            closed_n += 1
        else:
            raise FlightRecorderBlocked('FLIGHT_UNKNOWN_EPISODE_STATUS')
        keys.add(key)
        episodes[key] = (start,symbol,stop,target)
    event_keys = set()
    pending = 0
    unknown_delivery = 0
    for row in alerts:
        need(len(row) >= 18, 'FLIGHT_EVENT_INCOMPLETE')
        eventkey = value(row,0)
        need(eventkey and eventkey not in event_keys, 'FLIGHT_DUPLICATE_EVENT')
        owner = value(row,1)
        need(owner in episodes, 'FLIGHT_ORPHAN_EVENT')
        start,symbol,stop,target = episodes[owner]
        event_day, code = value(row,4), value(row,5)
        need(value(row,2)==start and value(row,3)==symbol and
             start <= event_day <= cutoff and code in EVENT_CODES,
             'FLIGHT_EVENT_WRONG_EPISODE_OR_DAY')
        need(eventkey == f'{owner}|{event_day}|{code}|1',
             'FLIGHT_EVENT_DEDUP_KEY_INVALID')
        need(price(value(row,8)) == stop and price(value(row,9)) == target,
             'FLIGHT_ORIGINAL_LEVELS_CHANGED')
        status = value(row,17)
        if status in PENDING:
            pending += 1
        else:
            # A new or unknown status is not evidence of an iPhone ACK.
            unknown_delivery += 1
        event_keys.add(eventkey)
    need(unknown_delivery == 0, 'FLIGHT_UNATTESTED_DELIVERY_STATE')
    panel_last = ''
    if isinstance(panel_table,list):
        for row in panel_table:
            if value(row,0) == 'Son doğrulanmış tarama seansı':
                panel_last = value(row,1)
                break
    panel_stale = bool(panel_last) and panel_last != cutoff
    return {
        'schema':'XRAY_PRIVATE_A21_FLIGHT_RECORDER_V1',
        'state':'PASS_PENDING_DEVICE_ACK' if pending else 'PASS_NO_PENDING_EVENTS',
        'latest_verified_scan_asof':cutoff,
        'candidate_count':len(candidates),
        'open_count':open_n,
        'closed_count':closed_n,
        'event_count':len(alerts),
        'pending_device_ack':pending,
        'device_receipts_verified':0,
        'panel_non_authoritative_stale':panel_stale,
        'panel_missing_asof':not bool(panel_last),
        'duplicate_or_orphan_events':False,
        'private_data_published':False,
        'research_only':True,
        'orders':False,
        'writes':False,
        'automatic_rule_change':False,
    }


def live_entrypoint():
    try:
        credential = os.getenv('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON','')
        spreadsheet_id = os.getenv('XRAY_PRIVATE_SPREADSHEET_ID','')
        need(bool(credential) and bool(spreadsheet_id),
             'FLIGHT_PRIVATE_CREDENTIALS_MISSING')
        api=PrivateSheetReadOnly(credential,spreadsheet_id)
        api.verify_metadata()
        first=[api.read('ADAY_GECMISI','M'),api.read('TARAMA_KAYITLARI','J'),
               api.read('UYARI_OLAYLARI','T'),api.read('PANEL','B')]
        status=inspect(*first)
        # Double-read prevents a torn candidate/outbox snapshot from
        # becoming a false health certificate during concurrent Sheet writes.
        second=[api.read('ADAY_GECMISI','M'),api.read('TARAMA_KAYITLARI','J'),
                api.read('UYARI_OLAYLARI','T'),api.read('PANEL','B')]
        need(first == second, 'FLIGHT_TORN_PRIVATE_READ')
        print(json.dumps(status,sort_keys=True))
        return 0
    except Exception:
        print('XRAY_A21_FLIGHT_RECORDER=BLOCKED_NO_DATA_PUBLISHED_NO_WRITES')
        return 3


if __name__=='__main__':
    raise SystemExit(live_entrypoint())
