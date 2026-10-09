#!/usr/bin/env python3
"""Unattended GitHub root: no market/vendor work on an ET weekend.

The cron is UTC and must stay calendar-neutral; a UTC Monday can still be
Sunday in New York. Explicit manual workflow_dispatch can examine the last
completed official session, but has NO alpha/MC/G9/notification authority.
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")
ROOT=Path(__file__).resolve().parent
WORKFLOW=ROOT.parent/".github/workflows/nasdaq-xray-daily.yml"
GUARD_COND="steps.session.outputs.allow_compute == 'true'"
ROOT_MARKERS=(
    "Install zero-dollar research runtime",
    "Verify deterministic alpha semantics",
    "Run autonomous XRAY data plane",
    "Commit durable XRAY checkpoints",
    "Atomically wake pre-MC after root checkpoint, never claim terminal success",
)

def permit_compute(now_utc:dt.datetime,event_name:str)->bool:
    if now_utc.tzinfo is None or now_utc.utcoffset()!=dt.timedelta(0):
        raise ValueError("REQUIRES_AWARE_UTC_CLOCK")
    if event_name not in {"schedule","push","workflow_dispatch"}:
        raise ValueError("UNSUPPORTED_ROOT_EVENT")
    if event_name=="workflow_dispatch":
        return True  # An explicit research invocation, not scheduled quota burn.
    return now_utc.astimezone(NY).weekday()<5

def check_workflow_guard(workflow:str)->None:
    if "id: session" not in workflow or "--emit" not in workflow:
        raise AssertionError("WEEKEND_COMPUTE_GATE_NOT_WIRED")
    lines=workflow.splitlines()
    for marker in ROOT_MARKERS:
        positions=[i for i,l in enumerate(lines) if l.strip()=="- name: "+marker]
        if len(positions)!=1:
            raise AssertionError("ROOT_MARKER_MISSING_OR_DUPLICATE:"+marker)
        start=positions[0]
        after=lines[start+1:start+5]
        if not any(GUARD_COND in line and line.strip().startswith("if:") for line in after):
            raise AssertionError("WEEKEND_MARKET_WORK_UNGUARDED:"+marker)

def selftest()->None:
    u=dt.timezone.utc
    d=lambda y,m,day,h:dt.datetime(y,m,day,h,tzinfo=u)
    # Saturday UTC 02:00 is still Friday 22:00 EDT: no UTC weekday shortcut.
    assert permit_compute(d(2026,10,10,2),"schedule")
    # Saturday and Sunday ET must not call Sina/Yahoo or wake Pre-MC.
    assert not permit_compute(d(2026,10,10,18),"schedule")
    assert not permit_compute(d(2026,10,11,18),"push")
    # Monday UTC 03:00 is still Sunday 23:00 EDT.
    assert not permit_compute(d(2026,10,12,3),"schedule")
    # Columbus Day 2026: stock market open, despite bond-market closure.
    assert permit_compute(d(2026,10,12,15),"schedule")
    # Explicit research invocation is a distinct, recorded event.
    assert permit_compute(d(2026,10,11,18),"workflow_dispatch")
    try:permit_compute(dt.datetime(2026,10,12,15),"schedule")
    except ValueError:pass
    else:raise AssertionError("NAIVE_CLOCK_ACCEPTED")
    try:permit_compute(d(2026,10,12,15),"rogue")
    except ValueError:pass
    else:raise AssertionError("UNKNOWN_EVENT_ACCEPTED")
    check_workflow_guard(WORKFLOW.read_text())
    print("XRAY_ROOT_ET_WEEKEND_QUOTA_GUARD_SELFTEST=PASS_DST_UTC_BOUNDARY_COLUBMUS_DAY_EXPLICIT_MANUAL_5_STAGES")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--emit",action="store_true")
    opts=a.parse_args()
    if opts.selftest:
        selftest();return
    if not opts.emit:
        a.error("use --selftest or --emit")
    name=os.environ.get("GITHUB_EVENT_NAME")
    allowed=permit_compute(dt.datetime.now(dt.timezone.utc),name)
    outfile=os.environ.get("GITHUB_OUTPUT")
    if not outfile:raise RuntimeError("GITHUB_OUTPUT_MISSING")
    with open(outfile,"a",encoding="utf-8") as out:
        out.write("allow_compute="+("true" if allowed else "false")+"\n")
    print("XRAY_ROOT_UNATTENDED_MARKET_WORK="+("ENABLED" if allowed else "WEEKEND_BLOCKED_QUOTA_PROTECTED"))
    print("XRAY_ROOT_WEEKEND_GUARD=RESEARCH_ONLY_NO_ALPHA_NO_TRADES_NO_PROVIDER_UPGRADE")

if __name__=="__main__":main()
