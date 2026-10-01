#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK_ID="6a825366222081918997094d76e6ae46"
ASOF="2026-09-30"

FILES={
 "pointer":ROOT/"chatgpt_canonical_state_v2.json",
 "mc":ROOT/"canonical_mc_20260930_v2.json",
 "history":ROOT/"canonical_history_20260930.json",
 "legal":ROOT/"canonical_legal_20260930.json",
 "stage1":ROOT/"canonical_stage1_20260930.json",
 "regime":ROOT/"canonical_regime_20260930.json",
 "events":ROOT/"canonical_event_state_20260930.json",
 "deep":ROOT/"canonical_deep_full_20260930.json",
 "final":ROOT/"canonical_final_tech_20260930.json",
}
OUT=ROOT/"canonical_terminal_20260930.json"

def blob_sha(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def load(k):
    p=FILES[k]
    return json.loads(p.read_text()),blob_sha(p)

def assert_unique(xs,name):
    assert len(xs)==len(set(xs)),f"{name}_DUPLICATE"

def main():
    data={}; shas={}
    for k in FILES:
        data[k],shas[k]=load(k)

    ptr=data["pointer"]; mc=data["mc"]; h=data["history"]; lg=data["legal"]
    st=data["stage1"]; rg=data["regime"]; ev=data["events"]; dp=data["deep"]; ft=data["final"]

    # Durable state / prior phases
    assert ptr["schema"]=="XRAY_GITHUB_DURABLE_STATE_V3"
    ps=ptr["state_json"]
    assert ptr["execution"]=="NONE" and ptr["real_money"]=="NO-GO"
    assert ps["task_id"]==TASK_ID and ps["asof_et"]==ASOF
    assert ptr["writer_task_id"]==TASK_ID
    assert ps["master_hash"]==ps["work_cursor"]["MASTER_HASH"]
    assert "SYSTEM|ENGINE_START|C4_13|RESEARCH_FORWARD_TEST_WATCH_ONLY" in ps["transition_keys"]
    assert any(x.startswith("SYSTEM|MC_BOUND|2026-09-30|") for x in ps["transition_keys"])

    # MC exact complete set
    assert mc["schema"]=="XRAY_CANONICAL_MC_20260930_V2"
    assert mc["task_id"]==TASK_ID and mc["asof_et"]==ASOF
    assert mc["execution"]=="NONE" and mc["real_money"]=="NO-GO"
    counts=mc["counts"]
    assert counts["TOTAL"]==504 and counts["MC_UNKNOWN"]==0
    primary=set(mc["primary_pass_symbols"]); fail=set(mc["primary_fail_symbols"])
    watch=set(mc["fallback_watch_symbols"]); core=set(mc["current_core_symbols"])
    assert_unique(mc["primary_pass_symbols"],"MC_PRIMARY")
    assert_unique(mc["primary_fail_symbols"],"MC_FAIL")
    assert_unique(mc["fallback_watch_symbols"],"MC_WATCH")
    assert not (primary&fail or primary&watch or fail&watch)
    assert core==primary|watch
    assert mc["current_core_count"]==len(core)==491
    assert len(primary)==456 and len(watch)==35 and len(fail)==13
    assert set(mc["r92_ineligible"])==watch
    assert {s for s,v in mc["state_caps"].items() if v=="WATCH"}==watch

    # History exact MC core -> terminal history outcomes
    assert h["schema"]=="XRAY_CANONICAL_HISTORY_V1"
    assert h["task_id"]==TASK_ID and h["asof_et"]==ASOF
    assert h["execution"]=="NONE" and h["real_money"]=="NO-GO"
    assert h["source_mc_artifact"]=="nasdaq-xray/canonical_mc_20260930_v2.json"
    assert h["source_mc_blob_sha"]==shas["mc"]
    assert h["input_count"]==len(core)==491
    assert set(h["results"])==core
    hpass=set(h["pass_symbols"]); hunknown=set(h["unknown_symbols"])
    hfail={s for s,v in h["results"].items() if v.get("status")=="FAIL_HISTORY"}
    assert h["unknown_count"]==0 and not hunknown
    assert hpass|hfail==core and not (hpass&hfail)
    assert len(hpass)==477 and len(hfail)==14
    assert set(h["r92_ineligible"])==watch
    assert {s for s in hpass if h["state_caps"].get(s)=="WATCH"}==watch

    # Legal exact history PASS
    assert lg["schema"]=="XRAY_CANONICAL_LEGAL_V1"
    assert lg["task_id"]==TASK_ID and lg["asof_et"]==ASOF
    assert lg["execution"]=="NONE" and lg["real_money"]=="NO-GO"
    assert lg["input_count"]==len(hpass)
    lpass=set(lg["pass_symbols"]); lblock=set(lg["blocked_symbols"]); lunk=set(lg["unknown_symbols"])
    assert lpass|lblock|lunk==hpass
    assert not (lpass&lblock or lpass&lunk or lblock&lunk)
    assert lg["counts"]["UNKNOWN_LEGAL"]==0 and not lunk
    assert lpass==hpass
    assert set(lg["r92_ineligible"])==watch

    # Stage1 exact legal PASS, preserve caps
    assert st["schema"]=="XRAY_STAGE1_SHADOW_V1"
    assert st["task_id"]==TASK_ID and st["asof_et"]==ASOF
    assert st["execution"]=="NONE" and st["real_money"]=="NO-GO"
    assert st["input_current_core_count"]==len(lpass)==477
    assert set(st["results"])==lpass
    assert st["unknown_count"]==0
    assert set(st["r92_ineligible"])==watch
    assert {s for s,v in st["state_caps"].items() if v=="WATCH"}==watch
    weekly=set(st["weekly_pass"])
    assert st["weekly_pass_count"]==len(weekly)

    # Regime on exact same legal/history survivor core
    assert rg["schema"]=="XRAY_REGIME_BREADTH_SHADOW_V1"
    assert rg["task_id"]==TASK_ID and rg["asof_et"]==ASOF
    assert rg["execution"]=="NONE" and rg["real_money"]=="NO-GO"
    assert rg["current_core_count"]==len(lpass)
    assert rg["history_ok_count"]==len(lpass)
    assert rg["breadth_missing_count"]==0
    assert rg["regime"] in {"STRONG","MIXED","WEAK"}

    # Events exact weekly scope
    assert ev["schema"]=="XRAY_CANONICAL_EVENT_STATE_V1"
    assert ev["task_id"]==TASK_ID and ev["asof_et"]==ASOF
    assert ev["execution"]=="NONE" and ev["real_money"]=="NO-GO"
    assert set(ev["weekly_scope"])==weekly
    assert ev["weekly_scope_count"]==len(weekly)
    assert set(ev["event_status_by_symbol"])==weekly
    assert ev["clean_discovery_count"]+ev["confirmed_block_count"]+ev["unresolved_count"]==len(weekly)

    # Deep exact weekly scope and cap propagation
    assert dp["schema"]=="XRAY_DEEP_PRE_R1_SHADOW_V1"
    assert dp["task_id"]==TASK_ID and dp["asof_et"]==ASOF
    assert dp["execution"]=="NONE" and dp["real_money"]=="NO-GO"
    assert dp["regime"]==rg["regime"] and dp["event_state_fresh"] is True
    assert dp["input_weekly_pass_count"]==len(weekly)
    assert set(dp["results"])==weekly
    assert dp["unknown_history_count"]==0
    assert set(dp["r92_ineligible"])==watch & weekly
    assert {s for s,v in dp["state_caps"].items() if v=="WATCH"}==watch & weekly

    confirmed=set()
    confirmed.update(f"{s}|A" for s in dp.get("a_geometry_rs_event_pass",[]))
    confirmed.update(f"{s}|B" for s in dp.get("b_breakout_rs_event_pass",[]))
    confirmed.update(f"{s}|D" for s in dp.get("d_dk3_pre_r1",[]))
    barmed=set(dp.get("b_armed_rs_event_pass",[]))
    assert not (barmed & {x.split("|")[0] for x in confirmed if x.endswith("|B")})

    # Event UNKNOWN is material only if the symbol would otherwise be a confirmed finalist.
    affected_event_unknown=sorted(
        s for s,r in dp["results"].items()
        if r.get("event_status")=="UNKNOWN"
        and (
          r.get("A",{}).get("pool")
          or r.get("B",{}).get("breakout_confirmed")
          or r.get("D",{}).get("dk3_pre_r1")
        )
        and r.get("mixed_rs_pass")
    )
    assert not affected_event_unknown,affected_event_unknown

    # Final exact confirmed set
    assert ft["schema"]=="XRAY_FINAL_TECH_SHADOW_V1"
    assert ft["task_id"]==TASK_ID and ft["asof_et"]==ASOF
    assert ft["execution"]=="NONE" and ft["real_money"]=="NO-GO"
    assert set(ft["results"])==confirmed
    assert ft["input_confirmed_family_candidates"]==len(confirmed)
    unknown_final={k:v for k,v in ft["results"].items() if v.get("result")=="UNKNOWN"}
    assert not unknown_final
    pre_g9=set(ft["pre_g9_tech_pass"])
    assert ft["pre_g9_tech_pass_count"]==len(pre_g9)
    assert all(ft["results"][k].get("r92_eligible") is True for k in pre_g9)
    assert all(ft["results"][k].get("state_cap")!="WATCH" for k in pre_g9)

    terminal_result="NO_CONFIRMED_SETUP" if not pre_g9 else "PRE_G9_SETUP_EXISTS"
    out={
      "schema":"XRAY_CANONICAL_TERMINAL_V2",
      "task_id":TASK_ID,"asof_et":ASOF,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "full_end_to_end_research_pass":True,
      "terminal_result":terminal_result,
      "r92_account_g9_applicable":bool(pre_g9),
      "g9_global_status":ps.get("g9_status","G9_BLOCKED_FREE_AUTOMATION_PATH"),
      "account_status":ps.get("account_status","UNKNOWN"),
      "counts":{
        "mc_input":504,"mc_primary_pass":456,"mc_fallback_watch":35,"mc_primary_fail":13,"mc_unknown":0,
        "history_pass":len(hpass),"history_fail":len(hfail),"history_unknown":0,
        "legal_pass":len(lpass),"legal_unknown":0,
        "weekly_pass":len(weekly),"breadth_missing":0,
        "event_confirmed_blocks":ev["confirmed_block_count"],"event_unresolved":ev["unresolved_count"],
        "affected_event_unknown":0,
        "deep_A_confirmed":len(dp.get("a_geometry_rs_event_pass",[])),
        "deep_B_breakout_confirmed":len(dp.get("b_breakout_rs_event_pass",[])),
        "deep_B_armed_non_r92":len(barmed),
        "deep_D_confirmed":len(dp.get("d_dk3_pre_r1",[])),
        "final_confirmed_candidates":len(confirmed),
        "pre_g9_tech_pass":len(pre_g9),
      },
      "sets":{
        "history_pass":sorted(hpass),
        "history_fail":sorted(hfail),
        "fallback_watch":sorted(watch),
        "weekly_pass":sorted(weekly),
        "confirmed_family_candidates":sorted(confirmed),
        "pre_g9_tech_pass":sorted(pre_g9),
        "b_armed_non_r92":sorted(barmed),
      },
      "evidence":{
        k:{"path":str(FILES[k].relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":shas[k]}
        for k in FILES
      },
      "checks":{
        "mc_complete_no_unknown":True,
        "history_exact_mc_core":True,
        "legal_exact_history_pass":True,
        "stage1_exact_legal_pass":True,
        "watch_cap_preserved":True,
        "weekly_exact_event_scope":True,
        "regime_full_survivor_core_no_missing":True,
        "deep_exact_weekly_scope_no_history_unknown":True,
        "no_affected_event_unknown":True,
        "final_exact_confirmed_family_set_no_unknown":True,
        "count_equality_never_substituted_for_set_equality":True,
      },
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"terminal_result":terminal_result,"counts":out["counts"]},sort_keys=True))

if __name__=="__main__":
    main()
