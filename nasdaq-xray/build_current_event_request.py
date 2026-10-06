#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timedelta
from pathlib import Path
import pandas_market_calendars as mcal

ROOT=Path(__file__).resolve().parent
STAGE1=Path(os.getenv("XRAY_EVENT_STAGE1",str(ROOT/"canonical_current_stage1.json")))
DEEP=Path(os.getenv("XRAY_EVENT_DEEP",str(ROOT/"canonical_current_deep_geometry.json")))
REGIME=Path(os.getenv("XRAY_EVENT_REGIME",str(ROOT/"canonical_current_regime.json")))
PREV_FINAL=Path(os.getenv("XRAY_EVENT_PREV_FINAL",str(ROOT/"canonical_current_final_tech.json")))
LIFECYCLE=Path(os.getenv("XRAY_EVENT_LIFECYCLE_REGISTRY",str(ROOT/"canonical_candidate_lifecycle_registry.json")))
OUT=Path(os.getenv("XRAY_EVENT_REQUEST_OUT",str(ROOT/"canonical_current_event_request.json")))
LIFECYCLE_ACTIVE_STATES={
    "WATCH_RETEST_REQUIRED","WATCH_RECONFIRMATION_REQUIRED",
    "WATCH_CHASE_RETEST_REQUIRED","WATCH_EXTENSION_RESET_REQUIRED",
    "WATCH_REGIME_REVALIDATION_REQUIRED","WATCH_REGIME_UNKNOWN",
    "PRE_G9_TECH_PASS","WATCH_EVENT_UNKNOWN_OR_BLOCKED","WATCH_MC_FALLBACK_CAP",
}
TASK="6a825366222081918997094d76e6ae46"
POLICY=ROOT/"chatgpt_compiled_policy_v3.json"
POLICY_BLOB="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
POLICY_HASH="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
POLICY_VERSION="C4.17"

def blob_sha(p:Path)->str:
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

def lifecycle_scope_from_final(final_obj,asof,sidecar_obj=None):
    """Return active prospective lifecycle symbols through later ASOFs.

    Embedded prior-Final state is accepted when it is not future-dated; an exact
    valid sidecar overrides it. Dead/expired/failed audit records are excluded
    from current Event scope so they cannot create unrelated event UNKNOWNs.
    """
    try:
        chosen=None
        f=final_obj or {}
        lr=f.get("lifecycle_registry") or {}
        fa=str(f.get("asof_et") or "")
        if (fa and fa<=asof
            and lr.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
            and lr.get("execution")=="NONE" and lr.get("real_money")=="NO-GO"
            and isinstance(lr.get("records"),dict)):
            chosen=lr
        if sidecar_obj is not None:
            sc=sidecar_obj or {}
            sa=str(sc.get("asof_et") or "")
            if (sa and sa<=asof
                and sc.get("schema")=="XRAY_CANDIDATE_LIFECYCLE_REGISTRY_V1"
                and sc.get("execution")=="NONE" and sc.get("real_money")=="NO-GO"
                and isinstance(sc.get("records"),dict)):
                chosen=sc
            else:
                return []
        if not chosen:return []
        return sorted(set(
            str(rec.get("symbol")) for rec in (chosen.get("records") or {}).values()
            if rec.get("symbol") and str(rec.get("state") or "") in LIFECYCLE_ACTIVE_STATES
            and str(rec.get("last_asof") or chosen.get("asof_et") or "")<=asof
        ))
    except Exception:
        return []

def event_geometry_scope(fresh_geometry,lifecycle_scope):
    return sorted(set(fresh_geometry or [])|set(lifecycle_scope or []))

def sessions(asof):
    d=datetime.fromisoformat(asof).date()
    cal=mcal.get_calendar("NASDAQ")
    sched=cal.schedule(start_date=(d-timedelta(days=40)).isoformat(),end_date=(d+timedelta(days=25)).isoformat())
    ds=[x.date().isoformat() for x in sched.index]
    if asof not in ds: raise RuntimeError("ASOF_NOT_OFFICIAL_SESSION")
    i=ds.index(asof)
    # Family C may confirm a breakout 10 completed sessions after reaction0.
    # For AMC events reaction0 is the NEXT RTH, so the source earnings event can
    # sit one additional completed session before that reaction. Keep current
    # ASOF + prior 11 official sessions (12 total) to cover the exact boundary.
    past=ds[max(0,i-11):i+1]
    future=ds[i+1:i+9]
    if len(past)!=12 or len(future)!=8: raise RuntimeError("SESSION_WINDOW_INCOMPLETE")
    return past,future

def main():
    s=json.loads(STAGE1.read_text()); d=json.loads(DEEP.read_text()); r=json.loads(REGIME.read_text())
    pol=json.loads(POLICY.read_text())
    assert blob_sha(POLICY)==POLICY_BLOB
    assert pol.get("schema")=="XRAY_GITHUB_COMPILED_POLICY_V3" and pol.get("policy_hash")==POLICY_HASH
    pp=json.loads(pol["payload_json"])
    assert pp.get("version")==POLICY_VERSION and pp.get("execution")=="NONE" and pp.get("real_money")=="NO-GO"
    asof=s["asof_et"]
    assert s["task_id"]==d["task_id"]==r["task_id"]==TASK
    assert d["asof_et"]==r["asof_et"]==asof
    assert s["execution"]==d["execution"]==r["execution"]=="NONE"
    assert s["real_money"]==d["real_money"]==r["real_money"]=="NO-GO"
    stage1_unknown=sorted(set(s.get("unknown") or []))
    breadth_missing=sorted(set(r.get("breadth_missing") or []))
    deep_history_unknown=sorted(set(d.get("unknown_history") or []))
    assert len(stage1_unknown)==int(s.get("unknown_count",len(stage1_unknown)))
    assert len(breadth_missing)==int(r.get("breadth_missing_count",len(breadth_missing)))
    assert len(deep_history_unknown)==int(d.get("unknown_history_count",len(deep_history_unknown)))
    current_weekly=sorted(set(s.get("weekly_pass") or []))
    assert len(current_weekly)==int(s.get("weekly_pass_count",len(current_weekly)))
    weekly=sorted(set(s.get("recent_weekly_scope") or current_weekly))
    assert len(weekly)==int(s.get("recent_weekly_scope_count",len(weekly)))
    assert set(current_weekly)<=set(weekly),"CURRENT_WEEKLY_NOT_SUBSET_OF_TRIGGER_SCOPE"
    assert not (set(stage1_unknown)&set(weekly)),"UNKNOWN_STAGE1_LEAKED_INTO_WEEKLY_SCOPE"
    assert int(d.get("input_weekly_pass_count",-1))==len(current_weekly)
    assert int(d.get("input_weekly_trigger_scope_count",-1))==len(weekly)
    assert set(d.get("weekly_trigger_scope") or [])==set(weekly)
    past,future=sessions(asof)
    fresh_geometry=sorted(set(
        (d.get("a_geometry") or [])+
        (d.get("b_breakout") or [])+
        (d.get("b_armed") or [])+
        (d.get("d_geometry_rs") or [])
    ))
    assert set(fresh_geometry)<=set(weekly)
    lifecycle_scope=[]
    try:
        prev=json.loads(PREV_FINAL.read_text()) if PREV_FINAL.exists() else {}
        side=json.loads(LIFECYCLE.read_text()) if LIFECYCLE.exists() else None
        lifecycle_scope=lifecycle_scope_from_final(prev,asof,side)
    except Exception:
        lifecycle_scope=[]
    finalists=event_geometry_scope(fresh_geometry,lifecycle_scope)
    obj={
      "schema":"XRAY_EVENT_EPOCH_REQUEST_V1","status":"READY","task_id":TASK,"asof_et":asof,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
      "compiled_policy_blob_sha":POLICY_BLOB,
      "compiled_policy_hash":POLICY_HASH,
      "compiled_policy_version":POLICY_VERSION,
      "coverage_unknowns":{
        "stage1":{"count":len(stage1_unknown),"symbols":stage1_unknown},
        "breadth":{"count":len(breadth_missing),"symbols":breadth_missing},
        "deep_history":{"count":len(deep_history_unknown),"symbols":deep_history_unknown},
      },
      "upstream_coverage_complete":not (stage1_unknown or breadth_missing or deep_history_unknown),
      "request_scope_complete":True,
      "current_weekly_scope":current_weekly,"current_weekly_scope_count":len(current_weekly),
      "current_weekly_scope_hash":hash_lines(current_weekly),
      "weekly_scope":weekly,"weekly_scope_count":len(weekly),"weekly_scope_hash":hash_lines(weekly),
      "fresh_geometry_scope":fresh_geometry,"fresh_geometry_scope_count":len(fresh_geometry),
      "fresh_geometry_scope_hash":hash_lines(fresh_geometry),
      "lifecycle_scope":lifecycle_scope,"lifecycle_scope_count":len(lifecycle_scope),
      "lifecycle_scope_hash":hash_lines(lifecycle_scope),
      "geometry_scope":finalists,"geometry_scope_count":len(finalists),"geometry_scope_hash":hash_lines(finalists),
      "past_family_c_sessions":past,"future_horizon_sessions":future,
      "family_c_breakout_max_sessions":10,"family_c_amc_source_lookback_extra_sessions":1,
      "market_close_semantics":"ASOF_COMPLETED_RTH;EVENT_AFTER_ASOF_CLOSE_BEFORE_NEXT_RTH_COUNTS_INSIDE_HORIZON",
      "source_stage1_path":"nasdaq-xray/canonical_current_stage1.json","source_stage1_blob_sha":blob_sha(STAGE1),
      "source_regime_path":"nasdaq-xray/canonical_current_regime.json","source_regime_blob_sha":blob_sha(REGIME),
      "source_deep_geometry_path":"nasdaq-xray/canonical_current_deep_geometry.json","source_deep_geometry_blob_sha":blob_sha(DEEP),
      "required_discovery":{
        "required":False,
        "role":"OPTIONAL_ACCELERATOR_ONLY",
        "provider":"PROVIDER_NEUTRAL_ZERO_DOLLAR_DISCOVERY",
        "preferred_providers":["PUBLIC_WEB","BIGDATA_IF_ZERO_DOLLAR_CALLABLE","QUARTR_IF_ZERO_DOLLAR_CALLABLE"],
        "exchanges":["XNAS","XNGS","XNMS","XNCM","XNGM"],
        "category":"earnings-call",
        "paid_topup_forbidden":True,
        "provider_failure_never_clears_or_blocks":True,
        "geometry_direct_official_fallback_required":True
      },
      "official_confirmation":"ISSUER_IR_OR_SEC_PRIMARY;DISCOVERY_OPTIONAL_NEVER_BLOCKS_OR_CLEARS_BY_ITSELF;GEOMETRY_SCOPE_MUST_ATTEMPT_DIRECT_OFFICIAL_PRIMARY_WHEN_DISCOVERY_UNAVAILABLE"
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"upstream_coverage_complete":obj["upstream_coverage_complete"],
                      "stage1_unknown_count":len(stage1_unknown),
                      "breadth_missing_count":len(breadth_missing),
                      "deep_history_unknown_count":len(deep_history_unknown),
                      "current_weekly_scope_count":len(current_weekly),
                      "weekly_scope_count":len(weekly),
                      "fresh_geometry_scope_count":len(fresh_geometry),
                      "lifecycle_scope_count":len(lifecycle_scope),
                      "geometry_scope_count":len(finalists),"past":past,"future":future},sort_keys=True))

if __name__=="__main__": main()
