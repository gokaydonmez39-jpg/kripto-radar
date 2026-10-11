#!/usr/bin/env python3
"""Read-only audit of EVERY GitHub workflow's automatic schedule & Issue privilege.

This is static trigger/security topology evidence, not runtime provider/alpha GO.
Manual-only or push workflows remain in the inventory, not silently ignored.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
WF=ROOT/".github"/"workflows"
SCHEMA="XRAY_ALL_GITHUB_WORKFLOW_SCHEDULE_PRIVILEGE_AUDIT_V1"

# All 23 AUTOMATICALLY SCHEDULED workflows; discovered from 135 repo YAML files.
# Root, preopen, delivery, E2E, account, G9 and other safety services are included.
EXPECTED={
 "nasdaq-xray-daily.yml":("30 * * * *",),
 "nasdaq-xray-delivery.yml":("*/15 * * * 1-5","7 * * * 0,6"),
 "xray-account-gate-reconcile.yml":("12 * * * *",),
 "xray-alpaca-delayed-sip-research.yml":("55 13,17 * * 1-5",),
 "xray-canonical-current-final.yml":("53 5-23 * * 1-5","53 0-3 * * 2-6"),
 "xray-canonical-current-post-mc.yml":("50 5-23 * * 1-5","50 0-3 * * 2-6"),
 "xray-canonical-current-pre-mc.yml":("35 5-23 * * 1-5","35 0-3 * * 2-6"),
 "xray-e2e-production-readiness.yml":("13 * * * 1-5",),
 "xray-final-gate-overlay-v2.yml":("55 * * * 1-5",),
 "xray-final-gate-overlay.yml":("15 * * * *",),
 "xray-github-native-root-watchdog.yml":("*/15 * * * 1-5",),
 "xray-live-truth-attestation.yml":("13 * * * 1-5",),
 "xray-manual-decision-research-shadow.yml":("17 21 * * 1-5",),
 "xray-massive-grouped-history-resume.yml":("17 */3 * * *",),
 "xray-multi-provider-research-shadow.yml":("07 21 * * 1-5",),
 "xray-preopen-source-audit.yml":("5 12 * * 1-5","25 12 * * 1-5",
                                    "5 13 * * 1-5","15 13 * * 1-5",
                                    "15 14 * * 1-5"),
 "xray-research-watch-radar.yml":("17 15,20,23 * * 1-5",),
 "xray-resilience-observability.yml":("47 * * * 1-5","47 */3 * * 0,6"),
 "xray-sec-mirror-cik-shadow.yml":("37 13 * * 1-5",),
 "xray-sec-transport-matrix-probe.yml":("23 12 * * 1-5",),
 "xray-strict-g9-gate.yml":("32 * * * 1-5",),
 "xray-twelve-history-resume.yml":("53 * * * *",),
 "xray-zero-cost-four-stage-verification.yml":("17 13 * * 1-5",),
}
READONLY_PROVIDER_SCHEDULED={
 "xray-alpaca-delayed-sip-research.yml",
 "xray-massive-grouped-history-resume.yml",
 "xray-multi-provider-research-shadow.yml",
 "xray-sec-mirror-cik-shadow.yml",
 "xray-sec-transport-matrix-probe.yml",
 "xray-twelve-history-resume.yml",
 "xray-zero-cost-four-stage-verification.yml",
}
ISSUE_WRITERS={"nasdaq-xray-delivery.yml"}
PROVIDER_RIGHTS={
 "xray-massive-grouped-history-resume.yml":(
    'XRAY_MASSIVE_NONDISPLAY_LICENSE_OK', 'XRAY_MASSIVE_PRIVATE_CACHE_RIGHTS_OK',
    'XRAY_MASSIVE_LICENSE_EVIDENCE_SHA256', 'BLOCKED_RIGHTS_OR_KEY'),
 "xray-twelve-history-resume.yml":(
    'XRAY_TWELVE_NONDISPLAY_LICENSE_OK', 'XRAY_TWELVE_PRIVATE_CACHE_RIGHTS_OK',
    'XRAY_TWELVE_LICENSE_EVIDENCE_SHA256', 'BLOCKED_SOURCE_LICENSE_OR_KEY'),
}

def crons(source):
    return tuple(re.findall(r'^\\s*- cron: ["\\\']([^"\\\']+)["\\\']\\s*$',source,re.M))

def inventory(files):
    errors=[]
    names=set(files)
    scheduled={}
    writer_names=[]
    for name,source in files.items():
        if not isinstance(source,str) or not source.strip():
            errors.append("WORKFLOW_UNREADABLE:"+name)
            continue
        found=crons(source)
        if found:
            scheduled[name]=list(found)
        if re.search(r'^\\s+issues:\\s*write\\s*$',source,re.M):
            writer_names.append(name)
        if name in READONLY_PROVIDER_SCHEDULED:
            if not re.search(r'^\\s+contents:\\s*read\\s*$',source,re.M):
                errors.append("SCHEDULED_SHADOW_CONTENTS_NOT_READ_ONLY:"+name)
            if re.search(r'^\\s+contents:\\s*write\\s*$',source,re.M):
                errors.append("SCHEDULED_SHADOW_WRITE_PRIVILEGE:"+name)
    for n,expected in EXPECTED.items():
        if n not in names:errors.append("SCHEDULED_WORKFLOW_FILE_MISSING:"+n)
        elif crons(files[n])!=expected:errors.append("SCHEDULED_CRON_CHANGED:"+n)
    for n in scheduled:
        if n not in EXPECTED:errors.append("UNREVIEWED_NEW_SCHEDULE:"+n)
    for n in writer_names:
        if n not in ISSUE_WRITERS:errors.append("UNAUTHORIZED_ISSUE_WRITE_PRIVILEGE:"+n)
    for n in ISSUE_WRITERS:
        if n not in writer_names:errors.append("AUTHORIZED_DELIVERY_ISSUE_WRITER_MISSING:"+n)
    for n,needles in PROVIDER_RIGHTS.items():
        if n not in names:continue
        for value in needles:
            if value not in files[n]:
                errors.append("SCHEDULED_VENDOR_ENTITLEMENT_GUARD_DRIFT:"+n+":"+value)
    return {"schema":SCHEMA,"total_workflow_yaml_files":len(names),
            "scheduled_count":len(scheduled),
            "expected_scheduled_count":len(EXPECTED),
            "automated_schedules":dict(sorted(scheduled.items())),
            "issue_writers":sorted(writer_names),
            "extra_readonly_provider_scheduled":sorted(READONLY_PROVIDER_SCHEDULED),
            "contract_status":"PASS" if not errors else "FAIL",
            "blockers":sorted(set(errors)),
            "alpha_authority":False,"device_delivery_attested":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def read_files():
    return {p.name:p.read_text(encoding="utf-8")
            for p in sorted(WF.iterdir())
            if p.is_file() and p.suffix in (".yml",".yaml")}

def selftest():
    actual=read_files()
    base=inventory(actual)
    assert base["contract_status"]=="PASS",base["blockers"]
    assert base["scheduled_count"]==23
    assert base["issue_writers"]==["nasdaq-xray-delivery.yml"]
    def bad(modify,want):
        sample=dict(actual)
        modify(sample)
        result=inventory(sample)
        assert result["contract_status"]=="FAIL"
        assert any(want in x for x in result["blockers"]),(want,result["blockers"])
    bad(lambda x:x.update({"nasdaq-xray.yml":x["nasdaq-xray.yml"]+
        '\\nschedule:\\n  - cron: "15 * * * *"\\n'}),"UNREVIEWED_NEW_SCHEDULE")
    bad(lambda x:x.update({"xray-sec-mirror-cik-shadow.yml":
        x["xray-sec-mirror-cik-shadow.yml"].replace(
            "contents: read","contents: write")}),
        "SCHEDULED_SHADOW_CONTENTS_NOT_READ_ONLY")
    bad(lambda x:x.update({"xray-massive-grouped-history-resume.yml":
        x["xray-massive-grouped-history-resume.yml"].replace(
            "XRAY_MASSIVE_PRIVATE_CACHE_RIGHTS_OK","BYPASS_PRIVATE_CACHE")}),
        "SCHEDULED_VENDOR_ENTITLEMENT_GUARD_DRIFT")
    bad(lambda x:x.update({"xray-twelve-history-resume.yml":
        x["xray-twelve-history-resume.yml"].replace(
            "BLOCKED_SOURCE_LICENSE_OR_KEY","UNCONDITIONAL_CALL")}),
        "SCHEDULED_VENDOR_ENTITLEMENT_GUARD_DRIFT")
    bad(lambda x:x.update({"xray-e2e-production-readiness.yml":
        x["xray-e2e-production-readiness.yml"].replace(
            '"13 * * * 1-5"','"14 * * * 1-5"')}),
        "SCHEDULED_CRON_CHANGED")
    bad(lambda x:x.update({"xray-sec-mirror-cik-shadow.yml":
        x["xray-sec-mirror-cik-shadow.yml"].replace(
            "contents: read","contents: read\\n  issues: write")}),
        "UNAUTHORIZED_ISSUE_WRITE_PRIVILEGE")
    bad(lambda x:x.pop("xray-research-watch-radar.yml"),
        "SCHEDULED_WORKFLOW_FILE_MISSING")
    print("XRAY_ALL_135_WORKFLOW_TRIGGER_AUDIT_SELFTEST=PASS_7_NEGATIVES_23_CRONS_ONE_ISSUE_WRITER")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if not a.out:p.error("--out required")
    result=inventory(read_files())
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\\n",encoding="utf-8")
    print("XRAY_ALL_WORKFLOW_SCHEDULE_INVENTORY="+result["contract_status"])
    print("XRAY_ALL_WORKFLOW_YAML_FILES="+str(result["total_workflow_yaml_files"]))
    print("XRAY_ALL_WORKFLOW_SCHEDULES="+str(result["scheduled_count"]))
    print("XRAY_ALL_WORKFLOW_ISSUE_WRITERS="+str(len(result["issue_writers"])))
    if result["blockers"]:
        print("XRAY_ALL_WORKFLOW_BLOCKERS="+json.dumps(result["blockers"]))
        raise SystemExit(2)

if __name__=="__main__":main()
