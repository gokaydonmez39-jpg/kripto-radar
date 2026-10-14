#!/usr/bin/env python3
"""Resumable candidate-local C4.17 A/B/D technical research across ALL watch symbols.

Reads actual same-ASOF 260 regular-session daily OHLCV from the existing
Sina source/official ticker-continuity resolver, not price/DV30 snapshots
masquerading as 260/52 bars. Reuses original weekly, A/B/D and Final R1/RR
engines. Zero orders and no fabricated C4.17 AL, primary MC, regime or
event clear. Retains progress by watchlist source SHA; no top-N cap.
"""
from __future__ import annotations
import collections
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

SCHEMA="XRAY_ALL_CANDIDATES_C417_TECHNICAL_FUNNEL_V1"
# Provider history can recover within the same ASOF. Never freeze an unresolved
# daily/weekly history outcome as a completed scan, including legacy state.
RETRYABLE_HISTORY_STATUSES=frozenset({
    "UNKNOWN_260_OFFICIAL_HISTORY",
    "UNKNOWN_52_COMPLETED_WEEKS",
    "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY",
})
BATCH_SIZE=475
MAX_WORKERS=4


def need(ok, why):
    if not ok:
        raise ValueError("XRAY_ALL_CANDIDATE_TECH_"+why)


def engine_source_fingerprint():
    """Invalidate stored candidate decisions if ANY technical engine changes."""
    from pathlib import Path
    root=Path(__file__).resolve().parent
    names=("candidate_local_full_technical_funnel_v1.py",
           "stage1_shadow.py","deep_pre_r1_shadow.py",
           "final_tech_shadow.py","alpha_semantics.py",
           "candidate_local_independent_math_v1.py")
    data=[]
    for name in names:
        raw=(root/name).read_bytes()
        data.append((name,hashlib.sha256(raw).hexdigest()))
    return hashlib.sha256(json.dumps(data,separators=(",",":")).encode()).hexdigest()


def terminal_record(record):
    """A provider-history UNKNOWN must remain retryable, even in legacy state."""
    return (type(record) is dict
            and record.get("terminal_scan") is True
            and type(record.get("status")) is str
            and not record["status"].startswith("UNKNOWN")
            and record.get("status") not in RETRYABLE_HISTORY_STATUSES)

def technical_disposition(ready, any_watch, any_unresolved_geometry):
    """Retain valid candidate-local families; unresolved-only math stays retryable."""
    if ready:
        return "TECHNICAL_WATCH_NEEDS_PRIMARY", True
    if any_unresolved_geometry:
        return "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY", False
    if any_watch:
        return "WATCH_TRIGGER_WITH_FINAL_GATE_BLOCKERS", True
    return "TECHNICAL_GEOMETRY_NOT_APPROVED", True


def prepare(watch, old=None):
    """Persistent state is invalidated when exact WATCH source or ASOF changes."""
    need(type(watch) is dict
         and watch.get("schema")=="XRAY_MINIMAL_SWING_WATCH_RADAR_V1"
         and watch.get("all_eligible_candidates_tracked") is True
         and watch.get("watchlist_cap") is None,"COMPLETE_WATCH_REQUIRED")
    rows=watch.get("watchlist")
    need(type(rows) is list and
         len(rows)==watch.get("watchlist_count")==
                    watch.get("price_liquidity_screened_count"),
         "NO_SILENT_CANDIDATE_TRUNCATION")
    syms=[r.get("symbol") for r in rows]
    need(all(type(s) is str and s for s in syms)
         and len(set(syms))==len(syms),"UNIQUE_CANDIDATES")
    asof=watch.get("asof_et")
    source=watch.get("source_candidates_sha256")
    digest=watch.get("watchlist_digest")
    engine_sha=engine_source_fingerprint()
    need(type(asof) is str and len(asof)==10 and
         type(source) is str and len(source)==64 and
         type(digest) is str and len(digest)==64,
         "SOURCE_FINGERPRINTS")
    prev=old if type(old) is dict else {}
    reusable=(prev.get("schema")==SCHEMA and
        prev.get("asof_et")==asof and
        prev.get("source_candidates_sha256")==source and
        prev.get("watchlist_digest")==digest and
        prev.get("engine_source_sha256")==engine_sha and
        prev.get("candidate_count")==len(rows))
    prior=prev.get("results") if reusable else {}
    prior=prior if type(prior) is dict else {}
    kept={s:prior[s] for s in syms
          if s in prior and terminal_record(prior[s])}
    return {"schema":SCHEMA,"asof_et":asof,
            "engine_source_sha256":engine_sha,
            "source_candidates_sha256":source,
            "watchlist_digest":digest,
            "candidate_count":len(rows),"results":kept,
            "authority":"C417_CANDIDATE_LOCAL_TECHNICAL_RESEARCH_NO_RELEASE",
            "execution":"NONE","real_money":"NO-GO",
            "unknown_never_pass":True,"registered_r92_count":0,
            "automatic_orders":[]}


def summarize(state, watch):
    expected=[r["symbol"] for r in watch["watchlist"]]
    seen={s for s,r in state["results"].items()
          if terminal_record(r)}
    pending=[s for s in expected if s not in seen]
    stats=dict(sorted(collections.Counter(
        r.get("status","UNKNOWN") for r in state["results"].values()).items()))
    preliminary=[s for s in expected
        if terminal_record(state["results"].get(s))
        and state["results"][s].get("technical_observation_ready") is True]
    triggered=[s for s in expected
        if bool(state["results"].get(s,{}).get("confirmed_families"))]
    audits=[
        family["independent_geometry_audit"]
        for record in state["results"].values()
        if isinstance(record,dict)
        for family in (record.get("family_results") or {}).values()
        if isinstance(family,dict)
        and isinstance(family.get("independent_geometry_audit"),dict)
    ]
    verified=sum(a.get("independently_verified") is True for a in audits)
    state.update({"attempted_count":len(state["results"]),
                  "independent_math_audit_count":len(audits),
                  "independent_math_audit_verified_count":verified,
                  "independent_math_audit_unresolved_count":len(audits)-verified,
                  "transient_retry_count":len(state["results"])-len(seen),
                  "evaluated_count":len(seen),"pending_count":len(pending),
                  "pending_symbols":pending,
                  "full_scope_scanned":not pending,
                  "status_counts":stats,
                  "preliminary_technical_watch_count":len(preliminary),
                  "preliminary_technical_watch_symbols":preliminary,
                  "recent_a_b_d_trigger_count":len(triggered),
                  "recent_a_b_d_trigger_symbols":triggered,
                  "final_buy_signals":[],
                  "final_buy_signal_count":0,
                  "last_batch_source_mode":"SINA_US_DAILY_WITH_OFFICIAL_CALENDAR",
                  "remaining_primary_release_gates":[
                     "EXACT_PRIMARY_MARKET_CAP",
                     "ISSUER_SPLIT_CA_PIT",
                     "REGIME_BREADTH_FINALIST",
                     "EIGHT_SESSIONS_OFFICIAL_EVENT_CLEAR",
                     "LEGAL_NASDAQ_FULL_HALT",
                     "TERMINAL_SAME_ASOF_C417_APPROVAL",
                     "R92_LIFECYCLE_REGISTRY_AND_PLATFORM_DELIVERY"],
                  "provider_credits_assumed_available":False})
    need(len(seen)+len(pending)==len(expected) and
         not (seen-set(expected)),"FULL_PARTITION_EXACT")
    return state


def _history_ok(x, official_days):
    import pandas as pd
    if x is None or x.empty:return False
    if len(x)<260:return False
    df=x.iloc[-260:].reset_index(drop=True)
    try:
        dates=[d.date().isoformat() for d in pd.to_datetime(df["date"])]
        return (dates==official_days and
            all(df[k].notna().all() and
                all(math.isfinite(float(v)) and float(v)>0 for v in df[k])
                for k in ("open","high","low","close","volume")) and
            all(float(hi)>=max(float(lo),float(op),float(cl))
                and float(lo)<=min(float(op),float(cl))
                for hi,lo,op,cl in zip(df["high"],df["low"],
                                        df["open"],df["close"])))
    except (TypeError,ValueError,KeyError):
        return False


def official_260(asof):
    import pandas_market_calendars as mcal
    end=date.fromisoformat(asof)
    begin=end-timedelta(days=550)
    days=[d.date().isoformat() for d in
          mcal.get_calendar("NASDAQ").valid_days(
             start_date=begin.isoformat(),end_date=asof)]
    need(len(days)>=260 and days[-1]==asof,"OFFICIAL_LATEST_260_DAYS")
    return days[-260:]


def evaluate_one(sym, asof, calendar_days, week_last, qqq):
    """Never invent entry, stop or T1: Final eval_one computes original geometry."""
    import stage1_shadow as stage
    import deep_pre_r1_shadow as deep
    import final_tech_shadow as final
    from candidate_local_independent_math_v1 import audit as audit_final_geometry
    from alpha_semantics import mechanical_scale_breaks, mechanical_split_suspects
    try:
        data,source=stage.load_history(sym,asof)
        if not _history_ok(data,calendar_days):
            return sym,{"status":"UNKNOWN_260_OFFICIAL_HISTORY",
                        "history_source":source,"terminal_scan":False}
        data=data.iloc[-260:].reset_index(drop=True)
        anomalies=mechanical_scale_breaks(data,260) or mechanical_split_suspects(data,260)
        ca_status="PASS_NO_LOCAL_SPLIT_DISCONTINUITY"
        if anomalies:
            updated,ca_status,events=stage.split_consistent_history(sym,data,260)
            if not str(ca_status).startswith("PASS") or not _history_ok(updated,calendar_days):
                return sym,{"status":"UNKNOWN_CORPORATE_ACTION_PIT",
                            "split_reconciliation_status":ca_status,
                            "history_source":source,"terminal_scan":False}
            data=updated.reset_index(drop=True)
        current_week=stage.weekly_gate(data,asof,week_last)
        eligible,ctx=stage.recent_weekly_context(data,week_last)
        if current_week.get("weeks",0)<52:
            return sym,{"status":"UNKNOWN_52_COMPLETED_WEEKS",
                        "completed_weeks":current_week.get("weeks",0),
                        "history_source":source,"terminal_scan":False}
        if not eligible:
            return sym,{"status":"NO_CURRENT_OR_RECENT_WEEKLY_GATE",
                        "completed_weeks":current_week.get("weeks",0),
                        "history_source":source,"terminal_scan":True}
        a,b,d=deep.evaluate_recent_families(data,qqq,eligible)
        geometries={"A":a,"B":b,"D":d}
        pass_families={k:g for k,g in geometries.items()
            if (g.get("pool") is True and g.get("trigger_date") in eligible
                and (k=="A" or k=="D" and g.get("dk3_pre_r1") is True
                     or k=="B" and g.get("breakout_confirmed") is True))}
        if not pass_families:
            return sym,{"status":"NO_CONFIRMED_A_B_D_RECENT_TRIGGER",
                        "completed_weeks":current_week.get("weeks",0),
                        "history_source":source,"terminal_scan":True}
        family_results={}
        ready=False
        any_watch=False
        any_unresolved_geometry=False
        for family,g in pass_families.items():
            z=final.eval_one(sym,family,g,data,
                event_status="UNKNOWN",state_cap="WATCH",
                r92_eligible=False,regime_finalist_status="UNKNOWN")
            any_watch=any_watch or str(z.get("result","")).startswith("WATCH")
            # Independent fail-closed arithmetic and historical stop audit.
            # R1 source-zone discovery and issuer corporate actions stay separate.
            math_audit=audit_final_geometry(family,g,z,data)
            any_unresolved_geometry=(any_unresolved_geometry or
                math_audit.get("independently_verified") is not True)
            levels=z.get("levels") or {}
            rr=z.get("rr") or {}
            eligible_levels=all(type(levels.get(k)) in (int,float)
               and math.isfinite(levels[k]) and levels[k]>0
               for k in ("entry_low","entry_high","S0","T1"))
            risk=bool(z.get("risk_pass") is True and
                rr.get("basic_pass") is True and
                rr.get("severe_pass") is True and
                z.get("target_overlap") is False and
                z.get("extension_veto") is False and
                z.get("lifecycle") in {"ENTRY_BAND","RETEST_ENTRY_BAND"}
                and not (z.get("invalidation") or {}).get("breached")
                and eligible_levels
                and math_audit.get("independently_verified") is True)
            ready=ready or risk
            family_results[family]={
                "status":"WATCH_R1_RR_TECHNICAL_ONLY" if risk else z.get("result","UNKNOWN"),
                "risk_rr_geometry_observed":risk,
                "entry_usd":round(levels["entry_model"],4) if risk else None,
                "entry_band_usd":[round(levels["entry_low"],4),
                                  round(levels["entry_high"],4)] if risk else None,
                "structural_stop_usd":round(levels["S0"],4) if risk else None,
                "target_t1_usd":round(levels["T1"],4) if risk else None,
                "risk_percent":round(100*z["geometry"]["risk_percent"],3)
                    if risk else None,
                "basic_rr":round(rr["basic"],3) if risk else None,
                "severe_rr":round(rr["severe"],3) if risk else None,
                "trigger_date":g.get("trigger_date"),
                "setup_id":z.get("setup_id"),
                "source_r1_target":(z.get("target") or {}).get("source"),
                "independent_geometry_audit":math_audit,
                "diagnostic_only_reason":z.get("reason"),
                "diagnostic_only_not_trade_signal":True,
                "diagnostic_only_entry_stop_target":({
                    "entry_model_usd":round(float(levels["entry_model"]),4),
                    "stop_s0_usd":round(float(levels["S0"]),4),
                    "target_t1_usd":round(float(levels["T1"]),4)}
                    if eligible_levels and type(levels.get("entry_model"))
                           in (int,float) and
                           math.isfinite(levels["entry_model"]) and
                           levels["entry_model"]>0 else None),
                "diagnostic_blockers":list(z.get("diagnostic_blockers") or []),
                "event_primary_status":"UNKNOWN",
                "regime_primary_status":"UNKNOWN",
                "final_AL":False}
        disposition, complete = technical_disposition(
            ready, any_watch, any_unresolved_geometry)
        return sym,{"status":disposition,
                    "family_results":family_results,
                    "confirmed_families":sorted(pass_families),
                    "technical_observation_ready":ready,
                    "completed_weeks":current_week.get("weeks",0),
                    "history_source":source,"terminal_scan":complete}
    except Exception as exc:
        return sym,{"status":"UNKNOWN_TECHNICAL_PROVIDER_OR_ENGINE",
                    "error_type":type(exc).__name__,
                    "terminal_scan":False}


def progress(watch,old=None,batch_size=BATCH_SIZE):
    """One bounded unattended batch, with exact candidate-local partition."""
    import stage1_shadow as stage
    from alpha_semantics import mechanical_scale_breaks,mechanical_split_suspects
    need(type(batch_size) is int and 1<=batch_size<=500,"BOUNDED_BATCH")
    state=prepare(watch,old)
    all_symbols=[x["symbol"] for x in watch["watchlist"]]
    pending=[sym for sym in all_symbols if sym not in state["results"]]
    if not pending:return summarize(state,watch)
    asof=watch["asof_et"]
    calendar_days=official_260(asof)
    week_last=stage.build_week_last(asof)
    qqq,src=stage.load_history("QQQ",asof)
    if not _history_ok(qqq,calendar_days):
        state["benchmark_status"]="UNKNOWN_QQQ_OFFICIAL_260_HISTORY"
        return summarize(state,watch)
    qqq=qqq.iloc[-260:].reset_index(drop=True)
    if mechanical_scale_breaks(qqq,260) or mechanical_split_suspects(qqq,260):
        state["benchmark_status"]="UNKNOWN_QQQ_CORPORATE_ACTION"
        return summarize(state,watch)
    state["benchmark_status"]="QQQ_260_COMPLETED_RTH_BARS_OBSERVED"
    sub=pending[:batch_size]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        tasks=[executor.submit(evaluate_one,sym,asof,calendar_days,week_last,qqq)
               for sym in sub]
        for fut in as_completed(tasks):
            sym,record=fut.result()
            if (sym=="FROG" and
                (watch.get("candidate_local_special_review") or {})
                    .get("known_issuer_event_block") is True and
                watch["asof_et"]=="2026-10-13"):
                record["official_issuer_eight_session_event_veto"]=True
                record["r92_blocker"]="ISSUER_EVENT_OCT20_22_2026"
                if record.get("technical_observation_ready") is True:
                    record["status"]="TECHNICAL_WATCH_OFFICIAL_ISSUER_EVENT_VETO"
            state["results"][sym]=record
    return summarize(state,watch)


def selftest():
    from candidate_local_independent_math_v1 import selftest as math_selftest
    math_selftest()
    def w(asof="2026-10-13"):
        a=[{"symbol":s} for s in ("AAPL","FROG","NVDA")]
        return {"schema":"XRAY_MINIMAL_SWING_WATCH_RADAR_V1",
          "asof_et":asof,"source_candidates_sha256":"a"*64,
          "watchlist_digest":"b"*64,"watchlist":a,
          "watchlist_count":3,"price_liquidity_screened_count":3,
          "watchlist_cap":None,"all_eligible_candidates_tracked":True}
    a=prepare(w())
    need(len(a["results"])==0 and
         summarize(a,w())["pending_count"]==3,"INITIAL_ALL_PENDING")
    a["results"]["NVDA"]={"status":"TECHNICAL_WATCH_NEEDS_PRIMARY",
          "terminal_scan":True,"technical_observation_ready":True,
          "family_results":{"D":{"independent_geometry_audit":
                                     {"independently_verified":True}}}}
    b=prepare(w(),a)
    full=summarize(b,w())
    need(full["evaluated_count"]==1 and
         full["pending_count"]==2 and
         full["preliminary_technical_watch_symbols"]==["NVDA"]
         and not full["final_buy_signals"],"PARTIAL_PROGRESS_WITHOUT_FAKE_BUY")
    need(full["independent_math_audit_count"]==1
         and full["independent_math_audit_verified_count"]==1
         and full["independent_math_audit_unresolved_count"]==0,
         "INDEPENDENT_MATH_AUDIT_COUNTS")
    a["results"]["NVDA"]["family_results"]["D"]["independent_geometry_audit"]={
        "independently_verified":False}
    unresolved=summarize(a,w())
    need(unresolved["independent_math_audit_unresolved_count"]==1
         and unresolved["independent_math_audit_verified_count"]==0,
         "UNRESOLVED_MATH_NEVER_COUNTED_AS_VERIFIED")
    changed=prepare(w("2026-10-14"),a)
    need(changed["results"]=={},"ASOF_INVALIDATES_STALE_TRIGGERS")
    malformed=w()
    malformed["watchlist_count"]=2
    try:prepare(malformed)
    except ValueError:pass
    else:raise AssertionError("TRUNCATED_SCOPE_ACCEPTED")
    mark=w()
    mark["all_eligible_candidates_tracked"]=False
    try:prepare(mark)
    except ValueError:pass
    else:raise AssertionError("TOP_N_ACCEPTED")
    need(BATCH_SIZE>=475 and MAX_WORKERS<=4,
         "FULL_SCOPE_BATCH_NO_UNBOUNDED_CONCURRENT_PROVIDER_CALLS")
    for ready in (False, True):
        for watch_hit in (False, True):
            for unresolved in (False, True):
                disposition, complete = technical_disposition(
                    ready, watch_hit, unresolved)
                if ready:
                    need(disposition=="TECHNICAL_WATCH_NEEDS_PRIMARY"
                         and complete, "VALID_FAMILY_MUST_NOT_BE_GLOBALLY_VETOED")
                elif unresolved:
                    need(disposition=="UNKNOWN_FROZEN_TECHNICAL_GEOMETRY"
                         and not complete, "MIXED_UNKNOWN_MATH_CANNOT_TERMINATE")
                else:
                    need(disposition in ("WATCH_TRIGGER_WITH_FINAL_GATE_BLOCKERS",
                                         "TECHNICAL_GEOMETRY_NOT_APPROVED")
                         and complete, "PROVEN_NONPASS_TERMINATES")
    for status in ("UNKNOWN","UNKNOWN_LEGACY","UNKNOWN_PROVIDER_ERROR"):
        need(not terminal_record({"status":status,"terminal_scan":True}),
             "ALL_UNKNOWN_VARIANTS_REMAIN_RETRYABLE")
    # Regression: the previous version incorrectly accepted these as terminal.
    # This must fail for both new and already-persisted legacy rows.
    for status in RETRYABLE_HISTORY_STATUSES:
        historical=prepare(w())
        historical["results"]["AAPL"]={"status":status,"terminal_scan":True}
        reloaded=prepare(w(),historical)
        need("AAPL" not in reloaded["results"],
             "LEGACY_HISTORY_UNKNOWN_MUST_RETRY_"+status)
        checked=summarize(historical,w())
        need(checked["evaluated_count"]==0
             and checked["pending_count"]==3
             and checked["transient_retry_count"]==1,
             "HISTORY_UNKNOWN_CANNOT_COUNT_COMPLETE_"+status)
    reliable=prepare(w())
    reliable["results"]["AAPL"]={"status":"NO_CURRENT_OR_RECENT_WEEKLY_GATE",
                                 "terminal_scan":True}
    need("AAPL" in prepare(w(),reliable)["results"],
         "REAL_TERMINAL_CLASSIFICATION_MUST_REUSE")
    for status in ("UNKNOWN_TECHNICAL_PROVIDER_OR_ENGINE",
                   "UNKNOWN_FROZEN_TECHNICAL_GEOMETRY"):
        legacy=prepare(w())
        legacy["results"]["AAPL"]={"status":status,"terminal_scan":True,
                                   "technical_observation_ready":True}
        checked=summarize(legacy,w())
        need(checked["pending_count"]==3 and
             checked["evaluated_count"]==0 and
             checked["preliminary_technical_watch_count"]==0,
             "UNKNOWN_NEVER_TERMINAL_OR_READY_"+status)
        need(not prepare(w(),legacy)["results"],
             "UNKNOWN_LEGACY_RETRY_"+status)
    with_transient=prepare(w())
    with_transient["results"]["AAPL"]={
        "status":"UNKNOWN_CORPORATE_ACTION_PIT","terminal_scan":False}
    transient=summarize(with_transient,w())
    need(transient["attempted_count"]==1 and
         transient["evaluated_count"]==0 and
         transient["pending_count"]==3 and
         transient["transient_retry_count"]==1,
         "NO_FALSE_COMPLETION_ON_RETRYABLE_PROVIDER_ERROR")
    print("XRAY_ALL_CANDIDATE_C417_TECH_SELFTEST=PASS_LOCAL_RESUME_ALL_WATCHED_NO_FAKED_AL")


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--watch",type=Path)
    parser.add_argument("--previous",type=Path)
    parser.add_argument("--batch-size",type=int,default=BATCH_SIZE)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.selftest:return selftest()
    need(args.watch and args.out,"WATCH_AND_OUTPUT_REQUIRED")
    watch=json.loads(args.watch.read_text())
    prior=(json.loads(args.previous.read_text())
           if args.previous and args.previous.is_file() else {})
    out=progress(watch,prior.get("candidate_technical_funnel"),args.batch_size)
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"scope":out["candidate_count"],
      "processed":out["evaluated_count"],"pending":out["pending_count"],
      "technical_watch":out["preliminary_technical_watch_count"],
      "benchmark":out.get("benchmark_status"),
      "signals":0},sort_keys=True))


if __name__=="__main__":main()
