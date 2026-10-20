#!/usr/bin/env python3
"""Hard-lock preference: ChatGPT only; GitHub stays a silent evidence store.

This does not send a push, certify device receipt, or grant R92/alpha.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/"notification_channel_policy_v1.json"
WORKFLOW=ROOT.parent/".github/workflows/nasdaq-xray-delivery.yml"
SCHEMA="XRAY_NOTIFICATION_CHANNEL_POLICY_V1"
CANONICAL="6a825366222081918997094d76e6ae46"


def verify(p, workflow):
    if not isinstance(p,dict) or not isinstance(workflow,str):
        raise ValueError("INVALID_PREFERENCE_INPUT")
    if (p.get("schema")!=SCHEMA or p.get("user_preference")!="CHATGPT_ONLY"
        or p.get("user_delivery_authority_task_id")!=CANONICAL
        or p.get("github_issue_creation_enabled") is not False
        or p.get("github_issue_notifications_desired") is not False
        or p.get("github_actions_audit_evidence_enabled") is not True
        or p.get("platform_iphone_receipt_attested") is not False
        or p.get("registered_r92_required") is not True
        or p.get("dedup_required") is not True
        or p.get("never_emit_unregistered_candidate") is not True
        or p.get("no_synthetic_user_notification") is not True
        or p.get("unknown_never_pass") is not True
        or p.get("execution")!="NONE" or p.get("real_money")!="NO-GO"):
        raise ValueError("CHATGPT_ONLY_POLICY_MISMATCH")
    follow=p.get("registered_r92_lifecycle_followup_policy")
    allowed={"ENTRY_ZONE_APPROACHING","ENTRY_ZONE_TOUCHED",
             "ENTRY_ZONE_LEFT_ABOVE","TARGET_LEVEL_TOUCHED",
             "STOP_LEVEL_TOUCHED","INVALIDATED","EXPIRED",
             "OFFICIAL_HALT","EVENT_VETO","AMBIGUOUS_INTRABAR_ORDER"}
    if (p.get("user_visible_event_scope") !=
        "VERIFIED_REGISTERED_R92_BUY_OR_PRIOR_REGISTERED_MATERIAL_LIFECYCLE_ONLY"
        or not isinstance(follow,dict)
        or follow.get("schema")!="XRAY_VERIFIED_R92_LIFECYCLE_FOLLOWUP_POLICY_V1"
        or follow.get("enabled") is not True
        or set(follow.get("allowed_material_states") or [])!=allowed
        or len(follow.get("allowed_material_states") or [])!=len(allowed)
        or follow.get("scope")!="ONLY_PREVIOUSLY_VERIFIED_AND_REGISTERED_R92"
        or any(follow.get(k) is not True for k in (
            "requires_candidate_r92_current_or_exact_immutable_origin",
            "requires_material_transition_proven",
            "requires_independent_authoritative_timestamped_data",
            "requires_preserved_r92_entry_stop_target_levels",
            "requires_durable_exact_dedup",
            "requires_write_readback_before_notification_attempt",
            "requires_original_r92_key_and_source_asof",
            "source_stale_or_unknown_no_user_alert",
            "watch_early_or_prescreen_no_user_alert",
            "never_claim_trade_fill_or_profit",
            "never_claim_platform_receipt_without_ack",
            "no_new_task_or_channel","no_broker_or_orders",
            "unknown_never_pass"))
        or follow.get("execution")!="NONE"
        or follow.get("real_money")!="NO-GO"):
        raise ValueError("VERIFIED_R92_FOLLOWUP_POLICY_MISSING_OR_WEAKENED")
    must=[
        "issues: read",
        "if: steps.prep.outputs.ready == 'true' && false",
        "Classify registered R92 presence without claiming source readiness",
        "Reject stale latest completed Nasdaq source before R92 delivery",
        "Refresh official Nasdaq halt + Security Status guard",
        "SUPPRESSED_CHATGPT_ONLY",
        "XRAY_DELIVERY_USER_DEVICE_RECEIPT=UNVERIFIED",
    ]
    if any(s not in workflow for s in must) or "issues: write" in workflow:
        raise ValueError("GITHUB_ISSUE_DELIVERY_NOT_DISABLED")
    if workflow.count("gh issue create")!=1:
        raise ValueError("LEGACY_GITHUB_ISSUE_SINK_DRIFT")
    return {"schema":SCHEMA,"user_channel":"CHATGPT_ONLY",
            "github_issue_creation_enabled":False,
            "phone_receipt_attested":False,
            "no_new_r92_created":True,
            "execution":"NONE","real_money":"NO-GO"}


def selftest():
    p=json.loads(CONFIG.read_text())
    wf=WORKFLOW.read_text()
    out=verify(p,wf)
    assert out["github_issue_creation_enabled"] is False
    cases=[
        ({**p,"user_preference":"BOTH"},wf),
        ({**p,"github_issue_creation_enabled":True},wf),
        ({**p,"github_issue_notifications_desired":True},wf),
        ({**p,"platform_iphone_receipt_attested":True},wf),
        ({**p,"dedup_required":False},wf),
        ({**p,"registered_r92_required":False},wf),
        ({**p,"execution":"ORDER"},wf),
        ({**p,"unknown_never_pass":False},wf),
        (p,wf.replace("issues: read","issues: write")),
        (p,wf.replace("if: steps.prep.outputs.ready == 'true' && false",
                       "if: steps.prep.outputs.ready == 'true'")),
        (p,wf.replace("SUPPRESSED_CHATGPT_ONLY","MISSING_RETRY_REQUIRED")),
        ({**p,"registered_r92_lifecycle_followup_policy":{
            **p["registered_r92_lifecycle_followup_policy"],
            "requires_independent_authoritative_timestamped_data":False}},wf),
        ({**p,"registered_r92_lifecycle_followup_policy":{
            **p["registered_r92_lifecycle_followup_policy"],
            "requires_durable_exact_dedup":False}},wf),
        ({**p,"registered_r92_lifecycle_followup_policy":{
            **p["registered_r92_lifecycle_followup_policy"],
            "allowed_material_states":["SOURCE_STALE"]}},wf),
        ({**p,"user_visible_event_scope":"ANY_WATCH_OR_BUY"},wf),
    ]
    for altered,flow in cases:
        try:verify(altered,flow)
        except ValueError:continue
        raise AssertionError("CHATGPT_ONLY_NEGATIVE_BYPASS")
    print("XRAY_CHATGPT_ONLY_DELIVERY_SELFTEST=PASS_1_POSITIVE_15_NEGATIVES")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    if args.selftest:
        selftest()
    elif args.check:
        result=verify(json.loads(CONFIG.read_text()),WORKFLOW.read_text())
        print("XRAY_USER_NOTIFICATION_CHANNEL=CHATGPT_ONLY")
        print("XRAY_GITHUB_ISSUE_CREATION=DISABLED")
        print("XRAY_CHATGPT_PHONE_RECEIPT=UNVERIFIED")
        print("XRAY_NOTIFICATION_GUARD="+json.dumps(result,sort_keys=True))
    else:parser.error("--selftest or --check required")

if __name__=="__main__":main()
