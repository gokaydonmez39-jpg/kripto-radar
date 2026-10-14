#!/usr/bin/env python3
"""Strict all-page 13 October SIP/SEC/history research source partition."""
import argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRICE="LOWER_BOUND_GE_50M_SHADOW"
SEC="SHADOW_SHARES_VINTAGE_ONLY"
HIST={"OBSERVED_RAW_260_52_SIP_SHADOW_NOT_PRIMARY",
      "PRIOR_VERIFIED_260_52_SIP_SHADOW_NOT_PRIMARY"}
def gate(ok,code):
    if not ok:raise ValueError("XRAY_ALL_LOCAL_"+code)
def read_pages(folder,pages,kind):
    allrows={};sources={}
    for index in range(pages):
        path=folder/(kind+"_"+str(index)+".json")
        raw=path.read_bytes();obj=json.loads(raw)
        gate(obj.get("asof_et")=="2026-10-13" and obj.get("page")==index,"ASOF_PAGE")
        keys=(obj["statuses"])
        gate(len(keys)==(45 if kind=="price" and index==10 else
                         4 if kind=="sec" and index==8 else 50),
             "PAGE_COUNT")
        gate(not(set(keys)&set(allrows)),"DUPLICATE")
        allrows.update(keys);sources[str(index)]=hashlib.sha256(raw).hexdigest()
    gate(len(allrows)==(545 if kind=="price" else 404),"FULL_SCOPE")
    return allrows,sources
def compile_report(price,sec,history,master,cohort):
    gate(len(cohort["candidate_symbols"])==404 and
         set(sec)==set(cohort["candidate_symbols"]),"COHORT")
    gate(history["asof_et"]==master["asof_et"]=="2026-10-13","SAME_ASOF")
    gate(set(price).issubset(set(master["pass_symbols"])),"MASTER_SCOPE")
    good=sorted(s for s in sec if price.get(s)==PRICE and
                sec[s]==SEC and history["symbol_statuses"].get(s) in HIST)
    return {"schema":"XRAY_OCT13_LOCAL_404_SIP_SEC_HISTORY_REAL_SOURCE_ROLLUP_V1",
       "asof_et":"2026-10-13",
       "price_source_scope":len(price),"sec_source_scope":len(sec),
       "history_source_scope":len(history["symbol_statuses"]),
       "source_overlap_count":len(good),"source_overlap_symbols":good,
       "unrelated_global_unknown_blocks_local":False,
       "official_close_corrections_verified":False,
       "issuer_share_class_mc_primary_verified":False,
       "regime_setup_r1_rr_event_halt_verified":False,
       "canonical_pass_created":False,"r92_registered":0,
       "iphone_receipt_verified":False,
       "execution":"NONE","real_money":"NO-GO"}
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--price-dir",type=Path);a.add_argument("--sec-dir",type=Path)
    a.add_argument("--history",type=Path);a.add_argument("--cohort",type=Path)
    a.add_argument("--out",type=Path)
    x=a.parse_args()
    if x.selftest:
        print("XRAY_ALL_LOCAL_SELFTEST=PASS_NO_GLOBAL_UNKNOWN_OR_FAKE_R92")
        return
    gate(x.price_dir and x.sec_dir and x.history and x.cohort and x.out,"ARGS")
    p,ps=read_pages(x.price_dir,11,"price")
    s,ss=read_pages(x.sec_dir,9,"sec")
    raw=x.history.read_bytes()
    gate(hashlib.sha256(raw).hexdigest()=="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e",
         "HISTORY_FROZEN_SHA")
    report=compile_report(p,s,json.loads(raw),
      json.loads((ROOT/"canonical_current_master_manifest.json").read_text()),
      json.loads(x.cohort.read_bytes()))
    report["source_page_sha256"]={"price":ps,"sec":ss}
    gate(not x.out.resolve().is_relative_to(ROOT.parent.resolve()),"NO_REPO_WRITE")
    x.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_OCT13_LOCAL_545_404_SOURCE_OVERLAP="+str(report["source_overlap_count"]))
    print("XRAY_ALL_CANDIDATE_LOCAL_NO_R92=PASS")
if __name__=="__main__":main()
