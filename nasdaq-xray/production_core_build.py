#!/usr/bin/env python3
"""Build fail-closed zero-key XRAY shadow CURRENT_CORE for autonomous GitHub data plane.
This is not the ChatGPT canonical Durable State authority.
"""
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
MC=ROOT/"mc_zero_key_state.json"
SINA=ROOT/"sina_candidates.json"
OUT=ROOT/"production_core_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"

mc=json.loads(MC.read_text())
sc=json.loads(SINA.read_text())
if mc.get("schema")!="XRAY_MC_ZERO_KEY_V3":
    raise RuntimeError("MC_STATE_SCHEMA_MISMATCH")
if mc.get("status")!="READY":
    raise RuntimeError("MC_STATE_NOT_READY")
if mc.get("execution")!="NONE" or mc.get("real_money")!="NO-GO" or mc.get("unknown_never_pass") is not True:
    raise RuntimeError("MC_STATE_SAFETY_MISMATCH")
if mc.get("alpha_authority") is not False or mc.get("pit_safe_shadow") is not True:
    raise RuntimeError("MC_STATE_PIT_AUTHORITY_MISMATCH")
if mc.get("asof_et")!=sc.get("asof_et"):
    raise RuntimeError("ASOF_MISMATCH_MC_SINA")
core=sorted(set(mc.get("current_core_zero_key") or []))
cand=set((sc.get("candidates") or {}).keys())
if any(s not in cand for s in core):
    raise RuntimeError("CORE_NOT_SUBSET_HARDGATE_CANDIDATES")
fallback_watch=sorted(set(mc.get("fallback_watch_symbols") or []) & set(core))
state_caps={s:("WATCH" if s in fallback_watch else "NORMAL") for s in core}
r92_ineligible=list(fallback_watch)
serial="\n".join(core)
out={
  "schema":"XRAY_EXTERNAL_ZERO_KEY_CORE_V1",
  "status":"READY",
  "task_id":TASK_ID,
  "asof_et":mc["asof_et"],
  "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
  "authority":"EXTERNAL_SHADOW_DATA_PLANE_NOT_CANONICAL_DURABLE_STATE",
  "current_core_mc_pass":core,
  "current_core_count":len(core),
  "current_core_hash":hashlib.sha256(serial.encode()).hexdigest(),
  "state_caps":state_caps,
  "fallback_watch_symbols":fallback_watch,
  "r92_ineligible":r92_ineligible,
  "mc_unresolved":mc.get("unresolved") or {},
  "mc_unresolved_count":mc.get("unresolved_count",0),
  "mc_definitive_fail":mc.get("definitive_fail") or {},
  "mc_policy":"BIGDATA_EXACT_XNAS_PRIMARY;RALLIES_XNAS_PLUS_LONGBRIDGE_NASD_FALLBACK_REQUIRES_BOTH_GE_2_1B_REL_DIFF_LE_10PCT_AND_CAPS_WATCH_R92_FALSE",
  "updated_at_utc":datetime.now(timezone.utc).isoformat()
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps({"asof":out["asof_et"],"current_core_count":len(core),"mc_unresolved_count":out["mc_unresolved_count"]},sort_keys=True))
