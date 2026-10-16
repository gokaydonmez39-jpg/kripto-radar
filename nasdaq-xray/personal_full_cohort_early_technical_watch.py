#!/usr/bin/env python3
"""Independent SIP full-cohort early technical WATCH, distinct from C4.17 AL.

The input is ONE exact-source six-gate causal research artifact. This process
re-reads OHLCV in RAM solely for individually proven technical observations.
Persist only symbolic diagnostic classifications, never vendor bars, prices,
stops, targets, trading actions or licensed primary declarations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

from alpaca_full_universe_asof_sip_availability import sha as symbols_sha
from source_epoch_freshness_guard import last_complete_session
from current_history_source_request import expected_dates
from alpaca_personal_seven_technical_shadow import quality, assess, chunks
from alpaca_free_sip_shadow_guard import request_batch
from official_first_trade_260_history_guard import fence

SCHEMA="XRAY_PERSONAL_FULL_COHORT_EARLY_TECH_WATCH_V1"
SOURCE="XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1"
READY="TECHNICAL_FAMILY_RESEARCH_ONLY_RELEASE_GATES_OPEN"
WATCH="TECHNICAL_WATCH_OBSERVED_RESEARCH_NOT_AL"


def need(condition,code):
    if not condition:raise ValueError("XRAY_EARLY_WATCH_"+code)


def cohort(doc,now):
    need(type(doc) is dict and doc.get("schema")==SOURCE,"CAUSAL_SCHEMA")
    asof=last_complete_session(now)
    need(doc.get("asof_et")==asof,"LATEST_COMPLETED_ASOF")
    need(doc.get("execution")=="NONE" and doc.get("real_money")=="NO-GO"
         and doc.get("no_vendor_ohlcv_persisted") is True
         and doc.get("no_canonical_mutations") is True
         and doc.get("source_rights_not_inferred") is True
         and doc.get("registered_r92_count")==0
         and doc.get("c417_price_dv30_primary_attested") is False
         and doc.get("issuer_class_mc_current_attested") is False
         and doc.get("technical_a_b_d_r1_event_regime_attested") is False,
         "SAFETY_AND_UNPROMOTED_SOURCE")
    scope=doc.get("per_symbol_causal_routing")
    high=doc.get("next_gate_mc_sec_research_only_symbols")
    partial=doc.get("rth30_partial_missing_slot_high_research_only_symbols")
    need(type(partial) is list and partial==sorted(set(partial)) and
         doc.get("rth30_partial_notional_is_proxy_not_trade_floor") is True and
         doc.get("rth30_partial_research_never_primary") is True and
         len(partial)==doc.get("rth30_partial_missing_slot_high_research_only_count") and
         symbols_sha(partial)==doc.get("rth30_partial_missing_slot_high_research_only_sha256"),
         "EXACT_SYMBOLIC_PARTIAL_SHA_NO_PRIMARY")
    need(type(scope) is dict and doc.get("scope_count")==len(scope) and
         len(scope)>0 and type(high) is list and high==sorted(set(high)) and
         len(high)==doc.get("rth30_lower_bound_observed") and
         symbols_sha(high)==doc.get("rth30_lower_bound_sha256") and
         set(partial).issubset(high) and set(high).issubset(scope) and
         len(high)-len(partial)==
             doc.get("rth30_strict_complete_slot_lower_bound_observed") and
         all(scope[s]["first_unresolved_gate"]=="PRICE_DV30" and
             scope[s]["causal_class"]==(
                 "RTH_OBSERVED_PARTIAL_BARLOW_PROXY_ONLY" if s in partial
                 else "RTH_30MIN_LOWER_BOUND_ONLY")
             for s in high),"EXACT_POSITIVE_RTH_RESEARCH_COHORT")
    counts=Counter(row.get("first_unresolved_gate") for row in scope.values())
    need(dict(sorted(counts.items()))==doc.get("first_unresolved_gate_counts"),
         "FULL_SOURCE_GATE_PARTITION")
    return asof,high


def run(doc,now,fetch):
    asof,names=cohort(doc,now)
    # The independently technical-scanned RTH lower-bound cohort can be
    # smaller than the full source identity universe. Report BOTH
    # denominators; never describe cohort completeness as universe coverage.
    source_scope=doc["per_symbol_causal_routing"]
    cohort_set=set(names)
    outside_counts=Counter(row.get("first_unresolved_gate")
        for sym,row in source_scope.items() if sym not in cohort_set)
    outside_count=len(source_scope)-len(names)
    need(outside_count>=0 and sum(outside_counts.values())==outside_count,
         "FULL_IDENTITY_NONCOHORT_PARTITION")
    days,weeks=expected_dates(asof)
    need(len(days)==260 and len(weeks)==52 and days[-1]==asof,
         "EXACT_260_52_OFFICIAL_DATES")
    result={
        "schema":SCHEMA,"asof_et":asof,
        "source_causal_digest_sha256":sha256(json.dumps(
            doc,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "source_causal_scope_count":doc["scope_count"],
        "research_partial_rth_source_count":
            doc["rth30_partial_missing_slot_high_research_only_count"],
        "research_complete_rth_source_count":
            doc["rth30_strict_complete_slot_lower_bound_observed"],
        "partial_source_is_not_c417_primary":True,
        "full_identity_source_partition_checked":True,
        "technical_cohort_is_universe_count":len(names)==doc["scope_count"],
        "outside_technical_cohort_count":outside_count,
        "outside_technical_cohort_first_unresolved_gate_counts":
            dict(sorted(outside_counts.items())),
        "full_identity_technical_scan_attested":False,
        "source_rth_lower_bound_cohort_sha256":symbols_sha(names),
        "source_research_likelihood_not_a_price_prediction":True,
        "scope_count":len(names),
        "technical_status_by_symbol":{},
        "technical_research_watch_symbols":[],
        "technical_setup_family_verified":{},
        # Even an empty source-qualified cohort has a deterministic membership.
        # Omission used to make the existing automatic WATCH CI fail every time
        # RTH bars were missing and no candidate was safely released.
        "watch_membership_digest_sha256":sha256(json.dumps({
            "asof_et":asof,"technical_setup_family_verified":{}
        },sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "source_rights_not_inferred":True,
        "all_symbols_classified":False,
        "source_independent_primary_history_attested":False,
        "source_independent_primary_dv30_attested":False,
        "source_independent_primary_mc_attested":False,
        "source_event_and_regime_release_attested":False,
        "registered_r92_count":0,
        "iphone_delivery_receipt_attested":False,
        "no_vendor_ohlcv_or_price_levels_persisted":True,
        "execution":"NONE","real_money":"NO-GO",
        "orders":[],"buy_signals":[],"user_notification_sent":False,
        "platform_notification_sent":False,
        "benchmark_status":"UNKNOWN_NOT_QUERIED",
        "api_batches_attempted":0,
        "status":"STARTED_NOT_RELEASE_AUTHORITY",
    }
    if not names:
        result["all_symbols_classified"]=True
        result["full_identity_technical_scan_attested"]=outside_count==0
        result["status"]="EMPTY_RESEARCH_COHORT_NOT_A_NO_SETUP_PROOF"
        result["classification_counts"]={}
        return result
    start=days[0]+"T00:00:00Z"
    # SIP historical end MUST be >15min in the past on personal plans.
    # Tomorrow 00:00Z can be in the future while today's Nasdaq RTH has
    # already closed; that caused actual ALPACA_HTTP_403 on 2026-10-14.
    # Resolve each session's official close (including shortened sessions).
    import pandas_market_calendars as mcal
    calendar=mcal.get_calendar("NASDAQ")
    close_calendar=calendar.schedule(start_date=asof,end_date=asof)
    need(len(close_calendar)==1,"OFFICIAL_NASDAQ_CLOSE_MISSING")
    end_time=close_calendar.iloc[0]["market_close"].to_pydatetime()+timedelta(seconds=1)
    need(end_time.tzinfo is not None and
         end_time<=now-timedelta(minutes=16),
         "SIP_HISTORICAL_END_WITHIN_RECENT_15_MIN_WINDOW")
    end=end_time.isoformat().replace("+00:00","Z")
    try:
        result["api_batches_attempted"]+=1
        r=fetch(["QQQ"],start,end,asof)
        need(type(r) is dict and set(r)=={"QQQ"},"BENCHMARK_SCOPE")
        benchmark,qstate=quality(r["QQQ"],days,weeks,asof)
    except Exception as exc:
        benchmark=None
        token=str(exc).split(":",1)[0]
        token=token if (token.startswith(("ALPACA_","XRAY_EARLY_WATCH_"))
            and token.replace("_","").isalnum() and len(token)<90) else type(exc).__name__
        qstate="UNKNOWN_QQQ_SOURCE_"+token
    result["benchmark_status"]=qstate
    if qstate!="HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY":
        benchmark=None
    if benchmark is None:
        result["technical_status_by_symbol"]={x:"UNKNOWN_QQQ_FRESH_BENCHMARK_OR_HISTORY"
                                               for x in names}
    else:
        import stage1_shadow as stage
        import deep_pre_r1_shadow as deep
        eligible_weeks=stage.build_week_last(asof)
        groups=chunks(names)
        for i,grp in enumerate(groups):
            # A failed API batch still consumes a request attempt and
            # potentially vendor quota; count BEFORE the network call.
            result["api_batches_attempted"]+=1
            try:
                r=fetch(grp,start,end,asof)
                need(type(r) is dict and set(r)==set(grp),"EXACT_PROVIDER_BATCH_SET")
            except Exception as exc:
                for symbol in grp:
                    result["technical_status_by_symbol"][symbol]=\
                        "UNKNOWN_PROVIDER_BATCH_"+type(exc).__name__
                if "429" in str(exc) or "RATE_LIMIT" in str(exc) or "403" in str(exc):
                    for other in groups[i+1:]:
                        for symbol in other:
                            result["technical_status_by_symbol"][symbol]=\
                                "UNKNOWN_UNATTEMPTED_UPSTREAM_CLIFF"
                    break
                continue
            for symbol in grp:
                try:
                    listing=fence(symbol,asof)
                    if listing and listing["own_listed_history_short"]:
                        result["technical_status_by_symbol"][symbol]=\
                            "FAIL_OWN_ISSUER_FIRST_TRADE_LT260"
                        continue
                    df,hstate=quality(r[symbol],days,weeks,asof)
                    if hstate!="HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY":
                        result["technical_status_by_symbol"][symbol]=hstate
                        continue
                    status,verified=assess(symbol,df,benchmark,asof,eligible_weeks)
                    if status==READY and verified>0:
                        # Recompute family identity without exporting OHLCV,
                        # retaining exact source-scope and geometry checks.
                        eligible,_=stage.recent_weekly_context(df,eligible_weeks)
                        a,b,d=deep.evaluate_recent_families(df,benchmark,eligible)
                        patterns={"A":a,"B":b,"D":d}
                        families=sorted(k for k,g in patterns.items()
                            if g.get("pool") is True and
                            g.get("trigger_date") in eligible and
                            (k=="A" or k=="D" and g.get("dk3_pre_r1") is True
                             or k=="B" and g.get("breakout_confirmed") is True))
                        need(len(families)==verified and all(f in ("A","B","D")
                             for f in families),"TECHNICAL_FAMILY_VERIFIED_EXACT")
                        result["technical_setup_family_verified"][symbol]=families
                        result["technical_status_by_symbol"][symbol]=WATCH
                    elif status==READY:
                        result["technical_status_by_symbol"][symbol]=\
                            "UNKNOWN_TECHNICAL_ZERO_INDEPENDENT_VERIFICATIONS"
                    else:
                        result["technical_status_by_symbol"][symbol]=status
                except Exception:
                    result["technical_status_by_symbol"][symbol]=\
                        "UNKNOWN_TECHNICAL_EVALUATION_FAILED"
            del r
    detail=result["technical_status_by_symbol"]
    need(set(detail)==set(names),"EXACT_SCOPE_NEVER_TRUNCATED")
    result["technical_research_watch_symbols"]=sorted(
        sym for sym,s in detail.items() if s==WATCH)
    result["watch_membership_digest_sha256"]=sha256(json.dumps({
        "asof_et":asof,
        "technical_setup_family_verified":result["technical_setup_family_verified"]
    },sort_keys=True,separators=(",",":")).encode()).hexdigest()
    need(set(result["technical_setup_family_verified"])==
         set(result["technical_research_watch_symbols"]),
         "NO_UNVERIFIED_WATCH_FAMILY")
    result["classification_counts"]=dict(sorted(Counter(detail.values()).items()))
    need(sum(result["classification_counts"].values())==len(names),
         "EXACT_STATUS_PARTITION")
    result["all_symbols_classified"]=True
    result["full_identity_technical_scan_attested"]=outside_count==0
    result["status"]="ALL_COHORT_SYMBOLS_CLASSIFIED_RESEARCH_ONLY"
    return result


def selftest():
    from copy import deepcopy
    now=datetime(2026,10,14,22,tzinfo=timezone.utc)
    syms=["AAPL","BSP","NVDA"]
    scope={s:{"first_unresolved_gate":"PRICE_DV30",
              "causal_class":"RTH_30MIN_LOWER_BOUND_ONLY"} for s in syms}
    d={"schema":SOURCE,"asof_et":"2026-10-14","execution":"NONE",
       "real_money":"NO-GO","no_vendor_ohlcv_persisted":True,
       "no_canonical_mutations":True,"source_rights_not_inferred":True,
       "registered_r92_count":0,"c417_price_dv30_primary_attested":False,
       "issuer_class_mc_current_attested":False,
       "technical_a_b_d_r1_event_regime_attested":False,
       "scope_count":3,"per_symbol_causal_routing":scope,
       "next_gate_mc_sec_research_only_symbols":syms,
       "rth30_lower_bound_observed":3,
       "rth30_strict_complete_slot_lower_bound_observed":3,
       "rth30_partial_missing_slot_high_research_only_count":0,
       "rth30_partial_missing_slot_high_research_only_symbols":[],
       "rth30_partial_missing_slot_high_research_only_sha256":symbols_sha([]),
       "rth30_partial_research_never_primary":True,
       "rth30_partial_notional_is_proxy_not_trade_floor":True,
       "rth30_lower_bound_sha256":symbols_sha(syms),
       "first_unresolved_gate_counts":{"PRICE_DV30":3}}
    a,scope=cohort(d,now)
    need(a=="2026-10-14" and scope==syms,"BASE_SCOPE")
    def inaccessible(symbols,start,end,asof):
        raise RuntimeError("ALPACA_HTTP_403")
    result=run(d,now,inaccessible)
    partial=deepcopy(d)
    partial["rth30_strict_complete_slot_lower_bound_observed"]=2
    partial["rth30_partial_missing_slot_high_research_only_count"]=1
    partial["rth30_partial_missing_slot_high_research_only_symbols"]=["AAPL"]
    partial["rth30_partial_missing_slot_high_research_only_sha256"]=symbols_sha(["AAPL"])
    partial["per_symbol_causal_routing"]["AAPL"]["causal_class"]=(
        "RTH_OBSERVED_PARTIAL_BARLOW_PROXY_ONLY")
    p_asof,p_syms=cohort(partial,now)
    need(p_asof=="2026-10-14" and p_syms==syms and
         run(partial,now,inaccessible)["technical_research_watch_symbols"]==[],
         "PARTIAL_PROVEN_POSITIVE_SCOPE_NOT_A_SYNTHETIC_WATCH")
    partial_bad=deepcopy(partial)
    partial_bad["per_symbol_causal_routing"]["AAPL"]["causal_class"]=(
        "RTH_30MIN_LOWER_BOUND_ONLY")
    try:cohort(partial_bad,now)
    except ValueError:pass
    else:raise AssertionError("PARTIAL_FORGED_STRICT_CLASS_ACCEPTED")
    partial_bad=deepcopy(partial)
    partial_bad["rth30_partial_missing_slot_high_research_only_sha256"]="0"*64
    try:cohort(partial_bad,now)
    except ValueError:pass
    else:raise AssertionError("PARTIAL_FORGED_SHA_ACCEPTED")
    need(result["scope_count"]==3 and result["all_symbols_classified"] and
         result["technical_research_watch_symbols"]==[] and
         result["registered_r92_count"]==0 and not result["user_notification_sent"] and
         sum(result["classification_counts"].values())==3,
         "PROVIDER_OUTAGE_CANNOT_CREATE_WATCH")
    # Research budget telemetry must count failed vendor requests too.
    # Benchmark succeeds; first cohort batch raises transient transport;
    # second succeeds. No mocked input may imply independent technical GO.
    from unittest.mock import patch
    import stage1_shadow
    def benchmark_then_first_bad(syms,start,end,asof):
        calls.append(tuple(syms))
        if syms==["QQQ"]:
            return {"QQQ":[]}
        if syms==["AAPL"]:
            raise RuntimeError("SIMULATED_PROVIDER_503")
        return {sym:[] for sym in syms}
    calls=[]
    with (patch(__name__+".quality",
                return_value=([], "HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY")),
          patch(__name__+".assess",return_value=("NO_TECHNICAL_SETUP",0)),
          patch(__name__+".chunks",
                side_effect=lambda syms:[[syms[0]],syms[1:]]),
          patch.object(stage1_shadow,"build_week_last",return_value=[])):
        counted=run(d,now,benchmark_then_first_bad)
    need(calls==[("QQQ",),("AAPL",),("BSP","NVDA")] and
         counted["api_batches_attempted"]==3 and
         counted["technical_status_by_symbol"]["AAPL"]==
            "UNKNOWN_PROVIDER_BATCH_RuntimeError" and
         counted["registered_r92_count"]==0 and
         counted["technical_research_watch_symbols"]==[],
         "FAILED_PROVIDER_BATCH_NOT_ACCOUNTED_OR_PROMOTED")
    cliff_calls=[]
    def benchmark_then_403(syms,start,end,asof):
        cliff_calls.append(tuple(syms))
        if syms==["QQQ"]:return {"QQQ":[]}
        raise RuntimeError("SIMULATED_HTTP_403")
    with (patch(__name__+".quality",
                return_value=([], "HISTORICAL_SIP_260_52_RAW_RESEARCH_ONLY")),
          patch(__name__+".chunks",
                side_effect=lambda syms:[[syms[0]],syms[1:]]),
          patch.object(stage1_shadow,"build_week_last",return_value=[])):
        blocked=run(d,now,benchmark_then_403)
    need(cliff_calls==[("QQQ",),("AAPL",)] and
         blocked["api_batches_attempted"]==2 and
         blocked["technical_status_by_symbol"]["BSP"]==
            "UNKNOWN_UNATTEMPTED_UPSTREAM_CLIFF" and
         blocked["technical_status_by_symbol"]["NVDA"]==
            "UNKNOWN_UNATTEMPTED_UPSTREAM_CLIFF" and
         blocked["registered_r92_count"]==0,
         "PROVIDER_403_CLIFF_MUST_HAVE_EXACT_ATTEMPT_COUNT")
    # A complete technical scan of 3/4 eligible-source identities MUST NOT
    # masquerade as a complete scan of four (or of all NASDAQ securities).
    extended=deepcopy(d)
    extended["scope_count"]=4
    extended["per_symbol_causal_routing"]["ZZZ"]={
        "first_unresolved_gate":"HISTORY",
        "causal_class":"UNPROVEN_260_SESSIONS"}
    extended["first_unresolved_gate_counts"]={"HISTORY":1,"PRICE_DV30":3}
    partial=run(extended,now,inaccessible)
    # All 3 symbol records exist, but no RTH-positive evidence is allowed.
    # A zero research cohort is expected after a source outage, not CI failure.
    empty=deepcopy(d)
    empty["next_gate_mc_sec_research_only_symbols"]=[]
    empty["rth30_lower_bound_observed"]=0
    empty["rth30_strict_complete_slot_lower_bound_observed"]=0
    empty["rth30_lower_bound_sha256"]=symbols_sha([])
    for v in empty["per_symbol_causal_routing"].values():
        v["first_unresolved_gate"]="PRICE_DV30"
        v["causal_class"]="RTH_30MIN_UNKNOWN_NOT_ATTESTED"
    empty_result=run(empty,now,inaccessible)
    expected_digest=sha256(json.dumps({
        "asof_et":"2026-10-14","technical_setup_family_verified":{}
    },sort_keys=True,separators=(",",":")).encode()).hexdigest()
    need(empty_result["scope_count"]==0 and
         empty_result["source_causal_scope_count"]==3 and
         empty_result["outside_technical_cohort_count"]==3 and
         empty_result["status"]=="EMPTY_RESEARCH_COHORT_NOT_A_NO_SETUP_PROOF" and
         empty_result["technical_research_watch_symbols"]==[] and
         empty_result["watch_membership_digest_sha256"]==expected_digest and
         empty_result["registered_r92_count"]==0 and
         empty_result["all_symbols_classified"] is True and
         empty_result["full_identity_technical_scan_attested"] is False,
         "EMPTY_COHORT_MUST_PROVE_DIGEST_NO_FALSE_ZERO_OR_AL")
    need(partial["full_identity_source_partition_checked"] is True
         and partial["source_causal_scope_count"]==4
         and partial["scope_count"]==3
         and partial["outside_technical_cohort_count"]==1
         and partial["outside_technical_cohort_first_unresolved_gate_counts"]==
             {"HISTORY":1}
         and partial["all_symbols_classified"] is True
         and partial["full_identity_technical_scan_attested"] is False
         and partial["technical_cohort_is_universe_count"] is False
         and partial["registered_r92_count"]==0
         and partial["technical_research_watch_symbols"]==[],
         "NO_FALSE_FULL_UNIVERSE_TECHNICAL_COVERAGE")
    cases=[
        ("BAD_ASOF",lambda x:x.update(asof_et="2026-10-13")),
        ("FORGED_BARS",lambda x:x.update(no_vendor_ohlcv_persisted=False)),
        ("FORGED_PRIMARY",lambda x:x.update(c417_price_dv30_primary_attested=True)),
        ("FORGED_R92",lambda x:x.update(registered_r92_count=1)),
        ("SCOPE_TRUNCATED",lambda x:x["next_gate_mc_sec_research_only_symbols"].pop()),
        ("SHA_WRONG",lambda x:x.update(rth30_lower_bound_sha256="bad")),
        ("GATE_WRONG",lambda x:x["per_symbol_causal_routing"]["NVDA"].update(
            first_unresolved_gate="MC")),
    ]
    for name,change in cases:
        broken=deepcopy(d);change(broken)
        try:cohort(broken,now)
        except ValueError:pass
        else:raise AssertionError("XRAY_EARLY_WATCH_FORGED_SOURCE_ACCEPTED_"+name)
    print("XRAY_EARLY_WATCH_SELFTEST=PASS_FAILED_BATCH_503_403_EXACT_ATTEMPT_COUNTS_9_CAUSAL_NEGATIVES_NO_FALSE_WATCH")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--causal",type=Path)
    p.add_argument("--out",type=Path)
    opts=p.parse_args()
    if opts.selftest:selftest();return
    need(opts.causal is not None and opts.out is not None,
         "REQUIRE_CAUSAL_AND_PRIVATE_OUT")
    need(not opts.out.resolve().is_relative_to(Path(__file__).resolve().parent.parent),
         "NO_VENDOR_DERIVED_SYMBOLS_IN_PUBLIC_REPOSITORY")
    key=os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID")
    secret=os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY")
    need(bool(key and secret),"NO_PERSONAL_PROVIDER_KEYS")
    source=json.loads(opts.causal.read_text())
    result=run(source,datetime.now(timezone.utc),
       lambda syms,start,end,asof:request_batch(
           syms,start,end,key,secret,adjustment="raw",asof=asof))
    source_run=os.environ.get("XRAY_RESEARCH_UPSTREAM_RUN_ID","")
    need(source_run.isdecimal() and int(source_run)>0,
         "REQUIRE_PROVEN_UPSTREAM_GITHUB_RUN_ID")
    result["source_workflow_run_id"]=int(source_run)
    opts.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_EARLY_TECH_RESEARCH="+json.dumps({
        "asof":result["asof_et"],"scope":result["scope_count"],
        "verified_technical_research_watch_count":
            len(result["technical_research_watch_symbols"]),
        "partial_rth_research_scope_count":
            result["research_partial_rth_source_count"],
        "classification_counts":result["classification_counts"],
        "R92":0,"notification_sent":False},sort_keys=True))


if __name__=="__main__":main()
