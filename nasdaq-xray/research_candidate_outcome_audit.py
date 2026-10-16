#!/usr/bin/env python3
"""Research-only after-the-fact WATCH follow-up diagnostics, NOT a backtest.

Strictly post-ASOF observations and an authorized benchmark are mandatory.
Prices are read from private, licensed input but never emitted or persisted.
An EOD WATCH is not an executable entry; forward close moves are not P&L.
No historical source is silently upgraded to canonical C4.17 AL.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re

import pandas_market_calendars as mcal
from research_candidate_memory import ensure, validate_ledger, canonical
from research_candidate_episode_provenance import SCHEMA as PROVENANCE_SCHEMA, EPISODE_SCHEMA

SCHEMA="XRAY_RESEARCH_FORWARD_OUTCOME_DIAGNOSTICS_V1"
HORIZONS=(1,3,5,10,20)
H64=re.compile(r"[a-f0-9]{64}\Z")


def aware(s):
    ensure(type(s) is str, "DATETIME_STRING")
    try:
        value=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    except ValueError as e:
        raise ValueError("XRAY_MEMORY_DATETIME_INVALID") from e
    ensure(value.tzinfo is not None, "DATETIME_TZ")
    return value.astimezone(dt.timezone.utc)


def positive(x):
    return type(x) in (int,float) and math.isfinite(x) and x>0


def session_schedule(asof):
    ensure(type(asof) is str, "ASOF")
    try:
        d=dt.date.fromisoformat(asof)
    except ValueError as e:
        raise ValueError("XRAY_MEMORY_ASOF_FORMAT") from e
    cal=mcal.get_calendar("NASDAQ")
    schedule=cal.schedule(start_date=d.isoformat(),
                          end_date=(d+dt.timedelta(days=90)).isoformat())
    days=[str(index.date()) for index in schedule.index]
    ensure(asof in days, "ASOF_NOT_OFFICIAL_SESSION")
    at=days.index(asof)
    future=days[at+1:at+21]
    ensure(len(future)==20, "CALENDAR_HORIZON_INCOMPLETE")
    close={str(index.date()):row["market_close"].to_pydatetime()
           for index,row in schedule.iterrows()}
    open_=schedule.loc[future[0]]["market_open"].to_pydatetime()
    return future,close,open_


def validated_prices(rows,*,name,identity,future,closes,now):
    ensure(type(rows) is list and len(rows)<=20, "EXCESS_"+name+"_ROWS")
    found={}
    for bar in rows:
        ensure(type(bar) is dict and
               bar.get("issuer_class_key")==identity and
               bar.get("session") in future and
               bar["session"] not in found,"DUPLICATE_OR_FOREIGN_"+name)
        ensure(bar.get("source_authorized") is True and
               bar.get("regular_session_complete") is True and
               bar.get("split_adjustment_verified") is True and
               type(bar.get("source_sha256")) is str and
               H64.fullmatch(bar["source_sha256"]) is not None and
               positive(bar.get("adjusted_close")),"BAD_"+name+"_BAR")
        available=aware(bar.get("available_at_utc"))
        ensure(closes[bar["session"]]+dt.timedelta(minutes=30)<=available<=now,
               "LEAKED_OR_FUTURE_"+name+"_BAR")
        found[bar["session"]]=bar
    return found


def bind_episode_to_durable_provenance(ledger, entry, episode, provenance,
                                       *, asof, next_open, closes, now):
    """Pure consistency check. Caller must authenticate GH API/artifact externally."""
    ensure(type(provenance) is dict and
           provenance.get("schema")==PROVENANCE_SCHEMA and
           provenance.get("asof_et")==asof and
           provenance.get("execution")=="NONE" and
           provenance.get("real_money")=="NO-GO" and
           provenance.get("unknown_never_pass") is True and
           provenance.get("alpha_authority") is False and
           provenance.get("r92_authority") is False and
           provenance.get("forward_return_computed") is False and
           provenance.get("model_calibrated") is False and
           provenance.get("backtest_proven") is False and
           provenance.get("iphone_delivery_receipt_attested") is False and
           provenance.get("durable_ledger_entry_sha256")==entry["entry_sha256"],
           "UNTRUSTED_EPISODE_PROVENANCE_HEADER")
    acceptance=aware(provenance.get("accepted_at_utc"))
    official_cutoff=closes[asof]+dt.timedelta(minutes=30)
    ensure(acceptance>=official_cutoff and acceptance<next_open and
           acceptance<=now and
           aware(provenance.get("official_eod_buffer_cutoff_utc"))==official_cutoff and
           aware(provenance.get("next_market_open_utc"))==next_open,
           "PROVENANCE_OFFICIAL_TIME_DRIFT_OR_LATE")
    rows=provenance.get("episodes")
    ensure(type(rows) is list and
           len(rows)==entry["watch_count"] and
           provenance.get("symbolic_watch_count")==len(rows) and
           provenance.get("eligible_episodes")==len(rows) and
           provenance.get("rejected_late_episodes")==0 and
           type(provenance.get("acceptance_workflow_run_id")) is int and
           provenance["acceptance_workflow_run_id"]>0,
           "PROVENANCE_COHORT_OR_ACCEPTANCE_CARDINALITY")
    ensure(all(type(x) is dict and x.get("schema")==EPISODE_SCHEMA and
               x.get("asof_et")==asof and
               x.get("source_acceptance_sha256")==entry["source_acceptance_sha256"] and
               x.get("ledger_entry_sha256")==entry["entry_sha256"] and
               x.get("trusted_acceptance_workflow_run_id")==
                   provenance["acceptance_workflow_run_id"] and
               x.get("candidate_decision_at_utc")==provenance["accepted_at_utc"] and
               x.get("decision_time_provenance")==
                   "SUCCESSFUL_GITHUB_ACCEPTANCE_RUN_UPDATED_AT" and
               x.get("decision_time_bound_to_supplied_successful_run_metadata") is True and
               x.get("github_run_api_identity_authenticated_inside_module") is False and
               x.get("eligible_for_next_session_research_only") is True and
               x.get("ineligible_reason") is None and
               x.get("issuer_class_identity_verified") is False and
               x.get("licensed_price_available") is False and
               x.get("no_c417_release") is True and
               x.get("no_trade_or_fill") is True and
               x.get("alpha_authority") is False and
               x.get("r92_authority") is False and
               x.get("iphone_delivery_receipt_attested") is False and
               x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
               for x in rows),
           "FORGED_PROVENANCE_EPISODE_ROW")
    symbols=[x["symbol"] for x in rows]
    ensure(symbols==sorted(entry["watch_families"]) and
           all(x["families"]==entry["watch_families"][x["symbol"]]
               for x in rows),
           "PROVENANCE_WATCH_COHORT_NOT_EXACT")
    candidates=[x for x in rows if x["symbol"]==episode["symbol"]]
    ensure(len(candidates)==1 and canonical(candidates[0])==canonical(episode),
           "EPISODE_NOT_IDENTICAL_TO_BOUND_PROVENANCE")
    ensure(aware(episode["candidate_decision_at_utc"])==acceptance,
           "EPISODE_DECISION_NOT_ACCEPTANCE_TIME")
    return provenance["acceptance_workflow_run_id"]


def audit(ledger,episode,market,provenance,*,observed_at_utc):
    validate_ledger(ledger)
    now=aware(observed_at_utc)
    ensure(type(episode) is dict and
           episode.get("schema")=="XRAY_RESEARCH_EPISODE_SOURCE_V1",
           "EPISODE_SCHEMA")
    asof=episode.get("asof_et")
    symbol=episode.get("symbol")
    digest=episode.get("source_acceptance_sha256")
    ensure(type(digest) is str and H64.fullmatch(digest) is not None,
           "EPISODE_HASH")
    accepted=[entry for entry in ledger["entries"]
              if entry["asof_et"]==asof and
              entry["source_acceptance_sha256"]==digest and
              symbol in entry["watch_families"]]
    ensure(len(accepted)==1,"EPISODE_NOT_IN_ACCEPTED_PIT_MEMORY")
    ensure(episode.get("families")==accepted[0]["watch_families"][symbol],
           "EPISODE_FAMILY_DRIFT")
    ensure(episode.get("candidate_decision_at_utc") is not None,
           "NO_PIT_DECISION_TIMESTAMP")
    future,closes,next_open=session_schedule(asof)
    decision=aware(episode["candidate_decision_at_utc"])
    ensure(closes[asof]<=decision<next_open and decision<=now,
           "DECISION_LOOKAHEAD_OR_EARLY")
    run_id=bind_episode_to_durable_provenance(
        ledger,accepted[0],episode,provenance,asof=asof,
        next_open=next_open,closes=closes,now=now)
    ensure(type(market) is dict and
           market.get("schema")=="XRAY_RESEARCH_AUTHORIZED_OUTCOME_BARS_V1" and
           market.get("symbol")==symbol and
           market.get("asof_et")==asof and
           market.get("rights_derived_metrics_permitted") is True and
           market.get("historical_universe_includes_delisted") is True and
           market.get("issuer_class_identity_verified") is True and
           market.get("corporate_action_adjustment_verified") is True and
           market.get("execution")=="NONE" and
           market.get("real_money")=="NO-GO",
           "MARKET_SOURCE_RIGHTS_OR_SURVIVORSHIP")
    identity=market.get("issuer_class_key")
    benchmark=market.get("benchmark_class_key")
    ensure(type(identity) is str and bool(identity) and
           type(benchmark) is str and bool(benchmark) and
           benchmark!=identity and
           type(market.get("market_data_source_sha256")) is str and
           H64.fullmatch(market["market_data_source_sha256"]) is not None,
           "MARKET_IDENTITY_SOURCE")
    ensure(market.get("reference_session")==asof and
           market.get("benchmark_reference_session")==asof,
           "REFERENCE_ASOF_SESSION_MISMATCH")
    ensure(positive(market.get("reference_adjusted_close")) and
           positive(market.get("benchmark_reference_adjusted_close")),
           "REFERENCE_ADJUSTED_CLOSE")
    ensure(closes[asof]<=aware(market.get("reference_available_at_utc"))<=decision and
           closes[asof]<=aware(market.get("benchmark_reference_available_at_utc"))<=decision,
           "REFERENCE_KNOWN_AFTER_DECISION")
    stock=validated_prices(market.get("stock_future_bars"),name="STOCK",
                           identity=identity,future=future,closes=closes,now=now)
    bench=validated_prices(market.get("benchmark_future_bars"),name="BENCH",
                           identity=benchmark,future=future,closes=closes,now=now)
    details={}
    for horizon in HORIZONS:
        segment=future[:horizon]
        missing=[d for d in segment if d not in stock or d not in bench]
        if missing:
            details[str(horizon)]={
                "status":"UNKNOWN_MISSING_COMPLETE_COMPARABLE_SESSION",
                "missing_session_count":len(missing),
                "first_missing_session":missing[0],
                "forward_return_pct":None,"benchmark_return_pct":None,
                "excess_return_pct_points":None}
            continue
        sr=100*(stock[segment[-1]]["adjusted_close"]/
                market["reference_adjusted_close"]-1)
        br=100*(bench[segment[-1]]["adjusted_close"]/
                market["benchmark_reference_adjusted_close"]-1)
        details[str(horizon)]={
            "status":"COMPLETED_RESEARCH_FORWARD_CLOSE_MOVE_NOT_TRADE",
            "session":segment[-1],
            "forward_return_pct":round(sr,6),
            "benchmark_return_pct":round(br,6),
            "excess_return_pct_points":round(sr-br,6)}
    return {
        "schema":SCHEMA,
        "symbol":symbol,"families":episode["families"],
        "asof_et":asof,"accepted_receipt_sha256":digest,
        "source_market_data_sha256":market["market_data_source_sha256"],
        "source_issuer_class_key":identity,
        "durable_ledger_entry_sha256":accepted[0]["entry_sha256"],
        "trusted_acceptance_workflow_run_id":run_id,
        "episode_provenance_consistency_checked":True,
        "github_api_and_artifact_authenticated_inside_module":False,
        "comparison_benchmark_class_key":benchmark,
        "horizons":details,
        "primary_alpha_authority":False,
        "backtest_proven":False,
        "model_calibrated":False,
        "position_or_fill_inferred":False,
        "decision_timestamp_independently_authenticated_by_this_module":False,
        "sample_comparability_externally_attested":False,
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
        "raw_prices_persisted":False,
        "limitations":[
          "External source and decision timestamp attestations still required",
          "Complete adjusted closes are observations, not executable fills",
          "No selection-bias, market beta, costs or walk-forward model verdict",
          "An incomplete horizon is UNKNOWN; no missing-bar zero filling",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    for x in ("ledger","episode","market","provenance","out"):
        p.add_argument("--"+x,required=True,type=Path)
    p.add_argument("--observed-at-utc",required=True)
    a=p.parse_args()
    ensure(a.out.resolve() not in {a.ledger.resolve(),
          a.episode.resolve(),a.market.resolve(),
          a.provenance.resolve()},"INPUT_OVERWRITE_FORBIDDEN")
    o=audit(json.loads(a.ledger.read_text()),
            json.loads(a.episode.read_text()),
            json.loads(a.market.read_text()),
            json.loads(a.provenance.read_text()),
            observed_at_utc=a.observed_at_utc)
    a.out.write_bytes(canonical(o)+b"\n")
    print(json.dumps({"status":"RESEARCH_DIAGNOSTIC_ONLY",
        "complete_horizons":sum(x["status"].startswith("COMPLETED")
                      for x in o["horizons"].values()),
        "alpha":False,"model_calibrated":False,"execution":"NONE",
        "real_money":"NO-GO"},sort_keys=True))


if __name__=="__main__":
    main()
