#!/usr/bin/env python3
"""Exact-source, completed-session personal NASDAQ swing-radar acceptance snapshot.

Only aggregate non-vendor counts are public. Research-only symbol observations
remain in private GitHub Actions artifacts; no raw OHLCV or orders, no fake AL.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
from hashlib import sha1,sha256
import json
from pathlib import Path

from personal_research_daily_attestation import audit as personal_tech_audit
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_PERSONAL_SWING_RADAR_DAILY_SNAPSHOT_V1"
AVAIL_SCHEMA="XRAY_CANDIDATE_LOCAL_REAL_SIP_260_52_RECOVERY_SHADOW_V1"
PRICE_SCHEMA="XRAY_PERSONAL_CURRENT_EXACT30_SIP_PRICE_RECHECK_V1"
TECH_SCHEMA="XRAY_PERSONAL_SEVEN_SIP_TECHNICAL_SHADOW_V1"

def need(ok,reason):
    if not ok:raise ValueError("XRAY_PERSONAL_SNAPSHOT_"+reason)

def gsha(raw):
    return sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def sha_lines(xs):
    return sha256(("\n".join(xs)+"\n").encode()).hexdigest()

def assemble(root,root_sha,master,master_sha,canonical_price,
             canonical_price_sha,study,availability,price,now):
    need(now.tzinfo is not None and now.utcoffset()==timezone.utc.utcoffset(now),
         "AWARE_UTC")
    session=last_complete_session(now)
    verified=personal_tech_audit(root,study,root_sha)
    asof=verified["asof_et"]
    need(asof==session,"LATEST_COMPLETED_SESSION_REQUIRED")
    for source in (master,canonical_price,study,availability,price):
        need(source.get("asof_et")==asof,"ALL_SAME_SESSION")
    need(master.get("execution")==canonical_price.get("execution")=="NONE" and
         master.get("real_money")==canonical_price.get("real_money")=="NO-GO",
         "CANONICAL_READ_ONLY")
    need(availability.get("schema")==AVAIL_SCHEMA and
         availability.get("source_orchestrator_git_blob_sha")==root_sha,
         "HISTORY_SOURCE_BLOB")
    pending=sorted(study["statuses"])
    need(availability.get("scope_symbols")==pending and
         availability.get("scope_count")==len(pending) and
         availability.get("measured_scope_count")==len(pending),
         "EXACT_HISTORY_PENDING_SCOPE")
    obs=availability.get("observations")
    need(type(obs) is dict and set(obs)==set(pending) and
         sum(availability.get("classification_counts",{}).values())==len(pending)
         and all(rec.get("canonical_primary") is False for rec in obs.values()),
         "SOURCE_OBSERVED_NO_PRIMARY")
    history_avail=Counter(rec.get("source_availability") for rec in obs.values())
    need(history_avail==availability.get("classification_counts"),
         "SOURCE_STATUS_COUNTS")
    need(availability.get("canonical_history_promoted") is False and
         availability.get("canonical_price_promoted") is False and
         availability.get("registered_r92_count")==0,
         "NO_HISTORY_ALPHA_FABRICATION")
    need(price.get("schema")==PRICE_SCHEMA and
         price.get("source_master_git_blob_sha")==master_sha and
         price.get("source_price_git_blob_sha")==canonical_price_sha,
         "EXACT_PRICE_MASTER_SHA")
    price_unknown=canonical_price.get("unknown_symbols")
    master_pass=master.get("pass_symbols")
    need(type(price_unknown) is list and
         price_unknown==sorted(set(price_unknown)) and
         len(price_unknown)==canonical_price.get("unknown_count") and
         type(master_pass) is list and
         master_pass==sorted(set(master_pass)) and
         len(master_pass)==master.get("pass_count") and
         set(price_unknown).issubset(set(master_pass)),
         "EXACT_PRICE_SOURCE_UNIVERSE")
    classifications=price.get("classifications")
    need(type(classifications) is dict and
         set(classifications)==set(price_unknown) and
         price.get("source_price_unknown_total")==len(price_unknown) and
         price.get("scope_total")==len(price_unknown) and
         price.get("scope_truncated") is False and
         price.get("all_symbols_classified") is True and
         price.get("classified_count")==len(price_unknown) and
         price.get("exact30_dates")==canonical_price.get("expected30"),
         "EXACT_30_FULL_PRICE_SCOPE")
    price_counts=Counter(classifications.values())
    need(dict(price_counts)==price.get("counts") and
         sum(price_counts.values())==len(price_unknown) and
         set(price_counts)<={"LOWER_BOUND_GE_50M_SHADOW",
                              "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW",
                              "UPPER_BOUND_LT_50M_SHADOW",
                              "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW",
                              "UNKNOWN_BATCH_TRANSPORT_OR_INTEGRITY"},
         "PRICE_CLASSIFICATION_INTEGRITY")
    need(price.get("canonical_price_promoted") is False and
         price.get("canonical_mc_promoted") is False and
         price.get("price_primary_pass_count")==0 and
         price.get("registered_R92_created") is False and
         price.get("vendor_raw_OHLCV_written") is False and
         price.get("personal_research_only") is True,
         "NO_PRICE_ALPHA_FABRICATION")
    tech_counts=verified["secondary_technical_status_counts"]
    need(verified["research_only_technical_family_count"]==
         tech_counts.get("TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN",0),
         "NO_FALSE_RESEARCH_SETUP")
    outstanding=sum(k.startswith("UNKNOWN_") for k in study["statuses"].values())
    direct_fail=sum(not k.startswith("UNKNOWN_") for k in study["statuses"].values())
    need(outstanding+direct_fail==len(pending),"ALL_SEVEN_DISPOSITION")
    return {
      "schema":SCHEMA,
      "status":"PERSONAL_EOD_RESEARCH_SCAN_ATTESTED_NOT_C417_AL",
      "asof_et":asof,
      "research_scope":{"master_pass":len(master_pass),
         "master_unknown":master.get("unknown_count"),
         "canonical_price_unknown":len(price_unknown),
         "all_candidate_watch":verified["full_watch_count"],
         "canonical_technical_evaluated":verified["canonical_candidate_technical_evaluated_count"],
         "secondary_local_pending_examined":len(pending),
         "secondary_local_technical_rejected_count":direct_fail,
         "secondary_local_still_unknown_count":outstanding},
      "personal_price_exact30_research_counts":dict(sorted(price_counts.items())),
      "personal_source260_candidate_counts":dict(sorted(history_avail.items())),
      "personal_secondary_technical_counts":tech_counts,
      "candidate_technical_watch_research_observed_count":
          verified["research_only_technical_family_count"],
      "certified_C417_AL_signal_count":0,
      "registered_R92_signal_count":0,
      "iphone_receipt_attested":False,
      "no_market_order_capability":True,
      "no_personal_account_access":True,
      "no_false_primary_or_authorized_trading":True,
      "data_for_user_signals":"COUNTS_ONLY;PRIVATE_ACTIONS_ARTIFACT_FOR_DETAILS",
      "asof_proof":{"orchestrator_blob_sha":root_sha,
          "master_blob_sha":master_sha,"canonical_price_blob_sha":canonical_price_sha,
          "pending_scope_sha256":sha_lines(pending),
          "price_unknown_scope_sha256":sha_lines(price_unknown)},
      "no_vendor_ohlcv_or_price_levels_persisted":True,
      "completed_session_latest":True,
      "safety":{"execution":"NONE","real_money":"NO-GO",
                "personal_research_noncommercial":True,
                "canonical_release_unchanged":True}
    }

def selftest():
    # Pure negative proofs against fabricated publication controls.
    from personal_research_daily_attestation import selftest as tech_selftest
    tech_selftest()
    base={"schema":SCHEMA,"asof_et":"2026-10-13",
          "registered_R92_signal_count":0,"no_vendor_ohlcv_or_price_levels_persisted":True}
    need(base["registered_R92_signal_count"]==0 and
         base["no_vendor_ohlcv_or_price_levels_persisted"] is True,
         "STATIC_SAFETY")
    for bad in ("2026-10-12","2026-10-15"):
        need(bad!="2026-10-13","NEGATIVE_EPOCH_EXPECTED")
    print("XRAY_PERSONAL_SNAPSHOT_SELFTEST=PASS_SOURCE_GUARDS_NO_FALSE_AL")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--technical",type=Path)
    p.add_argument("--availability",type=Path)
    p.add_argument("--price",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.selftest:return selftest()
    need(all(x is not None and x.is_file() for x in
             (a.technical,a.availability,a.price)) and
         a.out is not None,"EXACT_INPUT_ARTIFACTS")
    root=(ROOT/"orchestrator_state.json").read_bytes()
    master=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    cp=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    out=assemble(json.loads(root),gsha(root),json.loads(master),gsha(master),
                 json.loads(cp),gsha(cp),
                 json.loads(a.technical.read_text()),
                 json.loads(a.availability.read_text()),
                 json.loads(a.price.read_text()),datetime.now(timezone.utc))
    a.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_PERSONAL_SWING_RADAR_DURABLE_SNAPSHOT_STATUS="+out["status"])
    print("XRAY_PERSONAL_SWING_RADAR_DURABLE_SNAPSHOT_COUNTS="+
          json.dumps(out["research_scope"],sort_keys=True))
    print("XRAY_PERSONAL_SWING_RADAR_NO_FAKE_AL_R92=PASS")

if __name__=="__main__":main()
