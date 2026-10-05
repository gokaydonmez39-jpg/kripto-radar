#!/usr/bin/env python3
from datetime import datetime,timezone
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

print("XRAY_DELIVERY_SCHEDULER_GUARD_SELFTEST=PASS")
