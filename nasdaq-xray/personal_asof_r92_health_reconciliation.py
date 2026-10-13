#!/usr/bin/env python3
"""Independent read-only same-ASOF / R92 / Health acceptance measurement."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCES={
 "MASTER":"canonical_current_master_manifest.json",
 "PRICE":"canonical_current_price_dv30.json",
 "HISTORY":"canonical_current_history.json",
 "TERMINAL":"canonical_current_terminal.json",
 "ROOT":"sina_state.json",
 "HEALTH_RUNTIME":"health_chatgpt_runtime_attestation_20261013.json"
}
def git_blob(buf):
    return hashlib.sha1(b"blob "+str(len(buf)).encode()+b"\\0"+buf).hexdigest()
def read_sources():
    data={}
    bindings={}
    for k,path in SOURCES.items():
        p=ROOT/path
        raw=p.read_bytes()
        data[k]=json.loads(raw)
        bindings[k]={"path":"nasdaq-xray/"+path,"blob":git_blob(raw),
                     "asof_et":data[k].get("asof_et")}
    return data,bindings
def calculate(data,bindings):
    keys=("MASTER","PRICE","HISTORY","TERMINAL","ROOT")
    asofs={k:data[k].get("asof_et") for k in keys}
    same=(len(set(asofs.values()))==1 and all(asofs.values()))
    m=data["MASTER"];p=data["PRICE"];t=data["TERMINAL"];root=data["ROOT"]
    n=t.get("r92_candidates")
    registered=isinstance(n,list) and len(n)>0
    history_scope=data["HISTORY"].get("input_count")
    health=data["HEALTH_RUNTIME"]
    holiday=health.get("actual_holiday_health_invocation_observed") is True
    source_gate=all(x.get("execution")=="NONE" and
       x.get("real_money")=="NO-GO" and
       x.get("unknown_never_pass") is True
       for x in (m,p,root,t))
    checks={
       "same_asof_proven":bool(same),
       "exact_current_source_metadata_safe":bool(source_gate),
       "master_unknown_zero":m.get("unknown_count")==0,
       "price_unknown_zero":p.get("unknown_count")==0,
       "root_history_unknown_zero":root.get("unknown_count")==0,
       "terminal_full_e2e":t.get("full_end_to_end_research_pass") is True,
       "terminal_has_existing_r92":registered,
       "health_real_holiday_runtime_witness":holiday,
       "terminal_r92_official_safety_tested":bool(
          t.get("candidate_delivery_safety",{}).get("status")=="PASS")
          if isinstance(t.get("candidate_delivery_safety"),dict) else False,
    }
    # A new R92 may not be generated from this audit. Only exact current
    # canonical factory may register after independent security/event checks.
    return {"schema":"XRAY_PERSONAL_ASOF_R92_HEALTH_READONLY_RECONCILIATION_V1",
        "current_source_asofs":asofs,
        "bound_source_blobs":bindings,
        "policy":"C4.17_RELEASE_GATES_UNCHANGED",
        "real_source_checks":checks,
        "source_history_input_count":history_scope,
        "source_terminal_r92_count":len(n) if isinstance(n,list) else None,
        "official_holiday_runtime_proven":holiday,
        "current_chain_same_asof":bool(same),
        "all_release_preconditions_witnessed":all(checks.values()),
        "r92_write_performed":False,
        "canonical_mutations":False,
        "production_release":"NO-GO",
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def test():
    d,b=read_sources()
    out=calculate(d,b)
    assert out["current_chain_same_asof"] is False
    assert out["production_release"]=="NO-GO"
    assert out["r92_write_performed"] is False
    assert out["real_source_checks"]["health_real_holiday_runtime_witness"] is False
    assert d["ROOT"]["unknown_count"]==3185
    assert d["MASTER"]["unknown_count"]==10
    import copy
    bad=copy.deepcopy(d)
    bad["ROOT"]["asof_et"]=d["MASTER"]["asof_et"]
    assert calculate(bad,b)["current_chain_same_asof"] is False
    bad["HISTORY"]["asof_et"]=d["MASTER"]["asof_et"]
    bad["TERMINAL"]["asof_et"]=d["MASTER"]["asof_et"]
    assert calculate(bad,b)["current_chain_same_asof"] is True
    assert calculate(bad,b)["all_release_preconditions_witnessed"] is False
    print("XRAY_ASOF_HEALTH_R92_SELFTEST=PASS_REAL_MIXED_AND_FABRICATED_ASOF_NOT_RELEASE")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:
        test();return
    if args.out is None or args.out.resolve().is_relative_to(ROOT.parent.resolve()):
        raise ValueError("REQUIRE_NONCANONICAL_REPORT_OUTPUT")
    data,bindings=read_sources()
    result=calculate(data,bindings)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\\n")
    print("XRAY_ASOF_CHAIN_SAME="+str(result["current_chain_same_asof"]))
    print("XRAY_R92_REGISTERED="+str(result["source_terminal_r92_count"]))
    print("XRAY_HEALTH_REAL_HOLIDAY_RUNTIME="+str(result["official_holiday_runtime_proven"]))
    print("XRAY_PRODUCTION_RELEASE="+result["production_release"])

if __name__=="__main__":main()
