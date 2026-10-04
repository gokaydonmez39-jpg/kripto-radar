#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
contract=json.loads((ROOT/"scheduler_failover_contract.json").read_text())
kick=json.loads((ROOT/"scheduler_kick_dataplane.json").read_text())
wf=(ROOT.parent/".github/workflows/nasdaq-xray-daily.yml").read_text()

assert contract["schema"]=="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1"
assert contract["execution"]=="NONE" and contract["real_money"]=="NO-GO"
assert contract["unknown_never_pass"] is True
assert contract["max_kicks_per_health_run"]==1
assert int(contract["stale_after_seconds"])>=3600
assert kick["schema"]=="XRAY_SCHEDULER_KICK_V1"
assert kick["execution"]=="NONE" and kick["real_money"]=="NO-GO"
assert '"30 * * * *"' in wf or "'30 * * * *'" in wf
assert '"nasdaq-xray/scheduler_kick_dataplane.json"' in wf or "'nasdaq-xray/scheduler_kick_dataplane.json'" in wf
assert 'name: NASDAQ SWING XRAY Autonomous Data Plane' in wf
print("XRAY_SCHEDULER_FAILOVER_SELFTEST=PASS")
