#!/usr/bin/env python3
"""Fail-closed ChatGPT Health prompt/runtime attestation sanity checker.

The GitHub repo cannot directly inspect ChatGPT automation prompts. This
checks a deliberately MANUAL, dated connected-task witness against a current
strict Nasdaq market-session recovery contract. CI PASS proves that missing
runtime proof is BLOCKED; it never proves the ChatGPT task obeyed a holiday.
No Github/ChatGPT task writes, no secret, price, AL or market data.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
WITNESS=ROOT/"health_chatgpt_runtime_attestation_20261013.json"
CONTRACT=ROOT/"scheduler_failover_contract.json"
APPEND_BLOCK=ROOT/"health_chatgpt_prompt_append_v21.txt"
TASK_ID="6abd0465d15c8191aac5888abb784f27"
SENTINEL="HEALTH_NASDAQ_EXCHANGE_CAS_V21=BOUND"
SCHEMA="XRAY_CHATGPT_HEALTH_RUNTIME_TASK_ATTESTATION_V1"
EXPECTED="HEALTH_TASK_PROMPT_HOLIDAY_VETO_DRIFT_UNVERIFIED"

def need(pred,code):
    if not pred:raise ValueError("HEALTH_RUNTIME_ATTESTATION_"+code)

def validate_append(text):
    need(isinstance(text,str) and text.startswith("HEALTH_NASDAQ_EXCHANGE_CAS_V21=BOUND\\n".replace("\\\\n","\\n")),
         "APPEND_HEAD_MISSING")
    need(text.count("HEALTH_NASDAQ_EXCHANGE_CAS_V21=BOUND")==1,
         "APPEND_DUPLICATE")
    need(text.rstrip().endswith("END_HEALTH_NASDAQ_EXCHANGE_CAS_V21"),
         "APPEND_FOOTER_MISSING")
    required=(
      "SCOPE=","PRECEDENCE=","TIME_AUTHORITY=","CALENDAR_AUTHORITY=",
      "ROOT_CAS_VETO=","EARLY_CLOSE=","CALENDAR_UNAVAILABLE=",
      "VALID_ROOT_ACTION=","FINAL_KICK=","PROMPT_DRIFT_HEALTH=",
      "NO_ALPHA_PROMOTION=true","NO_PAID_FALLBACK=true",
      "NO_BROKER_OR_ORDER_ACTION=true","EXECUTION=NONE",
      "REAL_MONEY=NO-GO","UNKNOWN_NEVER_PASS=true",
    )
    lines=text.splitlines()
    for marker in required:
        need(any(line.startswith(marker) for line in lines),
             "APPEND_REQUIRED_LINE_MISSING_"+marker[:25])
    need('permit_compute(now_utc,"schedule")' in text,
         "APPEND_MISSING_OFFICIAL_SESSION_PREDICATE")
    need("DO NOT update scheduler_kick_dataplane.json" in text,
         "APPEND_HOLIDAY_HARD_VETO_MISSING")
    need("Preserve every existing prompt byte" in text,
         "APPEND_FULL_PROMPT_PRESERVATION_REQUIRED")


def validate(att,contract):
    need(type(att) is dict and type(contract) is dict,"OBJECTS_REQUIRED")
    need(att.get("schema")==SCHEMA,"WITNESS_SCHEMA")
    need(contract.get("schema")=="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1",
         "CONTRACT_SCHEMA")
    for obj,kind in ((att,"WITNESS"),(contract,"CONTRACT")):
        need(obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO",
             kind+"_MONEY_EXECUTION_SAFETY")
    need(att.get("unknown_never_pass") is True and
         contract.get("unknown_never_pass") is True,"UNKNOWN_POLICY")
    need(att.get("policy")=="C4.17" and att.get("control")=="C4.27",
         "POLICY_CONTROL")
    need(att.get("task_id")==TASK_ID and
         att.get("task_title")=="XRAY Health + G9 Multi-Watch",
         "TASK_IDENTITY")
    need(att.get("attestation_type")==
         "MANUAL_CONNECTED_TASK_METADATA_OBSERVATION_NOT_RUNTIME_PROOF",
         "NOT_CONNECTED_OBSERVATION")
    need(att.get("provider")=="CHATGPT_AUTOMATIONS","PROVIDER")
    need(att.get("expected_schedule")==(
         "BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261002T064900\n"
         "RRULE:FREQ=HOURLY;BYMINUTE=49;BYSECOND=0\nEND:VEVENT"),
         "SCHEDULE_DRIFT")
    need(att.get("enabled_xray_task_count_observed")==5 and
         att.get("is_enabled_observed") is True,
         "FIVE_TASK_TOPOLOGY")
    need(att.get("notifications_enabled_observed") is False and
         att.get("email_enabled_observed") is False,
         "SILENT_SUPPORT_TOPOLOGY")
    need(att.get("prompt_contains_legacy_v12") is True and
         att.get("prompt_contains_legacy_v11") is True and
         att.get("prompt_contains_health_root_weekday_only") is True,
         "PREIMAGE_EVIDENCE_INCOMPLETE")
    need(att.get("holiday_veto_required_sentinel")==SENTINEL and
         att.get("prompt_contains_explicit_nasdaq_holiday_cas_veto") is False and
         att.get("prompt_contains_holiday_veto_sentinel") is False,
         "FALSE_HOLIDAY_PROMPT_CLAIM")
    need(att.get("classification")==EXPECTED and
         att.get("runtime_task_prompt_guard_current") is False,
         "FORGED_PROMPT_RUNTIME_PASS")
    need(att.get("actual_holiday_health_invocation_observed") is False and
         att.get("actual_holiday_cas_suppression_observed") is False and
         att.get("operational_health_runtime_pass") is False,
         "FORGED_HOLIDAY_EXECUTION_PASS")
    need(att.get("raw_task_prompt_or_secrets_stored") is False and
         att.get("repo_workflow_success_not_chatgpt_automation_success") is True and
         att.get("no_automation_mutated_by_this_attestation") is True,
         "EVIDENCE_CONFIDENTIALITY_OR_SCOPE")
    for flag in ("root_production_readiness_released",
                 "alpha_authority","primary_price_pass_created",
                 "primary_mc_created","r92_created"):
        need(att.get(flag) is False, "PRODUCTION_PROMOTION_"+flag)
    policy=contract.get("health_policy")
    need(type(policy) is dict,"CONTRACT_HEALTH_POLICY")
    for flag in ("nasdaq_exchange_session_required_for_root_kick",
                 "exchange_closed_weekday_kick_forbidden"):
        need(policy.get(flag) is True,"EXCHANGE_GUARD_"+flag)
    need(policy.get("exchange_calendar_failure")=="BLOCK_CAS_FAIL_CLOSED",
         "EXCHANGE_CALENDAR_OUTAGE")
    need(policy.get("exchange_calendar_authority")==
         "ROOT_WEEKEND_QUOTA_GUARD_PERMIT_COMPUTE_SCHEDULE",
         "CALENDAR_AUTHORITY")
    need(att.get("github_contract_authority")==
         "nasdaq-xray/scheduler_failover_contract.json",
         "CONTRACT_PATH")
    need(att.get("github_contract_asof_observation_blob_sha")==
         "3c6a70adb8c233275220fb34cf1e2dde9230eaf0",
         "CONTRACT_PREIMAGE_SHA")
    need(att.get("github_contract_official_session_required") is True and
         att.get("github_root_guard_official_calendar_ci_tested") is True,
         "SOURCE_CI_LIMIT")
    try:
        stamp=dt.datetime.fromisoformat(str(att.get("observed_at_utc")).replace("Z","+00:00"))
    except (ValueError,TypeError) as exc:
        raise ValueError("HEALTH_RUNTIME_ATTESTATION_BAD_OBSERVED_AT") from exc
    need(stamp.tzinfo is not None,"NAIVE_WITNESS_TIME")
    need(stamp.astimezone(ZoneInfo("America/New_York")).date()==
         dt.date(2026,10,13),"OBSERVATION_DAY")
    return {
      "status":"BLOCKED_CHATGPT_HEALTH_HOLIDAY_PROMPT_DRIFT",
      "evidence_kind":"DATED_MANUAL_TASK_METADATA_OBSERVATION_ONLY",
      "task_id":TASK_ID,
      "task_prompt_holiday_gate_verified":False,
      "github_calendar_guard_tested":True,
      "chatgpt_runtime_cas_behavior_verified":False,
      "five_enabled_tasks_preserved":True,
      "no_new_automation":True,
      "alpha_authority":False,
      "r92_created":False,
      "execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True,
      "ci_success_not_runtime_recovery":True,
    }

def selftest(att,contract):
    block=APPEND_BLOCK.read_text()
    validate_append(block)
    broken=(
      block.replace("ROOT_CAS_VETO=","UNSAFE_ROOT_CAS_VETO="),
      block.replace("permit_compute(now_utc,\\\"schedule\\\")","WEEKDAY_ONLY"),
      block.replace("DO NOT update scheduler_kick_dataplane.json","MAY update scheduler_kick_dataplane.json"),
      block.replace("Preserve every existing prompt byte","Replace with a shorter prompt"),
      block.replace("EXECUTION=NONE","EXECUTION=TRADE"),
      block.replace("REAL_MONEY=NO-GO","REAL_MONEY=GO"),
      block.replace("UNKNOWN_NEVER_PASS=true","UNKNOWN_NEVER_PASS=false"),
      block.replace("END_HEALTH_NASDAQ_EXCHANGE_CAS_V21","END_UNSAFE_GUARD"),
      block+"HEALTH_NASDAQ_EXCHANGE_CAS_V21=BOUND\\n",
      block.replace("NO_ALPHA_PROMOTION=true","NO_ALPHA_PROMOTION=false"),
    )
    for i,txt in enumerate(broken):
        try:validate_append(txt)
        except ValueError:pass
        else:raise AssertionError("UNSAFE_APPEND_PATCH_ACCEPTED_"+str(i))
    pass_state=validate(att,contract)
    need(pass_state["status"]=="BLOCKED_CHATGPT_HEALTH_HOLIDAY_PROMPT_DRIFT",
         "INCORRECT_CLOSED_STATUS")
    checks={
      "task_id":("bad","TASK_IDENTITY"),
      "enabled_xray_task_count_observed":(6,"FIVE_TASK_TOPOLOGY"),
      "is_enabled_observed":(False,"FIVE_TASK_TOPOLOGY"),
      "notifications_enabled_observed":(True,"SILENT_SUPPORT_TOPOLOGY"),
      "prompt_contains_holiday_veto_sentinel":(True,"FALSE_HOLIDAY_PROMPT_CLAIM"),
      "prompt_contains_explicit_nasdaq_holiday_cas_veto":(True,"FALSE_HOLIDAY_PROMPT_CLAIM"),
      "runtime_task_prompt_guard_current":(True,"FORGED_PROMPT_RUNTIME_PASS"),
      "actual_holiday_cas_suppression_observed":(True,"FORGED_HOLIDAY_EXECUTION_PASS"),
      "operational_health_runtime_pass":(True,"FORGED_HOLIDAY_EXECUTION_PASS"),
      "classification":("PASS","FORGED_PROMPT_RUNTIME_PASS"),
      "alpha_authority":(True,"PRODUCTION_PROMOTION"),
      "r92_created":(True,"PRODUCTION_PROMOTION"),
      "real_money":("GO","WITNESS_MONEY_EXECUTION_SAFETY"),
      "unknown_never_pass":(False,"UNKNOWN_POLICY"),
      "raw_task_prompt_or_secrets_stored":(True,"EVIDENCE_CONFIDENTIALITY_OR_SCOPE"),
      "holiday_veto_required_sentinel":("OLD","FALSE_HOLIDAY_PROMPT_CLAIM"),
      "expected_schedule":("DTSTART:20261014T060000","SCHEDULE_DRIFT"),
      "observed_at_utc":("invalid","BAD_OBSERVED_AT"),
    }
    for key,(bad,err) in checks.items():
        tampered=copy.deepcopy(att);tampered[key]=bad
        try:validate(tampered,contract)
        except ValueError as exc:
            need(err in str(exc),"WRONG_ERROR_"+key)
        else:raise AssertionError("HEALTH_FAILOPEN_WITNESS_MUTATION_"+key)
    for key,bad in (
        ("nasdaq_exchange_session_required_for_root_kick",False),
        ("exchange_closed_weekday_kick_forbidden",False),
        ("exchange_calendar_failure","ALLOW"),
        ("exchange_calendar_authority","ET_WEEKDAY_ONLY"),
    ):
        altered=copy.deepcopy(contract)
        altered["health_policy"][key]=bad
        try:validate(att,altered)
        except ValueError:pass
        else:raise AssertionError("HEALTH_FAILOPEN_CONTRACT_MUTATION_"+key)
    print("XRAY_CHATGPT_HEALTH_TASK_BINDING_GUARD=PASS_32_NEGATIVES_RUNTIME_STILL_BLOCKED")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    att=json.loads(WITNESS.read_text())
    contract=json.loads(CONTRACT.read_text())
    validate_append(APPEND_BLOCK.read_text())
    if args.selftest:selftest(att,contract)
    state=validate(att,contract)
    if args.out is not None:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(state,sort_keys=True,indent=2)+"\n")
    print("XRAY_CHATGPT_HEALTH_TASK_RUNTIME="+state["status"])
    print("XRAY_CHATGPT_HEALTH_NO_FALSE_AUTOMATION_PASS=PASS")

if __name__=="__main__":main()
