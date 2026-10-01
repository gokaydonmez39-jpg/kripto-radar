#!/usr/bin/env python3
"""NASDAQ SWING X-RAY external autonomous orchestrator.
Deterministic research data plane only.
EXECUTION=NONE. REAL_MONEY=NO-GO. UNKNOWN!=PASS.
Does not mutate ChatGPT canonical Durable State and never places orders.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"orchestrator_state.json"
TASK_ID="6a825366222081918997094d76e6ae46"

PIPELINE_SCRIPTS=[
 "sina_stage.py",
 "mc_zero_key.py",
 "production_core_build.py",
 "stage1_shadow.py",
 "regime_breadth_shadow.py",
 "deep_pre_r1_shadow.py",
 "final_tech_shadow.py",
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
    for name in PIPELINE_SCRIPTS:
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
    event_hash=sha_file("event_official_state.json")
    engine_hash=stable_engine_hash()
    old=readj("orchestrator_state.json")
    fingerprint=hashlib.sha256((cand_hash+"|"+event_hash+"|"+engine_hash).encode()).hexdigest()

    # Same completed epoch + same official-event evidence + same engine code => zero-data-plane no-op.
    if old.get("fingerprint")==fingerprint and old.get("status") in {"ENGINE_PASS_FULL_GO_BLOCKED","ENGINE_PASS_NO_CONFIRMED_SETUP"}:
        old["last_noop_check_utc"]=datetime.now(timezone.utc).isoformat()
        STATE.write_text(json.dumps(old,indent=2,sort_keys=True)+"\n")
        print("XRAY_ORCHESTRATOR=NOOP_UNCHANGED_EPOCH")
        return

    # 2) Fail-closed zero-key MC and autonomous shadow core.
    run("mc_zero_key.py")
    run("production_core_build.py")
    core=readj("production_core_state.json")

    # 3) Technical stack on one identical core state.
    common_env={"XRAY_MC_STATE":str(ROOT/"production_core_state.json")}
    run("stage1_shadow.py",common_env)
    run("regime_breadth_shadow.py",common_env)
    run("deep_pre_r1_shadow.py")
    run("final_tech_shadow.py")

    st1=readj("stage1_shadow.json")
    rg=readj("regime_breadth_shadow.json")
    deep=readj("deep_pre_r1_shadow.json")
    final=readj("final_tech_shadow.json")
    mc=readj("mc_zero_key_state.json")

    pre_g9=final.get("pre_g9_tech_pass") or []
    event_fresh=bool(deep.get("event_state_fresh"))
    blockers=[]
    if not event_fresh: blockers.append("OFFICIAL_EVENT_STATE_STALE_OR_MISSING")
    blockers.append("G9_BLOCKED_NO_AUTHORIZED_ZERO_DOLLAR_RUNTIME_SOURCE")
    blockers.append("ACCOUNT_GATE_UNKNOWN")
    blockers.append("OBSERVED_IPHONE_SIGNAL_DELIVERY_UNPROVEN")
    blockers.append("CANONICAL_CHATGPT_DURABLE_STATE_NOT_MIGRATED")

    status="ENGINE_PASS_FULL_GO_BLOCKED" if pre_g9 else "ENGINE_PASS_NO_CONFIRMED_SETUP"
    out={
      "schema":"XRAY_ORCHESTRATOR_V1","task_id":TASK_ID,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":status,"asof_et":ss.get("asof_et"),
      "fingerprint":fingerprint,
      "candidate_hash":cand_hash,"event_hash":event_hash,"engine_hash":engine_hash,
      "history":{"status":ss.get("status"),"queue_total":ss.get("queue_total"),"counts":ss.get("counts")},
      "mc":{"current_core_count":core.get("current_core_count"),"unresolved_count":mc.get("unresolved_count"),"definitive_fail_count":mc.get("definitive_fail_count")},
      "stage1":{"weekly_pass_count":st1.get("weekly_pass_count"),"unknown_count":st1.get("unknown_count")},
      "regime":{"regime":rg.get("regime"),"breadth_missing_count":rg.get("breadth_missing_count"),"breadth_above_sma50_pct":rg.get("breadth_above_sma50_pct"),"nh20":rg.get("nh20"),"nl20":rg.get("nl20")},
      "deep":{"a_pass":deep.get("a_geometry_rs_event_pass") or [],"b_breakout_pass":deep.get("b_breakout_rs_event_pass") or [],"b_armed":deep.get("b_armed_rs_event_pass") or [],"d_pass":deep.get("d_dk3_pre_r1") or [],"event_state_fresh":event_fresh},
      "final_tech":{"pre_g9_tech_pass":pre_g9,"watch":final.get("watch") or [],"fail":final.get("fail") or []},
      "g9_status":"BLOCKED",
      "account_gate":"UNKNOWN_NOT_CONFIGURED",
      "full_go_blockers":blockers,
      "authority":"EXTERNAL_AUTONOMOUS_SHADOW_DATA_PLANE; CHATGPT_CANONICAL_STATE_UNCHANGED"
    }
    STATE.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_ORCHESTRATOR="+status)
    print(json.dumps({"asof":out["asof_et"],"core":core.get("current_core_count"),"weekly":st1.get("weekly_pass_count"),"regime":rg.get("regime"),"pre_g9":pre_g9,"blockers":blockers},sort_keys=True))

if __name__=="__main__":
    main()
