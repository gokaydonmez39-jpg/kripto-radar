#!/usr/bin/env python3
"""C4.17 constrained HISTORY transport prefetch when PRICE has unresolved symbols.

SHADOW ONLY. Structural request for *existing* PRICE PASS symbols, never
canonical HISTORY authority. Four unresolved symbols remain UNKNOWN and cannot
be silently promoted, omitted from global readiness, or considered failures.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from current_history_source_request import expected_dates,sha256_lines,build as canonical_build

SCHEMA="XRAY_C417_PRICE_PARTIAL_HISTORY_PREFETCH_SHADOW_V1"
PRICE=ROOT/"canonical_current_price_dv30.json"
MASTER=ROOT/"canonical_current_master_manifest.json"

def git_blob(buf:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(buf)).encode()+b"\\0"+buf).hexdigest()

def ordered(xs):
    return isinstance(xs,list) and xs==sorted(set(xs)) and all(
        isinstance(s,str) and bool(s) for s in xs)

def build(price:dict,master:dict,price_sha:str,master_sha:str)->dict:
    if not all(isinstance(x,dict) for x in (price,master)):
        raise ValueError("INPUT_NOT_OBJECT")
    if not all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
               and x.get("unknown_never_pass") is True for x in (price,master)):
        raise ValueError("POLICY_SAFETY_INVALID")
    asof=price.get("asof_et")
    if asof!=master.get("asof_et") or not isinstance(asof,str):
        raise ValueError("SAME_ASOF_REQUIRED")
    if not all(isinstance(h,str) and len(h)==40
               and all(c in "0123456789abcdef" for c in h)
               for h in (price_sha,master_sha)):
        raise ValueError("GIT_BLOB_SHA_INVALID")
    passing=price.get("pass_symbols")
    unknown=price.get("unknown_symbols")
    blocked=price.get("blocked_symbols")
    master_scope=master.get("pass_symbols")
    for group in (passing,unknown,blocked,master_scope):
        if not ordered(group):
            raise ValueError("UNORDERED_OR_DUPLICATE_SCOPE")
    if not passing or not unknown:
        raise ValueError("THIS_CONTRACT_REQUIRES_PARTIAL_PRICE_AND_EXISTING_PASS")
    if not (len(passing)==price.get("pass_count")
        and len(unknown)==price.get("unknown_count")
        and len(blocked)==price.get("blocked_count")
        and sha256_lines(passing)==price.get("pass_hash")
        and set(passing).isdisjoint(unknown)
        and set(passing).isdisjoint(blocked)
        and set(unknown).isdisjoint(blocked)
        and set(passing+unknown+blocked).issubset(master_scope)
        and master.get("pass_count")==len(master_scope)
        and master.get("queue_hash")==price.get("source_master_queue_hash")
        and len(master_scope)==price.get("source_master_count")):
        raise ValueError("EXACT_PRICE_MASTER_SCOPE_MISMATCH")
    results=price.get("results")
    if not isinstance(results,dict) or set(results)!=set(master_scope):
        raise ValueError("PRICE_RESULT_PARTITION_NOT_FULL_MASTER")
    buckets=Counter()
    for symbol,record in results.items():
        if not isinstance(record,dict):raise ValueError("BAD_RESULT_RECORD")
        state=record.get("status")
        if state=="PASS_PRICE_DV30":
            if symbol not in passing:raise ValueError("PASS_SET_NOT_REPLAYABLE")
        elif state=="UNKNOWN":
            if symbol not in unknown:raise ValueError("UNKNOWN_SET_NOT_REPLAYABLE")
        elif state=="BLOCK_CURRENT_RUN":
            if symbol not in blocked:raise ValueError("BLOCKED_SET_NOT_REPLAYABLE")
        elif isinstance(state,str) and state.startswith("FAIL_"):
            if symbol in set(passing+unknown+blocked):
                raise ValueError("FAIL_SYMBOL_IN_ELIGIBLE_SCOPE")
        else:
            raise ValueError("NONTERMINAL_OR_UNRECOGNIZED_PRICE_STATUS")
        buckets[state]+=1
    if dict(buckets)!=price.get("counts"):
        raise ValueError("PRICE_COUNTS_NOT_REPLAYABLE")
    daily,weeks=expected_dates(asof)
    if (len(daily)!=260 or len(weeks)!=52 or daily[-1]!=asof
        or price.get("expected30")!=daily[-30:]):
        raise ValueError("NASDAQ_DATE_SET_NOT_EXACT")
    return {
      "schema":SCHEMA,"status":"SHADOW_TRANSPORT_REQUEST_READY_NO_CANONICAL_HISTORY",
      "asof_et":asof,"policy":"C4.17","control":"C4.27",
      "price_blob_sha":price_sha,"master_blob_sha":master_sha,
      "requested_price_pass_count":len(passing),
      "requested_price_pass_hash":sha256_lines(passing),
      "requested_symbols":passing,
      "explicit_unresolved_price_count":len(unknown),
      "explicit_unresolved_price_hash":sha256_lines(unknown),
      "excluded_unknown_symbols":unknown,
      "blocked_symbols":blocked,
      "required_260_official_sessions":daily,
      "required_52_completed_week_closes":weeks,
      "target_daily_count":260,"target_weekly_count":52,
      "vendor_calls_made":0,"vendor_bars_present":False,
      "provider_entitlement_proven":False,
      "raw_ohlcv_in_artifact":False,
      "canonical_history_authority":False,"canonical_history_pass_created":0,
      "mc_primary_pass_created":0,"full_e2e_pass":False,
      "r92_eligible":False,"can_register_R92":False,"device_receipt_proven":False,
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }

def selftest():
    asof="2026-10-09"
    master_syms=["AAA","BBB","CCC","DDD","EEE","FFF","GGG"]
    passing=["AAA","BBB"];unknown=["DDD","EEE","FFF","GGG"]
    p={"asof_et":asof,"pass_symbols":passing,"pass_count":2,
       "pass_hash":sha256_lines(passing),"unknown_symbols":unknown,
       "unknown_count":4,"blocked_symbols":[],"blocked_count":0,
       "source_master_queue_hash":"0"*64,"source_master_count":7,
       "results":{"AAA":{"status":"PASS_PRICE_DV30"},
                  "BBB":{"status":"PASS_PRICE_DV30"},
                  "CCC":{"status":"FAIL_DV30"},
                  **{x:{"status":"UNKNOWN"} for x in unknown}},
       "counts":{"PASS_PRICE_DV30":2,"FAIL_DV30":1,"UNKNOWN":4},
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    m={"asof_et":asof,"pass_symbols":master_syms,"pass_count":7,
       "queue_hash":"0"*64,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    daily,_=expected_dates(asof);p["expected30"]=daily[-30:]
    res=build(p,m,"a"*40,"b"*40)
    assert res["requested_price_pass_count"]==2
    assert res["explicit_unresolved_price_count"]==4
    assert res["canonical_history_pass_created"]==0
    try:canonical_build(p,m,"a"*40)
    except AssertionError:pass
    else:raise AssertionError("CANONICAL_PRICE_UNKNOWN_BYPASSED")
    for tag,fn in (
      ("unknown_becomes_pass",lambda pp,mm:pp["results"]["DDD"].update(status="PASS_PRICE_DV30")),
      ("undocumented_fail",lambda pp,mm:pp["results"]["CCC"].update(status="UNKNOWN")),
      ("unbound_price",lambda pp,mm:pp.update(pass_hash="0"*64)),
      ("bad_unknown_count",lambda pp,mm:pp.update(unknown_count=0)),
      ("master_extra",lambda pp,mm:mm["pass_symbols"].append("ZZZ")),
      ("asof_drift",lambda pp,mm:mm.update(asof_et="2026-10-08")),
      ("unsafe",lambda pp,mm:pp.update(real_money="GO")),
      ("duplicate",lambda pp,mm:pp["unknown_symbols"].append("DDD")),
      ("bad_date",lambda pp,mm:pp["expected30"][-1:]=["2026-10-08"]),
      ("counts_mismatch",lambda pp,mm:pp["counts"].update(UNKNOWN=3)),
    ):
        x,y=copy.deepcopy(p),copy.deepcopy(m);fn(x,y)
        try:build(x,y,"a"*40,"b"*40)
        except (ValueError,AssertionError):continue
        raise AssertionError("FAIL_OPEN_PARTIAL_PRICE_PREFETCH:"+tag)
    print("XRAY_HISTORY_PREFETCH_PARTIAL_PRICE=PASS_10_NEGATIVES_4_UNKNOWN_STAY_UNKNOWN_NO_VENDOR_NO_PRIMARY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest();return
    price_buf=PRICE.read_bytes()
    master_buf=MASTER.read_bytes()
    report=build(json.loads(price_buf),json.loads(master_buf),
                 git_blob(price_buf),git_blob(master_buf))
    print("XRAY_SHADOW_PREFETCH_PRICE_PASS="+str(report["requested_price_pass_count"]))
    print("XRAY_SHADOW_PREFETCH_PRICE_UNKNOWN_EXCLUDED="+str(report["explicit_unresolved_price_count"]))
    if args.out:
        if args.out.resolve().is_relative_to(ROOT.parent):
            raise ValueError("OUTPUT_TO_PUBLIC_GITHUB_TREE_FORBIDDEN")
        args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\\n")
    print("XRAY_SHADOW_PREFETCH=SAFE_RESEARCH_ONLY_NO_HISTORY_PASS_OR_TRADES")

if __name__=="__main__":
    main()
