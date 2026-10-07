#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
POINTER=ROOT/"chatgpt_canonical_state_v2.json"
TERMINAL=ROOT/"canonical_current_terminal.json"
TASK="6a825366222081918997094d76e6ae46"

def load(path:Path)->dict:
    return json.loads(path.read_text(encoding="utf-8"))

def compact(state:dict)->str:
    return json.dumps(state,ensure_ascii=False,separators=(",",":"))

def state_hash(rev:int,state:dict)->str:
    raw=f"XRAY_STATE_REGISTER_V1\n{rev}\n{compact(state)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def blob(path:Path)->str:
    return subprocess.check_output(["git","hash-object",str(path)],cwd=REPO,text=True).strip()

def append_unique(seq,items):
    out=list(seq or []); seen=set(out)
    for x in items:
        if x not in seen: out.append(x); seen.add(x)
    return out

def evidence(term,key):
    m=(term.get("evidence") or {}).get(key) or {}
    rel=m.get("path"); sha=m.get("blob_sha")
    assert rel and sha,(key,m)
    p=REPO/rel
    assert p.exists(),(key,rel)
    assert blob(p)==sha,(key,blob(p),sha)
    return load(p),rel,sha

def build(old:dict,term:dict,old_blob:str):
    rev=int(old["revision"]); state=old["state_json"]
    assert old["schema"]=="XRAY_GITHUB_DURABLE_STATE_V3"
    assert old["execution"]=="NONE" and old["real_money"]=="NO-GO"
    assert old.get("writer_task_id")==TASK
    assert int(state["revision"])==rev
    assert state_hash(rev,state)==old["state_hash"]
    snap=REPO/old["immutable_snapshot_path"]; qs=load(snap)
    assert qs["revision"]==rev and qs["state_hash"]==old["state_hash"] and qs["state_json"]==state
    assert state_hash(rev,qs["state_json"])==qs["state_hash"]

    assert term["schema"]=="XRAY_CANONICAL_CURRENT_TERMINAL_V1"
    assert term["execution"]=="NONE" and term["real_money"]=="NO-GO"
    assert term.get("unknown_never_pass") is True
    assert term.get("task_id")==TASK
    asof=str(term["asof_et"])
    assert asof>str(state.get("asof_et") or ""),(state.get("asof_et"),asof)

    # Re-measure every immutable research source before advancing durability.
    master,master_path,master_sha=evidence(term,"master")
    price,price_path,price_sha=evidence(term,"price")
    hist,hist_path,hist_sha=evidence(term,"history")
    legal,legal_path,legal_sha=evidence(term,"legal")
    stage1,stage1_path,stage1_sha=evidence(term,"stage1")
    regime,regime_path,regime_sha=evidence(term,"regime")
    events,event_path,event_sha=evidence(term,"events")
    deep,deep_path,deep_sha=evidence(term,"deep")
    final,final_path,final_sha=evidence(term,"final")
    policy,policy_path,policy_sha=evidence(term,"policy")
    mc,mc_path,mc_sha=evidence(term,"mc")
    sw_path=str(term.get("settlement_witness_path") or "")
    sw_sha=str(term.get("settlement_witness_blob_sha") or "")
    assert sw_path and sw_sha
    swp=REPO/sw_path; assert swp.exists() and blob(swp)==sw_sha
    settlement=load(swp)
    assert term.get("settlement_witness_status")=="PASS"

    ns=copy.deepcopy(state)
    nrev=rev+1
    ns["revision"]=nrev
    ns["asof_et"]=asof
    ns["state_epoch"]=term.get("generated_at_utc")
    ns["updated_at_utc"]=term.get("generated_at_utc")
    ns["active_signals"]=[]
    ns["r92"]=[]; ns["r93"]=[]
    ns["master_hash"]=master.get("pass_hash") or master.get("queue_hash")
    ns["engine_mode"]="RESEARCH_FORWARD_TEST_WATCH_ONLY"
    ns["g9_status"]=term.get("g9_global_status")
    ns["account_status"]=term.get("account_status")
    ns["runtime_kernel"]="C4.27_C4.17_PRODUCTION_RESILIENCE_V2"

    full=term.get("full_end_to_end_research_pass") is True
    if full:
        ns["status"]="TERMINAL_FULL_E2E_NO_CONFIRMED_SETUP" if not (term.get("sets") or {}).get("pre_g9_tech_pass") else "TERMINAL_PRE_G9_SETUP_EXISTS"
    else:
        assert term.get("terminal_result")=="PARTIAL_UNKNOWN"
        assert any(int(v or 0)>0 for v in (term.get("blockers") or {}).values())
        ns["status"]="TERMINAL_PARTIAL_UNKNOWN"

    tc=term.get("counts") or {}; bl=term.get("blockers") or {}
    ns["work_cursor"]={
      "ASOF_ET":asof,
      "MASTER_HASH":master.get("pass_hash") or master.get("queue_hash"),
      "PHASE":"TERMINAL" if full else "TERMINAL_PARTIAL_UNKNOWN",
      "CHUNK_INDEX":0,"CHUNK_TOTAL":0,
      "COMPLETED_HASH":blob(TERMINAL),
      "COUNTS":{
        "MASTER_TOTAL":int(tc.get("master_total",0) or 0),
        "MASTER_UNIQUE":int(master.get("raw_identity_total",tc.get("master_total",0)) or 0),
        "UNKNOWN":int(bl.get("master_unknown",0) or 0),
        "PASS_PRICE_DV30":int(tc.get("price_dv30_pass",0) or 0),
        "PRICE_DV30_UNKNOWN":int(bl.get("price_unknown",0) or 0),
        "BLOCK_CURRENT_RUN":int(tc.get("price_dv30_blocked_current_run",0) or 0),
        "MC_PASS_PRIMARY":int(tc.get("mc_primary_pass",0) or 0),
        "MC_FAIL_PRIMARY":int(tc.get("mc_primary_fail",0) or 0),
        "MC_FAIL_FALLBACK_TWO_SOURCE":int(tc.get("mc_fallback_fail",0) or 0),
        "MC_PASS_FALLBACK_WATCH":int(tc.get("mc_fallback_watch",0) or 0),
        "MC_UNKNOWN":int(tc.get("mc_unknown",0) or 0),
        "TOTAL":int(tc.get("price_dv30_pass",0) or 0),
        "CURRENT_CORE_MC":int(tc.get("history_input",0) or 0),
        "HISTORY_INPUT":int(tc.get("history_input",0) or 0),
        "HISTORY_PASS":int(tc.get("history_pass",0) or 0),
        "HISTORY_FAIL":int(tc.get("history_fail",0) or 0),
        "HISTORY_UNKNOWN":int(bl.get("history_unknown",0) or 0),
        "LEGAL_PASS":int(tc.get("legal_pass",0) or 0),
        "LEGAL_BLOCKED":int(tc.get("legal_blocked",0) or 0),
        "LEGAL_UNKNOWN":int(bl.get("legal_unknown",0) or 0),
        "STAGE1_INPUT":int(hist.get("pass_count",0) or 0),
        "WEEKLY_PASS":int(tc.get("weekly_pass",0) or 0),
        "BREADTH_MISSING":int(bl.get("breadth_missing",0) or 0),
        "EVENT_CONFIRMED_BLOCKS":int(tc.get("event_confirmed_blocks",0) or 0),
        "EVENT_UNRESOLVED":int(tc.get("event_unresolved",0) or 0),
        "AFFECTED_EVENT_UNKNOWN":int(bl.get("affected_event_unknown",0) or 0),
        "DEEP_A_CONFIRMED":int(tc.get("deep_A_confirmed",0) or 0),
        "DEEP_B_BREAKOUT_CONFIRMED":int(tc.get("deep_B_breakout_confirmed",0) or 0),
        "DEEP_B_ARMED_NON_R92":int(tc.get("deep_B_armed_non_r92",0) or 0),
        "DEEP_C_CONFIRMED":int(tc.get("deep_C_confirmed",0) or 0),
        "DEEP_D_CONFIRMED":int(tc.get("deep_D_confirmed",0) or 0),
        "FINAL_CONFIRMED_CANDIDATES":int(tc.get("final_confirmed_candidates",0) or 0),
        "PRE_G9_TECH_PASS":int(tc.get("pre_g9_tech_pass",0) or 0),
        "R92_REGISTERED":0,"R93_REGISTERED":0
      }
    }

    ns["transition_keys"]=append_unique(ns.get("transition_keys"),[
      f"SYSTEM|POINTER_ADVANCE|REV{nrev}|FROM_REV{rev}|{asof}",
      f"SYSTEM|MASTER_IDENTITY_BOUND|{asof}|{str(master.get('pass_hash') or master.get('queue_hash') or '')[:12]}",
      f"SYSTEM|PRICE_DV30_BOUND|{asof}|{str(price.get('pass_hash') or '')[:12]}",
      f"SYSTEM|SETTLEMENT_BOUND|{asof}|PASS|C4.17_DV30",
      f"SYSTEM|MC_BOUND|{asof}|PRIMARY{tc.get('mc_primary_pass',0)}|WATCH{tc.get('mc_fallback_watch',0)}|FAIL{int(tc.get('mc_primary_fail',0) or 0)+int(tc.get('mc_fallback_fail',0) or 0)}|UNKNOWN{tc.get('mc_unknown',0)}",
      f"SYSTEM|HISTORY_BOUND|{asof}|INPUT{tc.get('history_input',0)}|PASS{tc.get('history_pass',0)}|FAIL{tc.get('history_fail',0)}",
      f"SYSTEM|EVENTS_BOUND|{asof}|UNRESOLVED{tc.get('event_unresolved',0)}|AFFECTED_UNKNOWN{bl.get('affected_event_unknown',0)}",
      f"SYSTEM|DEEP_FINAL_BOUND|{asof}|PREG9_{tc.get('pre_g9_tech_pass',0)}",
      f"SYSTEM|TERMINAL|{asof}|{'FULL_E2E' if full else 'PARTIAL_UNKNOWN'}|{term.get('terminal_result')}"
    ])

    # Partial epochs are durable current state, never false completed/delivered epochs.
    ns["daily_keys"]=list(ns.get("daily_keys") or [])
    ns["delivery_keys"]=list(ns.get("delivery_keys") or [])
    ns["completed_epochs"]=list(ns.get("completed_epochs") or [])
    if full:
        # Only a real FULL_E2E epoch may become a completed epoch.
        entry={
          "asof_et":asof,"status":ns["status"],"full_end_to_end_research_pass":True,
          "terminal_result":term.get("terminal_result"),
          "terminal_path":"nasdaq-xray/canonical_current_terminal.json",
          "terminal_blob_sha":blob(TERMINAL),"deep_blob_sha":deep_sha,"final_blob_sha":final_sha,
          "final_confirmed_candidates":int(tc.get("final_confirmed_candidates",0) or 0),
          "pre_g9_tech_pass":int(tc.get("pre_g9_tech_pass",0) or 0),
          "b_armed_non_r92":int(tc.get("deep_B_armed_non_r92",0) or 0)
        }
        ns["completed_epochs"]=[x for x in ns["completed_epochs"] if not (isinstance(x,dict) and x.get("asof_et")==asof)]+[entry]
        dk=f"DAILY|{asof}|"+("FULL_E2E_NO_CONFIRMED_SETUP" if not (term.get("sets") or {}).get("pre_g9_tech_pass") else "PRE_G9_SETUP_EXISTS")
        ns["daily_keys"]=append_unique(ns["daily_keys"],[dk])
    else:
        assert not any(str(x).startswith(f"DAILY|{asof}|") for x in ns["daily_keys"])
        assert not any(f"DAILY_{asof}" in str(x) for x in ns["delivery_keys"])
        assert not any(isinstance(x,dict) and x.get("asof_et")==asof for x in ns["completed_epochs"])

    ns["master_identity_evidence"]={"path":master_path,"blob_sha":master_sha,"asof_et":asof,"queue_total":master.get("queue_total"),"raw_identity_total":master.get("raw_identity_total"),"pass_count":master.get("pass_count"),"unknown_count":master.get("unknown_count"),"pass_hash":master.get("pass_hash")}
    ns["price_dv30_evidence"]={"path":price_path,"blob_sha":price_sha,"pass_count":price.get("pass_count"),"pass_hash":price.get("pass_hash"),"unknown_count":price.get("unknown_count"),"blocked_count":price.get("blocked_count"),"counts":price.get("counts")}
    ns["compiled_policy"]={"path":policy_path,"blob_sha":policy_sha,"policy_hash":policy.get("policy_hash"),"version":"C4.17"}
    ns["mc_evidence"]={"path":mc_path,"blob_sha":mc_sha,"input_price_dv30_blob_sha":(term.get("evidence") or {}).get("mc",{}).get("current_price_blob_sha"),"input_price_dv30_pass_hash":mc.get("input_pass_hash"),"counts":mc.get("counts"),"unknown_symbols":mc.get("unknown_symbols") or []}
    ns["history_evidence"]={"path":hist_path,"blob_sha":hist_sha,"schema":hist.get("schema"),"input_count":hist.get("input_count"),"pass_count":hist.get("pass_count"),"fail_count":int(tc.get("history_fail",0) or 0),"unknown_count":hist.get("unknown_count"),"source_mc_blob_sha":hist.get("source_mc_blob_sha")}
    ns["legal_evidence"]={"path":legal_path,"blob_sha":legal_sha,"pass_count":int(tc.get("legal_pass",0) or 0),"blocked_count":int(tc.get("legal_blocked",0) or 0),"unknown_count":int(bl.get("legal_unknown",0) or 0)}
    ns["stage1_evidence"]={"path":stage1_path,"blob_sha":stage1_sha,"input_count":hist.get("pass_count"),"weekly_pass_count":int(tc.get("weekly_pass",0) or 0),"unknown_count":int(bl.get("stage1_unknown",0) or 0)}
    ns["regime_breadth_evidence"]={"path":regime_path,"blob_sha":regime_sha,"regime":regime.get("regime"),"breadth_missing_count":int(bl.get("breadth_missing",0) or 0)}
    ns["event_evidence"]={"path":event_path,"blob_sha":event_sha,"weekly_scope_count":events.get("weekly_scope_count"),"confirmed_block_count":events.get("confirmed_block_count"),"unresolved_count":events.get("unresolved_count"),"affected_event_unknown_count":events.get("affected_geometry_event_unknown_count")}
    ns["deep_final_evidence"]={"deep_path":deep_path,"deep_blob_sha":deep_sha,"final_path":final_path,"final_blob_sha":final_sha,"terminal_path":"nasdaq-xray/canonical_current_terminal.json","terminal_blob_sha":blob(TERMINAL),"full_end_to_end_research_pass":full,"terminal_result":term.get("terminal_result"),"pre_g9_tech_pass":int(tc.get("pre_g9_tech_pass",0) or 0),"blockers":copy.deepcopy(bl)}
    ns["settlement_resolver_evidence"]={"path":sw_path,"blob_sha":sw_sha,"asof_et":asof,"settlement_status":settlement.get("settlement_status"),"policy_version":settlement.get("policy_version"),"source":settlement.get("source")}
    ns.pop("pointer_hash_recovery",None)

    nh=state_hash(nrev,ns)
    snap_rel=f"nasdaq-xray/state/REV{nrev}_{nh}.json"
    proof={
      "transition_type":"NORMAL_TERMINAL_ADVANCE",
      "source_revision":rev,"source_state_hash":old["state_hash"],"source_pointer_blob_sha":old_blob,
      "source_terminal_path":"nasdaq-xray/canonical_current_terminal.json","source_terminal_blob_sha":blob(TERMINAL),
      "target_asof_et":asof,"target_terminal_result":term.get("terminal_result"),
      "full_end_to_end_research_pass":full
    }
    np={
      "schema":"XRAY_GITHUB_DURABLE_STATE_V3","authority":"GITHUB_CURRENT_POINTER",
      "execution":"NONE","real_money":"NO-GO","revision":nrev,"state_hash":nh,
      "prev_state_hash":old["state_hash"],"state_json":ns,"source_proof":proof,
      "transition_rule":"NORMAL_EXACT_PLUS_ONE;PREV_STATE_HASH_EQUALS_IMMEDIATE_PRIOR_STATE_HASH;TERMINAL_AND_IMMUTABLE_EVIDENCE_BLOBS_EXACT",
      "immutable_snapshot_path":snap_rel,"storage_protocol":"GITHUB_CONTENTS_CAS_V1",
      "prev_pointer_blob_sha":old_blob,"writer_task_id":TASK,
      "state_hash_rule":"SHA256_UTF8(XRAY_STATE_REGISTER_V1\\n+REVISION+\\n+COMPACT_STATE_JSON_PRESERVE_KEY_ORDER)"
    }
    snap={
      "schema":"XRAY_GITHUB_STATE_SNAPSHOT_V3","execution":"NONE","real_money":"NO-GO",
      "revision":nrev,"state_hash":nh,"prev_state_hash":old["state_hash"],
      "state_json":copy.deepcopy(ns),"source_proof":copy.deepcopy(proof),
      "state_hash_rule":np["state_hash_rule"],"recovery_snapshot":False
    }
    assert np["revision"]==rev+1 and np["prev_state_hash"]==old["state_hash"]
    assert state_hash(nrev,np["state_json"])==np["state_hash"]
    assert state_hash(nrev,snap["state_json"])==snap["state_hash"]
    return np,snap,snap_rel

def pointer_exact_current(old,term,current_terminal_blob):
    s=old.get("state_json") or {}
    df=s.get("deep_final_evidence") or {}
    return bool(
        str(s.get("asof_et") or "")==str(term.get("asof_et") or "")
        and df.get("terminal_path")=="nasdaq-xray/canonical_current_terminal.json"
        and df.get("terminal_blob_sha")==current_terminal_blob
    )

def selftest():
    s={"revision":4,"schema":"XRAY_STATE_REGISTER_V1","asof_et":"2026-01-01",
       "deep_final_evidence":{"terminal_path":"nasdaq-xray/canonical_current_terminal.json","terminal_blob_sha":"NEW"}}
    h=state_hash(4,s)
    assert len(h)==64 and h==state_hash(4,copy.deepcopy(s))
    assert state_hash(5,s)!=h
    p={"revision":4,"state_hash":h,"state_json":s}
    t={"asof_et":"2026-01-01"}
    assert pointer_exact_current(p,t,"NEW") is True
    assert pointer_exact_current(p,t,"OLD") is False
    assert pointer_exact_current(p,{"asof_et":"2026-01-02"},"NEW") is False
    print("XRAY_CANONICAL_POINTER_TRANSITION_SELFTEST=PASS")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    old=load(POINTER); term=load(TERMINAL)
    current_terminal_blob=blob(TERMINAL)
    if pointer_exact_current(old,term,current_terminal_blob):
        # Already advanced only when both epoch and immutable terminal content match.
        assert state_hash(int(old["revision"]),old["state_json"])==old["state_hash"]
        print(json.dumps({"changed":False,"reason":"ALREADY_EXACT_CURRENT","revision":old["revision"],"asof_et":term["asof_et"],"terminal_blob_sha":current_terminal_blob},sort_keys=True))
        return
    old_blob=blob(POINTER)
    np,snap,snap_rel=build(old,term,old_blob)
    POINTER.write_text(json.dumps(np,ensure_ascii=False,sort_keys=False,indent=2)+"\n",encoding="utf-8")
    sp=REPO/snap_rel; sp.parent.mkdir(parents=True,exist_ok=True)
    sp.write_text(json.dumps(snap,ensure_ascii=False,sort_keys=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"changed":True,"revision":np["revision"],"state_hash":np["state_hash"],"prev_state_hash":np["prev_state_hash"],"asof_et":np["state_json"]["asof_et"],"status":np["state_json"]["status"],"snapshot":snap_rel},sort_keys=True))

if __name__=="__main__":
    main()
