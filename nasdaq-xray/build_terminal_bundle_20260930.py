#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF="2026-09-30"

FILES={
 "hard_state":ROOT/"canonical_full_hard_gate_20260930_state.json",
 "hard_candidates":ROOT/"canonical_full_hard_gate_20260930_candidates.json",
 "mc_resolution":ROOT/"canonical_mc_resolution_20260930.json",
 "mc_input":ROOT/"canonical_mc_input_20260930.json",
 "legal":ROOT/"canonical_legal_survivors_core_20260930.json",
 "stage1":ROOT/"canonical_stage1_20260930.json",
 "regime":ROOT/"canonical_regime_20260930.json",
 "events":ROOT/"canonical_event_state_20260930.json",
 "deep":ROOT/"canonical_deep_full_20260930.json",
 "final":ROOT/"canonical_final_tech_20260930.json",
}
OUT=ROOT/"canonical_terminal_bundle_20260930.json"

def blob_sha(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def load(k):
    p=FILES[k]
    return json.loads(p.read_text()),blob_sha(p)

def exact_set(xs):
    return set(xs or [])

def main():
    data={}; shas={}
    for k in FILES:
        data[k],shas[k]=load(k)

    hs=data["hard_state"]; hc=data["hard_candidates"]; mc=data["mc_resolution"]
    mi=data["mc_input"]; lg=data["legal"]; st=data["stage1"]; rg=data["regime"]
    ev=data["events"]; dp=data["deep"]; ft=data["final"]

    assert hs["schema"]=="XRAY_NASDAQ_SCREENER_SINA_V2"
    assert hs["task_id"]==TASK_ID and hs["asof_et"]==ASOF
    assert hs["execution"]=="NONE" and hs["real_money"]=="NO-GO"
    assert hs["status"]=="HISTORY_COMPLETE"
    assert hs["unknown_count"]==0 and hs["pending_retry"]==0
    assert hs["cursor"]==hs["queue_total"]
    assert hs["queue_total"]==len(hs["queue"])==len(hs["security_names"])==len(hs["results"])
    assert len(set(hs["queue"]))==hs["queue_total"]
    assert not any(str(v.get("status","")).startswith("UNKNOWN") for v in hs["results"].values())

    hard_pass={s for s,v in hs["results"].items() if v.get("status")=="PASS"}
    hard_candidate_set=set((hc.get("candidates") or {}).keys())
    assert hc["schema"]=="XRAY_SINA_CANDIDATES_V2"
    assert hc["task_id"]==TASK_ID and hc["asof_et"]==ASOF
    assert hc["candidate_count"]==len(hard_candidate_set)
    assert hard_pass==hard_candidate_set

    assert mc["schema"]=="XRAY_CANONICAL_MC_RESOLUTION_V1"
    assert mc["task_id"]==TASK_ID and mc["work_asof_et"]==ASOF
    mc_set=set((mc.get("results") or {}).keys())
    assert mc_set==hard_pass
    assert mc["input_count"]==len(hard_pass)
    primary_pass={s for s,v in mc["results"].items() if v["status"]=="MC_PASS_PRIMARY"}
    primary_fail={s for s,v in mc["results"].items() if v["status"]=="MC_FAIL_PRIMARY"}
    fallback_watch={s for s,v in mc["results"].items() if v["status"]=="MC_PASS_FALLBACK_WATCH"}
    mc_unknown={s for s,v in mc["results"].items() if v["status"]=="MC_UNKNOWN"}
    assert not mc_unknown
    assert primary_pass|primary_fail|fallback_watch==hard_pass
    assert not (primary_pass&primary_fail or primary_pass&fallback_watch or primary_fail&fallback_watch)

    assert mi["schema"]=="XRAY_CANONICAL_MC_INPUT_V1"
    assert mi["task_id"]==TASK_ID and mi["asof_et"]==ASOF
    assert set(mi["current_core_mc_pass"])==primary_pass
    assert mi["current_core_count"]==len(primary_pass)
    assert set(mi["excluded_watch_only"])==fallback_watch
    assert set(mi["mc_definitive_fail"])==primary_fail

    assert lg["task_id"]==TASK_ID and lg["work_asof_et"]==ASOF
    legal_pass=set(lg["legal_pass_symbols"])
    assert lg["legal_unknown_count"]==0
    assert legal_pass==primary_pass

    assert st["schema"]=="XRAY_STAGE1_SHADOW_V1"
    assert st["task_id"]==TASK_ID and st["asof_et"]==ASOF
    assert st["unknown_count"]==0
    assert set(st["results"])==primary_pass
    weekly=set(st["weekly_pass"])
    assert st["weekly_pass_count"]==len(weekly)

    assert rg["schema"]=="XRAY_REGIME_BREADTH_SHADOW_V1"
    assert rg["task_id"]==TASK_ID and rg["asof_et"]==ASOF
    assert rg["current_core_count"]==len(primary_pass)
    assert rg["history_ok_count"]==len(primary_pass)
    assert rg["breadth_missing_count"]==0
    assert rg["regime"] in {"STRONG","MIXED","WEAK"}

    assert ev["schema"]=="XRAY_CANONICAL_EVENT_STATE_V1"
    assert ev["task_id"]==TASK_ID and ev["asof_et"]==ASOF
    assert set(ev["weekly_scope"])==weekly
    assert ev["weekly_scope_count"]==len(weekly)

    assert dp["schema"]=="XRAY_DEEP_PRE_R1_SHADOW_V1"
    assert dp["task_id"]==TASK_ID and dp["asof_et"]==ASOF
    assert dp["regime"]==rg["regime"]
    assert dp["event_state_fresh"] is True
    assert dp["input_weekly_pass_count"]==len(weekly)
    assert dp["unknown_history_count"]==0

    confirmed=set()
    confirmed.update(f"{s}|A" for s in dp.get("a_geometry_rs_event_pass",[]))
    confirmed.update(f"{s}|B" for s in dp.get("b_breakout_rs_event_pass",[]))
    confirmed.update(f"{s}|D" for s in dp.get("d_dk3_pre_r1",[]))
    b_armed=set(dp.get("b_armed_rs_event_pass",[]))
    assert not (b_armed & {x.split("|")[0] for x in confirmed if x.endswith("|B")})

    assert ft["schema"]=="XRAY_FINAL_TECH_SHADOW_V1"
    assert ft["task_id"]==TASK_ID and ft["asof_et"]==ASOF
    assert set(ft["results"])==confirmed
    assert ft["input_confirmed_family_candidates"]==len(confirmed)
    unknown_final={k:v for k,v in ft["results"].items() if v.get("result")=="UNKNOWN"}
    assert not unknown_final
    pre_g9=set(ft["pre_g9_tech_pass"])
    assert ft["pre_g9_tech_pass_count"]==len(pre_g9)

    terminal_result="NO_CONFIRMED_SETUP" if not pre_g9 else "PRE_G9_SETUP_EXISTS"
    # A technical candidate that fails/watches does not become R92. Only pre-G9 tech
    # passes can proceed toward account/G9/R92 logic.
    r92_applicable=bool(pre_g9)

    out={
      "schema":"XRAY_CANONICAL_TERMINAL_BUNDLE_V1",
      "task_id":TASK_ID,
      "asof_et":ASOF,
      "execution":"NONE",
      "real_money":"NO-GO",
      "unknown_never_pass":True,
      "full_end_to_end_research_pass":True,
      "terminal_result":terminal_result,
      "r92_account_g9_applicable":r92_applicable,
      "g9_global_status":"G9_BLOCKED_FREE_AUTOMATION_PATH",
      "account_status":"UNKNOWN",
      "counts":{
        "identity_queue":hs["queue_total"],
        "hard_gate_pass":len(hard_pass),
        "mc_primary_pass":len(primary_pass),
        "mc_primary_fail":len(primary_fail),
        "mc_fallback_watch":len(fallback_watch),
        "mc_unknown":0,
        "legal_primary_pass":len(legal_pass),
        "weekly_pass":len(weekly),
        "breadth_missing":rg["breadth_missing_count"],
        "event_confirmed_blocks":ev["confirmed_block_count"],
        "event_unresolved":ev["unresolved_count"],
        "deep_A_confirmed":len(dp.get("a_geometry_rs_event_pass",[])),
        "deep_B_breakout_confirmed":len(dp.get("b_breakout_rs_event_pass",[])),
        "deep_B_armed_non_r92":len(b_armed),
        "deep_D_confirmed":len(dp.get("d_dk3_pre_r1",[])),
        "final_confirmed_candidates":len(confirmed),
        "pre_g9_tech_pass":len(pre_g9),
        "r92_registered":0,
        "r93_registered":0,
      },
      "sets":{
        "hard_gate_pass":sorted(hard_pass),
        "mc_primary_pass":sorted(primary_pass),
        "mc_primary_fail":sorted(primary_fail),
        "mc_fallback_watch":sorted(fallback_watch),
        "weekly_pass":sorted(weekly),
        "confirmed_family_candidates":sorted(confirmed),
        "pre_g9_tech_pass":sorted(pre_g9),
        "b_armed_non_r92":sorted(b_armed),
      },
      "evidence":{
        k:{"path":str(FILES[k].relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":shas[k]}
        for k in FILES
      },
      "checks":{
        "hard_pass_exact_candidate_set":True,
        "mc_result_exact_hard_pass_set":True,
        "mc_primary_exact_mc_input_core":True,
        "legal_exact_primary_core":True,
        "stage1_exact_primary_core":True,
        "weekly_exact_event_scope":True,
        "regime_full_core_no_missing":True,
        "deep_no_history_unknown":True,
        "final_exact_confirmed_family_set":True,
        "final_no_unknown":True,
        "count_equality_never_substituted_for_set_equality":True,
      },
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
      "terminal_result":terminal_result,
      "counts":out["counts"],
      "evidence_blobs":{k:v["blob_sha"] for k,v in out["evidence"].items()}
    },sort_keys=True))

if __name__=="__main__":
    main()
