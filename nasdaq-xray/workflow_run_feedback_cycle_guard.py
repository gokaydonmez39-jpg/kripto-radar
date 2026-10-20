#!/usr/bin/env python3
"""XRAY three-workflow cycle cut proof; no network, signals or provider calls.

A code-only audit of the explicit workflow_run names, not a general YAML or
GitHub scheduling simulation. PR-only validation; cannot certify runtime
executions, cadence, or source completeness.
"""
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent/".github"/"workflows"
FINAL="XRAY Canonical Current Final Factory"
POINTER="XRAY Canonical Pointer Transition"
RESILIENCE="XRAY Resilience + Official Witnesses"
DATA="NASDAQ SWING XRAY Autonomous Data Plane"

def need(ok,code):
    if not ok:raise ValueError("XRAY_CYCLE_GUARD_"+code)

def targets(txt):
    """Extract one literal inline workflow_run.workflows list exactly."""
    lines=txt.splitlines()
    found=[i for i,line in enumerate(lines) if line=="  workflow_run:"]
    need(len(found)==1,"RUN_DECLARATION_COUNT")
    selection=[]
    for line in lines[found[0]+1:]:
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:",line):
            break
        selection.append(line)
    work=[line for line in selection if line.startswith("    workflows:")]
    need(len(work)==1,"WORKFLOWS_DECLARATION_COUNT")
    try: values=json.loads(work[0].split(":",1)[1].strip())
    except ValueError as exc:
        raise ValueError("XRAY_CYCLE_GUARD_TARGET_JSON") from exc
    need(type(values) is list and all(type(v) is str for v in values)
         and len(set(values))==len(values),"TARGET_LIST_AMBIGUOUS")
    return values

def verify(r,p,f):
    rt,pt,ft=targets(r),targets(p),targets(f)
    need(DATA in rt,"ROOT_RESILIENCE_EDGE_LOST")
    need(POINTER not in rt,"POINTER_RESILIENCE_CYCLE_RESTORED")
    need(rt==[DATA],"RESILIENCE_EXTRA_WAKE_OR_DUPLICATE")
    need(pt==[FINAL],"FINAL_POINTER_EDGE_CHANGED")
    need(RESILIENCE in ft,"RESILIENCE_FINAL_EDGE_CHANGED")
    # Verify fallback triggers remain; no attempt to prove real GitHub dispatch.
    for trigger in ("  push:","  schedule:","  workflow_dispatch:"):
        need(trigger in r,"RESILIENCE_FALLBACK_LOST")
    need('"nasdaq-xray/chatgpt_canonical_state_v2.json"' in r,
         "POINTER_PUSH_FALLBACK_LOST")
    need("  workflow_run:" in p and "  workflow_run:" in f,
         "DOWNSTREAM_WORKFLOW_RUN_MISSING")
    return {"removed_workflow_run_edge":POINTER+" -> "+RESILIENCE,
            "preserved_root_to_resilience":True,
            "preserved_resilience_to_final":True,
            "preserved_final_to_pointer":True,
            "calendar_and_source_validation_proven":False,
            "run_success_proven":False,
            "market_or_R92_authority":False,
            "execution":"NONE","real_money":"NO-GO"}

def paths():
    return [(ROOT/name).read_text() for name in
        ("xray-resilience-observability.yml",
         "xray-canonical-pointer-transition.yml",
         "xray-canonical-current-final.yml")]

def selftest():
    r,p,f=paths()
    need(verify(r,p,f)["preserved_root_to_resilience"] is True,
         "CURRENT_TOPOLOGY")
    old=r.replace('workflows: ["'+DATA+'"]',
       'workflows: ["'+POINTER+'", "'+DATA+'"]')
    need(old!=r,"NEGATIVE_FIXTURE_NOT_CONSTRUCTED")
    adversarial=[
        ("OLD_CYCLE",old,p,f),
        ("NO_ROOT_WAKE",r.replace('workflows: ["'+DATA+'"]',
                                'workflows: ["'+POINTER+'"]'),p,f),
        ("ROOT_AND_POINTER",old,p,f),
        ("NO_POINTER_PUSH",r.replace(
             '"nasdaq-xray/chatgpt_canonical_state_v2.json"',
             '"nasdaq-xray/not_the_pointer.json"'),p,f),
        ("NO_SCHEDULE",r.replace("  schedule:","  not_schedule:"),p,f),
        ("NO_DISPATCH",r.replace("  workflow_dispatch:",
                                 "  not_dispatch:"),p,f),
        ("NO_FINAL_POINTER",r,p.replace(
              'workflows: ["'+FINAL+'"]',
              'workflows: ["'+RESILIENCE+'"]'),f),
        ("NO_RESILIENCE_FINAL",r,p,f.replace(
              '"'+RESILIENCE+'", ','"MISSING Resilience", ')),
        ("EXTRA_RESILIENCE_WAKES",r.replace(
              'workflows: ["'+DATA+'"]',
              'workflows: ["'+DATA+'", "UNKNOWN"]'),p,f),
        ("DUPLICATE_WORKFLOW_DECLARATION",r.replace(
              "  workflow_run:", "  workflow_run:\n  workflow_run:",1),p,f),
    ]
    for label,x,y,z in adversarial:
        try:verify(x,y,z)
        except ValueError:continue
        raise RuntimeError("XRAY_CYCLE_GUARD_NEGATIVE_WAS_ACCEPTED_"+label)
    need(len(adversarial)==10,"NEGATIVE_COUNT")
    print("XRAY_WORKFLOW_RUN_CYCLE_GUARD=PASS_10_NEGATIVES_NO_ALPHA")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--check",action="store_true")
    o=ap.parse_args()
    need(o.selftest != o.check,"MODE")
    if o.selftest:selftest()
    else:
        report=verify(*paths())
        print("XRAY_WORKFLOW_RUN_ONE_EDGE_CUT="+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
