"""Private NEON 477 archive: exact source-verified ASOF, no alert or trade authority.

Only the existing authorized Google Sheet may receive output. No public rows,
raw IEX OHLCV, order, ChatGPT card, iOS push or extra clock/workflow is created.
Missing shadow factors become explicit N/A, never fabricated 0 or new AL.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote

import runner
import daily_job
import neon_shadow_v3 as neon
import private_sheet_writer as original

TAB = "NEON_477_GUNLUK"
LAST_COL = "W"
# The shared AL/STOP/outbox read cap is 20,000 rows and must NOT change.
# NEON appends 477 research rows every natural XNAS session, so it needs
# its own bounded, paginated authenticated reader. This limit is a finite
# per-tab safety bound, not a claim of unlimited Google Sheets capacity.
NEON_PAGE_ROWS = 8000
MAX_NEON_ARCHIVE_ROWS = 200000
VERSION = "NEON_V3_PRIVATE_RESEARCH_ONLY_V1"
HEADER = (
    "KAYIT_ID", "ASOF_ET", "SEMBOL", "SIRA", "SKOR_100",
    "ONCEKI_SKOR_ASOF", "SKOR_FARKI", "TREND_100",
    "MOMENTUM_100", "REL_GUC_100", "VOLATILITE_GUVEN_100",
    "SUREKLILIK_100", "KORIDOR", "KAYNAK_KARAR",
    "VERI_DURUMU", "SON_IEX_BAR_ZAMANI", "LIKIDITE",
    "SPREAD", "GAP", "KANIT_URL", "KAPSAM_SHA256",
    "ALGORITMA_SHA256", "SURUM"
)
assert len(HEADER) == 23
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN = re.compile(r"^https://github[.]com/gokaydonmez39-jpg/kripto-radar/actions/runs/[1-9][0-9]*$")


class NeonLedgerHold(ValueError):
    pass


def need(value, reason):
    if not value:
        raise NeonLedgerHold(reason)


def number(x, lo=0, hi=100):
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise NeonLedgerHold("INVALID_FACTOR_OR_SCORE") from None
    need(d.is_finite() and Decimal(lo) <= d <= Decimal(hi),
         "OUT_OF_RANGE_FACTOR_OR_SCORE")
    return d


def source_proof(scans, asof, url, master_sha, policy_sha):
    need(isinstance(scans,list) and scans and tuple(scans[0]) == original.SCAN_HEADER,
         "SCAN_HEADER_DRIFT")
    # A malformed data row may NOT be skipped and let an earlier valid
    # 477/477 proof impersonate the ledger's latest authoritative source.
    # Google returns trailing unused grid cells trimmed; every returned
    # source record must contain a canonical, validated ASOF before POST.
    existing = scans[1:]
    need(all(isinstance(r, list) and len(r) > 0 and
             original.canonical_scan_day(r[0]) for r in existing),
         "SCAN_ROW_ASOF_INVALID")
    need(all(len(r) >= 10 for r in existing), "SCAN_PARTIAL_ROW")
    # Do not let a valid last row hide an out-of-order/future scan epoch.
    # Gaps remain legal; an old session may NEVER be appended after a new one.
    days=[r[0] for r in existing]
    need(all(original.canonical_scan_day(d) for d in days) and
         len(days)==len(set(days)) and days==sorted(days),
         "SCAN_DATE_ORDER_OR_DUPLICATE")
    need(existing and existing[-1][0] == asof, "LATEST_SCAN_ASOF_MISMATCH")
    hits = [r for r in existing if r[0] == asof]
    need(len(hits) == 1, "SCAN_ASOF_DUPLICATE")
    r=hits[0]
    need(r[8] == url and RUN.fullmatch(r[8]) is not None and
         [str(r[i]).upper() for i in (2,3,4,5,6)] ==
         ["477","477","477","0","TRUE"], "SCAN_NOT_FINAL_477_OR_WRONG_RUN")
    note=original.scan_source_proof(r[9])
    # Substring membership accepts forged values such as 'scheduled' and
    # duplicate conflicting origin tokens. Only the exact natural producer
    # label and a SINGLE canonical source_event=schedule field may qualify.
    origins=[part.strip() for part in str(r[9]).split(";")
             if part.strip().startswith("source_event=")]
    need(note["scopeSHA"] == master_sha and
         note["algorithmSHA"] == policy_sha and
         r[1] == original.RUN_EVENT_LABELS["schedule"] and
         origins == ["source_event=schedule"],
         "SCAN_POLICY_OR_EVENT_PROOF_DRIFT")
    return r


def score_delta(score, previous, policy_sha):
    """One exact calculation for stored history and newly appended rows."""
    old=previous[4] if previous is not None and previous[21]==policy_sha else "N/A"
    if score=="N/A" or old=="N/A":
        return "N/A"
    return str((number(score)-number(old)).quantize(
        Decimal(".01"),rounding=ROUND_HALF_UP))


def previous_archive(existing, asof, master):
    need(isinstance(existing,list) and existing and tuple(existing[0])==HEADER,
         "NEON_LEDGER_HEADER_DRIFT")
    day_rows={}
    found=set()
    last_day=None
    for row in existing[1:]:
        need(isinstance(row,list) and len(row) == len(HEADER), "LEDGER_ROW_WIDTH")
        d,s=row[1],row[2]
        try:
            need(date.fromisoformat(d).isoformat()==d,"LEDGER_ASOF_INVALID")
        except (ValueError,TypeError) as exc:
            raise NeonLedgerHold("LEDGER_ASOF_INVALID") from None
        # AppendCells must preserve 477-row day blocks in increasing ASOF.
        # A reverse or interleaved historic block is not a reliable delta
        # baseline even when all 477 symbol identities are individually valid.
        need(last_day is None or d>=last_day,
             "LEDGER_ASOF_ORDER_OR_NONCONTIGUOUS")
        last_day=d
        need(type(s) is str and neon.SYMBOL.fullmatch(s) is not None and
             row[0] == d+"|"+s and (d,s) not in found,
             "LEDGER_IDENTITY_OR_DUPLICATE")
        need(type(row[19]) is str and RUN.fullmatch(row[19]) is not None and
             type(row[20]) is str and HEX64.fullmatch(row[20]) is not None and
             type(row[21]) is str and HEX64.fullmatch(row[21]) is not None and
             row[22] == VERSION and
             (row[4] == "N/A" or 0 <= number(row[4]) <= 100),
             "LEDGER_PROVENANCE_INVALID")
        found.add((d,s))
        day_rows.setdefault(d,{})[s]=row
    need(all(len(items)==477 for items in day_rows.values()),
         "LEDGER_PARTIAL_ASOF")
    for rows in day_rows.values():
        need(len({r[19] for r in rows.values()})==1 and
             len({r[20] for r in rows.values()})==1 and
             len({r[21] for r in rows.values()})==1,
             "LEDGER_MIXED_DAY_SOURCE")
        # Historic source SHA and complete 477 IDs do NOT imply that
        # immutable persisted score cells remain mathematically coherent.
        # An unvalidated historical score must not contaminate a new delta.
        values=list(rows.values())
        missing=[r[4]=="N/A" for r in values]
        need(all(missing) or not any(missing),"LEDGER_MIXED_SCORE_STATUS")
        if all(missing):
            need(all(r[3]=="N/A" and
                     all(v=="N/A" for v in r[7:12]) and
                     r[12]=="HOLD" and r[13]=="UNKNOWN" and
                     r[14]=="HOLD_SHADOW_RESULT_MISSING"
                     for r in values),"LEDGER_NA_STATE_DRIFT")
            continue
        ranks=[r[3] for r in values]
        need(all(type(k) is str and re.fullmatch(r"[1-9][0-9]*",k)
                 for k in ranks) and
             {int(k) for k in ranks}==set(range(1,478)),
             "LEDGER_RANK_IDENTITY_DRIFT")
        ranked=sorted(values,key=lambda r:int(r[3]))
        last_score=None
        for r in ranked:
            score=number(r[4])
            factors=[number(v) for v in r[7:12]]
            expected=sum((value*Decimal(weight)
                          for value,weight in zip(factors,neon.WEIGHTS.values())),
                         Decimal(0)).quantize(Decimal(".01"),
                                               rounding=ROUND_HALF_UP)
            need(abs(score-expected)<=Decimal(".02"),
                 "LEDGER_SCORE_FACTOR_DRIFT")
            need(last_score is None or score<=last_score,
                 "LEDGER_RANK_SCORE_ORDER_DRIFT")
            last_score=score
    # The immutable archive is itself a consumer-facing score history.
    # Validate recorded prior date and delta before idempotent success or
    # another write. Preserve the producer's same-symbol/same-policy rule,
    # including gaps in sessions, PIT membership changes and N/A epochs.
    prior_day=None
    prior_rows={}
    for day,rows in day_rows.items():
        for symbol,row in rows.items():
            need(row[5]==(prior_day or "N/A"),"LEDGER_PRIOR_ASOF_DRIFT")
            old=prior_rows.get(symbol)
            expected=score_delta(row[4],old,row[21])
            if expected=="N/A":
                need(row[6]=="N/A","LEDGER_DELTA_MISSING_BASELINE")
            else:
                need(row[6]!="N/A" and
                     number(row[6],-100,100)==Decimal(expected),
                     "LEDGER_DELTA_MATH_DRIFT")
        prior_day,prior_rows=day,rows
    if asof in day_rows:
        return day_rows, "EXISTS"
    need(not day_rows or asof > max(day_rows), "NO_REPLAY_OR_BACKFILL")
    prior=max(day_rows,default=None)
    return day_rows, prior


def validated_shadow(payload, asof, master, master_sha, policy_sha):
    need(type(payload) is dict and
         payload.get("schema")=="XRAY_NASDAQ_NEON_V3_EPHEMERAL_SHADOW_V1" and
         payload.get("asof_et")==asof and
         payload.get("source_event")=="schedule" and
         payload.get("scope_sha256")==master_sha and
         payload.get("policy_sha256")==policy_sha and
         payload.get("notification_sent") is False and
         payload.get("orders_sent")==0 and
         payload.get("chatgpt_card_written") is False,
         "NEON_SHADOW_PROVENANCE_DRIFT")
    counts=payload.get("counts")
    rows=payload.get("rows")
    need(type(counts) is dict and counts.get("master")==477 and
         counts.get("scored")==477 and counts.get("na")==0 and
         type(rows) is list and len(rows)==477,
         "SHADOW_NOT_477_FULLY_SCORED")
    result={}
    previous_ranked_score=None
    for index, row in enumerate(rows,1):
        need(type(row) is dict and row.get("symbol") in master and
             type(row.get("rank")) is int and row["rank"]==index,
             "SHADOW_RANK_OR_SYMBOL_INVALID")
        s=row["symbol"]
        need(s not in result and row.get("bar_asof")==asof and
             type(row.get("last_valid_bar_time")) is str and
             row["last_valid_bar_time"][:10]==asof,
             "SHADOW_DUPLICATE_OR_BAR_ASOF")
        # A matching date prefix is not a valid IEX timestamp or provenance.
        # A timezone-offset timestamp must resolve to the same UTC XNAS date.
        try:
            bar_time=datetime.fromisoformat(
                row["last_valid_bar_time"].replace("Z","+00:00"))
        except (ValueError, TypeError):
            raise NeonLedgerHold("SHADOW_BAR_TIMESTAMP_INVALID") from None
        need(bar_time.tzinfo is not None and bar_time.utcoffset() is not None
             and bar_time.astimezone(timezone.utc).date().isoformat()==asof,
             "SHADOW_BAR_TIMESTAMP_INVALID")
        factors=row.get("factors")
        need(type(factors) is dict and set(factors)==set(neon.WEIGHTS),
             "SHADOW_FACTOR_SET_INVALID")
        values={key:number(value) for key,value in factors.items()}
        score=number(row.get("score"))
        # Ranks are sequential, but that alone does not establish ordering.
        # Equal-score symbol order is presentation-only; numerical order is required.
        need(previous_ranked_score is None or score <= previous_ranked_score,
             "SHADOW_RANK_SCORE_OUT_OF_ORDER")
        previous_ranked_score=score
        expected=sum((values[k]*Decimal(w) for k,w in neon.WEIGHTS.items()),
                     Decimal(0)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        need(abs(score-expected)<=Decimal(".02"), "SHADOW_SCORE_MATH_DRIFT")
        need(row.get("source_decision") in ("AL","IZLE","ELE") and
             row.get("signal_status") in ("SOURCE_AL_NOT_DELIVERY_AUTHORITY","NO_NEW_AL"),
             "SHADOW_AL_AUTHORITY_DRIFT")
        if row["source_decision"]=="AL":
            need(row["signal_status"]=="SOURCE_AL_NOT_DELIVERY_AUTHORITY" and
                 row["decision_corridor"]=="HOLD_OUTBOX_NOT_ATTESTED",
                 "AL_CANNOT_GAIN_NEON_DELIVERY_AUTHORITY")
        else:
            need(row["signal_status"]=="NO_NEW_AL",
                 "SCORE_CANNOT_CREATE_AL")
            expected_corridor=("YAKINDAN_IZLE" if score>=Decimal("75")
                               else "BEKLE")
            need(row["decision_corridor"]==expected_corridor,
                 "SHADOW_SCORE_CORRIDOR_DRIFT")
        need(row.get("liquidity") in ("PASS_IEX_SINGLE_VENUE",
                                      "FAIL_IEX_SINGLE_VENUE"),
             "SHADOW_LIQUIDITY_STATUS_INVALID")
        need(row.get("spread")=="UNKNOWN" and row.get("gap")=="UNKNOWN" and
             row.get("orders_sent")==0, "RISK_UNKNOWN_CANNOT_BECOME_PASS")
        result[s]=(score,values,row)
    need(len(result)==477 and set(result)==set(master), "SHADOW_MASTER_COVERAGE")
    return result


def plan(asof, url, master, policy_sha, scans, existing, shadow):
    master_sha=neon.scope_digest(master)
    need(type(policy_sha) is str and HEX64.fullmatch(policy_sha) is not None,
         "INVALID_POLICY_SHA")
    need(type(url) is str and RUN.fullmatch(url) is not None,
         "INVALID_NASDAQ_RUN_URL")
    need(type(asof) is str and re.fullmatch(r"20\d{2}-\d{2}-\d{2}",asof),
         "ASOF_INVALID")
    need(date.fromisoformat(asof).isoformat()==asof,"ASOF_INVALID")
    source_proof(scans,asof,url,master_sha,policy_sha)
    ledger, prior=previous_archive(existing,asof,master)
    if prior=="EXISTS":
        same=ledger[asof]
        need(set(same)==set(master) and
             all(row[19]==url and row[20]==master_sha and
                 row[21]==policy_sha for row in same.values()),
             "SAME_ASOF_DIFFERENT_RUN_OR_POLICY")
        return {"status":"NEON_PRIVATE_477_ALREADY_VERIFIED_NO_REPLAY",
                "rows":[],"scored":sum(row[4]!="N/A" for row in same.values()),
                "na":sum(row[4]=="N/A" for row in same.values()),"asof":asof}
    measures=validated_shadow(shadow,asof,master,master_sha,policy_sha) if shadow is not None else None
    rows=[]
    for s in master:
        previous=ledger.get(prior,{}).get(s)
        if measures is None:
            score="N/A";rank="N/A";factors=["N/A"]*5
            status="HOLD_SHADOW_RESULT_MISSING";corridor="HOLD";source_dec="UNKNOWN"
            timestamp="N/A";liquid="UNKNOWN";spread="UNKNOWN";gap="UNKNOWN"
        else:
            value,fac,item=measures[s]
            score=str(value);rank=str(item["rank"])
            factors=[str(fac[x]) for x in ("trend","momentum","relative_strength",
                                         "volatility_safety","continuity")]
            status="RESEARCH_SCORE_UNVALIDATED";corridor=item["decision_corridor"]
            source_dec=item["source_decision"]
            timestamp=item["last_valid_bar_time"]
            liquid=item["liquidity"];spread=item["spread"];gap=item["gap"]
        delta=score_delta(score,previous,policy_sha)
        rows.append([asof+"|"+s,asof,s,rank,score,prior or "N/A",delta,
                     *factors,corridor,source_dec,status,timestamp,liquid,spread,gap,
                     url,master_sha,policy_sha,VERSION])
    need(len(rows)==477 and all(len(r)==len(HEADER) for r in rows),
         "NEON_477_OUTPUT_MALFORMED")
    return {"status":"NEON_PRIVATE_477_NEW_SOURCE_VERIFIED","rows":rows,
            "scored":sum(r[4]!="N/A" for r in rows),
            "na":sum(r[4]=="N/A" for r in rows),"asof":asof}


def read_archive(api):
    """Read EVERY allocated NEON grid row in bounded GET pages.

    Never use the 20,000-row scan/outbox cap for a 477-per-session archive.
    Grid rowCount comes from a fresh provider GET each time (including after
    an append that may have expanded the sheet). Pad omitted trailing blank
    cells to preserve row positions, then trim only final unused grid rows.
    Interior holes are left visible for previous_archive() to reject.
    """
    fields="?fields=sheets.properties(sheetId,title,gridProperties(rowCount))"
    meta=api.request(fields)
    need(isinstance(meta,dict) and isinstance(meta.get("sheets"),list),
         "NEON_ARCHIVE_METADATA_INVALID")
    matches=[x.get("properties",{}) for x in meta["sheets"]
             if isinstance(x,dict) and isinstance(x.get("properties"),dict)
             and x["properties"].get("title")==TAB]
    need(len(matches)==1 and
         type(matches[0].get("gridProperties",{}).get("rowCount")) is int,
         "NEON_ARCHIVE_METADATA_INVALID")
    allocated=matches[0]["gridProperties"]["rowCount"]
    need(1<=allocated<=MAX_NEON_ARCHIVE_ROWS,
         "NEON_ARCHIVE_CAPACITY_HOLD")
    occupied=[]
    for first in range(1,allocated+1,NEON_PAGE_ROWS):
        last=min(allocated,first+NEON_PAGE_ROWS-1)
        address=quote("'{}'!A{}:{}{}".format(TAB,first,LAST_COL,last),safe="")
        response=api.request(
            "/values/"+address+"?valueRenderOption=FORMATTED_VALUE")
        need(isinstance(response,dict) and
             isinstance(response.get("values",[]),list),
             "NEON_ARCHIVE_PAGE_INVALID")
        page=response.get("values",[])
        width=last-first+1
        need(len(page)<=width and all(isinstance(r,list) for r in page),
             "NEON_ARCHIVE_PAGE_INVALID")
        occupied.extend(page)
        occupied.extend([[] for _ in range(width-len(page))])
    while occupied and not occupied[-1]:
        occupied.pop()
    need(bool(occupied) and len(occupied)<=MAX_NEON_ARCHIVE_ROWS,
         "NEON_ARCHIVE_CAPACITY_HOLD")
    return occupied


def synchronize(api, asof, run_url, master, policy_sha, shadow):
    api.check_metadata()
    meta=api.request("?fields=properties(timeZone),sheets.properties(sheetId,title)")
    need(meta.get("properties",{}).get("timeZone")=="Europe/Istanbul",
         "SHEET_TIMEZONE_INVALID")
    titles=[s["properties"]["title"] for s in meta.get("sheets",[])
            if "properties" in s]
    need(titles.count(TAB)==1, "NEON_TAB_NOT_PREPARED")
    sheet_id=next(s["properties"]["sheetId"] for s in meta["sheets"]
                  if s.get("properties",{}).get("title")==TAB)
    scans=api.read("TARAMA_KAYITLARI","J")
    old=read_archive(api)
    p=plan(asof,run_url,master,policy_sha,scans,old,shadow)
    if not p["rows"]:
        return {k:p[k] for k in ("status","asof","scored","na")}
    need(read_archive(api)==old and
         api.read("TARAMA_KAYITLARI","J")==scans,
         "CONCURRENT_NEON_OR_SCAN_EDIT")
    # Reserve the entire 477-row next epoch BEFORE a possibly committing POST.
    need(len(old)+len(p["rows"])<=MAX_NEON_ARCHIVE_ROWS,
         "NEON_ARCHIVE_CAPACITY_HOLD")
    payload={"requests":[{"appendCells":{
        "sheetId":sheet_id,
        "rows":[{"values":[{"userEnteredValue":{"stringValue":v}} for v in row]}
                for row in p["rows"]],
        "fields":"userEnteredValue"}}]}
    api.request(":batchUpdate",method="POST",body=payload)
    after=read_archive(api)
    need(after==old+p["rows"],"NEON_477_PRIVATE_READBACK_FAILED")
    return {"status":p["status"],"asof":asof,
            "scored":p["scored"],"na":p["na"]}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--snapshot",required=True)
    parser.add_argument("--shadow",required=True)
    args=parser.parse_args(argv)
    try:
        need(os.environ.get("GITHUB_EVENT_NAME")=="schedule","NOT_NATURAL_EOD")
        run_id=os.environ.get("GITHUB_RUN_ID","")
        need(re.fullmatch(r"[1-9][0-9]*",run_id) is not None,
             "INVALID_GITHUB_RUN_ID")
        # Advisory research archive can still permanently mutate private
        # rows: never let unrelated scheduled jobs assume EOD provenance.
        original.verify_natural_eod_writer_identity(os.environ)
        credential=os.environ.get("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON","")
        need(bool(credential),"PRIVATE_SHEET_AUTH_MISSING")
        snapshot=json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        asof=snapshot.get("asof_et")
        # A valid historic private scan is NOT authority for a scheduled
        # runner to append a stale NEON day. Bind the source snapshot to
        # the CURRENT official completed XNAS session and the strict
        # close+45m .. close+45m+10h production window BEFORE Google auth.
        try:
            observed=datetime.now(timezone.utc)
            natural_day=daily_job.current_completed_session(observed)
            need(type(asof) is str and asof==natural_day,
                 "NEON_ASOF_NOT_CURRENT_NATURAL_SESSION")
            neon.session_dates(asof,observed)
        except Exception:
            raise NeonLedgerHold(
                "NEON_ASOF_NOT_CURRENT_NATURAL_SESSION") from None
        master=runner.get_scope(watchlist_file=str(Path(__file__).with_name(
            "nasdaq_watchlist_477.json")),asof=asof)
        need(snapshot.get("scope_sha256")==neon.scope_digest(master) and
             snapshot.get("valid_data_coverage_complete") is True and
             snapshot.get("new_signal_publishable") is True,
             "PRIMARY_SOURCE_NOT_FINAL")
        policy_sha=runner.analysis_fingerprint()
        need(snapshot.get("analysis_fingerprint_sha256")==policy_sha,
             "SOURCE_POLICY_DRIFT")
        shadow=json.loads(Path(args.shadow).read_text(encoding="utf-8")) \
            if Path(args.shadow).is_file() else None
        api=original.SheetApi(credential)
        result=synchronize(api,asof,
            "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/"+run_id,
            master,policy_sha,shadow)
        print(json.dumps({**result,"orders_sent":0,"notification_sent":False},
                         sort_keys=True))
        return 0
    except Exception as exc:
        # Never print private cell values, URLs, response bodies, credentials or
        # tracebacks. Advisory-only failure must not mark source EOD successful.
        code=str(exc) if isinstance(exc,NeonLedgerHold) else type(exc).__name__
        print(json.dumps({"status":"NEON_PRIVATE_LEDGER_HOLD",
                          "reason_code":code,"orders_sent":0,
                          "notification_sent":False},sort_keys=True))
        return 3

if __name__=="__main__":
    raise SystemExit(main())
