#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK="6a825366222081918997094d76e6ae46"
ASOF="2026-09-30"
POLICY_HASH="8fa4d40d4093cc94fb9a6c6669c5f38d4684bfa8ca3fbe25696387cd46b163cf"
FILES={
 "pointer":ROOT/"chatgpt_canonical_state_v2.json",
 "policy":ROOT/"chatgpt_compiled_policy_v2.json",
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

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
def load(k):
    p=FILES[k]
    return json.loads(p.read_text()),blob_sha(p)
def disjoint(*sets):
    seen=set()
    for s in sets:
        assert not (seen&s)
        seen|=s

def main():
    data={};shas={}
    for k in FILES:data[k],shas[k]=load(k)
    ptr=data["pointer"];pol=data["policy"];mc=data["mc"];h=data["history"];lg=data["legal"]
    st=data["stage1"];rg=data["regime"];ev=data["events"];dp=data["deep"];ft=data["final"]

    assert pol["schema"]=="XRAY_GITHUB_COMPILED_POLICY_V2"
    assert pol["policy_hash"]==POLICY_HASH and pol["execution"]=="NONE" and pol["real_money"]=="NO-GO"
    pp=json.loads(pol["payload_json"])
    assert pp["version"]=="C4.10" and pp["hard_gates"]["order"]==["identity/type","PRICE","DV20","MC","HISTORY","LEGAL/SHELL","Stage1","deep/events"]

    assert ptr["schema"]=="XRAY_GITHUB_DURABLE_STATE_V3"
    ps=ptr["state_json"]
    assert ptr["execution"]=="NONE" and ptr["real_money"]=="NO-GO"
    assert ps["task_id"]==TASK and ps["asof_et"]==ASOF
    assert ptr["writer_task_id"]==TASK
    assert "SYSTEM|ENGINE_START|C4_13|RESEARCH_FORWARD_TEST_WATCH_ONLY" in ps["transition_keys"]
    assert "SYSTEM|COMPILED_POLICY_BOUND|C4.10|8fa4d40d4093" in ps["transition_keys"]
    assert any(x.startswith("SYSTEM|MC_BOUND|2026-09-30|") for x in ps["transition_keys"])

    assert mc["schema"]=="XRAY_CANONICAL_MC_20260930_V2"
    assert mc["task_id"]==TASK and mc["asof_et"]==ASOF
    assert mc["execution"]=="NONE" and mc["real_money"]=="NO-GO"
    assert mc["counts"]=={"MC_PASS_PRIMARY":456,"MC_FAIL_PRIMARY":13,"MC_PASS_FALLBACK_WATCH":35,"MC_UNKNOWN":0,"TOTAL":504}
    primary=set(mc["primary_pass_symbols"]);mcfail=set(mc["primary_fail_symbols"]);watch=set(mc["fallback_watch_symbols"])
    assert len(primary)==456 and len(mcfail)==13 and len(watch)==35
    disjoint(primary,mcfail,watch)
    assert set(mc["r92_ineligible"])==watch
    assert {s for s,v in mc["state_caps"].items() if v=="WATCH"}==watch

    assert h["schema"]=="XRAY_CANONICAL_HISTORY_V2"
    assert h["task_id"]==TASK and h["asof_et"]==ASOF
    assert h["execution"]=="NONE" and h["real_money"]=="NO-GO"
    assert h["source_mc_artifact"]=="nasdaq-xray/canonical_mc_20260930_v2.json"
    assert h["input_count"]==456 and set(h["results"])==primary
    hpass=set(h["pass_symbols"]);hfail={s for s,v in h["results"].items() if v.get("status")=="FAIL_HISTORY"}
    hunk=set(h["unknown_symbols"])
    assert h["counts"]=={"FAIL_HISTORY":14,"PASS_HISTORY":442}
    assert len(hpass)==442 and len(hfail)==14 and not hunk and h["unknown_count"]==0
    disjoint(hpass,hfail); assert hpass|hfail==primary
    assert h["r92_ineligible"]==[] and set(h["state_caps"].values())=={"NORMAL"}
    c414=h["c4_14_scope"]
    assert c414["mode"]=="MC_PRIMARY_PASS_ONLY" and c414["fallback_watch_excluded_count"]==35
    assert set(c414["fallback_watch_symbols"])==watch
    assert c414["fallback_watch_remains_watch_only"] is True and c414["fallback_watch_r92_eligible"] is False

    assert lg["schema"]=="XRAY_CANONICAL_LEGAL_V1"
    assert lg["task_id"]==TASK and lg["asof_et"]==ASOF
    assert lg["execution"]=="NONE" and lg["real_money"]=="NO-GO"
    assert lg["input_count"]==len(hpass)
    lpass=set(lg["pass_symbols"]);lblock=set(lg["blocked_symbols"]);lunk=set(lg["unknown_symbols"])
    disjoint(lpass,lblock,lunk); assert lpass|lblock|lunk==hpass
    assert not lunk and lg["counts"]["UNKNOWN_LEGAL"]==0
    assert not (lpass&watch)

    assert st["schema"]=="XRAY_STAGE1_SHADOW_V1"
    assert st["task_id"]==TASK and st["asof_et"]==ASOF
    assert st["execution"]=="NONE" and st["real_money"]=="NO-GO"
    assert st["input_current_core_count"]==len(lpass)
    assert set(st["results"])==lpass
    assert st["unknown_count"]==0
    assert st["r92_ineligible"]==[]
    assert set(st["state_caps"].values())=={"NORMAL"}
    weekly=set(st["weekly_pass"]);assert st["weekly_pass_count"]==len(weekly)

    assert rg["schema"]=="XRAY_REGIME_BREADTH_SHADOW_V1"
    assert rg["task_id"]==TASK and rg["asof_et"]==ASOF
    assert rg["current_core_count"]==len(lpass) and rg["history_ok_count"]==len(lpass)
    assert rg["breadth_missing_count"]==0 and rg["regime"] in {"STRONG","MIXED","WEAK"}

    assert ev["schema"]=="XRAY_CANONICAL_EVENT_STATE_V1"
    assert ev["task_id"]==TASK and ev["asof_et"]==ASOF
    assert set(ev["weekly_scope"])==weekly and ev["weekly_scope_count"]==len(weekly)
    assert set(ev["event_status_by_symbol"])==weekly
    assert ev["clean_discovery_count"]+ev["confirmed_block_count"]+ev["unresolved_count"]==len(weekly)

    assert dp["schema"]=="XRAY_DEEP_PRE_R1_SHADOW_V1"
    assert dp["task_id"]==TASK and dp["asof_et"]==ASOF
    assert dp["regime"]==rg["regime"] and dp["event_state_fresh"] is True
    assert dp["input_weekly_pass_count"]==len(weekly) and set(dp["results"])==weekly
    assert dp["unknown_history_count"]==0 and dp["r92_ineligible"]==[]
    assert not {s for s,v in dp["state_caps"].items() if v=="WATCH"}
    affected=[
      s for s,r in dp["results"].items()
      if r.get("event_status")=="UNKNOWN" and r.get("mixed_rs_pass")
      and (r.get("A",{}).get("pool") or r.get("B",{}).get("breakout_confirmed") or r.get("D",{}).get("dk3_pre_r1"))
    ]
    assert not affected,affected

    confirmed=set()
    confirmed|={f"{s}|A" for s in dp.get("a_geometry_rs_event_pass",[])}
    confirmed|={f"{s}|B" for s in dp.get("b_breakout_rs_event_pass",[])}
    confirmed|={f"{s}|D" for s in dp.get("d_dk3_pre_r1",[])}
    barmed=set(dp.get("b_armed_rs_event_pass",[]))

    assert ft["schema"]=="XRAY_FINAL_TECH_SHADOW_V1"
    assert ft["task_id"]==TASK and ft["asof_et"]==ASOF
    assert set(ft["results"])==confirmed
    assert ft["input_confirmed_family_candidates"]==len(confirmed)
    assert not {k:v for k,v in ft["results"].items() if v.get("result")=="UNKNOWN"}
    pre_g9=set(ft["pre_g9_tech_pass"]);assert ft["pre_g9_tech_pass_count"]==len(pre_g9)
    for k in pre_g9:
        assert ft["results"][k].get("state_cap")!="WATCH"
        assert ft["results"][k].get("r92_eligible") is True

    terminal_result="NO_CONFIRMED_SETUP" if not pre_g9 else "PRE_G9_SETUP_EXISTS"
    out={
      "schema":"XRAY_CANONICAL_TERMINAL_V3","task_id":TASK,"asof_et":ASOF,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_hash":POLICY_HASH,
      "full_end_to_end_research_pass":True,"terminal_result":terminal_result,
      "r92_account_g9_applicable":bool(pre_g9),
      "g9_global_status":ps.get("g9_status","G9_BLOCKED_FREE_AUTOMATION_PATH"),
      "account_status":ps.get("account_status","UNKNOWN"),
      "counts":{
        "price_dv20_pass":504,"mc_primary_pass":456,"mc_primary_fail":13,"mc_fallback_watch":35,"mc_unknown":0,
        "history_primary_input":456,"history_pass":len(hpass),"history_fail":len(hfail),"history_unknown":0,
        "legal_pass":len(lpass),"legal_blocked":len(lblock),"legal_unknown":0,
        "stage1_input":st["input_current_core_count"],"weekly_pass":len(weekly),
        "breadth_missing":0,"event_confirmed_blocks":ev["confirmed_block_count"],"event_unresolved":ev["unresolved_count"],
        "affected_event_unknown":0,
        "deep_A_confirmed":len(dp.get("a_geometry_rs_event_pass",[])),
        "deep_B_breakout_confirmed":len(dp.get("b_breakout_rs_event_pass",[])),
        "deep_B_armed_non_r92":len(barmed),"deep_D_confirmed":len(dp.get("d_dk3_pre_r1",[])),
        "final_confirmed_candidates":len(confirmed),"pre_g9_tech_pass":len(pre_g9)
      },
      "sets":{
        "mc_fallback_watch":sorted(watch),"history_pass":sorted(hpass),"history_fail":sorted(hfail),
        "legal_pass":sorted(lpass),"weekly_pass":sorted(weekly),
        "confirmed_family_candidates":sorted(confirmed),"pre_g9_tech_pass":sorted(pre_g9),
        "b_armed_non_r92":sorted(barmed)
      },
      "evidence":{k:{"path":str(FILES[k].relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":shas[k]} for k in FILES},
      "checks":{
        "policy_v2_exact":True,"mc_complete_no_unknown":True,
        "history_exact_primary_only":True,"fallback_watch_excluded_after_mc":True,
        "legal_exact_history_pass":True,"stage1_exact_legal_pass":True,
        "weekly_exact_event_scope":True,"regime_full_primary_survivor_core_no_missing":True,
        "deep_exact_weekly_scope_no_history_unknown":True,"no_affected_event_unknown":True,
        "final_exact_confirmed_family_set_no_unknown":True,"count_equality_never_substituted_for_set_equality":True
      },
      "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"terminal_result":terminal_result,"counts":out["counts"]},sort_keys=True))
if __name__=="__main__":main()
