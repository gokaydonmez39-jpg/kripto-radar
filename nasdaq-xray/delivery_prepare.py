#!/usr/bin/env python3
"""Prepare XRAY material alert issue body. No broker execution."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SRC=ROOT/"material_alert.json"
OUT=ROOT/"material_alert_issue.md"

if not SRC.exists():
    print("XRAY_DELIVERY_NOOP=NO_ALERT_FILE")
    raise SystemExit(0)

x=json.loads(SRC.read_text())
if x.get("execution")!="NONE" or x.get("real_money")!="NO-GO":
    raise RuntimeError("DELIVERY_SAFETY_LOCK_FAIL")
if x.get("emit") is not True:
    print("XRAY_DELIVERY_NOOP=EMIT_FALSE")
    raise SystemExit(0)
if x.get("g9_status")!="PASS":
    raise RuntimeError("DELIVERY_G9_NOT_PASS")
if x.get("account_gate")!="PASS":
    raise RuntimeError("DELIVERY_ACCOUNT_GATE_NOT_PASS")
if x.get("canonical_gate")!="PASS":
    raise RuntimeError("DELIVERY_CANONICAL_GATE_NOT_PASS")

required=["signal_id","ticker","setup","entry_low","entry_high","chase_limit","stop","target","risk_reward","registered_at_utc"]
missing=[k for k in required if x.get(k) is None]
if missing:
    raise RuntimeError("DELIVERY_FIELDS_MISSING:"+",".join(missing))

body=f"""# XRAY MATERIAL SIGNAL

**Research/forward-test only — no broker order is placed.**

- Signal ID: `{x['signal_id']}`
- Ticker: **{x['ticker']}**
- Setup: **{x['setup']}**
- Entry: {x['entry_low']} – {x['entry_high']}
- Chase limit: {x['chase_limit']}
- Frozen stop: {x['stop']}
- Target: {x['target']}
- Live R/R: {x['risk_reward']}
- Registered UTC: {x['registered_at_utc']}
- G9: PASS
- Account gate: PASS
- Canonical gate: PASS
- EXECUTION: NONE
- REAL_MONEY: NO-GO

This notification is generated from the XRAY durable signal state. It is not an executed trade.
"""
OUT.write_text(body,encoding="utf-8")
print("XRAY_DELIVERY_READY=PASS")
