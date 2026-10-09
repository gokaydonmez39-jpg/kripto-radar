#!/usr/bin/env python3
"""Prepare a verified, zero-alpha CURRENT MC request from immutable GitHub sources.

This repairs request *provenance preparation* only. It does NOT modify a
disabled ChatGPT task, measure MC, create PRIMARY/AL or activate C4.18.
Research mode only, no licensed vendor prices or bars are exported.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
POLICY_SHA="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
POLICY_HASH="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
TASK="6a825366222081918997094d76e6ae46"
CURRENT_PRICE="nasdaq-xray/canonical_current_price_dv30.json"
SCHEMA="XRAY_MC_REQUEST_FRESHNESS_REBIND_V1"

def hash_lines(rows):
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()

def blob(path):
    return subprocess.check_output(
        ["git","hash-object",str(path)],cwd=REPO,text=True).strip()

def load_exact(repo_relative):
    path=(REPO/repo_relative).resolve()
    if not path.is_relative_to(REPO.resolve()) or not path.is_file():
        raise ValueError("SOURCE_PATH_INVALID")
    return json.loads(path.read_text(encoding="utf-8")),blob(path)

def assert_same_asof(price,handoff,price_sha,handoff_sha,policy_sha,settlement=None,settlement_sha=None):
    assert policy_sha==POLICY_SHA,"POLICY_BLOB_DRIFT"
    assert price.get("execution")==handoff.get("execution")=="NONE"
    assert price.get("real_money")==handoff.get("real_money")=="NO-GO"
    assert price.get("unknown_never_pass") is handoff.get("unknown_never_pass") is True
    asof=price.get("asof_et")
    assert isinstance(asof,str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}",asof)
    assert handoff.get("asof_et")==asof,"ASOF_DRIFT"
    symbols=price.get("pass_symbols")
    assert isinstance(symbols,list) and symbols==sorted(set(symbols)) and len(symbols)>0
    assert price.get("pass_count")==len(symbols),"PRICE_COUNT_MISMATCH"
    assert price.get("pass_hash")==hash_lines(symbols),"PRICE_PASS_HASH_MISMATCH"
    assert price.get("unknown_count")==0,"PRICE_UNKNOWN_NONZERO"
    assert type(price.get("blocked_count")) is int and price["blocked_count"]>=0
    assert handoff.get("source_price_blob_sha")==price_sha,"HANDOFF_PRICE_SHA_MISMATCH"
    assert handoff.get("status")=="COMMITTED" and handoff.get("bridge_role")=="FULL_SCOPE_MC_HANDOFF_PROVENANCE"
    assert handoff.get("coverage_complete") is True and handoff.get("classification_coverage_complete") is True
    assert handoff.get("partial_data") is False
    assert handoff.get("compiled_policy_blob_sha")==POLICY_SHA and handoff.get("compiled_policy_hash")==POLICY_HASH
    assert handoff.get("compiled_policy_version")=="C4.17"
    assert handoff.get("settlement_status")=="PASS","SETTLEMENT_NOT_PROVEN"
    ch=handoff.get("current_handoff",{})
    assert ch.get("price_blob_sha")==price_sha and ch.get("pass_count")==len(symbols)
    assert ch.get("pass_hash")==price["pass_hash"] and ch.get("blocked_count")==price["blocked_count"]
    assert ch.get("blocked_subset_of_full_scope_block") is True
    assert ch.get("no_new_pass_beyond_resolver") is True
    assert handoff.get("price_unknown_count")==0
    assert handoff.get("union_disjoint_proof",{}).get("pass_set_exact_current_price") is True
    assert isinstance(handoff_sha,str) and re.fullmatch(r"[0-9a-f]{40}",handoff_sha)
    if settlement is not None:
        assert handoff.get("settlement_witness_blob_sha")==settlement_sha,"SETTLEMENT_BLOB_DRIFT"
        assert settlement.get("status")=="COMMITTED" and settlement.get("settlement_status")=="PASS"
        assert settlement.get("asof_et")==asof
        assert settlement.get("compiled_policy_blob_sha")==POLICY_SHA
    return {
       "schema":SCHEMA,"status":"CURRENT_REQUEST_EVIDENCE_READY_NO_MC_MEASUREMENT",
       "asof_et":asof,"task_id":TASK,
       "input_path":CURRENT_PRICE,"input_blob_sha":price_sha,
       "input_pass_count":len(symbols),"input_pass_hash":price["pass_hash"],
       "input_pass_symbols":symbols,
       "input_unknown_count":0,"input_blocked_count":price["blocked_count"],
       "resolver_provenance_blob_sha":handoff_sha,
       "resolver_role":"FULL_SCOPE_MC_HANDOFF_AUTHORITY",
       "settlement_status":"PASS",
       "policy_path":"nasdaq-xray/chatgpt_compiled_policy_v3.json",
       "policy_blob_sha":POLICY_SHA,"policy_hash":POLICY_HASH,"policy_version":"C4.17",
       "candidate_created":False,"primary_mc_pass_created":0,
       "can_register_R92":False,"execution":"NONE","real_money":"NO-GO",
       "unknown_never_pass":True,
    }


def select_active_handoff(candidates):
    """Exactly one unsuperseded full-scope authority with SHA-pinned ancestry.

    A valid supersession link must point to another candidate with the
    exact immutable path AND Git blob, not just a matching ASOF or version.
    Fail closed on forks, dangling links, cross-source drift or cycles.
    """
    if not candidates:
        raise ValueError("CURRENT_EXACT_MC_HANDOFF_AUTHORITY_COUNT:0")
    index={p:(o,sha) for p,o,sha in candidates}
    if len(index)!=len(candidates):
        raise ValueError("DUPLICATE_MC_HANDOFF_PATH")
    predecessors=set()
    for path,o,sha in candidates:
        prev=o.get("supersedes_resolver_bridge_path")
        oldsha=o.get("supersedes_resolver_bridge_blob_sha")
        if prev is None and oldsha is None:
            continue
        if not isinstance(prev,str) or prev not in index or not isinstance(oldsha,str):
            raise ValueError("DANGLING_MC_HANDOFF_SUPERSESSION")
        p,actual_sha=index[prev]
        if oldsha!=actual_sha:
            raise ValueError("MC_HANDOFF_SUPERSESSION_BLOB_MISMATCH")
        if path==prev or p.get("asof_et")!=o.get("asof_et"):
            raise ValueError("MC_HANDOFF_SUPERSESSION_ASOF_OR_CYCLE")
        predecessors.add(prev)
    heads=[x for x in candidates if x[0] not in predecessors]
    if len(heads)!=1:
        raise ValueError("CURRENT_ACTIVE_MC_HANDOFF_HEAD_COUNT:"+str(len(heads)))
    # Every old candidate must be reachable from the single head.
    seen=set()
    path,_,_=heads[0]
    while path:
        if path in seen:
            raise ValueError("MC_HANDOFF_SUPERSESSION_CYCLE")
        seen.add(path)
        obj,_=index[path]
        path=obj.get("supersedes_resolver_bridge_path")
    if seen!=set(index):
        raise ValueError("MC_HANDOFF_FORK_NOT_CHAIN")
    return heads[0]

def build():
    price,price_sha=load_exact(CURRENT_PRICE)
    pol,pol_sha=load_exact("nasdaq-xray/chatgpt_compiled_policy_v3.json")
    if pol_sha!=POLICY_SHA:raise ValueError("COMPILED_POLICY_BLOB_CHANGED")
    asof=price.get("asof_et")
    if not isinstance(asof,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",asof):
        raise ValueError("PRICE_ASOF_INVALID")
    prefix="nasdaq-xray/canonical_resolver_bridge_"+asof.replace("-","")+"_c417_dv30_v"
    handoffs=[]
    for f in ROOT.glob("canonical_resolver_bridge_"+asof.replace("-","")+"_c417_dv30_v*.json"):
        rel="nasdaq-xray/"+f.name
        o,sha=load_exact(rel)
        if o.get("bridge_role")=="FULL_SCOPE_MC_HANDOFF_PROVENANCE" and o.get("source_price_blob_sha")==price_sha:
            handoffs.append((rel,o,sha))
    rel,hand,handsha=select_active_handoff(handoffs)
    witnesspath=hand.get("settlement_witness_path")
    if not isinstance(witnesspath,str) or not witnesspath.startswith("nasdaq-xray/"):
        raise ValueError("SETTLEMENT_WITNESS_PATH_INVALID")
    witness,wsha=load_exact(witnesspath)
    result=assert_same_asof(price,hand,price_sha,handsha,pol_sha,witness,wsha)
    result.update(resolver_provenance_path=rel,
                  settlement_witness_path=witnesspath,
                  settlement_witness_blob_sha=wsha)
    return result

def selftest():
    price={
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "asof_et":"2026-10-08","pass_symbols":["AAA","BBB"],
      "pass_count":2,"pass_hash":hash_lines(["AAA","BBB"]),
      "unknown_count":0,"blocked_count":1}
    hand={"execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
          "asof_et":"2026-10-08","status":"COMMITTED","bridge_role":"FULL_SCOPE_MC_HANDOFF_PROVENANCE",
          "coverage_complete":True,"classification_coverage_complete":True,"partial_data":False,
          "compiled_policy_blob_sha":POLICY_SHA,"compiled_policy_hash":POLICY_HASH,
          "compiled_policy_version":"C4.17","settlement_status":"PASS",
          "source_price_blob_sha":"a"*40,"price_unknown_count":0,
          "union_disjoint_proof":{"pass_set_exact_current_price":True},
          "current_handoff":{"price_blob_sha":"a"*40,"pass_count":2,
             "pass_hash":price["pass_hash"],"blocked_count":1,
             "blocked_subset_of_full_scope_block":True,"no_new_pass_beyond_resolver":True}}
    good=assert_same_asof(price,hand,"a"*40,"b"*40,POLICY_SHA)
    assert good["input_pass_count"]==2 and not good["can_register_R92"]
    bad=[
        ("STALE_PRICE_SHA",lambda p,h:h.update(source_price_blob_sha="c"*40)),
        ("PRICE_ASOF_MISMATCH",lambda p,h:h.update(asof_et="2026-10-07")),
        ("PRICE_SYMBOL_DUPLICATE",lambda p,h:p.update(pass_symbols=["AAA","AAA"])),
        ("PRICE_PASS_HASH_DRIFT",lambda p,h:p.update(pass_hash="f"*64)),
        ("PRICE_UNKNOWN_NONZERO",lambda p,h:p.update(unknown_count=1)),
        ("MC_HANDOFF_SETTLEMENT_UNKNOWN",lambda p,h:h.update(settlement_status="UNKNOWN")),
        ("MC_HANDOFF_PARTIAL",lambda p,h:h.update(partial_data=True)),
        ("MC_HANDOFF_BLOCKED_SUBSET_FALSE",lambda p,h:h["current_handoff"].update(blocked_subset_of_full_scope_block=False)),
        ("PASS_SET_CHANGED",lambda p,h:h["current_handoff"].update(pass_hash="0"*64)),
    ]
    import copy
    for label,alter in bad:
        p,h=copy.deepcopy(price),copy.deepcopy(hand)
        alter(p,h)
        try:assert_same_asof(p,h,"a"*40,"b"*40,POLICY_SHA)
        except AssertionError:continue
        raise AssertionError("INVALID_MC_REQUEST_ACCEPTED:"+label)
    base={"asof_et":"2026-10-08"}
    v2=("nasdaq-xray/test_v2.json",base,"1"*40)
    v3=("nasdaq-xray/test_v3.json",{
       "asof_et":"2026-10-08",
       "supersedes_resolver_bridge_path":v2[0],
       "supersedes_resolver_bridge_blob_sha":v2[2],
    },"2"*40)
    assert select_active_handoff([v2,v3])==v3
    broken=(v3[0],dict(v3[1],supersedes_resolver_bridge_blob_sha="3"*40),v3[2])
    for label,case in (
        ("DUPLICATE_HEAD",[v2,("nasdaq-xray/test_v4.json",base,"4"*40)]),
        ("MISMATCH_SHA",[v2,broken]),
        ("CYCLE",[v2,(v3[0],dict(v3[1],supersedes_resolver_bridge_path=v3[0]),v3[2])]),
    ):
        try:select_active_handoff(case)
        except ValueError:continue
        raise AssertionError("SUPERSESSION_BAD_CASE_ACCEPTED:"+label)
    print("XRAY_MC_REQUEST_REBIND_SELFTEST=PASS_1_BASELINE_9_NEGATIVE_SUPERSESSION_POSITIVE_3_NEGATIVE")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    r=build()
    if args.out:args.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_MC_REQUEST_REBIND=EVIDENCE_READY_ASOF_"+r["asof_et"])
    print("XRAY_MC_REQUEST_ONLY_NO_PRIMARY_NO_ALPHA=PASS")

if __name__=="__main__":main()
