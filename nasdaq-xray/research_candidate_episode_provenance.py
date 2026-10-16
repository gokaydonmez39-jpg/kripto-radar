#!/usr/bin/env python3
"""Source-bound first-known-time for symbolic WATCH episodes, NOT trading entry.

The *first provable* cohort snapshot time is the successful authenticated
three-source acceptance workflow's updated_at, never a backdated scan event.
If it finishes after the following Nasdaq open, the episode is ineligible for
next-session outcome study. Original price/identity decisions are NOT proved.
External call-site MUST authenticate GitHub run + downloaded exact artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas_market_calendars as mcal

from research_candidate_memory import (
    canonical, ensure, sha, safe_families, validate_ledger)
from research_candidate_memory_admission import admit, iso_utc

SCHEMA="XRAY_SYMBOLIC_RESEARCH_EPISODE_PROVENANCE_V1"
EPISODE_SCHEMA="XRAY_RESEARCH_EPISODE_SOURCE_V1"


def windows(asof):
    calendar=mcal.get_calendar("NASDAQ")
    d=dt.date.fromisoformat(asof)
    scheduled=calendar.schedule(
        start_date=d.isoformat(),
        end_date=(d+dt.timedelta(days=8)).isoformat())
    dates=[str(x.date()) for x in scheduled.index]
    ensure(asof in dates, "EPISODE_ASOF_OFFICIAL_SESSION")
    idx=dates.index(asof)
    ensure(idx+1<len(dates), "EPISODE_NEXT_TRADING_SESSION_NOT_FOUND")
    eod=(scheduled.loc[asof]["market_close"].to_pydatetime()+
         dt.timedelta(minutes=30))
    next_open=scheduled.iloc[idx+1]["market_open"].to_pydatetime()
    return eod,next_open,dates[idx+1]


def attest(ledger,receipt,run,artifact,*,asof,expected_run_id,
           now_utc=None):
    """Build research-only after-proof-time candidates from a stored entry."""
    validate_ledger(ledger)
    now=now_utc or dt.datetime.now(dt.timezone.utc)
    ensure(now.tzinfo is not None and now.utcoffset()==dt.timedelta(0),
           "EPISODE_CLOCK_NEEDS_UTC")
    admission=admit(run,receipt,expected_asof=asof,
                    artifact=artifact,expected_run_id=expected_run_id,
                    now_utc=now)
    source_sha=sha(receipt)
    matched=[x for x in ledger["entries"]
             if x["asof_et"]==asof and
             x["source_acceptance_sha256"]==source_sha]
    ensure(len(matched)==1, "EPISODE_NOT_ON_DURABLE_ACCEPTED_CHAIN")
    entry=matched[0]
    families=safe_families(receipt["research_watch_families"])
    ensure(entry["watch_families"]==families and
           entry["watch_count"]==len(families) and
           entry["source_run_ids"]=={
               "source":receipt["source_workflow_run_id"],
               "watch":receipt["technical_watch_workflow_run_id"],
               "mirror":receipt["mirror_workflow_run_id"]},
           "EPISODE_DURABLE_SOURCE_DRIFT")
    eod,next_open,next_session=windows(asof)
    known_at=iso_utc(run["updated_at"])
    ensure(known_at>=eod, "EPISODE_ACCEPTANCE_BEFORE_OFFICIAL_EOD")
    # CRITICAL: no next-session close benchmark if original evidence arrived
    # only after the next market open. Do not backdate a late observation.
    eligible=known_at<next_open
    episodes=[]
    for symbol in sorted(families):
        episodes.append({
            "schema":EPISODE_SCHEMA,
            "asof_et":asof,
            "symbol":symbol,
            "families":list(families[symbol]),
            "source_acceptance_sha256":source_sha,
            "ledger_entry_sha256":entry["entry_sha256"],
            "trusted_acceptance_workflow_run_id":admission["run_id"],
            "trusted_acceptance_workflow_head_sha":admission["run_head_sha"],
            "trusted_acceptance_artifact_id":artifact["id"],
            "candidate_decision_at_utc":known_at.isoformat(),
            "decision_time_provenance":"SUCCESSFUL_GITHUB_ACCEPTANCE_RUN_UPDATED_AT",
            "decision_time_bound_to_supplied_successful_run_metadata":True,
            "github_run_api_identity_authenticated_inside_module":False,
            "eligible_for_next_session_research_only":eligible,
            "ineligible_reason":None if eligible else
                "ACCEPTED_TOO_LATE_FOR_NEXT_TRADING_SESSION",
            "issuer_class_identity_verified":False,
            "licensed_price_available":False,
            "no_c417_release":True,
            "no_trade_or_fill":True,
            "alpha_authority":False,
            "r92_authority":False,
            "iphone_delivery_receipt_attested":False,
            "execution":"NONE","real_money":"NO-GO",
        })
    return {
        "schema":SCHEMA,
        "asof_et":asof,
        "accepted_at_utc":known_at.isoformat(),
        "next_session":next_session,
        "next_market_open_utc":next_open.isoformat(),
        "official_eod_buffer_cutoff_utc":eod.isoformat(),
        "acceptance_workflow_run_id":admission["run_id"],
        "durable_ledger_entry_sha256":entry["entry_sha256"],
        "symbolic_watch_count":len(episodes),
        "eligible_episodes":sum(e["eligible_for_next_session_research_only"]
                                for e in episodes),
        "rejected_late_episodes":sum(
            not e["eligible_for_next_session_research_only"]
            for e in episodes),
        "episodes":episodes,
        "provenance_limitation":
            "Only GitHub acceptance-completion time; independent original "
            "market-signal availability, licensed prices, corporate action "
            "and issuer-class primary sources remain UNKNOWN",
        "forward_return_computed":False,
        "backtest_proven":False,
        "model_calibrated":False,
        "alpha_authority":False,"r92_authority":False,
        "iphone_delivery_receipt_attested":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }


def main():
    p=argparse.ArgumentParser()
    for key in ("ledger","receipt","run","artifact","out"):
        p.add_argument("--"+key,required=True,type=Path)
    p.add_argument("--asof",required=True)
    p.add_argument("--run-id",required=True,type=int)
    a=p.parse_args()
    sources=[getattr(a,key).resolve() for key in
             ("ledger","receipt","run","artifact")]
    ensure(a.out.resolve() not in sources,"EPISODE_INPUT_OVERWRITE_FORBIDDEN")
    o=attest(*(json.loads(getattr(a,key).read_text())
               for key in ("ledger","receipt","run","artifact")),
             asof=a.asof,expected_run_id=a.run_id)
    a.out.write_bytes(canonical(o)+b"\n")
    print(json.dumps({
        "status":"PROVENANCE_ONLY_NO_MODEL_OR_TRADE",
        "asof_et":o["asof_et"],
        "eligible_episodes":o["eligible_episodes"],
        "rejected_late_episodes":o["rejected_late_episodes"],
        "alpha":False,"execution":"NONE","real_money":"NO-GO"
    },sort_keys=True))


if __name__=="__main__":
    main()
