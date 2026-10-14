#!/usr/bin/env python3
"""Read-only full Oct13 277 Stage1 pool -> A/B/D -> R1/RR source rollup."""
import argparse,collections,hashlib,json
from pathlib import Path
STAGE1_SCHEMA="XRAY_OCT13_STAGE1_277_FULL_RESEARCH_SOURCE_ROLLUP_V1"
FIRST_DEEP_SCHEMA="XRAY_OCT13_7_TRUE_SIP_DEEP_ABD_R1RR_SHADOW_V1"
PAGE_DEEP_SCHEMA="XRAY_20261013_LOCAL_277_DEEP_ABD_R1RR_PAGE_SHADOW_V1"
ASOF="2026-10-13"
def must(cond,msg):
    if not cond:raise ValueError("XRAY_DEEP_FULL277_"+msg)
def h(raw):return hashlib.sha256(raw).hexdigest()
def compile(st,first,files):
    must(st.get("schema")==STAGE1_SCHEMA and st.get("asof_et")==ASOF
         and st.get("total_source_scope")==277 and st.get("registered_r92")==0,
         "STAGE1_EXACT_277")
    pools=set(st["stage1_pool_symbols"])
    must(len(pools)==st["stage1_pool_count"]
         and all(st["stage1_actual_symbol_statuses"][s]=="STAGE1_RESEARCH_POOL_ONLY"
                 for s in pools),"STAGE1_POOL_BIND")
    first_raw=first.read_bytes()
    first_data=json.loads(first_raw)
    must(first_data["schema"]==FIRST_DEEP_SCHEMA and first_data["asof_et"]==ASOF
         and first_data["source_stage1_json_sha256"]==st["stage1_page_sha256"]["0"]
         and set(first_data["symbols"])==set(first_data["rows"])
         and set(first_data["symbols"])==pools.intersection(
             set(list(st["stage1_actual_symbol_statuses"])[:28])),
         "FIRST7_SOURCE")
    rows=dict(first_data["rows"])
    pins={"0":h(first_raw)}
    for i in range(1,10):
        buf=(files/("deep_"+str(i)+".json")).read_bytes()
        d=json.loads(buf)
        must(d.get("schema")==PAGE_DEEP_SCHEMA and d.get("asof_et")==ASOF
             and d.get("page")==i and
             d.get("stage1_page_sha256")==st["stage1_page_sha256"][str(i)]
             and d.get("source_277_json_sha256")==st["source_277_sha256"]
             and d.get("r92_registered")==0
             and d.get("execution")=="NONE" and d.get("real_money")=="NO-GO",
             "PAGE_PROVENANCE")
        pset=set(d["stage1_real_pool_symbols"])
        must(len(pset)==d["stage1_pool_count"]
             and set(d["evaluations"])==pset and
             sum(d["counts"].values())==len(pset)
             and not (set(rows)&pset),"PAGE_POOL_DISJOINT")
        rows.update(d["evaluations"]);pins[str(i)]=h(buf)
    must(set(rows)==pools,"ALL_STAGE1_POOLS_DEEP_ATTEMPTED")
    triggers={}
    r1rr={}
    for sym,row in rows.items():
        for family,f in (row.get("families") or {}).items():
            if f.get("actual_deep_trigger_confirmed") is True:
                triggers[sym+"|"+family]=bool(f.get("final_evaluated"))
                r1rr[sym+"|"+family]={
                    "frozen_R1_RR_evaluated":bool(f.get("final_evaluated")),
                    "risk_geometry_pass":f.get("risk_geometry_pass"),
                    "rr_basic_and_severe_pass":f.get("rr_basic_and_severe_pass"),
                    "technical_result":f.get("technical_result")}
    return {"schema":"XRAY_OCT13_277_REAL_STAGE1_DEEP_R1RR_COMPLETE_SHADOW_V1",
      "asof_et":ASOF,"source_277_stage1_count":277,
      "stage1_pool_count":len(pools),
      "source_deep_evaluated_symbol_count":len(rows),
      "deep_results":dict(sorted(collections.Counter(
           r.get("status","UNKNOWN") for r in rows.values()).items())),
      "actual_confirmed_recent_family_trigger_count":len(triggers),
      "actual_trigger_symbol_count":len({key.split("|")[0] for key in triggers}),
      "trigger_families_rr_evaluated":sum(triggers.values()),
      "risk_rr_diagnostics":r1rr,
      "stage1_page_sha256":st["stage1_page_sha256"],
      "deep_page_sha256":pins,
      "provenance_exact":True,
      "unrelated_global_unknown_not_veto":True,
      "official_nasdaq_halt_event_legal_asof_not_verified":True,
      "sec_issuer_class_mc_primary_not_verified":True,
      "primary_price_corrections_not_verified":True,
      "registered_r92":0,"iphone_delivery_receipt_verified":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--stage1",type=Path)
    a.add_argument("--first",type=Path)
    a.add_argument("--pages-dir",type=Path)
    a.add_argument("--out",type=Path)
    x=a.parse_args()
    if x.selftest:
        must(len(range(10))==10 and ASOF!="2026-10-12","ADVERSARIAL_DATE")
        print("XRAY_DEEP277_ROLLUP_SELFTEST=PASS_REQUIRES_ALL_STAGE1_POOL_SET")
        return
    must(x.stage1 and x.first and x.pages_dir and x.out,"ARGS")
    must(not x.out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),
         "NO_VENDOR_SOURCE_PUBLIC")
    src=json.loads(x.stage1.read_bytes())
    result=compile(src,x.first,x.pages_dir)
    x.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_DEEP277_ALL_POOL_COUNT="+str(result["stage1_pool_count"]))
    print("XRAY_DEEP277_ACTUAL_RECENT_FAMILY_TRIGGERS="+str(result["actual_confirmed_recent_family_trigger_count"]))
    print("XRAY_DEEP277_FROZEN_R1RR_EVALUATED="+str(result["trigger_families_rr_evaluated"]))
    print("XRAY_DEEP277_NO_FALSE_R92_OR_IPHONE=PASS")
if __name__=="__main__":main()
