#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def _must_kick_root(*, us_weekday: bool, root_age: int, stale_after: int, has_active: bool, kick_age: int, cooldown: int, preimages_equal: bool, second_snapshot_new_run: bool) -> bool:
    return (
        us_weekday
        and root_age > stale_after
        and not has_active
        and kick_age > cooldown
        and preimages_equal
        and not second_snapshot_new_run
    )

contract=json.loads((ROOT/"scheduler_failover_contract.json").read_text())
kick=json.loads((ROOT/"scheduler_kick_dataplane.json").read_text())
final_kick=json.loads((ROOT/"scheduler_kick_final.json").read_text())
final_wf=(ROOT.parent/".github/workflows/xray-canonical-current-final.yml").read_text()
wf=(ROOT.parent/".github/workflows/nasdaq-xray-daily.yml").read_text()
orch=(ROOT/"orchestrator_run.py").read_text()

assert contract["schema"]=="XRAY_SCHEDULER_FAILOVER_CONTRACT_V1"
assert contract["execution"]=="NONE" and contract["real_money"]=="NO-GO"
assert contract["unknown_never_pass"] is True
assert contract["max_kicks_per_health_run"]==1
assert int(contract["stale_after_seconds"])>=3600
assert 2700 <= int(contract["root_active_run_grace_seconds"]) <= 3600
assert 3000 <= int(contract["final_active_run_grace_seconds"]) <= 4200
assert contract["health_policy"]["active_run_suppression"] is True
assert int(contract["kick_cooldown_seconds"]) == 180
assert contract["double_actions_snapshot_required"] is True
assert int(contract["health_policy"]["kick_cooldown_seconds"]) == 180
assert contract["health_policy"]["double_actions_snapshot_required"] is True
assert contract["health_policy"]["weekday_time_zone"]=="America/New_York"
assert contract["health_policy"]["preopen_priority_window_is_gate"] is False
assert contract["health_policy"]["stale_root_action"]=="CAS_KICK_REQUIRED_ON_US_WEEKDAY_WHEN_PREDICATES_TRUE"
assert contract["health_policy"]["health_action_omission_is_fault"] is True
assert contract["health_policy"]["weekend_age_only_kick_forbidden"] is True

_stale=int(contract["stale_after_seconds"])
_cool=int(contract["kick_cooldown_seconds"])
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False) is True
assert _must_kick_root(us_weekday=False, root_age=_stale+9999, stale_after=_stale, has_active=False, kick_age=_cool+9999, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=True, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=False, second_snapshot_new_run=False) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=True) is False
assert "requested_at_utc" in contract["kick_lease_rule"]
assert "queued/in_progress" in contract["kick_lease_rule"]
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
assert '"nasdaq-xray/alpha_semantics.py"' in wf
assert '"nasdaq-xray/test_alpha_semantics.py"' in wf
assert '"nasdaq-xray/history_official_identity_evidence.json"' in wf
assert '"nasdaq-xray/requirements-runtime.txt"' in wf
assert "python nasdaq-xray/test_alpha_semantics.py" in wf
assert 'name: NASDAQ SWING XRAY Autonomous Data Plane' in wf
assert '"nasdaq-xray/final_tech_shadow.py"' not in wf
assert "nasdaq-xray/final_tech_shadow.json" not in wf
assert 'run("final_tech_shadow.py")' not in orch
assert '"XRAY_DEEP_GEOMETRY_ONLY":"1"' in orch
assert '"status":"DEFERRED_TO_CANONICAL_FINAL_FACTORY"' in orch
assert '"alpha_semantics.py"' in orch
assert '"history_official_identity_evidence.json"' in orch
assert "CANONICAL_EVENTS_LEGAL_R1_RR_LIFECYCLE_DEFERRED" in orch
print("XRAY_SCHEDULER_FAILOVER_SELFTEST=PASS")
