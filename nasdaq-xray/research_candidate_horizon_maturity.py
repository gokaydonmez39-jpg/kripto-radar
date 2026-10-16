#!/usr/bin/env python3
"""Calendar maturity, never realized returns or data-source release.

For an authenticated symbolic WATCH episode this records when a horizon can
*first be eligible for price-label review*. Passing a date barrier NEVER
attests any licensed return, valid benchmark, issuer identity or model result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas_market_calendars as mcal
from research_candidate_memory import canonical, ensure

SCHEMA="XRAY_RESEARCH_SYMBOLIC_HORIZON_MATURITY_V1"
HORIZONS=(1,3,5,10,20)


def summarize(provenance,*,now_utc):
    ensure(type(provenance) is dict and
           provenance.get("schema")=="XRAY_SYMBOLIC_RESEARCH_EPISODE_PROVENANCE_V1" and
           provenance.get("execution")=="NONE" and
           provenance.get("real_money")=="NO-GO" and
           provenance.get("alpha_authority") is False and
           provenance.get("backtest_proven") is False and
           provenance.get("forward_return_computed") is False and
           provenance.get("model_calibrated") is False,
           "MATURITY_UPSTREAM_AUTHORITY")
    ensure(now_utc.tzinfo is not None and
           now_utc.utcoffset()==dt.timedelta(0),
           "MATURITY_REQUIRES_AWARE_UTC")
    asof=provenance.get("asof_et")
    try:
        d=dt.date.fromisoformat(asof)
    except (TypeError,ValueError) as e:
        raise ValueError("XRAY_MEMORY_MATURITY_INVALID_ASOF") from e
    ensure(d.isoformat()==asof, "MATURITY_SESSION_DATE_FORMAT")
    cal=mcal.get_calendar("NASDAQ")
    sched=cal.schedule(
        start_date=asof,
        end_date=(d+dt.timedelta(days=100)).isoformat())
    sessions=[str(i.date()) for i in sched.index]
    ensure(asof in sessions and len(sessions)>=21,
           "MATURITY_CALENDAR_CANNOT_PROVE_20_SESSIONS")
    targets={str(h):{
        "session":sessions[h],
        "after_close_plus_30m_utc":(
            sched.loc[sessions[h]]["market_close"].to_pydatetime()
            +dt.timedelta(minutes=30)).isoformat(),
    } for h in HORIZONS}
    rows=provenance.get("episodes")
    ensure(type(rows) is list and
           len(rows)==provenance.get("symbolic_watch_count") and
           len(rows)==len({v.get("symbol") for v in rows}) and
           sum(v.get("eligible_for_next_session_research_only") is True
               for v in rows)==provenance.get("eligible_episodes"),
           "MATURITY_EPISODE_COUNT_DRIFT")
    eligible=0
    episode_out=[]
    for row in sorted(rows,key=lambda v:v["symbol"]):
        ensure(type(row) is dict and
               row.get("schema")=="XRAY_RESEARCH_EPISODE_SOURCE_V1" and
               row.get("asof_et")==asof and
               row.get("execution")=="NONE" and
               row.get("real_money")=="NO-GO" and
               row.get("alpha_authority") is False and
               row.get("r92_authority") is False and
               row.get("no_trade_or_fill") is True and
               row.get("licensed_price_available") is False and
               row.get("issuer_class_identity_verified") is False,
               "MATURITY_EPISODE_AUTHORITY")
        gate=row.get("eligible_for_next_session_research_only")
        ensure(type(gate) is bool, "MATURITY_EPISODE_ELIGIBILITY_TYPE")
        if gate:eligible+=1
        horizon_states={}
        for h in HORIZONS:
            x=targets[str(h)]
            cutoff=dt.datetime.fromisoformat(x["after_close_plus_30m_utc"])
            horizon_states[str(h)]={
                "target_session":x["session"],
                "earliest_label_review_utc":x["after_close_plus_30m_utc"],
                "status":(
                    "INELIGIBLE_ACCEPTED_AFTER_NEXT_OPEN"
                    if not gate else
                    "NOT_YET_MATURE"
                    if now_utc<cutoff else
                    "MATURE_BY_CALENDAR_OUTCOME_SOURCE_STILL_UNKNOWN"),
                "forward_return_pct":None,
                "benchmark_return_pct":None,
                "excess_return_pct_points":None,
            }
        episode_out.append({
            "symbol":row["symbol"],
            "candidate_decision_at_utc":row["candidate_decision_at_utc"],
            "horizons":horizon_states,
        })
    ensure(eligible==provenance["eligible_episodes"],
           "MATURITY_REPLAY_DRIFT")
    return {
        "schema":SCHEMA,
        "source_provenance_schema":provenance["schema"],
        "source_acceptance_workflow_run_id":
            provenance["acceptance_workflow_run_id"],
        "durable_ledger_entry_sha256":
            provenance["durable_ledger_entry_sha256"],
        "asof_et":asof,
        "observed_at_utc":now_utc.isoformat(),
        "episodes":episode_out,
        "eligible_episode_count":eligible,
        "outcome_sources_verified":False,
        "realized_return_computed":False,
        "model_trained":False,
        "model_calibrated":False,
        "alpha_authority":False,
        "r92_authority":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--provenance",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--now-utc")
    args=p.parse_args()
    ensure(args.out.resolve()!=args.provenance.resolve(),
           "MATURITY_INPUT_OVERWRITE_FORBIDDEN")
    now=(dt.datetime.fromisoformat(args.now_utc.replace("Z","+00:00"))
         if args.now_utc else dt.datetime.now(dt.timezone.utc))
    result=summarize(json.loads(args.provenance.read_text()),
                     now_utc=now)
    args.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({
        "status":"CALENDAR_ONLY_ALL_RETURNS_UNKNOWN",
        "eligible_episodes":result["eligible_episode_count"],
        "alpha":False,"execution":"NONE","real_money":"NO-GO"
    },sort_keys=True))


if __name__=="__main__":
    main()
