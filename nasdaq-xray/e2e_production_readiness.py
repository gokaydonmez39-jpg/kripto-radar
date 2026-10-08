#!/usr/bin/env python3
"""Read-only C4.17 / manual-research end-to-end production readiness witness.

Outputs *blocked states*, never prices, tickers, trade instructions or signals.
A green CI job running this script is NOT a production-ready claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY="68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4"

def read(name):
    p=ROOT/name
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError,OSError): return {}

def sha(name):
    try:
        b=(ROOT/name).read_bytes()
        return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
    except OSError:
        return None

def mc_exact(mc,price,price_sha):
    """Do NOT accept WATCH, missing provenance or incomplete symbol partitions."""
    symbols=set(price.get("pass_symbols") or [])
    statuses={
       "MC_PASS_PRIMARY":set(mc.get("primary_pass_symbols") or []),
       "MC_FAIL_PRIMARY":set(mc.get("primary_fail_symbols") or []),
       "MC_PASS_FALLBACK_WATCH":set(mc.get("fallback_watch_symbols") or []),
       "MC_FAIL_FALLBACK_TWO_SOURCE":set(mc.get("fallback_fail_symbols") or mc.get("fallback_two_source_fail_symbols") or []),
       "MC_UNKNOWN":set(mc.get("unknown_symbols") or [])}
    if not (mc.get("asof_et")==price.get("asof_et")
            and mc.get("input_blob_sha")==price_sha
            and mc.get("input_pass_hash")==price.get("pass_hash")
            and mc.get("policy_hash")==POLICY
            and mc.get("execution")=="NONE" and mc.get("real_money")=="NO-GO"
            and mc.get("unknown_never_pass") is True
            and set(mc.get("input_pass_symbols") or [])==symbols
            and len(mc.get("input_pass_symbols") or [])==len(symbols)
            and set(mc.get("results") or {})==symbols):
        return False
    seen=set()
    for group, group_symbols in statuses.items():
        if seen & group_symbols:return False
        seen |= group_symbols
        if any((mc["results"][s] or {}).get("status") != group for s in group_symbols):
            return False
    counts=mc.get("counts") or {}
    if any(int(counts.get(k,-1))!=len(v) for k,v in statuses.items()):
        return False
    return seen==symbols

def snapshot():
    master=read("canonical_current_master_manifest.json")
    price=read("canonical_current_price_dv30.json")
    req=read("canonical_current_resolver_request.json")
    terminal=read("canonical_current_terminal.json")
    ledger=read("delivery_ledger.json")
    blocks=[]
    def fail(code,ok):
        if not ok:blocks.append(code)
    asof=master.get("asof_et")
    safety=(all(x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                and x.get("unknown_never_pass") is True for x in (master,price,req,terminal)))
    fail("POLICY_SAFETY_NOT_ALL_ATTESTED",safety)
    master_set=set(master.get("pass_symbols") or [])
    fail("IDENTITY_PARTITION_INCOMPLETE",master.get("unknown_count")==0
         and int(master.get("queue_total") or -1)==len(master_set))
    price_set=set(price.get("pass_symbols") or [])
    fail("PRICE_PARTITION_NOT_EXACT_CURRENT",bool(asof)
         and price.get("asof_et")==asof
         and price.get("source_master_queue_hash")==master.get("queue_hash")
         and price.get("source_master_count")==master.get("queue_total")
         and len(price.get("results") or {})==len(master_set)
         and set(price.get("results") or {})==master_set
         and set(price.get("blocked_symbols") or []).isdisjoint(price_set)
         and int(price.get("pass_count") or -1)==len(price_set))
    fail("PRICE_BLOCKED_30_SESSION_BARS",price.get("unknown_count")==0
         and price.get("blocked_count")==0)
    price_sha=sha("canonical_current_price_dv30.json")
    fail("SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",req.get("asof_et")==asof
         and req.get("source_master_blob_sha")==sha("canonical_current_master_manifest.json")
         and req.get("source_price_blob_sha")==price_sha
         and req.get("settlement_already_proven") is True
         and req.get("settlement_bridge_blob_sha")==sha(
             Path(str(req.get("settlement_bridge_path") or "")).name))
    mc_files=list(ROOT.glob("canonical_mc_bridge_*_c417_dv30_v*.json"))
    mc_authorities=[p for p in mc_files if p.name.startswith("canonical_mc_bridge_"+str(asof or "").replace("-","")+"_"+ "c417_dv30_v")]
    mcs=[]
    for p in mc_authorities:
        try:j=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        if mc_exact(j,price,price_sha):mcs.append(p.name)
    fail("CURRENT_MC_AUTHORITY_MISSING",len(mcs)==1)
    exact_terminal=(terminal.get("asof_et")==asof
        and terminal.get("full_end_to_end_research_pass") is True
        and terminal.get("compiled_policy_hash")==POLICY)
    fail("CURRENT_TERMINAL_FROZEN_OR_INCOMPLETE",exact_terminal)
    fail("TERMINAL_CURRENT_MC_CHAIN_NOT_PROVEN",len(mcs)==1 and exact_terminal)
    # Delivery is independent: a zero-signal scenario may be a legitimate
    # completed run, but a device receipt must never be inferred from a ledger.
    fail("NOTIFICATION_DEVICE_RECEIPT_NOT_PROVEN",False)
    return {
        "schema":"XRAY_E2E_PRODUCTION_READINESS_AUDIT_V1",
        "asof_et":asof,"research_mode":"RESEARCH_ONLY_MANUAL_DECISION",
        "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
        "blockers":sorted(set(blocks)),
        "ready_for_current_research_signal":False,
        "full_e2e_research_attested":len(mcs)==1 and exact_terminal
            and not any(k in blocks for k in (
                "PRICE_PARTITION_NOT_EXACT_CURRENT","POLICY_SAFETY_NOT_ALL_ATTESTED",
                "SETTLEMENT_UNVERIFIED_OR_PRICE_SHA_DRIFT",
                "IDENTITY_PARTITION_INCOMPLETE","PRICE_BLOCKED_30_SESSION_BARS")),
        "current_mc_authority_count":len(mcs),
        "price_pass_count":price.get("pass_count"),"price_blocked_count":price.get("blocked_count"),
        "master_unknown_count":master.get("unknown_count"),
        "terminal_asof_et":terminal.get("asof_et"),
        "ledger_entry_count":len(ledger.get("deliveries") or {}),
        "source_blob_shas":{
            "master":sha("canonical_current_master_manifest.json"),
            "price":price_sha,
            "resolver_request":sha("canonical_current_resolver_request.json"),
            "terminal":sha("canonical_current_terminal.json")},
        "no_trading_or_device_receipt_claim":True,
        "explanation":"An Actions SUCCESS for this audit only means the fail-closed blocker classification completed."
    }

def selftest():
    price={"asof_et":"2026-10-08","pass_symbols":["A","B"],"pass_hash":"X"}
    mc={"asof_et":"2026-10-08","input_blob_sha":"P","input_pass_hash":"X",
       "input_pass_symbols":["A","B"],"policy_hash":POLICY,"execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "primary_pass_symbols":["A"],"primary_fail_symbols":[],
       "fallback_watch_symbols":["B"],"fallback_fail_symbols":[],"unknown_symbols":[],
       "counts":{"MC_PASS_PRIMARY":1,"MC_FAIL_PRIMARY":0,"MC_PASS_FALLBACK_WATCH":1,
                "MC_FAIL_FALLBACK_TWO_SOURCE":0,"MC_UNKNOWN":0},
       "results":{"A":{"status":"MC_PASS_PRIMARY"},"B":{"status":"MC_PASS_FALLBACK_WATCH"}}}
    assert mc_exact(mc,price,"P")
    from copy import deepcopy
    for change in (
       lambda x:x.update(input_blob_sha="OTHER"),
       lambda x:x.update(asof_et="2026-10-07"),
       lambda x:x["results"]["B"].update(status="MC_PASS_PRIMARY"),
       lambda x:x["unknown_symbols"].append("B"),
       lambda x:x["counts"].update(MC_PASS_PRIMARY=2),
       lambda x:x.update(input_pass_symbols=["A"]),
       lambda x:x.update(policy_hash="INVALID")):
        bad=deepcopy(mc);change(bad)
        assert not mc_exact(bad,price,"P"),bad
    print("XRAY_E2E_READINESS_MC_SELFTEST=PASS_POSITIVE_7_NEGATIVES")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output")
    args=p.parse_args()
    if args.selftest:
        selftest()
    else:
        result=snapshot()
        if args.output:
            Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print("XRAY_E2E_READINESS="+("ATTESTED_TECH_CHAIN_ONLY" if result["full_e2e_research_attested"] else "BLOCKED"))
        print("XRAY_E2E_BLOCKERS="+json.dumps(result["blockers"]))
        print("XRAY_E2E_SNAPSHOT="+json.dumps(result,sort_keys=True))
