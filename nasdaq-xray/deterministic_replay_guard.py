#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"canonical_replay_guard.json"
POLICY_FILE="chatgpt_compiled_policy_v3.json"
PRICE_FILE="canonical_current_price_dv30.json"
POINTER_FILE="chatgpt_canonical_state_v2.json"
FILES=[
 POLICY_FILE,"canonical_current_master_manifest.json",PRICE_FILE,
 "canonical_current_history.json","canonical_current_legal.json","canonical_current_stage1.json","canonical_current_regime.json",
 "canonical_current_deep_geometry.json","canonical_current_event_state.json","canonical_current_final_tech.json",
 "canonical_current_terminal.json",POINTER_FILE
]

def now(): return datetime.now(timezone.utc).isoformat()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    try:return json.loads(p.read_text())
    except Exception:return {}

def artifact_asof(fn,j):
    a=j.get("asof_et") or j.get("ASOF_ET")
    if a:return str(a)
    if fn==POINTER_FILE:
        s=j.get("state_json") or {}
        if isinstance(s,str):
            try:s=json.loads(s)
            except Exception:s={}
        a=s.get("asof_et") or s.get("ASOF_ET")
        if a:return str(a)
    return None

def policy_binding_ok(policy):
    try:
        payload=policy.get("payload_json") or {}
        if isinstance(payload,str):payload=json.loads(payload)
        hard=payload.get("hard_gates") or {}
        return (
            str(payload.get("version"))=="C4.17"
            and "dv30" in hard
            and "exactly30" in str(hard.get("dv30") or "").replace(" ","").lower()
            and "dv20" not in str(hard).lower()
        )
    except Exception:
        return False

def cand_keys(pointer):
    s=pointer.get("state_json") or {}
    if isinstance(s,str):
        try:s=json.loads(s)
        except Exception:s={}
    return sorted(str(x.get("delivery_key")) for x in (s.get("r92") or []) if isinstance(x,dict) and x.get("delivery_key"))

def main():
    prev=load(OUT) if OUT.exists() else {}
    rows=[];research_asofs=set();pointer_asof=None
    for fn in FILES:
        p=ROOT/fn
        if not p.exists():
            rows.append({"path":fn,"status":"MISSING"});continue
        j=load(p);a=artifact_asof(fn,j)
        if a:
            if fn==POINTER_FILE:pointer_asof=a
            else:research_asofs.add(a)
        rows.append({"path":fn,"status":"PRESENT","sha256":digest(p),"schema":j.get("schema"),"asof_et":a})
    ptr=load(ROOT/POINTER_FILE);keys=cand_keys(ptr)
    old=prev.get("candidate_delivery_keys") or []
    policy=load(ROOT/POLICY_FILE)
    policy_ok=policy_binding_ok(policy)
    all_present=all(x["status"]=="PRESENT" for x in rows)
    asof_consistent=len(research_asofs)<=1
    target_asof=next(iter(research_asofs),None) if len(research_asofs)==1 else None
    if pointer_asof is None:
        pointer_relation="UNKNOWN_POINTER_ASOF"
    elif target_asof is None:
        pointer_relation="UNKNOWN_RESEARCH_ASOF"
    elif pointer_asof==target_asof:
        pointer_relation="EXACT_CURRENT"
    elif pointer_asof<target_asof:
        pointer_relation="LAGGING_DURABLE_POINTER_PENDING_ATOMIC_COMMIT"
    else:
        pointer_relation="FUTURE_POINTER_DRIFT"
    pointer_safe=pointer_relation in {"EXACT_CURRENT","LAGGING_DURABLE_POINTER_PENDING_ATOMIC_COMMIT"}
    out={
      "schema":"XRAY_DETERMINISTIC_REPLAY_GUARD_V2",
      "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
      "unknown_never_pass":True,
      "policy_binding":{
        "policy_path":POLICY_FILE,
        "policy_version":"C4.17",
        "price_path":PRICE_FILE,
        "dv30_exact30_bound":policy_ok,
        "legacy_dv20_forbidden":True,
      },
      "artifacts":rows,"asof_values":sorted(research_asofs),
      "asof_consistent":asof_consistent,
      "pointer_binding":{
        "pointer_path":POINTER_FILE,
        "pointer_asof":pointer_asof,
        "research_asof":target_asof,
        "epoch_relation":pointer_relation,
        "pointer_not_alpha_authority":True,
        "future_pointer_forbidden":True,
      },
      "candidate_delivery_keys":keys,
      "semantic_diff":{"added":sorted(set(keys)-set(old)),"removed":sorted(set(old)-set(keys)),"unchanged":sorted(set(old)&set(keys))},
      "replay_rule":"ONLY_FROZEN_ASOF_EVIDENCE_MAY_BE_USED; LATER_VINTAGES_NEVER_BACKFILL_PRIOR_DECISION",
      "status":"PASS" if all_present and asof_consistent and policy_ok and pointer_safe else "FAIL_CLOSED",
      "generated_at_utc":now()
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"asofs":out["asof_values"],"pointer_relation":pointer_relation,"candidates":len(keys),"policy_binding_ok":policy_ok},sort_keys=True))

if __name__=="__main__": main()
