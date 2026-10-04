#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
contract=json.loads((ROOT/"scheduler_failover_contract.json").read_text())
kick=json.loads((ROOT/"scheduler_kick_dataplane.json").read_text())
final_kick=json.loads((ROOT/"scheduler_kick_final.json").read_text())
final_wf=(ROOT.parent/".github/workflows/xray-canonical-current-final.yml").read_text()
wf=(ROOT.parent/".github/workflows/nasdaq-xray-daily.yml").read_text()

assert contract["schema"]=="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1"
assert contract["execution"]=="NONE" and contract["real_money"]=="NO-GO"
assert contract["unknown_never_pass"] is True
assert contract["max_kicks_per_health_run"]==1
assert int(contract["stale_after_seconds"])>=3600
assert 2700 <= int(contract["root_active_run_grace_seconds"]) <= 3600
assert 3000 <= int(contract["final_active_run_grace_seconds"]) <= 4200
assert contract["health_policy"]["active_run_suppression"] is True
assert "queued or in_progress" in contract["health_policy"]["active_run_rule"]
assert kick["schema"]=="XRAY_SCHEDULER_KICK_V1"
assert kick["execution"]=="NONE" and kick["real_money"]=="NO-GO"
assert contract["final_workflow_name"]=="XRAY Canonical Current Final Factory"
assert contract["final_kick_path"]=="nasdaq-xray/scheduler_kick_final.json"
assert final_kick["schema"]=="XRAY_SCHEDULER_FINAL_KICK_V1"
assert final_kick["execution"]=="NONE" and final_kick["real_money"]=="NO-GO"
assert '"nasdaq-xray/scheduler_kick_final.json"' in final_wf or "'nasdaq-xray/scheduler_kick_final.json'" in final_wf
assert '"30 * * * *"' in wf or "'30 * * * *'" in wf
assert '"nasdaq-xray/scheduler_kick_dataplane.json"' in wf or "'nasdaq-xray/scheduler_kick_dataplane.json'" in wf
assert 'name: NASDAQ SWING XRAY Autonomous Data Plane' in wf
print("XRAY_SCHEDULER_FAILOVER_SELFTEST=PASS")
