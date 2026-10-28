#!/usr/bin/env python3
"""Fail-closed NASDAQ personal PANEL reconciliation from private source-of-truth.

No new scheduler, signal generation, broker, push, source edits or public rows.
Runs only inside the existing private EOD follow-up job with existing secrets.
"""
from datetime import date
import json
import os
import re
from private_sheet_writer import (
    SheetApi, HandoffBlocked, CANDIDATE_HEADER, SCAN_HEADER,
    rows_only, numeric, require,
)

PANEL_TITLE = 'XRAY — KİŞİSEL NASDAQ START / FINAL'
RUN_RE = re.compile(
    r'^https://github[.]com/gokaydonmez39-jpg/kripto-radar/actions/runs/[0-9]+$'
)
EXPECTED_LABELS = {
    8: 'Son doğrulanmış tarama seansı',
    9: 'GitHub çalışma kanıtı',
    15: 'Sinyal geçmişi',
}


def plan(panel, candidate_table, scan_table):
    """Pure deterministic plan; no historical level, event, or status writes."""
    require(isinstance(panel, list) and len(panel) > 15
            and panel[0] and panel[0][0] == PANEL_TITLE,
            'PANEL_IDENTITY_OR_RANGE_DRIFT')
    for index, label in EXPECTED_LABELS.items():
        require(len(panel[index]) >= 1 and panel[index][0] == label,
                'PANEL_LABEL_DRIFT')
    candidates = rows_only(candidate_table, CANDIDATE_HEADER)
    scans = rows_only(scan_table, SCAN_HEADER)
    require(bool(scans), 'PANEL_NO_VERIFIED_SCAN')
    require(len({r[0] for r in scans}) == len(scans),
            'PANEL_DUPLICATE_SCAN_DAY')
    scan_days = []
    for r in scans:
        require(len(r) >= 10, 'PANEL_SCAN_TRUNCATED')
        try:
            d = date.fromisoformat(r[0]).isoformat()
        except (TypeError, ValueError):
            raise HandoffBlocked('PANEL_BAD_SCAN_DATE') from None
        require(d == r[0], 'PANEL_NONCANONICAL_DATE')
        scan_days.append(d)
    require(scan_days == sorted(scan_days), 'PANEL_SCAN_ORDER_DRIFT')
    s = scans[-1]
    day = s[0]
    require([numeric(s[i]) for i in (2, 3, 4, 5)] ==
            [477., 477., 477., 0.] and str(s[6]).upper() == 'TRUE',
            'PANEL_LATEST_NOT_477_FINAL')
    require(RUN_RE.fullmatch(str(s[8])) is not None,
            'PANEL_UNTRUSTED_PROVENANCE_LINK')
    require(numeric(s[7]).is_integer() and 0 <= numeric(s[7]) <= 477,
            'PANEL_BAD_NEW_COUNT')
    identities = []
    matches = 0
    for r in candidates:
        require(len(r) >= 8 and r[0] == str(r[1])+'|'+str(r[2])
                and isinstance(r[2], str) and re.fullmatch(r'[A-Z0-9.]{1,16}', r[2]),
                'PANEL_BAD_EPISODE_ID')
        require(str(r[1]) <= day, 'PANEL_FUTURE_EPISODE')
        identities.append(r[0])
        matches += int(r[1] == day)
    require(len(identities) == len(set(identities)), 'PANEL_DUPLICATE_EPISODE')
    require(matches == int(numeric(s[7])), 'PANEL_NEW_EPISODE_COUNT_MISMATCH')
    # Preserve legacy custom panel comments, real alert state and all A-G prices.
    values = {
        8: [day,
            'Alpaca IEX EOD · 477/477 geçerli · 0 eksik · FINAL READY · '
            +str(matches)+' yeni teknik AL; XNAS '+day],
        9: [str(s[8]),
            'GitHub EOD kaynak kanıtı · private Sheet readback ayrı · '
            'iPhone cihaz ACK bilinmiyor'],
        15: [str(len(candidates))+' TEKNİK KAYIT',
             'ASOF|SEMBOL ayrı gözlem; orijinal stop ve hedef değişmez; '
             'son doğrulanmış EOD '+day],
    }
    changes = {r: vals for r, vals in values.items()
               if list(panel[r][1:3])+['']*(2-len(panel[r][1:3])) != vals}
    return {'values': values, 'changes': changes, 'asof_et': day,
            'candidate_count': len(candidates), 'new_count': matches}


def synchronize(api):
    api.check_metadata()
    original_panel = api.read('PANEL', 'C')
    original_candidates = api.read('ADAY_GECMISI', 'M')
    original_scans = api.read('TARAMA_KAYITLARI', 'J')
    p = plan(original_panel, original_candidates, original_scans)
    if not p['changes']:
        return {'status':'PANEL_READBACK_PASS', 'changed':False,
                'asof_et':p['asof_et'], 'device_ack':False}
    meta = api.request('?fields=properties(timeZone),sheets.properties(sheetId,title)')
    require(meta.get('properties',{}).get('timeZone') == 'Europe/Istanbul',
            'PANEL_TIMEZONE_DRIFT')
    ids = {x['properties']['title']:x['properties']['sheetId']
           for x in meta.get('sheets',[]) if 'properties' in x}
    panel_id = ids.get('PANEL')
    require(type(panel_id) is int and panel_id not in api.sheet_ids.values(),
            'PANEL_SHEET_ID_DRIFT')
    require(api.read('PANEL','C') == original_panel and
            api.read('ADAY_GECMISI','M') == original_candidates and
            api.read('TARAMA_KAYITLARI','J') == original_scans,
            'PANEL_CONCURRENT_SOURCE_CHANGE')
    requests = []
    for row_index, vals in sorted(p['changes'].items()):
        requests.append({'updateCells': {
            'range': {'sheetId':panel_id, 'startRowIndex':row_index,
                      'endRowIndex':row_index+1,
                      'startColumnIndex':1, 'endColumnIndex':3},
            'rows':[{'values':[{'userEnteredValue':{'stringValue':v}}
                               for v in vals]}],
            'fields':'userEnteredValue'
        }})
    api.request(':batchUpdate',method='POST',body={'requests':requests})
    after_panel = api.read('PANEL','C')
    require(all(len(after_panel)>idx and after_panel[idx][1:3]==vals
                for idx, vals in p['values'].items()),
            'PANEL_READBACK_MISMATCH')
    require(api.read('ADAY_GECMISI','M') == original_candidates
            and api.read('TARAMA_KAYITLARI','J') == original_scans,
            'PANEL_AUTHORITY_CHANGED_DURING_WRITE')
    return {'status':'PANEL_READBACK_PASS', 'changed':True,
            'asof_et':p['asof_et'], 'device_ack':False}


def main():
    try:
        secret = os.environ.get('XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON','')
        require(bool(secret),'PANEL_PRIVATE_AUTH_REQUIRED')
        api = SheetApi(secret)
        out = synchronize(api)
        # Public GitHub logs: aggregate status only; no symbols, prices or PII.
        print(json.dumps(out,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'PANEL_SYNC_BLOCKED',
                          'reason_type':type(exc).__name__,
                          'execution':'NONE','device_ack':False}))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
