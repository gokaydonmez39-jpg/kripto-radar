#!/usr/bin/env python3
"""Source-exact Nasdaq EOD PRICE/DV30 screen. Not a technical AL or an order."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_EOD_LIQUIDITY_SCREEN_V1"
FILES={
    "master":"canonical_current_master_manifest.json",
    "price":"canonical_current_price_dv30.json",
    "policy":"chatgpt_compiled_policy_v3.json",
    "history":"canonical_current_history.json",
    "final":"canonical_current_final_tech.json",
    "terminal":"canonical_current_terminal.json",
}

def require(value,reason):
    if not value: raise ValueError("XRAY_EOD_SCREEN_FAIL_CLOSED:"+reason)

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def shash(symbols):
    return hashlib.sha256("\n".join(symbols).encode()).hexdigest()

def exact_symbols(symbols):
    return (type(symbols) is list and symbols==sorted(set(symbols))
            and all(type(s) is str and re.fullmatch(r"[A-Z0-9.-]+",s) for s in symbols))

def analyze(obj,sha,now_utc):
    m,p,pol,h,f,t=(obj[k] for k in FILES)
    require(now_utc.tzinfo is not None and now_utc.utcoffset()==dt.timedelta(0),
            "RUNTIME_UTC_REQUIRED")
    for key,v in obj.items():
        require(v.get("execution")=="NONE" and v.get("real_money")=="NO-GO",
                "EXECUTION_SAFETY_"+key)
    require(m.get("unknown_never_pass") is True and p.get("unknown_never_pass") is True
            and t.get("unknown_never_pass") is True,"UNKNOWN_NEVER_PASS")
    require(pol.get("schema")=="XRAY_GITHUB_COMPILED_POLICY_V3"
            and pol.get("policy_hash")=="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"
            and sha["policy"]=="16c50cc8f887a5234a4be23862d7c8d0e564b0ac",
            "COMPILED_POLICY_EXACT")
    cp=json.loads(pol.get("payload_json") or "{}")
    require(cp.get("version")=="C4.17" and cp.get("unknown_never_pass") is True
            and cp.get("execution")=="NONE" and cp.get("real_money")=="NO-GO",
            "ALPHA_POLICY_FROZEN")
    require(p.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1"
            and m.get("schema")=="XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1",
            "SOURCE_SCHEMA")
    require(p.get("asof_et")==m.get("asof_et"),"SAME_ASOF")
    require(p.get("thresholds")=={"price":">=5","dv30":">=50000000 exact30 median"}
            and p.get("gate_order")==["PRICE","DV30"],"ALPHA_THRESHOLD_DRIFT")
    allowed_master=m.get("pass_symbols")
    screen=p.get("pass_symbols")
    unknown=m.get("unknown_symbols")
    require(all(exact_symbols(x) for x in (allowed_master,screen,unknown)),
            "SYMBOL_IDENTITY_OR_ORDER")
    require(len(allowed_master)==m.get("pass_count")==m.get("queue_total")
            and m.get("queue_hash")==shash(allowed_master)
            and m.get("queue_unique")==len(allowed_master),"MASTER_QUEUE_INTEGRITY")
    require(len(unknown)==m.get("unknown_count")
            and not (set(unknown)&set(allowed_master))
            and not (set(unknown)&set(screen)),"MASTER_UNKNOWN_NOT_SAFE")
    require(len(screen)==p.get("pass_count") and
            p.get("pass_hash")==shash(screen) and
            set(screen).issubset(allowed_master),"PRICE_SYMBOL_SET_OR_HASH")
    require(p.get("source_master_queue_hash")==m["queue_hash"]
            and p.get("source_master_count")==len(allowed_master),
            "MASTER_PRICE_LINEAGE")
    unresolved=p.get("unknown_symbols")
    blocked=p.get("blocked_symbols")
    require(exact_symbols(unresolved) and exact_symbols(blocked)
            and p.get("unknown_count")==len(unresolved)
            and p.get("blocked_count")==len(blocked)
            and not (set(unresolved)&set(blocked))
            and not (set(screen)&(set(unresolved)|set(blocked))),
            "PRICE_UNRESOLVED_PARTITION")
    counts=p.get("counts")
    require(type(counts) is dict and all(type(v) is int and v>=0
            for v in counts.values()),"PRICE_PARTITION_COUNTS")
    rows=p.get("results")
    require(type(rows) is dict and set(rows)==set(allowed_master),
            "PRICE_CLASSIFICATION_SET")
    observed={}
    for symbol in allowed_master:
        row=rows[symbol]
        require(type(row) is dict,"PRICE_ROW_NOT_OBJECT")
        state=row.get("status")
        require(type(state) is str and
                (state in {"PASS_PRICE_DV30","UNKNOWN","BLOCK_CURRENT_RUN"}
                 or state.startswith("FAIL_")),"PRICE_ROW_STATUS_INVALID")
        observed[state]=observed.get(state,0)+1
    require(counts==observed and counts.get("PASS_PRICE_DV30",0)==len(screen),
            "PRICE_PARTITION_COUNTS")
    require(set(unresolved)=={s for s in allowed_master
                             if rows[s]["status"]=="UNKNOWN"}
            and set(blocked)=={s for s in allowed_master
                               if rows[s]["status"]=="BLOCK_CURRENT_RUN"},
            "PRICE_UNRESOLVED_ROW_MISMATCH")
    for symbol in screen:
        row=rows.get(symbol) or {}
        info=row.get("info") or {}
        require(row.get("status")=="PASS_PRICE_DV30"
                and info.get("compact_terminal_proof") is True
                and info.get("no_synthetic_bar") is True
                and info.get("known_session_count")==30
                and info.get("missing_sessions")==[]
                and info.get("proof")=="EXACT30_MEDIAN_GE_GATE",
                "PRICE_PASS_EVIDENCE_"+symbol)
    for symbol in allowed_master:
        require((rows[symbol].get("status")=="PASS_PRICE_DV30")== (symbol in set(screen)),
                "PRICE_ROW_PARTITION_"+symbol)
    last=last_complete_session(now_utc)
    source_complete=not unresolved and not blocked
    ready=source_complete and p["asof_et"]==last
    return {
        "schema":SCHEMA,
        "asof_et":p["asof_et"],
        "latest_completed_official_nasdaq_session":last,
        "status":("EOD_PRICE_DV30_SOURCE_BLOCKED" if not source_complete
                  else "EOD_PRICE_DV30_SCREEN_READY" if ready
                  else "EOD_PRICE_DV30_SCREEN_STALE"),
        "current_screen_ready":ready,
        "source_cohort_complete":source_complete,
        "price_unknown_count":len(unresolved),
        "price_blocked_count":len(blocked),
        "withheld_due_to_incomplete_source_count":len(screen) if not source_complete else 0,
        "scope":"EXACT_MASTER_IDENTITY_PASS",
        "master_identity_pass_count":len(allowed_master),
        "master_identity_unknown_count":len(unknown),
        "master_unknown_intersect_screen_count":0,
        "price_dv30_pass_count":len(screen),
        "screen_symbols":screen if ready else [],
        "stale_observation_count":0 if ready else len(screen),
        "price_counts":counts,
        "gate_price_usd":5,
        "gate_dv30_median_usd":50000000,
        "gate_dv30_completed_sessions":30,
        "source_blob_shas":sha,
        "source_epoch_diagnostics":{"history":h.get("asof_et"),
            "final":f.get("asof_et"),"terminal":t.get("asof_et")},
        "technical_research_status":"NOT_VERIFIED_IN_THIS_SCREEN",
        "market_cap_primary_status":"NOT_VERIFIED_IN_THIS_SCREEN",
        "qualified_al_count":None,
        "no_confirmed_setup_asserted":False,
        "r92_registered_here":0,
        "research_signals":[],
        "g9_required_for_eod_liquidity_screen":False,
        "account_required_for_eod_liquidity_screen":False,
        "alpha_authority":False,
        "delivery_authority":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
        "orders":[],
    }

def build(root,now_utc):
    objs={};hashes={}
    for k,name in FILES.items():
        raw=(root/name).read_bytes()
        hashes[k]=blob(raw)
        objs[k]=json.loads(raw)
    return analyze(objs,hashes,now_utc)

def selftest():
    now=dt.datetime(2026,10,12,13,0,tzinfo=dt.timezone.utc)
    assert last_complete_session(now)=="2026-10-09"
    passed=["AAPL","NVDA"]
    missed=["ALIS"]
    master=["AAPL","NVDA","ZZZZ"]
    m={"schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1",
       "asof_et":"2026-10-09","pass_symbols":master,"pass_count":3,
       "queue_total":3,"queue_unique":3,"queue_hash":shash(master),
       "unknown_symbols":missed,"unknown_count":1,
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    p={"schema":"XRAY_CANONICAL_PRICE_DV30_V1",
       "asof_et":"2026-10-09","pass_symbols":passed,"pass_count":2,
       "pass_hash":shash(passed),"source_master_queue_hash":m["queue_hash"],
       "source_master_count":3,"unknown_count":0,"blocked_count":0,
       "unknown_symbols":[],"blocked_symbols":[],
       "gate_order":["PRICE","DV30"],
       "thresholds":{"price":">=5","dv30":">=50000000 exact30 median"},
       "counts":{"PASS_PRICE_DV30":2,"FAIL_PRICE":1},
       "results":{s:{"status":"PASS_PRICE_DV30",
                    "info":{"compact_terminal_proof":True,
                            "no_synthetic_bar":True,"known_session_count":30,
                            "missing_sessions":[],"proof":"EXACT30_MEDIAN_GE_GATE"}}
                  for s in passed},
       "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}
    p["results"]["ZZZZ"]={"status":"FAIL_PRICE"}
    po={"schema":"XRAY_GITHUB_COMPILED_POLICY_V3",
        "policy_hash":"68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4",
        "payload_json":json.dumps({"version":"C4.17","unknown_never_pass":True,
                                   "execution":"NONE","real_money":"NO-GO"}),
        "execution":"NONE","real_money":"NO-GO"}
    other={"asof_et":"2026-10-07","execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True}
    base={"master":m,"price":p,"policy":po,
          "history":other,"final":other,"terminal":other}
    hashes={k:"a"*40 for k in base}
    hashes["policy"]="16c50cc8f887a5234a4be23862d7c8d0e564b0ac"
    got=analyze(copy.deepcopy(base),hashes,now)
    assert got["status"]=="EOD_PRICE_DV30_SCREEN_READY"
    assert got["screen_symbols"]==passed
    assert got["qualified_al_count"] is None and got["research_signals"]==[]
    assert got["execution"]=="NONE" and got["real_money"]=="NO-GO"
    stale=analyze(copy.deepcopy(base),hashes,dt.datetime(2026,10,12,21,0,tzinfo=dt.timezone.utc))
    assert stale["screen_symbols"]==[] and not stale["current_screen_ready"]
    partial=copy.deepcopy(base)
    partial["price"]["results"]["ZZZZ"]["status"]="UNKNOWN"
    partial["price"]["counts"]={"PASS_PRICE_DV30":2,"UNKNOWN":1}
    partial["price"]["unknown_count"]=1
    partial["price"]["unknown_symbols"]=["ZZZZ"]
    blocked_report=analyze(copy.deepcopy(partial),hashes,now)
    assert blocked_report["status"]=="EOD_PRICE_DV30_SOURCE_BLOCKED"
    assert not blocked_report["current_screen_ready"]
    assert not blocked_report["source_cohort_complete"]
    assert blocked_report["price_unknown_count"]==1
    assert blocked_report["screen_symbols"]==[] and blocked_report["research_signals"]==[]
    assert blocked_report["qualified_al_count"] is None and blocked_report["r92_registered_here"]==0
    blocked_mutations=[
        lambda x:x["price"]["counts"].update(UNKNOWN=0),
        lambda x:x["price"].update(unknown_symbols=["AAPL"]),
        lambda x:x["price"]["results"]["AAPL"]["info"].update(no_synthetic_bar=False),
        lambda x:x["price"].update(blocked_symbols=["ZZZZ"],blocked_count=1),
        lambda x:x["price"]["results"]["ZZZZ"].update(status="PASS"),
    ]
    for i,mutate in enumerate(blocked_mutations):
        case=copy.deepcopy(partial);mutate(case)
        try:analyze(case,hashes,now)
        except ValueError:pass
        else:raise RuntimeError("UNSAFE_PARTIAL_SCREEN_ACCEPTED:"+str(i))
    mutations=[
        lambda x:x["price"].update(pass_hash="0"*64),
        lambda x:x["price"]["results"]["AAPL"]["info"].update(known_session_count=29),
        lambda x:x["price"]["results"]["AAPL"]["info"].update(no_synthetic_bar=False),
        lambda x:x["price"].update(unknown_count=1),
        lambda x:x["master"].update(unknown_symbols=["AAPL"],unknown_count=1),
        lambda x:x["price"]["results"]["ZZZZ"].update(status="PASS_PRICE_DV30"),
        lambda x:x["price"]["thresholds"].update(price=">=1"),
        lambda x:x["price"].update(asof_et="2026-10-12"),
        lambda x:x["master"].update(queue_hash="x"*64),
        lambda x:x["master"].update(execution="LIVE"),
        lambda x:x["price"].update(pass_count=1),
        lambda x:x["policy"].update(policy_hash="bad"),
    ]
    for i,mutate in enumerate(mutations):
        case=copy.deepcopy(base);mutate(case)
        try:analyze(case,hashes,now)
        except ValueError:pass
        else:raise RuntimeError("UNSAFE_SCREEN_MUTATION_ACCEPTED:"+str(i))
    print("XRAY_EOD_SCREEN_SELFTEST=PASS_3_POSITIVE_17_NEGATIVE_NO_MC_NO_AL")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    if args.out is None or args.out.resolve().is_relative_to(ROOT.parent.resolve()):
        ap.error("write report to a runner-private output path only")
    report=build(ROOT,dt.datetime.now(dt.timezone.utc))
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("XRAY_EOD_SCREEN="+report["status"])
    print("XRAY_EOD_PRICE_DV30_PASS_COUNT="+str(report["price_dv30_pass_count"]))
    print("XRAY_EOD_SCREENED_SYMBOLS="+str(len(report["screen_symbols"])))
    print("XRAY_EOD_CURRENT_AL=UNVERIFIED_NOT_ZERO")
    print("XRAY_EOD_EXECUTION=NONE")

if __name__=="__main__":
    main()
