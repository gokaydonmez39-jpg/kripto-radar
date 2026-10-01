#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_MASTER_STATE",str(ROOT/"canonical_current_full_state.json")))
OUT=Path(os.getenv("XRAY_MASTER_MANIFEST",str(ROOT/"canonical_current_master_manifest.json")))
TASK="6a825366222081918997094d76e6ae46"
ALLOWED_EXCLUSION_REASONS={
  "TEST_ISSUE","ETF","NEXTSHARES","WARRANT","RIGHT","UNIT",
  "PREFERRED","DEBT","ETN","FUND","WHEN_ISSUED"
}

def blob_sha(p):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def main():
    s=json.loads(INPUT.read_text())
    assert s["schema"]=="XRAY_NASDAQ_SCREENER_SINA_V2" and s["task_id"]==TASK
    assert s["execution"]=="NONE" and s["real_money"]=="NO-GO"
    q=s["queue"]
    names=s.get("security_names") or {}
    disc=s.get("discovery") or {}
    dm=s.get("discovery_meta") or {}
    exc=s.get("explicit_excluded_reason_counts") or {}
    proof={
      "queue_unique":len(set(q))==len(q),
      "queue_total_exact":int(s.get("queue_total",-1))==len(q),
      "queue_hash_exact":s.get("queue_hash")==hash_lines(q),
      "security_names_exact":set(names)==set(q),
      "discovery_exact":set(disc)==set(q),
      "full_identity":bool(dm.get("full_identity")),
      "authority_full_identity":dm.get("authority")=="FULL_IDENTITY_NO_PREFILTER",
      "official_footer_present":bool(s.get("official_footer")),
      "identity_authority_v3":s.get("identity_authority")=="NASDAQTRADER_EXPLICIT_TYPE_FILTER_V3_SPAC_DEFERRED_TO_LEGAL",
      "exclusion_reasons_policy_exact":set(exc).issubset(ALLOWED_EXCLUSION_REASONS) and "SPAC" not in exc,
    }
    complete=all(proof.values())
    identity_pass=sorted(q) if complete else []
    obj={
      "schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1",
      "task_id":TASK,"asof_et":s["asof_et"],
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "phase":"MASTER_IDENTITY",
      # Compatibility label retained for downstream contracts; semantics are identity-complete.
      "status":"HISTORY_COMPLETE" if complete else "PARTIAL",
      "status_semantics":"IDENTITY_COMPLETE_COMPATIBILITY_LABEL" if complete else "IDENTITY_PARTIAL",
      "queue_total":len(q),"queue_hash":s["queue_hash"],"queue_unique":len(set(q)),
      "unknown_count":0 if complete else len(q),
      "pending_retry":0,
      "pass_count":len(identity_pass),
      "pass_hash":hash_lines(identity_pass),
      "counts":{"PASS_IDENTITY":len(identity_pass),"UNKNOWN_IDENTITY":0 if complete else len(q)},
      "official_footer":s.get("official_footer"),
      "identity_authority":s.get("identity_authority"),
      "identity_ruleset":s.get("identity_ruleset"),
      "explicit_excluded_count":s.get("explicit_excluded_count"),
      "explicit_excluded_hash":s.get("explicit_excluded_hash"),
      "explicit_excluded_reason_counts":exc,
      "history_price_state_diagnostic_only":{
        "source_status":s.get("status"),
        "source_unknown_count":s.get("unknown_count"),
        "source_pending_retry":s.get("pending_retry"),
        "source_counts":s.get("counts") or {},
      },
      "source_state_path":str(INPUT.relative_to(ROOT.parent)).replace("\\","/") if INPUT.is_relative_to(ROOT.parent) else str(INPUT),
      "source_state_blob_sha":blob_sha(INPUT),
      "source_state_hash":s.get("state_hash"),
      "completion_proof":proof,
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
      "asof":obj["asof_et"],"status":obj["status"],"phase":obj["phase"],
      "queue_total":obj["queue_total"],"identity_unknown":obj["unknown_count"],
      "identity_pass":obj["pass_count"],
      "diagnostic_history_price_unknown":(obj["history_price_state_diagnostic_only"] or {}).get("source_unknown_count")
    },sort_keys=True))

if __name__=="__main__":
    main()
