#!/usr/bin/env python3
"""9 October 2026 pre-open: exact-source research gate with no false AL claims.

Read-only operational witness. Source/alpha correctness always comes from
the canonical E2E engine. Neither "test PASS" nor a healthy root process can
substitute for a current terminal and registered verified candidate.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import pathlib

ROOT=pathlib.Path(__file__).resolve().parent
UTC=dt.timezone.utc
SESSION_ASOF="2026-10-08"
SESSION_OPEN_UTC=dt.datetime(2026,10,9,13,30,tzinfo=UTC)
SCHEMA="XRAY_20261009_OPENING_RESEARCH_GATE_V1"

def parse_utc(value):
    if not isinstance(value,str) or not value:
        return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo is not None else None
    except ValueError:
        return None

def evaluate(now,root,readiness,sources,terminal):
    if now.tzinfo is None:
        raise ValueError("NOW_MUST_HAVE_TIMEZONE")
    now=now.astimezone(UTC)
    blockers=set()
    def need(condition,why):
        if not condition:blockers.add(why)

    need(root.get("execution")=="NONE" and root.get("real_money")=="NO-GO",
         "ROOT_SAFETY_UNVERIFIED")
    need(terminal.get("execution")=="NONE" and terminal.get("real_money")=="NO-GO",
         "TERMINAL_SAFETY_UNVERIFIED")
    need(readiness.get("execution")=="NONE" and readiness.get("real_money")=="NO-GO",
         "READINESS_SAFETY_UNVERIFIED")
    need(sources.get("execution")=="NONE" and sources.get("real_money")=="NO-GO",
         "SOURCE_SAFETY_UNVERIFIED")
    need(root.get("asof_et")==SESSION_ASOF
         and readiness.get("asof_et")==SESSION_ASOF
         and sources.get("asof_et")==SESSION_ASOF
         and terminal.get("asof_et")==SESSION_ASOF,
         "CURRENT_ASOF_EXACT_SET_NOT_PROVEN")
    need(sources.get("source_integrity_pass") is True,
         "MASTER_PRICE_RESOLVER_SHA_PARTITION_UNPROVEN")
    need(root.get("status")!="PARTIAL_HISTORY",
         "ROOT_HISTORY_PARTIAL")
    need(root.get("status") in ("DATA_PLANE_PARTIAL_UNKNOWN",
         "DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"),
         "ROOT_DATA_PLANE_COMPLETION_UNPROVEN")
    need(root.get("history_retryable") is not False or
         root.get("status")!="PARTIAL_HISTORY",
         "ROOT_HISTORY_NO_RETRYABLE_WORK")
    updated=parse_utc(root.get("updated_at_utc"))
    age=(now-updated).total_seconds() if updated is not None else None
    need(age is not None and -60<=age<=4500,
         "ROOT_DATA_PLANE_STALE_OVER_75_MIN")
    need(now < SESSION_OPEN_UTC,"PREOPEN_WINDOW_CLOSED")
    need(readiness.get("current_mc_authority_count")==1,
         "CURRENT_C417_PRIMARY_MC_MISSING")
    need(readiness.get("candidate_local_source_chain_attested") is True,
         "CANDIDATE_LOCAL_SOURCE_CHAIN_UNVERIFIED")
    need(readiness.get("ready_for_current_research_signal") is True,
         "REAL_REGISTERED_RESEARCH_CANDIDATE_UNVERIFIED")
    need(sources.get("candidate_local_source_preconditions_proven") is True,
         "PREOPEN_LOCAL_SOURCE_PRECONDITIONS_UNVERIFIED")
    # Delivery and account execution have separate authority, and must
    # never be silently asserted by opening gate.
    not_yet_open=now<SESSION_OPEN_UTC
    gate="SOURCE_RESEARCH_CANDIDATE_PREPARED_NOT_DEVICE_DELIVERED" if not blockers else "BLOCKED_NO_GO"
    return {
        "schema":SCHEMA,"asof_et":SESSION_ASOF,
        "generated_at_utc":now.isoformat(),
        "session_open_utc":SESSION_OPEN_UTC.isoformat(),
        "before_open":not_yet_open,
        "mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"alpha_authority":False,
        "root_history_unknown_count":root.get("unknown_count"),
        "root_data_plane_status":root.get("status"),
        "root_age_seconds":round(age) if age is not None and math.isfinite(age) else None,
        "canonical_terminal_asof":terminal.get("asof_et"),
        "c417_primary_mc_proven":readiness.get("current_mc_authority_count")==1,
        "registered_research_candidate_prepared":not bool(blockers),
        "user_phone_delivery_receipt_verified":False,
        "broker_order_authorized":False,
        "status":gate,"blockers":sorted(blockers),
        "not_trading_or_delivery_go":True,
    }

def selftest():
    now=dt.datetime(2026,10,9,10,tzinfo=UTC)
    root={"asof_et":SESSION_ASOF,"status":"DATA_PLANE_PARTIAL_UNKNOWN",
          "updated_at_utc":"2026-10-09T09:58:00Z",
          "execution":"NONE","real_money":"NO-GO"}
    rd={"asof_et":SESSION_ASOF,"execution":"NONE","real_money":"NO-GO",
        "current_mc_authority_count":1,
        "ready_for_current_research_signal":True,
        "candidate_local_source_chain_attested":True}
    src={"asof_et":SESSION_ASOF,"execution":"NONE","real_money":"NO-GO",
         "source_integrity_pass":True,
         "candidate_local_source_preconditions_proven":True}
    terminal={"asof_et":SESSION_ASOF,"execution":"NONE","real_money":"NO-GO"}
    assert evaluate(now,root,rd,src,terminal)["status"]=="SOURCE_RESEARCH_CANDIDATE_PREPARED_NOT_DEVICE_DELIVERED"
    assert evaluate(now,root,rd,src,terminal)["user_phone_delivery_receipt_verified"] is False
    assert evaluate(SESSION_OPEN_UTC,root,rd,src,terminal)["status"]=="BLOCKED_NO_GO"
    assert "PREOPEN_WINDOW_CLOSED" in evaluate(SESSION_OPEN_UTC,root,rd,src,terminal)["blockers"]
    from copy import deepcopy
    for obj,k,v,reason in (
        ("root","status","PARTIAL_HISTORY","ROOT_HISTORY_PARTIAL"),
        ("root","updated_at_utc","2026-10-08T23:00:00Z","ROOT_DATA_PLANE_STALE_OVER_75_MIN"),
        ("root","asof_et","2026-10-07","CURRENT_ASOF_EXACT_SET_NOT_PROVEN"),
        ("root","execution","ORDER","ROOT_SAFETY_UNVERIFIED"),
        ("readiness","current_mc_authority_count",0,"CURRENT_C417_PRIMARY_MC_MISSING"),
        ("readiness","ready_for_current_research_signal",False,"REAL_REGISTERED_RESEARCH_CANDIDATE_UNVERIFIED"),
        ("readiness","candidate_local_source_chain_attested",False,"CANDIDATE_LOCAL_SOURCE_CHAIN_UNVERIFIED"),
        ("sources","source_integrity_pass",False,"MASTER_PRICE_RESOLVER_SHA_PARTITION_UNPROVEN"),
        ("sources","candidate_local_source_preconditions_proven",False,"PREOPEN_LOCAL_SOURCE_PRECONDITIONS_UNVERIFIED"),
        ("terminal","asof_et","2026-10-07","CURRENT_ASOF_EXACT_SET_NOT_PROVEN"),
    ):
        allx={"root":deepcopy(root),"readiness":deepcopy(rd),"sources":deepcopy(src),"terminal":deepcopy(terminal)}
        allx[obj][k]=v
        result=evaluate(now,**allx)
        assert result["status"]=="BLOCKED_NO_GO" and reason in result["blockers"],(obj,k,reason)
        assert result["registered_research_candidate_prepared"] is False
    print("XRAY_OPENING_RESEARCH_GATE_SELFTEST=PASS_POSITIVE_10_NEGATIVE_NO_DEVICE_OR_TRADE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    import e2e_production_readiness as e2e
    import research_preopen_source_audit as source
    root=json.loads((ROOT/"orchestrator_state.json").read_text())
    terminal=json.loads((ROOT/"canonical_current_terminal.json").read_text())
    rd=e2e.snapshot()
    src=source.inspect(
        source.load("canonical_current_master_manifest.json"),
        source.load("canonical_current_price_dv30.json"),
        source.load("canonical_current_resolver_request.json"),
        terminal,rd,
        e2e.sha("canonical_current_master_manifest.json"),
        e2e.sha("canonical_current_price_dv30.json"))
    report=evaluate(dt.datetime.now(UTC),root,rd,src,terminal)
    if args.output:
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_OPENING_RESEARCH_GATE="+report["status"])
    print("XRAY_OPENING_GATE_BLOCKERS="+json.dumps(report["blockers"]))
    print("XRAY_OPENING_DEVICE_RECEIPT=UNPROVEN")
if __name__=="__main__":main()
