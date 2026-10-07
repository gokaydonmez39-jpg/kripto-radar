#!/usr/bin/env python3
"""Fail-closed builder for issuer-primary Event successors.

Consumes the non-canonical issuer-primary probe plus exact current Event
request/state. Missing, ambiguous, stale, or landing-page evidence is a no-op.
Default mode writes only a local successor candidate. --dry-run never writes.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN != PASS.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
REQUEST=ROOT/"canonical_current_event_request.json"
STATE=ROOT/"canonical_current_event_state.json"
PROBE=ROOT/"event_official_primary_probe_state.json"
TASK="6a825366222081918997094d76e6ae46"

def blob_sha(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def load(path:Path)->dict:
    return json.loads(path.read_text(encoding="utf-8"))

def valid_url(url:str)->bool:
    try:
        p=urlparse(url)
        return p.scheme in {"http","https"} and bool(p.hostname)
    except Exception:
        return False

def decision_matches(result:dict)->list[dict]:
    out=[]
    for issuer in result.get("issuer_probes") or []:
        if issuer.get("identity_validated") is not True:
            continue
        for m in issuer.get("matches") or []:
            if m.get("authority")!="ISSUER_IR_PRIMARY":
                continue
            if not valid_url(str(m.get("source_url") or "")):
                continue
            if str(m.get("extraction_basis") or "").startswith("BASE_PAGE_"):
                continue
            out.append(m)
    return out

def candidate_promotion(sym:str,result:dict,current_status:str,horizon:list[str])->dict|None:
    if current_status!="UNKNOWN":
        return None
    st=result.get("status")
    if st not in {"CLEAN_OUTSIDE_HORIZON_CANDIDATE","BLOCK_CONFIRMED_8SESSION_CANDIDATE"}:
        return None
    selected=str(result.get("selected_event_date") or "")[:10]
    if not selected or len(horizon)!=8:
        return None
    matches=decision_matches(result)
    selected_matches=[m for m in matches if str(m.get("event_date") or "")[:10]==selected]
    if not selected_matches:
        return None
    hs=set(horizon); hend=max(horizon)
    inside=[m for m in matches if str(m.get("event_date") or "")[:10] in hs]
    if st=="CLEAN_OUTSIDE_HORIZON_CANDIDATE":
        if selected<=hend or inside:
            return None
        cls="CLEAN_DISCOVERY"; hr="OUTSIDE_EXACT_8_SESSION_HORIZON"
    else:
        if selected not in hs:
            return None
        cls="BLOCK_CONFIRMED_8SESSION"; hr="INSIDE_EXACT_8_SESSION_HORIZON"
    chosen=selected_matches[0]
    return {"symbol":sym,"classification":cls,"event_date":selected,
            "horizon_result":hr,"authority":"ISSUER_IR_PRIMARY",
            "official_source_url":chosen["source_url"],
            "extraction_basis":chosen.get("extraction_basis")}

def eligible_promotions(req:dict,state:dict,probe:dict)->list[dict]:
    geometry=set(req.get("geometry_scope") or [])
    current=state.get("event_status_by_symbol") or {}
    horizon=list(req.get("future_horizon_sessions") or [])
    out=[]
    for sym,result in sorted((probe.get("results") or {}).items()):
        if sym not in geometry:
            continue
        rec=candidate_promotion(sym,result,current.get(sym),horizon)
        if rec:
            out.append(rec)
    return out

def exact_binding(req:dict,state:dict,probe:dict):
    if req.get("schema")!="XRAY_EVENT_EPOCH_REQUEST_V1" or req.get("status")!="READY":
        return False,"REQUEST_NOT_READY",None,None
    if state.get("schema")!="XRAY_CANONICAL_EVENT_STATE_V1":
        return False,"EVENT_STATE_SCHEMA",None,None
    if probe.get("schema")!="XRAY_EVENT_OFFICIAL_PRIMARY_PROBE_V1":
        return False,"PROBE_SCHEMA",None,None
    if req.get("task_id")!=TASK or state.get("task_id")!=TASK or probe.get("task_id")!=TASK:
        return False,"TASK_MISMATCH",None,None
    for obj in (req,state,probe):
        if obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO" or obj.get("unknown_never_pass") is not True:
            return False,"SAFETY_MISMATCH",None,None
    if probe.get("classification_applied") is not False:
        return False,"PROBE_ALREADY_APPLIED",None,None
    if probe.get("asof_et")!=req.get("asof_et") or state.get("asof_et")!=req.get("asof_et"):
        return False,"ASOF_MISMATCH",None,None
    if probe.get("source_event_request_blob_sha")!=blob_sha(REQUEST):
        return False,"STALE_PROBE_REQUEST",None,None
    if probe.get("source_event_state_blob_sha")!=blob_sha(STATE):
        return False,"STALE_PROBE_STATE",None,None
    if sorted(probe.get("scope") or [])!=sorted(req.get("geometry_scope") or []):
        return False,"PROBE_SCOPE_MISMATCH",None,None
    if list(probe.get("future_horizon_sessions") or [])!=list(req.get("future_horizon_sessions") or []):
        return False,"PROBE_HORIZON_MISMATCH",None,None
    rel=state.get("source_bridge_path"); sha=state.get("source_bridge_blob_sha")
    if not rel or not sha:
        return False,"STATE_BRIDGE_POINTER_MISSING",None,None
    pp=REPO/rel
    if not pp.exists() or blob_sha(pp)!=sha:
        return False,"STATE_BRIDGE_BLOB_MISMATCH",None,None
    pred=load(pp)
    if pred.get("schema")!="XRAY_EVENT_EPOCH_RESULT_V1" or pred.get("status")!="COMMITTED":
        return False,"PREDECESSOR_NOT_COMMITTED",None,None
    keys=["asof_et","compiled_policy_blob_sha","compiled_policy_hash","compiled_policy_version",
          "weekly_scope_hash","geometry_scope_hash","lifecycle_scope_hash",
          "source_stage1_path","source_stage1_blob_sha","source_regime_path","source_regime_blob_sha",
          "source_deep_geometry_path","source_deep_geometry_blob_sha"]
    for k in keys:
        if pred.get(k)!=req.get(k):
            return False,"PREDECESSOR_REQUEST_BINDING_"+k,None,None
    if pred.get("source_request_path")!="nasdaq-xray/canonical_current_event_request.json":
        return False,"PREDECESSOR_REQUEST_PATH",None,None
    if pred.get("source_request_blob_sha")!=blob_sha(REQUEST):
        return False,"PREDECESSOR_REQUEST_BLOB",None,None
    if sorted(pred.get("weekly_scope") or [])!=sorted(req.get("weekly_scope") or []):
        return False,"WEEKLY_SCOPE_SET_MISMATCH",None,None
    if sorted(pred.get("geometry_scope") or [])!=sorted(req.get("geometry_scope") or []):
        return False,"GEOMETRY_SCOPE_SET_MISMATCH",None,None
    if list(pred.get("future_horizon_sessions") or [])!=list(req.get("future_horizon_sessions") or []):
        return False,"HORIZON_MISMATCH",None,None
    return True,"EXACT",pp,pred

def next_path(asof:str):
    stamp=asof.replace("-","")
    rx=re.compile(rf"^canonical_event_bridge_{stamp}_c417_dv30_v(\d+)\.json$")
    vs=[]
    for p in ROOT.glob(f"canonical_event_bridge_{stamp}_c417_dv30_v*.json"):
        m=rx.match(p.name)
        if m: vs.append(int(m.group(1)))
    v=max(vs or [0])+1
    return ROOT/f"canonical_event_bridge_{stamp}_c417_dv30_v{v}.json",v

def build_successor(req,pred,pred_path,promotions,version):
    out=deepcopy(pred)
    status=out.setdefault("event_status_by_symbol",{})
    unresolved=out.setdefault("unresolved",{})
    confirmed=out.setdefault("confirmed_blocks",{})
    clearance=out.setdefault("official_horizon_clearance",{})
    resolved=set(out.get("provider_unavailable_but_officially_resolved_symbols") or [])
    for p in promotions:
        s=p["symbol"]; assert status.get(s)=="UNKNOWN"
        status[s]=p["classification"]; unresolved.pop(s,None); resolved.add(s)
        clearance[s]={"authority":"ISSUER_IR_PRIMARY","evidence_date":None,
          "evidence_kind":"EXPLICIT_EARNINGS_OR_FINANCIAL_RESULTS_DATE",
          "horizon_result":p["horizon_result"],"next_event_date":p["event_date"],
          "official_source_url":p["official_source_url"]}
        if p["classification"]=="BLOCK_CONFIRMED_8SESSION":
            confirmed[s]={"event_date":p["event_date"],"authority":"ISSUER_IR_PRIMARY",
              "official_source_url":p["official_source_url"],
              "reason":"OFFICIAL_EVENT_INSIDE_EXACT_8_SESSION_HORIZON"}
        else: confirmed.pop(s,None)
    weekly=list(req.get("weekly_scope") or []); geometry=set(req.get("geometry_scope") or [])
    clean=[s for s in weekly if status.get(s)=="CLEAN_DISCOVERY"]
    block=[s for s in weekly if status.get(s)=="BLOCK_CONFIRMED_8SESSION"]
    unk=[s for s in weekly if status.get(s)=="UNKNOWN"]
    assert len(clean)+len(block)+len(unk)==len(weekly)
    assert set(block)==set(confirmed) and set(unk)==set(unresolved)
    affected=sorted(geometry&set(unk))
    rel=str(pred_path.relative_to(REPO)).replace("\\","/"); psha=blob_sha(pred_path)
    out["authority"]=f"CANONICAL_EVENT_BRIDGE_C4_17_DV30_OFFICIAL_PRIMARY_SUCCESSOR_V{version}"
    out["committed_by"]="XRAY_EVENT_OFFICIAL_PRIMARY_SUCCESSOR_BUILDER"
    out["clean_discovery_count"]=len(clean); out["confirmed_block_count"]=len(block)
    out["unresolved_count"]=len(unk); out["affected_geometry_event_unknown"]=affected
    out["affected_geometry_event_unknown_count"]=len(affected)
    out["provider_unavailable_but_officially_resolved_symbols"]=sorted(resolved)
    out["supersedes_event_bridge_path"]=rel; out["supersedes_event_bridge_blob_sha"]=psha
    out["semantic_rebind"]={"rule":"OPTIONAL_DISCOVERY_DIRECT_OFFICIAL_PRIMARY_RESOLUTION_V1",
      "current_request_blob_sha":blob_sha(REQUEST),"weekly_scope_hash":req.get("weekly_scope_hash"),
      "geometry_scope_hash":req.get("geometry_scope_hash"),"lifecycle_scope_hash":req.get("lifecycle_scope_hash"),
      "no_alpha_threshold_change":True,"no_event_horizon_change":True,
      "decisions_changed_only_with_primary_evidence":True,"official_resolved_count":len(resolved),
      "affected_geometry_event_unknown_count":len(affected),"predecessor_path":rel,
      "predecessor_blob_sha":psha,"paid_top_up":False,"unknown_never_pass":True}
    proof=deepcopy(out.get("rebind_proof") or {})
    proof.update({"direct_official_primary_reverification":True,"exact_current_request_binding":True,
      "no_alpha_threshold_change":True,"no_event_horizon_change":True,"paid_top_up":False,
      "new_official_resolutions":[p["symbol"] for p in promotions],
      "resolved_symbol_count":len(resolved),"remaining_unresolved_count":len(unk),
      "remaining_geometry_event_unknown_count":len(affected),"unknown_never_pass":True})
    out["rebind_proof"]=proof
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--probe",default=str(PROBE)); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args(); req=load(REQUEST); state=load(STATE); probe=load(Path(a.probe))
    ok,reason,pp,pred=exact_binding(req,state,probe)
    if not ok:
        print(json.dumps({"status":"NOOP_STALE_OR_INVALID_BINDING","reason":reason},sort_keys=True)); return
    promotions=eligible_promotions(req,state,probe)
    if not promotions:
        print(json.dumps({"status":"NOOP_NO_PROMOTABLE_UNKNOWN","promotions":0},sort_keys=True)); return
    op,v=next_path(req["asof_et"]); out=build_successor(req,pred,pp,promotions,v)
    if a.dry_run:
        print(json.dumps({"status":"DRY_RUN_PROMOTABLE","path":str(op.relative_to(REPO)).replace("\\","/"),
          "promotions":promotions,"affected_after":out["affected_geometry_event_unknown_count"]},sort_keys=True)); return
    if op.exists(): raise RuntimeError("SUCCESSOR_PATH_ALREADY_EXISTS")
    op.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"SUCCESSOR_CANDIDATE_WRITTEN_LOCAL_ONLY","path":str(op.relative_to(REPO)).replace("\\","/"),
      "blob_sha":blob_sha(op),"promotions":promotions},sort_keys=True))

if __name__=="__main__": main()
