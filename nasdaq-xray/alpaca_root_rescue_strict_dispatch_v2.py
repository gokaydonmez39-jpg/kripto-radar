#!/usr/bin/env python3
"""Fail-closed entrypoint for Alpaca root-UNKNOWN research source.

Every row is evaluated under the independent exact official NASDAQ last-30
session requirement. This wrapper has no PRIMARY, AL or trading authority.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

import alpaca_root_unknown_rescue_shadow as legacy
import alpaca_strict_daily_shadow_v2 as strict
from alpaca_official_30_workflow_preflight import validate
from history_transport_cache_guard import official_completed_sessions
from source_epoch_freshness_guard import last_complete_session

ROOT=Path(__file__).resolve().parent

# A PRICE-PASS sample cannot be a prerequisite for independent ROOT UNKNOWN
# source diagnostics: this creates a zero-PASS bootstrap deadlock.
BLOCKED_PRICE="BLOCKED_NO_REPRESENTATIVE_CURRENT_PRICE_SCOPE"
MEASURED_PRICE="SHADOW_MEASUREMENT_COMPLETED_NO_PRIMARY_AUTHORITY"

def scheduled_probe_allowed(now,latest,price,root,remote_sha,expected_sha):
    """Strict pure predicate: stale/holiday/SHA/empty cohort cannot use provider quota."""
    if not isinstance(now,dt.datetime) or now.tzinfo is None or now.utcoffset()!=dt.timedelta(0):
        return False
    if not isinstance(price,dict) or not isinstance(root,dict):
        return False
    if not isinstance(remote_sha,str) or not isinstance(expected_sha,str):
        return False
    return bool(now.date().isoformat()==latest
        and price.get("asof_et")==root.get("asof_et")==latest
        and price.get("unknown_never_pass") is True
        and price.get("execution")=="NONE" and price.get("real_money")=="NO-GO"
        and root.get("execution")=="NONE" and root.get("real_money")=="NO-GO"
        and type(root.get("unknown_count")) is int and root.get("unknown_count")>0
        and len(remote_sha)==40 and len(expected_sha)==40 and remote_sha==expected_sha)

def classify_manual_root(event, price, root, *, scheduled_ready=False):
    if event not in ("push","workflow_dispatch","schedule"):
        raise ValueError("UNAUTHORIZED_ROOT_EVENT")
    if price.get("schema")!="XRAY_ALPACA_FREE_SIP_SHADOW_GUARD_V1":
        raise ValueError("PRICE_SHADOW_SCHEMA")
    if price.get("status") not in (BLOCKED_PRICE,MEASURED_PRICE):
        raise ValueError("PRICE_SHADOW_STATUS")
    for evidence in (price,root) if root is not None else (price,):
        if any((evidence.get("execution")!="NONE",
                evidence.get("real_money")!="NO-GO",
                evidence.get("candidate_created") is not False,
                evidence.get("vendor_raw_bars_persisted") is not False,
                evidence.get("primary_mc_authority") is not False)):
            raise ValueError("SHADOW_SAFETY_OR_AUTHORITY")
    if price["status"]==BLOCKED_PRICE and not (
            price.get("sample_count",3)<3 and
            price.get("reason_counts")=={"NO_REPRESENTATIVE_CURRENT_PRICE_SCOPE":1}
            and price.get("c417_price_pass_promoted") is False):
        raise ValueError("BLOCKED_PRICE_SCOPE_PROOF")
    if event=="push":
        if root is not None:raise ValueError("ROOT_VENDOR_ON_AUTOMATIC_PUSH")
        return "PUSH_PRICE_ONLY_OR_ZERO_SCOPE_NO_ROOT"
    if event=="schedule" and not scheduled_ready:
        if root is not None:raise ValueError("STALE_SCHEDULE_ROOT_VENDOR_RESULT")
        return "SCHEDULE_STALE_OR_UNSETTLED_QUOTA_FREE_NOOP"
    if event=="schedule" and scheduled_ready and root is None:
        raise ValueError("SCHEDULE_READY_WITHOUT_ROOT_PROOF")
    if (not isinstance(root,dict) or
        root.get("schema")!="XRAY_ROOT_UNKNOWN_SIP_RESCUE_SHADOW_V1" or
        root.get("status")!="SHADOW_HISTORICAL_SOURCE_DIAGNOSTIC_COMPLETE" or
        root.get("canonical_history_modified") is not False or
        root.get("asof_et")!=price.get("asof_et") or
        root.get("price_git_blob_sha")!=price.get("price_git_blob_sha")):
        raise ValueError("MANUAL_ROOT_EXACT_WITNESS_REQUIRED")
    if event=="schedule":
        return "SCHEDULE_EXACT_ASOF_BOUNDED_ROOT_SHADOW_ONLY"
    return ("MANUAL_ZERO_PRICE_ROOT_SHADOW_ONLY" if
            price["status"]==BLOCKED_PRICE else "MANUAL_PRICE_AND_ROOT_SHADOW_ONLY")

def selftest():
    asof="2026-10-08"
    all_dates=sorted(official_completed_sessions(asof))
    canonical=all_dates[-30:]
    fake=[all_dates[-31],*canonical[1:]]
    now=dt.datetime(2026,10,9,14,tzinfo=dt.timezone.utc)
    def mk(day):
        t=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(0),strict.legacy.EST)
        return {"t":t.astimezone(dt.timezone.utc).isoformat(),
                "o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":1000}
    original=legacy.sip.evaluate_daily
    legacy.sip.evaluate_daily=strict.evaluate_daily_strict
    try:
        neg=legacy.study(["UNIT"],asof,fake,{"UNIT":[mk(x) for x in fake]},now)
        assert neg=={"UNKNOWN_OFFICIAL_NASDAQ_30_CALENDAR_REQUIRED":1},neg
        positive=legacy.study(["UNIT"],asof,canonical,{"UNIT":[mk(x) for x in canonical]},now)
        assert positive=={"UNKNOWN_LT260_OR_52_WEEKS":1},positive
    finally:
        legacy.sip.evaluate_daily=original
    scheduled_now=dt.datetime(2026,10,19,22,10,tzinfo=dt.timezone.utc)
    scheduled_asof=last_complete_session(scheduled_now)
    assert scheduled_asof=="2026-10-19","EXPECTED_NASDAQ_COMPLETED_DAY"
    sp={"asof_et":scheduled_asof,"unknown_never_pass":True,
        "execution":"NONE","real_money":"NO-GO"}
    sr={"asof_et":scheduled_asof,"unknown_count":214,
        "execution":"NONE","real_money":"NO-GO"}
    sha="a"*40
    assert scheduled_probe_allowed(scheduled_now,scheduled_asof,sp,sr,sha,sha)
    # Real scheduled run #39351414911: 01:17 UTC on Oct 20 is still
    # 21:17 Oct 19 New York; UTC rollover cannot invalidate source ASOF.
    delayed=dt.datetime(2026,10,20,1,17,tzinfo=dt.timezone.utc)
    assert last_complete_session(delayed)==scheduled_asof
    if not scheduled_probe_allowed(delayed,scheduled_asof,sp,sr,sha,sha):
        raise RuntimeError("VALID_NASDAQ_SESSION_REJECTED_BY_UTC_DATE_ROLLOVER")
    ny_next_day=dt.datetime(2026,10,20,4,1,tzinfo=dt.timezone.utc)
    if scheduled_probe_allowed(ny_next_day,scheduled_asof,sp,sr,sha,sha):
        raise RuntimeError("STALE_NEW_YORK_SOURCE_SESSION_ADMITTED")
    holiday=dt.datetime(2026,11,26,22,10,tzinfo=dt.timezone.utc)
    h_asof=last_complete_session(holiday)
    assert h_asof=="2026-11-25","HOLIDAY_FRESHNESS_SOURCE"
    for edits in (
        {"now":holiday,"latest":h_asof},
        {"now":dt.datetime(2026,10,19,22,10)},
        {"price":dict(sp,asof_et="2026-10-16")},
        {"root":dict(sr,asof_et="2026-10-16")},
        {"root":dict(sr,unknown_count=0)},
        {"root":dict(sr,unknown_count="214")},
        {"root":dict(sr,execution="ORDER")},
        {"price":dict(sp,unknown_never_pass=False)},
        {"remote_sha":"b"*40},
        {"expected_sha":""},
    ):
        args={"now":scheduled_now,"latest":scheduled_asof,
            "price":sp,"root":sr,"remote_sha":sha,"expected_sha":sha}
        args.update(edits)
        assert not scheduled_probe_allowed(**args),("SCHEDULE_FALSE_POSITIVE",edits)
    px={"schema":"XRAY_ALPACA_FREE_SIP_SHADOW_GUARD_V1",
        "status":BLOCKED_PRICE,"sample_count":0,
        "reason_counts":{"NO_REPRESENTATIVE_CURRENT_PRICE_SCOPE":1},
        "c417_price_pass_promoted":False,"asof_et":"2026-10-16",
        "price_git_blob_sha":"a"*40,"execution":"NONE","real_money":"NO-GO",
        "candidate_created":False,"vendor_raw_bars_persisted":False,
        "primary_mc_authority":False}
    root={"schema":"XRAY_ROOT_UNKNOWN_SIP_RESCUE_SHADOW_V1",
        "status":"SHADOW_HISTORICAL_SOURCE_DIAGNOSTIC_COMPLETE",
        "asof_et":"2026-10-16","price_git_blob_sha":"a"*40,
        "execution":"NONE","real_money":"NO-GO",
        "candidate_created":False,"vendor_raw_bars_persisted":False,
        "primary_mc_authority":False,"canonical_history_modified":False}
    assert classify_manual_root("push",px,None).startswith("PUSH_")
    assert classify_manual_root("schedule",px,None)=="SCHEDULE_STALE_OR_UNSETTLED_QUOTA_FREE_NOOP"
    assert classify_manual_root("schedule",px,root,scheduled_ready=True)==("SCHEDULE_EXACT_ASOF_BOUNDED_ROOT_SHADOW_ONLY")
    assert classify_manual_root("workflow_dispatch",px,root)==(
        "MANUAL_ZERO_PRICE_ROOT_SHADOW_ONLY")
    assert classify_manual_root("workflow_dispatch",
        dict(px,status=MEASURED_PRICE),root)=="MANUAL_PRICE_AND_ROOT_SHADOW_ONLY"
    for event,p,q in (
        ("push",px,root),("pull_request",px,root),
        ("schedule",px,root),
        ("workflow_dispatch",px,None),
        ("workflow_dispatch",px,dict(root,status="BLOCKED")),
        ("workflow_dispatch",px,dict(root,price_git_blob_sha="b"*40)),
        ("workflow_dispatch",px,dict(root,canonical_history_modified=True)),
        ("workflow_dispatch",px,dict(root,primary_mc_authority=True)),
        ("workflow_dispatch",dict(px,reason_counts={}),root),
    ):
        try:classify_manual_root(event,p,q)
        except ValueError:pass
        else:raise RuntimeError("UNSAFE_ROOT_DIAGNOSTIC_ACCEPTED")
    for bad_price,bad_root in (
        (dict(px,real_money="YES"),root),
        (px,dict(root,status="BLOCKED")),
        (px,dict(root,price_git_blob_sha="b"*40)),
        (px,dict(root,canonical_history_modified=True)),
        (px,dict(root,primary_mc_authority=True)),
    ):
        try: classify_manual_root("schedule",bad_price,bad_root,scheduled_ready=True)
        except ValueError: pass
        else: raise RuntimeError("SCHEDULE_INVALID_SOURCE_ACCEPTED")
    for ready,invalid in ((True,None),(False,root)):
        try: classify_manual_root("schedule",px,invalid,scheduled_ready=ready)
        except ValueError: pass
        else: raise RuntimeError("SCHEDULE_READY_MISSING_OR_STALE_VENDOR_ACCEPTED")
    workflow=(ROOT.parent/".github"/"workflows"/
              "xray-alpaca-free-sip-shadow-proof.yml").read_text()
    assert 'cron: "10 22 * * 1-5"' in workflow
    assert "last_complete_session(now)" in workflow
    assert 'scheduled_probe_allowed(now,latest,p,s,remote,os.environ["GITHUB_SHA"])' in workflow
    assert "steps.scheduled_root.outputs.ready == 'true'" in workflow
    assert "--limit 12 --output" in workflow
    print("XRAY_SCHEDULED_ROOT_ELIGIBILITY=PASS_ONE_TRUE_TEN_FALSE_NO_HTTP")
    print("XRAY_ZERO_PRICE_ROOT_RESCUE=PASS_SCHEDULE_BOUNDED_AND_MANUAL_NEGATIVES_NO_ALPHA")
    print("XRAY_ALPACA_ROOT_STRICT_DISPATCH_V2=PASS_FAKE_CALENDAR_BLOCKED_REAL_CALENDAR_SHORT_UNKNOWN")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--offset",type=int,default=0)
    ap.add_argument("--limit",type=int,default=12)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    root_state=json.loads((ROOT/"sina_state.json").read_text(encoding="utf-8"))
    price=json.loads((ROOT/"canonical_current_price_dv30.json").read_text(encoding="utf-8"))
    if (root_state.get("asof_et")!=price.get("asof_et")
            or validate(price.get("asof_et"),price.get("expected30"))!="EXACT_OFFICIAL_NASDAQ_LAST_30"):
        raise SystemExit("XRAY_ALPACA_ROOT_STRICT_CALENDAR=BLOCKED")
    if price.get("asof_et")!=last_complete_session(dt.datetime.now(dt.timezone.utc)):
        raise SystemExit("XRAY_ROOT_ASOF_STALE_NO_VENDOR")
    original=legacy.sip.evaluate_daily
    legacy.sip.evaluate_daily=strict.evaluate_daily_strict
    try:
        result=legacy.run(args.offset,args.limit)
    finally:
        legacy.sip.evaluate_daily=original
    assert result["primary_mc_authority"] is False
    assert result["canonical_history_modified"] is False
    assert result["candidate_created"] is False
    assert result["vendor_raw_bars_persisted"] is False
    assert result["execution"]=="NONE" and result["real_money"]=="NO-GO"
    if args.output:
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("XRAY_ALPACA_ROOT_STRICT_DISPATCH_STATUS="+result["status"])

if __name__=="__main__":
    main()
