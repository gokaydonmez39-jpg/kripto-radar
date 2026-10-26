#!/usr/bin/env python3
"""Pure, privacy-safe negative contract for the ChatGPT-owned private Sheet outbox.

DOES NOT SEND PUSH, OPEN BROKERS, WRITE SHEETS, OR CLAIM DEVICE ACK.
The runtime private Google Sheet is the ledger; GitHub must never ingest its rows.
"""
from datetime import date
import re

EVENT_HEADER=(
    'OLAY_ANAHTARI','ADAY_ANAHTARI','AL_ASOF_ET','SEMBOL','OLAY_ASOF_ET',
    'OLAY_KODU','ONCELIK','IEX_KAPANIS_USD','ORIJINAL_STOP_USD',
    'ORIJINAL_HEDEF_USD','SMA20','SMA50','DESTEK_20','DIRENC_20',
    'TEPE_52','TAKIP_SEANSI','BIRINCIL_KANIT_URL','BILDIRIM_DURUMU',
    'BILDIRIM_ZAMANI_TR','NOT'
)
REQUESTED='ALERT_REQUESTED_NOT_DEVICE_ACK'
UNKNOWN='DELIVERY_UNKNOWN_REVIEW_REQUIRED'
ACKED='DEVICE_ACK_USER_ATTESTED'
ALLOWED_STATES=frozenset((REQUESTED,UNKNOWN,ACKED))
TYPES=frozenset((
    'AL_NEW_EPISODE','STOP_TOUCHED','GAP_BELOW_STOP',
    'BOTH_TOUCHED_STOP_FIRST_AMBIGUOUS','TARGET_TOUCHED',
    'TIME_EXIT_AT_CLOSE','SMA20_CROSS_DOWN','SMA50_CROSS_DOWN',
    'SUPPORT_20_BREAKDOWN','DAILY_DROP_2ATR','NEAR_STOP',
    '52_SESSION_BREAKOUT','OFFICIAL_ISSUER_RISK'
))
TICKER=re.compile(r'^[A-Z0-9.]{1,16}$')


class LedgerRefused(ValueError):
    pass


def event_key(al_asof,symbol,event_asof,event_type,first_trigger_index=1):
    """The same logical event cannot get a new ID on retries."""
    try:
        opening=date.fromisoformat(al_asof)
        triggered=date.fromisoformat(event_asof)
    except (ValueError,TypeError) as exc:
        raise LedgerRefused('BAD_EVENT_DATE') from exc
    if triggered<opening or not TICKER.fullmatch(str(symbol)):
        raise LedgerRefused('BAD_EVENT_IDENTITY')
    if event_type not in TYPES or type(first_trigger_index) is not int or first_trigger_index<1:
        raise LedgerRefused('BAD_EVENT_KIND_OR_EPISODE')
    return f'{al_asof}|{symbol}|{event_asof}|{event_type}|{first_trigger_index}'


def parse_ledger(matrix):
    """Fail closed on missing header, duplicate keys and unknown delivery states."""
    if not isinstance(matrix,list) or not matrix or tuple(matrix[0])!=EVENT_HEADER:
        raise LedgerRefused('SHEET_HEADER_DRIFT')
    found={}
    for index,row in enumerate(matrix[1:],start=2):
        if not row or not any(v!='' for v in row):
            continue
        if len(row)>len(EVENT_HEADER):
            raise LedgerRefused('UNEXPECTED_EVENT_CELLS')
        identity=row[0] if row else ''
        status=row[17] if len(row)>17 else ''
        if not isinstance(identity,str) or not identity:
            raise LedgerRefused('EVENT_MISSING_KEY')
        if identity in found:
            raise LedgerRefused('DUPLICATE_EVENT_KEY')
        if status not in ALLOWED_STATES:
            raise LedgerRefused('UNKNOWN_DELIVERY_STATE')
        found[identity]={'row_index':index,'status':status,'row':tuple(row)}
    return found


def verify_first_reservation(before,after,requested_keys):
    """A single-writer pre/readback proof, NOT a cross-provider atomic transaction.

    Reject replay and unverified reservations. Does not attempt delivery.
    """
    keys=list(requested_keys)
    if not keys or len(keys)!=len(set(keys)):
        raise LedgerRefused('EMPTY_OR_DUPLICATE_REQUEST_BATCH')
    old=parse_ledger(before)
    new=parse_ledger(after)
    if any(k in old for k in keys):
        raise LedgerRefused('EVENT_ALREADY_RECORDED_NO_RESEND')
    if any(k not in new or new[k]['status']!=REQUESTED for k in keys):
        raise LedgerRefused('REQUEST_RESERVATION_READBACK_MISSING')
    if any(k not in new or new[k]!=v for k,v in old.items()):
        raise LedgerRefused('EXISTING_EVENT_CHANGED_DURING_RESERVATION')
    if set(new)!=set(old)|set(keys):
        raise LedgerRefused('UNEXPECTED_CONCURRENT_EVENT')
    return {'request_allowed_after_readback':True,
            'device_delivery_attested':False,'new_event_count':len(keys)}


def delivery_status(ledger_matrix,event_id):
    """Never infer an iOS device acknowledgment from a sent/requested row."""
    entry=parse_ledger(ledger_matrix).get(event_id)
    if entry is None:
        return 'NOT_RECORDED'
    if entry['status']==ACKED:
        return 'USER_ATTESTED_DEVICE_ACK'
    return 'DELIVERY_UNKNOWN_NO_RESEND'
