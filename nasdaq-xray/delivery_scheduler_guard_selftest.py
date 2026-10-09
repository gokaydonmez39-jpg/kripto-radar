#!/usr/bin/env python3
from datetime import datetime,timezone
from pathlib import Path
from delivery_scheduler_guard import evaluate_readiness

CONTRACT={
  "schema":"XRAY_SCHEDULER_FAILOVER_CONTRACT_V1",
  "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
  "stale_after_seconds":4500,
}
NOW=datetime(2026,10,5,21,0,tzinfo=timezone.utc)

def run(status="completed",conclusion="success",created="2026-10-05T20:20:00Z",updated="2026-10-05T20:50:00Z"):
    return {"status":status,"conclusion":conclusion,"created_at":created,"updated_at":updated}

root_kick={"requested_at_utc":"2026-10-05T20:00:00Z"}
final_kick={"requested_at_utc":"2026-10-05T20:00:00Z"}
root=[run()]
final=[run(created="2026-10-05T20:25:00Z",updated="2026-10-05T20:40:00Z")]

ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,root,final)
assert ok and why=="PASS",(ok,why)

ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,root+[run(status="queued",conclusion=None)],final)
assert not ok and why=="ROOT_RECOVERY_ACTIVE",(ok,why)

ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,root,final+[run(status="in_progress",conclusion=None)])
assert not ok and why=="FINAL_RECOVERY_ACTIVE",(ok,why)

# The old implementation blocked on any queued job forever, even after a
# newer successful recovery. Prove both the recoverable and unrecovered paths.
root_old_zombie=run(status="queued",conclusion=None,
                    created="2026-10-05T18:00:00Z",updated="2026-10-05T18:00:00Z")
final_old_zombie=run(status="in_progress",conclusion=None,
                     created="2026-10-05T18:00:00Z",updated="2026-10-05T18:00:00Z")
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root+[root_old_zombie],final)
assert ok and why=="PASS",(ok,why)
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root,final+[final_old_zombie])
assert ok and why=="PASS",(ok,why)
root_new_orphan=run(status="queued",conclusion=None,
                    created="2026-10-05T19:00:00Z",updated="2026-10-05T19:00:00Z")
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          [root_new_orphan],final)
assert not ok and why=="ROOT_ORPHAN_UNRECOVERED",(ok,why)
final_new_orphan=run(status="in_progress",conclusion=None,
                     created="2026-10-05T19:00:00Z",updated="2026-10-05T19:00:00Z")
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root,[final_new_orphan])
assert not ok and why=="FINAL_ORPHAN_UNRECOVERED",(ok,why)
bad_status=run(status="unexpected",conclusion=None)
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root+[bad_status],final)
assert not ok and why=="ROOT_UNKNOWN_ACTIONS_RUN_STATUS",(ok,why)
bad_clock=run(status="queued",conclusion=None,created="NAIVE",
              updated="2026-10-05T20:50:00Z")
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root+[bad_clock],final)
assert not ok and why=="ROOT_ACTION_RUN_TIME_INVALID",(ok,why)
future=run(status="queued",conclusion=None,
           created="2026-10-05T21:10:00Z",updated="2026-10-05T21:10:00Z")
ok,why=evaluate_readiness(NOW,CONTRACT,root_kick,final_kick,
                          root+[future],final)
assert not ok and why=="ROOT_ACTION_RUN_FROM_FUTURE",(ok,why)

late_kick={"requested_at_utc":"2026-10-05T20:55:00Z"}
ok,why=evaluate_readiness(NOW,CONTRACT,late_kick,final_kick,root,final)
assert not ok and why=="ROOT_KICK_SUCCESS_NOT_OBSERVED",(ok,why)

stale_root=[run(created="2026-10-05T17:00:00Z",updated="2026-10-05T17:10:00Z")]
old_kick={"requested_at_utc":"2026-10-05T16:00:00Z"}
ok,why=evaluate_readiness(NOW,CONTRACT,old_kick,final_kick,stale_root,final)
assert not ok and why=="ROOT_SUCCESS_STALE",(ok,why)

# Sunday: age alone is not a delivery veto, but active/unwitnessed recovery still is.
SUN=datetime(2026,10,4,21,0,tzinfo=timezone.utc)
sun_root=[run(created="2026-10-04T12:00:00Z",updated="2026-10-04T12:10:00Z")]
sun_root_kick={"requested_at_utc":"2026-10-04T11:00:00Z"}
sun_final=[run(created="2026-10-04T12:30:00Z",updated="2026-10-04T12:40:00Z")]
sun_final_kick={"requested_at_utc":"2026-10-04T11:00:00Z"}
ok,why=evaluate_readiness(SUN,CONTRACT,sun_root_kick,sun_final_kick,sun_root,sun_final)
assert ok and why=="PASS",(ok,why)

workflow=(Path(__file__).resolve().parent.parent/".github/workflows/nasdaq-xray-delivery.yml").read_text()
assert 'workflow_run:' in workflow
assert 'workflows: ["XRAY Canonical Current Final Factory", "NASDAQ SWING XRAY Autonomous Data Plane"]' in workflow
assert "github.event.workflow_run.conclusion == 'success'" in workflow

print("XRAY_DELIVERY_SCHEDULER_GUARD_SELFTEST=PASS")
