#!/usr/bin/env python3
"""Fail-closed no-op historical watch topology regression (research only).

The dated 09-Oct source observer ended at 2026-10-09 20:15 UTC.
Once expired it must not fan out into root watchdog and waste GitHub
Actions quota or make successful empty watches look like fresh proofs.
The independent root watchdog and R92 delivery remain active.
"""
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
WATCH=ROOT/".github/workflows/xray-20261009-preopen-watch.yml"
DOG=ROOT/".github/workflows/xray-github-native-root-watchdog.yml"
CLOSE=datetime(2026,10,9,20,15,tzinfo=timezone.utc)

def selftest():
    assert datetime(2026,10,10,tzinfo=timezone.utc)>CLOSE
    w=WATCH.read_text()
    d=DOG.read_text()
    w_on=w.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
    assert "  workflow_dispatch:" in w_on,"HISTORICAL_MANUAL_REPLAY_DISABLED"
    for trigger in ("  workflow_run:","  schedule:","  push:"):
        assert trigger not in w_on,"EXPIRED_9OCT_WATCH_STILL_AUTOMATIC:"+trigger.strip()
    assert "XRAY 09-Oct Free Preopen 15-Minute Watch" not in d, (
        "EXPIRED_9OCT_WATCH_STILL_ROOT_WATCHDOG_TRIGGER")
    for mandatory in (
        '"XRAY Live Truth Attestation"',
        '"XRAY E2E Production Readiness (Fail-Closed)"',
        'cron: "*/15 * * * 1-5"',
    ):
        assert mandatory in d,"LIVE_ROOT_WATCHDOG_REQUIRED_TRIGGER_REMOVED:"+mandatory
    assert "python nasdaq-xray/github_native_root_watchdog.py --out" in d, (
        "LIVE_ROOT_WATCHDOG_ACTION_REMOVED")
    print("XRAY_09OCT_EXPIRED_WATCH=PASS_MANUAL_ONLY_NO_DUPLICATE_ACTIONS_LIVE_ROOT_WATCHDOG_INTACT")

if __name__=="__main__":
    selftest()
