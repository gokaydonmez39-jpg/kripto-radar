#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_MASTER_STATE",str(ROOT/"canonical_current_full_state.json")))
OUT=Path(os.getenv("XRAY_MASTER_MANIFEST",str(ROOT/"canonical_current_master_manifest.json")))
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(p):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def main():
    s=json.loads(INPUT.read_text())
    assert s["schema"]=="XRAY_NASDAQ_SCREENER_SINA_V2" and s["task_id"]==TASK
    q=s["queue"];r=s["results"]
    proof={
      "queue_unique":len(set(q))==len(q),
      "queue_result_cardinality_exact":len(q)==len(r),
      "cursor_complete":int(s.get("cursor",0))==len(q),
      "pending_retry_zero":int(s.get("pending_retry",0))==0,
      "unknown_zero":int(s.get("unknown_count",0))==0,
      "full_identity":bool((s.get("discovery_meta") or {}).get("full_identity")),
      "authority_full_identity":(s.get("discovery_meta") or {}).get("authority")=="FULL_IDENTITY_NO_PREFILTER",
    }
    complete=all(proof.values())
    passes=sorted(k for k,v in r.items() if v.get("status")=="PASS")
    obj={
      "schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1","task_id":TASK,
      "asof_et":s["asof_et"],"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "status":"HISTORY_COMPLETE" if complete else "PARTIAL",
      "queue_total":len(q),"queue_hash":s["queue_hash"],"queue_unique":len(set(q)),
      "unknown_count":int(s.get("unknown_count",0)),"pending_retry":int(s.get("pending_retry",0)),
      "pass_count":len(passes),"pass_hash":hashlib.sha256("\n".join(passes).encode()).hexdigest(),
      "counts":s.get("counts") or {},"official_footer":s.get("official_footer"),
      "identity_authority":s.get("identity_authority"),
      "source_state_path":str(INPUT.relative_to(ROOT.parent)).replace("\\","/") if INPUT.is_relative_to(ROOT.parent) else str(INPUT),
      "source_state_blob_sha":blob_sha(INPUT),"source_state_hash":s.get("state_hash"),
      "completion_proof":proof
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":obj["asof_et"],"status":obj["status"],"queue_total":obj["queue_total"],"unknown_count":obj["unknown_count"],"pass_count":obj["pass_count"]},sort_keys=True))
if __name__=="__main__": main()
