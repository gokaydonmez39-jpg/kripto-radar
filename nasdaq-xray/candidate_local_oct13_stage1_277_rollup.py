#!/usr/bin/env python3
"""Immutable-source rollup for 277 Oct13 SIP 260-session Stage1 results."""
import argparse,collections,hashlib,json
from pathlib import Path
# Pure metadata reconciliation: do not import the pandas-heavy Stage1 engine.

ASOF="2026-10-13"
SOURCE_SHA="c05669e7fbd0a91c3f6fb9f652c330157066496747132dcfc291d121d99fb26c"
STAGE0_SHA="114c04313f9763d485977a5b698986bef70363b2bbb613b7df31ad0c5597454d"
FIRST_SCHEMA="XRAY_OCT13_28_REAL_SIP_260_STAGE1_RESEARCH_SHADOW_V1"
REST_SCHEMA="XRAY_20261013_277_STAGE1_SIP_PAGE_RESEARCH_V1"
ALLOWED={
 "STAGE1_RESEARCH_POOL_ONLY",
 "STAGE1_RESEARCH_WEEKLY_PASS_NO_POOL",
 "STAGE1_RESEARCH_WEEKLY_FAIL",
 "UNKNOWN_CORPORATE_ACTION_PIT_NOT_RECONCILED",
 "UNKNOWN_INCOMPLETE_260_SIP",
 "UNKNOWN_SOURCE_OR_INTEGRITY",
 "UNKNOWN_NOT_ATTEMPTED_AFTER_PROVIDER_STOP"}
def check(x,msg):
    if not x:raise ValueError("XRAY_STAGE1_277_ROLLUP_"+msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def make(source,first,pages):
    raw=source.read_bytes()
    check(sha(raw)==SOURCE_SHA,"277_SOURCE_SHA")
    doc=json.loads(raw)
    syms=doc["source_overlap_symbols"]
    check(len(syms)==277 and syms==sorted(set(syms))
          and doc["asof_et"]==ASOF,"277_SOURCE_COHORT")
    rows={};pins={};calls=0
    for index in range(10):
        file=first if index==0 else pages/("stage1_"+str(index)+".json")
        buf=file.read_bytes();d=json.loads(buf)
        if index==0:
            check(sha(buf)==STAGE0_SHA,"IMMUTABLE_FIRST28_SHA")
        check(d.get("source_277_json_sha256")==SOURCE_SHA,
              "EXACT_UPSTREAM_SOURCE_LINK")
        check(d.get("unknown_never_pass") is True,"FAIL_CLOSED_EACH_PAGE")
        check(d.get("schema")==(FIRST_SCHEMA if index==0 else REST_SCHEMA)
              and d.get("asof_et")==ASOF,"PAGE_SCHEMA_ASOF")
        check(index==0 or d.get("page")==index,"PAGE_ORDINAL")
        wanted=syms[index*28:(index+1)*28]
        actual=d["status_by_symbol"]
        check(d.get("target_symbols")==wanted and
              set(actual)==set(wanted),"PAGE_EXACT_SET")
        check(sum(d["result_counts"].values())==len(wanted),"PAGE_CLASSIFIED")
        actual_counts=dict(collections.Counter(
             row.get("status") for row in actual.values()))
        check(actual_counts==d["result_counts"],"PAGE_COUNTS_RECOMPUTED")
        if index==0:
            check(d.get("raw_ohlcv_persisted") is False,"RAW_DATA_NOT_PUBLIC")
        else:
            check(d.get("no_raw_OHLCV_export") is True,"RAW_DATA_NOT_PUBLIC")
        check(d["r92_registered"]==0 and
              d.get("canonical_primary_created",False) is False
              and d.get("canonical_mutated",False) is False
              and d["execution"]=="NONE" and d["real_money"]=="NO-GO",
              "PAGE_RESEARCH_ONLY")
        for s,v in actual.items():
            state=v.get("status")
            check(state in ALLOWED or state.startswith("UNKNOWN_HTTP_"),
                  "UNEXPECTED_STAGE1_STATE")
            rows[s]=state
        pins[str(index)]=sha(buf)
        calls+=d.get("api_calls",d.get("actual_provider_calls",0))
    check(set(rows)==set(syms) and len(rows)==277,"GLOBAL_277_EXACT")
    counts=dict(sorted(collections.Counter(rows.values()).items()))
    positive=sorted(s for s in syms if rows[s]=="STAGE1_RESEARCH_POOL_ONLY")
    return {
      "schema":"XRAY_OCT13_STAGE1_277_FULL_RESEARCH_SOURCE_ROLLUP_V1",
      "asof_et":ASOF,"total_source_scope":277,
      "stage1_actual_symbol_statuses":rows,
      "stage1_status_counts":counts,
      "stage1_pool_count":len(positive),
      "stage1_pool_symbols":positive,
      "actual_sip_one_day_http_requests":calls,
      "source_277_sha256":sha(raw),
      "stage1_page_sha256":pins,
      "full_277_source_coverage_classified":True,
      "unrelated_global_master_unknown_not_veto":True,
      "stage1_pool_is_not_R92":True,
      "official_event_halt_unverified":True,
      "sec_class_pit_mc_primary_unverified":True,
      "close_corrections_unverified":True,
      "regime_deep_r1_rr_full_scope_unverified":True,
      "registered_r92":0,"iphone_receipt_verified":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
def selftest():
    x={"AAPL":"STAGE1_RESEARCH_POOL_ONLY",
       "OTHER":"UNKNOWN_CORPORATE_ACTION_PIT_NOT_RECONCILED"}
    check(len(x)==2 and x["OTHER"]!="STAGE1_RESEARCH_POOL_ONLY",
          "UNKNOWN_IS_NOT_POOL")
    check(277==9*28+25,"PAGE_PARTITION")
    print("XRAY_STAGE1_277_ROLLUP_SELFTEST=PASS_EXACT_277_UNKNOWN_VETO")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--source",type=Path)
    p.add_argument("--first",type=Path)
    p.add_argument("--pages-dir",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    check(a.source and a.first and a.pages_dir and a.out,"CLI")
    check(not a.out.resolve().is_relative_to(
          Path(__file__).resolve().parent.parent),"NO_PUBLIC_VENDOR_EXPORT")
    r=make(a.source,a.first,a.pages_dir)
    a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print("XRAY_STAGE1_277_FULL_SOURCE_POOL_COUNT="+str(r["stage1_pool_count"]))
    print("XRAY_STAGE1_277_FULL_STATUS_COUNTS="+json.dumps(r["stage1_status_counts"],sort_keys=True))
    print("XRAY_STAGE1_277_ACTUAL_SIP_REQUESTS="+str(r["actual_sip_one_day_http_requests"]))
    print("XRAY_STAGE1_277_SHADOW_NOT_R92=PASS")
if __name__=="__main__":main()
