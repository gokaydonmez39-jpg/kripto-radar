#!/usr/bin/env python3
"""Standalone personal research alert reservation contract, no device claim.

This is NOT an automatic sender or canonical R92 authority. The single
pre-existing ChatGPT alert task can reserve one independently re-validated
low-confidence *research* advisory after GitHub exact-blob checks. No other
task, trading system or workflow may send or reserve.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_RESEARCH_ADVISORY_LEDGER_V1"
DIGEST = "XRAY_PERSONAL_EOD_RESEARCH_DIGEST_V1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Z0-9.]+\Z")
RESERVED = "RESERVED_ATTEMPT_NOT_DEVICE_DELIVERY"

def need(test,reason):
    if not test:
        raise ValueError("XRAY_PERSONAL_ADVISORY_"+reason)

def stable_key(d):
    need(d.get("schema")==DIGEST
         and d.get("execution")=="NONE" and d.get("real_money")=="NO-GO"
         and d.get("unknown_never_pass") is True
         and d.get("certified_C417_AL_signal_count")==0
         and d.get("registered_r92_count")==0
         and d.get("candidate_setup_is_not_R92") is True
         and d.get("automated_alert_authority") is False
         and d.get("iphone_receipt_attested") is False
         and d.get("no_raw_ohlcv_or_levels_exported") is True
         and d.get("source_confidence",{}).get("grade")=="LOW",
         "RESEARCH_NOT_CANONICAL_R92")
    binds=d.get("source_epoch_blobs")
    need(isinstance(binds,dict) and set(binds)=={"root","master","price"}
         and all(SHA.fullmatch(binds[k]) for k in binds),
         "SOURCE_BLOBS_REQUIRED")
    asof=d.get("asof_et")
    need(isinstance(asof,str)
         and re.fullmatch(r"20\d\d-\d\d-\d\d",asof),
         "ASOF_INVALID")
    candidates=d.get("research_setup_candidate_symbols")
    triggers=d.get("recent_technical_triggers")
    need(isinstance(candidates,list)
         and candidates==sorted(set(candidates))
         and all(TOKEN.fullmatch(s) for s in candidates)
         and len(candidates)==d.get("research_setup_candidate_count")
         and isinstance(triggers,list)
         and len(triggers)==d.get("recent_technical_trigger_count")
         and len(set(x.get("symbol") for x in triggers
                     if isinstance(x,dict)))==len(triggers),
         "RESEARCH_CANDIDATE_PARTITION")
    derived=[]
    for row in triggers:
        need(isinstance(row,dict) and TOKEN.fullmatch(row.get("symbol",""))
             and row.get("not_a_trade_or_R92") is True
             and row.get("technical_source_confidence")=="LIMITED_SECONDARY_EOD"
             and row.get("math_formula_audited") is True
             and isinstance(row.get("unresolved_or_rejected"),list),
             "TRIGGER_PROVENANCE")
        if row.get("status")=="RESEARCH_SETUP_CANDIDATE":
            need(not row["unresolved_or_rejected"],"CANDIDATE_WITH_BLOCKERS")
            derived.append(row["symbol"])
        else:
            need(row.get("status")=="TRIGGER_OBSERVED_NOT_APPROVED"
                 and bool(row["unresolved_or_rejected"]),
                 "REJECTED_TRIGGER_UNLABELED")
    need(sorted(derived)==candidates, "CANDIDATE_TRIGGER_MISMATCH")
    if not candidates:
        return None
    need(d.get("status")=="PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE",
         "CANDIDATE_STATUS_FALSE")
    raw=json.dumps({"asof":asof,"source_blobs":binds,"symbols":candidates},
                   sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()

def reserve(current,d,origin_task):
    need(isinstance(current,dict)
         and current.get("schema")==SCHEMA
         and current.get("execution")=="NONE"
         and current.get("real_money")=="NO-GO"
         and current.get("unknown_never_pass") is True
         and current.get("scope")=="PERSONAL_RESEARCH_ADVISORY_ONLY_NEVER_R92",
         "LEDGER_CONTRACT")
    history=current.get("entries")
    need(isinstance(history,list) and len(history)<=1000
         and all(isinstance(entry,dict)
             and HEX.fullmatch(entry.get("key",""))
             and entry.get("status")==RESERVED
             and entry.get("device_receipt_attested") is False
             and entry.get("execution")=="NONE"
             and entry.get("real_money")=="NO-GO"
             and isinstance(entry.get("symbols"),list)
             for entry in history)
         and len({entry["key"] for entry in history})==len(history),
         "LEDGER_HISTORY_TAMPER")
    key=stable_key(d)
    if key is None or any(entry["key"]==key for entry in history):
        return None
    need(origin_task=="6a825366222081918997094d76e6ae46",
         "ONLY_EXISTING_USER_FACING_CHATGPT_TASK")
    new=deepcopy(current)
    new["entries"].append({
        "key":key,"asof_et":d["asof_et"],
        "symbols":d["research_setup_candidate_symbols"],
        "source_epoch_blobs":d["source_epoch_blobs"],
        "status":RESERVED,
        "device_receipt_attested":False,
        "execution":"NONE","real_money":"NO-GO"})
    return new

def selftest():
    raw=json.loads((ROOT/"personal_research_signal_digest.json").read_text())
    original=json.loads((ROOT/"personal_research_advisory_ledger.json").read_text())
    need(stable_key(raw) is None
         and reserve(original,raw,"6a825366222081918997094d76e6ae46") is None,
         "CURRENT_ZERO_CANDIDATES_SILENT")
    # Positive is synthetic and confined to RAM; it MUST never be committed.
    test=deepcopy(raw)
    trigger=test["recent_technical_triggers"][0]
    trigger["status"]="RESEARCH_SETUP_CANDIDATE"
    trigger["unresolved_or_rejected"]=[]
    test["status"]="PERSONAL_RESEARCH_SETUP_CANDIDATES_AVAILABLE"
    test["research_setup_candidate_symbols"]=[trigger["symbol"]]
    test["research_setup_candidate_count"]=1
    positive=reserve(original,test,"6a825366222081918997094d76e6ae46")
    need(positive is not None and len(positive["entries"])==1
         and positive["entries"][0]["status"]==RESERVED
         and positive["entries"][0]["device_receipt_attested"] is False
         and reserve(positive,test,"6a825366222081918997094d76e6ae46") is None,
         "RESERVATION_EXACT_ONCE")
    mutants=(
        ("FALSE_R92",lambda d:d.update(registered_r92_count=1)),
        ("FAKE_RECEIPT",lambda d:d.update(iphone_receipt_attested=True)),
        ("RAW_EXPORT",lambda d:d.update(no_raw_ohlcv_or_levels_exported=False)),
        ("FAKE_BLOB",lambda d:d["source_epoch_blobs"].update(root="xyz")),
        ("FAKE_MATH",lambda d:d["recent_technical_triggers"][0].update(
            math_formula_audited=False)),
        ("BLOCKED_RISK",lambda d:d["recent_technical_triggers"][0].update(
            unresolved_or_rejected=["RR_BASIC_BELOW_THRESHOLD"])),
        ("MISSING_TRIGGER",lambda d:d["recent_technical_triggers"].pop(0)),
        ("FAKE_STATUS",lambda d:d.update(status="PERSONAL_LIQUIDITY_WATCH_AND_REJECTED_TRIGGERS")),
        ("FALSE_CONFIDENCE",lambda d:d["source_confidence"].update(grade="HIGH")),
    )
    for label,change in mutants:
        d=deepcopy(test)
        change(d)
        try: stable_key(d)
        except ValueError:pass
        else:raise AssertionError("FALSE_ADVISORY_RELEASE_"+label)
    try:reserve(original,test,"WRONG_TASK")
    except ValueError:pass
    else:raise AssertionError("WRONG_TASK_ACCEPTED")
    bad=deepcopy(original)
    bad["entries"].append({"key":"0"*64,"status":"DELIVERED"})
    try:reserve(bad,test,"6a825366222081918997094d76e6ae46")
    except ValueError:pass
    else:raise AssertionError("FALSE_DEVICE_ACK_ACCEPTED")
    print("XRAY_PERSONAL_ADVISORY_LEDGER_SELFTEST=PASS_11_NEGATIVES_DEDUP_NO_PHONE_RECEIPT_NO_R92")

if __name__=="__main__":
    selftest()
