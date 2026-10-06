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
def master_identity_partition_integrity(master):
    mp=master.get("completion_proof",{}) or {}
    try:
        passes=list(master.get("pass_symbols") or [])
        unknowns=list(master.get("unknown_symbols") or [])
        pset=set(passes); uset=set(unknowns)
        pc=int(master.get("pass_count",-1)); uc=int(master.get("unknown_count",-1))
        qt=int(master.get("queue_total",-1)); raw=int(master.get("raw_identity_total",-1))
    except Exception:
        return False
    status_ok=(
        (uc==0 and master.get("status")=="HISTORY_COMPLETE")
        or (uc>0 and master.get("status")=="PARTIAL_UNKNOWN")
    )
    return bool(
        master.get("schema")=="XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1"
        and master.get("unknown_never_pass") is True
        and status_ok
        and pc==qt==len(passes)==len(pset)
        and uc==len(unknowns)==len(uset)
        and not (pset & uset)
        and raw==pc+uc
        and mp.get("identity_authority_v6") is True
        and mp.get("authority_full_identity") is True
        and mp.get("full_identity") is True
        and mp.get("queue_hash_exact") is True
        and mp.get("queue_total_exact") is True
        and mp.get("queue_unique") is True
        and mp.get("asof_identity_proof_binding") is True
        and mp.get("sec_spac_proof_binding") is True
        and mp.get("identity_partition_policy_exact") is True
        and mp.get("identity_unknown_partition_exact") is True
    )

def main():
    master=load("canonical_current_master_manifest.json")
    price=load("canonical_current_price_dv30.json")
    event=load("canonical_current_event_state.json")
    terminal=load("canonical_current_terminal.json")
    pit=load("canonical_official_source_guard.json")
    lineage=load("canonical_data_lineage_registry.json")
    replay=load("canonical_replay_guard.json")
    ledger=load("provider_health_ledger.json")
    delivery=load("delivery_ledger.json")
    pointer=load("chatgpt_canonical_state_v2.json")
    checks=[]; add=lambda name,state,detail: checks.append({"name":name,"state":state,"detail":detail})
    mp=master.get("completion_proof",{})
    master_identity_ok=master_identity_partition_integrity(master)
    master_unknown=master.get("unknown_count")
    add("master_identity","PASS" if master_identity_ok else "FAIL",{
      "authority":master.get("identity_authority"),
      "identity_authority_v6":mp.get("identity_authority_v6"),
      "authority_full_identity":mp.get("authority_full_identity"),
      "partition_integrity":master_identity_ok,
      "coverage_complete":master_unknown==0,
      "coverage_status":"COMPLETE" if master_unknown==0 else "PARTIAL_UNKNOWN",
      "pass_count":master.get("pass_count"),
      "unknown_count":master_unknown,
      "raw_identity_total":master.get("raw_identity_total")
    })
    pc=price.get("pass_count"); uc=price.get("unknown_count")
    add("price_dv30_counts","PASS" if price.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1" and isinstance(pc,int) and isinstance(uc,int) and pc>=0 and uc>=0 else "UNKNOWN",{"pass_count":pc,"unknown_count":uc,"schema":price.get("schema")})
    if terminal.get("status")=="FULL_E2E_RESEARCH_PASS":
        add("event_complete_for_terminal","PASS" if event.get("affected_geometry_event_unknown_count")==0 else "FAIL",event.get("affected_geometry_event_unknown_count"))
    else:
        add("event_complete_for_terminal","NOT_APPLICABLE",terminal.get("status"))
    add("official_source_guard","PASS" if pit.get("status")=="PASS" else "DEGRADED",pit.get("status"))
    ps=pointer.get("state_json") or {}
    if isinstance(ps,str):
        try: ps=json.loads(ps)
        except Exception: ps={}
    candidate_symbols=sorted({
        str(x.get("symbol") or "").upper()
        for x in (ps.get("r92") or [])
        if isinstance(x,dict) and x.get("delivery_key") and x.get("symbol")
    })
    src=pit.get("sources") or {}
    halt=(src.get("trade_halts") or {})
    sec=(src.get("security_status") or {})
    safety=pit.get("candidate_safety") or {}
    veto=set(str(x).upper() for x in (safety.get("veto_symbols") or []))
    veto |= set(str(x).upper() for x in (halt.get("active_halt_symbols") or []))
    veto |= set(str(x).upper() for x in (sec.get("suspension_symbols") or []))
    intersection=sorted(set(candidate_symbols)&veto)
    official_safety_pass=(halt.get("status")=="PASS" and sec.get("status")=="PASS")
    if not official_safety_pass:
        add("candidate_official_safety_guard","FAIL" if candidate_symbols else "DEGRADED",{
          "halt_feed_status":halt.get("status"),"security_status_feed":sec.get("status"),
          "registered_candidates":candidate_symbols
        })
    else:
        add("candidate_official_safety_guard","FAIL" if intersection else "PASS",{
          "registered_candidates":candidate_symbols,"veto_intersection":intersection,
          "veto_symbol_count":len(veto)
        })
    add("lineage_registry","PASS" if lineage.get("status") in {"COMPLETE_LINEAGE","COMPLETE_LINEAGE_SCHEMA"} else "DEGRADED",lineage.get("status"))
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
