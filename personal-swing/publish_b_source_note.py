#!/usr/bin/env python3
"""Attach redacted NASDAQ B evidence to the existing authoritative SUMMARY link cell.

Only a successful natural EOD producer can run this. No row values, formula,
delivery state, timestamps, named ranges or previous session cells are edited.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from urllib.parse import urlencode

from emit_b_source_envelope import EvidenceError, SCHEMA, collect
from private_sheet_writer import HandoffBlocked

TAB = "SWING_SKOR_GUNLUK"
RUN_PREFIX = "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/"
READY = "READY_FOR_CHATGPT_DAILY_DIGEST"
HEADER_COLUMNS = {0:"KAYIT_KIMLIGI",1:"ASOF_ET",4:"KAYIT_TIPI",26:"KANIT_URL",
                  27:"BILDIRIM_DURUMU",28:"BILDIRIM_ZAMANI_TR",29:"KAYIT_SHA256"}


def demand(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def label(value, query_fields):
    return "?" + urlencode({"ranges":value,"fields":query_fields})


def latest_summary(rows, source):
    demand(isinstance(rows,list) and 1<len(rows)<=50000,"SCORE_LEDGER_UNVERIFIED")
    h=rows[0]
    demand(isinstance(h,list) and len(h)==35 and all(h[i]==name for i,name in HEADER_COLUMNS.items()),
           "SCORE_HEADER_DRIFT")
    asof=source.get("asof")
    demand(isinstance(asof,str) and dt.date.fromisoformat(asof).isoformat()==asof,
           "SOURCE_DATE_UNVERIFIED")
    data=[r for r in rows[1:] if r and any(v!="" for v in r)]
    demand(all(isinstance(row,list) and len(row)>=2 and isinstance(row[1],str)
               and re.fullmatch(r"\d{4}-\d\d-\d\d",row[1])
               for row in data),"SCORE_LEDGER_ROW_UNVERIFIED")
    demand(bool(data) and max(r[1] for r in data)==asof,"SCORE_NEWER_OR_MISSING_ASOF")
    key=asof+"|SUMMARY"
    candidates=[(i,r) for i,r in enumerate(rows[1:],1) if isinstance(r,list)
                and (r[:1]==[key] or (len(r)>=5 and r[1]==asof and r[4]=="SUMMARY"))]
    demand(len(candidates)==1,"SCORE_SUMMARY_NOT_UNIQUE")
    i,r=candidates[0]
    demand(len(r)>=30 and r[1]==asof and r[4]=="SUMMARY" and type(source.get("run")) is int and source["run"]>0
           and r[26]==RUN_PREFIX+str(source["run"]) and r[27]==READY and r[28]==""
           and bool(re.fullmatch(r"[a-f0-9]{64}",r[29] if isinstance(r[29],str) else "")),
           "SCORE_SUMMARY_BINDING_UNVERIFIED")
    return i,r


def target_range(index):
    return "'"+TAB+"'!AA"+str(index+1)+":AC"+str(index+1)


def inspect_target(api, index, source_url):
    shape="properties(timeZone),sheets(properties(sheetId,title),data(startRow,startColumn,rowData(values(formattedValue,note))))"
    raw=api.request(label(target_range(index),shape))
    properties=raw.get("properties",{})
    hit=raw.get("sheets",[])
    demand(properties.get("timeZone")=="Europe/Istanbul" and isinstance(hit,list) and len(hit)==1,
           "SCORE_NOTE_TARGET_METADATA")
    entry=hit[0]
    prop=entry.get("properties",{})
    pieces=entry.get("data",[])
    demand(prop.get("title")==TAB and type(prop.get("sheetId")) is int and isinstance(pieces,list) and len(pieces)==1,
           "SCORE_NOTE_TARGET_TAB")
    part=pieces[0]
    grid=part.get("rowData",[])
    demand(part.get("startRow")==index and part.get("startColumn")==26 and len(grid)==1,
           "SCORE_NOTE_TARGET_COORDINATE")
    cells=grid[0].get("values",[])
    demand(len(cells)>=2 and cells[0].get("formattedValue")==source_url and
           cells[1].get("formattedValue")==READY and (len(cells)<3 or cells[2].get("formattedValue","")==""),
           "SCORE_NOTE_TARGET_NO_LONGER_READY")
    note=cells[0].get("note","")
    demand(isinstance(note,str),"SCORE_NOTE_TARGET_NOT_TEXT")
    return (prop["sheetId"],note)


def note_text(source):
    demand(source.get("schema")==SCHEMA and isinstance(source.get("proof"),list) and len(source["proof"])==4,
           "SOURCE_ENVELOPE_SCHEMA")
    result=SCHEMA+" "+json.dumps(source,separators=(",",":"),ensure_ascii=True)
    demand(len(result)<=2700 and "\n" not in result and "\r" not in result,"SOURCE_ENVELOPE_SIZE")
    return result


def synchronize_note(api, source):
    api.check_metadata()
    note=note_text(source)
    first=api.read(TAB,"AI")
    row,current=latest_summary(first,source)
    sheet_id,existing=inspect_target(api,row,current[26])
    if existing==note:
        return "ALREADY_VERIFIED"
    demand(existing=="","SCORE_NOTE_CONFLICT")
    second, current2=latest_summary(api.read(TAB,"AI"),source)
    demand(second==row and current2==current and inspect_target(api,row,current[26])==(sheet_id,""),
           "SCORE_NOTE_PREWRITE_DRIFT")
    change={"updateCells":{"range":{"sheetId":sheet_id,"startRowIndex":row,"endRowIndex":row+1,
                                  "startColumnIndex":26,"endColumnIndex":27},
                           "rows":[{"values":[{"note":note}]}],
                           "fields":"note"}}
    # One POST only. A lost or malformed ACK may follow a fully committed
    # note, but neither permits a blind second write or an optimistic PASS.
    def reconcile_exact_note_by_get():
        try:
            final_rows=api.read(TAB,"AI")
            final_index,final_row=latest_summary(final_rows,source)
            demand(final_index==row and final_row==current,
                   "SCORE_NOTE_UNCERTAIN_COMMIT_UNVERIFIED")
            demand(inspect_target(api,row,current[26])==(sheet_id,note),
                   "SCORE_NOTE_UNCERTAIN_COMMIT_UNVERIFIED")
        except Exception:
            # Provider diagnostics, URLs, private cells and HTTP bodies may
            # never enter public GitHub Actions logs or delivery receipts.
            raise EvidenceError("SCORE_NOTE_UNCERTAIN_COMMIT_UNVERIFIED") from None

    try:
        response=api.request(":batchUpdate",method="POST",
                             body={"requests":[change]})
    except HandoffBlocked as error:
        if str(error) not in (
                "GOOGLE_SHEETS_TRANSPORT_TimeoutError",
                "GOOGLE_SHEETS_TRANSPORT_URLError",
                "GOOGLE_SHEETS_HTTP_5XX"):
            raise
        reconcile_exact_note_by_get()
        return "ATTACHED_AND_VERIFIED"
    if not isinstance(response,dict) or response.get("replies")!=[{}]:
        reconcile_exact_note_by_get()
        return "ATTACHED_AND_VERIFIED"
    demand(inspect_target(api,row,current[26])==(sheet_id,note),
           "SCORE_NOTE_READBACK_UNVERIFIED")
    return "ATTACHED_AND_VERIFIED"


def main():
    # Reuse the existing EOD-bound private Sheets service account. Never print
    # requests, notes, Sheet IDs, credentials or provider exception text.
    from private_sheet_writer import SheetApi
    source=collect()
    status=synchronize_note(SheetApi(os.environ["XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON"]),source)
    print("XRAY_NASDAQ_B_SOURCE_NOTE="+status)


if __name__=="__main__":
    try:
        main()
    except EvidenceError as error:
        code=str(error)
        safe=code if re.fullmatch(r"[A-Z][A-Z0-9_]{2,70}",code) else "UNVERIFIED"
        print("XRAY_NASDAQ_B_SOURCE_NOTE=HOLD_"+safe,file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("XRAY_NASDAQ_B_SOURCE_NOTE=HOLD_UNVERIFIED",file=sys.stderr)
        sys.exit(1)
