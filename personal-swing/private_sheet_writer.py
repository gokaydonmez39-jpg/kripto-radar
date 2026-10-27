#!/usr/bin/env python3
"""Private, fail-closed Google Sheets handoff for VERIFIED personal 477 EOD.

Runs INSIDE the ephemeral GitHub Actions runner while latest.json exists.
Only a Google service-account token with private spreadsheet access is used.
Never emits rows, private identifiers or credentials to public Actions logs.
No brokerage, trades, public artifacts, push messaging, or alarm send.
"""
import argparse
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import handoff_guard
import runner

SPREADSHEET_ID = '1TT5MtHOAEew09mQTanQ6uIpgWNS_fzf4KrlkcpI-jrI'
CANDIDATE_SHEET_ID = 432001001
SCAN_SHEET_ID = 432001002
CANDIDATE_HEADER = ('ALARM KİMLİĞİ','ASOF ET','SEMBOL','SINIF',
                    'IEX KAPANIŞ USD','STOP 2ATR','HEDEF 2R','TAKİP DURUMU',
                    'KAPANIŞ SEANSI','SONUÇ','TEORİK %','BİLDİRİM','KAYNAK / NOT')
SCAN_HEADER = ('ASOF ET','ÜRETİM KANALI','İSTENEN','İŞLENEN','GEÇERLİ',
               'EKSİK','FINAL READY','YENİ KAYIT','RUN KANITI','DURUM / VERİ SINIRI')
BATCH_ENDPOINT = 'https://sheets.googleapis.com/v4/spreadsheets/'
MAX_ROWS = 1000


class HandoffBlocked(ValueError):
    pass


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


def plan(snapshot, candidates, scans, run_url):
    """Pure deterministic idempotent append plan; never changes prior cells.

    Google Sheets has no per-key CAS. Single GitHub workflow concurrency,
    two preflight reads and post-write readback reduce, but do NOT eliminate,
    races with another writer. No exactly-once delivery claim is made.
    """
    symbols = runner.get_scope(watchlist_file=str(Path(__file__).with_name('nasdaq_watchlist_477.json')))
    handoff_guard.validate_snapshot(
        snapshot, symbols, scope_sha=runner.sha_symbols(symbols),
        policy_sha=runner.analysis_fingerprint())
    require(isinstance(run_url, str) and
            run_url.startswith('https://github.com/') and '/actions/runs/' in run_url,
            'UNVERIFIED_RUN_ID')
    old_candidates = rows_only(candidates, CANDIDATE_HEADER)
    old_scans = rows_only(scans, SCAN_HEADER)
    candidate_keys = [row[0] for row in old_candidates]
    scan_keys = [row[0] for row in old_scans]
    require(len(candidate_keys) == len(set(candidate_keys)),
            'DUPLICATE_CANDIDATE_KEYS')
    require(len(scan_keys) == len(set(scan_keys)), 'DUPLICATE_SCAN_ASOF')
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
                require(abs(numeric(old[index]) - row[field]) < 0.011,
                        'CANDIDATE_ORIGINAL_LEVEL_CONFLICT')
            continue
        appended_candidates.append([
            key, asof, row['symbol'], 'TEKNİK AL ADAYI',
            money(row['close']), money(row['indicative_stop']),
            money(row['indicative_target_2r']), 'AÇIK • 0/15 SEANS',
            '', '', '', 'KAYDEDİLDİ_BİLDİRİM_AYRI',
            'GitHub private auto handoff; IEX single exchange; RSI14={} RVOL={}; '.format(
                row['rsi14'], row['relative_iex_volume']) +
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
    else:
        appended_scans = [[
            asof, 'GitHub auto VERIFIED IEX EOD', '477', '477', '477', '0',
            'TRUE', str(len(all_al)), run_url,
            'scopeSHA=' + snapshot['scope_sha256'] +
            ';algorithmSHA=' + snapshot['analysis_fingerprint_sha256'] +
            ';NO_ORDERS; SHEETS_READBACK_REQUIRED; NOT_DEVICE_ACK']]
    require(len(old_candidates) + len(appended_candidates) < MAX_ROWS and
            len(old_scans) + len(appended_scans) < MAX_ROWS,
            'SHEET_CAPACITY_REACHED')
    return {'candidate_rows':appended_candidates,'scan_rows':appended_scans,
            'asof_et':asof,'expected_keys':[asof+'|'+r['symbol'] for r in all_al],
            'expected_count':len(all_al)}


def as_cells(rows, sheet_id):
    return {'appendCells': {'sheetId':sheet_id,'rows':[
        {'values':[{'userEnteredValue':{'stringValue':str(value)}}
                   for value in row]} for row in rows],
        'fields':'userEnteredValue'}}


def payload_from_plan(p):
    req=[]
    if p['scan_rows']:
        req.append(as_cells(p['scan_rows'], SCAN_SHEET_ID))
    if p['candidate_rows']:
        req.append(as_cells(p['candidate_rows'], CANDIDATE_SHEET_ID))
    return {'requests':req}


def verify_readback(p, candidates, scans):
    cr=rows_only(candidates,CANDIDATE_HEADER)
    sr=rows_only(scans,SCAN_HEADER)
    require(sum(r[0] == p['asof_et'] for r in sr) == 1, 'SCAN_READBACK_MISSING_OR_DUPLICATE')
    for key in p['expected_keys']:
        require(sum(row[0] == key for row in cr) == 1,
                'CANDIDATE_READBACK_MISSING_OR_DUPLICATE')
    matches=[r for r in sr if r[0] == p['asof_et']]
    require(len(matches[0]) >= 8 and numeric(matches[0][7]) == p['expected_count'],
            'SCAN_COUNT_READBACK_MISMATCH')
    return {'status':'PRIVATE_SHEET_READBACK_PASS','asof_et':p['asof_et'],
            'candidates':p['expected_count'],'device_ack':False}


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
        except (ValueError, KeyError, TypeError) as exc:
            raise HandoffBlocked('GOOGLE_AUTH_CONFIGURATION_INVALID') from None
        require(bool(self.token), 'GOOGLE_TOKEN_NOT_AVAILABLE')

    def request(self, path, *, method='GET', body=None):
        url=BATCH_ENDPOINT+SPREADSHEET_ID+path
        raw=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
        req=Request(url, data=raw, method=method,
                    headers={'Authorization':'Bearer '+self.token,
                             'Content-Type':'application/json; charset=utf-8'})
        try:
            with urlopen(req,timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            # Do not include response body, candidate rows, token or URL in logs.
            raise HandoffBlocked('GOOGLE_SHEETS_TRANSPORT_'+type(exc).__name__) from None

    def check_metadata(self):
        data=self.request('?fields=sheets.properties(sheetId,title)')
        sheets={x['properties']['title']:x['properties']['sheetId']
                for x in data.get('sheets',[]) if 'properties' in x}
        require(sheets.get('ADAY_GECMISI')==CANDIDATE_SHEET_ID and
                sheets.get('TARAMA_KAYITLARI')==SCAN_SHEET_ID,
                'SHEET_TAB_OR_ID_DRIFT')

    def read(self, title, last_column):
        address=quote("'{0}'!A1:{1}{2}".format(title,last_column,MAX_ROWS),safe='')
        return self.request('/values/'+address+'?valueRenderOption=FORMATTED_VALUE').get('values',[])

    def apply(self,p):
        data=payload_from_plan(p)
        if data['requests']:
            self.request(':batchUpdate',method='POST',body=data)


def synchronize(snapshot, run_url, api):
    api.check_metadata()
    before_candidates=api.read('ADAY_GECMISI','M')
    before_scans=api.read('TARAMA_KAYITLARI','J')
    p=plan(snapshot,before_candidates,before_scans,run_url)
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
        snapshot=json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
        api=SheetApi(credential)
        out=synchronize(snapshot,
            'https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/'+run_id,
            api)
        # Public log contains aggregate count only, never symbol or signal rows.
        print(json.dumps(out,sort_keys=True))
        return 0
    except (HandoffBlocked,handoff_guard.HandoffInvalid,ValueError,KeyError,
            RuntimeError,FileNotFoundError) as exc:
        print(json.dumps({'status':'PRIVATE_SHEET_SYNC_BLOCKED',
                          'reason_type':type(exc).__name__,
                          'execution':'NONE','device_ack':False},sort_keys=True))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
