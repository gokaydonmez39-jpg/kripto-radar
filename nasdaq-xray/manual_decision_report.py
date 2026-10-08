#!/usr/bin/env python3
"""Evidence-bound manual-decision NASDAQ research; never trades, never forces G9/ACCOUNT."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY=ROOT/"manual_decision_policy_v1.json"
TERMINAL=ROOT/"canonical_current_terminal.json"
EVIDENCE={
    "final":"canonical_current_final_tech.json",
    "master":"canonical_current_master_manifest.json",
    "price":"canonical_current_price_dv30.json",
    "history":"canonical_current_history.json",
    "events":"canonical_current_event_state.json",
    "policy":"chatgpt_compiled_policy_v3.json",
    "official_halt_guard":"canonical_official_source_guard.json",
}
CHECKS=(
    "alpha_semantic_conformance_exact",
    "alpha_source_binding_exact",
    "lifecycle_frozen_semantics_exact",
    "candidate_legal_guard_exact_binding",
    "all_finalists_detailed_legal_review_exact",
    "mc_exact_price_pass_set",
    "semantic_provenance_chain_exact",
    "candidate_delivery_halt_guard_fail_closed",
)
THRESH={"A":(1.5,1.1),"B":(2.,1.5),"C":(2.,1.5),"D":(2.,1.5)}

def blob(path):
    b=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def finite(x):
    if isinstance(x,bool):return None
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError,OverflowError):return None

def candidate_check(key,row,mc_rec,event_status,master_ok,price_ok,history_ok,halted):
    """Independent negative gate; no downstream decision without pre-G9 C4.17 qualification."""
    reasons=[]
    sym,sep,family=str(key).partition("|")
    if not sep or not sym or family not in THRESH or not isinstance(row,dict):
        return False,["INVALID_CANDIDATE_KEY_OR_ROW"]
    if row.get("family")!=family or row.get("pre_g9_tech_pass") is not True or row.get("technical_hard_pass") is not True:
        reasons.append("PRE_G9_TECHNICAL_NOT_PASS")
    if row.get("risk_pass") is not True:
        reasons.append("RISK_GATE_NOT_PASS")
    risk=finite((row.get("geometry") or {}).get("risk_percent"))
    if risk is None or risk<=0 or risk>0.08:
        reasons.append("RISK_PERCENT_GT_8_OR_MISSING")
    rr=row.get("rr") or {}
    basic=finite(rr.get("basic")); severe=finite(rr.get("severe"))
    b,s=THRESH[family]
    if basic is None or basic<b or rr.get("basic_pass") is not True:
        reasons.append("RR_BASIC_FAIL")
    if severe is None or severe<s or rr.get("severe_pass") is not True:
        reasons.append("RR_SEVERE_FAIL")
    if row.get("target_overlap") is not False:
        reasons.append("TARGET_OVERLAP_OR_UNKNOWN")
    if event_status!="CLEAN_DISCOVERY" or row.get("event_status")!="CLEAN_DISCOVERY":
        reasons.append("EVENT_UNRESOLVED_OR_BLOCKED")
    if not all((master_ok,price_ok,history_ok)):
        reasons.append("CANDIDATE_IDENTITY_PRICE_HISTORY_UNKNOWN")
    if (not isinstance(mc_rec,dict) or
        mc_rec.get("status")!="MC_PASS_PRIMARY" or
        mc_rec.get("r92_eligible") is not True or
        mc_rec.get("state_cap") not in ("PASS","AL","GREEN")):
        reasons.append("PRIMARY_MC_NOT_PROVEN")
    if row.get("state_cap") not in ("PASS","AL","GREEN"):
        reasons.append("CANDIDATE_WATCH_CAP")
    if row.get("regime_finalist_status")!="PASS":
        reasons.append("REGIME_NOT_PASS")
    if row.get("extension_veto") is not False:
        reasons.append("EXTENSION_VETO_OR_UNKNOWN")
    if row.get("lifecycle") in ("RECONFIRMATION_REQUIRED","RETEST_REQUIRED",None,"UNKNOWN"):
        reasons.append("LIFECYCLE_NOT_FINAL")
    if row.get("candidate_legal_hard_flags") not in ([],):
        reasons.append("CANDIDATE_LEGAL_HARD_FLAG")
    if halted:reasons.append("OFFICIAL_HALT_OR_SUSPENSION")
    if row.get("result","").startswith("FAIL"):
        reasons.append("FINAL_REJECTED")
    return not reasons,sorted(set(reasons))

def validate_and_generate(root:Path=ROOT):
    policy_path=root/"manual_decision_policy_v1.json"
    p=json.loads(policy_path.read_text())
    if not (p.get("schema")=="XRAY_MANUAL_DECISION_RESEARCH_MODE_V1"
        and p.get("mode")=="RESEARCH_ONLY_MANUAL_DECISION"
        and p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
        and p.get("parent_policy_version")=="C4.17"
        and p.get("broker_account_read_required") is False
        and p.get("broker_trade_access_allowed") is False
        and p.get("g9",{}).get("mandatory_for_research_signal") is False
        and p.get("account",{}).get("mandatory_for_research_signal") is False
        and p.get("unknown_never_pass") is True
        and p.get("alpha_thresholds_unchanged") is True
        and p.get("parent_pipeline_unchanged") is True):
        raise ValueError("MANUAL_POLICY_CONTRACT_INVALID")
    t=json.loads((root/"canonical_current_terminal.json").read_text())
    if (t.get("execution")!="NONE" or t.get("real_money")!="NO-GO" or
        t.get("unknown_never_pass") is not True or
        t.get("compiled_policy_version")!="C4.17" or
        t.get("compiled_policy_hash")!=p.get("parent_policy_sha256")):
        raise ValueError("TERMINAL_POLICY_MISMATCH")
    ev=t.get("evidence") or {}
    objs={}
    hashes={"terminal":blob(root/"canonical_current_terminal.json"),"manual_policy":blob(policy_path)}
    for key,filename in EVIDENCE.items():
        path=root/filename
        sha=blob(path)
        bound=ev.get(key) or {}
        if bound.get("path")!="nasdaq-xray/"+filename or bound.get("blob_sha")!=sha:
            raise ValueError("UNBOUND_SOURCE:"+key)
        obj=json.loads(path.read_text())
        if key!="policy" and obj.get("asof_et")!=t.get("asof_et"):
            if key!="official_halt_guard":
                raise ValueError("ASOF_DRIFT:"+key)
        if obj.get("execution")!="NONE" or obj.get("real_money")!="NO-GO":
            raise ValueError("SOURCE_SAFETY:"+key)
        objs[key]=obj;hashes[key]=sha
    cp=objs["policy"]
    if cp.get("policy_hash")!=p.get("parent_policy_sha256"):
        raise ValueError("PARENT_POLICY_HASH_DRIFT")
    checks=t.get("checks") or {}
    if any(checks.get(k) is not True for k in CHECKS):
        raise ValueError("CRITICAL_CANONICAL_CHECK_NOT_PASS")
    if (t.get("candidate_delivery_safety") or {}).get("status")!="PASS":
        raise ValueError("HALT_GUARD_NOT_PASS")
    final=objs["final"]
    if (final.get("policy_semantics_exact") is not True or
        final.get("lifecycle_semantics_exact") is not True or
        final.get("source_compiled_policy_hash")!=p["parent_policy_sha256"]):
        raise ValueError("FINAL_SEMANTICS_UNVERIFIED")
    if (len(final.get("pre_g9_tech_pass") or [])!=final.get("pre_g9_tech_pass_count")
        or final.get("pre_g9_tech_pass_count")!=(t.get("counts") or {}).get("pre_g9_tech_pass")):
        raise ValueError("PRE_G9_COUNT_DISAGREEMENT")
    mc_binding=ev.get("mc") or {}
    mc_rel=str(mc_binding.get("path") or "")
    if not (mc_rel.startswith("nasdaq-xray/canonical_mc_bridge_") and mc_rel.endswith(".json")
        and "/" not in mc_rel[len("nasdaq-xray/"):]):
        raise ValueError("MC_PATH_NOT_ALLOWED")
    mcpath=root/mc_rel.removeprefix("nasdaq-xray/")
    if blob(mcpath)!=mc_binding.get("blob_sha"):
        raise ValueError("MC_SHA_DRIFT")
    mc=json.loads(mcpath.read_text())
    if mc.get("asof_et")!=t["asof_et"]:
        raise ValueError("MC_ASOF_DRIFT")
    hashes["mc"]=blob(mcpath)
    if (objs["history"].get("source_mc_blob_sha")!=hashes["mc"]
        or mc.get("input_blob_sha")!=hashes["price"]):
        raise ValueError("PRICE_HISTORY_MC_LINEAGE_BROKEN")
    halted=set((t.get("candidate_delivery_safety") or {}).get("veto_symbols") or [])
    master=set(objs["master"].get("pass_symbols") or [])
    prices=set(objs["price"].get("pass_symbols") or [])
    histories=set(objs["history"].get("pass_symbols") or [])
    events=(objs["events"].get("event_status_by_symbol") or {})
    candidates=[];reason_counts={}
    for key,row in sorted((final.get("results") or {}).items()):
        sym=key.split("|",1)[0]
        ok,reasons=candidate_check(key,row,(mc.get("results") or {}).get(sym),
            events.get(sym),sym in master,sym in prices,sym in histories,sym in halted)
        if ok:
            levels=row.get("levels") or {}
            if not all(finite(levels.get(k)) is not None for k in ("entry_model","S0","T1")):
                ok=False;reasons=["ENTRY_STOP_TARGET_MISSING"]
        if ok:
            candidates.append({
                "symbol":sym,"setup":row.get("family"),
                "entry_model":levels["entry_model"],"stop":levels["S0"],
                "target":levels["T1"],
                "risk_percent":round(100*float(row["geometry"]["risk_percent"]),3),
                "rr_basic":row["rr"]["basic"],"rr_severe":row["rr"]["severe"],
                "trigger_date":row.get("trigger_date"),
                "asof_et":t["asof_et"],
                "label":"MANUAL_EVALUATION_RESEARCH_ONLY_NOT_LIVE_BID_ASK",
                "never_execute":True})
        else:
            for reason in reasons:reason_counts[reason]=reason_counts.get(reason,0)+1
    if candidates and t.get("candidate_local_research_pass") is not True:
        raise ValueError("TERMINAL_LOCAL_RESEARCH_NOT_PASS")
    status="QUALIFIED_RESEARCH_SIGNAL_AVAILABLE" if candidates else "NO_QUALIFIED_TECHNICAL_RESEARCH_SIGNAL"
    return {"schema":"XRAY_MANUAL_DECISION_REPORT_V1","asof_et":t["asof_et"],
        "status":status,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"manual_decision_only":True,
        "alpha_authority":False,"broker_or_account_required":False,
        "g9_required":False,"g9_current_status":"NOT_EVALUATED_IN_THIS_RESEARCH_MODE",
        "full_go_claimed":False,"order_count":0,
        "full_finalist_count":len(final.get("results") or {}),
        "pre_g9_technical_pass_count":final.get("pre_g9_tech_pass_count"),
        "research_signal_count":len(candidates),
        "research_signals":candidates[:p.get("delivery",{}).get("max_symbols",3)],
        "rejection_reason_counts":reason_counts,
        "source_blob_shas":hashes,
        "delivery_enabled":False,
        "notice":"Research evidence for user manual review; prices may be delayed, not a live market order; no broker calls."}

def selftest():
    template={"family":"D","pre_g9_tech_pass":True,
              "technical_hard_pass":True,"risk_pass":True,
              "geometry":{"risk_percent":0.06},
              "rr":{"basic":2.2,"basic_pass":True,
                    "severe":1.7,"severe_pass":True},
              "target_overlap":False,"event_status":"CLEAN_DISCOVERY",
              "state_cap":"PASS","regime_finalist_status":"PASS",
              "extension_veto":False,"lifecycle":"CONFIRMED",
              "candidate_legal_hard_flags":[],"result":"PASS"}
    mc={"status":"MC_PASS_PRIMARY","r92_eligible":True,"state_cap":"PASS"}
    run=lambda row,m=mc,event="CLEAN_DISCOVERY",halt=False: candidate_check(
        "TEST|D",row,m,event,True,True,True,halt)[0]
    assert run(template) is True
    assert run({**template,"geometry":{"risk_percent":0.081}}) is False
    assert run({**template,"risk_pass":False}) is False
    assert run({**template,"rr":{**template["rr"],"basic":1.9}}) is False
    assert run({**template,"target_overlap":True}) is False
    assert run({**template,"technical_hard_pass":False}) is False
    assert run({**template,"pre_g9_tech_pass":False}) is False
    assert run({**template,"state_cap":"WATCH"}) is False
    assert run(template,{"status":"MC_PASS_FALLBACK_WATCH","r92_eligible":False,"state_cap":"WATCH"}) is False
    assert run(template,event="UNKNOWN") is False
    assert run(template,halt=True) is False
    assert run({**template,"lifecycle":"RECONFIRMATION_REQUIRED"}) is False
    print("XRAY_MANUAL_DECISION_NEGATIVE_POSITIVE_SELFTEST=PASS")

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--selftest",action="store_true")
    arg.add_argument("--out",default="/tmp/xray_manual_decision_report.json")
    a=arg.parse_args()
    if a.selftest:selftest();return
    target=Path(a.out)
    target.unlink(missing_ok=True)
    report=validate_and_generate()
    target.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("XRAY_MANUAL_DECISION_STATUS="+report["status"])
    print("XRAY_MANUAL_DECISION_SIGNAL_COUNT="+str(report["research_signal_count"]))
    print("XRAY_MANUAL_DECISION_REPORT=SHADOW_ONLY")

if __name__=="__main__":
    main()
