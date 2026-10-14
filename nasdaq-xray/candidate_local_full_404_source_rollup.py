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
def verify_page(obj, kind, index, expected, master_sha=None, price_sha=None,
                cohort_sha=None):
    """Adversarial exact-set/ASOF/source check; counts alone never certify."""
    gate(type(obj) is dict and type(index) is int,"PAGE_TYPE")
    gate(obj.get("asof_et")=="2026-10-13" and obj.get("page")==index,"ASOF_PAGE")
    gate(obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO",
         "SAFETY")
    gate(type(expected) is list and len(expected)>0 and len(expected)<=50
         and len(set(expected))==len(expected),"EXPECTED_PAGE_SET")
    actual=obj.get("statuses")
    gate(type(actual) is dict and set(actual)==set(expected),"EXACT_PAGE_SYMBOLS")
    if kind=="price":
        gate(obj.get("schema")=="XRAY_OCT13_ALPACA_50_SINGLE_SYMBOL_SIP_RTH_BOUNDS_V1",
             "PRICE_SCHEMA")
        gate(obj.get("target_symbols")==expected
             and obj.get("target_count")==len(expected),"PRICE_ORDER_AND_COUNT")
        gate(obj.get("no_vendor_raw_ohlcv_exported") is True
             and obj.get("single_symbol_isolation") is True
             and obj.get("price_primary_created") is False
             and obj.get("mc_primary_created") is False
             and obj.get("r92_created") is False
             and obj.get("canonical_files_mutated") is False,
             "PRICE_SHADOW_NEVER_PRIMARY")
        if master_sha is not None and price_sha is not None:
            gate(obj.get("master_source_git_blob_sha")==master_sha
                 and obj.get("price_source_git_blob_sha")==price_sha,
                 "PRICE_SOURCE_BLOBS")
        gate(obj.get("request_count",0)<=160,"PRICE_BOUNDED_CALLS")
    elif kind=="sec":
        gate(obj.get("schema")=="XRAY_CANDIDATE_LOCAL_SEC50_SOURCE_VINTAGES_V1",
             "SEC_SCHEMA")
        gate(obj.get("symbols_requested")==expected
             and obj.get("requested_count")==len(expected),"SEC_ORDER_AND_COUNT")
        gate(obj.get("primary_price_verified") is False
             and obj.get("primary_mc_approved")==0
             and obj.get("r92_registered")==0
             and obj.get("canonical_modified") is False
             and obj.get("global_unknown_veto") is False,
             "SEC_SHADOW_NEVER_PRIMARY")
        if cohort_sha is not None:
            gate(obj.get("source_cohort_sha256")==cohort_sha,"SEC_COHORT_SHA")
        gate(obj.get("api_calls",0)<=101,"SEC_BOUNDED_CALLS")
    else:
        raise ValueError("XRAY_ALL_LOCAL_ROLE")
    gate(set(actual.values()).issubset(
        {"LOWER_BOUND_GE_50M_SHADOW","AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
         "UPPER_BOUND_LT_50M_SHADOW","UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW",
         "UNKNOWN_NOT_ATTEMPTED","UNKNOWN_SIP_SOURCE_OR_INTEGRITY"}
        | {"UNKNOWN_SIP_HTTP_"+str(code) for code in (400,401,403,404,429,500,502,503)}
        if kind=="price" else
        {"SHADOW_SHARES_VINTAGE_ONLY","UNKNOWN","UNKNOWN_EXACT_CIK_ROUTE",
         "UNKNOWN_SEC_TRANSPORT","UNKNOWN_UNATTEMPTED_SEC_STOP",
         "UNKNOWN_NOT_ATTEMPTED","UNKNOWN_NO_SEC_INDEX"}),
        "UNKNOWN_CLASSIFICATION")
    return True

def read_pages(folder,pages,kind,expected,master_sha=None,price_sha=None,
               cohort_sha=None):
    gate(type(expected) is list and len(set(expected))==len(expected),
         "FULL_EXPECTED_SET")
    gate(len(expected)==(545 if kind=="price" else 404),"EXPECTED_SCOPE")
    allrows={};sources={}
    for index in range(pages):
        path=folder/(kind+"_"+str(index)+".json")
        raw=path.read_bytes();obj=json.loads(raw)
        page_expected=expected[index*50:(index+1)*50]
        verify_page(obj,kind,index,page_expected,master_sha,price_sha,cohort_sha)
        gate(not(set(obj["statuses"])&set(allrows)),"DUPLICATE")
        allrows.update(obj["statuses"])
        sources[str(index)]=hashlib.sha256(raw).hexdigest()
    gate(set(allrows)==set(expected),"FULL_EXACT_SET")
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
        meta={"asof_et":"2026-10-13","page":0,"execution":"NONE",
              "real_money":"NO-GO","statuses":{"AAPL":"LOWER_BOUND_GE_50M_SHADOW"},
              "schema":"XRAY_OCT13_ALPACA_50_SINGLE_SYMBOL_SIP_RTH_BOUNDS_V1",
              "target_symbols":["AAPL"],"target_count":1,
              "no_vendor_raw_ohlcv_exported":True,"single_symbol_isolation":True,
              "price_primary_created":False,"mc_primary_created":False,
              "r92_created":False,"canonical_files_mutated":False,
              "request_count":2}
        gate(verify_page(meta,"price",0,["AAPL"]),"SELFTEST_POSITIVE")
        for name,mutated,expect in (
            ("FOREIGN",dict(meta,statuses={"OTHER":"LOWER_BOUND_GE_50M_SHADOW"}),["AAPL"]),
            ("CROSS_ASOF",dict(meta,asof_et="2026-10-12"),["AAPL"]),
            ("FAKE_PRIMARY",dict(meta,price_primary_created=True),["AAPL"]),
            ("UNVERIFIED",dict(meta, statuses={"AAPL":"PASS_PRIMARY"}),["AAPL"]),
            ("SOURCE_PAGE_SWAP",dict(meta,target_symbols=["OTHER"]),["AAPL"])):
            try:verify_page(mutated,"price",0,expect)
            except ValueError:pass
            else:raise AssertionError("XRAY_ALL_LOCAL_NEGATIVE_ACCEPTED_"+name)
        print("XRAY_ALL_LOCAL_SELFTEST=PASS_5_ADVERSARIAL_VETOES_NO_GLOBAL_UNKNOWN_OR_FAKE_R92")
        return
    gate(x.price_dir and x.sec_dir and x.history and x.cohort and x.out,"ARGS")
    import subprocess
    master_path=ROOT/"canonical_current_master_manifest.json"
    price_path=ROOT/"canonical_current_price_dv30.json"
    sha=lambda z:subprocess.check_output(["git","hash-object",str(z)],text=True).strip()
    m=json.loads(master_path.read_bytes())
    price=json.loads(price_path.read_bytes())
    cohort_raw=x.cohort.read_bytes()
    cohort=json.loads(cohort_raw)
    gate(m.get("asof_et")==price.get("asof_et")=="2026-10-13",
         "CANONICAL_SOURCE_ASOF")
    gate(cohort.get("schema")=="XRAY_CANDIDATE_LOCAL_404_20261013_SOURCE_GATED_V1"
         and cohort.get("cross_asof_shadow_only") is True,
         "FROZEN_404_SOURCE_ONLY")
    wanted_price=price.get("unknown_symbols")
    wanted_sec=cohort.get("candidate_symbols")
    gate(type(wanted_price) is list and type(wanted_sec) is list
         and wanted_price==sorted(set(wanted_price))
         and wanted_sec==sorted(set(wanted_sec)),"SOURCE_SORT_AND_UNIQUENESS")
    p,ps=read_pages(x.price_dir,11,"price",wanted_price,sha(master_path),sha(price_path))
    s,ss=read_pages(x.sec_dir,9,"sec",wanted_sec,
                    cohort_sha=hashlib.sha256(cohort_raw).hexdigest())
    raw=x.history.read_bytes()
    gate(hashlib.sha256(raw).hexdigest()=="1d5bb3aaceb571fc84a631ab90e46fa15601067996a9062b2cc5ac6535563a9e",
         "HISTORY_FROZEN_SHA")
    history=json.loads(raw)
    gate(history.get("asof_et")=="2026-10-13"
         and len(history.get("symbol_statuses") or {})==3185,
         "IMMUTABLE_3185_HISTORY_MEMBERSHIP")
    report=compile_report(p,s,history,m,cohort)
    report["exact_page_and_current_blob_coverage_verified"]=True
    report["source_page_sha256"]={"price":ps,"sec":ss}
    gate(not x.out.resolve().is_relative_to(ROOT.parent.resolve()),"NO_REPO_WRITE")
    x.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_OCT13_LOCAL_545_404_SOURCE_OVERLAP="+str(report["source_overlap_count"]))
    print("XRAY_ALL_CANDIDATE_LOCAL_NO_R92=PASS")
if __name__=="__main__":main()
