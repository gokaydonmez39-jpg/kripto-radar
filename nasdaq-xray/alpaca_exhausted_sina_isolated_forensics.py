#!/usr/bin/env python3
"""Bounded symbol-local SIP research diagnostics for exhausted Sina exceptions.

The independent 260/52 census can distinguish source-observed from missing,
but its INVALID_OHLCV_OR_ZERO_VOLUME class conflates different repairs.
This follow-on fetches the exact exhausted cohort in bounded batches, then
remeasures only deficient symbols one by one. No market rows, symbol identity,
dates of missing bars, provider errors or API credentials leave process memory.
Neither a second read of the same vendor nor valid daily bars confer PRIMARY
authority, split continuity, rights, R92 or permission to place orders.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path

from alpaca_exhausted_sina_260_shadow import (
    ROOT, SINA, MASTER, BATCH, MAX_ELIGIBLE, OBSERVED, ALLOWED,
    cohort, need, PAGER_MAX_PAGES_PER_BATCH,
)
from alpaca_free_sip_shadow_guard import blob_sha, request_batch, sufficient_delay, timestamp_date
from alpaca_full_scope_260_shadow import classify
from current_history_source_request import expected_dates
from sina_state_hash_guard import verify as verify_state_hash

SCHEMA = "XRAY_EXHAUSTED_SINA_ISOLATED_SIP_FORENSICS_V1"
MAX_ISOLATED = 16
ALLOWED_REASONS = {
    "ZERO_VOLUME_DAILY_BAR", "INVALID_OHLCV_VALUES",
    "MISSING_LATEST_COMPLETED_SESSION", "MISSING_OTHER_OFFICIAL_SESSIONS",
    "NO_BAR_CONFIRMED_SINGLE_SYMBOL",
    "ISOLATED_CLASS_CHANGED_NOT_PROVEN",
    "ISOLATED_PROVIDER_TRANSPORT_UNVERIFIED",
    "UNATTEMPTED_ISOLATION_BUDGET",
    "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN",
}

def reason(rows, days, asof, original):
    """A reason for a *still failing* isolated recheck; never promote PASS."""
    if original == "NO_BAR":
        return "NO_BAR_CONFIRMED_SINGLE_SYMBOL" if rows == [] else "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"
    if original == "MISSING_EXACT_COMPLETED_SESSIONS":
        try:
            found = {timestamp_date(row["t"]).isoformat() for row in rows}
        except (KeyError, TypeError, ValueError, OverflowError):
            return "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"
        missing = set(days) - found
        if not missing:
            return "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"
        return ("MISSING_LATEST_COMPLETED_SESSION" if asof in missing
                else "MISSING_OTHER_OFFICIAL_SESSIONS")
    if original == "INVALID_OHLCV_OR_ZERO_VOLUME":
        saw_zero = False
        try:
            for row in rows:
                timestamp_date(row["t"])
                vals = [row[key] for key in ("o", "h", "l", "c", "v")]
                if any(type(v) not in (int, float) or not math.isfinite(v) for v in vals):
                    return "INVALID_OHLCV_VALUES"
                o, h, l, c, volume = vals
                if not (h >= max(o, l, c) > 0 and 0 < l <= min(o, c)):
                    return "INVALID_OHLCV_VALUES"
                if volume < 0:
                    return "INVALID_OHLCV_VALUES"
                if volume == 0:
                    saw_zero = True
        except (KeyError, TypeError, ValueError, OverflowError):
            return "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"
        return "ZERO_VOLUME_DAILY_BAR" if saw_zero else "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"
    return "UNCLASSIFIED_SOURCE_QUALITY_UNKNOWN"

def run(asof, selected, days, weeks, sina_sha, master_sha, credentials,
        source_fetch, now, minute_probe=None):
    need(now.tzinfo is not None and sufficient_delay(asof, now), "OFFICIAL_HOLDBACK")
    need(type(selected) is list and selected == sorted(set(selected))
         and 0 <= len(selected) <= MAX_ELIGIBLE, "EXHAUSTED_COHORT")
    need(len(days) == 260 and len(weeks) == 52 and days[-1] == asof,
         "EXACT_260_52")
    output = {
        "schema": SCHEMA, "status": "BLOCKED_NOT_MEASURED",
        "asof_et": asof, "source_sina_state_git_blob_sha": sina_sha,
        "source_master_git_blob_sha": master_sha,
        "selected_exhausted_count": len(selected),
        "expected_daily_sessions": 260, "expected_completed_week_closes": 52,
        "batch_size": BATCH, "isolated_budget": MAX_ISOLATED,
        "requests_attempted": 0, "isolated_attempted": 0,
        "isolated_recheck_reason_counts": {},
        "first_pass_counts": {}, "first_pass_deficient": 0,
        "zero_volume_minute_checks": 0, "zero_volume_minute_counts": {},
        "worst_case_page_requests_upper_bound": 0,
        "source_rights_independently_verified": False,
        "source_independent_primary_history_authority": False,
        "canonical_history_pass_created": 0, "canonical_price_pass_created": 0,
        "canonical_mc_pass_created": 0, "r92_registered": False,
        "provider_raw_ohlcv_persisted": False,
        "provider_symbols_persisted": False, "execution": "NONE",
        "real_money": "NO-GO", "unknown_never_pass": True,
    }
    if not selected:
        output["status"] = "BLOCKED_NO_EXHAUSTED_COHORT"
        return output
    if not all(credentials):
        output["status"] = "BLOCKED_NO_PRIVATE_CREDENTIALS"
        return output
    start = days[0] + "T00:00:00Z"
    end = (dt.date.fromisoformat(asof) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    first = {}
    # First phase is necessary to discover the 11 unknown symbol IDs without
    # writing their identities to GitHub artifacts or logs.
    for i in range(0, len(selected), BATCH):
        batch = selected[i:i+BATCH]
        output["requests_attempted"] += 1
        try:
            data = source_fetch(batch, start, end, *credentials, asof)
            need(type(data) is dict and set(data) <= set(batch), "FIRST_SCOPE")
            for symbol in batch:
                category, _ = classify(data.get(symbol, []), days, weeks, asof)
                need(category in ALLOWED, "FIRST_CLASS")
                first[symbol] = category
        except (RuntimeError, ValueError, TypeError, KeyError, OSError):
            # No fallback to an incomplete first-page result.
            for symbol in selected[i:]:
                first[symbol] = "TRANSPORT_UNVERIFIED"
            break
    need(set(first) == set(selected), "FIRST_PARTITION")
    output["first_pass_counts"] = dict(sorted(collections.Counter(first.values()).items()))
    failures = [s for s in selected if first[s] != OBSERVED]
    output["first_pass_deficient"] = len(failures)
    categories = collections.Counter()
    minute_counts = collections.Counter()
    for symbol in failures[:MAX_ISOLATED]:
        output["isolated_attempted"] += 1
        output["requests_attempted"] += 1
        try:
            single = source_fetch([symbol], start, end, *credentials, asof)
            need(type(single) is dict and set(single) <= {symbol}, "ISOLATED_SCOPE")
            rows = single.get(symbol, [])
            latest, _ = classify(rows, days, weeks, asof)
            need(latest in ALLOWED, "ISOLATED_CLASS")
            if latest != first[symbol]:
                categories["ISOLATED_CLASS_CHANGED_NOT_PROVEN"] += 1
            else:
                category=reason(rows, days, asof, latest)
                categories[category] += 1
                if category=="ZERO_VOLUME_DAILY_BAR" and minute_probe is not None:
                    from alpaca_sina_zero_volume_minute_witness import zero_day,WITNESS_CODES
                    zero_session=zero_day(rows,days)
                    if zero_session is None:
                        minute_counts["MINUTE_OFFICIAL_ZERO_DAY_UNVERIFIED"]+=1
                    elif output["zero_volume_minute_checks"]>=8:
                        minute_counts["MINUTE_OFFICIAL_ZERO_DAY_UNVERIFIED"]+=1
                    else:
                        output["zero_volume_minute_checks"]+=1
                        try:
                            witness=minute_probe(symbol,zero_session,asof,credentials)
                        except (RuntimeError,ValueError,TypeError,KeyError,OSError):
                            witness="MINUTE_INVALID_OR_TRANSPORT_UNKNOWN"
                        need(witness in WITNESS_CODES,"MINUTE_WITNESS_ENUM")
                        minute_counts[witness]+=1
        except (RuntimeError, ValueError, TypeError, KeyError, OSError):
            categories["ISOLATED_PROVIDER_TRANSPORT_UNVERIFIED"] += 1
    remaining = len(failures) - output["isolated_attempted"]
    if remaining:
        categories["UNATTEMPTED_ISOLATION_BUDGET"] += remaining
    need(set(categories) <= ALLOWED_REASONS
         and sum(categories.values()) == len(failures), "ISOLATED_PARTITION")
    need(output["isolated_attempted"] <= MAX_ISOLATED
         and output["requests_attempted"] <= (len(selected)+BATCH-1)//BATCH+MAX_ISOLATED,
         "GLOBAL_REQUEST_BUDGET")
    output["isolated_recheck_reason_counts"] = dict(sorted(
        (k,v) for k,v in categories.items() if v))
    output["zero_volume_minute_counts"]=dict(sorted(minute_counts.items()))
    need(output["zero_volume_minute_checks"]<=8
         and sum(output["zero_volume_minute_counts"].values())<=categories.get(
             "ZERO_VOLUME_DAILY_BAR",0),"ZERO_MINUTE_COUNTS_BUDGET")
    output["worst_case_page_requests_upper_bound"] = (
        output["requests_attempted"] * PAGER_MAX_PAGES_PER_BATCH
        +output["zero_volume_minute_checks"])
    output["status"] = (
        "SHADOW_FORENSICS_MEASURED_NOT_CANONICAL"
        if "TRANSPORT_UNVERIFIED" not in first.values()
        and "ISOLATED_PROVIDER_TRANSPORT_UNVERIFIED" not in categories
        and "UNATTEMPTED_ISOLATION_BUDGET" not in categories
        else "SHADOW_FORENSICS_PARTIAL_FAIL_CLOSED")
    return output

def selftest():
    from alpaca_free_sip_shadow_guard import EST
    asof = "2026-10-14"
    days, weeks = expected_dates(asof)
    now = dt.datetime(2026, 10, 15, 19, tzinfo=dt.timezone.utc)
    def bar(day,volume=100):
        t = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(), EST)
        return {"t": t.isoformat(), "o": 10.0, "h": 11.0,
                "l": 9.0, "c": 10.0, "v": volume}
    rows = {
        "AAA": [bar(d) for d in days],
        "BBB": [bar(d, 0 if d == days[-1] else 100) for d in days],
        "CCC": [bar(d) for d in days[:-1]],
        "DDD": [],
        "EEE": [dict(bar(d), c=12.0) if d == days[-2] else bar(d) for d in days],
    }
    calls = []
    def fake(block,start,end,key,secret,epoch):
        calls.append(tuple(block))
        need(epoch==asof and key=="FAKE" and secret=="FAKE", "TEST_SCOPING")
        return {s: rows[s] for s in block}
    selected = sorted(rows)
    result = run(asof,selected,days,weeks,"a"*40,"b"*40,
                 ("FAKE","FAKE"),fake,now)
    want = {"ZERO_VOLUME_DAILY_BAR":1,"MISSING_LATEST_COMPLETED_SESSION":1,
            "NO_BAR_CONFIRMED_SINGLE_SYMBOL":1,"INVALID_OHLCV_VALUES":1}
    need(result["isolated_recheck_reason_counts"]==want
         and result["status"]=="SHADOW_FORENSICS_MEASURED_NOT_CANONICAL"
         and "UNATTEMPTED_ISOLATION_BUDGET" not in result["isolated_recheck_reason_counts"]
         and result["first_pass_counts"][OBSERVED]==1
         and result["requests_attempted"]==5
         and calls==[tuple(selected),("BBB",),("CCC",),("DDD",),("EEE",)]
         and result["canonical_history_pass_created"]==0
         and result["r92_registered"] is False, "SYNTHETIC_5_PARTITION")
    def mock_minute(symbol,day,epoch,keys):
        need(symbol=="BBB" and day==asof and epoch==asof and keys==("FAKE","FAKE"),
             "MINUTE_WITNESS_SHADOW_SCOPE")
        return "MINUTE_POSITIVE_DAILY_ZERO_DISCREPANCY_SHADOW"
    observed_minute=run(asof,selected,days,weeks,"a"*40,"b"*40,
                        ("FAKE","FAKE"),fake,now,minute_probe=mock_minute)
    need(observed_minute["zero_volume_minute_checks"]==1
         and observed_minute["zero_volume_minute_counts"]==
             {"MINUTE_POSITIVE_DAILY_ZERO_DISCREPANCY_SHADOW":1}
         and observed_minute["isolated_recheck_reason_counts"]==want
         and observed_minute["canonical_history_pass_created"]==0
         and observed_minute["r92_registered"] is False,
         "ONE_DAY_MINUTE_DOES_NOT_REPAIR_HISTORY")
    def denied(*_):raise RuntimeError("ALPACA_HTTP_403")
    bad = run(asof,selected,days,weeks,"a"*40,"b"*40,
              ("FAKE","FAKE"),denied,now)
    need(bad["status"]=="SHADOW_FORENSICS_PARTIAL_FAIL_CLOSED"
         and bad["first_pass_counts"]=={"TRANSPORT_UNVERIFIED":5}
         and bad["isolated_recheck_reason_counts"]==
             {"ISOLATED_PROVIDER_TRANSPORT_UNVERIFIED":5}, "DENIED_NO_PASS")
    never = run(asof,selected,days,weeks,"a"*40,"b"*40,("",""),denied,now)
    need(never["requests_attempted"]==0
         and never["status"]=="BLOCKED_NO_PRIVATE_CREDENTIALS", "NO_CREDENTIALS_NETWORK")
    def changing(block,start,end,key,secret,epoch):
        if len(block)==1 and block==["BBB"]:return {"BBB":[bar(d) for d in days]}
        return {s:rows[s] for s in block}
    changed = run(asof,selected,days,weeks,"a"*40,"b"*40,
                  ("FAKE","FAKE"),changing,now)
    need(changed["isolated_recheck_reason_counts"].get(
         "ISOLATED_CLASS_CHANGED_NOT_PROVEN")==1, "CHANGED_NOT_PROMOTED")
    try: run(asof,["ZZZ","ZZZ"],days,weeks,"a"*40,"b"*40,
             ("FAKE","FAKE"),fake,now)
    except ValueError:pass
    else: raise AssertionError("DUPLICATE_COHORT_ACCEPTED")
    need(reason([bar(d) for d in days[:-2]],days,asof,
                "MISSING_EXACT_COMPLETED_SESSIONS") ==
         "MISSING_LATEST_COMPLETED_SESSION","MISSING_LATEST_DIAGNOSIS")
    print("XRAY_SINA_ISOLATED_FORENSICS_SELFTEST=PASS_5_SYNTHETIC_4_GAPS_TRANSPORT_AUTH_DRIFT_PRIVACY_NO_PRIMARY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:return selftest()
    need(args.out is not None and not args.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "RUNNER_TEMP_OUTPUT_ONLY")
    state=json.loads(SINA.read_text())
    master=json.loads(MASTER.read_text())
    now=dt.datetime.now(dt.timezone.utc)
    need(verify_state_hash(state)=="PASS_DETERMINISTIC_BLOB_INTERNAL",
         "SINA_INTERNAL_SHA")
    asof,selected=cohort(state,master,now)
    days,weeks=expected_dates(asof)
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or "").strip()
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or "").strip()
    def query(block,start,end,k,s,epoch):
        return request_batch(block,start,end,k,s,adjustment="raw",asof=epoch)
    from alpaca_sina_zero_volume_minute_witness import observe as witness
    output=run(asof,selected,days,weeks,blob_sha(SINA),blob_sha(MASTER),
               (key,secret),query,now,minute_probe=witness)
    args.out.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print("XRAY_SINA_ISOLATED_STATUS="+output["status"])
    print("XRAY_SINA_ISOLATED_FIRST_COUNTS="+json.dumps(output["first_pass_counts"],sort_keys=True))
    print("XRAY_SINA_ISOLATED_REASON_COUNTS="+json.dumps(
        output["isolated_recheck_reason_counts"],sort_keys=True))
    print("XRAY_SINA_ZERO_DAILY_MINUTE_COUNTS="+json.dumps(
        output["zero_volume_minute_counts"],sort_keys=True))
    print("XRAY_SINA_ISOLATED_NO_CANONICAL_NO_R92=PASS")

if __name__=="__main__":
    main()
