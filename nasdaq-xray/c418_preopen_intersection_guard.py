#!/usr/bin/env python3
"""C4.18 provenance-bound SEC / Alpaca 260x52 intersection, advisory ONLY.

Consumes two existing SANITIZED private Actions witnesses; no provider calls,
no raw OHLCV or share counts, no market-cap calculation, no PRIMARY, R92, GO
or trade. A matched transport/shares cohort never proves vendor rights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
SCHEMA="XRAY_C418_PREOPEN_EXACT_PARTITION_SHADOW_V1"
SUCCESS="SHADOW_260_DAILY_52_WEEK_OBSERVED"
SEC_VINTAGE="SHADOW_SHARES_VINTAGE_ONLY"

def _sha(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def _digest(items)->str:
    """Canonical PRICE hashes do NOT include a trailing newline."""
    return hashlib.sha256("\n".join(sorted(items)).encode()).hexdigest()

def _sec_digest(items)->str:
    """SEC batch-scoped SHA uses exactly one trailing newline."""
    return hashlib.sha256(("\n".join(sorted(items))+"\n").encode()).hexdigest()

def audit(price,master,alpaca,sec,price_sha,master_sha):
    """Set equality, blob equality and source safety; never count-only joins."""
    if not all(isinstance(x,dict) for x in (price,master,alpaca,sec)):
        raise ValueError("MALFORMED_SOURCE")
    asof=price.get("asof_et")
    names=price.get("pass_symbols")
    parent=master.get("pass_symbols")
    if (not isinstance(asof,str) or asof!=master.get("asof_et")
        or not isinstance(names,list) or not names
        or names!=sorted(set(names)) or price.get("pass_count")!=len(names)
        or price.get("pass_hash")!=_digest(names)
        or not isinstance(parent,list) or len(parent)!=len(set(parent))
        or not set(names).issubset(set(parent))
        or "QQQ" in names):
        raise ValueError("CANONICAL_PRICE_IDENTITY_SCOPE_INVALID")
    for x in (price,master,alpaca,sec):
        if x.get("execution")!="NONE" or x.get("real_money")!="NO-GO":
            raise ValueError("SOURCE_EXECUTION_SAFETY_DRIFT")
    if (alpaca.get("schema")!="XRAY_ALPACA_CURRENT_515_EXACT260_SIP_SHADOW_V1"
        or alpaca.get("asof_et")!=asof
        or alpaca.get("source_price_blob_sha")!=price_sha
        or alpaca.get("source_master_blob_sha")!=master_sha
        or alpaca.get("source_price_pass_hash")!=price.get("pass_hash")
        or alpaca.get("price_pass_count")!=len(names)
        or alpaca.get("expected_scope_count")!=len(names)+1
        or alpaca.get("measured_scope_count")!=len(names)+1
        or alpaca.get("status")!="SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY"
        or alpaca.get("api_feed")!="sip"
        or alpaca.get("api_timeframe")!="1Day"
        or alpaca.get("api_adjustment")!="raw"
        or alpaca.get("expected_daily_sessions")!=260
        or alpaca.get("required_completed_week_closes")!=52
        or alpaca.get("transport_error_class") is not None
        or alpaca.get("current_c417_history_primary_authority") is not False
        or alpaca.get("source_market_data_rights_independently_attested") is not False
        or alpaca.get("corporate_action_adjustment_and_share_class_attested") is not False
        or alpaca.get("vendor_ohlcv_in_artifact") is not False
        or alpaca.get("vendor_raw_bars_persisted") is not False
        or alpaca.get("r92_created") is not False):
        raise ValueError("ALPACA_SHADOW_SOURCE_OR_RIGHTS_INVALID")
    counts=alpaca.get("counts")
    missing=alpaca.get("unverified_symbols")
    if (not isinstance(counts,dict) or not isinstance(missing,dict)
        or sum(counts.values())!=len(names)+1
        or counts.get("UNCHECKED_DUE_TO_TRANSPORT",0)!=0
        or len(missing)!=len(names)+1-counts.get(SUCCESS,0)
        or not set(missing).issubset(set(names))
        or any(value==SUCCESS for value in missing.values())):
        raise ValueError("ALPACA_INCOMPLETE_OR_FALSE_COUNTS")
    if (sec.get("schema")!="XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1"
        or sec.get("asof_et")!=asof
        or sec.get("master_git_blob_sha")!=master_sha
        or sec.get("price_git_blob_sha")!=price_sha
        or sec.get("sample_scope_sha256")!=_sec_digest(names)
        or sec.get("sample_count")!=len(names)
        or sec.get("batch_offset")!=0
        or sec.get("batch_limit")!=len(names)
        or sec.get("c417_primary_mc_count")!=0
        or sec.get("market_cap_calculated") is not False
        or sec.get("production_alpha_authority") is not False
        or sec.get("price_binding_attested") is not False
        or sec.get("corporate_action_binding_attested") is not False):
        raise ValueError("SEC_SHADOW_SOURCE_OR_AUTHORITY_INVALID")
    statuses=sec.get("statuses")
    reasons=sec.get("reason_codes")
    if (not isinstance(statuses,dict) or set(statuses)!=set(names)
        or not isinstance(reasons,dict) or set(reasons)!=set(names)
        or dict(Counter(statuses.values()))!=sec.get("status_counts")):
        raise ValueError("SEC_STATUS_NOT_EXACT_FULL_SET")
    price_set=set(names)
    short=set(missing)
    observed=price_set-short
    vintage={s for s,v in statuses.items() if v==SEC_VINTAGE}
    joint=observed&vintage
    mc_unknown=observed-vintage
    if (joint&mc_unknown or joint&short or mc_unknown&short
        or joint|mc_unknown|short!=price_set):
        raise ValueError("INEXACT_SET_PARTITION")
    return {
       "schema":SCHEMA, "asof_et":asof,
       "source_price_blob_sha":price_sha,"source_master_blob_sha":master_sha,
       "price_pass_scope":len(names),"alpaca_including_qqq":len(names)+1,
       "history_shadow_numeric_complete":len(observed),
       "sec_shares_vintage_shadow":len(vintage),
       "technical_intersection":len(joint),
       "history_observed_sec_unknown":len(mc_unknown),
       "history_short_in_price_pass":len(short),
       "history_short_sec_vintage":len(short&vintage),
       "history_short_sec_unknown":len(short-vintage),
       "technical_intersection_sha256":_digest(joint),
       "unproven_mc_cohort_sha256":_digest(mc_unknown),
       "history_short_sha256":_digest(short),
       "status":"EXACT_RESEARCH_PARTITION_ONLY",
       "source_legal_authority":False,"production_authority":False,
       "can_create_PRIMARY":False,"can_create_HISTORY_PASS":False,
       "can_register_R92":False,"real_money":"NO-GO",
       "execution":"NONE","unknown_never_pass":True,
       "vendor_raw_bars_exported":False,"raw_share_counts_exported":False,
    }

def selftest():
    symbols=["A","B","C"]
    p={"asof_et":"2026-10-09","pass_symbols":symbols,"pass_count":3,
       "pass_hash":_digest(symbols),"execution":"NONE","real_money":"NO-GO"}
    m={"asof_et":"2026-10-09","pass_symbols":symbols+["D"],
       "execution":"NONE","real_money":"NO-GO"}
    a={"schema":"XRAY_ALPACA_CURRENT_515_EXACT260_SIP_SHADOW_V1",
       "asof_et":"2026-10-09","source_price_blob_sha":"a"*40,
       "source_master_blob_sha":"b"*40,"source_price_pass_hash":p["pass_hash"],
       "price_pass_count":3,"expected_scope_count":4,"measured_scope_count":4,
       "status":"SHADOW_FULL_515_SCOPE_MEASURED_NO_AUTHORITY",
       "api_feed":"sip","api_timeframe":"1Day","api_adjustment":"raw",
       "expected_daily_sessions":260,"required_completed_week_closes":52,
       "transport_error_class":None,"current_c417_history_primary_authority":False,
       "source_market_data_rights_independently_attested":False,
       "corporate_action_adjustment_and_share_class_attested":False,
       "vendor_ohlcv_in_artifact":False,"vendor_raw_bars_persisted":False,
       "r92_created":False,"counts":{SUCCESS:3,"MISSING_EXACT_COMPLETED_SESSIONS":1,
                               "UNCHECKED_DUE_TO_TRANSPORT":0},
       "unverified_symbols":{"C":"MISSING_EXACT_COMPLETED_SESSIONS"},
       "execution":"NONE","real_money":"NO-GO"}
    t={"schema":"XRAY_SEC_MULTISYMBOL_PIT_SHADOW_V1",
       "asof_et":"2026-10-09","master_git_blob_sha":"b"*40,
       "price_git_blob_sha":"a"*40,"sample_scope_sha256":_sec_digest(symbols),
       "sample_count":3,"batch_limit":3,"batch_offset":0,
       "c417_primary_mc_count":0,"market_cap_calculated":False,
       "production_alpha_authority":False,"price_binding_attested":False,
       "corporate_action_binding_attested":False,
       "statuses":{"A":SEC_VINTAGE,"B":"UNKNOWN","C":SEC_VINTAGE},
       "reason_codes":{"A":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED",
                       "B":"NO_SEC_DEI_OR_GAAP_SHARES_FACT",
                       "C":"SHARE_CLASS_CORP_ACTION_AND_PIT_PRICE_STILL_REQUIRED"},
       "status_counts":{SEC_VINTAGE:2,"UNKNOWN":1},
       "execution":"NONE","real_money":"NO-GO"}
    from copy import deepcopy
    assert _digest(symbols)!=_sec_digest(symbols)
    out=audit(p,m,a,t,"a"*40,"b"*40)
    assert (out["technical_intersection"],out["history_observed_sec_unknown"],
            out["history_short_in_price_pass"])==(1,1,1)
    assert not out["can_create_PRIMARY"] and not out["can_register_R92"]
    for key,group,value in (
        ("pass_count",p,4),
        ("source_master_blob_sha",a,"0"*40),
        ("expected_scope_count",a,3),
        ("vendor_raw_bars_persisted",a,True),
        ("source_market_data_rights_independently_attested",a,True),
        ("sample_scope_sha256",t,"0"*64),
        ("c417_primary_mc_count",t,1),
        ("batch_limit",t,2)):
        pp,mm,aa,tt=(deepcopy(p),deepcopy(m),deepcopy(a),deepcopy(t))
        obj=pp if group is p else aa if group is a else tt
        obj[key]=value
        try:audit(pp,mm,aa,tt,"a"*40,"b"*40)
        except ValueError:pass
        else:raise AssertionError("PARTITION_NEGATIVE_FALSE_PASS_"+key)
    print("XRAY_C418_EXACT_341_PARTITION_SELFTEST=PASS_SET_SHA_NEGATIVES_NO_PRIMARY")

def main():
    x=argparse.ArgumentParser()
    x.add_argument("--selftest",action="store_true")
    x.add_argument("--private-alpaca",type=Path)
    x.add_argument("--private-sec",type=Path)
    x.add_argument("--out",type=Path)
    args=x.parse_args()
    if args.selftest:selftest();return
    if not args.private_alpaca or not args.private_sec or not args.out:
        raise SystemExit("XRAY_C418_PARTITION=BLOCKED_PRIVATE_SOURCES_REQUIRED")
    if any(p.resolve().is_relative_to(REPO.resolve())
           for p in (args.private_alpaca,args.private_sec,args.out)):
        raise SystemExit("XRAY_C418_PARTITION=BLOCKED_PRIVATE_FILES_INSIDE_REPO")
    from source_epoch_freshness_guard import last_complete_session
    if last_complete_session(datetime.now(timezone.utc))!=json.loads(
        (ROOT/"canonical_current_price_dv30.json").read_text())["asof_et"]:
        raise SystemExit("XRAY_C418_PARTITION=BLOCKED_STALE_CURRENT_ASOF")
    pb=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    mb=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    res=audit(json.loads(pb),json.loads(mb),
              json.loads(args.private_alpaca.read_text()),
              json.loads(args.private_sec.read_text()),_sha(pb),_sha(mb))
    args.out.write_text(json.dumps(res,sort_keys=True)+"\n")
    print("XRAY_C418_RESEARCH_PRIORITY="+str(res["technical_intersection"]))
    print("XRAY_C418_PARTITION_AUTHORITY=SHADOW_ONLY_NO_MC_NO_R92")
    raise SystemExit(2)

if __name__=="__main__":
    main()
