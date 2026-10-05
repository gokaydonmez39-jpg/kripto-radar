# READINESS_FINAL_REBIND_AFTER_RESILIENCE_2026_10_04
#!/usr/bin/env python3
from __future__ import annotations
import glob,hashlib,json,os,re
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK="6a825366222081918997094d76e6ae46"
POLICY_HASH="26a95745a50b65e85f6ece24b6501af0994764a84ddd886edb70d1fcd770849c"
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

GATE_FILES={
 "g9_runtime":ROOT/"strict_g9_runtime_state.json",
 "account_gate":ROOT/"account_gate_contract.json",
 "account_adapter":ROOT/"account_provider_adapter_contract.json",
}
OFFICIAL_HALT_GUARD=ROOT/"canonical_official_source_guard.json"
HALT_GUARD_MAX_AGE_SECONDS=int(os.getenv("XRAY_HALT_GUARD_MAX_AGE_SECONDS","900"))

def blob_sha(p:Path):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def load(p:Path):
    return json.loads(p.read_text())

def load_gate_reporting():
    # Final-gate reporting is explicitly zero-alpha. Missing/malformed gate
    # evidence can only remain UNKNOWN/BLOCKED; it can never change FULL_E2E
    # research calculations or create a candidate.
    out={
      "g9_global_status":"G9_BLOCKED_FREE_AUTOMATION_PATH",
      "account_status":"UNKNOWN",
      "evidence":{},
    }
    try:
        p=GATE_FILES["g9_runtime"]; j=load(p)
        assert j.get("schema")=="XRAY_STRICT_G9_RUNTIME_V1"
        assert j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
        out["g9_global_status"]="G9_PASS" if j.get("g9_pass") is True else "G9_BLOCKED_FREE_AUTOMATION_PATH"
        out["evidence"]["g9_runtime"]={"path":"nasdaq-xray/strict_g9_runtime_state.json","blob_sha":blob_sha(p),"runtime_status":j.get("status"),"adapter_status":j.get("adapter_status")}
    except Exception as e:
        out["evidence"]["g9_runtime"]={"status":"UNKNOWN","reason":type(e).__name__}
    try:
        p=GATE_FILES["account_gate"]; j=load(p)
        assert j.get("schema")=="XRAY_ACCOUNT_GATE_CONTRACT_V1"
        assert j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
        assert j.get("provider")=="PROVIDER_NEUTRAL"
        ap=GATE_FILES["account_adapter"]; aj=load(ap)
        assert aj.get("schema")=="XRAY_ACCOUNT_PROVIDER_ADAPTER_CONTRACT_V1"
        bound=(j.get("adapter_contract") or {}).get("blob_sha")
        actual=blob_sha(ap)
        assert bound==actual, f"ACCOUNT_ADAPTER_BINDING_MISMATCH bound={bound} actual={actual}"
        status=str(j.get("current_status") or "UNKNOWN")
        out["account_status"]=status if status else "UNKNOWN"
        out["evidence"]["account_gate"]={"path":"nasdaq-xray/account_gate_contract.json","blob_sha":blob_sha(p),"provider":j.get("provider"),"current_adapter":j.get("current_adapter"),"adapter_contract_path":"nasdaq-xray/account_provider_adapter_contract.json","adapter_contract_blob_sha":actual}
        live_raw=str(os.getenv("XRAY_ACCOUNT_LIVE_PROBE_STATE") or "").strip()
        if live_raw:
            lp=Path(live_raw)
            live=load(lp)
            schema=str(live.get("schema") or "")
            provider=str(live.get("provider") or "")
            allowed_live={
              "XRAY_ACCOUNT_LONGBRIDGE_OPENAPI_PROBE_V1":"LONGBRIDGE_DIRECT_OPENAPI",
              "XRAY_ACCOUNT_LONGBRIDGE_HOSTED_MCP_PROBE_V1":"LONGBRIDGE_HOSTED_MCP",
              "XRAY_ACCOUNT_LONGBRIDGE_MCP_V2_PROBE_V1":"LONGBRIDGE_HOSTED_MCP_V2",
            }
            assert schema in allowed_live
            assert provider==allowed_live[schema]
            assert live.get("execution")=="NONE" and live.get("real_money")=="NO-GO"
            assert live.get("private_values_persisted") is False
            assert live.get("secret_values_persisted") is False
            current_run=str(os.getenv("GITHUB_RUN_ID") or "")
            probe_run=str(live.get("workflow_run_id") or "")
            same_run=bool(current_run and probe_run and current_run==probe_run)
            live_status=str(live.get("status") or "UNKNOWN")
            out["evidence"]["account_live_probe"]={
              "path":str(lp),
              "blob_sha":blob_sha(lp),
              "provider":provider,
              "status":live_status,
              "reason_code":live.get("reason_code"),
              "workflow_run_id":probe_run or None,
              "workflow_run_attempt":live.get("workflow_run_attempt"),
              "same_run_attested":same_run,
              "network_attempted":live.get("network_attempted") is True,
              "balance_parseable":live.get("balance_parseable") is True,
              "positions_parseable":live.get("positions_parseable") is True,
              "private_values_persisted":False,
              "secret_values_persisted":False,
            }
            if live_status=="PASS":
                adapter=(aj.get("adapters") or {}).get(provider) or {}
                assert adapter.get("status") in {
                    "ELIGIBLE_FRESH_SAME_RUN_ONLY",
                    "ELIGIBLE_FRESH_SAME_RUN_ONLY_BOOTSTRAP_READY",
                }
                assert same_run, "ACCOUNT_LIVE_PROBE_NOT_SAME_WORKFLOW_RUN"
                assert live.get("network_attempted") is True
                assert live.get("balance_parseable") is True
                assert live.get("positions_parseable") is True
                assert live.get("reason_code")=="SAME_RUN_READ_ONLY_ACCOUNT_PROBE_PASS"
                out["account_status"]="ACCOUNT_PASS"
                out["evidence"]["account_gate"]["current_adapter"]=provider
    except Exception as e:
        out["evidence"]["account_gate"]={"status":"UNKNOWN","reason":type(e).__name__}
    return out

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
              and j.get("policy_version")=="C4.17"
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
    gate_reporting=load_gate_reporting()
    assert pol["schema"]=="XRAY_GITHUB_COMPILED_POLICY_V3" and pol["policy_hash"]==POLICY_HASH
    pp=json.loads(pol["payload_json"])
    assert pp["version"]=="C4.17" and pp["hard_gates"]["order"]==["identity/type","PRICE","DV20","MC","HISTORY","LEGAL/SHELL","Stage1","deep/events"]
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
        assert sw.get("compiled_policy_hash")==POLICY_HASH and sw.get("compiled_policy_version")=="C4.17"
    else:
        assert mc.get("settlement_witness_status") in {None,"NOT_REQUIRED_POINTER_ASOF","PASS"}
    primary=set(mc.get("primary_pass_symbols") or [])
    mcfail=set(mc.get("primary_fail_symbols") or [])
    watch=set(mc.get("fallback_watch_symbols") or [])
    fallback_fail=set(mc.get("fallback_fail_symbols") or mc.get("fallback_two_source_fail_symbols") or [])
    mcunk=set(mc.get("unknown_symbols") or [])
    groups=[primary,mcfail,watch,fallback_fail,mcunk]
    for i in range(len(groups)):
        for j in range(i+1,len(groups)):
            assert not (groups[i]&groups[j])
    assert primary|mcfail|watch|fallback_fail|mcunk==price_pass
    assert len(mcunk)==0 and (mc.get("counts") or {}).get("MC_UNKNOWN",0)==0

    h=d["history"]; lg=d["legal"]; si=d["stage1_input"]; st=d["stage1"]; rg=d["regime"]; dg=d["deep_geometry"]
    er=d["event_request"]; ev=d["events"]; fc=d["family_c"]; dp=d["deep"]; ft=d["final"]
    for x in [h,lg,st,rg,er,ev,fc,dp,ft]:
        assert x["task_id"]==TASK and x["asof_et"]==asof and x["execution"]=="NONE" and x["real_money"]=="NO-GO"
    assert h["unknown_count"]==0 and h["input_count"]==len(primary) and set(h["results"])==primary
    assert h.get("source_mc_blob_sha")==blob_sha(mc_path)
    assert h.get("source_mc_policy_hash")==POLICY_HASH and h.get("source_mc_policy_version")=="C4.17"
    hpass=set(h["pass_symbols"]); hfail=set(h["results"])-hpass
    assert hpass|hfail==primary and not (hpass&hfail)
    assert all((h["results"][s].get("status")=="FAIL_HISTORY") for s in hfail)

    assert lg["input_count"]==len(hpass) and set(lg["results"])==hpass
    assert lg.get("source_history_blob_sha")==sh["history"] and lg.get("source_history_pass_hash")==h.get("pass_hash")
    legal_master_semantic_rebind=False
    if lg.get("source_master_blob_sha")!=sh["full_state"]:
        # The master file may be refreshed within the same ASOF without changing
        # identity/legal semantics (e.g. footer timestamp / updated_at metadata).
        # Never accept blob drift from count equality alone: recompute every LEGAL
        # decision from the CURRENT full-state fields actually used by legal_phase.py.
        cur=d["full_state"]
        assert cur.get("task_id")==TASK and cur.get("asof_et")==asof
        assert set(hpass)<=set((cur.get("security_names") or {}).keys())
        proof={}
        spp=lg.get("source_proof_path")
        if spp:
            pp=(ROOT.parent/spp)
            assert pp.exists() and blob_sha(pp)==lg.get("source_proof_blob_sha")
            px=load(pp)
            if px.get("schema")=="XRAY_CANONICAL_LEGAL_PROOF_V1" and px.get("task_id")==TASK and px.get("asof_et")==asof:
                proof=px.get("proofs") or {}
        suspect=re.compile(r"\\bacquisition\\b|\\bspac\\b|\\bblank check\\b",re.I)
        for s in sorted(hpass):
            name=str((cur.get("security_names") or {}).get(s) or "")
            disc=(cur.get("discovery") or {}).get(s) or {}
            industry=str(disc.get("industry") or "").strip()
            got=(lg.get("results") or {}).get(s) or {}
            if industry.lower()=="blank checks":
                assert got.get("status")=="BLOCK_LEGAL_SHELL" and got.get("reason")=="NASDAQ_SAME_RUN_INDUSTRY_BLANK_CHECKS",(s,got,industry)
                assert got.get("security_name")==name,(s,got.get("security_name"),name)
            elif suspect.search(name):
                pv=proof.get(s)
                if pv and pv.get("decision")=="OPERATING_PASS" and pv.get("source") in {"SEC","ISSUER","NASDAQ_OFFICIAL","BIGDATA_SEC_GROUNDED"}:
                    assert got.get("status")=="PASS_LEGAL" and got.get("reason")=="EXPLICIT_OPERATING_PROOF" and got.get("proof")==pv,(s,got,pv)
                elif pv and pv.get("decision")=="SHELL_BLOCK":
                    assert got.get("status")=="BLOCK_LEGAL_SHELL" and got.get("reason")=="EXPLICIT_SHELL_PROOF" and got.get("proof")==pv,(s,got,pv)
                else:
                    assert got.get("status")=="UNKNOWN_LEGAL" and got.get("reason")=="SUSPECT_SPAC_ACQUISITION_REQUIRES_PROOF",(s,got)
                    assert got.get("security_name")==name and got.get("industry")==industry,(s,got,name,industry)
            else:
                assert got.get("status")=="PASS_LEGAL" and got.get("reason")=="NO_SPAC_SHELL_INDICATOR_IN_OFFICIAL_IDENTITY_OR_SCREENER",(s,got)
                assert got.get("security_name")==name,(s,got.get("security_name"),name)
        legal_master_semantic_rebind=True
    assert (lg["counts"] or {}).get("UNKNOWN_LEGAL",0)==0 and not lg["unknown_symbols"]
    lpass=set(lg["pass_symbols"]); lblock=set(lg["blocked_symbols"])
    assert lpass|lblock==hpass and not (lpass&lblock)

    assert si["task_id"]==TASK and si["asof_et"]==asof and si["execution"]=="NONE" and si["real_money"]=="NO-GO"
    assert si.get("source_mc_blob_sha")==blob_sha(mc_path)
    assert si.get("source_history_blob_sha")==sh["history"] and si.get("source_legal_blob_sha")==sh["legal"]
    assert si.get("source_mc_policy_hash")==POLICY_HASH and si.get("source_mc_policy_version")=="C4.17"
    assert si.get("source_history_pass_hash")==h.get("pass_hash") and si.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert st["input_current_core_count"]==len(lpass) and set(st["results"])==lpass
    assert st.get("source_input_blob_sha")==sh["stage1_input"]
    assert st.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert st.get("source_mc_policy_hash")==POLICY_HASH and st.get("source_mc_policy_version")=="C4.17"
    assert st["unknown_count"]==0
    weekly=set(st["weekly_pass"]); assert len(weekly)==st["weekly_pass_count"]
    assert rg["current_core_count"]==len(lpass) and rg["breadth_missing_count"]==0
    assert rg.get("source_input_blob_sha")==sh["stage1_input"]
    assert rg.get("source_legal_pass_hash")==lg.get("pass_hash")
    assert rg.get("source_mc_policy_hash")==POLICY_HASH and rg.get("source_mc_policy_version")=="C4.17"

    assert dg["task_id"]==TASK and dg["asof_et"]==asof and dg["execution"]=="NONE" and dg["real_money"]=="NO-GO"
    assert dg.get("source_stage1_blob_sha")==sh["stage1"]
    assert dg.get("source_mc_policy_hash")==POLICY_HASH and dg.get("source_mc_policy_version")=="C4.17"

    assert er["weekly_scope_count"]==len(weekly) and set(er["weekly_scope"])==weekly
    assert er.get("compiled_policy_hash")==POLICY_HASH and er.get("compiled_policy_version")=="C4.17"
    assert er.get("compiled_policy_blob_sha")==sh["policy"]
    assert er.get("source_stage1_blob_sha")==sh["stage1"]
    assert er.get("source_regime_blob_sha")==sh["regime"]
    assert er.get("source_deep_geometry_blob_sha")==sh["deep_geometry"]
    assert ev["weekly_scope_count"]==len(weekly) and set(ev["weekly_scope"])==weekly
    assert ev["source_request_blob_sha"]==sh["event_request"]
    assert ev.get("compiled_policy_hash")==POLICY_HASH and ev.get("compiled_policy_version")=="C4.17"
    assert ev.get("compiled_policy_blob_sha")==sh["policy"]
    assert set(ev["event_status_by_symbol"])==weekly
    assert ev["clean_discovery_count"]+ev["confirmed_block_count"]+ev["unresolved_count"]==len(weekly)

    assert fc["weekly_scope_count"]==len(weekly)
    assert fc.get("source_stage1_blob_sha")==sh["stage1"] and fc.get("source_event_blob_sha")==sh["events"]
    assert fc.get("source_compiled_policy_hash")==POLICY_HASH and fc.get("source_compiled_policy_version")=="C4.17"
    assert dp["input_weekly_pass_count"]==len(weekly) and set(dp["results"])==weekly
    assert dp.get("source_stage1_blob_sha")==sh["stage1"]
    assert dp.get("source_regime_blob_sha")==sh["regime"] and dp.get("source_event_blob_sha")==sh["events"]
    assert dp.get("source_mc_policy_hash")==POLICY_HASH and dp.get("source_mc_policy_version")=="C4.17"
    assert dp["event_state_fresh"] is True and dp["unknown_history_count"]==0
    assert dp["regime"]==rg["regime"]

    confirmed=set()
    confirmed|={f"{s}|A" for s in dp.get("a_geometry_rs_event_pass",[])}
    confirmed|={f"{s}|B" for s in dp.get("b_breakout_rs_event_pass",[])}
    confirmed|={f"{s}|D" for s in dp.get("d_dk3_pre_r1",[])}
    confirmed|={f"{s}|C" for s in (fc.get("confirmed") or {})}
    assert ft["input_confirmed_family_candidates"]==len(confirmed)
    assert ft.get("source_deep_blob_sha")==sh["deep"] and ft.get("source_family_c_blob_sha")==sh["family_c"]
    assert ft.get("source_compiled_policy_hash")==POLICY_HASH and ft.get("source_compiled_policy_version")=="C4.17"
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

    # Current operational candidate-safety overlay. This never creates alpha or
    # rewrites historical event facts: it can only veto current deliverable
    # candidates or fail closed when official halt state is unavailable/stale.
    raw_pre=set(pre)
    halt_vetoed=[]
    halt_guard_unknown=0
    halt_safety={
      "status":"UNKNOWN","guard_path":"nasdaq-xray/canonical_official_source_guard.json",
      "max_age_seconds":HALT_GUARD_MAX_AGE_SECONDS,"active_halt_symbols":[],
      "vetoed_candidates":[],"zero_alpha":True,
    }
    try:
        g=load(OFFICIAL_HALT_GUARD)
        assert g.get("schema")=="XRAY_OFFICIAL_SOURCE_GUARD_V1"
        assert g.get("execution")=="NONE" and g.get("real_money")=="NO-GO"
        src=(g.get("sources") or {})
        hs=(src.get("trade_halts") or {})
        ss=(src.get("security_status") or {})
        assert hs.get("status")=="PASS"
        assert ss.get("status")=="PASS"
        gt=datetime.fromisoformat(str(g.get("generated_at_utc")).replace("Z","+00:00")).astimezone(timezone.utc)
        age=(datetime.now(timezone.utc)-gt).total_seconds()
        assert -60 <= age <= HALT_GUARD_MAX_AGE_SECONDS, f"OFFICIAL_SAFETY_GUARD_STALE:{age}"
        safety=g.get("candidate_safety") or {}
        veto=set(str(x).upper() for x in (safety.get("veto_symbols") or []))
        # Backward-safe reconstruction is only diagnostic redundancy; both
        # source feeds above must still PASS.
        active=set(str(x).upper() for x in (hs.get("active_halt_symbols") or []))
        susp=set(str(x).upper() for x in (ss.get("suspension_symbols") or []))
        assert veto==(active|susp), (sorted(veto),sorted(active|susp))
        halt_vetoed=sorted(k for k in raw_pre if str(k).split("|",1)[0].upper() in veto)
        pre=raw_pre-set(halt_vetoed)
        halt_safety.update({
          "status":"PASS","guard_blob_sha":blob_sha(OFFICIAL_HALT_GUARD),
          "generated_at_utc":g.get("generated_at_utc"),"age_seconds":round(age,3),
          "active_halt_symbols":sorted(active),
          "security_status_suspension_symbols":sorted(susp),
          "veto_symbols":sorted(veto),
          "vetoed_candidates":halt_vetoed,
        })
    except Exception as e:
        if raw_pre:
            halt_guard_unknown=1
            pre=set()
        halt_safety.update({"status":"UNKNOWN","reason":f"{type(e).__name__}:{str(e)[:180]}"})

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
      "candidate_halt_guard_unknown":halt_guard_unknown,
    }
    full=all(v==0 for v in blockers.values())
    terminal_result=("NO_CONFIRMED_SETUP" if not pre else "PRE_G9_SETUP_EXISTS") if full else "PARTIAL_UNKNOWN"
    out={
      "schema":"XRAY_CANONICAL_CURRENT_TERMINAL_V1","status":"FULL_E2E_RESEARCH_PASS" if full else "PARTIAL",
      "task_id":TASK,"asof_et":asof,"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "compiled_policy_hash":POLICY_HASH,"compiled_policy_version":"C4.17",
      "full_end_to_end_research_pass":full,"terminal_result":terminal_result,
      "pointer_asof_before_candidate":pointer_asof,
      "settlement_witness_required":settlement_witness_required,
      "settlement_witness_status":mc.get("settlement_witness_status"),
      "settlement_witness_path":mc.get("settlement_witness_path"),
      "settlement_witness_blob_sha":mc.get("settlement_witness_blob_sha"),
      "r92_account_g9_applicable":bool(full and pre),"r92_candidates":sorted(pre) if full else [],
      "candidate_delivery_safety":halt_safety,
      "g9_global_status":gate_reporting["g9_global_status"],
      "account_status":gate_reporting["account_status"],
      "final_gate_reporting_zero_alpha":True,
      "blockers":blockers,
      "counts":{
        "master_total":m["queue_total"],"price_dv20_pass":p["pass_count"],
        "mc_primary_pass":len(primary),"mc_primary_fail":len(mcfail),"mc_fallback_watch":len(watch),"mc_fallback_fail":len(fallback_fail),"mc_unknown":len(mcunk),
        "history_input":h["input_count"],"history_pass":len(hpass),"history_fail":len(hfail),
        "legal_pass":len(lpass),"legal_blocked":len(lblock),
        "weekly_pass":len(weekly),"event_confirmed_blocks":ev["confirmed_block_count"],"event_unresolved":ev["unresolved_count"],
        "deep_A_confirmed":len(dp.get("a_geometry_rs_event_pass",[])),
        "deep_B_breakout_confirmed":len(dp.get("b_breakout_rs_event_pass",[])),
        "deep_B_armed_non_r92":len(dp.get("b_armed_rs_event_pass",[])),
        "deep_C_confirmed":len(fc.get("confirmed") or {}),
        "deep_D_confirmed":len(dp.get("d_dk3_pre_r1",[])),
        "final_confirmed_candidates":len(confirmed),
        "pre_g9_tech_pass_before_halt_guard":len(raw_pre),
        "halt_vetoed_candidates":len(halt_vetoed),
        "pre_g9_tech_pass":len(pre),
      },
      "sets":{
        "mc_fallback_watch":sorted(watch),"mc_fallback_fail":sorted(fallback_fail),"history_pass":sorted(hpass),"history_fail":sorted(hfail),
        "legal_pass":sorted(lpass),"weekly_pass":sorted(weekly),"confirmed_family_candidates":sorted(confirmed),
        "pre_g9_tech_pass_before_halt_guard":sorted(raw_pre),
        "halt_vetoed_candidates":halt_vetoed,
        "pre_g9_tech_pass":sorted(pre),"affected_event_unknown":affected_event_unknown,
        "family_c_unknown":family_c_unknown,"final_unknown":final_unknown,
      },
      "evidence":{
        **{k:{"path":str(FILES[k].relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":sh[k]} for k in FILES},
        "mc":{"path":str(mc_path.relative_to(ROOT.parent)).replace("\\","/"),"blob_sha":blob_sha(mc_path)},
        "official_halt_guard":(
          {"path":"nasdaq-xray/canonical_official_source_guard.json","blob_sha":blob_sha(OFFICIAL_HALT_GUARD)}
          if OFFICIAL_HALT_GUARD.exists() else {"status":"MISSING"}
        ),
        **gate_reporting["evidence"],
      },
      "checks":{
        "policy_order_exact":True,"master_complete":True,"price_exact_master":True,"mc_exact_price_pass_set":True,
        "sequential_settlement_bound":(not settlement_witness_required) or mc.get("settlement_witness_status")=="PASS",
        "history_exact_mc_primary":True,"fallback_watch_excluded_after_mc":True,"legal_exact_history_pass":True,
        "legal_master_blob_exact":lg.get("source_master_blob_sha")==sh["full_state"],
        "legal_master_semantic_rebind":legal_master_semantic_rebind,
        "stage1_exact_legal_pass":True,"weekly_exact_event_scope":True,"regime_no_missing":True,
        "deep_exact_weekly_scope":True,"final_exact_confirmed_family_set":True,
        "exact_blob_provenance_chain":True,
        "count_equality_never_substituted_for_set_equality":True,
        "final_gate_reporting_does_not_affect_alpha":True,
        "candidate_delivery_halt_guard_fail_closed":halt_safety.get("status")=="PASS" or not raw_pre,
      },
      "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"asof":asof,"status":out["status"],"terminal_result":terminal_result,"blockers":blockers,"pre_g9":len(pre)},sort_keys=True))

if __name__=="__main__": main()
