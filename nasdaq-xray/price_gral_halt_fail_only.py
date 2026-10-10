#!/usr/bin/env python3
"""Exact 2026-10-09 GRAL Nasdaq historical full-session halt, FAIL ONLY.

Authority comes from immutable original official Nasdaq RSS halt witness;
source-coverage corroboration is an actual, same-ASOF Sina observation.
Never turn a provider observation or halted zero-volume pseudo-bar into PASS.
No network calls, synthetic market bars, alpha, MC, or orders.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EVENT=ROOT/"evidence/nasdaq_gral_20260923_full_session_halt_v1.json"
SINA=ROOT/"sina_state.json"
PINNED_EVENT_BLOB="55f807af528a723883e307105d7f59f202324dbb"
ONLY_ASOF="2026-10-09"
HALT_DAY="2026-09-23"
SCHEMA="XRAY_PRICE_GRAL_20261009_HALTED_SESSION_FAIL_ONLY_V1"

def blob_sha(buf:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(buf)).encode()+bytes([0])+buf).hexdigest()

def evaluate(row,asof,dates,queue_hash,event,event_sha,sina,sina_sha):
    if (asof!=ONLY_ASOF or not isinstance(row,dict)
        or row.get("status") not in {"UNKNOWN","BLOCK_CURRENT_RUN"}
        or row.get("status")=="PASS_PRICE_DV30"
        or not isinstance(dates,list) or len(dates)!=30
        or len(set(dates))!=30 or dates!=sorted(dates)
        or dates[-1]!=asof or HALT_DAY not in dates
        or not isinstance(event,dict) or event_sha!=PINNED_EVENT_BLOB
        or not isinstance(sina,dict) or not isinstance(sina_sha,str)
        or len(sina_sha)!=40 or not isinstance(queue_hash,str)):
        return None
    if not (event.get("schema")=="XRAY_PRICE_HISTORICAL_HALT_FAIL_ONLY_WITNESS_V1"
        and event.get("asof_et")=="2026-10-07"
        and event.get("symbol")=="GRAL"
        and event.get("halt_session")==HALT_DAY
        and event.get("execution")=="NONE" and event.get("real_money")=="NO-GO"
        and event.get("unknown_never_pass") is True
        and event.get("no_synthetic_bar") is True
        and event.get("alpha_authority") is False
        and event.get("decision_direction")=="BLOCK_TO_FAIL_ONLY_NEVER_PASS"):
        return None
    evidence=event.get("official_rss_record") or {}
    origin=event.get("source") or {}
    if not (evidence.get("IssueSymbol")=="GRAL"
        and evidence.get("Mkt")=="Q"
        and evidence.get("HaltDate")=="09/23/2026"
        and evidence.get("ReasonCode")=="T3"
        and str(evidence.get("HaltTime") or "").strip().startswith("06:55:00")
        and evidence.get("ResumptionDate")=="09/24/2026"
        and str(evidence.get("ResumptionTradeTime") or "").strip().startswith("07:05:00")
        and origin.get("url")=="https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate=09232026"
        and origin.get("workflow_run_id")==37751249372
        and origin.get("workflow_head_sha")=="da25d4204220d34a00d0deb08ec9494f6154eb2d"
        and origin.get("official_feed_row_count")==93
        and origin.get("matched_symbol_row_count")==1):
        return None
    if not (sina.get("asof_et")==asof
        and sina.get("queue_hash")==queue_hash
        and sina.get("execution")=="NONE"
        and sina.get("real_money")=="NO-GO"
        and sina.get("unknown_never_pass") is True
        and sina.get("expected30")==dates
        and isinstance(sina.get("queue"),list)
        and sina.get("queue_total")==len(sina["queue"])
        and "GRAL" in sina["queue"]
        and isinstance(sina.get("results"),dict)
        and len(sina["results"])==len(sina["queue"])):
        return None
    source=sina["results"].get("GRAL")
    if not isinstance(source,dict):return None
    info=source.get("info")
    if not (source.get("status")=="UNKNOWN_STATIC"
        and type(source.get("attempts")) is int and source["attempts"]>=1
        and isinstance(info,dict)
        and info.get("reason")=="EXACT30_INCOMPLETE_NEVER_PASS"
        and info.get("no_synthetic_bar") is True
        and info.get("known_session_count")==29
        and info.get("dates")==[HALT_DAY]):
        return None
    source_clock=source.get("updated_at_utc")
    try:
        timestamp=dt.datetime.fromisoformat(str(source_clock).replace("Z","+00:00"))
        if timestamp.tzinfo is None or timestamp.date()<dt.date.fromisoformat(asof):
            return None
    except (ValueError,TypeError,OverflowError):
        return None
    return {
        "schema":SCHEMA,
        "reason":"OFFICIAL_NASDAQ_GRAL_FULL_SESSION_HALT_EXACT30_UNUSABLE",
        "proof":"IMMUTABLE_OFFICIAL_RSS_HALT_PLUS_SAME_ASOF_29_SINA_BARS",
        "source":"NASDAQ_TRADER_HISTORICAL_HALT_FAIL_ONLY",
        "asof_et":asof,"official_halt_date":HALT_DAY,
        "official_resumption_date":"2026-09-24",
        "official_event_witness_git_blob_sha":event_sha,
        "same_asof_sina_state_git_blob_sha":sina_sha,
        "same_asof_sina_queue_hash":queue_hash,
        "expected_sessions":30,"observed_usable_sessions":29,
        "missing_sessions":[HALT_DAY],
        "no_synthetic_bar":True,
        "decision_direction":"FAIL_ONLY_NEVER_PASS",
        "alpha_authority":False,"mc_primary_authority":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }

def apply_to_results(results,asof,dates,queue_hash,*,event_path=EVENT,sina_path=SINA):
    if asof!=ONLY_ASOF or not isinstance(results,dict):return []
    row=results.get("GRAL")
    if not isinstance(row,dict) or row.get("status") not in {"UNKNOWN","BLOCK_CURRENT_RUN"}:
        return []
    try:
        eb=event_path.read_bytes();sb=sina_path.read_bytes()
        if blob_sha(eb)!=PINNED_EVENT_BLOB:return []
        event=json.loads(eb);sina=json.loads(sb)
    except (ValueError,OSError,TypeError):
        return []
    proof=evaluate(row,asof,dates,queue_hash,event,blob_sha(eb),sina,blob_sha(sb))
    if proof is None:return []
    results["GRAL"]={
      "status":"FAIL_DV30_INSUFFICIENT_SESSIONS",
      "info":proof,
      "provenance":"EXACT_20261009_OFFICIAL_HALT_SINA_FAIL_ONLY",
    }
    return ["GRAL"]

def selftest():
    from copy import deepcopy
    from price_dv30_phase import expected30
    from pathlib import Path
    dates=expected30(ONLY_ASOF)
    event_bytes=EVENT.read_bytes()
    sina_bytes=SINA.read_bytes()
    assert blob_sha(event_bytes)==PINNED_EVENT_BLOB
    event=json.loads(event_bytes);sina=json.loads(sina_bytes)
    assert sina["asof_et"]==ONLY_ASOF
    row={"status":"UNKNOWN","info":{"reason":"AUTHENTICATED_SIP_RESOLVER_BRIDGE_REQUIRED"}}
    original=dict(row)
    proof=evaluate(row,ONLY_ASOF,dates,sina["queue_hash"],event,PINNED_EVENT_BLOB,
                   sina,blob_sha(sina_bytes))
    assert proof and proof["observed_usable_sessions"]==29
    assert row==original and proof["decision_direction"]=="FAIL_ONLY_NEVER_PASS"
    real={"GRAL":deepcopy(row),"AAPL":{"status":"PASS_PRICE_DV30"}}
    assert apply_to_results(real,ONLY_ASOF,dates,sina["queue_hash"])==["GRAL"]
    assert real["GRAL"]["status"]=="FAIL_DV30_INSUFFICIENT_SESSIONS"
    assert real["AAPL"]=={"status":"PASS_PRICE_DV30"}
    assert apply_to_results(real,ONLY_ASOF,dates,sina["queue_hash"])==[]
    cases=[
      ("ASOF",row,"2026-10-08",dates,event,PINNED_EVENT_BLOB,sina),
      ("WRONG_EVENT_SHA",row,ONLY_ASOF,dates,event,"0"*40,sina),
      ("NO_HALT_DAY",row,ONLY_ASOF,[d for d in dates if d!=HALT_DAY],event,PINNED_EVENT_BLOB,sina),
      ("TAMPERED_OFFICIAL",row,ONLY_ASOF,dates,dict(event,official_rss_record=dict(event["official_rss_record"],ResumptionDate="09/23/2026")),PINNED_EVENT_BLOB,sina),
      ("SOURCE_ASOF_DRIFT",row,ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,dict(sina,asof_et="2026-10-08")),
      ("SOURCE_BAD_COUNT",row,ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,dict(sina,results=dict(sina["results"],GRAL=dict(sina["results"]["GRAL"],info=dict(sina["results"]["GRAL"]["info"],known_session_count=30)))),
      ("SOURCE_NO_SYNTHETIC_FALSE",row,ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,dict(sina,results=dict(sina["results"],GRAL=dict(sina["results"]["GRAL"],info=dict(sina["results"]["GRAL"]["info"],no_synthetic_bar=False)))),
      ("PREEXISTING_PASS",{"status":"PASS_PRICE_DV30"},ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,sina),
      ("PREEXISTING_FAIL",{"status":"FAIL_DV30"},ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,sina),
      ("SCOPE_QUEUE_HASH",row,ONLY_ASOF,dates,event,PINNED_EVENT_BLOB,dict(sina,queue_hash="0"*64)),
    ]
    for name,r,asof,ds,ev,sha,st in cases:
        outcome=evaluate(r,asof,ds,sina["queue_hash"],ev,sha,st,blob_sha(sina_bytes))
        assert outcome is None, ("UNSAFE_GRAL_FAIL_ONLY_ACCEPTED",name,outcome)
    assert apply_to_results({"GRAL":row},"2026-10-08",dates,sina["queue_hash"])==[]
    print("XRAY_GRAL_09_OCT_OFFICIAL_HALT=PASS_REAL_PINNED_WITNESS_10_NEGATIVE_NO_PRIMARY")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:selftest()
    else:ap.error("--selftest only")
