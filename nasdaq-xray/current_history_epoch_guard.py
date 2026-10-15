#!/usr/bin/env python3
"""Separate current 260/52 evidence from a stale global history diagnostic.

This is a read-only provenance check. It cannot create, infer, or release any
history PASS, MC PASS, R92 signal, or vendor right. It doesn't fetch market data.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
PATHS={
    "price":"nasdaq-xray/canonical_current_price_dv30.json",
    "history":"nasdaq-xray/canonical_current_history.json",
    "root":"nasdaq-xray/orchestrator_state.json",
    "master":"nasdaq-xray/canonical_current_master_manifest.json",
}
SCHEMA="XRAY_HISTORY_CURRENT_EPOCH_SCOPE_TRUTH_V1"

def hash_lines(values:list[str])->str:
    return hashlib.sha256("\n".join(values).encode()).hexdigest()

def parse(path:str)->dict:
    return json.loads((REPO/path).read_text(encoding="utf-8"))

def blob(path:str)->str:
    return subprocess.check_output(
        ["git","hash-object",str(REPO/path)],cwd=REPO,text=True).strip()

def need(ok:bool,code:str)->None:
    if not ok:
        raise ValueError("XRAY_CURRENT_HISTORY_EPOCH_"+code)


def decide(price:dict,history:dict,root:dict,master:dict,price_blob_sha:str|None=None)->dict:
    need(all(type(x) is dict for x in (price,history,root,master)),
         "NONOBJECT_DOCUMENT")
    ps=price.get("pass_symbols")
    need(type(ps) is list and ps==sorted(set(ps)),"PRICE_PASS_PARTITION_INVALID")
    need(hash_lines(ps)==price.get("pass_hash"),"PRICE_PASS_HASH_DRIFT")
    need(type(price.get("pass_count")) is int and
         len(ps)==price["pass_count"],"PRICE_PASS_COUNT_DRIFT")
    need(type(price.get("unknown_count")) is int and
         price["unknown_count"]>=0,"PRICE_UNKNOWN_COUNT_INVALID")
    asof=price.get("asof_et")
    need(isinstance(asof,str) and len(asof)==10,"PRICE_ASOF_INVALID")
    need(master.get("asof_et")==asof and root.get("asof_et")==asof,
         "MASTER_OR_ROOT_ASOF_MISMATCH")
    need(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
             and x.get("unknown_never_pass") is not False
             for x in (price,history,root,master)),
         "RESEARCH_SAFETY_POLICY")
    mps=master.get("pass_symbols")
    need(type(mps) is list and len(mps)==len(set(mps))
         and set(ps)<=set(mps),"PRICE_SYMBOL_OUTSIDE_MASTER")
    hs=history.get("pass_symbols")
    need(type(hs) is list and hs==sorted(set(hs)),
         "HISTORY_PASS_PARTITION_INVALID")
    h_asof=history.get("asof_et")
    # A zero-PASS current PRICE is a real, expected fail-closed state.
    # Reporting this as NO SOURCE SCOPE avoids a recurring workflow crash;
    # it must NEVER become vacuous HISTORY_PASS or a 260/52 claim.
    if not ps:
        return {
          "schema":SCHEMA,
          "status":"HISTORY_PRICE_ZERO_PASS_NO_SOURCE_SCOPE",
          "asof_et":asof,"source_price_pass_count":0,
          "source_price_unknown_count":price["unknown_count"],
          "history_asof_et":h_asof,
          "history_input_count":history.get("input_count"),
          "current_history_authority_proven":False,
          "scope_claim_structurally_consistent":False,
          "source_entitlement_independently_verified":False,
          "actual_260_52_ohlcv_independently_verified":False,
          "history_input_set_equals_price_pass":False,
          "history_source_price_blob_exact":False,
          "history_output_pass_equals_price_pass":False,
          "history_input_count_equals_current_price":False,
          "historical_root_unknown_count":root.get("unknown_count"),
          "historical_root_unknown_is_current_514_history_measurement":False,
          "required_history_scope":"CURRENT_EXACT_PRICE_PASS_WITH_260_COMPLETED_DAILY_AND_52_COMPLETED_WEEKS",
          "raw_ohlcv_present_in_report":False,"r92_eligible":False,
          "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
        }
    need(price["unknown_count"]==0,"PRICE_UNKNOWN")
    current_asof=h_asof==asof
    exact_hist_count=(history.get("input_count")==len(ps))
    exact_hist_scope=hs==ps
    # HISTORY output contains only survivors. Its pass set is NOT its input set.
    # Positive scope witness requires an explicit entire input set and pinned
    # input PRICE blob, followed by complete PASS/FAIL/UNKNOWN result partition.
    source_inputs=history.get("input_symbols")
    input_set_exact=(isinstance(source_inputs,list)
         and source_inputs==ps and len(source_inputs)==history.get("input_count"))
    bound_price_sha=(isinstance(price_blob_sha,str)
         and len(price_blob_sha)==40
         and history.get("source_price_blob_sha")==price_blob_sha)
    results=history.get("results")
    completed=(isinstance(results,dict) and set(results)==set(ps)
         and all(isinstance(v,dict) and v.get("status") in
                 {"PASS_HISTORY","FAIL_HISTORY","UNKNOWN_HISTORY"} for v in results.values())
         and sum(v.get("status")=="PASS_HISTORY" for v in results.values())==len(hs)
         and {k for k,v in results.items() if v.get("status")=="PASS_HISTORY"}==set(hs))
    actual_unknown=sum(v.get("status")=="UNKNOWN_HISTORY" for v in results.values()) if isinstance(results,dict) else -1
    # A source-file's asserted '260/52 proof exact' flag is NOT evidence of
    # licensed OHLCV, price integrity or point-in-time corporate-action checks.
    # This guard sees only self-reported canonical JSON and cannot inspect an
    # independently verified provider grant or actual exchange-session bars.
    # Keep structural consistency observable but never mint source authority.
    scope_claim_structurally_consistent=(current_asof and exact_hist_count and input_set_exact
         and bound_price_sha and completed and actual_unknown==0
         and history.get("unknown_count")==0
         and history.get("history_260_52_proof_exact") is True)
    history_authoritative=False
    status=("HISTORY_CURRENT_SCOPE_CLAIM_ONLY_SOURCE_UNVERIFIED"
            if scope_claim_structurally_consistent else "HISTORY_CURRENT_SCOPE_NOT_PROVEN")
    if not current_asof:
        status="HISTORY_STALE_ASOF"
    elif not exact_hist_count or not input_set_exact:
        status="HISTORY_CURRENT_INPUT_SET_UNVERIFIED"
    elif not bound_price_sha:
        status="HISTORY_CURRENT_SOURCE_PRICE_BLOB_UNVERIFIED"
    elif not scope_claim_structurally_consistent:
        status="HISTORY_CURRENT_260_52_OR_RESULT_PROOF_UNVERIFIED"
    return {
      "schema":SCHEMA,"status":status,"asof_et":asof,
      "source_price_pass_count":len(ps),
      "history_asof_et":h_asof,
      "history_input_count":history.get("input_count"),
      "current_history_authority_proven":history_authoritative,
      "scope_claim_structurally_consistent":scope_claim_structurally_consistent,
      "source_entitlement_independently_verified":False,
      "actual_260_52_ohlcv_independently_verified":False,
      "history_input_set_equals_price_pass":input_set_exact,
      "history_source_price_blob_exact":bound_price_sha,
      "history_output_pass_equals_price_pass":exact_hist_scope,
      "history_input_count_equals_current_price":exact_hist_count,
      "historical_root_unknown_count":root.get("unknown_count"),
      "historical_root_unknown_is_current_514_history_measurement":False,
      "required_history_scope":"CURRENT_EXACT_PRICE_PASS_WITH_260_COMPLETED_DAILY_AND_52_COMPLETED_WEEKS",
      "raw_ohlcv_present_in_report":False,"r92_eligible":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }

def selftest():
    symbols=["AAA","BBB"]
    p={"asof_et":"2026-10-08","pass_symbols":symbols,
       "pass_count":2,"pass_hash":hash_lines(symbols),
       "unknown_count":0,"execution":"NONE","real_money":"NO-GO"}
    m={"asof_et":p["asof_et"],"pass_symbols":symbols,"execution":"NONE","real_money":"NO-GO"}
    r={"asof_et":p["asof_et"],"unknown_count":231,"execution":"NONE","real_money":"NO-GO"}
    h={"asof_et":"2026-10-07","pass_symbols":symbols,"input_count":2,
       "execution":"NONE","real_money":"NO-GO"}
    need(decide(p,h,r,m)["status"]=="HISTORY_STALE_ASOF",
         "BASELINE_STALE")
    need(decide(p,h,r,m)["historical_root_unknown_is_current_514_history_measurement"] is False,
         "ROOT_UNPROVEN")
    # Current production zero-PASS PRICE is valid NO-GO, not an exception.
    empty=copy.deepcopy(p)
    empty.update(pass_symbols=[],pass_count=0,pass_hash=hash_lines([]),
                 unknown_count=513)
    report=decide(empty,h,r,m,price_blob_sha="a"*40)
    need(report["status"]=="HISTORY_PRICE_ZERO_PASS_NO_SOURCE_SCOPE"
         and report["source_price_pass_count"]==0
         and report["source_price_unknown_count"]==513
         and report["current_history_authority_proven"] is False
         and report["scope_claim_structurally_consistent"] is False
         and report["r92_eligible"] is False,
         "ZERO_PRICE_PASS_FALSE_AUTHORITY")
    tampered=copy.deepcopy(empty)
    tampered["pass_hash"]="0"*64
    try:decide(tampered,h,r,m)
    except ValueError:pass
    else:raise AssertionError("ZERO_PASS_HASH_BYPASS")
    bad=[
       ("PRICE_HASH_DRIFT",lambda a,b,c,d:a.update(pass_hash="0"*64)),
       ("PRICE_DUPLICATE",lambda a,b,c,d:a.update(pass_symbols=["AAA","AAA"])),
       ("MASTER_ASOF_DRIFT",lambda a,b,c,d:d.update(asof_et="2026-10-07")),
       ("ROOT_ASOF_DRIFT",lambda a,b,c,d:c.update(asof_et="2026-10-07")),
       ("OUTSIDE_MASTER",lambda a,b,c,d:d.update(pass_symbols=["AAA"])),
    ]
    for name,alter in bad:
        a,b,c,d=copy.deepcopy(p),copy.deepcopy(h),copy.deepcopy(r),copy.deepcopy(m)
        alter(a,b,c,d)
        try:decide(a,b,c,d)
        except ValueError:continue
        raise AssertionError("ACCEPTED_BAD_HISTORY_SCOPE:"+name)
    h["asof_et"]=p["asof_et"]
    h["input_count"]=1
    need(decide(p,h,r,m)["status"]=="HISTORY_CURRENT_INPUT_SET_UNVERIFIED",
         "INCOMPLETE_INPUT_SET_UNVERIFIED")
    h["input_count"]=2
    h["pass_symbols"]=["AAA"]
    need(decide(p,h,r,m)["status"]=="HISTORY_CURRENT_INPUT_SET_UNVERIFIED",
         "INCOMPLETE_INPUT_SET_UNVERIFIED")
    # Positive scope proof is attainable only with explicit exact source,
    # complete per-symbol outcome partition and verified 260/52 witness.
    h.update(input_symbols=["AAA","BBB"],source_price_blob_sha="a"*40,
             unknown_count=0,history_260_52_proof_exact=True,
             results={"AAA":{"status":"PASS_HISTORY"},"BBB":{"status":"FAIL_HISTORY"}})
    # RED regression: claimed 260/52 flags without a lawful source grant
    # cannot make a current HISTORY result authoritative.
    need(decide(p,h,r,m,price_blob_sha="a"*40)["current_history_authority_proven"] is False,
         "UNLICENSED_HISTORY_FALSE_POSITIVE")
    good=decide(p,h,r,m,price_blob_sha="a"*40)
    need(good["status"]=="HISTORY_CURRENT_SCOPE_CLAIM_ONLY_SOURCE_UNVERIFIED"
         and good["scope_claim_structurally_consistent"] is True
         and good["current_history_authority_proven"] is False,
         "STRUCTURAL_ONLY_NOT_MARKET_AUTHORITY")
    # Even self-asserted source rights cannot become independent verification.
    claimed=copy.deepcopy(h)
    claimed["source_entitlement_proven"]=True
    claimed["source_grant_sha256"]="b"*64
    asserted=decide(p,claimed,r,m,price_blob_sha="a"*40)
    need(asserted["scope_claim_structurally_consistent"] is True
         and asserted["current_history_authority_proven"] is False
         and asserted["source_entitlement_independently_verified"] is False,
         "SELFASSERTED_VENDOR_LICENSE_MUST_NOT_AUTHORIZE_HISTORY")
    h["history_260_52_proof_exact"]=False
    need(decide(p,h,r,m,price_blob_sha="a"*40)["status"]==
         "HISTORY_CURRENT_260_52_OR_RESULT_PROOF_UNVERIFIED",
         "FALSE_260_52_SOURCE_PROOF")
    print("XRAY_HISTORY_EPOCH_SCOPE_SELFTEST=PASS_ZERO_PRICE_6_NEGATIVES_2_UNLICENSED_NO_SOURCE_AUTHORITY_OPTIMIZED_SAFE")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:selftest();return
    data={key:parse(path) for key,path in PATHS.items()}
    out=decide(**data,price_blob_sha=blob(PATHS["price"]))
    out["canonical_price_blob_sha"]=blob(PATHS["price"])
    out["history_blob_sha"]=blob(PATHS["history"])
    if args.out:args.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("XRAY_HISTORY_EPOCH_SCOPE="+out["status"])
    print("XRAY_HISTORY_CURRENT_INPUT_COUNT="+str(out["source_price_pass_count"]))
    print("XRAY_HISTORY_LEGACY_231_NOT_CURRENT_PROOF=PASS")

if __name__=="__main__":main()
