#!/usr/bin/env python3
"""Private, fail-closed Google Sheets handoff for VERIFIED personal 477 EOD.

Runs INSIDE the ephemeral GitHub Actions runner while latest.json exists.
Only a Google service-account token with private spreadsheet access is used.
Never emits rows, private identifiers or credentials to public Actions logs.
No brokerage, trades, public artifacts, push messaging, or alarm send.
"""
import argparse
from collections.abc import Mapping
import json
import math
import os
import random
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import handoff_guard
import runner

CANDIDATE_HEADER = ('ALARM KİMLİĞİ','ASOF ET','SEMBOL','SINIF',
                    'IEX KAPANIŞ USD','STOP 2ATR','HEDEF 2R','TAKİP DURUMU',
                    'KAPANIŞ SEANSI','SONUÇ','TEORİK %','BİLDİRİM','KAYNAK / NOT')
SCAN_HEADER = ('ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ',
               'EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI')
BATCH_ENDPOINT = 'https://sheets.googleapis.com/v4/spreadsheets/'
VERIFIED_RUN_URL = re.compile(
    r'^https://github[.]com/gokaydonmez39-jpg/kripto-radar/actions/runs/[1-9][0-9]*$')
# Bound loaded private ledger entries, not the initial 1,000-row grid.
# The Sheets API appendCells extends the grid; a capped read silently misses
# older events and can cause duplicate AL/STOP or replay. Read all occupied
# rows and explicitly HOLD on excessive size instead of truncating.
MAX_ROWS = 20000
# Honest source labels: a verified 477 IEX result is not necessarily an
# automatically scheduled GitHub run. Never infer the event from its status.
RUN_EVENT_LABELS = {
    'schedule': 'GitHub schedule VERIFIED IEX EOD',
    'workflow_dispatch': 'GitHub workflow_dispatch VERIFIED IEX EOD',
    'push': 'GitHub push VERIFIED IEX EOD',
}


class HandoffBlocked(ValueError):
    pass


# Only author-controlled symbolic error identifiers may enter PUBLIC GitHub
# logs; never emit private Sheet cells, Google response bodies, URLs, tokens,
# secrets, exception values or tracebacks.
_PUBLIC_BLOCK_CODES = frozenset({
    'GOOGLE_SHEETS_HTTP_400',
    'GOOGLE_SHEETS_HTTP_409',
    'GOOGLE_SHEETS_HTTP_429',
    'GOOGLE_SHEETS_HTTP_401',
    'GOOGLE_SHEETS_HTTP_403',
    'GOOGLE_SHEETS_HTTP_404',
    'GOOGLE_SHEETS_HTTP_5XX',
    'GOOGLE_SHEETS_HTTP_OTHER',
    'GOOGLE_SHEETS_TRANSPORT_URLError',
    'GOOGLE_SHEETS_TRANSPORT_TimeoutError',
    'GOOGLE_SHEETS_READ_RETRY_EXHAUSTED',
    'GOOGLE_SHEETS_METHOD_SCOPE_INVALID',
    'GOOGLE_SHEETS_POST_SCOPE_INVALID',
    'GOOGLE_AUTH_CONFIGURATION_INVALID',
    'GOOGLE_TOKEN_NOT_AVAILABLE',
    'GOOGLE_SERVICE_ACCOUNT_NOT_CONFIGURED',
    'PRIVATE_SHEET_ID_NOT_CONFIGURED',
    'INVALID_GOOGLE_AUTH_TYPE',
    'SHEET_TIMEZONE_DRIFT',
    'SHEET_TAB_OR_ID_DRIFT',
    'SHEET_PANEL_IDENTITY_MISMATCH',
    'SHEET_HEADER_DRIFT',
    'SHEET_MISSING',
    'SHEET_READ_CAPACITY_REACHED',
    'SHEET_CAPACITY_REACHED',
    'CANDIDATE_IDENTITY_CONFLICT',
    'CANDIDATE_ORIGINAL_LEVEL_CONFLICT',
    'CANDIDATE_EPOCH_SET_CONFLICT',
    'CANDIDATE_EPOCH_READBACK_SET_CONFLICT',
    'CANDIDATE_READBACK_DUPLICATE_KEY',
    'CANDIDATE_READBACK_LEVELS_OR_VALUES_CHANGED',
    'CANDIDATE_READBACK_MISSING_OR_DUPLICATE',
    'CONCURRENT_SHEET_EDIT_BLOCKED',
    'DUPLICATE_CANDIDATE_KEYS',
    'DUPLICATE_SCAN_ASOF',
    'SCAN_DATE_ORDER_OR_STALE_ASOF',
    'EXISTING_SCAN_EPOCH_CONFLICT',
    'EXISTING_SCAN_INCOMPLETE',
    'EXISTING_SCAN_SOURCE_PROOF_MISSING_OR_MALFORMED',
    'EXISTING_SCAN_SOURCE_SHA_CONFLICT',
    'EXISTING_SCAN_SOURCE_IDENTITY_CONFLICT',
    'SCAN_COUNT_READBACK_MISMATCH',
    'SCAN_EPOCH_COLLISION',
    'SCAN_READBACK_DUPLICATE_ASOF',
    'SCAN_READBACK_MISSING_OR_DUPLICATE',
    'SCAN_READBACK_PROVENANCE_OR_VALUES_CHANGED',
    'GITHUB_RUN_ID_MISSING',
    'UNTRUSTED_GITHUB_EVENT',
    'NON_NATURAL_CANONICAL_EOD_WRITE_UNAUTHORIZED',
    'NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED',
    'NATURAL_EOD_SNAPSHOT_NONCURRENT_ASOF',
    'EPOCH_CAS_ASOF_INVALID',
    'EPOCH_CAS_POST_RECEIPT_UNVERIFIED',
    'EPOCH_CAS_INDEPENDENT_GET_UNVERIFIED',
    'EPOCH_LEASE_MODE_UNRECOGNIZED',
    'EPOCH_LEASE_TOKEN_MISSING',
    'EPOCH_LEASE_CONSUMER_UNVERIFIED',
    'SOURCE_LASTMILE_MODE_UNRECOGNIZED',
    'SOURCE_LASTMILE_TOKEN_MISSING',
    'SOURCE_LASTMILE_PROVENANCE_UNVERIFIED',
    'UNVERIFIED_RUN_ID',
    'MISSING_AUTHENTICATED_SHEET_METADATA',
    'INVALID_EXISTING_LEVEL',
    'BAD_NUMERIC_LEVEL',
})


EXPECTED_EOD_WORKFLOW_REF = (
    'gokaydonmez39-jpg/kripto-radar/'
    '.github/workflows/xray-personal-477-eod.yml@refs/heads/main')
EXPECTED_EOD_REPOSITORY = 'gokaydonmez39-jpg/kripto-radar'
RUN_ID_RE = re.compile(r'[1-9][0-9]*')
GIT_COMMIT_RE = re.compile(r'[0-9a-f]{40}')


def verify_natural_eod_writer_identity(environment):
    """Reject cross-workflow, rerun, non-main and forged event metadata.

    This is the REAL canonical Sheet writer's entry-point admission,
    separate from the inactive atomic Git lease library. A successful
    source check does NOT imply Sheet delivery or ChatGPT card delivery.
    No I/O or credentials are needed to make this decision.
    """
    require(
        isinstance(environment,Mapping) and
        environment.get('GITHUB_EVENT_NAME') == 'schedule' and
        environment.get('GITHUB_REPOSITORY') == EXPECTED_EOD_REPOSITORY and
        environment.get('GITHUB_REF') == 'refs/heads/main' and
        environment.get('GITHUB_WORKFLOW_REF') == EXPECTED_EOD_WORKFLOW_REF and
        environment.get('GITHUB_RUN_ATTEMPT') == '1' and
        isinstance(environment.get('GITHUB_SHA'),str) and
        GIT_COMMIT_RE.fullmatch(environment['GITHUB_SHA']) is not None and
        isinstance(environment.get('GITHUB_RUN_ID'),str) and
        RUN_ID_RE.fullmatch(environment['GITHUB_RUN_ID']) is not None,
        'NATURAL_EOD_WRITER_IDENTITY_UNVERIFIED')
    return True


def require_current_natural_eod_snapshot(snapshot):
    """Final independent freshness fence BEFORE any private Google client.

    An authenticated scheduled runner may still receive a substituted/stale
    latest.json artifact. Exact current official XNAS close+45m..+10h
    admission is re-evaluated here, not inherited from a prior scanner job.
    If calendar/clock validation is unavailable, no private writes occur.
    Historical recovery/backfill is never authorized.
    """
    code='NATURAL_EOD_SNAPSHOT_NONCURRENT_ASOF'
    require(type(snapshot) is dict and
            canonical_scan_day(snapshot.get('asof_et')),code)
    try:
        import daily_job
        current=daily_job.current_completed_session()
    except Exception:
        raise HandoffBlocked(code) from None
    require(type(current) is str and canonical_scan_day(current)
            and current==snapshot['asof_et'],code)
    return True


def public_failure_code(exc):
    """Return ONLY an audited constant; never log arbitrary error text."""
    if isinstance(exc, HandoffBlocked) and str(exc) in _PUBLIC_BLOCK_CODES:
        return str(exc)
    return 'UNCLASSIFIED'


def require(condition, code):
    if not condition:
        raise HandoffBlocked(code)


def money(x):
    require(type(x) in (float,int) and math.isfinite(x) and x > 0,
            'BAD_NUMERIC_LEVEL')
    return ('{:.3f}'.format(x).rstrip('0').rstrip('.')).replace('.', ',')


def numeric(x):
    try:
        return float(str(x).replace(' ', '').replace(',', '.'))
    except (ValueError, TypeError):
        raise HandoffBlocked('INVALID_EXISTING_LEVEL') from None


def rows_only(table, header):
    require(isinstance(table, list) and bool(table), 'SHEET_MISSING')
    require(tuple(table[0]) == header, 'SHEET_HEADER_DRIFT')
    return [list(row) for row in table[1:] if row and any(v != '' for v in row)]


def scan_source_proof(note):
    """Require exactly one canonical fingerprint for each replay authority."""
    require(isinstance(note, str),
            'EXISTING_SCAN_SOURCE_PROOF_MISSING_OR_MALFORMED')
    parts = [part.strip() for part in note.split(';')]
    proof = {}
    for label in ('scopeSHA', 'algorithmSHA'):
        hits = [part[len(label)+1:] for part in parts
                if part.startswith(label + '=')]
        require(len(hits) == 1 and len(hits[0]) == 64
                and all(ch in '0123456789abcdef' for ch in hits[0]),
                'EXISTING_SCAN_SOURCE_PROOF_MISSING_OR_MALFORMED')
        proof[label] = hits[0]
    return proof


def canonical_natural_scan_source(row):
    """Exact receipt-origin predicate for downstream research-only consumers.

    A valid SHA cannot elevate a manual/duplicate/mislabeled run to the
    canonical scheduled producer. This is pure; never grants write authority.
    """
    if not isinstance(row, (list, tuple)) or len(row) < 10:
        return False
    if row[1] != RUN_EVENT_LABELS['schedule'] or not isinstance(row[9], str):
        return False
    fields = [part.strip() for part in row[9].split(';')
              if part.strip().startswith('source_event=')]
    return fields == ['source_event=schedule']


def canonical_scan_day(day):
    """Reject malformed private ASOF keys before lexicographic ordering."""
    if type(day) is not str or re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}',day) is None:
        return False
    try:
        return date.fromisoformat(day).isoformat() == day
    except ValueError:
        return False


def plan(snapshot, candidates, scans, run_url, run_event='schedule'):
    """Pure deterministic idempotent append plan; never changes prior cells.

    Google Sheets has no per-key CAS. Single GitHub workflow concurrency,
    two preflight reads and post-write readback reduce, but do NOT eliminate,
    races with another writer. No exactly-once delivery claim is made.
    """
    symbols = runner.get_scope(watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')),asof=snapshot.get('asof_et'))
    handoff_guard.validate_snapshot(
        snapshot, symbols, scope_sha=runner.sha_symbols(symbols),
        policy_sha=runner.analysis_fingerprint())
    require(isinstance(run_url, str) and
            VERIFIED_RUN_URL.fullmatch(run_url) is not None,
            'UNVERIFIED_RUN_ID')
    require(type(run_event) is str and run_event in RUN_EVENT_LABELS,
            'UNTRUSTED_GITHUB_EVENT')
    old_candidates = rows_only(candidates, CANDIDATE_HEADER)
    old_scans = rows_only(scans, SCAN_HEADER)
    candidate_keys = [row[0] for row in old_candidates]
    scan_keys = [row[0] for row in old_scans]
    require(len(candidate_keys) == len(set(candidate_keys)),
            'DUPLICATE_CANDIDATE_KEYS')
    require(len(scan_keys) == len(set(scan_keys)), 'DUPLICATE_SCAN_ASOF')
    # A successful historical receipt does NOT authorize a late manual
    # workflow_dispatch or same-run retry to append/claim an older ASOF.
    # The private ledger is monotonic; gaps remain explicit, never backfilled.
    require(all(canonical_scan_day(day) for day in scan_keys) and
            scan_keys == sorted(scan_keys) and
            (not scan_keys or snapshot['asof_et'] >= scan_keys[-1]),
            'SCAN_DATE_ORDER_OR_STALE_ASOF')
    require(len(old_candidates) < MAX_ROWS and len(old_scans) < MAX_ROWS,
            'SHEET_CAPACITY_REACHED')

    asof = snapshot['asof_et']
    all_al = [r for r in snapshot['rows'] if r['decision'] == 'AL']
    existing_candidates = {r[0]:r for r in old_candidates}
    appended_candidates = []
    for row in all_al:
        key = asof + '|' + row['symbol']
        old = existing_candidates.get(key)
        if old is not None:
            require(len(old) >= 7 and old[1] == asof and old[2] == row['symbol'],
                    'CANDIDATE_IDENTITY_CONFLICT')
            # Historical levels are IMMUTABLE; do not rewrite or rederive them.
            for index,field in ((4,'close'),(5,'indicative_stop'),
                                (6,'indicative_target_2r')):
                # Existing rows may display 2dp while the engine stores 3dp.
                # 1-cent drift is NOT ordinary rounding; treat it as a conflict.
                cell=str(old[index]).replace(',', '.')
                digits=len(cell.split('.',1)[1]) if '.' in cell else 0
                tolerance=min(0.00501,0.5*10**(-min(digits,3))+0.00001)
                require(abs(numeric(old[index]) - row[field]) <= tolerance,
                        'CANDIDATE_ORIGINAL_LEVEL_CONFLICT')
            continue
        appended_candidates.append([
            key, asof, row['symbol'], 'TEKNİK AL ADAYI',
            money(row['close']), money(row['indicative_stop']),
            money(row['indicative_target_2r']), 'AÇIK • 0/15 SEANS',
            '', '', '', 'KAYDEDİLDİ_BİLDİRİM_AYRI',
            'GitHub private handoff; source_event={}; IEX single exchange; RSI14={} RVOL={}; '.format(
                run_event, row['rsi14'], row['relative_iex_volume']) +
            'run=' + run_url + '; NO_BROKER_NO_ORDERS'])

    matching_scans = [r for r in old_scans if r[0] == asof]
    require(len(matching_scans) <= 1, 'SCAN_EPOCH_COLLISION')
    appended_scans = []
    if matching_scans:
        existing = matching_scans[0]
        require(len(existing) >= 8, 'EXISTING_SCAN_INCOMPLETE')
        actual = [numeric(existing[i]) for i in (2,3,4,5,7)]
        require(actual == [477.,477.,477.,0.,float(len(all_al))] and
                str(existing[6]).upper() == 'TRUE',
                'EXISTING_SCAN_EPOCH_CONFLICT')
        require(len(existing) >= 10,
                'EXISTING_SCAN_SOURCE_PROOF_MISSING_OR_MALFORMED')
        # A retry may read back ONLY the receipt of its OWN run and trigger.
        # The same ASOF, 477 coverage and algorithm SHA cannot authorize
        # a different workflow_dispatch/schedule run to borrow another
        # producer's immutable EOD receipt. This is read-only on conflicts.
        origin_fields = [
            part.strip() for part in str(existing[9]).split(';')
            if part.strip().startswith('source_event=')
        ]
        require(existing[1] == RUN_EVENT_LABELS[run_event] and
                existing[8] == run_url and
                origin_fields == ['source_event=' + run_event],
                'EXISTING_SCAN_SOURCE_IDENTITY_CONFLICT')
        proof = scan_source_proof(existing[9])
        require(proof['scopeSHA'] == snapshot['scope_sha256'] and
                proof['algorithmSHA'] == snapshot['analysis_fingerprint_sha256'],
                'EXISTING_SCAN_SOURCE_SHA_CONFLICT')
    else:
        appended_scans = [[
            asof, RUN_EVENT_LABELS[run_event], '477', '477', '477', '0',
            'TRUE', str(len(all_al)), run_url,
            'scopeSHA=' + snapshot['scope_sha256'] +
            ';algorithmSHA=' + snapshot['analysis_fingerprint_sha256'] +
            ';source_event=' + run_event +
            ';NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK']]
    # EOD scan and all its new-AL candidates are appended in ONE Google
    # batchUpdate. A complete existing epoch must have EXACTLY the candidate
    # set specified by its immutable research snapshot. A candidate without
    # a scan is an orphan, not permission to reconstruct/backfill the scan.
    epoch_candidates = [
        r for r in old_candidates
        if str(r[0]).startswith(asof + '|') or
           (len(r) > 1 and r[1] == asof)
    ]
    expected_epoch_keys = {asof + '|' + r['symbol'] for r in all_al}
    existing_epoch_keys = {r[0] for r in epoch_candidates}
    require((existing_epoch_keys == expected_epoch_keys and
             len(epoch_candidates) == len(expected_epoch_keys))
            if matching_scans else not epoch_candidates,
            'CANDIDATE_EPOCH_SET_CONFLICT')
    require(len(old_candidates) + len(appended_candidates) < MAX_ROWS and
            len(old_scans) + len(appended_scans) < MAX_ROWS,
            'SHEET_CAPACITY_REACHED')
    expected_keys=[asof+'|'+r['symbol'] for r in all_al]
    all_rows={r[0]:r for r in old_candidates+appended_candidates}
    expected_rows={key:list(all_rows[key]) for key in expected_keys}
    scan_row=matching_scans[0] if matching_scans else appended_scans[0]
    return {'candidate_rows':appended_candidates,'scan_rows':appended_scans,
            'asof_et':asof,'expected_keys':expected_keys,
            'expected_candidate_rows':expected_rows,
            'expected_scan_row':list(scan_row),
            'expected_count':len(all_al)}


def as_cells(rows, sheet_id):
    return {'appendCells': {'sheetId':sheet_id,'rows':[
        {'values':[{'userEnteredValue':{'stringValue':str(value)}}
                   for value in row]} for row in rows],
        'fields':'userEnteredValue'}}


def epoch_marker(asof, scan_sheet_id):
    """Deterministic per-ASOF Google-owned native named range for first writer.

    A competing writer must attempt the SAME namedRangeId and name, so
    at most one same-ASOF batch can insert the source scan plus AL rows.
    A mutable named range is not an immutable Git provenance attestation.
    """
    try:
        canonical=(type(asof) is str and
                   re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}',asof) is not None
                   and date.fromisoformat(asof).isoformat()==asof)
    except ValueError:
        canonical=False
    require(canonical and type(scan_sheet_id) is int
            and 0 <= scan_sheet_id <= 2147483647,
            'EPOCH_CAS_ASOF_INVALID')
    compact=asof.replace('-','')
    return {
        'namedRangeId':'xray_p477_eod_epoch_'+compact,
        'name':'XRAY_P477_EOD_EPOCH_'+compact,
        'range':{'sheetId':scan_sheet_id,'startRowIndex':0,
                 'endRowIndex':1,'startColumnIndex':0,'endColumnIndex':1},
    }

def _marker_matches(observed, expected):
    """Accept protocol-default omission of startIndex=0; reject other drift."""
    if not isinstance(observed,dict):
        return False
    if (observed.get('namedRangeId')!=expected['namedRangeId'] or
            observed.get('name')!=expected['name']):
        return False
    actual_range=observed.get('range')
    if not isinstance(actual_range,dict):
        return False
    exp=expected['range']
    return (actual_range.get('sheetId')==exp['sheetId'] and
            actual_range.get('startRowIndex',0)==0 and
            actual_range.get('endRowIndex')==1 and
            actual_range.get('startColumnIndex',0)==0 and
            actual_range.get('endColumnIndex')==1)


def payload_from_plan(p, sheet_ids=None):
    # Resolve authenticated private sheet IDs from metadata. The epoch
    # reservation and the 477 final scan + new AL candidates are submitted
    # in ONE batchUpdate; no separate create-lease POST is authorized.
    ids=sheet_ids if sheet_ids is not None else {'scan':1,'candidate':2}
    req=[]
    if p['scan_rows']:
        req.append({'addNamedRange':{'namedRange':epoch_marker(
            p['asof_et'],ids['scan'])}})
        req.append(as_cells(p['scan_rows'], ids['scan']))
    if p['candidate_rows']:
        req.append(as_cells(p['candidate_rows'], ids['candidate']))
    return {'requests':req}


def verify_readback(p, candidates, scans):
    """Readback must prove VALUES and provenance, not only the existence of keys."""
    cr=rows_only(candidates,CANDIDATE_HEADER)
    sr=rows_only(scans,SCAN_HEADER)
    all_candidate_keys=[r[0] for r in cr]
    all_scan_keys=[r[0] for r in sr]
    require(len(set(all_candidate_keys))==len(all_candidate_keys),
            'CANDIDATE_READBACK_DUPLICATE_KEY')
    require(len(set(all_scan_keys))==len(all_scan_keys),
            'SCAN_READBACK_DUPLICATE_ASOF')
    require(sum(r[0] == p['asof_et'] for r in sr) == 1,
            'SCAN_READBACK_MISSING_OR_DUPLICATE')
    matching_scan=next(r for r in sr if r[0]==p['asof_et'])
    require(matching_scan == p['expected_scan_row'],
            'SCAN_READBACK_PROVENANCE_OR_VALUES_CHANGED')
    require(len(matching_scan) >= 8 and
            numeric(matching_scan[7]) == p['expected_count'],
            'SCAN_COUNT_READBACK_MISMATCH')
    observed={r[0]:r for r in cr}
    for key in p['expected_keys']:
        require(key in observed,'CANDIDATE_READBACK_MISSING_OR_DUPLICATE')
        require(observed[key] == p['expected_candidate_rows'][key],
                'CANDIDATE_READBACK_LEVELS_OR_VALUES_CHANGED')
    # The second live GET must reject additional same-ASOF candidates,
    # including rows injected after the original atomic batch but before
    # independent readback. A subset check is not an exact-set receipt.
    epoch_rows = [
        r for r in cr
        if str(r[0]).startswith(p['asof_et'] + '|') or
           (len(r) > 1 and r[1] == p['asof_et'])
    ]
    require(len(epoch_rows) == len(p['expected_keys']) and
            {r[0] for r in epoch_rows} == set(p['expected_keys']),
            'CANDIDATE_EPOCH_READBACK_SET_CONFLICT')
    return {'status':'PRIVATE_SHEET_READBACK_PASS','asof_et':p['asof_et'],
            'candidates':p['expected_count'],'device_ack':False}



def require_source_lastmile_before_private_post(
        environment, *, transport=None, now=None, completed_session=None):
    """Recheck actual unique scheduled EOD at every private Sheet POST.

    This is a READ-ONLY supplementary fence while immutable tag ownership
    remains OFF. A successful GET does NOT provide atomic CAS authority,
    does NOT prove a Google commit, and must never be used to unlock an
    untrusted recovery or device notification.

    The production EOD workflow explicitly sets ENFORCE_GET in each of
    its four private writer jobs. OFF preserves isolated/offline tests.
    """
    require(isinstance(environment,Mapping),
            'SOURCE_LASTMILE_MODE_UNRECOGNIZED')
    mode=environment.get('XRAY_PERSONAL477_SOURCE_LASTMILE_MODE','OFF')
    require(mode in ('OFF','ENFORCE_GET'),
            'SOURCE_LASTMILE_MODE_UNRECOGNIZED')
    if mode=='OFF':
        return {'status':'LASTMILE_MODE_OFF_NOT_AUTHORITY',
                'writes':0,'ab_release_authorized':False}
    # Wrong event/branch/attempt must stop before contacting GitHub or Google.
    verify_natural_eod_writer_identity(environment)
    token=environment.get('GITHUB_TOKEN','')
    require(isinstance(token,str) and bool(token),
            'SOURCE_LASTMILE_TOKEN_MISSING')
    try:
        import natural_run_readonly_probe as source
        import epoch_lease as lease
        result=source.verify_bounded(
            dict(environment),
            transport if transport is not None else lease.github_transport(token),
            now_factory=(lambda: now) if now is not None else None,
            completed_session=completed_session)
        require(isinstance(result,dict) and
                result.get('status')==source.STATUS and
                result.get('source_event')=='schedule' and
                result.get('run_id')==int(environment['GITHUB_RUN_ID']) and
                result.get('writes')==0 and
                result.get('orders') is False and
                result.get('ab_release_authorized') is False,
                'SOURCE_LASTMILE_PROVENANCE_UNVERIFIED')
        return result
    except Exception:
        # Prevent all provider exception text, private rows, run URL and
        # bearer tokens from appearing in the public Actions logs.
        raise HandoffBlocked('SOURCE_LASTMILE_PROVENANCE_UNVERIFIED') from None


def require_epoch_lease_before_private_post(
        environment, *, transport=None, now=None, completed_session=None):
    """Staged, opt-in owner fence for ALL NASDAQ private Sheets POSTs.

    No Sheet mutation can begin in ENFORCE mode without the current,
    separately read-back, immutable natural EOD tag owner. OFF is the
    existing production setting until the Actions ruleset credential can
    prove the full no-bypass rule and a live two-writer canary succeeds.

    A verified lease is ONLY the precondition for POST, never delivery,
    AL/STOP authority, an execution permission, or evidence that a Google
    batch committed. Test injection cannot enable a production lease.
    """
    require(isinstance(environment,Mapping),
            'EPOCH_LEASE_MODE_UNRECOGNIZED')
    mode=environment.get('XRAY_PERSONAL477_EPOCH_LEASE_MODE','OFF')
    require(mode in ('OFF','ENFORCE'), 'EPOCH_LEASE_MODE_UNRECOGNIZED')
    if mode == 'OFF':
        return {'state':'LEASE_ENFORCEMENT_NOT_ACTIVATED',
                'sheet_writes':0,'ab_release_authorized':False}
    # Check GH runner provenance before token, tag or Google network use.
    verify_natural_eod_writer_identity(environment)
    token=environment.get('GITHUB_TOKEN','')
    require(isinstance(token,str) and bool(token),
            'EPOCH_LEASE_TOKEN_MISSING')
    try:
        import epoch_lease
        import daily_job
        observed=now if now is not None else datetime.now(timezone.utc)
        asof=(completed_session(observed)
              if completed_session is not None else
              daily_job.current_completed_session(observed))
        require(isinstance(asof,str) and bool(asof),
                'EPOCH_LEASE_CONSUMER_UNVERIFIED')
        verified=epoch_lease.verify_existing_tag_consumer(
            asof,
            transport if transport is not None
            else epoch_lease.github_transport(token),
            now=observed,
            runtime_env=dict(environment) if now is not None else None,
            completed_session=completed_session)
        require(verified.get('state')=='LEASE_OWNER_READBACK_ONLY' and
                verified.get('asof_et')==asof and
                verified.get('run_id')==int(environment['GITHUB_RUN_ID']) and
                verified.get('source_sha')==environment['GITHUB_SHA'] and
                verified.get('sheet_writes')==0 and
                verified.get('orders') is False and
                verified.get('ab_release_authorized') is False,
                'EPOCH_LEASE_CONSUMER_UNVERIFIED')
        return verified
    except Exception:
        # No bearer token, private row, provider reason, or REST body in
        # GitHub Actions logs; no retries or optimistic completion.
        raise HandoffBlocked('EPOCH_LEASE_CONSUMER_UNVERIFIED') from None



def _valid_private_string_rows(rows):
    """Only bounded, literal string-valued research cells; no formulas or clears."""
    return (type(rows) is list and 1 <= len(rows) <= MAX_ROWS and
            all(type(row) is dict and set(row) == {'values'} and
                type(row['values']) is list and
                1 <= len(row['values']) <= 35 and
                all(type(cell) is dict and set(cell) == {'userEnteredValue'} and
                    type(cell['userEnteredValue']) is dict and
                    set(cell['userEnteredValue']) == {'stringValue'} and
                    type(cell['userEnteredValue']['stringValue']) is str
                    for cell in row['values']) for row in rows))


def _valid_private_batch_post(body):
    """Allowlist the ACTUAL shape and sheet columns used by NASDAQ producers.

    These pure limits are separate from the natural owner, source SHA, lease
    and authenticated Sheet metadata; they grant NO new writing authority.
    A known Google request name with 'fields=*', formulaValue, wrong source
    column or a forged named range must never reach the network.
    """
    if (type(body) is not dict or set(body) != {'requests'} or
            type(body['requests']) is not list or
            not 1 <= len(body['requests']) <= MAX_ROWS):
        return False
    source_named_range_seen = False

    def sheet_id(value):
        return type(value) is int and 0 <= value <= 2147483647

    for index, request in enumerate(body['requests']):
        if type(request) is not dict or len(request) != 1:
            return False
        verb, payload = next(iter(request.items()))
        if type(payload) is not dict:
            return False
        if verb == 'appendCells':
            if (set(payload) != {'sheetId','rows','fields'} or
                    not sheet_id(payload.get('sheetId')) or
                    payload.get('fields') != 'userEnteredValue' or
                    not _valid_private_string_rows(payload.get('rows'))):
                return False
        elif verb == 'updateCells':
            if (set(payload) != {'start','rows','fields'} and
                    set(payload) != {'range','rows','fields'}):
                return False
            if (payload.get('fields') != 'userEnteredValue' or
                    not _valid_private_string_rows(payload.get('rows')) or
                    len(payload['rows']) != 1):
                return False
            if 'start' in payload:
                start = payload['start']
                if (type(start) is not dict or
                        set(start) != {'sheetId','rowIndex','columnIndex'} or
                        not sheet_id(start.get('sheetId')) or
                        type(start.get('rowIndex')) is not int or
                        not 1 <= start['rowIndex'] < MAX_ROWS or
                        start.get('columnIndex') != 7 or
                        len(payload['rows'][0]['values']) != 4):
                    return False
            else:
                area = payload['range']
                if (type(area) is not dict or set(area) !=
                        {'sheetId','startRowIndex','endRowIndex',
                         'startColumnIndex','endColumnIndex'} or
                        not sheet_id(area.get('sheetId')) or
                        type(area.get('startRowIndex')) is not int or
                        not 1 <= area['startRowIndex'] < MAX_ROWS or
                        area.get('endRowIndex') != area['startRowIndex'] + 1 or
                        area.get('startColumnIndex') != 1 or
                        area.get('endColumnIndex') != 3 or
                        len(payload['rows'][0]['values']) != 2):
                    return False
        elif verb == 'addNamedRange':
            if (source_named_range_seen or index != 0 or
                    len(body['requests']) < 2 or
                    set(payload) != {'namedRange'}):
                return False
            tag = payload['namedRange']
            if (type(tag) is not dict or
                    set(tag) != {'namedRangeId','name','range'} or
                    type(tag.get('name')) is not str or
                    type(tag.get('range')) is not dict):
                return False
            match = re.fullmatch(r'XRAY_P477_EOD_EPOCH_(20[0-9]{6})',
                                 tag['name'])
            if match is None:
                return False
            compact = match.group(1)
            asof = compact[:4]+'-'+compact[4:6]+'-'+compact[6:]
            sid = tag['range'].get('sheetId')
            if not sheet_id(sid):
                return False
            try:
                if tag != epoch_marker(asof, sid):
                    return False
            except HandoffBlocked:
                return False
            following = body['requests'][1]
            if (type(following) is not dict or
                    set(following) != {'appendCells'} or
                    type(following['appendCells']) is not dict or
                    following['appendCells'].get('sheetId') != sid or
                    not _valid_private_string_rows(
                        following['appendCells'].get('rows')) or
                    len(following['appendCells']['rows'][0]['values']) < 1 or
                    following['appendCells']['rows'][0]['values'][0]
                    ['userEnteredValue']['stringValue'] != asof):
                return False
            source_named_range_seen = True
        else:
            return False
    return True




def _valid_canonical_new_al(v, asof, run_url):
    """Check initial AL provenance and rounded 2R before any Google POST.

    This is an independent *necessary* transport fence; upstream snapshot
    validation, PIT 477 membership, XNAS timing and true protected tag owner
    remain separate requirements. No market/provider calls are made here.
    """
    if (type(v) is not list or len(v) != len(CANDIDATE_HEADER) or
            not v[2] or v[0] != asof+'|'+v[2] or v[1] != asof or
            v[3] != 'TEKNİK AL ADAYI' or
            v[7] != 'AÇIK • 0/15 SEANS' or
            v[8:11] != ['', '', ''] or
            v[11] != 'KAYDEDİLDİ_BİLDİRİM_AYRI'):
        return False
    number = r'[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?'
    note_pattern = (
        r'GitHub private handoff; source_event=schedule; '
        r'IEX single exchange; RSI14=('+number+r') RVOL=('+number+
        r'); run='+re.escape(run_url)+r'; NO_BROKER_NO_ORDERS'
    )
    match = re.fullmatch(note_pattern, v[12])
    if match is None:
        return False
    rsi, rvol = (float(raw) for raw in match.groups())
    if (not math.isfinite(rsi) or not math.isfinite(rvol) or
            not 0 <= rsi <= 100 or rvol < 0):
        return False

    # Exactly the locale and maximum three decimals produced by money().
    # Stop and 2R are RESEARCH-ONLY: never a promise of a fill price.
    price_cell = r'(?:0|[1-9][0-9]*)(?:,[0-9]{1,3})?'
    if any(re.fullmatch(price_cell, value) is None for value in v[4:7]):
        return False
    close, stop, target = (float(x.replace(',', '.')) for x in v[4:7])
    if (not all(math.isfinite(x) for x in (close, stop, target)) or
            not 0 < stop < close < target):
        return False
    # Rounding each of the three values to .001 can cause <=.002 error
    # in (target-close) - 2*(close-stop): 1+1+2 half-ticks.
    if abs((target-close) - 2*(close-stop)) > 0.00201:
        return False
    return True


def _valid_private_batch_targets(body, scope):
    """Bind approved cell shapes to authenticated, unique worksheet IDs.

    A correct-looking source append without its exact same-ASOF namedRange
    claim is NOT an authorized EOD. No single append may mutate source or
    candidate tabs. Outbox, score and NEON remain independently append-only.
    The real owner/lease and source checks remain separate prerequisites.
    """
    if type(scope) is not dict or not {'scan','candidate','alerts','panel'}.issubset(scope):
        return False
    ids=list(scope.values())
    if (any(type(v) is not int or not 0<=v<=2147483647 for v in ids) or
            len(set(ids)) != len(ids)):
        return False
    if type(body) is not dict or type(body.get('requests')) is not list:
        return False
    requests=body['requests']
    if not requests:
        return False
    first=requests[0]
    eod=type(first) is dict and set(first)=={'addNamedRange'}
    if eod:
        if len(requests) not in (2,3):
            return False
        marker=first['addNamedRange']['namedRange']
        if marker['range']['sheetId'] != scope['scan']:
            return False
        compact=marker['name'][-8:]
        asof=compact[:4]+'-'+compact[4:6]+'-'+compact[6:8]
        source=requests[1]['appendCells']
        if (source['sheetId'] != scope['scan'] or
                len(source['rows']) != 1 or
                len(source['rows'][0]['values']) != len(SCAN_HEADER)):
            return False
        source_fields=[
            cell['userEnteredValue']['stringValue']
            for cell in source['rows'][0]['values']
        ]
        # The EOD source is the canonical proof of 477 coverage and zero
        # missing symbols. A syntactically valid Sheets append must never
        # fabricate FINAL or silently diverge from the exact AL batch.
        # These are transport-level shape invariants; actual 52-bar data,
        # scope SHA and source owner still require the independent plan,
        # GitHub source admission and Google readback.
        candidate_rows=(requests[2]['appendCells']['rows']
                        if len(requests)==3 and
                           type(requests[2]) is dict and
                           set(requests[2])=={'appendCells'} else [])
        candidate_count=len(candidate_rows)
        proof=source_fields[9]
        if (source_fields[:7] != [
                asof,RUN_EVENT_LABELS['schedule'],
                '477','477','477','0','TRUE'] or
                source_fields[7] != str(candidate_count) or
                candidate_count > 477 or
                VERIFIED_RUN_URL.fullmatch(source_fields[8]) is None or
                re.fullmatch(
                    r'scopeSHA=[0-9a-f]{64};algorithmSHA=[0-9a-f]{64};'
                    r'source_event=schedule;NO_ORDERS;'
                    r' SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK',
                    proof) is None):
            return False
        if len(requests)==3:
            candidate=requests[2]
            if type(candidate) is not dict or set(candidate) != {'appendCells'}:
                return False
            p=candidate['appendCells']
            if (p['sheetId'] != scope['candidate'] or
                    not _valid_private_string_rows(p['rows']) or
                    any(len(r['values']) != len(CANDIDATE_HEADER)
                        for r in p['rows'])):
                return False
            observed_keys=[]
            for row in p['rows']:
                v=[c['userEnteredValue']['stringValue'] for c in row['values']]
                if not _valid_canonical_new_al(v, asof, source_fields[8]):
                    return False
                observed_keys.append(v[0])
            if len(set(observed_keys))!=candidate_count:
                return False
        return True

    allowed_append={}
    for name,width in (('alerts',20),('score',35),('neon',23)):
        if name in scope:
            allowed_append[scope[name]]=width
    for request in requests:
        verb,payload=next(iter(request.items()))
        if verb=='addNamedRange':
            return False
        if verb=='appendCells':
            sid=payload['sheetId']
            width=allowed_append.get(sid)
            if width is None or any(len(r['values']) != width for r in payload['rows']):
                return False
        elif verb=='updateCells':
            if 'start' in payload:
                if payload['start']['sheetId'] != scope['candidate']:
                    return False
            else:
                if payload['range']['sheetId'] != scope['panel']:
                    return False
        else:
            return False
    return True


class SheetApi:
    """Restrict HTTP calls to official Google Sheets API (credential is scoped)."""

    def __init__(self, service_account_json):
        try:
            from google.oauth2.service_account import Credentials
            from google.auth.transport.requests import Request as AuthRequest
            info=json.loads(service_account_json)
            require(info.get('type') == 'service_account',
                    'INVALID_GOOGLE_AUTH_TYPE')
            credentials=Credentials.from_service_account_info(
                info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
            credentials.refresh(AuthRequest())
            self.token=credentials.token
        except Exception:
            # Provider exceptions can contain OAuth diagnostics. Never expose
            # exception values or tracebacks in public Actions job output.
            raise HandoffBlocked('GOOGLE_AUTH_CONFIGURATION_INVALID') from None
        require(bool(self.token), 'GOOGLE_TOKEN_NOT_AVAILABLE')
        spreadsheet_id=os.environ.get('XRAY_PRIVATE_SPREADSHEET_ID','')
        require(isinstance(spreadsheet_id,str) and
                len(spreadsheet_id)>=20 and spreadsheet_id.replace('-','').replace('_','').isalnum(),
                'PRIVATE_SHEET_ID_NOT_CONFIGURED')
        self.base=BATCH_ENDPOINT+spreadsheet_id
        self.sheet_ids=None
        self._post_scope=None
        # Only genuine service-account construction authorizes a live client.
        # __new__-created fixtures have no such marker and remain offline.
        self._authenticated_production_client=True

    def request(self, path, *, method='GET', body=None):
        # One shared HTTP boundary for all private NASDAQ writers.
        # No caller, even with a valid service account, can invoke generic
        # Google mutation verbs or DELETE/PATCH/PUT through this transport.
        # This is a safety allowlist, NOT an authorization to write.
        require(type(method) is str and method in ('GET', 'POST'),
                'GOOGLE_SHEETS_METHOD_SCOPE_INVALID')
        if method == 'POST':
            # All reviewed NASDAQ producers use the SAME spreadsheet
            # batchUpdate path. Reject arbitrary endpoints and dangerous
            # request types before *any* GitHub/Google I/O.
            require(type(path) is str and path == ':batchUpdate' and
                    _valid_private_batch_post(body) and
                    _valid_private_batch_targets(
                        body,getattr(self,'_post_scope',None)),
                    'GOOGLE_SHEETS_POST_SCOPE_INVALID')
            # In live source-lastmile ENFORCE mode the immutable FINAL row
            # must cite THIS scheduled GitHub run, not merely a correctly
            # formatted URL borrowed from another historical or competing
            # EOD. Deny before any GitHub source/lease GET or Google POST.
            if (os.environ.get('XRAY_PERSONAL477_SOURCE_LASTMILE_MODE')
                    == 'ENFORCE_GET' and
                    'addNamedRange' in body['requests'][0]):
                run_id=os.environ.get('GITHUB_RUN_ID')
                require(type(run_id) is str and
                        re.fullmatch(r'[1-9][0-9]*',run_id) is not None and
                        body['requests'][1]['appendCells']['rows'][0]
                            ['values'][8]['userEnteredValue']['stringValue']
                        == ('https://github.com/gokaydonmez39-jpg/'
                            'kripto-radar/actions/runs/'+run_id),
                        'GOOGLE_SHEETS_POST_SCOPE_INVALID')
                # Last-mile date admission is independent from snapshot/plan.
                # A valid CURRENT run URL may not be attached to an OLD EOD
                # marker by an alternate caller of the shared Sheets client.
                # XNAS calendar uncertainty denies before any GitHub/Google IO.
                try:
                    import daily_job
                    current=daily_job.current_completed_session()
                    marker=body['requests'][0]['addNamedRange']['namedRange']
                    date_ok=(type(current) is str and
                             canonical_scan_day(current) and
                             marker['name']=='XRAY_P477_EOD_EPOCH_'+
                               current.replace('-',''))
                except Exception:
                    date_ok=False
                require(date_ok,'GOOGLE_SHEETS_POST_SCOPE_INVALID')
                # Source scope/policy SHA must be recomputed from THIS exact
                # production checkout, not merely accepted as 64 hex chars.
                # An alternate direct SheetApi caller cannot pair a current
                # natural run URL with forged scope or algorithm provenance.
                # Any filesystem, PIT or fingerprint uncertainty is HOLD
                # before both GitHub admission GET and Google mutation POST.
                try:
                    symbols=runner.get_scope(
                        watchlist_file=str(Path(__file__).resolve().with_name(
                            'nasdaq_watchlist_477.json')),asof=current)
                    expected_scope=runner.sha_symbols(symbols)
                    expected_policy=runner.analysis_fingerprint()
                    source_note=body['requests'][1]['appendCells']['rows'][0][
                        'values'][9]['userEnteredValue']['stringValue']
                    fingerprints_ok=(
                        type(symbols) is list and len(symbols)==477 and
                        len(set(symbols))==477 and
                        type(expected_scope) is str and
                        re.fullmatch(r'[0-9a-f]{64}',expected_scope) is not None and
                        type(expected_policy) is str and
                        re.fullmatch(r'[0-9a-f]{64}',expected_policy) is not None and
                        source_note==(
                            'scopeSHA='+expected_scope+
                            ';algorithmSHA='+expected_policy+
                            ';source_event=schedule;NO_ORDERS; '
                            'SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK'))
                except Exception:
                    fingerprints_ok=False
                require(fingerprints_ok,'GOOGLE_SHEETS_POST_SCOPE_INVALID')
        else:
            require(body is None, 'GOOGLE_SHEETS_METHOD_SCOPE_INVALID')
        # One central last-mile barrier: canonical EOD scan, outbox,
        # lifecycle, PANEL, score and NEON all use this Sheets client.
        # In ENFORCE mode, a missing/competing protected tag owner denies
        # every private batch POST BEFORE Google network I/O.
        if method == 'POST':
            # A real authenticated client or GitHub Actions process must
            # NEVER downgrade the natural EOD source proof by omitting OFF.
            # Even valid append-only payloads are unsafe without the source
            # admission receipt. Do not contact GitHub or Google on failure.
            if (getattr(self,'_authenticated_production_client',False) is True
                    or os.environ.get('GITHUB_ACTIONS')=='true'):
                require(
                    os.environ.get('XRAY_PERSONAL477_SOURCE_LASTMILE_MODE')
                    == 'ENFORCE_GET',
                    'SOURCE_LASTMILE_MODE_UNRECOGNIZED')
            require_source_lastmile_before_private_post(os.environ)
            require_epoch_lease_before_private_post(os.environ)
        url=self.base+path
        raw=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
        req=Request(url, data=raw, method=method,
                    headers={'Authorization':'Bearer '+self.token,
                             'Content-Type':'application/json; charset=utf-8'})
        # GET is idempotent; bounded exponential backoff with jitter for
        # transient quota/provider faults. A failed POST may have committed,
        # so POST is NEVER retried automatically.
        read_attempts = 4 if method == 'GET' else 1
        for attempt in range(read_attempts):
            try:
                with urlopen(req, timeout=30) as response:
                    return json.load(response)
            except HTTPError as exc:
                retriable = exc.code in (429, 500, 502, 503, 504)
                if method == 'GET' and retriable and attempt + 1 < read_attempts:
                    time.sleep(2 ** attempt + random.uniform(0.0, 0.25))
                    continue
                # Status only: no provider reason/body/URL/header in public logs.
                if exc.code in (400, 401, 403, 404, 409, 429):
                    category = 'GOOGLE_SHEETS_HTTP_' + str(exc.code)
                elif 500 <= exc.code <= 599:
                    category = 'GOOGLE_SHEETS_HTTP_5XX'
                else:
                    category = 'GOOGLE_SHEETS_HTTP_OTHER'
                raise HandoffBlocked(category) from None
            except (URLError, TimeoutError) as exc:
                if method == 'GET' and attempt + 1 < read_attempts:
                    time.sleep(2 ** attempt + random.uniform(0.0, 0.25))
                    continue
                raise HandoffBlocked(
                    'GOOGLE_SHEETS_TRANSPORT_' + type(exc).__name__) from None
        raise HandoffBlocked('GOOGLE_SHEETS_READ_RETRY_EXHAUSTED')

    def check_metadata(self):
        data=self.request('?fields=properties(timeZone),sheets.properties(sheetId,title)')
        require(data.get('properties',{}).get('timeZone')=='Europe/Istanbul',
                'SHEET_TIMEZONE_DRIFT')
        sheets={x['properties']['title']:x['properties']['sheetId']
                for x in data.get('sheets',[]) if 'properties' in x}
        required={'PANEL','ADAY_GECMISI','TARAMA_KAYITLARI',
                  'KURALLAR','UYARI_OLAYLARI'}
        require(required.issubset(sheets) and
                all(type(sheets[k]) is int for k in required) and
                len({sheets[k] for k in required})==len(required),
                'SHEET_TAB_OR_ID_DRIFT')
        panel=self.read('PANEL','A')
        require(bool(panel) and bool(panel[0]) and
                panel[0][0]=='XRAY — KİŞİSEL NASDAQ START / FINAL',
                'SHEET_PANEL_IDENTITY_MISMATCH')
        self.sheet_ids={'candidate':sheets['ADAY_GECMISI'],
                        'scan':sheets['TARAMA_KAYITLARI'],
                        'alerts':sheets['UYARI_OLAYLARI']}
        # Metadata is read from the original authenticated workbook.
        # A duplicate optional tab or reused sheetId is ambiguous, not a
        # legitimate destination for a mutation.
        optional=('SWING_SKOR_GUNLUK','NEON_477_GUNLUK')
        names=[item.get('properties',{}).get('title')
               for item in data.get('sheets',[]) if isinstance(item,dict)]
        require(all(names.count(name) <= 1 for name in optional),
                'SHEET_TAB_OR_ID_DRIFT')
        scope={**self.sheet_ids,'panel':sheets['PANEL']}
        for name,role in (('SWING_SKOR_GUNLUK','score'),
                          ('NEON_477_GUNLUK','neon')):
            if name in sheets:
                scope[role]=sheets[name]
        require(all(type(v) is int for v in scope.values()) and
                len(set(scope.values()))==len(scope),
                'SHEET_TAB_OR_ID_DRIFT')
        self._post_scope=scope

    def read(self, title, last_column):
        # Open-ended A1 is deliberate: never silently truncate identities at
        # row 1,000 or at the software maximum; fail closed on oversize instead.
        address=quote("'{0}'!A1:{1}".format(title,last_column),safe='')
        values=self.request('/values/'+address+'?valueRenderOption=FORMATTED_VALUE').get('values',[])
        require(isinstance(values,list) and len(values)<=MAX_ROWS,
                'SHEET_READ_CAPACITY_REACHED')
        return values

    def apply(self,p):
        require(isinstance(self.sheet_ids,dict),'MISSING_AUTHENTICATED_SHEET_METADATA')
        data=payload_from_plan(p,self.sheet_ids)
        if not data['requests']:
            return
        # One POST only: a lost reply is uncertain commitment, NEVER retry.
        result=self.request(':batchUpdate',method='POST',body=data)
        if p['scan_rows']:
            expected=data['requests'][0]['addNamedRange']['namedRange']
            replies=result.get('replies') if isinstance(result,dict) else None
            require(type(replies) is list and
                    len(replies)==len(data['requests']) and
                    isinstance(replies[0],dict) and
                    isinstance(replies[0].get('addNamedRange'),dict) and
                    _marker_matches(
                        replies[0]['addNamedRange'].get('namedRange'),expected),
                    'EPOCH_CAS_POST_RECEIPT_UNVERIFIED')
            # Independent GET: don't equate a successful 200 POST with a
            # permanently visible owner. This remains supplementary to
            # exact Sheet scan + candidate readback in synchronize().
            current=self.request('?fields=namedRanges(namedRangeId,name,range)')
            named=current.get('namedRanges') if isinstance(current,dict) else None
            require(type(named) is list and
                    len([r for r in named if isinstance(r,dict) and
                         (r.get('namedRangeId')==expected['namedRangeId'] or
                          r.get('name')==expected['name'])])==1 and
                    any(_marker_matches(r,expected) for r in named),
                    'EPOCH_CAS_INDEPENDENT_GET_UNVERIFIED')


def synchronize(snapshot, run_url, api, run_event='schedule'):
    api.check_metadata()
    before_candidates=api.read('ADAY_GECMISI','M')
    before_scans=api.read('TARAMA_KAYITLARI','J')
    p=plan(snapshot,before_candidates,before_scans,run_url,run_event=run_event)
    # Second read minimizes accidental stale writes. This is not an atomic
    # compare-and-swap; distinct external writers must be serialized.
    require(api.read('ADAY_GECMISI','M')==before_candidates and
            api.read('TARAMA_KAYITLARI','J')==before_scans,
            'CONCURRENT_SHEET_EDIT_BLOCKED')
    api.apply(p)
    return verify_readback(p,api.read('ADAY_GECMISI','M'),
                           api.read('TARAMA_KAYITLARI','J'))


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',required=True)
    args=parser.parse_args(argv)
    try:
        credential=os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON')
        require(bool(credential),'GOOGLE_SERVICE_ACCOUNT_NOT_CONFIGURED')
        run_id=os.environ.get('GITHUB_RUN_ID','')
        require(run_id.isdigit(),'GITHUB_RUN_ID_MISSING')
        run_event=os.environ.get('GITHUB_EVENT_NAME','')
        require(run_event in RUN_EVENT_LABELS,'UNTRUSTED_GITHUB_EVENT')
        # A manual dispatch/push has no independently attested natural
        # scheduler parent/child and no Sheets compare-and-swap recovery
        # contract. Such a run must NEVER reserve a canonical EOD epoch
        # which would then veto the next scheduled EOD and A34 lifecycle.
        # The pure plan remains available for offline research tests only.
        require(run_event == 'schedule',
                'NON_NATURAL_CANONICAL_EOD_WRITE_UNAUTHORIZED')
        # The event label alone is untrusted. GitHub's actual natural EOD
        # repository, default branch, workflow, source SHA and attempt must
        # ALL agree before reading snapshot or opening any Google client.
        verify_natural_eod_writer_identity(os.environ)
        snapshot=json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
        require_current_natural_eod_snapshot(snapshot)
        api=SheetApi(credential)
        out=synchronize(snapshot,
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/'+run_id,
            api,run_event=run_event)
        # Public log contains aggregate count only, never symbol or signal rows.
        print(json.dumps(out,sort_keys=True))
        return 0
    except Exception as exc:
        # In particular: no HTTP body, credentials, private row or endpoint
        # may appear in a public workflow log, even for unexpected failures.
        print(json.dumps({'status':'PRIVATE_SHEET_SYNC_BLOCKED',
                          'reason_type':type(exc).__name__,
                          'reason_code':public_failure_code(exc),
                          'execution':'NONE','device_ack':False},sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
