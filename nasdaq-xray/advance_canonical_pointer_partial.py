#!/usr/bin/env python3
from __future__ import annotations
import copy,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
POINTER=ROOT/"chatgpt_canonical_state_v2.json"
TERMINAL=ROOT/"canonical_current_terminal.json"
TASK="6a825366222081918997094d76e6ae46"

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def compact(x): return json.dumps(x,ensure_ascii=False,separators=(",",":"))
def state_hash(rev:int,state:dict)->str:
    return hashlib.sha256((f"XRAY_STATE_REGISTER_V1\n{rev}\n"+compact(state)).encode()).hexdigest()
def blob(p:Path)->str:
    return subprocess.check_output(["git","hash-object",str(p)],cwd=REPO,text=True).strip()
def ev(t:dict,key:str):
    m=(t.get("evidence") or {}).get(key) or {}
    rel=m.get("path"); sha=m.get("blob_sha")
    assert rel and sha,(key,m)
    p=REPO/rel
    assert p.exists(),(key,rel)
    assert blob(p)==sha,(key,blob(p),sha)
    return load(p),rel,sha
def uniq(seq,more):
    out=list(seq or []); seen=set(out)
    for x in more:
        if x not in seen: out.append(x);seen.add(x)
    return out

def main():
    p=load(POINTER); t=load(TERMINAL)
    assert p.get("schema")=="XRAY_GITHUB_DURABLE_STATE_V3"
    assert p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
    assert p.get("writer_task_id")==TASK
    rev=int(p["revision"]); s=copy.deepcopy(p["state_json"])
    assert state_hash(rev,s)==p["state_hash"],"CURRENT_POINTER_HASH_INVALID"
    snap=REPO/p["immutable_snapshot_path"]; q=load(snap)
    assert q["revision"]==rev and q["state_hash"]==p["state_hash"] and q["state_json"]==s
    assert state_hash(rev,q["state_json"])==q["state_hash"]

    assert t.get("schema")=="XRAY_CANONICAL_CURRENT_TERMINAL_V1"
    assert t.get("task_id")==TASK
    assert t.get("execution")=="NONE" and t.get("real_money")=="NO-GO"
    assert t.get("unknown_never_pass") is True
    assert t.get("full_end_to_end_research_pass") is False
    assert t.get("terminal_result")=="PARTIAL_UNKNOWN"
    assert t.get("status")=="PARTIAL"
    asof=str(t["asof_et"])
    assert asof>=str(s.get("asof_et") or "")
    terminal_blob=blob(TERMINAL)
    prior_terminal=((s.get("deep_final_evidence") or {}).get("terminal_blob_sha"))
    if s.get("asof_et")==asof and prior_terminal==terminal_blob:
        print(json.dumps({"status":"NOOP_ALREADY_BOUND","revision":rev,"asof_et":asof},sort_keys=True))
        return

    master,master_path,master_blob=ev(t,"master")
    price,price_path,price_blob=ev(t,"price")
    mc,mc_path,mc_blob=ev(t,"mc")
    history,history_path,history_blob=ev(t,"history")
    legal,legal_path,legal_blob=ev(t,"legal")
    stage1,stage1_path,stage1_blob=ev(t,"stage1")
    regime,regime_path,regime_blob=ev(t,"regime")
    events,event_path,event_blob=ev(t,"events")
    deep,deep_path,deep_blob=ev(t,"deep")
    final,final_path,final_blob=ev(t,"final")
    policy,policy_path,policy_blob=ev(t,"policy")
    for obj,name in [(master,"master"),(price,"price"),(mc,"mc"),(history,"history"),(legal,"legal"),
                     (stage1,"stage1"),(regime,"regime"),(events,"events"),(deep,"deep"),(final,"final")]:
        assert str(obj.get("asof_et"))==asof,(name,obj.get("asof_et"),asof)

    rp=str(t.get("settlement_witness_path") or ""); rb=str(t.get("settlement_witness_blob_sha") or "")
    assert rp and rb and t.get("settlement_witness_status")=="PASS"
    resolver=load(REPO/rp); assert blob(REPO/rp)==rb
    assert str(resolver.get("asof_et"))==asof

    tc=t.get("counts") or {}; blockers=t.get("blockers") or {}
    new_rev=rev+1
    s["revision"]=new_rev
    s["schema"]="XRAY_STATE_REGISTER_V1"
    s["asof_et"]=asof
    s["state_epoch"]=t.get("generated_at_utc")
    s["updated_at_utc"]=t.get("generated_at_utc")
    assert s["state_epoch"],"TERMINAL_TIMESTAMP_MISSING"
    s["status"]="TERMINAL_PARTIAL_UNKNOWN"
    s["active_signals"]=[]; s["r92"]=[]; s["r93"]=[]
    s["master_hash"]=master.get("pass_hash") or master.get("queue_hash")
    s["engine_mode"]="RESEARCH_FORWARD_TEST_WATCH_ONLY"
    s["runtime_kernel"]="C4.27_C4.17_PRODUCTION_RESILIENCE_V2"
    s["g9_status"]=t.get("g9_global_status")
    s["account_status"]=t.get("account_status")
    s["work_cursor"]={
      "ASOF_ET":asof,"MASTER_HASH":s["master_hash"],"PHASE":"TERMINAL_PARTIAL_UNKNOWN",
      "CHUNK_INDEX":0,"CHUNK_TOTAL":0,"COMPLETED_HASH":terminal_blob,
      "COUNTS":{
        "MASTER_TOTAL":int(tc.get("master_total",0)),"MASTER_PASS":int(tc.get("master_pass",0)),
        "MASTER_UNKNOWN":int(blockers.get("master_unknown",0)),
        "PASS_PRICE_DV30":int(tc.get("price_dv30_pass",0)),
        "PRICE_DV30_UNKNOWN":int(blockers.get("price_unknown",0)),
        "BLOCK_CURRENT_RUN":int(tc.get("price_dv30_blocked_current_run",0)),
        "MC_PASS_PRIMARY":int(tc.get("mc_primary_pass",0)),
        "MC_FAIL_PRIMARY":int(tc.get("mc_primary_fail",0)),
        "MC_PASS_FALLBACK_WATCH":int(tc.get("mc_fallback_watch",0)),
        "MC_FAIL_FALLBACK_TWO_SOURCE":int(tc.get("mc_fallback_fail",0)),
        "MC_UNKNOWN":int(tc.get("mc_unknown",0)),
        "HISTORY_INPUT":int(tc.get("history_input",0)),"HISTORY_PASS":int(tc.get("history_pass",0)),
        "HISTORY_FAIL":int(tc.get("history_fail",0)),"HISTORY_UNKNOWN":int(blockers.get("history_unknown",0)),
        "LEGAL_PASS":int(tc.get("legal_pass",0)),"LEGAL_BLOCKED":int(tc.get("legal_blocked",0)),
        "LEGAL_UNKNOWN":int(blockers.get("legal_unknown",0)),
        "WEEKLY_PASS":int(tc.get("weekly_pass",0)),"STAGE1_UNKNOWN":int(blockers.get("stage1_unknown",0)),
        "BREADTH_MISSING":int(blockers.get("breadth_missing",0)),
        "EVENT_CONFIRMED_BLOCKS":int(tc.get("event_confirmed_blocks",0)),
        "EVENT_UNRESOLVED":int(tc.get("event_unresolved",0)),
        "AFFECTED_EVENT_UNKNOWN":int(blockers.get("affected_event_unknown",0)),
        "DEEP_A_CONFIRMED":int(tc.get("deep_A_confirmed",0)),
        "DEEP_B_BREAKOUT_CONFIRMED":int(tc.get("deep_B_breakout_confirmed",0)),
        "DEEP_B_ARMED_NON_R92":int(tc.get("deep_B_armed_non_r92",0)),
        "DEEP_C_CONFIRMED":int(tc.get("deep_C_confirmed",0)),
        "DEEP_D_CONFIRMED":int(tc.get("deep_D_confirmed",0)),
        "FINAL_CONFIRMED_CANDIDATES":int(tc.get("final_confirmed_candidates",0)),
        "PRE_G9_TECH_PASS":int(tc.get("pre_g9_tech_pass",0)),
        "R92_REGISTERED":0,"R93_REGISTERED":0
      }
    }
    a=asof
    s["daily_keys"]=[x for x in (s.get("daily_keys") or []) if not str(x).startswith(f"DAILY|{a}|")]
    s["delivery_keys"]=[x for x in (s.get("delivery_keys") or []) if f"DAILY_{a}" not in str(x)]
    s["completed_epochs"]=[x for x in (s.get("completed_epochs") or []) if not (isinstance(x,dict) and x.get("asof_et")==a)]
    transitions=[
      f"SYSTEM|NORMAL_POINTER_ADVANCE|REV{new_rev}|FROM_REV{rev}",
      f"SYSTEM|MASTER_IDENTITY_BOUND|{a}|PASS{tc.get('master_pass',0)}|UNKNOWN{blockers.get('master_unknown',0)}",
      f"SYSTEM|PRICE_DV30_BOUND|{a}|PASS{tc.get('price_dv30_pass',0)}|BLOCK{tc.get('price_dv30_blocked_current_run',0)}|UNKNOWN{blockers.get('price_unknown',0)}",
      f"SYSTEM|MC_BOUND|{a}|PRIMARY{tc.get('mc_primary_pass',0)}|WATCH{tc.get('mc_fallback_watch',0)}|FAIL{int(tc.get('mc_primary_fail',0))+int(tc.get('mc_fallback_fail',0))}|UNKNOWN{tc.get('mc_unknown',0)}",
      f"SYSTEM|HISTORY_BOUND|{a}|INPUT{tc.get('history_input',0)}|PASS{tc.get('history_pass',0)}|FAIL{tc.get('history_fail',0)}",
      f"SYSTEM|EVENTS_BOUND|{a}|BLOCK{tc.get('event_confirmed_blocks',0)}|UNRESOLVED{tc.get('event_unresolved',0)}|AFFECTED_UNKNOWN{blockers.get('affected_event_unknown',0)}",
      f"SYSTEM|DEEP_FINAL_BOUND|{a}|PREG9_{tc.get('pre_g9_tech_pass',0)}",
      f"SYSTEM|TERMINAL|{a}|PARTIAL_UNKNOWN"
    ]
    s["transition_keys"]=uniq(s.get("transition_keys"),transitions)

    s["master_identity_evidence"]={"path":master_path,"blob_sha":master_blob,"asof_et":a,
      "queue_total":master.get("queue_total"),"pass_count":master.get("pass_count"),
      "unknown_count":master.get("unknown_count"),"pass_hash":master.get("pass_hash"),"completion_proof":master.get("completion_proof")}
    s["price_dv30_evidence"]={"path":price_path,"blob_sha":price_blob,"pass_count":price.get("pass_count"),
      "pass_hash":price.get("pass_hash"),"unknown_count":price.get("unknown_count"),"blocked_count":price.get("blocked_count"),"counts":price.get("counts")}
    s["compiled_policy"]={"path":policy_path,"blob_sha":policy_blob,"policy_hash":policy.get("policy_hash"),"version":"C4.17"}
    s["mc_evidence"]={"path":mc_path,"blob_sha":mc_blob,"input_price_dv30_blob_sha":mc.get("input_blob_sha"),
      "input_price_dv30_pass_hash":mc.get("input_pass_hash"),"counts":mc.get("counts"),
      "current_core_count":int(tc.get("history_input",0)),"fallback_watch_count":int(tc.get("mc_fallback_watch",0)),
      "unknown_symbols":mc.get("unknown_symbols") or []}
    s["history_evidence"]={"path":history_path,"blob_sha":history_blob,"schema":history.get("schema"),
      "input_count":history.get("input_count"),"pass_count":history.get("pass_count"),
      "fail_count":int(tc.get("history_fail",0)),"unknown_count":history.get("unknown_count"),
      "source_mc_blob_sha":history.get("source_mc_blob_sha")}
    s["legal_evidence"]={"path":legal_path,"blob_sha":legal_blob,"pass_count":int(tc.get("legal_pass",0)),
      "blocked_count":int(tc.get("legal_blocked",0)),"unknown_count":int(blockers.get("legal_unknown",0))}
    s["stage1_evidence"]={"path":stage1_path,"blob_sha":stage1_blob,"input_count":history.get("pass_count"),
      "weekly_pass_count":int(tc.get("weekly_pass",0)),"unknown_count":int(blockers.get("stage1_unknown",0))}
    s["regime_breadth_evidence"]={"path":regime_path,"blob_sha":regime_blob,"regime":regime.get("regime"),
      "breadth_missing_count":int(blockers.get("breadth_missing",0))}
    s["event_evidence"]={"path":event_path,"blob_sha":event_blob,"weekly_scope_count":events.get("weekly_scope_count"),
      "confirmed_block_count":events.get("confirmed_block_count"),"unresolved_count":events.get("unresolved_count"),
      "affected_event_unknown_count":events.get("affected_geometry_event_unknown_count")}
    s["deep_final_evidence"]={"deep_path":deep_path,"deep_blob_sha":deep_blob,"final_path":final_path,
      "final_blob_sha":final_blob,"terminal_path":"nasdaq-xray/canonical_current_terminal.json","terminal_blob_sha":terminal_blob,
      "full_end_to_end_research_pass":False,"terminal_result":"PARTIAL_UNKNOWN",
      "pre_g9_tech_pass":int(tc.get("pre_g9_tech_pass",0)),"blockers":copy.deepcopy(blockers)}
    s["settlement_resolver_evidence"]={"path":rp,"blob_sha":rb,"asof_et":a,
      "settlement_status":resolver.get("settlement_status"),"policy_version":resolver.get("policy_version"),"source":resolver.get("source")}

    nh=state_hash(new_rev,s)
    snap_rel=f"nasdaq-xray/state/REV{new_rev}_{nh}.json"
    np={
      "schema":"XRAY_GITHUB_DURABLE_STATE_V3","authority":"GITHUB_CURRENT_POINTER",
      "execution":"NONE","real_money":"NO-GO","revision":new_rev,"state_hash":nh,"prev_state_hash":p["state_hash"],
      "state_json":s,
      "source_proof":{"transition_type":"NORMAL_PARTIAL_TERMINAL_ADVANCE","source_revision":rev,
        "source_pointer_blob_sha":blob(POINTER),"source_terminal_path":"nasdaq-xray/canonical_current_terminal.json",
        "source_terminal_blob_sha":terminal_blob},
      "transition_rule":"NORMAL_PLUS_ONE_FROM_VALID_POINTER_TO_EXACT_PARTIAL_TERMINAL;NO_COMPLETION_OR_DELIVERY_PROMOTION",
      "immutable_snapshot_path":snap_rel,"storage_protocol":"GITHUB_CONTENTS_CAS_V1",
      "prev_pointer_blob_sha":blob(POINTER),"writer_task_id":TASK,
      "state_hash_rule":"SHA256_UTF8(XRAY_STATE_REGISTER_V1\\n+REVISION+\\n+COMPACT_STATE_JSON_PRESERVE_KEY_ORDER)"
    }
    ns={"schema":"XRAY_GITHUB_STATE_SNAPSHOT_V3","execution":"NONE","real_money":"NO-GO","revision":new_rev,
        "state_hash":nh,"prev_state_hash":p["state_hash"],"state_json":copy.deepcopy(s),
        "source_proof":copy.deepcopy(np["source_proof"]),"state_hash_rule":np["state_hash_rule"],
        "normal_partial_transition_snapshot":True}
    assert state_hash(new_rev,np["state_json"])==nh
    outp=REPO/snap_rel; outp.parent.mkdir(parents=True,exist_ok=True)
    POINTER.write_text(json.dumps(np,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    outp.write_text(json.dumps(ns,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"ADVANCED","revision":new_rev,"state_hash":nh,"snapshot":snap_rel,"asof_et":a},sort_keys=True))

if __name__=="__main__": main()
