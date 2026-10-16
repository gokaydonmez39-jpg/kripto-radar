#!/usr/bin/env python3
"""Personal NASDAQ X-RAY six-gate causal dependency resolver.

Consumes SAME-RUN source, 260/52, exact-root bridge and 30Min RTH research
receipts. Produces a per-symbol next SAFE evidence action, not a pass.
Deliberately cannot manufacture canonical PRICE, HISTORY, MC, technical,
R92, notification receipt, licensed data rights or trading authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

from source_epoch_freshness_guard import last_complete_session
from alpaca_full_universe_asof_sip_availability import sha as scope_sha
from alpaca_personal_joint_260_d30_rth_shadow import (
    PARTIAL_HIGH, PARTIAL_UNRESOLVED, PARTIAL_REJECTED,
)
from alpaca_full_universe_30d_daily_proxy_shadow import (
    VALID as D30_HIGH, LOW_PRICE as D30_LOW_PRICE, LOW_DV as D30_LOW_DV,
)

ROOT = Path(__file__).resolve().parent
SCHEMA = "XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1"
DAILY_SCHEMA = "XRAY_ALPACA_PERSONAL_UNIVERSE_ASOF_SIP_COVERAGE_V1"
HISTORY_SCHEMA = "XRAY_PERSONAL_FULL_NASDAQ_SIP_260_DAILY_52_WEEK_RESEARCH_V1"
BRIDGE_SCHEMA = "XRAY_PERSONAL_SIP_ROOT_SOURCE_BRIDGE_V1"
RTH_SCHEMA = "XRAY_PERSONAL_JOINT_HISTORY_DAILY30_EXACT_RTH30_BOUND_V1"
DAY_OK = "OBSERVED_SIP_DAILY_ASOF_SHADOW"
HIST_OK = "SHADOW_260_DAILY_52_WEEK_OBSERVED"
RTH_HIGH = "LOWER_BOUND_GE_50M_SHADOW"
RTH_MID = "AMBIGUOUS_BETWEEN_BOUNDS_SHADOW"
RTH_LOW = "UPPER_BOUND_LT_50M_SHADOW"
RTH_UNKNOWN = "UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
RTH_PROVIDER = "UNKNOWN_HISTORICAL_SIP_RTH_PROVIDER_STOP"
STAGES = ("SOURCE", "HISTORY", "PRICE_DV30", "MC", "TECH", "R92_DELIVERY")


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_SIX_GATE_" + reason)


def partition(obj, key, counts_key, names):
    values = obj.get(key)
    counts = obj.get(counts_key)
    need(type(values) is dict and set(values) == set(names) and
         all(type(v) is str and v for v in values.values()),
         "SYMBOL_SCOPE_" + key)
    need(type(counts) is dict and
         counts == dict(sorted(Counter(values.values()).items())),
         "EXACT_PARTITION_" + key)
    return values


def route(symbol, source, history, history_reason, d30, rth):
    """Single first unresolved prerequisite, plus independent parallel research."""
    if source != DAY_OK:
        return ("SOURCE", "LATEST_ASOF_BAR_UNPROVEN",
                "RETRY_DELAYED_SIP_DAILY_ON_OFFICIAL_SESSION", "NONE")
    if history != HIST_OK:
        if history_reason == "OFFICIAL_SAME_ISSUER_FIRST_TRADE_LT260_VETO":
            action = "KEEP_OFFICIAL_LT260_VETO_NO_HISTORY_PROMOTION"
        elif history_reason.startswith("MISSING_LEADING_ONLY_"):
            action = "CHECK_OFFICIAL_ISSUER_FIRST_TRADE_NOT_TICKER_AGE"
        elif history_reason == "ZERO_OR_NEGATIVE_RECORDED_VOLUME":
            action = "RECHECK_EXACT_ZERO_VOLUME_HISTORICAL_SESSIONS"
        elif history_reason.startswith("MISSING_"):
            action = "VERIFY_EXACT_OFFICIAL_DATE_GAPS_AND_SOURCE"
        elif history_reason == "NO_SOURCE_BAR":
            action = "CHECK_LISTING_AND_INDEPENDENT_HISTORICAL_SOURCE"
        else:
            action = "RECONCILE_260_OFFICIAL_SESSIONS_AND_ISSUER"
        # Do not make a history pass from any good 30-day source proxy.
        return ("HISTORY", history_reason, action,
                "DAILY30_SHADOW_CAN_BE_RESEARCHED_INDEPENDENTLY")
    if d30 != D30_HIGH:
        if d30 == D30_LOW_PRICE:
            action = "RECHECK_CURRENT_COMPLETED_RTH_PRICE_GE5"
        elif d30 == D30_LOW_DV:
            action = "CHECK_EXACT30_RTH_DOLLAR_VOLUME_INDEPENDENTLY"
        else:
            action = "REPAIR_EXACT30_SIP_DATE_OR_VOLUME_SOURCE"
        return ("PRICE_DV30", d30, action, "NONE")
    if rth == RTH_HIGH:
        return ("PRICE_DV30", "RTH_30MIN_LOWER_BOUND_ONLY",
                "PROVE_OFFICIAL_RTH_AUCTION_CORRECTIONS_SPLITS_AND_RIGHTS",
                "VERIFY_SEC_ISSUER_CLASS_MC_2B_INDEPENDENTLY")
    if rth == RTH_MID:
        return ("PRICE_DV30", "RTH_30MIN_BOUNDS_AMBIGUOUS",
                "RECONCILE_AUCTION_AND_CORRECTED_RTH_VOLUME",
                "VERIFY_SEC_ISSUER_CLASS_MC_ONLY_AS_SHADOW")
    if rth == RTH_LOW:
        return ("PRICE_DV30", "RTH_DAILY_UPPER_LT50M",
                "VALIDATE_VENUE_RTH_VOLUME_AND_SOURCE_CONFLICT", "NONE")
    if rth in (RTH_UNKNOWN, RTH_PROVIDER):
        return ("PRICE_DV30", "RTH_DATA_INTEGRITY_OR_PROVIDER_UNKNOWN",
                "ISOLATE_BAD_30MIN_SESSION_OR_PROVIDER_BATCH", "NONE")
    raise ValueError("XRAY_SIX_GATE_RTH_UNKNOWN_CLASS_FOR_" + symbol)


def build(day, hist, bridge, rth, now, source_digests=None):
    need(type(now) is dt.datetime and now.tzinfo is not None and
         all(type(x) is dict for x in (day, hist, bridge, rth)),
         "INPUT_SHAPES")
    current = last_complete_session(now)
    need(all(x.get("asof_et") == current for x in (day, hist, bridge, rth)),
         "LATEST_COMPLETE_NASDAQ_SESSION")
    need(day.get("schema") == DAILY_SCHEMA and
         hist.get("schema") == HISTORY_SCHEMA and
         bridge.get("schema") == BRIDGE_SCHEMA and
         rth.get("schema") == RTH_SCHEMA, "SOURCE_SCHEMA")
    need(all(x.get("execution") == "NONE" and x.get("real_money") == "NO-GO"
             for x in (day, hist, bridge, rth)), "NO_TRADING")
    need(day.get("no_vendor_ohlcv_persisted") is True and
         day.get("no_canonical_promotion") is True and
         hist.get("no_vendor_ohlcv_persisted") is True and
         hist.get("canonical_price_history_mc_untouched") is True and
         bridge.get("no_c417_dv30_or_mc_pass") is True and
         bridge.get("no_vetted_r92_or_delivery") is True and
         bridge.get("joint_scope_has_no_rth_mc_technical_or_signal_authority") is True and
         rth.get("official_c417_primary_dv30_attested") is False and
         rth.get("official_RTH_close_auction_volume_attested") is False and
         rth.get("official_RTH_corrections_attested") is False and
         rth.get("vendor_ohlcv_persisted") is False and
         rth.get("canonical_master_price_history_mc_untouched") is True and
         all(x.get("registered_R92_count") == 0 for x in (day, hist, rth)),
         "NO_FALSE_GATE_AUTHORITY")
    names = sorted((day.get("symbol_classifications") or {}).keys())
    need(names and len(names) <= 6500 and
         len(names) == hist.get("scope_count") ==
         bridge.get("identity_scope_count") == day.get("measured_scope_count") ==
         day.get("source_sina_queue_count"), "FULL_IDENTITY_SCOPE")
    fp = scope_sha(names)
    need(fp == day.get("source_sina_queue_sha256") ==
         hist.get("source_full_identity_queue_sha256") ==
         bridge.get("exact_identity_queue_sha256") and
         bridge.get("same_asof_same_universe_join") is True,
         "ROOT_QUEUE_SHA_JOIN")
    day_labels = partition(day, "symbol_classifications",
                           "classification_counts", names)
    hist_labels = partition(hist, "symbol_classifications",
                            "classification_counts", names)
    causes = partition(hist, "symbol_nonpass_cause_classes",
                       "history_nonpass_cause_counts", names)
    d30_source = hist.get("daily30_source_proxy")
    need(type(d30_source) is dict and
         d30_source.get("research_daily_proxy_not_official_rth_dv30") is True,
         "DAILY30_NOT_PRIMARY")
    d30 = partition(d30_source, "symbol_classifications",
                    "classification_counts", names)
    cohort = sorted(sym for sym in names
                    if hist_labels[sym] == HIST_OK and d30[sym] == D30_HIGH)
    need(len(cohort) == bridge.get(
         "260_52_and_daily30_ge50m_joint_research_count") ==
         rth.get("joint_cohort_count") and
         scope_sha(cohort) == bridge.get(
             "260_52_and_daily30_ge50m_joint_sha256") ==
         rth.get("joint_history260_daily30_cohort_sha256"),
         "260_DAILY30_RTH_EXACT_COHORT_SHA")
    rth_labels = partition(rth, "classifications",
                           "classification_counts", cohort)
    # Independent symbolic evidence, strictly a subset of strict UNKNOWN.
    # Never overwrite canonical/strict labels; permit only parallel research.
    partial = rth.get("partial_missing_slot_research_by_symbol")
    causes_rth = rth.get("symbol_rth_integrity_failure_codes")
    need(type(partial) is dict and type(causes_rth) is dict and
         rth.get("partial_missing_slot_symbolic_only_never_canonical") is True and
         rth.get("partial_notional_method")==
             "SUM_OBSERVED_30MIN_BAR_LOW_TIMES_VOLUME_PER_OFFICIAL_SESSION" and
         rth.get("partial_no_daily_close_proxy_or_unobserved_zero_fill") is True and
         rth.get("partial_notional_source_trade_conditions_unattested") is True and
         rth.get("partial_notional_proxy_not_mathematical_trade_floor") is True and
         set(partial) == {sym for sym,why in causes_rth.items()
             if why == "EARLY_AND_FULL_BAR_COUNTS_EXACT"} and
         set(causes_rth).issubset(cohort) and
         all(rth_labels[sym] == RTH_UNKNOWN for sym in partial) and
         set(partial.values()).issubset({
             PARTIAL_HIGH, PARTIAL_UNRESOLVED, PARTIAL_REJECTED}) and
         dict(sorted(Counter(partial.values()).items())) ==
         rth.get("partial_missing_slot_research_counts") and
         dict(sorted(Counter(causes_rth.values()).items())) ==
         rth.get("rth_integrity_cause_counts"),
         "PARTIAL_RESEARCH_SOURCE_INTEGRITY_NEVER_STRICT_PASS")
    partial_high = sorted(sym for sym,kind in partial.items()
                          if kind == PARTIAL_HIGH)
    need(rth.get("official_session_count") == 30 and
         rth.get("source_rights_not_inferred") is True and
         rth.get("registered_R92_count") == 0 and
         sum(rth["classification_counts"].values()) == len(cohort),
         "RTH_NOT_PRIMARY_OR_COUNT")
    need(sum(v == RTH_HIGH for v in rth_labels.values()) ==
         rth.get("rth_lower_bound_ge50m_shadow_count"),
         "RTH_HIGH_COUNT_INCONSISTENT")
    need(hist.get("full_history_260_52_observed_count") ==
         bridge.get("260_daily_52_week_observed") ==
         sum(x == HIST_OK for x in hist_labels.values()) and
         sum(x == DAY_OK for x in day_labels.values()) ==
         bridge.get("daily_asof_bar_observed"),
         "SOURCE_HISTORY_COUNTS")
    details = {}
    actions = Counter()
    primary = Counter()
    for sym in names:
        stage, reason, action, parallel = route(
            sym, day_labels[sym], hist_labels[sym], causes[sym],
            d30[sym], rth_labels.get(sym))
        details[sym] = {
            "first_unresolved_gate": stage,
            "causal_class": reason,
            "next_safe_evidence_action": action,
            "parallel_research_only": parallel,
        }
        primary[stage] += 1
        actions[action] += 1
    need(sum(primary.values()) == len(names) and
         all(d["first_unresolved_gate"] in STAGES[:3]
             for d in details.values()), "NO_UNPROVEN_PROMOTION")
    strict_high = sorted(sym for sym in cohort if rth_labels[sym] == RTH_HIGH)
    high = sorted(set(strict_high) | set(partial_high))
    need(set(strict_high).isdisjoint(partial_high) and
         len(strict_high) == rth["rth_lower_bound_ge50m_shadow_count"] and
         len(high) == len(strict_high)+len(partial_high) and
         all(details[sym]["first_unresolved_gate"] == "PRICE_DV30"
             for sym in high), "RESEARCH_HIGH_NEVER_PRIMARY")
    for sym in partial_high:
        need(details[sym]["causal_class"] == "RTH_DATA_INTEGRITY_OR_PROVIDER_UNKNOWN",
             "PARTIAL_CANNOT_OVERRIDE_OTHER_CAUSAL_GATE")
        details[sym]["causal_class"] = "RTH_OBSERVED_PARTIAL_BARLOW_PROXY_ONLY"
        details[sym]["parallel_research_only"] = (
            "EVALUATE_TECHNICAL_A_B_D_ONLY_WITH_INDEPENDENT_DAILY_HISTORY")
        # First unresolved source action is retained.
        need(details[sym]["next_safe_evidence_action"] ==
             "ISOLATE_BAD_30MIN_SESSION_OR_PROVIDER_BATCH",
             "PARTIAL_RTH_NEXT_SAFE_EVIDENCE_UNCHANGED")
    return {
        "schema": SCHEMA,
        "asof_et": current,
        "exact_root_identity_scope_sha256": fp,
        "scope_count": len(names),
        "input_report_sha256": source_digests or {},
        "six_gate_dependency_order": list(STAGES),
        "research_only_causal_next_action": True,
        "source_day_observed": sum(x == DAY_OK for x in day_labels.values()),
        "history260_52_observed": sum(x == HIST_OK for x in hist_labels.values()),
        "daily30_high_liquidity_proxy_count": sum(x == D30_HIGH for x in d30.values()),
        "joint260_daily30_research_scope": len(cohort),
        "rth30_lower_bound_observed": len(high),
        "rth30_strict_complete_slot_lower_bound_observed": len(strict_high),
        "rth30_partial_missing_slot_high_research_only_count": len(partial_high),
        "rth30_partial_missing_slot_high_research_only_symbols": partial_high,
        "rth30_partial_missing_slot_high_research_only_sha256":
            scope_sha(partial_high),
        "rth30_partial_research_never_primary": True,
        "rth30_partial_notional_is_proxy_not_trade_floor":True,
        "rth30_lower_bound_sha256": scope_sha(high),
        "rth30_ambiguous_count": sum(x == RTH_MID for x in rth_labels.values()),
        "rth30_data_unknown_count": sum(x in (RTH_UNKNOWN, RTH_PROVIDER)
                                        for x in rth_labels.values()),
        "next_gate_mc_sec_research_only_symbols": high,
        "first_unresolved_gate_counts": dict(sorted(primary.items())),
        "next_safe_evidence_action_counts": dict(sorted(actions.items())),
        "per_symbol_causal_routing": details,
        "issuer_class_mc_current_attested": False,
        "c417_price_dv30_primary_attested": False,
        "technical_a_b_d_r1_event_regime_attested": False,
        "registered_r92_count": 0,
        "iphone_device_delivery_attested": False,
        "no_vendor_ohlcv_persisted": True,
        "no_canonical_mutations": True,
        "source_rights_not_inferred": True,
        "execution": "NONE", "real_money": "NO-GO",
        "status": "SIX_GATE_DEPENDENCY_ROUTED_RESEARCH_NO_AL",
    }


def selftest():
    asof = "2026-10-14"
    now = dt.datetime(2026, 10, 14, 22, tzinfo=dt.timezone.utc)
    names = ["AAA", "BBB", "CCC", "DDD"]
    fp = scope_sha(names)
    base = {"asof_et": asof, "execution": "NONE", "real_money": "NO-GO"}
    day_labels = {"AAA":DAY_OK, "BBB":DAY_OK, "CCC":DAY_OK,
                  "DDD":"UNKNOWN_DAILY_MISSING_OR_INTEGRITY"}
    hlabels = {"AAA":HIST_OK, "BBB":"INVALID_OHLCV_OR_ZERO_VOLUME",
               "CCC":HIST_OK, "DDD":"NO_BAR"}
    causes = {"AAA":"260_52_OBSERVED_RESEARCH_ONLY",
              "BBB":"ZERO_OR_NEGATIVE_RECORDED_VOLUME",
              "CCC":"260_52_OBSERVED_RESEARCH_ONLY",
              "DDD":"NO_SOURCE_BAR"}
    d30 = {"AAA":D30_HIGH, "BBB":D30_HIGH, "CCC":D30_LOW_DV,
           "DDD":"UNKNOWN_DAILY30_ASOF_MISSING"}
    def counts(d): return dict(sorted(Counter(d.values()).items()))
    day = dict(base, schema=DAILY_SCHEMA, symbol_classifications=day_labels,
               classification_counts=counts(day_labels),
               measured_scope_count=4, source_sina_queue_count=4,
               source_sina_queue_sha256=fp,
               no_vendor_ohlcv_persisted=True, no_canonical_promotion=True,
               registered_R92_count=0)
    hist = dict(base, schema=HISTORY_SCHEMA, scope_count=4,
                source_full_identity_queue_sha256=fp,
                symbol_classifications=hlabels,
                classification_counts=counts(hlabels),
                symbol_nonpass_cause_classes=causes,
                history_nonpass_cause_counts=counts(causes),
                full_history_260_52_observed_count=2,
                no_vendor_ohlcv_persisted=True,
                canonical_price_history_mc_untouched=True,
                registered_R92_count=0,
                daily30_source_proxy={
                    "symbol_classifications":d30,
                    "classification_counts":counts(d30),
                    "research_daily_proxy_not_official_rth_dv30":True})
    bridge = dict(base, schema=BRIDGE_SCHEMA,
                  identity_scope_count=4,
                  exact_identity_queue_sha256=fp,
                  same_asof_same_universe_join=True,
                  daily_asof_bar_observed=3,
                  **{"260_daily_52_week_observed":2},
                  **{"260_52_and_daily30_ge50m_joint_research_count":1},
                  **{"260_52_and_daily30_ge50m_joint_sha256":scope_sha(["AAA"])},
                  no_c417_dv30_or_mc_pass=True,
                  no_vetted_r92_or_delivery=True,
                  joint_scope_has_no_rth_mc_technical_or_signal_authority=True)
    rth_labels = {"AAA":RTH_HIGH}
    rth = dict(base, schema=RTH_SCHEMA, joint_cohort_count=1,
               joint_history260_daily30_cohort_sha256=scope_sha(["AAA"]),
               classifications=rth_labels,
               classification_counts=counts(rth_labels),
               rth_lower_bound_ge50m_shadow_count=1,
               partial_missing_slot_research_by_symbol={},
               partial_missing_slot_research_counts={},
               partial_missing_slot_symbolic_only_never_canonical=True,
               partial_notional_method="SUM_OBSERVED_30MIN_BAR_LOW_TIMES_VOLUME_PER_OFFICIAL_SESSION",
               partial_no_daily_close_proxy_or_unobserved_zero_fill=True,
               partial_notional_source_trade_conditions_unattested=True,
               partial_notional_proxy_not_mathematical_trade_floor=True,
               symbol_rth_integrity_failure_codes={},
               rth_integrity_cause_counts={},
               official_session_count=30,
               source_rights_not_inferred=True,
               registered_R92_count=0,
               official_c417_primary_dv30_attested=False,
               official_RTH_close_auction_volume_attested=False,
               official_RTH_corrections_attested=False,
               vendor_ohlcv_persisted=False,
               canonical_master_price_history_mc_untouched=True)
    import copy
    good = build(day,hist,bridge,rth,now)
    part = copy.deepcopy(rth)
    part["classifications"]["AAA"] = RTH_UNKNOWN
    part["classification_counts"] = {RTH_UNKNOWN:1}
    part["rth_lower_bound_ge50m_shadow_count"] = 0
    part["symbol_rth_integrity_failure_codes"] = {
        "AAA":"EARLY_AND_FULL_BAR_COUNTS_EXACT"}
    part["rth_integrity_cause_counts"] = {"EARLY_AND_FULL_BAR_COUNTS_EXACT":1}
    part["partial_missing_slot_research_by_symbol"] = {"AAA":PARTIAL_HIGH}
    part["partial_missing_slot_research_counts"] = {PARTIAL_HIGH:1}
    partial_ok = build(day,hist,bridge,part,now)
    need(partial_ok["rth30_lower_bound_observed"]==1 and
         partial_ok["rth30_strict_complete_slot_lower_bound_observed"]==0 and
         partial_ok["rth30_partial_missing_slot_high_research_only_count"]==1 and
         partial_ok["rth30_data_unknown_count"]==1 and
         partial_ok["per_symbol_causal_routing"]["AAA"]["causal_class"]==
             "RTH_OBSERVED_PARTIAL_BARLOW_PROXY_ONLY" and
         partial_ok["per_symbol_causal_routing"]["AAA"]["first_unresolved_gate"]==
             "PRICE_DV30" and
         partial_ok["c417_price_dv30_primary_attested"] is False and
         partial_ok["registered_r92_count"]==0,
         "PARTIAL_POSITIVE_RESEARCH_CANNOT_CHANGE_STRICT_UNKNOWN_OR_AL")
    badpartial=copy.deepcopy(part)
    badpartial["partial_no_daily_close_proxy_or_unobserved_zero_fill"]=False
    try:build(day,hist,bridge,badpartial,now)
    except ValueError as exc:
        need("PARTIAL_RESEARCH_SOURCE_INTEGRITY" in str(exc),
             "OLD_CLOSE_PROXY_MUST_NOT_PROMOTE")
    else:raise AssertionError("OLD_DAILY_CLOSE_PROXY_ACCEPTED")
    badpartial=copy.deepcopy(part)
    badpartial["partial_missing_slot_research_counts"]={PARTIAL_HIGH:2}
    try:build(day,hist,bridge,badpartial,now)
    except ValueError as exc:
        need("PARTIAL_RESEARCH_SOURCE_INTEGRITY" in str(exc),
             "FORGED_PARTIAL_COUNT_MUST_FAIL")
    else:raise AssertionError("FORGED_PARTIAL_COUNT_ACCEPTED")
    badpartial=copy.deepcopy(part)
    badpartial["classifications"]["AAA"]=RTH_HIGH
    badpartial["classification_counts"]={RTH_HIGH:1}
    badpartial["rth_lower_bound_ge50m_shadow_count"]=1
    try:build(day,hist,bridge,badpartial,now)
    except ValueError as exc:
        need("PARTIAL_RESEARCH_SOURCE_INTEGRITY" in str(exc),
             "PARTIAL_WITH_STRICT_PASS_MUST_FAIL")
    else:raise AssertionError("PARTIAL_FORGED_STRICT_PASS_ACCEPTED")
    need(good["scope_count"] == 4 and
         good["first_unresolved_gate_counts"] ==
         {"HISTORY":1,"PRICE_DV30":2,"SOURCE":1} and
         good["rth30_lower_bound_observed"] == 1 and
         good["registered_r92_count"] == 0,
         "SYNTHETIC_GRAPH_COUNTS_NO_AL")
    cases = [
        (lambda d,h,b,r: d.update(asof_et="2026-10-13"), "LATEST_COMPLETE"),
        (lambda d,h,b,r: b.update(exact_identity_queue_sha256="f"*64),
         "ROOT_QUEUE_SHA"),
        (lambda d,h,b,r: r.update(rth_lower_bound_ge50m_shadow_count=2),
         "RTH_HIGH_COUNT"),
        (lambda d,h,b,r: r["classifications"].update(AAA="FALSE_GO"),
         "EXACT_PARTITION_classifications"),
        (lambda d,h,b,r: r.update(official_c417_primary_dv30_attested=True),
         "NO_FALSE_GATE"),
        (lambda d,h,b,r: r.update(joint_cohort_count=2),
         "260_DAILY30_RTH_EXACT"),
        (lambda d,h,b,r: h["classification_counts"].update(
            {"SHADOW_260_DAILY_52_WEEK_OBSERVED":3}),
         "EXACT_PARTITION_symbol_classifications"),
        (lambda d,h,b,r: d.update(registered_R92_count=1),
         "NO_FALSE_GATE"),
        (lambda d,h,b,r: r.update(vendor_ohlcv_persisted=True),
         "NO_FALSE_GATE"),
        (lambda d,h,b,r: h["daily30_source_proxy"][
            "symbol_classifications"].update(AAA=D30_LOW_PRICE),
         "EXACT_PARTITION_symbol_classifications"),
    ]
    for mutate, expected in cases:
        d,h,b,r = (copy.deepcopy(x) for x in (day,hist,bridge,rth))
        mutate(d,h,b,r)
        try: build(d,h,b,r,now)
        except ValueError as exc:
            need(expected in str(exc), "NEGATIVE_CAUSE_" + expected)
        else:
            raise AssertionError("SIX_GATE_BAD_EVIDENCE_ACCEPTED_" + expected)
    print("XRAY_SIX_GATE_CAUSAL_BREAKER_SELFTEST=PASS_12_NEGATIVES_PARTIAL_414_SHADOW_NO_FALSE_AL")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--daily",type=Path)
    ap.add_argument("--history",type=Path)
    ap.add_argument("--bridge",type=Path)
    ap.add_argument("--rth",type=Path)
    ap.add_argument("--out",type=Path)
    opts=ap.parse_args()
    if opts.selftest:
        selftest();return
    files = {"daily":opts.daily,"history":opts.history,"bridge":opts.bridge,
             "rth":opts.rth}
    need(opts.out is not None and
         all(v is not None and v.is_file() for v in files.values())
         and not opts.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "SAME_RUN_SOURCE_REPORTS_EPHEMERAL_OUTPUT_ONLY")
    data={k:v.read_bytes() for k,v in files.items()}
    docs={k:json.loads(raw) for k,raw in data.items()}
    hashes={k:hashlib.sha256(raw).hexdigest() for k,raw in data.items()}
    out=build(docs["daily"],docs["history"],docs["bridge"],docs["rth"],
              dt.datetime.now(dt.timezone.utc),hashes)
    opts.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SIX_GATE_CAUSAL_BREAKER="+json.dumps({
        "status":out["status"],
        "scope":out["scope_count"],
        "asof_et":out["asof_et"],
        "primary_gate_counts":out["first_unresolved_gate_counts"],
        "rth_bound":out["rth30_lower_bound_observed"],
        "rth_ambiguous":out["rth30_ambiguous_count"],
        "rth_unknown":out["rth30_data_unknown_count"],
        "mc_attested":False, "technical_attested":False,
        "R92":0},sort_keys=True))


if __name__=="__main__":
    main()
