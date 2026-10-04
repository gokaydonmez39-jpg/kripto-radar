#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_replay_guard.json"
FILES=[
 "chatgpt_compiled_policy_v3.json","canonical_current_master_manifest.json","canonical_current_price_dv20.json",
 "canonical_current_history.json","canonical_current_legal.json","canonical_current_stage1.json","canonical_current_regime.json",
 "canonical_current_deep_geometry.json","canonical_current_event_state.json","canonical_current_final_tech.json",
 "canonical_current_terminal.json","chatgpt_canonical_state_v2.json"
]
def now(): return datetime.now(timezone.utc).isoformat()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    try:return json.loads(p.read_text())
    except Exception:return {}
def cand_keys(pointer):
    s=pointer.get("state_json") or {}
    if isinstance(s,str):
        try:s=json.loads(s)
        except Exception:s={}
    return sorted(str(x.get("delivery_key")) for x in (s.get("r92") or []) if isinstance(x,dict) and x.get("delivery_key"))
def main():
    prev=load(OUT) if OUT.exists() else {}
    rows=[]; asofs=set()
    for fn in FILES:
        p=ROOT/fn
        if not p.exists():
            rows.append({"path":fn,"status":"MISSING"}); continue
        j=load(p); a=j.get("asof_et") or j.get("ASOF_ET")
        if a: asofs.add(str(a))
        rows.append({"path":fn,"status":"PRESENT","sha256":digest(p),"schema":j.get("schema"),"asof_et":a})
    ptr=load(ROOT/"chatgpt_canonical_state_v2.json"); keys=cand_keys(ptr)
    old=prev.get("candidate_delivery_keys") or []
    out={"schema":"XRAY_DETERMINISTIC_REPLAY_GUARD_V1","execution":"NONE","real_money":"NO-GO","alpha_authority":False,
         "unknown_never_pass":True,"artifacts":rows,"asof_values":sorted(asofs),
         "asof_consistent":len(asofs)<=1,"candidate_delivery_keys":keys,
         "semantic_diff":{"added":sorted(set(keys)-set(old)),"removed":sorted(set(old)-set(keys)),"unchanged":sorted(set(old)&set(keys))},
         "replay_rule":"ONLY_FROZEN_ASOF_EVIDENCE_MAY_BE_USED; LATER_VINTAGES_NEVER_BACKFILL_PRIOR_DECISION",
         "status":"PASS" if all(x["status"]=="PRESENT" for x in rows) and len(asofs)<=1 else "FAIL_CLOSED",
         "generated_at_utc":now()}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"asofs":out["asof_values"],"candidates":len(keys)},sort_keys=True))
if __name__=="__main__": main()
