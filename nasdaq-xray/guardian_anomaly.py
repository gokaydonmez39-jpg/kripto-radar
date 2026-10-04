#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_guardian_state.json"
def now():return datetime.now(timezone.utc).isoformat()
def load(fn):
    try:return json.loads((ROOT/fn).read_text())
    except Exception:return {}
def main():
    master=load("canonical_current_master_manifest.json")
    price=load("canonical_current_price_dv20.json")
    event=load("canonical_current_event_state.json")
    terminal=load("canonical_current_terminal.json")
    pit=load("canonical_official_source_guard.json")
    lineage=load("canonical_data_lineage_registry.json")
    replay=load("canonical_replay_guard.json")
    ledger=load("provider_health_ledger.json")
    delivery=load("delivery_ledger.json")
    checks=[]; add=lambda name,state,detail: checks.append({"name":name,"state":state,"detail":detail})
    add("master_identity","PASS" if master.get("completion_proof",{}).get("identity_authority_v3") is True else "FAIL","official identity proof")
    pc=price.get("pass_count"); uc=price.get("unknown_count")
    add("price_dv20_counts","PASS" if isinstance(pc,int) and isinstance(uc,int) and pc>=0 and uc>=0 else "UNKNOWN",{"pass_count":pc,"unknown_count":uc})
    if terminal.get("status")=="FULL_E2E_RESEARCH_PASS":
        add("event_complete_for_terminal","PASS" if event.get("affected_geometry_event_unknown_count")==0 else "FAIL",event.get("affected_geometry_event_unknown_count"))
    else:
        add("event_complete_for_terminal","NOT_APPLICABLE",terminal.get("status"))
    add("official_source_guard","PASS" if pit.get("status")=="PASS" else "DEGRADED",pit.get("status"))
    add("lineage_registry","PASS" if lineage.get("status")=="COMPLETE_LINEAGE" else "DEGRADED",lineage.get("status"))
    add("deterministic_replay","PASS" if replay.get("status")=="PASS" else "FAIL",replay.get("status"))
    bad_delivery=[k for k,v in (delivery.get("deliveries") or {}).items() if v.get("backup_issue_status") not in {None,"DELIVERED"}]
    add("delivery_ledger","PASS" if not bad_delivery else "FAIL",{"missing_or_failed":bad_delivery})
    core_bad=[]
    for name,st in (ledger.get("providers") or {}).items():
        if st.get("status") in {"CIRCUIT_OPEN"}: core_bad.append(name)
    add("provider_circuit_breakers","PASS" if not core_bad else "FAIL",core_bad)
    hard_fail=any(x["state"]=="FAIL" for x in checks)
    degraded=any(x["state"] in {"DEGRADED","UNKNOWN"} for x in checks)
    out={"schema":"XRAY_GUARDIAN_STATE_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "unknown_never_pass":True,"self_healing_may_not_change_alpha":True,"checks":checks,
         "status":"FAIL_CLOSED" if hard_fail else ("DEGRADED" if degraded else "PASS"),"generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"checks":{x["name"]:x["state"] for x in checks}},sort_keys=True))
if __name__=="__main__": main()
