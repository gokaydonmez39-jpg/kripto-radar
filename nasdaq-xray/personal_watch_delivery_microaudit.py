#!/usr/bin/env python3
"""Live personal XRAY WATCH / AL / notification observability micro-audit.

Every conclusion is based on actual repo bytes (plus exchange-session calendar).
This cannot query ChatGPT task settings or prove an iPhone push receipt: those
are a different platform. It never sends a notification, creates a candidate,
promotes SIP research to C4.17 primary evidence, or accesses a broker.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha1, sha256
import json
from pathlib import Path

from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_WATCH_NOTIFICATION_MICROAUDIT_V1"
TASK="6a825366222081918997094d76e6ae46"
WATCH_SCHEMA="XRAY_MINIMAL_SWING_WATCH_RADAR_V1"
TECH_SCHEMA="XRAY_ALL_CANDIDATES_C417_TECHNICAL_FUNNEL_V1"
AL_SCHEMA="XRAY_RESEARCH_CANDIDATE_R92_V1"


def blob(raw):
    return sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def emit(docs,shas,session):
    issues=[]
    def issue(code,why,next_action):
        issues.append({"code":code,"evidence":why,"repair_key":next_action})
    root=docs["orchestrator_state.json"]
    sina=docs["sina_candidates.json"]
    snap=docs["personal_swing_radar_current.json"]
    master=docs["canonical_current_master_manifest.json"]
    terminal=docs["canonical_current_terminal.json"]
    pointer=docs["chatgpt_canonical_state_v2.json"]
    notification=docs["notification_channel_policy_v1.json"]
    ledger=docs["delivery_ledger.json"]
    watch=root.get("watch_radar") or {}
    tech=root.get("candidate_technical_funnel") or {}
    state=pointer.get("state_json") or {}
    watchlist=watch.get("watchlist")
    technical_watch=tech.get("preliminary_technical_watch_symbols")
    if not isinstance(watchlist,list):watchlist=[]
    if not isinstance(technical_watch,list):technical_watch=[]
    reported=dict(sorted({k:v.get("asof_et")
        for k,v in [("root",root),("sina",sina),("watch",watch),
                   ("technical",tech),("personal_snapshot",snap),
                   ("master",master),("terminal",terminal),
                   ("pointer",state)]}.items()))
    if root.get("asof_et")!=session:
        issue("ROOT_NOT_LATEST_COMPLETED_SESSION",
              str(root.get("asof_et"))+" != "+session,
              "RECHECK_OFFICIAL_COMPLETED_SESSION_BEFORE_WATCH")
    if sina.get("asof_et")!=root.get("asof_et") or watch.get("asof_et")!=root.get("asof_et"):
        issue("SINA_WATCH_EPOCH_MISMATCH",
              "Source and root WATCH must refer to exact same completed session",
              "REBUILD_SINA_WATCH_WITH_CURRENT_ROOT_ASOF")
    if not (root.get("execution")=="NONE" and root.get("real_money")=="NO-GO"
            and sina.get("execution")=="NONE" and sina.get("real_money")=="NO-GO"
            and terminal.get("execution")=="NONE"
            and terminal.get("real_money")=="NO-GO"):
        issue("SAFETY_CONTRACT_BROKEN","Execution/real-money guard mismatch",
              "STOP_ALL_NOTIFICATION_AND_SIGNAL_RELEASE")
    if root.get("status")!="HISTORY_COMPLETE" or int(root.get("unknown_count") or 0):
        issue("ROOT_UPSTREAM_HISTORY_PARTIAL",
              "status="+str(root.get("status"))+" unknown="+str(root.get("unknown_count")),
              "CONTINUE_PROVEN_SIP_HISTORY_AND_CAUSAL_SOURCE_RECONCILIATION")
    count=sina.get("candidate_count")
    rows=sina.get("candidates")
    if (sina.get("schema")!="XRAY_SINA_CANDIDATES_V2"
        or not isinstance(rows,dict) or count!=len(rows)):
        issue("SOURCE_CANDIDATE_PARTITION_INVALID","Sina candidate count != exact map",
              "REPAIR_SOURCE_CANDIDATE_SCHEMA_BEFORE_WATCH")
    elif count==0:
        issue("NO_CANONICAL_SOURCE_CANDIDATES",
              "Latest source candidate_count=0; not proof that the market has no setups",
              "QUALIFY_INDEPENDENT_SIP_TECHNICAL_WATCH_WITHOUT_FALSE_SINA_BRIDGE")
    source_sha=sha256(shas["sina_candidates.json"]["raw"]).hexdigest()
    if (watch.get("schema")!=WATCH_SCHEMA
        or watch.get("source_candidates_sha256")!=source_sha
        or watch.get("watchlist_cap") is not None
        or watch.get("all_eligible_candidates_tracked") is not True
        or watch.get("watchlist_count")!=len(watchlist)
        or watch.get("price_liquidity_screened_count")!=len(watchlist)):
        issue("WATCH_PARTITION_OR_SOURCE_SHA_INVALID",
              "WATCH must be untruncated and exact-bound to source candidate bytes",
              "RECOMPUTE_FULL_WATCHLIST_WITH_EXACT_SOURCE_SHA")
    if watch.get("watchlist_count")==0:
        issue("NO_EVIDENCE_BACKED_WATCH_ROWS",
              "zero current WATCH rows, even if independent SIP liquidity census is nonzero",
              "RUN_ASOF_BOUND_A_B_D_PREBREAKOUT_OBSERVER_ON_QUALIFIED_SOURCE")
    if (tech.get("schema")!=TECH_SCHEMA
        or tech.get("asof_et")!=root.get("asof_et")
        or tech.get("preliminary_technical_watch_count")!=len(technical_watch)):
        issue("TECH_WATCH_COUNT_OR_ASOF_INVALID",
              "Technical observation count, symbols, schema, or ASOF inconsistent",
              "REBUILD_EXACT_SOURCE_TECHNICAL_FUNNEL")
    if not technical_watch:
        issue("NO_VERIFIED_TECHNICAL_WATCH",
              "No A/B/D source-bound preliminary technical WATCH was observed",
              "ASSESS_EARLY_B_BASE_PIVOT_A_D_WITH_FRESH_RTH_AND_R1_PROOF")
    # Current personal snapshot may contain real research counts, but cannot
    # legitimately become current WATCH without exact latest ASOF + three SHAs.
    p=snap.get("asof_proof") or {}
    snap_ok=bool(snap.get("schema")=="XRAY_PERSONAL_SWING_RADAR_DAILY_SNAPSHOT_V1"
                 and snap.get("asof_et")==session
                 and p.get("orchestrator_blob_sha")==shas["orchestrator_state.json"]["sha"]
                 and p.get("master_blob_sha")==shas["canonical_current_master_manifest.json"]["sha"]
                 and p.get("canonical_price_blob_sha")==shas["canonical_current_price_dv30.json"]["sha"]
                 and snap.get("safety",{}).get("execution")=="NONE"
                 and snap.get("registered_R92_signal_count")==0)
    if not snap_ok:
        issue("PERSONAL_SNAPSHOT_STALE_OR_SHA_DRIFT",
              "ASOF and source blob proofs not simultaneously current",
              "REGENERATE_SNAPSHOT_FROM_EXACT_CURRENT_OR_REPORT_UNAVAILABLE")
    if master.get("asof_et")!=session or terminal.get("asof_et")!=session:
        issue("CANONICAL_TERMINAL_EPOCH_BEHIND",
              "master="+str(master.get("asof_et"))+
              " terminal="+str(terminal.get("asof_et")),
              "RESTORE_CANONICAL_C417_EPOCH_CHAIN_WITHOUT_SHADOW_PROMOTION")
    if state.get("asof_et")!=session:
        issue("CANONICAL_POINTER_EPOCH_BEHIND",
              "pointer_asof="+str(state.get("asof_et")),
              "RECONCILE_POINTER_ONLY_AFTER_EXACT_TERMINAL_AND_R92_PROOF")
    registered=state.get("r92")
    registered_count=len(registered) if isinstance(registered,list) else None
    if registered_count != 0:
        # Do not infer the user's device received a registered item!
        issue("R92_REGISTRY_REQUIRES_INDEPENDENT_VALIDATION",
              "Pointer contains candidate records but this audit does not authorize their release",
              "CHECK_C417_SIGNED_TERMINAL_AND_DELIVERY_RECEIPT")
    else:
        issue("NO_REGISTERED_R92",
              "Current canonical pointer has no registered AL/R92",
              "KEEP_NO_AL_UNTIL_ALL_SIX_PRIMARY_GATES_PASS")
    deliveries=ledger.get("deliveries")
    if not isinstance(deliveries,dict):deliveries={}
    conf=bool(notification.get("schema")=="XRAY_NOTIFICATION_CHANNEL_POLICY_V1"
              and notification.get("user_preference")=="CHATGPT_ONLY"
              and notification.get("user_delivery_authority_task_id")==TASK
              and notification.get("github_issue_creation_enabled") is False)
    if not conf:
        issue("CHANNEL_POLICY_CONFLICT","ChatGPT-only safety channel config mismatch",
              "RESTORE_SINGLE_CANONICAL_TASK_CHANNEL_AND_NO_GITHUB_ISSUES")
    if not deliveries:
        issue("NO_DELIVERY_LEDGER_RECEIPTS","Delivery ledger is empty",
              "DO_NOT_CLAIM_PUSH_DELIVERY_WITHOUT_PLATFORM_RECEIPT")
    issue("CHATGPT_PHONE_ACK_NOT_OBSERVABLE_FROM_GITHUB",
          "GitHub success or ChatGPT task configuration cannot prove an iPhone push",
          "VERIFY_TASK_DELIVERY_WITH_PLATFORM_ACK_SEPARATELY")
    event=(
        "NO_CURRENT_TECHNICAL_WATCH_AND_NO_R92"
        if not technical_watch and not registered_count
        else "UNRELEASED_RESEARCH_TECHNICAL_WATCH"
        if technical_watch else "REGISTERED_R92_REQUIRES_PRIMARY_CHECK")
    return {
        "schema":SCHEMA,"expected_last_completed_nasdaq_session":session,
        "asof_by_source":reported,
        "full_root_queue_total":root.get("queue_total"),
        "root_history_unknown_count":root.get("unknown_count"),
        "root_source_candidate_count":count,
        "current_price_liquidity_prescreen_watch_count":len(watchlist),
        "claimed_technical_watch_count":len(technical_watch),
        "current_personal_snapshot_exact_epoch_sha_verified":snap_ok,
        "canonical_pointer_r92_count":registered_count,
        "github_delivery_ledger_record_count":len(deliveries),
        "notification_channel_preference":"CHATGPT_ONLY" if conf else "UNKNOWN_CONFLICT",
        "chatgpt_task_state_independently_attested_by_this_run":False,
        "iphone_push_ack_independently_attested_by_this_run":False,
        "delivery_workflow_is_not_an_iphone_push_channel":True,
        "research_liquidity_is_not_a_rising_stock_prediction":True,
        "distinct_alert_classes":["IZLE_EARLY_TECHNICAL_RESEARCH_NOT_AL",
                                  "WATCH_PREENTRY_SOURCE_PROVEN_NOT_AL",
                                  "AL_ONLY_REGISTERED_R92_ALL_PRIMARY_GATES"],
        "current_release_status":event,
        "blocker_count":len(issues),
        "repair_order":issues,
        "execution":"NONE","real_money":"NO-GO",
        "orders":[],"new_r92":[],"user_notification_sent":False,
        "status":"MICROAUDIT_COMPLETE_STATUS_NOT_NOTIFICATION_OR_ALPHA",
    }


def test():
    d="2026-10-14"
    a=lambda x:{"asof_et":x,"execution":"NONE","real_money":"NO-GO"}
    sina=dict(a(d),schema="XRAY_SINA_CANDIDATES_V2",candidate_count=0,
              candidates={})
    raw=(json.dumps(sina)+"\n").encode()
    root=dict(a(d),status="PARTIAL_HISTORY",unknown_count=4,queue_total=10)
    root["watch_radar"]={"schema":WATCH_SCHEMA,"asof_et":d,
        "watchlist":[],"watchlist_count":0,"price_liquidity_screened_count":0,
        "watchlist_cap":None,"all_eligible_candidates_tracked":True,
        "source_candidates_sha256":sha256(raw).hexdigest()}
    root["candidate_technical_funnel"]={"schema":TECH_SCHEMA,"asof_et":d,
        "preliminary_technical_watch_count":0,
        "preliminary_technical_watch_symbols":[]}
    paths={
        "orchestrator_state.json":root,
        "sina_candidates.json":sina,
        "personal_swing_radar_current.json":{
            **a("2026-10-13"),"schema":"XRAY_PERSONAL_SWING_RADAR_DAILY_SNAPSHOT_V1",
            "asof_proof":{},"registered_R92_signal_count":0},
        "canonical_current_master_manifest.json":a("2026-10-13"),
        "canonical_current_price_dv30.json":a("2026-10-13"),
        "canonical_current_terminal.json":a("2026-10-07"),
        "chatgpt_canonical_state_v2.json":{"state_json":{"asof_et":"2026-10-07","r92":[]}},
        "notification_channel_policy_v1.json":{
            "schema":"XRAY_NOTIFICATION_CHANNEL_POLICY_V1",
            "user_preference":"CHATGPT_ONLY",
            "user_delivery_authority_task_id":TASK,
            "github_issue_creation_enabled":False},
        "delivery_ledger.json":{"deliveries":{}},
    }
    shas={p:{"raw":json.dumps(obj).encode(),"sha":blob(json.dumps(obj).encode())}
          for p,obj in paths.items()}
    shas["sina_candidates.json"]={"raw":raw,"sha":blob(raw)}
    good=emit(paths,shas,d)
    codes={x["code"] for x in good["repair_order"]}
    def prove(ok,code):
        if not ok:raise AssertionError("XRAY_WATCH_MICROAUDIT_TEST_"+code)
    prove({"NO_CANONICAL_SOURCE_CANDIDATES","NO_EVIDENCE_BACKED_WATCH_ROWS",
           "NO_VERIFIED_TECHNICAL_WATCH","CANONICAL_TERMINAL_EPOCH_BEHIND",
           "PERSONAL_SNAPSHOT_STALE_OR_SHA_DRIFT",
           "NO_REGISTERED_R92","NO_DELIVERY_LEDGER_RECEIPTS",
           "CHATGPT_PHONE_ACK_NOT_OBSERVABLE_FROM_GITHUB"}.issubset(codes),
          "BLOCKER_CAUSAL_COVERAGE")
    prove(good["current_release_status"]==
          "NO_CURRENT_TECHNICAL_WATCH_AND_NO_R92","NO_TECH_WATCH_NO_AL")
    prove(not good["user_notification_sent"] and
          not good["iphone_push_ack_independently_attested_by_this_run"],
          "NO_FALSE_DEVICE_RECEIPT")
    # A WATCH observation is distinct from BUY/R92 and cannot prove delivery.
    paths["orchestrator_state.json"]["candidate_technical_funnel"].update(
        preliminary_technical_watch_count=1,
        preliminary_technical_watch_symbols=["AAPL"])
    observed=emit(paths,shas,d)
    prove(observed["claimed_technical_watch_count"]==1,
          "PRE_AL_WATCH_COUNT_NOT_SUPPRESSED")
    prove(observed["current_release_status"]==
          "UNRELEASED_RESEARCH_TECHNICAL_WATCH",
          "WATCH_CLASS_SEPARATE_FROM_R92")
    prove(observed["canonical_pointer_r92_count"]==0 and
          not observed["user_notification_sent"],
          "WATCH_NEVER_CLAIMS_AL_OR_PLATFORM_SEND")
    # A fake phone-receipt boolean in repository policy is never accepted.
    paths["notification_channel_policy_v1.json"]["platform_iphone_receipt_attested"]=True
    false_receipt=emit(paths,shas,d)
    prove(not false_receipt["iphone_push_ack_independently_attested_by_this_run"],
          "FORGED_REPO_PLATFORM_ACK_REJECTED")
    print("XRAY_WATCH_DELIVERY_MICROAUDIT_SELFTEST=PASS_EPOCH_ISSUE_GUARDS_WATCH_VS_R92_NO_PUSH_CLAIM")


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--selftest",action="store_true")
    cli.add_argument("--out",type=Path)
    args=cli.parse_args()
    if args.selftest:test();return
    if args.out is None:cli.error("--out required")
    names=["orchestrator_state.json","sina_candidates.json",
           "personal_swing_radar_current.json",
           "canonical_current_master_manifest.json",
           "canonical_current_price_dv30.json",
           "canonical_current_terminal.json",
           "chatgpt_canonical_state_v2.json",
           "notification_channel_policy_v1.json","delivery_ledger.json"]
    data={n:(ROOT/n).read_bytes() for n in names}
    obj={n:json.loads(t) for n,t in data.items()}
    sha={n:{"raw":t,"sha":blob(t)} for n,t in data.items()}
    current=last_complete_session(datetime.now(timezone.utc))
    report=emit(obj,sha,current)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("XRAY_WATCH_DELIVERY_MICROAUDIT="+json.dumps({
        "root_asof":report["asof_by_source"]["root"],
        "target_asof":current,"watched":report["current_price_liquidity_prescreen_watch_count"],
        "technical_watch":report["claimed_technical_watch_count"],
        "R92":report["canonical_pointer_r92_count"],
        "issue_count":report["blocker_count"],
        "release_status":report["current_release_status"],
        "device_ack":False},sort_keys=True))


if __name__=="__main__":main()
