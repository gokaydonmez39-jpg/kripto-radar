#!/usr/bin/env python3
"""Read-only Monday XRAY launch contract audit, NOT an alpha or delivery gate.

Verifies safety topology and temporal regression boundaries. CI success proves
these code/config invariants, NOT provider rights, real candidates, device
receipt, or execution readiness. Never modifies canonical state.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
NY=ZoneInfo("America/New_York")
TR=ZoneInfo("Europe/Istanbul")
WF=ROOT/".github"/"workflows"
DATA=ROOT/"nasdaq-xray"
SCHEMA="XRAY_MONDAY_LAUNCH_STATIC_MICROAUDIT_V1"
REQUIRED={
    "nasdaq-xray-daily.yml":("30 * * * *",),
    "xray-canonical-current-pre-mc.yml":("35 5-23 * * 1-5","35 0-3 * * 2-6"),
    "xray-canonical-current-post-mc.yml":("50 5-23 * * 1-5","50 0-3 * * 2-6"),
    "xray-canonical-current-final.yml":("53 5-23 * * 1-5","53 0-3 * * 2-6"),
    "xray-github-native-root-watchdog.yml":("*/15 * * * 1-5",),
    "nasdaq-xray-delivery.yml":("*/15 * * * 1-5","7 * * * 0,6"),
    "xray-preopen-source-audit.yml":(
        "5 12 * * 1-5","25 12 * * 1-5","5 13 * * 1-5",
        "15 13 * * 1-5","15 14 * * 1-5"),
}
CHECKS={
    "root_weekend_guard":("nasdaq-xray-daily.yml",(
        "python nasdaq-xray/root_weekend_quota_guard.py --emit",
        "if: steps.session.outputs.allow_compute == 'true'",
        "python nasdaq-xray/orchestrator_run.py",
        "python nasdaq-xray/github_native_stage_relay.py --out",
    )),
    "watchdog_lease":("xray-github-native-root-watchdog.yml",(
        "github_native_root_watchdog.py --selftest",
        "github_native_root_watchdog.py --out",
        "github_native_chain_health.py --out",
    )),
    "delivery_requires_verified_registration":("nasdaq-xray-delivery.yml",(
        "delivery_candidate_preflight.py",
        "if: steps.presence.outputs.registered == 'true'",
        "if: steps.source_epoch.outputs.ready == 'true'",
        "if: steps.scheduler.outputs.ready == 'true'",
        "if: steps.prep.outputs.ready == 'true'",
        "if: always() && steps.prep.outputs.ready == 'true'",
        "XRAY_DELIVERY_NOOP=NO_REGISTERED_RESEARCH_CANDIDATE",
        "XRAY_DELIVERY_R92_PRESENT=true",
        "gh issue create",
        'gh issue view "$existing" --json number,title,body,url',
        "delivery_issue_receipt_guard.py",
        "XRAY_BACKUP_DELIVERY_UNVERIFIED",
        "--search-json",
        "gh label list --repo",
        'gh api --method GET --paginate',
        '"/repos/$GITHUB_REPOSITORY/issues?state=all&per_page=100"',
        '--jq \'.[] | select(has("pull_request") | not) | {number,title}\'',
        "| jq -s '.' >",

    )),
    "official_safety_before_delivery":("nasdaq-xray-delivery.yml",(
        "Refresh official Nasdaq halt + Security Status guard",
        "XRAY_DELIVERY_OFFICIAL_SAFETY_GUARD=PASS",
        "Synthetic registered-R92 delivery self-test",
        "Create or recover deduplicated research candidate issues",
    )),
    "preopen_no_false_release":("xray-preopen-source-audit.yml",(
        "XRAY_PREOPEN_CURRENT_MAIN_SHA_EXACT=PASS",
        "preopen_live_release_gate.py --selftest",
        "r[\"r92_created\"] is False",
        "r[\"real_device_receipt_verified\"] is False",
    )),
    "root_relay_checkout_immutability":("nasdaq-xray-daily.yml",(
        "Atomically wake pre-MC after root checkpoint",
        "github_native_stage_relay.py --out",
    )),
}

def crons(yml:str)->tuple[str,...]:
    return tuple(re.findall(r'^\s*- cron: [\"\']([^\"\']+)[\"\']\s*$',yml,re.M))

def validate_contract(files:dict[str,str])->dict:
    errors=[]
    for name,want in REQUIRED.items():
        actual=crons(files[name])
        if actual!=want:
            errors.append("CRON_DRIFT:"+name)
    for label,(name,needles) in CHECKS.items():
        if any(n not in files[name] for n in needles):
            errors.append("SAFETY_STEP_MISSING:"+label)
    d=files["nasdaq-xray-delivery.yml"]
    # One issue creation per key; fallback double-create after uncertain HTTP
    # failure risks two user-facing notifications for one registered R92.
    if d.count("gh issue create")!=1 or "|| gh issue create" in d:
        errors.append("DELIVERY_DUPLICATE_ISSUE_CREATE_PATH")
    if "'.[0].number // empty'" in d or "gh issue list --repo" in d:
        errors.append("DELIVERY_UNVERIFIED_FIRST_FUZZY_MATCH")
    if "gh api --method GET --paginate" not in d or "--search \"$delivery_key in:title\"" in d:
        errors.append("DELIVERY_ISSUE_LOOKUP_NOT_EXHAUSTIVE")
    if "set -euo pipefail" not in d:
        errors.append("DELIVERY_PAGINATION_API_FAILURE_NOT_FATAL")
    receipt_guard=(DATA/"delivery_issue_receipt_guard.py").read_text()
    if "def unique_exact_issue(" not in receipt_guard:
        errors.append("DELIVERY_EXACT_ISSUE_LOOKUP_GUARD_MISSING")
    scheduler=(DATA/"delivery_scheduler_guard.py").read_text()
    for needle in ("def _weekday_root_successes(", "def _later_red_than_green(",
                   "ROOT_LATEST_RUN_FAILED_OR_CANCELLED",
                   "FINAL_LATEST_RUN_FAILED_OR_CANCELLED",
                   'rt=_dt(latest_root.get("created_at"))'):
        if needle not in scheduler:
            errors.append("DELIVERY_SCHEDULER_FAIL_CLOSED_REGRESSION:"+needle)
    ledger=(DATA/"delivery_ledger_merge.py").read_text()
    for needle in ("def _checked_at(", "DELIVERY_EQUAL_TIMESTAMP_RECEIPT_CONFLICT",
                   'combined["backup_issue_status"] = best.get("backup_issue_status")'):
        if needle not in ledger:
            errors.append("DELIVERY_LEDGER_LATEST_OBSERVATION_REGRESSION:"+needle)
    ordering=(
        "Refresh official Nasdaq halt + Security Status guard",
        "Synthetic registered-R92 delivery self-test",
        "Classify registered R92 presence without claiming source readiness",
        "Reject stale latest completed Nasdaq source before R92 delivery",
        "Verify scheduler and final recovery readiness",
        "Prepare fail-closed registered research alerts",
        "Create or recover deduplicated research candidate issues",
    )
    if not all(d.find(a)<d.find(b) for a,b in zip(ordering,ordering[1:])):
        errors.append("DELIVERY_SAFETY_STEP_ORDER_DRIFT")
    wd=(DATA/"github_native_root_watchdog.py").read_text()
    for needle in (
        "weekend_noop_root_ids_ignored_for_weekday_success",
        "health_lease_authorizes(", "get_health_kick(",
        "two_read_authorized(", "ROOT_DISPATCH_ACCEPTED_NOT_RECOVERY",
    ):
        if needle not in wd:
            errors.append("WATCHDOG_REPAIR_CONTRACT_MISSING:"+needle)
    relay=(DATA/"github_native_stage_relay.py").read_text()
    for needle in ("exact_checked_out_main(", '["git","rev-parse","HEAD"]',
                   "fingerprint(first_runs)!=fingerprint(next_runs)",
                   "SOURCE_ASOF_MISMATCH"):
        if needle not in relay:
            errors.append("RELAY_SHA_CONTRACT_MISSING:"+needle)
    return {"ok":not errors,"errors":sorted(set(errors))}

def session_timeline():
    from preopen_live_release_gate import official_window
    # Columbus Day is a regular Nasdaq stock-market session, not a bond day.
    d=dt.datetime(2026,10,12,13,30,tzinfo=dt.timezone.utc)
    assert d.astimezone(NY).strftime("%Y-%m-%d %H:%M")=="2026-10-12 09:30"
    assert d.astimezone(TR).strftime("%Y-%m-%d %H:%M")=="2026-10-12 16:30"
    for hour,minute in ((12,5),(12,25),(13,5),(13,15)):
        assert official_window(dt.datetime(2026,10,12,hour,minute,
                                          tzinfo=dt.timezone.utc))["preopen"]
    assert not official_window(d)["preopen"]
    # Winter EDT -> EST transition still has 09:15 ET observation.
    winter=dt.datetime(2026,11,2,14,15,tzinfo=dt.timezone.utc)
    assert winter.astimezone(NY).strftime("%H:%M")=="09:15"
    assert official_window(winter)["preopen"]
    assert not official_window(dt.datetime(2026,11,2,12,5,
                                         tzinfo=dt.timezone.utc))["preopen"]
    return True

def current_readonly_diagnostics():
    names=("canonical_current_master_manifest.json",
           "canonical_current_price_dv30.json",
           "canonical_current_terminal.json",
           "delivery_ledger.json","provider_automation_governance.json")
    data={name:json.loads((DATA/name).read_text()) for name in names}
    m,p,t,ledger,governance=(data[n] for n in names)
    if any(v.get("execution")!="NONE" or v.get("real_money")!="NO-GO"
           for v in (m,p,t,ledger,governance)):
        raise AssertionError("CANONICAL_EXECUTION_SAFETY_DRIFT")
    if governance.get("no_paid_fallback") is not True:
        raise AssertionError("PAID_PROVIDER_FALLBACK_DRIFT")
    provider=governance.get("providers") or {}
    if provider.get("ALPHASTOCKS",{}).get("unattended_automation_allowed") is not False:
        raise AssertionError("ALPHASTOCKS_UNATTENDED_RIGHTS_DRIFT")
    if provider.get("BIGDATA",{}).get("paid_top_up_allowed") is not False:
        raise AssertionError("BIGDATA_PAID_TOPUP_DRIFT")
    candidates=t.get("r92_candidates") or []
    deliveries=ledger.get("deliveries") or {}
    return {
        "master_asof":m.get("asof_et"),"master_unknown_count":m.get("unknown_count"),
        "price_asof":p.get("asof_et"),"price_pass_count":p.get("pass_count"),
        "terminal_asof":t.get("asof_et"),
        "terminal_status":t.get("status"),
        "registered_r92_count":len(candidates),
        "recorded_backup_issue_count":sum(
            x.get("backup_issue_status")=="DELIVERED" for x in deliveries.values()
        ),
        "device_receipt_attested":False,
        "device_receipt_note":"UNOBSERVABLE_FROM_GITHUB_OR_AUTOMATION_SETTINGS",
        "research_release_attested_by_this_audit":False,
    }

def selftest():
    files={k:(WF/k).read_text() for k in REQUIRED}
    ok=validate_contract(files)
    assert ok["ok"],ok
    regressions=[
        ("nasdaq-xray-daily.yml",'"30 * * * *"','"31 * * * *"'),
        ("xray-preopen-source-audit.yml",'"15 13 * * 1-5"','"16 13 * * 1-5"'),
        ("nasdaq-xray-delivery.yml","gh issue create","echo no-issue"),
        ("nasdaq-xray-delivery.yml",
         "if: steps.prep.outputs.ready == 'true'",
         "if: always()"),
        ("nasdaq-xray-delivery.yml",
         "XRAY_DELIVERY_OFFICIAL_SAFETY_GUARD=PASS",
         "SAFETY_NOT_CHECKED"),
        ("xray-github-native-root-watchdog.yml",
         "github_native_chain_health.py --out", "no-chain-health"),
        ("nasdaq-xray-daily.yml","root_weekend_quota_guard.py --emit","disabled-weekend-guard"),
        ("nasdaq-xray-delivery.yml","delivery_issue_receipt_guard.py","MISSING_VERIFIER"),
        ("nasdaq-xray-delivery.yml",'gh issue view "$existing" --json number,title,body,url',
         "UNVERIFIED_ISSUE_SEARCH_RESULT"),
        ("nasdaq-xray-delivery.yml","--search-json",
         "UNVERIFIED_ISSUE_FUZZY_RESULT"),
        ("nasdaq-xray-delivery.yml","gh issue create",
         "gh issue create || gh issue create"),
    ]
    for name,needle,replacement in regressions:
        assert needle in files[name],(name,needle)
        modified=dict(files)
        modified[name]=files[name].replace(needle,replacement)
        assert not validate_contract(modified)["ok"],(name,needle)
    # Move the *entire* refresh step after issue creation, not just rename it.
    # This must fail even though all original safety step names remain present.
    modified=dict(files)
    raw=modified["nasdaq-xray-delivery.yml"]
    start=raw.index("      - name: Refresh official Nasdaq halt + Security Status guard")
    stop=raw.index("      - name: Synthetic registered-R92 delivery self-test",start)
    guard_step=raw[start:stop]
    without_guard=raw[:start]+raw[stop:]
    destination=without_guard.index("      - name: Reconcile durable delivery ledger")
    modified["nasdaq-xray-delivery.yml"]=(
        without_guard[:destination]+guard_step+without_guard[destination:])
    assert not validate_contract(modified)["ok"]
    assert session_timeline()
    print("XRAY_MONDAY_MICROAUDIT_SELFTEST=PASS_12_NEGATIVES_DST_DELIVERY_RECEIPTS_RECOVERY_NO_FALSE_GO")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.out:parser.error("--out required")
    files={name:(WF/name).read_text() for name in REQUIRED}
    contract=validate_contract(files)
    diagnosis=current_readonly_diagnostics()
    result={
        "schema":SCHEMA,
        "kind":"STATIC_SCHEDULER_DELIVERY_RECOVERY_AND_CURRENT_SOURCE_CONTRACT_ONLY",
        "contract_status":"PASS" if contract["ok"] else "FAIL",
        "contract_blockers":contract["errors"],
        "calendar_boundary_verified":session_timeline(),
        "observed_source":diagnosis,
        "alpha_authority":False,
        "no_real_device_receipt_claim":True,
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
    }
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_MONDAY_MICROAUDIT_CONTRACT="+result["contract_status"])
    print("XRAY_MONDAY_MICROAUDIT_R92="+str(diagnosis["registered_r92_count"]))
    print("XRAY_MONDAY_MICROAUDIT_DEVICE_RECEIPT=UNVERIFIED")
    if not contract["ok"]:
        raise SystemExit("XRAY_MONDAY_MICROAUDIT_STATIC_GUARD_FAIL_CLOSED")

if __name__=="__main__":
    main()
