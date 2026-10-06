#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REQ=Path(os.getenv("XRAY_EVENT_REQUEST",str(ROOT/"canonical_current_event_request.json")))
BRIDGE_ENV=os.getenv("XRAY_EVENT_BRIDGE")
OUT=Path(os.getenv("XRAY_EVENT_STATE_OUT",str(ROOT/"canonical_current_event_state.json")))
TASK="6a825366222081918997094d76e6ae46"
POLICY_BLOB="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
POLICY_HASH="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION="C4.17"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def fail_closed_discovery_coverage(ev,weekly,status,unresolved,future_sessions):
    """Allow partial provider coverage only when every uncovered symbol is explicit UNKNOWN.

    Symbols independently resolved by issuer/SEC primary evidence may be CLEAN only
    when their next official event is strictly outside the requested future horizon.
    """
    weekly=set(weekly or [])
    unresolved_keys=set((unresolved or {}).keys())
    unavailable=set(ev.get("discovery_unavailable_symbols") or [])
    resolved=set(ev.get("provider_unavailable_but_officially_resolved_symbols") or [])
    clearance=ev.get("official_horizon_clearance") or {}
    paginated=ev.get("pagination_complete") is True
    partial=ev.get("partial_data") is True

    if paginated and not unavailable:
        return True,"COMPLETE_PROVIDER_DISCOVERY"
    if not partial or not unavailable:
        return False,"PARTIAL_DISCOVERY_NOT_EXPLICIT"
    if not unavailable<=weekly or not unavailable<=unresolved_keys:
        return False,"UNAVAILABLE_SCOPE_NOT_EXACT_UNKNOWN"
    for sym in unavailable:
        rec=(unresolved or {}).get(sym) or {}
        if status.get(sym)!="UNKNOWN" or rec.get("fail_closed") is not True:
            return False,"UNAVAILABLE_SYMBOL_NOT_FAIL_CLOSED_UNKNOWN"
        if rec.get("reason") not in {
            "BIGDATA_PROVIDER_CREDIT_EXHAUSTED",
            "REQUIRED_DISCOVERY_PROVIDER_UNAVAILABLE",
            "OPTIONAL_DISCOVERY_PROVIDER_UNAVAILABLE",
            "OFFICIAL_PRIMARY_UNRESOLVED_AFTER_DIRECT_ATTEMPT",
            "OFFICIAL_PRIMARY_NOT_FOUND",
        }:
            return False,"UNAVAILABLE_REASON_NOT_ALLOWED"

    horizon=max(future_sessions or [""])
    horizon_set=set(future_sessions or [])
    if not resolved<=weekly or resolved&unresolved_keys:
        return False,"OFFICIAL_RESOLUTION_SCOPE_INVALID"
    for sym in resolved:
        rec=clearance.get(sym) or {}
        st=status.get(sym)
        if rec.get("authority") not in {"ISSUER_IR_PRIMARY","SEC_PRIMARY"}:
            return False,"OFFICIAL_RESOLUTION_AUTHORITY_INVALID"
        if not rec.get("official_source_url"):
            return False,"OFFICIAL_RESOLUTION_SOURCE_MISSING"
        nxt=str(rec.get("next_event_date") or rec.get("event_date") or "")[:10]
        if st=="CLEAN_DISCOVERY":
            if not horizon or not nxt or nxt<=horizon:
                return False,"OFFICIAL_NEXT_EVENT_NOT_OUTSIDE_HORIZON"
        elif st=="BLOCK_CONFIRMED_8SESSION":
            if not nxt or nxt not in horizon_set:
                return False,"OFFICIAL_BLOCK_EVENT_NOT_INSIDE_HORIZON"
        else:
            return False,"OFFICIAL_RESOLUTION_STATUS_INVALID"
    return True,"PARTIAL_PROVIDER_FAIL_CLOSED_WITH_DIRECT_PRIMARY_RESOLUTION"


def main():
    req=json.loads(REQ.read_text())
    asof=req["asof_et"]
    bridge=Path(BRIDGE_ENV) if BRIDGE_ENV else ROOT/f"canonical_event_bridge_{asof.replace('-','')}.json"
    if not bridge.is_absolute():
        bridge=(ROOT.parent/bridge).resolve()
    if not bridge.exists(): raise RuntimeError(f"EVENT_BRIDGE_MISSING:{bridge}")
    ev=json.loads(bridge.read_text())
    assert req["schema"]=="XRAY_EVENT_EPOCH_REQUEST_V1" and req["status"]=="READY"
    assert ev["schema"]=="XRAY_EVENT_EPOCH_RESULT_V1" and ev["status"]=="COMMITTED"
    assert req["task_id"]==ev["task_id"]==TASK and ev["asof_et"]==asof
    assert req["execution"]==ev["execution"]=="NONE" and req["real_money"]==ev["real_money"]=="NO-GO"
    assert req.get("compiled_policy_blob_sha")==POLICY_BLOB
    assert req.get("compiled_policy_hash")==POLICY_HASH
    assert req.get("compiled_policy_version")==POLICY_VERSION
    assert ev.get("compiled_policy_hash")==req.get("compiled_policy_hash")
    assert ev.get("compiled_policy_version")==req.get("compiled_policy_version")
    assert ev.get("compiled_policy_blob_sha")==req.get("compiled_policy_blob_sha")
    assert int(ev["weekly_scope_count"])==int(req["weekly_scope_count"])
    assert ev["weekly_scope_hash"]==req["weekly_scope_hash"]
    assert int(ev["geometry_scope_count"])==int(req["geometry_scope_count"])
    assert ev["geometry_scope_hash"]==req["geometry_scope_hash"]
    for k in ["source_stage1_path","source_stage1_blob_sha","source_regime_path","source_regime_blob_sha","source_deep_geometry_path","source_deep_geometry_blob_sha"]:
        assert ev.get(k)==req.get(k),(k,ev.get(k),req.get(k))
    weekly=sorted(req["weekly_scope"])
    status=ev.get("event_status_by_symbol") or {}
    assert set(status)==set(weekly)
    confirmed=ev.get("confirmed_blocks") or {}
    unresolved=ev.get("unresolved") or {}
    assert set(confirmed)<=set(weekly) and set(unresolved)<=set(weekly) and not (set(confirmed)&set(unresolved))
    clean=[s for s in weekly if status.get(s)=="CLEAN_DISCOVERY"]
    block=[s for s in weekly if status.get(s)=="BLOCK_CONFIRMED_8SESSION"]
    unk=[s for s in weekly if status.get(s)=="UNKNOWN"]
    assert len(clean)+len(block)+len(unk)==len(weekly)
    assert set(block)==set(confirmed)
    assert set(unk)==set(unresolved)
    geometry=set(req.get("geometry_scope") or [])
    affected=sorted(geometry&set(unk))
    assert affected==sorted(ev.get("affected_geometry_event_unknown") or [])
    coverage_ok,coverage_mode=fail_closed_discovery_coverage(
        ev,weekly,status,unresolved,req.get("future_horizon_sessions") or []
    )
    assert coverage_ok,coverage_mode
    out={
      "schema":"XRAY_CANONICAL_EVENT_STATE_V1","task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_path":req.get("compiled_policy_path"),
      "compiled_policy_blob_sha":req.get("compiled_policy_blob_sha"),
      "compiled_policy_hash":req.get("compiled_policy_hash"),
      "compiled_policy_version":req.get("compiled_policy_version"),
      "weekly_scope":weekly,"weekly_scope_count":len(weekly),"weekly_scope_hash":req["weekly_scope_hash"],
      "geometry_scope":sorted(geometry),"geometry_scope_count":len(geometry),"geometry_scope_hash":req["geometry_scope_hash"],
      "event_status_by_symbol":dict(sorted(status.items())),
      "confirmed_blocks":dict(sorted(confirmed.items())),
      "unresolved":dict(sorted(unresolved.items())),
      "clean_discovery_count":len(clean),"confirmed_block_count":len(block),"unresolved_count":len(unk),
      "affected_geometry_event_unknown":affected,"affected_geometry_event_unknown_count":len(affected),
      "family_c_events":ev.get("family_c_events") or {},
      "discovery_hits":ev.get("discovery_hits") or [],
      "pagination_complete":ev.get("pagination_complete") is True,
      "partial_data":ev.get("partial_data") is True,
      "coverage_complete":ev.get("coverage_complete") is True,
      "discovery_coverage_mode":coverage_mode,
      "discovery_unavailable_symbols":sorted(ev.get("discovery_unavailable_symbols") or []),
      "provider_unavailable_but_officially_resolved_symbols":sorted(ev.get("provider_unavailable_but_officially_resolved_symbols") or []),
      "official_horizon_clearance":ev.get("official_horizon_clearance") or {},
      "source_policy":ev.get("source_policy"),
      "source_request_path":"nasdaq-xray/canonical_current_event_request.json",
      "source_request_blob_sha":blob_sha(REQ),
      "source_bridge_path":str(bridge.relative_to(ROOT.parent)).replace("\\","/"),
      "source_bridge_blob_sha":blob_sha(bridge),
      "authority":"CANONICAL_EVENT_TASKSTATE_BRIDGE_NORMALIZED"
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"weekly":len(weekly),"clean":len(clean),"blocked":len(block),"unresolved":len(unk),"affected_geometry_unknown":len(affected)},sort_keys=True))

if __name__=="__main__":main()
