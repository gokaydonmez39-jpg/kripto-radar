#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external autonomous orchestrator.
Deterministic research data plane only.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
Does not mutate ChatGPT canonical Durable State and never places orders.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"orchestrator_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"

ENGINE_FILES=[
 "sina_stage.py",
 "mc_zero_key.py",
 "production_core_build.py",
 "alpha_semantics.py",
 "stage1_shadow.py",
 "regime_breadth_shadow.py",
 "deep_pre_r1_shadow.py",
 "history_official_identity_evidence.json",
 "requirements-runtime.txt",
]

def readj(path):
    p=ROOT/path
    return json.loads(p.read_text()) if p.exists() else {}

def sha_file(path):
    p=ROOT/path
    if not p.exists(): return "MISSING"
    return hashlib.sha256(p.read_bytes()).hexdigest()

def stable_engine_hash():
    h=hashlib.sha256()
    for name in ENGINE_FILES:
        p=ROOT/name
        h.update(name.encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()

def run(script, extra_env=None):
    env=os.environ.copy()
    if extra_env: env.update(extra_env)
    print(f"XRAY_RUN={script}", flush=True)
    cp=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT.parent,env=env,text=True)
    if cp.returncode!=0:
        raise RuntimeError(f"{script}:EXIT_{cp.returncode}")

def main():
    now_et=datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    # Keep an all-UTC schedule without accidentally treating UTC Saturday as ET Friday loss.
    if now_et.weekday()>=5:
        print("XRAY_ORCHESTRATOR=NOOP_ET_WEEKEND")
        return

    # 1) Progress/refresh official universe + PRICE/DV20/HISTORY.
    # Repeated local invocations are resumable and bounded; same epoch does zero new work once complete.
    max_loops=5
    for i in range(max_loops):
        run("sina_stage.py")
        ss=readj("sina_state.json")
        print("XRAY_HISTORY_STATUS="+str(ss.get("status"))+" CURSOR="+str(ss.get("cursor"))+"/"+str(ss.get("queue_total")),flush=True)
        if ss.get("status")=="HISTORY_COMPLETE":
            break
    ss=readj("sina_state.json")
    if ss.get("status")!="HISTORY_COMPLETE":
        out={
          "schema":"XRAY_ORCHESTRATOR_V1","task_id":TASK_ID,
          "execution":"NONE","real_money":"NO-GO",
          "updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "status":"PARTIAL_HISTORY","asof_et":ss.get("asof_et"),
          "cursor":ss.get("cursor"),"queue_total":ss.get("queue_total"),
          "g9_status":"BLOCKED","account_gate":"UNKNOWN_NOT_CONFIGURED"
        }
        STATE.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print("XRAY_ORCHESTRATOR=PARTIAL_HISTORY")
        return

    cand_hash=sha_file("sina_candidates.json")
    engine_hash=stable_engine_hash()
    old=readj("orchestrator_state.json")
    fingerprint=hashlib.sha256((cand_hash+"|"+engine_hash).encode()).hexdigest()

    # Root is a data-plane support layer, not canonical candidate authority.
    # It must never depend on stale/current Canonical Event, Legal, lifecycle or
    # finalist artifacts from a different ASOF.
    if old.get("fingerprint")==fingerprint and old.get("status")=="DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED":
        print("XRAY_ORCHESTRATOR=NOOP_UNCHANGED_DATA_PLANE")
        return

    # 2) Fail-closed zero-key MC and autonomous support core.
    run("mc_zero_key.py")
    run("production_core_build.py")
    core=readj("production_core_state.json")

    # 3) Root-owned technical diagnostics only. Deep runs geometry-only so this
    # layer never consumes Canonical Event/Legal/Final evidence. All event,
    # detailed legal, R1/RR, lifecycle, official-safety and candidate authority
    # remains exclusively in the canonical Post-MC/Final chain.
    common_env={"XRAY_MC_STATE":str(ROOT/"production_core_state.json")}
    run("stage1_shadow.py",common_env)
    run("regime_breadth_shadow.py",common_env)
    run("deep_pre_r1_shadow.py",{
        "XRAY_DEEP_GEOMETRY_ONLY":"1",
        "XRAY_STAGE1_STATE":str(ROOT/"stage1_shadow.json"),
        "XRAY_DEEP_OUT":str(ROOT/"deep_pre_r1_shadow.json"),
    })

    st1=readj("stage1_shadow.json")
    rg=readj("regime_breadth_shadow.json")
    deep=readj("deep_pre_r1_shadow.json")
    mc=readj("mc_zero_key_state.json")

    coverage_faults=[]
    if int(ss.get("unknown_count",0) or 0)>0: coverage_faults.append("HARD_GATE_UNKNOWN_REMAINS")
    if int(mc.get("unresolved_count",0) or 0)>0: coverage_faults.append("MC_UNRESOLVED_REMAINS")
    if int(st1.get("unknown_count",0) or 0)>0: coverage_faults.append("STAGE1_UNKNOWN_REMAINS")
    if int(rg.get("breadth_missing_count",0) or 0)>0: coverage_faults.append("BREADTH_MISSING_REMAINS")
    if int(deep.get("unknown_history_count",0) or 0)>0: coverage_faults.append("DEEP_HISTORY_UNKNOWN_REMAINS")

    blockers=list(coverage_faults)
    blockers.append("CANONICAL_EVENTS_LEGAL_R1_RR_LIFECYCLE_DEFERRED")
    blockers.append("G9_BLOCKED_NO_AUTHORIZED_ZERO_DOLLAR_RUNTIME_SOURCE")
    blockers.append("ACCOUNT_GATE_UNKNOWN")
    blockers.append("OBSERVED_IPHONE_SIGNAL_DELIVERY_UNPROVEN")

    status="DATA_PLANE_PARTIAL_UNKNOWN" if coverage_faults else "DATA_PLANE_PASS_CANONICAL_DOWNSTREAM_DEFERRED"
    out={
      "schema":"XRAY_ORCHESTRATOR_V1","task_id":TASK_ID,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":status,"asof_et":ss.get("asof_et"),
      "fingerprint":fingerprint,
      "candidate_hash":cand_hash,"engine_hash":engine_hash,
      "history":{"status":ss.get("status"),"queue_total":ss.get("queue_total"),"counts":ss.get("counts")},
      "mc":{"current_core_count":core.get("current_core_count"),"unresolved_count":mc.get("unresolved_count"),"definitive_fail_count":mc.get("definitive_fail_count")},
      "stage1":{"weekly_pass_count":st1.get("weekly_pass_count"),"unknown_count":st1.get("unknown_count")},
      "regime":{"regime":rg.get("regime"),"breadth_missing_count":rg.get("breadth_missing_count"),"breadth_above_sma50_pct":rg.get("breadth_above_sma50_pct"),"nh20":rg.get("nh20"),"nl20":rg.get("nl20")},
      "deep_geometry":{
        "a_geometry_count":deep.get("a_geometry_count"),
        "b_breakout_count":deep.get("b_breakout_count"),
        "b_armed_count":deep.get("b_armed_count"),
        "d_geometry_count":deep.get("d_geometry_rs_count"),
        "unknown_history_count":deep.get("unknown_history_count"),
        "event_and_regime_finalist_authority":"DEFERRED_TO_CANONICAL_CHAIN"
      },
      "final_tech":{"status":"DEFERRED_TO_CANONICAL_FINAL_FACTORY","pre_g9_tech_pass":[]},
      "coverage_faults":coverage_faults,
      "g9_status":"BLOCKED",
      "account_gate":"UNKNOWN_NOT_CONFIGURED",
      "full_go_blockers":blockers,
      "authority":"EXTERNAL_AUTONOMOUS_SUPPORT_DATA_PLANE_ONLY; CANONICAL_CANDIDATE_AUTHORITY_UNCHANGED"
    }
    STATE.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_ORCHESTRATOR="+status)
    print(json.dumps({"asof":out["asof_et"],"core":core.get("current_core_count"),
                      "weekly":st1.get("weekly_pass_count"),"regime":rg.get("regime"),
                      "coverage_faults":coverage_faults},sort_keys=True))

if __name__=="__main__":
    main()
