#!/usr/bin/env python3
"""Snapshot-only SIP EOD research-watch integrity. Never synthesizes BUY/GO.

A one-off connected-provider observation may be surfaced in research telemetry,
but does not confer an unattended vendor license, PRICE/MC authority, R92, G9,
account, candidate delivery, or canonical FINAL status.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from source_epoch_freshness_guard import last_complete_session

SNAPSHOT = ROOT / "research" / "sip_eod_manual_11_watch_20261009_v1.json"
MASTER = ROOT / "canonical_current_master_manifest.json"
PRICE = ROOT / "canonical_current_price_dv30.json"
POLICY = ROOT / "chatgpt_compiled_policy_v3.json"
FORBIDDEN = {"close","open","high","low","market_cap","raw_bars","bars","volume",
             "daily_ohlcv","trade_price","entry","stop","target","orders",
             "user_account","access_token","api_key"}


def must(condition, reason):
    if not condition:
        raise ValueError("XRAY_SIP_MANUAL_WATCH_BLOCKED:" + reason)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def symbol_hash(symbols):
    return hashlib.sha256("\n".join(symbols).encode()).hexdigest()


def valid_symbols(values):
    return (type(values) is list and values == sorted(set(values))
            and all(type(s) is str and re.fullmatch(r"[A-Z0-9.-]+",s) for s in values))


def evaluate(snapshot, master, price, policy, hashes, now_utc):
    must(now_utc.tzinfo is not None and now_utc.utcoffset() == dt.timedelta(),
         "UTC_CLOCK")
    must(snapshot.get("schema") == "XRAY_INTERACTIVE_SIP_EOD_TECHNICAL_WATCH_SHADOW_V1",
         "SNAPSHOT_SCHEMA")
    must(not (FORBIDDEN & set(snapshot)), "NO_RAW_OR_ORDER_DATA")
    must(snapshot.get("asof_et") == "2026-10-09" and
         snapshot.get("observation_date_trt") == "2026-10-12",
         "OBSERVATION_SESSION_FROZEN")
    must(snapshot.get("research_only") is True and
         snapshot.get("manual_interactive_sip_only") is True and
         snapshot.get("automated_vendor_history_fetch_this_run") is False and
         snapshot.get("runner_provider_rights_verified") is False and
         snapshot.get("provider_upstream_independence_verified") is False and
         snapshot.get("c417_production_history_promoted") is False and
         snapshot.get("c417_production_primary_mc_promoted") is False and
         snapshot.get("strict_g9_pass") is False and
         snapshot.get("account_pass") is False and
         snapshot.get("technical_al_confirmed") is False and
         snapshot.get("alpha_authority") is False and
         snapshot.get("delivery_authority") is False and
         snapshot.get("order_authority") is False and
         snapshot.get("no_alpha_policy_change") is True and
         snapshot.get("no_device_delivery_claim") is True and
         snapshot.get("market_data_values_in_public_artifact") is False and
         snapshot.get("original_raw_vendor_bars_in_public_artifact") is False and
         snapshot.get("execution") == "NONE" and
         snapshot.get("real_money") == "NO-GO" and
         snapshot.get("unknown_never_pass") is True,
         "PRODUCTION_PROMOTION_FORBIDDEN")
    must(snapshot.get("interactive_providers") ==
         ["ALPACA_HISTORIC_SIP","RALLIES_HISTORICAL","LONGBRIDGE_EOD_QUOTE"]
         and snapshot.get("eod_close_crosschecked_symbols_count") == 11
         and snapshot.get("eod_close_crosschecked_all_exact") is True
         and snapshot.get("eod_same_upstream_independence") == "UNKNOWN",
         "SOURCE_CROSSCHECK_UNREPLAYED")
    a = snapshot.get("watch_55d_high_breakout")
    b = snapshot.get("watch_near20d_high")
    watches = snapshot.get("watch_symbols")
    unavailable = snapshot.get("insufficient_260_sessions_symbols")
    must(all(valid_symbols(v) for v in (a,b,watches,unavailable)),
         "SYMBOL_SET_INVALID")
    must(len(a) == 5 and len(b) == 6 and len(watches) == 11 and
         watches == sorted(set(a+b)) and
         not set(watches).intersection(unavailable) and
         len(unavailable) == 17 and
         snapshot.get("observed_technical_watch_count") == 11 and
         snapshot.get("scope_price_dv30_pass") == 514 and
         snapshot.get("full_260_session_and_52_iso_week_coverage") == 497 and
         snapshot.get("insufficient_260_sessions_count") == 17 and
         497+17 == 514, "OBSERVED_COHORT_COUNTS")
    must(type(snapshot.get("research_screen_rule")) is str
         and "NOT C4.17 exact R1/RR/stop model" in snapshot["research_screen_rule"],
         "NO_MANUAL_RULE_AS_POLICY")
    must(snapshot.get("source_artifact_paths") ==
         {"master":"nasdaq-xray/canonical_current_master_manifest.json",
          "price":"nasdaq-xray/canonical_current_price_dv30.json"},
         "SOURCE_PATHS_FROZEN")
    must(all(x.get("execution") == "NONE" and x.get("real_money") == "NO-GO"
             for x in (master,price,policy)), "POLICY_EXECUTION_DRIFT")
    must(master.get("unknown_never_pass") is True and
         price.get("unknown_never_pass") is True,
         "SOURCE_UNKNOWN_NEVER_PASS")
    must(policy.get("schema") == "XRAY_GITHUB_COMPILED_POLICY_V3" and
         policy.get("policy_hash") ==
         "68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4" and
         hashes["policy"] == "16c50cc8f887a5234a4be23862d7c8d0e564b0ac" and
         json.loads(policy.get("payload_json") or "{}").get("version") == "C4.17",
         "ALPHA_POLICY_UNCHANGED")
    master_syms,price_syms,unknown = (
        master.get("pass_symbols"),price.get("pass_symbols"),
        master.get("unknown_symbols"))
    must(all(valid_symbols(v) for v in (master_syms,price_syms,unknown)),
         "CANONICAL_SOURCE_SETS")
    must(master.get("pass_count") == len(master_syms) and
         master.get("queue_hash") == symbol_hash(master_syms) and
         master.get("unknown_count") == len(unknown) and
         not set(master_syms).intersection(unknown), "MASTER_SOURCE_INTEGRITY")
    must(price.get("pass_count") == len(price_syms) and
         price.get("pass_hash") == symbol_hash(price_syms) and
         price.get("source_master_queue_hash") == master.get("queue_hash") and
         set(price_syms).issubset(master_syms), "PRICE_SOURCE_INTEGRITY")
    pinned = snapshot.get("exact_source_blob_sha") or {}
    # The word 'current' means current COMPLETED EOD, not any live quote,
    # independently re-run history, C4.17 alpha, or automation entitlement.
    source_pinned = (pinned.get("master") == hashes["master"] and
                     pinned.get("price") == hashes["price"])
    same_asof = (snapshot["asof_et"] == master.get("asof_et") ==
                 price.get("asof_et") == last_complete_session(now_utc))
    eligible = source_pinned and same_asof
    if eligible:
        must(set(watches).issubset(price_syms) and
             set(watches).issubset(master_syms) and
             not set(watches).intersection(unknown),
             "WATCH_IDENTITY_PRICE_NOT_PASS")
        must(price.get("unknown_count") == 0 and
             price.get("blocked_count") == 0 and
             master.get("pass_count") == 3184 and
             price.get("pass_count") == 514, "ORIGINAL_COHORT_NOT_EXACT")
        for sym in watches:
            row=(price.get("results") or {}).get(sym) or {}
            must(row.get("status") == "PASS_PRICE_DV30" and
                 (row.get("info") or {}).get("compact_terminal_proof") is True,
                 "WATCH_PRICE_PASS_UNPROVEN:"+sym)
    return {
        "schema":"XRAY_MANUAL_SIP_WATCH_PROVENANCE_READBACK_V1",
        "snapshot_asof_et":snapshot["asof_et"],
        "latest_completed_session":last_complete_session(now_utc),
        "status":"EOD_MANUAL_TECH_WATCH_CURRENT_UNREPLAYED"
                 if eligible else "STALE_ARCHIVAL_SNAPSHOT_NOT_CURRENT",
        "canonical_master_price_exact":source_pinned,
        "same_asof_latest_completed":same_asof,
        "observed_watch_count":11,
        "current_eod_research_watch_count":11 if eligible else 0,
        "current_eod_research_watch":watches if eligible else [],
        "historical_only_watch":watches if not eligible else [],
        "observed_breakout_watch":a if eligible else [],
        "observed_near_high_watch":b if eligible else [],
        "asof_complete_history_symbols_observed":497,
        "asof_insufficient_history_symbols_observed":17,
        "close_crosschecks":11,
        "public_vendor_ohlcv_present":False,
        "live_provider_replay_or_licensing_attested":False,
        "technical_C417_AL_count":"UNVERIFIED",
        "not_a_buy_signal":True,
        "r92_registered":0,
        "candidate_delivery_performed":False,
        "full_go":False,
        "orders":[],
        "execution":"NONE",
        "real_money":"NO-GO",
        "unknown_never_pass":True,
        "snapshot_git_blob_sha":hashes["snapshot"],
        "source_git_blob_shas":hashes,
    }


def load(path):
    raw=path.read_bytes()
    return json.loads(raw),git_blob(raw)


def build(now_utc):
    s,ssha=load(SNAPSHOT)
    m,msha=load(MASTER)
    p,psha=load(PRICE)
    pol,phash=load(POLICY)
    return evaluate(s,m,p,pol,
                    {"snapshot":ssha,"master":msha,"price":psha,"policy":phash},
                    now_utc)


def selftest():
    snap,_=load(SNAPSHOT)
    watched=snap["watch_symbols"]
    price_syms=sorted(watched+["P%04d"%i for i in range(503)])
    master_syms=sorted(price_syms+["M%04d"%i for i in range(2670)])
    unknown=["U%04d"%i for i in range(12)]
    master={"pass_symbols":master_syms,"pass_count":3184,
            "queue_hash":symbol_hash(master_syms),
            "unknown_symbols":unknown,"unknown_count":12,
            "asof_et":"2026-10-09","execution":"NONE",
            "real_money":"NO-GO","unknown_never_pass":True}
    price={"pass_symbols":price_syms,"pass_count":514,
           "pass_hash":symbol_hash(price_syms),
           "source_master_queue_hash":master["queue_hash"],
           "unknown_count":0,"blocked_count":0,
           "asof_et":"2026-10-09","execution":"NONE","real_money":"NO-GO",
           "unknown_never_pass":True,
           "results":{k:{"status":"PASS_PRICE_DV30",
                        "info":{"compact_terminal_proof":True}} for k in watched}}
    pol={"schema":"XRAY_GITHUB_COMPILED_POLICY_V3",
         "policy_hash":"68684c130849016dd5148c1afdaa888766dc8070506af892420e493629a92fa4",
         "payload_json":json.dumps({"version":"C4.17"}),
         "execution":"NONE","real_money":"NO-GO"}
    hashes={"snapshot":"e"*40,"master":"a"*40,"price":"b"*40,
            "policy":"16c50cc8f887a5234a4be23862d7c8d0e564b0ac"}
    snap=copy.deepcopy(snap)
    snap["exact_source_blob_sha"]={"master":hashes["master"],"price":hashes["price"]}
    now=dt.datetime(2026,10,12,13,0,tzinfo=dt.timezone.utc)
    r=evaluate(snap,master,price,pol,hashes,now)
    must(r["current_eod_research_watch_count"]==11 and
         not r["full_go"] and not r["candidate_delivery_performed"] and
         not r["live_provider_replay_or_licensing_attested"],
         "TEST_POSITIVE")
    old=evaluate(snap,master,price,pol,hashes,
                 dt.datetime(2026,10,13,21,0,tzinfo=dt.timezone.utc))
    must(old["status"]=="STALE_ARCHIVAL_SNAPSHOT_NOT_CURRENT" and
         old["current_eod_research_watch_count"]==0 and
         old["current_eod_research_watch"]==[],
         "TEST_EXPIRATION")
    drift=copy.deepcopy(hashes);drift["price"]="f"*40
    old2=evaluate(snap,master,price,pol,drift,now)
    must(old2["current_eod_research_watch_count"]==0,
         "TEST_BLOB_BINDING")
    mutants=[
        lambda s,m,p,h:s.update(execution="LIVE"),
        lambda s,m,p,h:s.update(technical_al_confirmed=True),
        lambda s,m,p,h:s.update(runner_provider_rights_verified=True),
        lambda s,m,p,h:s.update(scope_price_dv30_pass=515),
        lambda s,m,p,h:s.update(close=10.2),
        lambda s,m,p,h:s["watch_symbols"].append("NOPE"),
        lambda s,m,p,h:s["watch_near20d_high"].append("PLTR"),
        lambda s,m,p,h:m["unknown_symbols"].append("PLTR"),
        lambda s,m,p,h:p["results"]["PLTR"].update(status="UNKNOWN"),
        lambda s,m,p,h:p.update(pass_hash="x"*64),
        lambda s,m,p,h:h.update(policy="f"*40),
        lambda s,m,p,h:s.update(eod_same_upstream_independence="PROVEN"),
    ]
    for i,fun in enumerate(mutants):
        s,m,p,h=(copy.deepcopy(snap),copy.deepcopy(master),
                 copy.deepcopy(price),copy.deepcopy(hashes))
        fun(s,m,p,h)
        try: evaluate(s,m,p,pol,h,now)
        except ValueError: pass
        else: raise RuntimeError("UNSAFE_WATCH_MUTATION_ACCEPTED:"+str(i))
    print("XRAY_INTERACTIVE_SIP_WATCH_SELFTEST=PASS_3_POSITIVE_12_NEGATIVE_PYTHON_O_SAFE")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    if not args.out or args.out.resolve().is_relative_to(ROOT.parent):
        ap.error("out must be outside git repository (private runner path)")
    report=build(dt.datetime.now(dt.timezone.utc))
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("XRAY_INTERACTIVE_SIP_WATCH="+report["status"])
    print("XRAY_INTERACTIVE_SIP_WATCH_COUNT="+str(report["current_eod_research_watch_count"]))
    print("XRAY_C417_AL=UNVERIFIED_NOT_ASSUMED_ZERO")
    print("XRAY_SIP_WATCH_RUNNER_LICENSE=NOT_ATTESTED")


if __name__=="__main__":
    main()
