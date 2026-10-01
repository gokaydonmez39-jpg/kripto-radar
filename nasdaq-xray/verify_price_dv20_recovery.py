#!/usr/bin/env python3
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
S=ROOT/"rallies_recovery_summary.json"
F=ROOT/"longbridge_fallback_recovery.json"
O=ROOT/"price_dv20_recovery_verified.json"

def sha_lines(xs):
    return hashlib.sha256("\n".join(xs).encode("utf-8")).hexdigest()

s=json.loads(S.read_text())
f=json.loads(F.read_text())

checks={}
checks["task_id_match"]=s.get("task_id")==f.get("task_id")=="6a825366222081918997094d76e6ae46"
checks["asof_match"]=s.get("asof_et")==f.get("asof_et")=="2026-09-29"
checks["identity_total"]=s.get("identity_queue_total")==3405
checks["primary_counts"]=s.get("counts")=={
  "PASS_PRICE_DV20":498,
  "FAIL_PRICE":1604,
  "FAIL_DV20":947,
  "MISSING_EXACT20":356,
}
checks["missing_count"]=len(s.get("missing_symbols") or [])==356
checks["fallback_complete"]=f.get("cursor")==356 and f.get("total_missing")==356 and f.get("status")=="COMPLETE"
checks["fallback_keyset"]=set(f.get("results") or {})==set(s.get("missing_symbols") or [])
dist={}
for sym,v in (f.get("results") or {}).items():
    st=v.get("status")
    dist[st]=dist.get(st,0)+1
checks["fallback_distribution"]=dist=={
  "FAIL_DV20":194,
  "FAIL_PRICE":127,
  "UNKNOWN_EXACT20_MISSING":35,
}
checks["fallback_no_pass"]=not any(str(v.get("status","")).startswith("PASS") for v in (f.get("results") or {}).values())
checks["pass_symbol_hash"]=sha_lines(sorted(s.get("pass_symbols") or []))==s.get("group_hashes",{}).get("PASS_PRICE_DV20")
fallback_serial=[]
for sym in sorted(f.get("results") or {}):
    v=f["results"][sym]
    fallback_serial.append(sym+"|"+json.dumps(v,sort_keys=True,separators=(",",":")))
fallback_hash=sha_lines(fallback_serial)

final_counts={
  "PASS_PRICE_DV20":498,
  "FAIL_PRICE":1604+127,
  "FAIL_DV20":947+194,
  "UNKNOWN_EXACT20":35,
}
checks["final_total"]=sum(final_counts.values())==3405

manifest={
  "schema":"XRAY_PRICE_DV20_RECOVERY_VERIFIED_V1",
  "task_id":"6a825366222081918997094d76e6ae46",
  "asof_et":"2026-09-29",
  "execution":"NONE",
  "real_money":"NO-GO",
  "unknown_never_pass":True,
  "identity_queue_total":3405,
  "identity_queue_hash":s.get("identity_queue_hash"),
  "primary_classification_hash":s.get("classification_hash"),
  "primary_group_hashes":s.get("group_hashes"),
  "fallback_source_missing_hash":f.get("source_missing_group_hash"),
  "fallback_result_hash":fallback_hash,
  "fallback_distribution":dist,
  "final_counts":final_counts,
  "final_pass_count":498,
  "final_pass_hash":s.get("group_hashes",{}).get("PASS_PRICE_DV20"),
  "final_pass_symbols":s.get("pass_symbols"),
  "checks":checks,
  "status":"PASS" if all(checks.values()) else "FAIL",
  "verified_at_utc":datetime.now(timezone.utc).isoformat(),
  "usage_boundary":"ZERO_ALPHA_RECOVERY_EVIDENCE_ONLY;NOT_G9;NOT_DIRECT_STATE_WRITE;CONSUME_ONLY_AFTER_REV21_AND_CANONICAL_IDENTITY_BIND",
}
manifest["manifest_hash"]=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
O.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
print(json.dumps({k:manifest[k] for k in ["status","final_counts","fallback_distribution","fallback_result_hash","manifest_hash"]},sort_keys=True))
if manifest["status"]!="PASS":
    raise SystemExit(2)
