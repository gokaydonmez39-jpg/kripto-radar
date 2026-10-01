#!/usr/bin/env python3
from __future__ import annotations
import glob,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK="6a825366222081918997094d76e6ae46"
POLICY_HASH="987982f0d17fc0f01a28fe22540fc3e09d4e2f28e3aa1b40c0113e3112b44c16"
OUT=Path(os.getenv("XRAY_TERMINAL_OUT",str(ROOT/"canonical_current_terminal.json")))
FILES={
 "pointer":ROOT/"chatgpt_canonical_state_v2.json",
 "policy":ROOT/"chatgpt_compiled_policy_v3.json",
 "full_state":ROOT/"canonical_current_full_state.json",
 "master":ROOT/"canonical_current_master_manifest.json",
 "price":ROOT/"canonical_current_price_dv20.json",
 "history":ROOT/"canonical_current_history.json",
 "legal":ROOT/"canonical_current_legal.json",
 "stage1_input":ROOT/"canonical_current_stage1_input.json",
 "stage1":ROOT/"canonical_current_stage1.json",
 "regime":ROOT/"canonical_current_regime.json",
 "deep_geometry":ROOT/"canonical_current_deep_geometry.json",
 "event_request":ROOT/"canonical_current_event_request.json",
 "events":ROOT/"canonical_current_event_state.json",
 "family_c":ROOT/"canonical_current_family_c.json",
 "deep":ROOT/"canonical_current_deep_full.json",
 "final":ROOT/"canonical_current_final_tech.json",
}

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def load(p:Path):
    return json.loads(p.read_text())

def find_mc(price,price_blob):
    valid=[]
    for fp in glob.glob(str(ROOT/"canonical_mc_bridge_*.json")):
        try:
            j=json.load(open(fp))
            if (
              j.get("schema")=="XRAY_MC_EPOCH_RESULT_V1" and j.get("status")=="COMMITTED"
              and j.get("task_id")==TASK and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
              and j.get("asof_et")==price["asof_et"]
              and j.get("input_path")=="nasdaq-xray/canonical_current_price_dv20.json"
              and j.get("input_blob_sha")==price_blob
              and j.get("input_pass_hash")==price["pass_hash"]
              and j.get("policy_hash")==POLICY_HASH
              and j.get("policy_version")=="C4.11"
              and int(j.get("input_count",-1))==int(price["pass_count"])
              and set((j.get("results") or {}).keys())==set(price["pass_symbols"])
            ):
                valid.append((Path(fp),j))
        except Exception:
            pass
    if len(valid)!=1: raise RuntimeError(f"MC_BRIDGE_BINDING_MATCHES:{len(valid)}")
    return valid[0]

def main():
    d={k:load(p) for k,p in FILES.items()}
    sh={k:blob_sha(p) for k,p in FILES.items()}
    pol=d["policy"]; ptr=d["pointer"]; m=d["master"]; p=d["price"]
    assert pol["schema"]=="XRAY_GITHUB_COMPILED_POLICY_V3" and pol["policy_hash"]==POLICY_HASH
    pp=json.loads(pol["payload_json"])
    assert pp["version"]=="C4.11" and pp["hard_gates"]["order"]==["identity/type","PRICE","DV20","MC","HISTORY","LEGAL/SHELL","Stage1","deep/events"]
    assert pp["settlement"]["primary"]=="ALPACA_HISTORICAL_SIP_DAILY_AFTER_15M"
    assert "NON-G9" in pp["settlement"]["g9_separation"]
    assert p["task_id"]==m["task_id"]==TASK
    asof=p["asof_et"]
    assert m["asof_et"]==asof and m["status"]=="HISTORY_COMPLETE"
    assert m["unknown_count"]==0 and m["pending_retry"]==0
    assert p["execution"]=="NONE" and p["real_money"]=="NO-GO" and p["unknown_count"]==0
    assert p["source_master_queue_hash"]==m["queue_hash"] and int(p["source_master_count"])==int(m["queue_total"])
    ps=ptr.get("state_json") or {}
    if isinstance(ps,str): ps=json.loads(ps)
    assert isinstance(ps,dict)
    pointer_asof=str(ps.get("asof_et") or "")
    settlement_witness_required=bool(pointer_asof and asof>pointer_asof)
    assert len(p["results"])==int(m["queue_total"])
    price_pass=set(p["pass_symbols"])
    assert len(price_pass)==p["pass_count"]
    mc_path,mc=find_mc(p,sh["price"])
    if settlement_witness_required:
        assert mc.get("settlement_witness_status")=="PASS","SETTLEMENT_WITNESS_REQUIRED"
        swp=mc.get("settlement_witness_path")
        swsha=mc.get("settlement_witness_blob_sha")
        assert swp and swsha,"SETTLEMENT_WITNESS_IDENTITY_MISSING"
        sw_path=ROOT.parent/swp
        assert sw_path.exists() and blob_sha(sw_path)==swsha,"SETTLEMENT_WITNESS_BLOB_MISMATCH"
        sw=json.loads(sw_path.read_text())
        assert sw.get("schema")=="XRAY_RESOLVER_EPOCH_RESULT_V1" and sw.get("status")=="COMMITTED"
        assert sw.get("task_id")==TASK and sw.get("asof_et")==asof and sw.get("settlement_status")=="PASS"
        assert sw.get("queue_hash")==m["queue_hash"]
        assert sw.get("compiled_policy_hash")==POLICY_HASH and sw.get("compiled_policy_version")=="C4.11"
    else:
        assert mc.get("settlement_witness_status") in {None,"NOT_REQUIRED_POINTER_ASOF","PASS"}
    primary=set(mc.get("primary_pass_symbols") or [])
    mcfail=set(mc.get("primary_fail_symbols") or [])
    watch=set(mc.get("fallback_watch_symbols") or [])
    mcunk=set(mc.get("unknown_symbols") or [])
    assert not (primary&mcfail or primary&watch or primary&mcunk or mcfail&watch or mcfail&mcunk or watch&mcunk)
    assert primary|mcfail|watch|mcunk==price_pass
    assert len(mcunk)==0 and (mc.get("counts") or {}).get("MC_UNKNOWN",0)==0

    h=d["history"]; lg=d["legal"]; si=d["stage1_input"]; st=d["stage1"]; rg=d["regime"]; dg=d["deep_geometry"]
    er=d["event_request"]; ev=d["events"]; fc=d["family_c"]; dp=d["deep"]; ft=d["final"]
    for x in [h,lg,st,rg,er,ev,fc,dp,ft]:
        assert x["task_id"]==TASK and x["asof_et"]==asof and x["execution"]=="NONE" and x["real_money"]=="NO-GO"
    assert h["unknown_count"]==0 and h["input_count"]==len(primary) and set(h["results"])==primary
    assert h.get("source_mc_blob_sha")==blob_sha(mc_path)
    assert h.get("source_mc_policy_hash")==POLICY_HASH and h.get("source_mc_policy_version")=="C4.11"
    hpass=set(h["pass_symbols"]); hfail=set(h["results"])-hpass
    assert hpass|hfail==primary and not (hpass&hfail)
    assert all((h["results"][s].get("status")=="FAIL_HISTORY") for s in hfail)

    assert lg["input_count"]==len(hpass) and set(lg["results"])==hpass
    assert lg.get("source_history_blob_sha")==sh["history"] and lg.get("source_history_pass_hash")==h.get("pass_hash")
    assert lg.get("source_master_blob_sha")==sh["full_state"]
    assert (lg["counts"] or {}).get("UNKNOWN_LEGAL",0)==0 and not lg["unknown_symbols"]
    lpass=set(lg["pass_symbols"]); lblock=set(lg["blocked_symbols"])
    assert lpass|lblock==hpass and not (lpass&lblock)

    assert si["task_id"]==TASK and si["asof_et"]==asof and si["execution"]=="NONE" and si["real_money"]=="NO-GO"
    assert si.get("source_mc_blob_sha")==blob_sha(mc_path)
    assert si.get("source_history_blob_sha")==sh["history"] and si.get("source_legal_blob_sha")==sh["legal"]
    assert si.get("source_mc_policy_hash")==POLICY_HASH and si.get("source_mc_policy_version")=="C4.11"
    assert si.get("source_history_pass_hash")==h.get("pass_hash") and si.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert st["input_current_core_count"]==len(lpass) and set(st["results"])==lpass
    assert st.get("source_input_blob_sha")==sh["stage1_input"]
    assert st.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert st.get("source_mc_policy_hash")==POLICY_HASH and st.get("source_mc_policy_version")=="C4.11"
    assert st["unknown_count"]==0
    weekly=set(st["weekly_pass"]); assert len(weekly)==st["weekly_pass_count"]
    assert rg["current_core_count"]==len(lpass) and rg["breadth_missing_count"]==0
    assert rg.get("source_input_blob_sha")==sh["stage1_input"]
    assert rg.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert rg.get("source_mc_policy_hash")==POLICY_HASH and rg.get("source_mc_policy_version")=="C4.11"

    assert dg["task_id"]==TASK and dg["asof_et"]==asof and dg["execution"]=="NONE" and dg["real_money"]=="NO-GO"
    assert dg.get("source_stage1_blob_sha")==sh["stage1"]
    assert dg.get("source_mc_policy_hash")==POLICY_HASH and dg.get("source_mc_policy_version")=="C4.11"

    assert er["weekly_scope_count"]==len(weekly) and set(er["weekly_scope"])==weekly
    assert er.get("compiled_policy_hash")==POLICY_HASH and er.get("compiled_policy_version")=="C4.11"
    assert er.get("compiled_policy_blob_sha")==sh["policy"]
    assert er.get("source_stage1_blob_sha")==sh["stage1"]
    assert er.get("source_regime_blob_sha")==sh["regime"]
    assert er.get("source_deep_geometry_blob_sha")==sh["deep_geometry"]
    assert ev["weekly_scope_count"]==len(weekly) and set(ev["weekly_scope"])==weekly
    assert ev["source_request_blob_sha"]==sh["event_request"]
    assert ev.get("compiled_policy_hash")==POLICY_HASH and ev.get("compiled_policy_version")=="C4.11"
    assert ev.get("compiled_policy_blob_sha")==sh["policy"]
    assert set(ev["event_status_by_symbol"])==weekly
    assert ev["clean_discovery_count"]+ev["confirmed_block_count"]+ev["unresolved_count"]==len(weekly)

    assert fc["weekly_scope_count"]==len(weekly)
    assert fc.get("source_stage1_blob_sha")==sh["stage1"] and fc.get("source_event_blob_sha")==sh["events"]
    assert fc.get("source_compiled_policy_hash")==POLICY_HASH and fc.get("source_compiled_policy_version")=="C4.11"
    assert dp["input_weekly_pass_count"]==len(weekly) and set(dp["results"])==weekly
    assert dp.get("source_stage1_blob_sha")==sh["stage1"]
    assert dp.get("source_regime_blob_sha")==sh["regime"] and dp.get("source_event_blob_sha")==sh["events"]
    assert dp.get("source_mc_policy_hash")==POLICY_HASH and dp.get("source_mc_policy_version")=="C4.11"
    assert dp["event_state_fresh"] is True and dp["unknown_history_count"]==0
    assert dp["regime"]==rg["regime"]

    confirmed=set()
    confirmed|={f"{s}|A" for s in dp.get("a_geometry_rs_event_pass",[])}
    confirmed|={f"{s}|B" for s in dp.get("b_breakout_rs_event_pass",[])}
    confirmed|={f"{s}|D" for s in dp.get("d_dk3_pre_r1",[])}
    confirmed|={f"{s}|C" for s in (fc.get("confirmed") or {})}
    assert ft["input_confirmed_family_candidates"]==len(confirmed)
    assert ft.get("source_deep_blob_sha")==sh["deep"] and ft.get("source_family_c_blob_sha")==sh["family_c"]
    assert ft.get("source_compiled_policy_hash")==POLICY_HASH and ft.get("source_compiled_policy_version")=="C4.11"
    assert set(ft["results"])==confirmed
    final_unknown=sorted(k for k,v in ft["results"].items() if v.get("result")=="UNKNOWN")
    affected_event_unknown=sorted(ev.get("affected_geometry_event_unknown") or [])
    family_c_unknown=sorted((fc.get("unknown") or {}).keys())
    pre=set(ft.get("pre_g9_tech_pass") or [])
    assert len(pre)==int(ft.get("pre_g9_tech_pass_count",len(pre)))
    assert pre<=confirmed
    for k in pre:
        assert ft["results"][k].get("state_cap")!="WATCH"
        assert ft["results"][k].get("r92_eligible") is True

    blockers={
      "master_unknown":int(m["unknown_count"]),
      "price_unknown":int(p["unknown_count"]),
      "mc_unknown":len(mcunk),
      "history_unknown":int(h["unknown_count"]),
      "legal_unknown":int((lg["counts"] or {}).get("UNKNOWN_LEGAL",0)),
      "stage1_unknown":int(st["unknown_count"]),
      "breadth_missing":int(rg["breadth_missing_count"]),
      "deep_history_unknown":int(dp["unknown_history_count"]),
      "affected_event_unknown":len(affected_event_unknown),
      "family_c_history_unknown":len(family_c_unknown),
      "final_unknown":len(final_unknown),
    }
    full=all(v==0 for v in blockers.values())
    terminal_result=("NO_CONFIRMED_SETUP" if not pre else "PRE_G9_SETUP_EXISTS") if full else "PARTIAL_UNKNOWN"
    out={
      "schema":"XRAY_CANONICAL_CURRENT_TERMINAL_V1","status":"FULL_E2E_RESEARCH_PASS" if full else "PARTIAL",
      "task_id":TASK,"asof_et":asof,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_hash":POLICY_HASH,"compiled_policy_version":"C4.11",
      "full_end_to_end_research_pass":full,"terminal_result":terminal_result,
      "pointer_asof_before_candidate":pointer_asof,
      "settlement_witness_required":settlement_witness_required,
      "settlement_witness_status":mc.get("settlement_witness_status"),
      "settlement_witness_path":mc.get("settlement_witness_path"),
      "settlement_witness_blob_sha":mc.get("settlement_witness_blob_sha"),
      "r92_account_g9_applicable":bool(full and pre),"r92_candidates":sorted(pre) if full else [],
      "g9_global_status":ps.get("g9_status","G9_BLOCKED_FREE_AUTOMATION_PATH"),
      "account_status":ps.get("account_status","UNKNOWN"),
      "blockers":blockers,
      "counts":{
        "master_total":m["queue_total"],"price_dv20_pass":p["pass_count"],
        "mc_primary_pass":len(primary),"mc_primary_fail":len(mcfail),"mc_fallback_watch":len(watch),"mc_unknown":len(mcunk),
        "history_input":h["input_count"],"history_pass":len(hpass),"history_fail":len(hfail),
        "legal_pass":len(lpass),"legal_blocked":len(lblock),
        "weekly_pass":len(weekly),"event_confirmed_blocks":ev["confirmed_block_count"],"event_unresolved":ev["unresolved_count"],
        "deep_A_confirmed":len(dp.get("a_geometry_rs_event_pass",[])),
        "deep_B_breakout_confirmed":len(dp.get("b_breakout_rs_event_pass",[])),
        "deep_B_armed_non_r92":len(dp.get("b_armed_rs_event_pass",[])),
        "deep_C_confirmed":len(fc.get("confirmed") or {}),
        "deep_D_confirmed":len(dp.get("d_dk3_pre_r1",[])),
        "final_confirmed_candidates":len(confirmed),"pre_g9_tech_pass":len(pre),
      },
      "sets":{
        "mc_fallback_watch":sorted(watch),"history_pass":sorted(hpass),"history_fail":sorted(hfail),
        "legal_pass":sorted(lpass),"weekly_pass":sorted(weekly),"confirmed_family_candidates":sorted(confirmed),
        "pre_g9_tech_pass":sorted(pre),"affected_event_unknown":affected_event_unknown,
        "family_c_unknown":family_c_unknown,"final_unknown":final_unknown,
      },
      "evidence":{
        **{k:{"path":str(FILES[k].relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":sh[k]} for k in FILES},
        "mc":{"path":str(mc_path.relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":blob_sha(mc_path)}
      },
      "checks":{
        "policy_order_exact":True,"master_complete":True,"price_exact_master":True,"mc_exact_price_pass_set":True,
        "sequential_settlement_bound":(not settlement_witness_required) or mc.get("settlement_witness_status")=="PASS",
        "history_exact_mc_primary":True,"fallback_watch_excluded_after_mc":True,"legal_exact_history_pass":True,
        "stage1_exact_legal_pass":True,"weekly_exact_event_scope":True,"regime_no_missing":True,
        "deep_exact_weekly_scope":True,"final_exact_confirmed_family_set":True,
        "exact_blob_provenance_chain":True,
        "count_equality_never_substituted_for_set_equality":True,
      },
      "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"status":out["status"],"terminal_result":terminal_result,"blockers":blockers,"pre_g9":len(pre)},sort_keys=True))

if __name__=="__main__": main()
