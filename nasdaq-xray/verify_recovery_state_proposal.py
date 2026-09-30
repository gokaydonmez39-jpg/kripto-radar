#!/usr/bin/env python3
import hashlib, json, os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
P=ROOT/"recovery_state_proposal.json"
O=ROOT/"recovery_state_proposal_verified.json"
p=json.loads(P.read_text(encoding="utf-8"))
rev=int(p["target_revision"])
state_json=p["target_state_json"]
calc=hashlib.sha256(("XRAY_STATE_REGISTER_V1\n"+str(rev)+"\n"+state_json).encode("utf-8")).hexdigest()
expected=p["target_state_hash"]
parsed=json.loads(state_json)
checks={
 "hash_match":calc==expected,
 "target_revision_match":parsed.get("revision")==rev==21,
 "task_id_match":parsed.get("task_id")==p["canonical_task_id"],
 "asof_match":parsed.get("asof_et")=="2026-09-29",
 "status_match":parsed.get("status")=="RECOVERY_REBASED_MASTER_PENDING",
 "phase_match":(parsed.get("work_cursor") or {}).get("PHASE")=="MASTER_IDENTITY",
 "cursor_zero":(parsed.get("work_cursor") or {}).get("CHUNK_INDEX")==0,
 "no_active_signals":parsed.get("active_signals")==[],
 "no_r92":parsed.get("r92")==[],
 "no_r93":parsed.get("r93")==[],
 "no_carryforward":(parsed.get("recovery_rebase") or {}).get("incomplete_results_carried_forward") is False,
 "source_hash_bound":(parsed.get("recovery_rebase") or {}).get("from_state_hash")==p["source_state_hash"],
 "witness_hash_bound":(parsed.get("recovery_rebase") or {}).get("settlement_witness_hash")==p["recovery_witness_hash"],
}
out={
 "schema":"XRAY_RECOVERY_STATE_PROPOSAL_VERIFY_V1",
 "source_proposal":"recovery_state_proposal.json",
 "github_sha":os.getenv("GITHUB_SHA"),
 "computed_state_hash":calc,
 "expected_state_hash":expected,
 "checks":checks,
 "result":"PASS" if all(checks.values()) else "FAIL",
 "execution":"NONE",
 "real_money":"NO-GO"
}
O.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(out,sort_keys=True))
if out["result"]!="PASS": raise SystemExit(2)
