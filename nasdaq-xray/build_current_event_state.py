#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REQ=Path(os.getenv("XRAY_EVENT_REQUEST",str(ROOT/"canonical_current_event_request.json")))
OUT=Path(os.getenv("XRAY_EVENT_STATE_OUT",str(ROOT/"canonical_current_event_state.json")))
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def main():
    req=json.loads(REQ.read_text())
    asof=req["asof_et"]
    bridge=ROOT/f"canonical_event_bridge_{asof.replace('-','')}.json"
    if not bridge.exists(): raise RuntimeError("EVENT_BRIDGE_MISSING")
    ev=json.loads(bridge.read_text())
    assert req["schema"]=="XRAY_EVENT_EPOCH_REQUEST_V1" and req["status"]=="READY"
    assert ev["schema"]=="XRAY_EVENT_EPOCH_RESULT_V1" and ev["status"]=="COMMITTED"
    assert req["task_id"]==ev["task_id"]==TASK and ev["asof_et"]==asof
    assert req["execution"]==ev["execution"]=="NONE" and req["real_money"]==ev["real_money"]=="NO-GO"
    assert req.get("compiled_policy_hash")=="bc4ad11c4029bf5feb5399ae3aa7af9c9c8dd7ad6c44119bac4e5734287b931e"
    assert req.get("compiled_policy_version")=="C4.14"
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
      "source_policy":ev.get("source_policy"),
      "source_request_path":"nasdaq-xray/canonical_current_event_request.json",
      "source_request_blob_sha":blob_sha(REQ),
      "source_bridge_path":str(bridge.relative_to(ROOT.parent)).replace("\\","/"),
      "source_bridge_blob_sha":blob_sha(bridge),
      "authority":"CANONICAL_EVENT_TASKSTATE_BRIDGE_NORMALIZED"
    }
    assert out["pagination_complete"] is True
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"weekly":len(weekly),"clean":len(clean),"blocked":len(block),"unresolved":len(unk),"affected_geometry_unknown":len(affected)},sort_keys=True))

if __name__=="__main__":main()
