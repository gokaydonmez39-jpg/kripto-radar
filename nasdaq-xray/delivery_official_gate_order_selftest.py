#!/usr/bin/env python3
"""Static adversarial guard for read-only XRAY delivery workflow order.

A delivery run without a registered candidate MUST NOT fetch official
halt/security status or burn external provider calls. Future valid R92 MUST
retain the mandatory up-to-date official source veto, after ASOF check.
No market/vendor network calls, secrets, notifications, or trading.
"""
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
WORKFLOW=HERE.parent/".github/workflows/nasdaq-xray-delivery.yml"


def need(ok,code):
    if not ok:
        raise ValueError("XRAY_DELIVERY_GUARD_ORDER_"+code)


def validate(workflow):
    need(type(workflow) is str and workflow,"EMPTY")
    labels=list(re.finditer(r"(?m)^      - name: ([^\r\n]+)$",workflow))
    need(bool(labels),"STEPS_MISSING")
    steps={}
    for i,m in enumerate(labels):
        name=m.group(1)
        need(name not in steps,"DUPLICATE_STEP_"+name)
        steps[name]=workflow[m.start():labels[i+1].start() if i+1<len(labels)
                             else len(workflow)]
    presence="Classify registered R92 presence without claiming source readiness"
    epoch="Reject stale latest completed Nasdaq source before R92 delivery"
    official="Refresh official Nasdaq halt + Security Status guard"
    scheduler="Verify scheduler and final recovery readiness"
    prep="Prepare fail-closed registered research alerts"
    names=(presence,epoch,official,scheduler,prep)
    need(all(n in steps for n in names),"MANDATORY_STEP_MISSING")
    order=[workflow.index("      - name: "+n+"\n") for n in names]
    need(order==sorted(order) and len(set(order))==5,
         "OFFICIAL_NETWORK_BEFORE_REGISTERED_FRESH_R92")
    need("python nasdaq-xray/delivery_candidate_preflight.py)" in steps[presence]
         and 'registered=true' in steps[presence]
         and 'registered=false' in steps[presence],
         "NO_EXACT_REGISTRATION_GATE")
    need("if: steps.presence.outputs.registered == 'true'" in steps[epoch]
         and "source_epoch_freshness_guard.py --out" in steps[epoch]
         and 'report["freshness_ready"] is True' in steps[epoch]
         and 'out.write("ready="+str(ok).lower()+"\\n")' in steps[epoch],
         "NO_SAME_SESSION_FRESHNESS_GATE")
    need("if: steps.source_epoch.outputs.ready == 'true'" in steps[official]
         and "python nasdaq-xray/official_source_guard.py\n" in steps[official]
         and 'h.get("status")=="PASS"' in steps[official]
         and 'ss.get("status")=="PASS"' in steps[official],
         "NO_MANDATORY_OFFICIAL_HALT_AND_SECURITY_PASS")
    need("if: steps.source_epoch.outputs.ready == 'true'" in steps[scheduler]
         and "delivery_scheduler_guard.py" in steps[scheduler],
         "NO_SCHEDULER_EPOCH_GATE")
    need("if: steps.scheduler.outputs.ready == 'true'" in steps[prep]
         and "delivery_prepare.py" in steps[prep],
         "NO_PREPARE_LAST")
    # No shadow duplicate official network request outside the guarded step.
    need(workflow.count("python nasdaq-xray/official_source_guard.py\n")==1,
         "BYPASS_OFFICIAL_CALL")
    need(re.search(r"(?m)^  deliver:\n    if: \$\{\{ github.event_name != 'pull_request'",workflow)
         is not None,
         "UNTRUSTED_PR_LIVE_DELIVERY")
    need("if: github.event_name == 'pull_request' || github.event_name == 'push'"
         in workflow,"NO_PR_OFFLINE_AUDIT")
    return True


def selftest():
    src=WORKFLOW.read_text(encoding="utf-8")
    need(validate(src),"POSITIVE_GUARD_ORDER")
    official="      - name: Refresh official Nasdaq halt + Security Status guard\n"
    presence="      - name: Classify registered R92 presence without claiming source readiness\n"
    for case,mutated in (
        ("EARLY_NETWORK",src.replace(official,presence+official,1)),
        ("MISSING_GUARD",src.replace(
            "        if: steps.source_epoch.outputs.ready == 'true'\n        run: |\n          python nasdaq-xray/official_source_guard.py",
            "        run: |\n          python nasdaq-xray/official_source_guard.py",1)),
        ("WEAK_GUARD",src.replace(
            "        if: steps.source_epoch.outputs.ready == 'true'\n        run: |\n          python nasdaq-xray/official_source_guard.py",
            "        if: steps.presence.outputs.registered == 'true'\n        run: |\n          python nasdaq-xray/official_source_guard.py",1)),
        ("MISSING_ASOF",src.replace(
            "if: steps.presence.outputs.registered == 'true'",
            "if: steps.presence.outputs.registered != 'false'",1)),
        ("NO_HALT_PASS",src.replace(
            'h.get("status")=="PASS"',
            'h.get("status")!="FAIL"',1)),
        ("NO_SECURITY_PASS",src.replace(
            'ss.get("status")=="PASS"',
            'ss.get("status")!="FAIL"',1)),
        ("EXTRA_CALL",src.replace(
            "python nasdaq-xray/official_source_guard.py\n",
            "python nasdaq-xray/official_source_guard.py\n"
            "          python nasdaq-xray/official_source_guard.py\n",1)),
        ("PR_LIVE",src.replace(
            "github.event_name != 'pull_request' && ",
            "",1)),
    ):
        need(mutated!=src,"FORGED_FIXTURE_NOT_MUTATED_"+case)
        try:
            validate(mutated)
        except ValueError:
            continue
        raise ValueError("FORGED_"+case+"_WAS_ACCEPTED")
    print("XRAY_DELIVERY_LAZY_OFFICIAL_GUARD_SELFTEST=PASS_8_ADVERSARIAL_NEGATIVES_PR_OFFLINE_NO_PROVIDER")


if __name__=="__main__":
    selftest()
