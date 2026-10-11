#!/usr/bin/env python3
"""Current XNAS preopen evidence: exact session, source, delivery and root fences.

Pure read-only local audit. Never fetch provider bars, declare a market-data
license, send a signal/device notification, change the policy, or place orders.
This is a monitor, not a C4.17 PRIMARY/HISTORY/R92 authorization.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from source_epoch_freshness_guard import last_complete_session
import e2e_production_readiness as e2e
import research_preopen_source_audit as source

ROOT=Path(__file__).resolve().parent
NY=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
SCHEMA="XRAY_CURRENT_PREOPEN_SOURCE_AND_DELIVERY_GATE_V1"
MAX_ROOT_AGE=4500
MAX_OFFICIAL_GUARD_AGE=900

def stamp(v):
    if not isinstance(v,str):
        return None
    try:
        t=dt.datetime.fromisoformat(v.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except (ValueError,OverflowError):
        return None

def official_window(now):
    if now.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    now=now.astimezone(UTC)
    et=now.astimezone(NY)
    schedule=mcal.get_calendar("NASDAQ").schedule(
        start_date=et.date().isoformat(),end_date=et.date().isoformat())
    if len(schedule)!=1:
        return {"preopen":False,"current_session":None,"opening_utc":None}
    open_utc=schedule.iloc[0]["market_open"].to_pydatetime().astimezone(UTC)
    # Two useful stages: early audit at 08:25 ET and final audit ~09:15 ET.
    local_start=dt.datetime.combine(et.date(),dt.time(8,0),NY).astimezone(UTC)
    return {"preopen":local_start<=now<open_utc,
            "current_session":et.date().isoformat(),
            "opening_utc":open_utc.isoformat()}

def evaluate(now,root,master,price,terminal,official,readiness,sources):
    if now.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    now=now.astimezone(UTC)
    w=official_window(now)
    reasons=set()
    def require(ok,code):
        if not ok:reasons.add(code)
    require(w["preopen"],"NOT_OFFICIAL_NASDAQ_PREOPEN_WINDOW")
    try:
        last=last_complete_session(now)
    except (ValueError,TypeError,AttributeError,ImportError):
        last=None
        reasons.add("OFFICIAL_COMPLETED_SESSION_UNAVAILABLE")
    for role,data in (("ROOT",root),("MASTER",master),("PRICE",price),
                      ("TERMINAL",terminal),("OFFICIAL",official),
                      ("READINESS",readiness),("SOURCE",sources)):
        require(isinstance(data,dict) and data.get("execution")=="NONE"
                and data.get("real_money")=="NO-GO",
                role+"_SAFETY_UNVERIFIED")
    require(last is not None and all(d.get("asof_et")==last for d in
            (root,master,price,terminal,readiness,sources)),
            "PREOPEN_LAST_COMPLETE_ASOF_NOT_EXACT")
    updated=stamp(root.get("updated_at_utc"))
    age=(now-updated).total_seconds() if updated else None
    require(age is not None and -60<=age<=MAX_ROOT_AGE,
            "ROOT_RUN_STATE_STALE_OR_FUTURE")
    require(root.get("status")!="PARTIAL_HISTORY" and
            root.get("unknown_count")==0,
            "ROOT_HISTORY_PARTIAL_OR_UNKNOWN")
    require(sources.get("source_integrity_pass") is True,
            "SOURCE_SHA_AND_SET_CHAIN_UNVERIFIED")
    # Independent non-G9 veto, derived directly from PRICE rows. A forged or
    # stale summary flag cannot authorize a non-C4.17 vendor source even when
    # all other readiness booleans are accidentally set True.
    non_g9_price_count=e2e.non_g9_price_pass_count(price)
    require(non_g9_price_count==0 and
            readiness.get("price_pass_explicit_non_g9_count")==0,
            "C417_NON_G9_PRICE_SOURCE_RELEASE_VETO")
    require(readiness.get("current_mc_authority_count")==1 and
            sources.get("current_primary_mc_proof_complete") is True,
            "C417_MC_PRIMARY_CHAIN_NOT_PROVEN")
    require(readiness.get("official_nasdaq_session_freshness_attested") is True,
            "CANONICAL_EPOCH_STALE")
    require(readiness.get("full_e2e_research_attested") is True and
            terminal.get("full_end_to_end_research_pass") is True,
            "FULL_RESEARCH_CHAIN_NOT_PROVEN")
    require(readiness.get("candidate_local_source_chain_attested") is True,
            "CANDIDATE_SOURCE_CHAIN_NOT_PROVEN")
    ss=official.get("sources") or {}
    require((ss.get("trade_halts") or {}).get("status")=="PASS" and
            (ss.get("security_status") or {}).get("status")=="PASS",
            "OFFICIAL_HALT_SUSPENSION_FEED_NOT_PASS")
    generated=stamp(official.get("generated_at_utc"))
    age_guard=(now-generated).total_seconds() if generated else None
    require(age_guard is not None and -60<=age_guard<=MAX_OFFICIAL_GUARD_AGE,
            "OFFICIAL_GUARD_STALE")
    candidate_keys=terminal.get("r92_candidates") or []
    require(isinstance(candidate_keys,list),"REGISTERED_CANDIDATE_LIST_MALFORMED")
    candidate_count=len(candidate_keys) if isinstance(candidate_keys,list) else 0
    if candidate_count:
        require(terminal.get("candidate_local_research_pass") is True and
                readiness.get("ready_for_current_research_signal") is True,
                "POSITIVE_CANDIDATE_NOT_RESEARCH_REGISTERED")
    # This witness never claims notification or device receipt, even if code
    # checks, platform toggles, or a backup GitHub issue are healthy.
    source_ready=not reasons
    # Candidate-local research is independent of unrelated global universe
    # unknowns. All positive local proof MUST still be bound to the real E2E
    # registered-R92 witness, exact current session and official safety.
    # This gate never registers, delivers or promotes an R92 itself.
    local_reasons=set()
    def local_require(ok,code):
        if not ok: local_reasons.add(code)
    local_require(w["preopen"],"LOCAL_NOT_OFFICIAL_PREOPEN")
    local_require(last is not None and all(
        d.get("asof_et")==last for d in
        (root,master,price,terminal,readiness,sources)),
        "LOCAL_CURRENT_EPOCH_NOT_EXACT")
    local_require(age is not None and -60<=age<=MAX_ROOT_AGE,
                  "LOCAL_ROOT_SCHEDULER_STALE")
    for role,data in (("ROOT",root),("MASTER",master),("PRICE",price),
                      ("TERMINAL",terminal),("OFFICIAL",official),
                      ("READINESS",readiness),("SOURCE",sources)):
        local_require(isinstance(data,dict) and data.get("execution")=="NONE"
                      and data.get("real_money")=="NO-GO",
                      "LOCAL_"+role+"_SAFETY_UNVERIFIED")
    local_require(sources.get("source_integrity_pass") is True,
                  "LOCAL_SOURCE_SHA_SET_NOT_PROVEN")
    local_require(non_g9_price_count==0 and
                  readiness.get("price_pass_explicit_non_g9_count")==0,
                  "LOCAL_NON_G9_PRICE_RELEASE_VETO")
    local_require(readiness.get("current_mc_authority_count")==1 and
                  sources.get("current_primary_mc_proof_complete") is True,
                  "LOCAL_PRIMARY_MC_NOT_PROVEN")
    local_require(readiness.get("official_nasdaq_session_freshness_attested") is True
                  and readiness.get("candidate_local_source_chain_attested") is True
                  and sources.get("candidate_local_source_preconditions_proven") is True,
                  "LOCAL_CANDIDATE_LINEAGE_NOT_PROVEN")
    local_require((ss.get("trade_halts") or {}).get("status")=="PASS" and
                  (ss.get("security_status") or {}).get("status")=="PASS",
                  "LOCAL_OFFICIAL_SAFETY_NOT_PASS")
    local_require(age_guard is not None and -60<=age_guard<=MAX_OFFICIAL_GUARD_AGE,
                  "LOCAL_OFFICIAL_GUARD_STALE")
    local_require(candidate_count>0,"LOCAL_NO_REGISTERED_R92")
    local_require(terminal.get("candidate_local_research_pass") is True and
                  readiness.get("ready_for_current_research_signal") is True,
                  "LOCAL_EXACT_R92_REGISTRATION_NOT_ATTESTED")
    candidate_local_ready=not local_reasons
    return {
        "schema":SCHEMA,"observed_utc":now.isoformat(),
        "opening_utc":w["opening_utc"],"session_date_et":w["current_session"],
        "expected_completed_session_et":last,
        "master_asof_et":master.get("asof_et"),
        "terminal_asof_et":terminal.get("asof_et"),
        "root_age_seconds":round(age) if age is not None and math.isfinite(age) else None,
        "official_guard_age_seconds":round(age_guard) if age_guard is not None and math.isfinite(age_guard) else None,
        "registered_candidate_count":candidate_count,
        "explicit_non_g9_price_pass_count":non_g9_price_count,
        "candidate_local_research_preconditions_attested":candidate_local_ready,
        "candidate_local_preopen_blockers":sorted(local_reasons),
        "candidate_local_preopen_status":(
            "CURRENT_R92_LOCAL_PRECONDITIONS_ONLY_NO_DEVICE_RECEIPT"
            if candidate_local_ready else "LOCAL_RESEARCH_BLOCKED_NO_GO"),
        "status":"PREOPEN_RESEARCH_CHAIN_ATTESTED_NO_DEVICE_RECEIPT" if source_ready else "PREOPEN_BLOCKED_NO_GO",
        "research_source_chain_ready":source_ready,
        "blockers":sorted(reasons),
        "c417_primary_created":False,"c417_history_created":False,
        "r92_created":False,"notification_attempted":False,
        "real_device_receipt_verified":False,
        "alpha_promotion_authorized":False,
        "automated_orders_authorized":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        "no_vendor_bars_or_private_account_data_emitted":True,
    }

def selftest():
    monday=dt.datetime(2026,10,12,13,15,tzinfo=UTC)
    window=official_window(monday)
    assert window["preopen"] and window["current_session"]=="2026-10-12"
    assert window["opening_utc"]=="2026-10-12T13:30:00+00:00"
    assert last_complete_session(monday)=="2026-10-09"
    assert not official_window(dt.datetime(2026,10,11,13,tzinfo=UTC))["preopen"]
    assert not official_window(dt.datetime(2026,10,12,13,30,tzinfo=UTC))["preopen"]
    base={"asof_et":"2026-10-09","execution":"NONE","real_money":"NO-GO"}
    root=dict(base,updated_at_utc="2026-10-12T13:00:00Z",
              status="DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED",unknown_count=0)
    master=dict(base)
    price=dict(base,pass_symbols=[],results={})
    terminal=dict(base,full_end_to_end_research_pass=True,
                  candidate_local_research_pass=True,r92_candidates=[])
    official={"execution":"NONE","real_money":"NO-GO",
              "generated_at_utc":"2026-10-12T13:14:00Z",
              "sources":{"trade_halts":{"status":"PASS"},
                         "security_status":{"status":"PASS"}}}
    readiness=dict(base,price_pass_explicit_non_g9_count=0,
       current_mc_authority_count=1,
       official_nasdaq_session_freshness_attested=True,
       full_e2e_research_attested=True,
       candidate_local_source_chain_attested=True,
       ready_for_current_research_signal=False)
    sources=dict(base,source_integrity_pass=True,
                 current_primary_mc_proof_complete=True)
    objs=[root,master,price,terminal,official,readiness,sources]
    good=evaluate(monday,*objs)
    assert good["research_source_chain_ready"] and not good["real_device_receipt_verified"]
    assert good["registered_candidate_count"]==0
    assert not good["candidate_local_research_preconditions_attested"]
    assert "LOCAL_NO_REGISTERED_R92" in good["candidate_local_preopen_blockers"]
    import copy
    cases=[
        (0,"status","PARTIAL_HISTORY","ROOT_HISTORY_PARTIAL_OR_UNKNOWN"),
        (0,"updated_at_utc","2026-10-10T13:00:00Z","ROOT_RUN_STATE_STALE_OR_FUTURE"),
        (1,"asof_et","2026-10-08","PREOPEN_LAST_COMPLETE_ASOF_NOT_EXACT"),
        (2,"execution","TRADE","PRICE_SAFETY_UNVERIFIED"),
        (3,"full_end_to_end_research_pass",False,"FULL_RESEARCH_CHAIN_NOT_PROVEN"),
        (4,"generated_at_utc","2026-10-12T12:00:00Z","OFFICIAL_GUARD_STALE"),
        (5,"current_mc_authority_count",0,"C417_MC_PRIMARY_CHAIN_NOT_PROVEN"),
        (6,"source_integrity_pass",False,"SOURCE_SHA_AND_SET_CHAIN_UNVERIFIED"),
        (5,"price_pass_explicit_non_g9_count",1,
         "C417_NON_G9_PRICE_SOURCE_RELEASE_VETO"),
        (6,"current_primary_mc_proof_complete",False,"C417_MC_PRIMARY_CHAIN_NOT_PROVEN"),
    ]
    for idx,k,val,reason in cases:
        m=copy.deepcopy(objs)
        m[idx][k]=val
        a=evaluate(monday,*m)
        assert a["status"]=="PREOPEN_BLOCKED_NO_GO" and reason in a["blockers"],(k,a)
        assert not a["real_device_receipt_verified"] and not a["alpha_promotion_authorized"]
    bad=copy.deepcopy(objs)
    bad[2]["pass_symbols"]=["TEST_NON_G9_SOURCE"]
    bad[2]["results"]={"TEST_NON_G9_SOURCE":{
        "status":"PASS_PRICE_DV30",
        "info":{"source":"RALLIES_BULK_ALL_TICKERS_EXACT30_NON_G9"}}}
    direct=evaluate(monday,*bad)
    assert direct["status"]=="PREOPEN_BLOCKED_NO_GO"
    assert direct["explicit_non_g9_price_pass_count"]==1
    assert "C417_NON_G9_PRICE_SOURCE_RELEASE_VETO" in direct["blockers"]
    assert direct["alpha_promotion_authorized"] is False
    # The ONLY local positive is already-registered and SHA-validated by the
    # upstream E2E witness (simulated here). Incomplete global coverage does
    # not erase that independent precondition; this creates no signal.
    local=copy.deepcopy(objs)
    local[0]["status"]="PARTIAL_HISTORY"
    local[0]["unknown_count"]=23
    local[3]["full_end_to_end_research_pass"]=False
    local[3]["r92_candidates"]=["TEST_RESEARCH|B"]
    local[5]["full_e2e_research_attested"]=False
    local[5]["ready_for_current_research_signal"]=True
    local[6]["candidate_local_source_preconditions_proven"]=True
    separate=evaluate(monday,*local)
    assert separate["status"]=="PREOPEN_BLOCKED_NO_GO"
    assert separate["candidate_local_research_preconditions_attested"] is True
    assert separate["registered_candidate_count"]==1
    assert separate["notification_attempted"] is False
    assert separate["real_device_receipt_verified"] is False
    for index,patch,reason in (
        (5,{"ready_for_current_research_signal":False},
         "LOCAL_EXACT_R92_REGISTRATION_NOT_ATTESTED"),
        (6,{"candidate_local_source_preconditions_proven":False},
         "LOCAL_CANDIDATE_LINEAGE_NOT_PROVEN"),
        (4,{"generated_at_utc":"2026-10-12T12:00:00Z"},
         "LOCAL_OFFICIAL_GUARD_STALE"),
        (5,{"current_mc_authority_count":0},"LOCAL_PRIMARY_MC_NOT_PROVEN"),
        (0,{"updated_at_utc":"2026-10-09T12:00:00Z"},
         "LOCAL_ROOT_SCHEDULER_STALE"),
    ):
        corrupted=copy.deepcopy(local)
        corrupted[index].update(patch)
        denied=evaluate(monday,*corrupted)
        assert not denied["candidate_local_research_preconditions_attested"]
        assert reason in denied["candidate_local_preopen_blockers"],reason
    corrupted=copy.deepcopy(local)
    corrupted[2]["pass_symbols"]=["TEST_NON_G9"]
    corrupted[2]["results"]={"TEST_NON_G9":{
        "status":"PASS_PRICE_DV30",
        "info":{"source":"RALLIES_BULK_NON_G9"}}}
    denied=evaluate(monday,*corrupted)
    assert not denied["candidate_local_research_preconditions_attested"]
    assert "LOCAL_NON_G9_PRICE_RELEASE_VETO" in denied["candidate_local_preopen_blockers"]
    bad=copy.deepcopy(objs)
    bad[3]["r92_candidates"]=["TEST_NOT_REGISTERED"]
    assert "POSITIVE_CANDIDATE_NOT_RESEARCH_REGISTERED" in evaluate(monday,*bad)["blockers"]
    assert evaluate(dt.datetime(2026,10,11,13,tzinfo=UTC),*objs)["status"]=="PREOPEN_BLOCKED_NO_GO"
    print("XRAY_DYNAMIC_PREOPEN_SELFTEST=PASS_20261012_09_ET_11_NEGATIVE_NO_GO_NO_DEVICE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.out is None or args.out.resolve().is_relative_to(ROOT.parent.resolve()):
        p.error("private runner temp --out required")
    read=lambda n:json.loads((ROOT/n).read_text(encoding="utf-8"))
    terminal=read("canonical_current_terminal.json")
    master=read("canonical_current_master_manifest.json")
    price=read("canonical_current_price_dv30.json")
    readiness=e2e.snapshot()
    sources=source.inspect(
        master,price,read("canonical_current_resolver_request.json"),
        terminal,readiness,e2e.sha("canonical_current_master_manifest.json"),
        e2e.sha("canonical_current_price_dv30.json"))
    result=evaluate(dt.datetime.now(UTC),read("orchestrator_state.json"),
                    master,price,terminal,read("canonical_official_source_guard.json"),
                    readiness,sources)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_DYNAMIC_PREOPEN="+result["status"])
    print("XRAY_DYNAMIC_PREOPEN_ASOF="+str(result["expected_completed_session_et"]))
    print("XRAY_DYNAMIC_PREOPEN_EXPLICIT_NON_G9_PRICE="+str(result["explicit_non_g9_price_pass_count"]))
    print("XRAY_DYNAMIC_PREOPEN_BLOCKERS="+json.dumps(result["blockers"]))
    print("XRAY_DYNAMIC_PREOPEN_LOCAL="+result["candidate_local_preopen_status"])
    print("XRAY_DYNAMIC_PREOPEN_LOCAL_BLOCKERS="+json.dumps(
        result["candidate_local_preopen_blockers"]))
    print("XRAY_DYNAMIC_PREOPEN_USER_DEVICE_RECEIPT=UNVERIFIED")

if __name__=="__main__":
    main()
