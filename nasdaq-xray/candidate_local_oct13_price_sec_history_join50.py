#!/usr/bin/env python3
"""Exact Oct13 evidence intersections. No vendor bar or share totals persisted."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
PR="LOWER_BOUND_GE_50M_SHADOW"
SH="SHADOW_SHARES_VINTAGE_ONLY"
HIST={"OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY",
      "PRIOR_VERIFIED_260_52_SIP_SHADOW_NOT_PRIMARY"}
def need(ok,msg):
    if not ok:raise ValueError("XRAY_LOCAL_50_JOIN_"+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def inspect(price,sec,history,master,hashes):
    need(price.get("schema")=="XRAY_OCT13_ALPACA_50_SINGLE_SYMBOL_SIP_RTH_BOUNDS_V1"
         and sec.get("schema")=="XRAY_CANDIDATE_LOCAL_SEC50_SOURCE_VINTAGES_V1",
         "SCHEMA")
    need(price.get("asof_et")==sec.get("asof_et")==
         history.get("asof_et")==master.get("asof_et")==ASOF,"EXACT_ASOF")
    need(price.get("page")==sec.get("page")==0,"PAGE_SOURCE_0")
    need(price.get("target_count")==sec.get("requested_count")==50,"50_EACH")
    need(len(price.get("statuses",{}))==len(sec.get("statuses",{}))==50,
         "50_COMPLETED")
    need(price.get("price_primary_created") is False and
         sec.get("primary_mc_approved")==0 and
         price.get("execution")==sec.get("execution")=="NONE",
         "PRIMARY_NEVER_FROM_SHADOW")
    p={k for k,v in price["statuses"].items() if v==PR}
    m={k for k,v in sec["statuses"].items() if v==SH}
    h={k for k,v in history["symbol_statuses"].items() if v in HIST}
    qualified=sorted(p&m&h&set(master["pass_symbols"]))
    # A direct 13 October price + 13 October history + SEC vintage is still
    # not an official C4.17 MC or a verified price close adjustment chain.
    return {"schema":"XRAY_20261013_CANDIDATE_LOCAL_50_PIT_SOURCE_INTERSECTION_V1",
      "asof_et":ASOF,
      "price_scope_count":50,
      "price_rth_lower_bound_positive":len(p),
      "sec_pit_share_vintage_available":len(m),
      "source_local_same_asof_intersection_count":len(qualified),
      "source_local_same_asof_intersection_symbols":qualified,
      "source_artifact_sha256":hashes,
      "other_symbols_global_unknown_do_not_veto":True,
      "official_close_correction_chain_proven":False,
      "sec_issuer_class_pit_market_cap_over_2b_proven":False,
      "setup_stage1_regime_r1_rr_asof_proven":False,
      "nasdaq_halt_and_sec_legal_event_asof_proven":False,
      "candidate_local_release_ready":False,
      "r92_registered":0,
      "real_iphone_device_receipt_verified":False,
      "canonical_files_mutated":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
def selftest():
    p={"schema":"XRAY_OCT13_ALPACA_50_SINGLE_SYMBOL_SIP_RTH_BOUNDS_V1",
       "asof_et":ASOF,"page":0,"target_count":50,
       "statuses":{f"T{i:02d}":PR for i in range(50)},
       "price_primary_created":False,"execution":"NONE"}
    s={"schema":"XRAY_CANDIDATE_LOCAL_SEC50_SOURCE_VINTAGES_V1",
       "asof_et":ASOF,"page":0,"requested_count":50,
       "statuses":{f"T{i:02d}":SH for i in range(50)},
       "primary_mc_approved":0,"execution":"NONE"}
    h={"asof_et":ASOF,"symbol_statuses":{f"T{i:02d}":next(iter(HIST)) for i in range(50)}}
    m={"asof_et":ASOF,"pass_symbols":[f"T{i:02d}" for i in range(50)],
       "unknown_count":100,"unknown_symbols":["OTHER"]}
    r=inspect(p,s,h,m,{})
    need(r["source_local_same_asof_intersection_count"]==50 and
         not r["candidate_local_release_ready"] and r["r92_registered"]==0,
         "GLOBAL_UNKNOWN_IGNORED_BUT_RELEASE_FALSE")
    p["asof_et"]="2026-10-12"
    try:inspect(p,s,h,m,{})
    except ValueError:pass
    else:raise AssertionError("CROSS_ASOF_ACCEPTED")
    print("XRAY_LOCAL_50_SAME_ASOF_JOIN_SELFTEST=PASS_GLOBAL_UNKNOWN_NO_VETO_OLD_DATE_VETO")
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--price",type=Path);a.add_argument("--sec",type=Path)
    a.add_argument("--history",type=Path);a.add_argument("--out",type=Path)
    x=a.parse_args()
    if x.selftest:selftest();return
    need(x.price and x.sec and x.history and x.out
         and not x.out.resolve().is_relative_to(ROOT.parent.resolve()),"ARGS")
    b=[z.read_bytes() for z in (x.price,x.sec,x.history)]
    expected=("1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e")
    need(sha(b[2])==expected,"FROZEN_13OCT_HISTORY_SHA")
    report=inspect(*(json.loads(a) for a in b),
        json.loads((ROOT/"canonical_current_master_manifest.json").read_text()),
        {"price_oct13":sha(b[0]),"sec_oct13":sha(b[1]),"history_oct13":sha(b[2])})
    x.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_LOCAL_50_OCT13_SAME_ASOF_SOURCE_INTERSECTION="+str(report["source_local_same_asof_intersection_count"]))
    print("XRAY_LOCAL_50_PRIMARY_R92_ZERO=PASS")
if __name__=="__main__":main()
