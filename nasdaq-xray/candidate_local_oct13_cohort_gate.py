#!/usr/bin/env python3
"""Candidate-local C4.17 read-only gate. Global UNKNOWN never vetoes another ticker."""
from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
POS_PRICE={"LOWER_BOUND_GE_50M_SHADOW","PRIOR_VERIFIED_LOWER_BOUND_GE_50M_SHADOW"}
POS_HIST={"OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY","PRIOR_VERIFIED_260_52_SIP_SHADOW_NOT_PRIMARY"}
STAGES=("master","price","mc","history","legal","event","final","halt","risk")
REQUIRED=("source_asof","master_identity_pit","price_rth_dv30_primary",
          "mc_sec_class_pit_primary","history_260_52_primary",
          "legal_sec_filings_verified","event_8k_10k_10q_verified",
          "nasdaq_official_halt_clear","stage1_regime_setup_rr_pass",
          "source_sha_chain_valid")
def need(v,msg):
    if not v:raise ValueError("XRAY_CANDIDATE_LOCAL_"+msg)
def digest(data):
    return hashlib.sha256(data).hexdigest()
def evaluate_candidate(symbol,proof,master):
    """No requirement for master.unknown_count=0 or price.unknown_count=0."""
    need(isinstance(symbol,str) and symbol and isinstance(proof,dict),"INPUT")
    need(master.get("asof_et")==ASOF and
         symbol in master.get("pass_symbols",[]),"LOCAL_MASTER_PASS")
    checks={key:(proof.get(key)==ASOF if key=="source_asof" else
                 proof.get(key) is True) for key in REQUIRED}
    # Exact source equality required; no unknown of another ticker participates.
    ready=all(checks.values())
    return {"symbol":symbol,"asof_et":ASOF,"checks":checks,
            "candidate_local_primary_ready":ready,
            "status":"LOCAL_PRIMARY_CHAIN_PASS" if ready else "LOCAL_SOURCE_GATES_OPEN",
            "r92_registerable":ready,
            "real_money":"NO-GO","execution":"NONE"}
def source_scope(price,history,master):
    need(price.get("asof_et")=="2026-10-12" and
         history.get("asof_et")==ASOF,"CROSS_ASOF_SOURCE_LABELS")
    p=price["symbol_statuses"];h=history["symbol_statuses"]
    need(len(p)==540 and len(h)==3185 and set(p).issubset(set(h)),
         "FROZEN_PARTITIONS")
    eligible=sorted(set(master["pass_symbols"]).intersection(
        s for s in p if p[s] in POS_PRICE and h[s] in POS_HIST))
    known=sorted(s for s in p if p[s] in POS_PRICE and h[s] in POS_HIST)
    need(len(known)==404 and len(eligible)==404,"KNOWN_404_OR_IDENTITY_DRIFT")
    return known
def chunks(items,size):
    need(1<=size<=50,"BOUNDED_CHUNK")
    return [items[i:i+size] for i in range(0,len(items),size)]
def inspect(price,history,master,current_price,source_hashes):
    cohort=source_scope(price,history,master)
    need(current_price.get("asof_et")==ASOF and
         current_price.get("pass_count")==0,"CURRENT_PRICE_NOT_FALSE_PASS")
    pending=sorted(set(current_price.get("unknown_symbols",[])))
    pending_master=sorted(set(master.get("unknown_symbols",[])))
    need(len(pending)==545 and len(pending_master)==10,
         "PENDING_SCOPE_DRIFT")
    blockset=set(pending_master)
    candidates={}
    for s in cohort:
        need(s not in blockset,"UNKNOWN_IDENTITY_IN_COHORT")
        # Frozen 12 Oct PRICE cannot support 13 Oct PRIMARY.
        proof={"source_asof":"2026-10-12"}
        candidates[s]=evaluate_candidate(s,proof,master)
    # Future candidate-local evidence may be applied per symbol without
    # requiring another symbol's identity or price to complete.
    return {
        "schema":"XRAY_CANDIDATE_LOCAL_404_20261013_SOURCE_GATED_V1",
        "asof_et":ASOF,"cohort_size":len(cohort),
        "candidate_symbols":cohort,"candidate_checks":candidates,
        "candidate_local_primary_pass_count":sum(
          x["candidate_local_primary_ready"] for x in candidates.values()),
        "cross_asof_shadow_only":True,
        "price_source_asof_et":"2026-10-12",
        "history_source_asof_et":ASOF,
        "global_unknown_not_a_candidate_local_veto":True,
        "primary_required_for_each_symbol":list(REQUIRED),
        "source_sha256":source_hashes,
        "price_unknown_chunks_50":chunks(pending,50),
        "master_unknown_chunks_50":chunks(pending_master,50),
        "price_unknown_count":len(pending),
        "master_unknown_count":len(pending_master),
        "nonblocking_recovery_queue_only":True,
        "canonical_mutated":False,
        "r92_registered":0,"device_receipt_attested":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
def selftest():
    master={"asof_et":ASOF,"pass_symbols":["AAPL"],
            "unknown_count":999,"unknown_symbols":["OTHER"]}
    full={"source_asof":ASOF}
    full.update({k:True for k in REQUIRED if k!="source_asof"})
    got=evaluate_candidate("AAPL",full,master)
    need(got["r92_registerable"] and got["candidate_local_primary_ready"],
         "UNRELATED_GLOBAL_UNKNOWN_FALSE_VETO")
    for k in REQUIRED:
        bad=dict(full);bad[k]="2026-10-12" if k=="source_asof" else False
        need(not evaluate_candidate("AAPL",bad,master)["r92_registerable"],
             "SINGLE_GATE_BYPASS_"+k)
    for bad in ("OTHER","MISSING"):
        try:evaluate_candidate(bad,full,master)
        except ValueError:pass
        else:raise AssertionError("UNKNOWN_MASTER_PROMOTED")
    need([len(c) for c in chunks(list(range(101)),50)]==[50,50,1],
         "CHUNK_LOSS")
    print("XRAY_CANDIDATE_LOCAL_SELFTEST=PASS_10_NEGATIVES_GLOBAL_UNKNOWN_NO_VETO")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--price-artifact",type=Path)
    ap.add_argument("--history-artifact",type=Path)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if a.selftest:selftest();return
    need(a.price_artifact and a.history_artifact and a.out,"CLI")
    need(not a.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "EPHEMERAL_OUTPUT")
    rawp=a.price_artifact.read_bytes();rawh=a.history_artifact.read_bytes()
    need(digest(rawp)=="add16b6188d284de90f9ac9dff668afcc51ebf94edfaa55303db6b9c16b0ac58",
         "PRICE_IMMUTABLE_SHA")
    need(digest(rawh)=="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e",
         "HISTORY_IMMUTABLE_SHA")
    report=inspect(json.loads(rawp),json.loads(rawh),
        json.loads((ROOT/"canonical_current_master_manifest.json").read_text()),
        json.loads((ROOT/"canonical_current_price_dv30.json").read_text()),
        {"price_oct12":digest(rawp),"history_oct13":digest(rawh)})
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_CANDIDATE_LOCAL_COHORT="+str(report["cohort_size"]))
    print("XRAY_CANDIDATE_LOCAL_R92="+str(report["r92_registered"]))
    print("XRAY_CANDIDATE_LOCAL_PRICE_CHUNKS="+str(len(report["price_unknown_chunks_50"])))
    print("XRAY_CANDIDATE_LOCAL_404_CROSS_ASOF_BLOCK_ONLY_NOT_GLOBAL=PASS")
if __name__=="__main__":main()
