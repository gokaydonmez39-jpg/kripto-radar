#!/usr/bin/env python3
"""Empirical research-readiness examination gate; NEVER authorizes learned AL.

A review-eligible *shadow dataset* does not imply a valid backtest, trained
model, calibrated probability, 7/7 R92, G9, broker or mobile delivery.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import re
import pandas_market_calendars as mcal
from pathlib import Path
from research_candidate_memory import ensure

SCHEMA="XRAY_RESEARCH_LEARNING_READINESS_V1"
MIN_REVIEW_EPISODES=100  # Proposed statistical REVIEW threshold, NOT C4.17 policy.
C417="C4.17"
HORIZONS=("1","3","5","10","20")


def check(calibration, reports):
    ensure(type(calibration) is dict and
           calibration.get("schema")=="XRAY_ALPHA_CALIBRATION_AUDIT_V1" and
           calibration.get("current_policy_version")==C417 and
           calibration.get("execution")=="NONE" and
           calibration.get("real_money")=="NO-GO" and
           calibration.get("alpha_authority") is False and
           calibration.get("no_threshold_change") is True,
           "CALIBRATION_SOURCE_HEADER")
    rows=calibration.get("observed_terminal_snapshots")
    ensure(type(rows) is list and
           calibration.get("observed_snapshot_count")==len(rows),
           "CALIBRATION_SNAPSHOT_COUNT")
    dates=[]
    for row in rows:
        ensure(type(row) is dict and type(row.get("asof_et")) is str,
               "SNAPSHOT_DATE")
        try:
            date_obj=dt.date.fromisoformat(row["asof_et"])
        except ValueError as e:
            raise ValueError("XRAY_MEMORY_BAD_SESSION_DATE") from e
        ensure(date_obj.isoformat()==row["asof_et"],"BAD_SESSION_FORMAT")
        dates.append(row["asof_et"])
        if row.get("comparable_to_current_c417") is True:
            ensure(row.get("full_end_to_end_research_pass") is True and
                   row.get("compiled_policy_version")==C417,
                   "FALSE_C417_COMPARABLE_SNAPSHOT")
    ensure(len(dates)==len(set(dates)),"DUPLICATE_C417_SESSION")
    if dates:
        days=mcal.get_calendar("NASDAQ").valid_days(
            start_date=min(dates),end_date=max(dates))
        valid={str(x.date()) for x in days}
        ensure(set(dates).issubset(valid),"NON_NASDAQ_C417_SESSION")
    comparable=sum(x.get("comparable_to_current_c417") is True for x in rows)
    target=calibration.get("target_comparable_sessions")
    ensure(type(target) is int and target>=60 and
           calibration.get("comparable_current_policy_session_count")==comparable and
           calibration.get("calibration_pass") is (comparable>=target),
           "CALIBRATION_COUNT_OR_VERDICT_DRIFT")
    ensure(type(reports) is list,"REPORTS_TYPE")
    accepted=set()
    complete=0
    unknown=0
    for report in reports:
        ensure(type(report) is dict and
               report.get("schema")=="XRAY_RESEARCH_FORWARD_OUTCOME_DIAGNOSTICS_V1" and
               report.get("execution")=="NONE" and
               report.get("real_money")=="NO-GO" and
               report.get("primary_alpha_authority") is False and
               report.get("backtest_proven") is False and
               report.get("model_calibrated") is False and
               report.get("raw_prices_persisted") is False and
               report.get("sample_comparability_externally_attested") is False,
               "OUTCOME_RESEARCH_ONLY_HEADER")
        key=(report.get("asof_et"),report.get("symbol"),
             report.get("accepted_receipt_sha256"))
        ensure(all(type(x) is str and bool(x) for x in key) and
               key not in accepted,"DUPLICATE_OR_INVALID_EPISODE")
        ensure(type(report.get("source_market_data_sha256")) is str and
               re.fullmatch(r"[a-f0-9]{64}",report["source_market_data_sha256"]) is not None and
               re.fullmatch(r"[a-f0-9]{64}",key[2]) is not None,
               "OUTCOME_SOURCE_SHA")
        accepted.add(key)
        horizons=report.get("horizons")
        ensure(type(horizons) is dict and set(horizons)==set(HORIZONS),
               "OUTCOME_HORIZON_SET")
        outcomes=[horizons[k] for k in HORIZONS]
        ensure(all(type(o) is dict and
                   o.get("status") in (
                       "COMPLETED_RESEARCH_FORWARD_CLOSE_MOVE_NOT_TRADE",
                       "UNKNOWN_MISSING_COMPLETE_COMPARABLE_SESSION")
                   for o in outcomes),"OUTCOME_STATUS_INVALID")
        for out in outcomes:
            nums=[out.get(k) for k in ("forward_return_pct",
                  "benchmark_return_pct","excess_return_pct_points")]
            if out["status"].startswith("COMPLETED"):
                ensure(all(type(v) in (int,float) and math.isfinite(v) for v in nums)
                       and abs(nums[0]-nums[1]-nums[2])<0.00001,
                       "FORWARD_BENCHMARK_MATH")
            else:
                ensure(all(v is None for v in nums),"UNKNOWN_HORIZON_WITH_FINITE_RESULT")
        if all(x["status"].startswith("COMPLETED") for x in outcomes):
            complete+=1
        else:
            unknown+=1
    can_review=comparable>=target and complete>=MIN_REVIEW_EPISODES
    reasons=[]
    if comparable<target:reasons.append("COMPARABLE_C417_SESSION_COUNT_INSUFFICIENT")
    if complete<MIN_REVIEW_EPISODES:reasons.append("FULL_20_SESSION_EPISODE_COUNT_INSUFFICIENT")
    reasons+=["INDEPENDENT_EPISODE_TIME_AND_SOURCE_ATTESTATION_NOT_PROVEN",
              "WALK_FORWARD_AND_SURVIVORSHIP_VALIDATION_NOT_PROVEN",
              "REAL_OUT_OF_SAMPLE_PERFORMANCE_NOT_PROVEN"]
    return {
      "schema":SCHEMA,
      "status":"DATASET_REVIEW_CANDIDATE_NOT_MODEL_AUTHORIZED"
          if can_review else "INSUFFICIENT_COMPARABLE_LEARNING_EVIDENCE",
      "policy":C417,
      "comparable_current_policy_sessions":comparable,
      "target_comparable_sessions":target,
      "outcome_episodes_examined":len(accepted),
      "complete_20_session_episodes":complete,
      "censored_or_unknown_episodes":unknown,
      "proposed_min_complete_review_episodes":MIN_REVIEW_EPISODES,
      "shadow_dataset_review_candidate":can_review,
      "blockers":reasons,
      "brier_score":None,
      "precision":None,"recall":None,
      "false_positive_rate":None,"false_negative_rate":None,
      "out_of_sample_alpha":None,"model_trained":False,
      "model_calibrated":False,"policy_threshold_changed":False,
      "alpha_authority":False,"r92_authority":False,
      "iphone_delivery_receipt_attested":False,
      "execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--audit",required=True,type=Path)
    p.add_argument("--reports",type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    paths={a.audit.resolve()}
    if a.reports:paths.add(a.reports.resolve())
    ensure(a.out.resolve() not in paths,"INPUT_OVERWRITE_FORBIDDEN")
    audit=json.loads(a.audit.read_text())
    reports=json.loads(a.reports.read_text()) if a.reports else []
    out=check(audit,reports)
    a.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":out["status"],
        "comparable_sessions":out["comparable_current_policy_sessions"],
        "complete_20_session_episodes":out["complete_20_session_episodes"],
        "trained":False,"alpha":False},sort_keys=True))


if __name__=="__main__":
    main()
