#!/usr/bin/env python3
"""Synthetic source epoch race negatives. No providers, orders or permissions."""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
A="a"*40
B="b"*40
def need(ok,reason):
    if not ok: raise ValueError(reason)
def selected(event,sha,upstream):
    need(event in ("workflow_run","push","schedule","workflow_dispatch"),"BAD_EVENT")
    value=upstream if event=="workflow_run" else sha
    need(bool(re.fullmatch("[0-9a-f]{40}",value)),"BAD_SHA")
    return value
def exact_code(before,after):
    need(len(before)==3 and len(after)==3,"BAD_SCOPE")
    need(all(re.fullmatch("[0-9a-f]{40}",x) for x in before+after),"BAD_BLOB")
    need(before==after,"TESTED_SOURCE_CHANGED")
def negative(fn):
    try: fn()
    except ValueError:return
    raise RuntimeError("NEGATIVE_BYPASS")
def main():
    a=(ROOT/".github/workflows/xray-account-gate-reconcile.yml").read_text()
    m=(ROOT/".github/workflows/xray-manual-decision-research-shadow.yml").read_text()
    need("ref: "+chr(36)+"{{ github.sha }}" in a,"ACCOUNT_PIN_MISSING")
    need("TESTED_RECONCILER_BLOB" in a and "TESTED_SELFTEST_BLOB" in a
         and "TESTED_FENCE_BLOB" in a,"ACCOUNT_CODE_FENCE_MISSING")
    need("XRAY_ACCOUNT_TESTED_SOURCE_EPOCH_DRIFT" in a,"ACCOUNT_DRIFT_RULE_MISSING")
    need(a.count("python nasdaq-xray/reconcile_account_gate_selftest.py")>=2,"ACCOUNT_RETEST_MISSING")
    need("github.event_name == 'workflow_run' && github.event.workflow_run.head_sha || github.sha" in m,
         "MANUAL_UPSTREAM_PIN_MISSING")
    need("github.event.workflow_run.head_repository.full_name == github.repository" in m
         and "github.event.workflow_run.head_branch == 'main'" in m,"MANUAL_ORIGIN_MISSING")
    need("XRAY_MANUAL_SOURCE_EPOCH=BLOCKED_MAIN_ADVANCED" in m,"MANUAL_CURRENT_MAIN_FENCE_MISSING")
    need(not re.search(r"^\s*ref:\s*main\s*$",a,re.M)
         and not re.search(r"^\s*ref:\s*main\s*$",m,re.M),"MOVING_MAIN_REF")
    need(selected("workflow_run",B,A)==A and selected("push",A,B)==A
         and selected("schedule",A,B)==A
         and selected("workflow_dispatch",A,B)==A,"POSITIVE_EPOCH")
    exact_code((A,A,A),(A,A,A))
    negative(lambda:selected("workflow_run",B,"invalid"))
    negative(lambda:selected("bad",A,B))
    negative(lambda:exact_code((A,A,A),(A,B,A)))
    negative(lambda:exact_code((A,A,A),(B,A,A)))
    negative(lambda:exact_code((A,A,A),(A,A,B)))
    negative(lambda:exact_code((A,A,"invalid"),(A,A,"invalid")))
    print("XRAY_SOURCE_EPOCH_REGRESSION=PASS_5_POSITIVE_6_NEGATIVE_NON_AUTHORITY")
if __name__=="__main__":main()
