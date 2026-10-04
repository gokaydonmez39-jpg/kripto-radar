#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GUARD=ROOT/"canonical_official_source_guard.json"
OUT=ROOT/"official_pit_ledger.json"

def now():
    return datetime.now(timezone.utc).isoformat()

def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def h(obj):
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()

def main():
    if not GUARD.exists():
        raise RuntimeError("OFFICIAL_SOURCE_GUARD_MISSING")
    g=json.loads(GUARD.read_text(encoding="utf-8"))
    if g.get("schema")!="XRAY_OFFICIAL_SOURCE_GUARD_V1":
        raise RuntimeError("OFFICIAL_SOURCE_GUARD_SCHEMA_FAIL")
    try:
        out=json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        out={
            "schema":"XRAY_OFFICIAL_PIT_LEDGER_V1",
            "execution":"NONE",
            "real_money":"NO-GO",
            "alpha_authority":False,
            "append_only_semantics":True,
            "unknown_never_pass":True,
            "snapshots":[]
        }
    if out.get("schema")!="XRAY_OFFICIAL_PIT_LEDGER_V1":
        raise RuntimeError("PIT_LEDGER_SCHEMA_FAIL")
    snaps=out.setdefault("snapshots",[])
    seen={(x.get("source"),x.get("payload_sha256")) for x in snaps if isinstance(x,dict)}
    added=0
    for source,payload in sorted((g.get("sources") or {}).items()):
        ph=h(payload)
        key=(source,ph)
        if key in seen:
            continue
        snaps.append({
            "source":source,
            "payload_sha256":ph,
            "observed_at_utc":now(),
            "guard_generated_at_utc":g.get("generated_at_utc"),
            "source_status":payload.get("status"),
            "payload":payload
        })
        seen.add(key); added+=1
    # Candidate-safety state is also persisted as a separate immutable observation.
    safety=g.get("candidate_safety") or {}
    if safety:
        ph=h(safety); key=("candidate_safety",ph)
        if key not in seen:
            snaps.append({
                "source":"candidate_safety",
                "payload_sha256":ph,
                "observed_at_utc":now(),
                "guard_generated_at_utc":g.get("generated_at_utc"),
                "source_status":safety.get("halt_guard_status"),
                "payload":safety
            })
            added+=1
    out["snapshot_count"]=len(snaps)
    out["last_ingest_at_utc"]=now()
    out["status"]="PASS" if g.get("status")=="PASS" else "DEGRADED"
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"snapshot_count":len(snaps),"added":added},sort_keys=True))

if __name__=="__main__":
    main()
