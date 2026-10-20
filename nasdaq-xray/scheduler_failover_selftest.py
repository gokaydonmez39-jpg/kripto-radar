#!/usr/bin/env python3
from __future__ import annotations
import json
import datetime as dt
from unittest.mock import patch
from pathlib import Path
from root_weekend_quota_guard import permit_compute

ROOT=Path(__file__).resolve().parent

def _must_kick_root(*, us_weekday: bool, root_age: int, stale_after: int, has_active: bool, kick_age: int, cooldown: int, preimages_equal: bool, second_snapshot_new_run: bool, when_utc: dt.datetime | None = None) -> bool:
    # A weekday is not an official Nasdaq session.  A missing or invalid
    # calendar/time witness cannot authorize an automatic Health CAS kick.
    try:
        official_session = (when_utc is not None and permit_compute(when_utc,"schedule"))
    except Exception:
        official_session = False
    return (
        official_session
        and us_weekday
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
resilience_wf=(ROOT.parent/".github/workflows/xray-resilience-observability.yml").read_text()
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
_OPEN_NOW=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)  # Columbus Day: Nasdaq open
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False, when_utc=_OPEN_NOW) is True
assert _must_kick_root(us_weekday=False, root_age=_stale+9999, stale_after=_stale, has_active=False, kick_age=_cool+9999, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False, when_utc=_OPEN_NOW) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=True, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False, when_utc=_OPEN_NOW) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=False, when_utc=_OPEN_NOW) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=False, second_snapshot_new_run=False, when_utc=_OPEN_NOW) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale, has_active=False, kick_age=_cool+1, cooldown=_cool, preimages_equal=True, second_snapshot_new_run=True, when_utc=_OPEN_NOW) is False
# Regression: NY weekdays are NOT always Nasdaq sessions.  Observed
# Independence Day Friday must never permit unattended Health root recovery.
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale,
    has_active=False, kick_age=_cool+1, cooldown=_cool,
    preimages_equal=True, second_snapshot_new_run=False,
    when_utc=dt.datetime(2026,7,3,15,tzinfo=dt.timezone.utc)) is False
assert _must_kick_root(us_weekday=True, root_age=_stale+1, stale_after=_stale,
    has_active=False, kick_age=_cool+1, cooldown=_cool,
    preimages_equal=True, second_snapshot_new_run=False,
    when_utc=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)) is True
# Half-day is a valid Nasdaq session: do not confuse exchange closure
# with the shorter 13:00 ET close.  Christmas/Thanksgiving are not.
_BASE_KICK={"us_weekday":True,"root_age":_stale+1,"stale_after":_stale,
            "has_active":False,"kick_age":_cool+1,"cooldown":_cool,
            "preimages_equal":True,"second_snapshot_new_run":False}
for _closed in ((2026,11,26,15),(2026,12,25,15),(2026,7,3,15)):
    assert _must_kick_root(**_BASE_KICK,when_utc=dt.datetime(
        *_closed,tzinfo=dt.timezone.utc)) is False
assert _must_kick_root(**_BASE_KICK,when_utc=dt.datetime(
    2026,11,27,15,tzinfo=dt.timezone.utc)) is True
assert _must_kick_root(**_BASE_KICK,when_utc=dt.datetime(
    2026,10,13,15,tzinfo=dt.timezone.utc)) is True
assert _must_kick_root(**_BASE_KICK) is False
assert _must_kick_root(**_BASE_KICK,when_utc=dt.datetime(2026,10,13,15)) is False
with patch("root_weekend_quota_guard.mcal.get_calendar",side_effect=RuntimeError("CALENDAR_OUTAGE")):
    assert _must_kick_root(**_BASE_KICK,when_utc=dt.datetime(
        2026,10,13,15,tzinfo=dt.timezone.utc)) is False

assert contract["health_policy"]["nasdaq_exchange_session_required_for_root_kick"] is True
assert contract["health_policy"]["exchange_closed_weekday_kick_forbidden"] is True
assert contract["health_policy"]["exchange_calendar_failure"]=="BLOCK_CAS_FAIL_CLOSED"
assert contract["health_policy"]["exchange_calendar_authority"]=="ROOT_WEEKEND_QUOTA_GUARD_PERMIT_COMPUTE_SCHEDULE"

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
# An observed successful root kick must wake official safety even if the
# upstream PRICE/MC factory correctly defers with UNKNOWN.  This repairs
# freshness, not source authority or candidate eligibility.
# Pointer->Resilience workflow_run was intentionally CUT to break the
# Final->Pointer->Resilience->Final feedback cycle.  Root completion,
# pointer push fallback, schedule and independent manual dispatch remain.
# Unlike bare assert, these production topology checks also run with -O.
from workflow_run_feedback_cycle_guard import verify as _verify_cycle_cut
_pointer_wf=(ROOT.parent/".github/workflows/xray-canonical-pointer-transition.yml").read_text()
_cycle_cut=_verify_cycle_cut(resilience_wf,_pointer_wf,final_wf)
if not (_cycle_cut["preserved_root_to_resilience"] is True
        and _cycle_cut["preserved_resilience_to_final"] is True
        and _cycle_cut["preserved_final_to_pointer"] is True
        and _cycle_cut["market_or_R92_authority"] is False):
    raise RuntimeError("XRAY_FAILOVER_NEW_GRAPH_AUTHORITY_DRIFT")
_old_resilience=resilience_wf.replace(
    'workflows: ["NASDAQ SWING XRAY Autonomous Data Plane"]',
    'workflows: ["XRAY Canonical Pointer Transition", "NASDAQ SWING XRAY Autonomous Data Plane"]')
if _old_resilience == resilience_wf:
    raise RuntimeError("XRAY_FAILOVER_REGRESSION_MUTANT_NOT_CREATED")
try:
    _verify_cycle_cut(_old_resilience,_pointer_wf,final_wf)
except ValueError:
    pass
else:
    raise RuntimeError("XRAY_FAILOVER_OLD_FEEDBACK_CYCLE_FALSE_ACCEPTED")
assert "    branches: [main]" in resilience_wf
assert "if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'" in resilience_wf
assert "Persist official safety independent of blocked research pointer" in resilience_wf
assert "python nasdaq-xray/official_source_guard.py" in resilience_wf
assert 'workflows: ["XRAY Resilience + Official Witnesses", "XRAY Canonical Current Post-MC Factory", "XRAY Event Official Primary Promote"]' in final_wf
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
