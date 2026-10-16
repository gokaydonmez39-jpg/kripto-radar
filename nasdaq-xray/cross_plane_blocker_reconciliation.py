#!/usr/bin/env python3
"""Independent root/history/PRICE cross-plane blocker audit, never AL.

Three distinct quantities MUST NOT be silently joined as equivalent:
root PARTIAL_HISTORY unknown, personal shadow 260/52 unproven, and canonical
PRICE/DV30 UNKNOWN. Same NASDAQ ASOF + 3189 identity SHA is necessary, but
not sufficient, for shared gate meanings. Report only symbolic causes.
Caller must authenticate same-run research artifact with GitHub API.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from source_epoch_freshness_guard import last_complete_session

SCHEMA="XRAY_CROSS_PLANE_BLOCKER_RECONCILIATION_V1"
GATES=("SOURCE","HISTORY","PRICE_DV30")
PRICE_STATES={
    "FAIL_PRICE","FAIL_DV30","FAIL_DV30_INSUFFICIENT_SESSIONS",
    "FAIL_PRICE_NO_ASOF_BAR","UNKNOWN","PASS"}
HEX64=re.compile("[0-9a-f]{64}\\Z")


def need(ok,why):
    if not ok:
        raise ValueError("XRAY_CROSS_PLANE_"+why)


def universe_sha(symbols):
    return hashlib.sha256("\n".join(symbols).encode("ascii")).hexdigest()


def reconcile(root,price,six,*,now_utc):
    need(type(now_utc) is dt.datetime and now_utc.tzinfo is not None and
         now_utc.utcoffset()==dt.timedelta(0),"UTC_CLOCK_REQUIRED")
    need(all(type(x) is dict for x in (root,price,six)),"INPUT_SCHEMA")
    asof=last_complete_session(now_utc)
    need(root.get("asof_et")==price.get("asof_et")==six.get("asof_et")==asof,
         "CURRENT_OFFICIAL_SAME_ASOF")
    need(root.get("schema")=="XRAY_ORCHESTRATOR_V1" and
         price.get("schema")=="XRAY_CANONICAL_PRICE_DV30_V1" and
         six.get("schema")=="XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1",
         "REPORT_SCHEMA")
    need(root.get("execution")==price.get("execution")==six.get("execution")=="NONE" and
         root.get("real_money")==price.get("real_money")==six.get("real_money")=="NO-GO" and
         root.get("g9_status")=="BLOCKED" and
         price.get("unknown_never_pass") is True and
         six.get("c417_price_dv30_primary_attested") is False and
         six.get("issuer_class_mc_current_attested") is False and
         six.get("technical_a_b_d_r1_event_regime_attested") is False and
         six.get("registered_r92_count")==0 and
         six.get("iphone_device_delivery_attested") is False and
         six.get("no_vendor_ohlcv_persisted") is True and
         six.get("no_canonical_mutations") is True and
         six.get("source_rights_not_inferred") is True,
         "UNAUTHORIZED_GATE_OR_SOURCE_PROMOTION")
    routes=six.get("per_symbol_causal_routing")
    results=price.get("results")
    need(type(routes) is dict and type(results) is dict and
         len(routes)==len(results)==root.get("queue_total")==
         price.get("source_master_count")==six.get("scope_count") and
         0<len(routes)<=6500,
         "SYMBOL_SCOPE_COUNT")
    symbols=sorted(routes)
    need(symbols==sorted(results) and
         all(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}",s) for s in symbols),
         "UNIVERSE_PARTITION")
    digest=universe_sha(symbols)
    need(digest==root.get("queue_hash")==
         price.get("source_master_queue_hash")==
         six.get("exact_root_identity_scope_sha256"),
         "EXACT_UNIVERSE_SHA")
    recorded=six.get("input_report_sha256")
    need(type(recorded) is dict and set(recorded)==
         {"bridge","daily","history","rth"} and
         all(type(v) is str and HEX64.fullmatch(v) is not None
             for v in recorded.values()),
         "FOUR_SOURCE_REPORT_DIGESTS")
    need(six.get("six_gate_dependency_order")==
         ["SOURCE","HISTORY","PRICE_DV30","MC","TECH","R92_DELIVERY"] and
         six.get("research_only_causal_next_action") is True,
         "GATE_DEPENDENCY_ORDER")
    routings=Counter()
    actions=Counter()
    canonical=Counter()
    intersections=defaultdict(Counter)
    issue_rows={}
    for sym in symbols:
        routing=routes[sym]
        price_row=results[sym]
        need(type(routing) is dict and type(price_row) is dict,
             "SYMBOL_ROW_SCHEMA")
        lane=routing.get("first_unresolved_gate")
        action=routing.get("next_safe_evidence_action")
        pstatus=price_row.get("status")
        need(lane in GATES and type(action) is str and action and
             type(routing.get("causal_class")) is str and
             type(routing.get("parallel_research_only")) is str and
             pstatus in PRICE_STATES,
             "UNKNOWN_SYMBOL_GATE_OR_PRICE_CLASS")
        routings[lane]+=1
        actions[action]+=1
        canonical[pstatus]+=1
        intersections[lane][pstatus]+=1
        if pstatus=="UNKNOWN":
            issue_rows[sym]={
                "canonical_price_state":"UNKNOWN",
                "research_first_unresolved_gate":lane,
                "research_causal_class":routing["causal_class"],
                "safe_next_evidence_action":action,
                "alpha_authority":False}
    need(dict(sorted(routings.items()))==
         six.get("first_unresolved_gate_counts") and
         dict(sorted(actions.items()))==
         six.get("next_safe_evidence_action_counts"),
         "SIX_GATE_PARTITION_REPLAY_DRIFT")
    expected=dict(sorted({k:v for k,v in canonical.items() if v>0}.items()))
    need(price.get("counts")==expected and
         price.get("unknown_count")==len(issue_rows) and
         price.get("pass_count")==canonical.get("PASS",0) and
         set(price.get("unknown_symbols",[]))==set(issue_rows) and
         len(price.get("unknown_symbols",[]))==len(issue_rows) and
         set(price.get("pass_symbols",[]))==
         {sym for sym,row in results.items() if row["status"]=="PASS"},
         "CANONICAL_PRICE_PARTITION_DRIFT")
    reasons=root.get("history_unknown_reason_counts")
    need(root.get("status")=="PARTIAL_HISTORY" and
         root.get("unknown_reason_partition_exact") is True and
         type(reasons) is dict and reasons and
         all(type(v) is int and v>=0 for v in reasons.values()) and
         sum(reasons.values())==root.get("unknown_count") and
         type(root["unknown_count"]) is int,
         "ROOT_HISTORY_UNKNOWN_REASON_PARTITION")
    research_history_unproven=len(symbols)-six.get("history260_52_observed",-1)
    need(research_history_unproven>=0 and
         six["source_day_observed"]<=len(symbols) and
         six["joint260_daily30_research_scope"]<=six["history260_52_observed"] and
         sum(routings.values())==len(symbols),
         "SHADOW_HISTORY_COHORT_COUNT")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "root_universe_sha256":digest,"universe_count":len(symbols),
        "canonical_root_history_unknown_count":root["unknown_count"],
        "canonical_root_history_unknown_reason_counts":dict(sorted(reasons.items())),
        "independent_research_history_260_52_unproven_count":research_history_unproven,
        "canonical_price_dv30_unknown_count":len(issue_rows),
        "canonical_price_dv30_pass_count":canonical.get("PASS",0),
        "canonical_price_status_counts":dict(sorted(canonical.items())),
        "personal_sip_first_unresolved_gate_counts":dict(sorted(routings.items())),
        "canonical_price_unknown_by_personal_first_gate":{
            gate:dict(sorted(Counter(
                row["research_first_unresolved_gate"] for row in issue_rows.values()
            ).items())) if False else
            sum(x["research_first_unresolved_gate"]==gate
                for x in issue_rows.values())
            for gate in GATES},
        "canonical_price_status_by_personal_first_gate":{
            gate:dict(sorted(intersections[gate].items())) for gate in GATES},
        "personal_next_safe_evidence_action_counts":dict(sorted(actions.items())),
        "canonical_unknown_symbolic_repair_worklist":dict(sorted(issue_rows.items())),
        "six_gate_input_report_sha256":dict(sorted(recorded.items())),
        "count_semantics":"223 root historical unresolved, 260/52 research history unproven, and 548 canonical price UNKNOWN are distinct criteria; NEVER add/subtract as one failure metric",
        "same_epoch_and_identity_does_not_establish_same_policy":True,
        "personal_history_and_liquidity_still_research_only":True,
        "licensed_source_access_or_rights_independently_verified":False,
        "github_source_artifact_authenticated_inside_module":False,
        "no_market_provider_called":True,
        "no_raw_market_prices_or_volume_in_output":True,
        "canonical_mutated":False,
        "alpha_authority":False,"r92_authority":False,
        "iphone_delivery_attested":False,
        "unknown_never_pass":True,
        "execution":"NONE","real_money":"NO-GO",
        "status":"RESEARCH_CROSS_PLANE_EXACT_PARTITION_NOT_CANONICAL_RELEASE"
    }


def main():
    parser=argparse.ArgumentParser()
    for x in ("root","price","six","out"):
        parser.add_argument("--"+x,type=Path,required=True)
    parser.add_argument("--observed-at-utc")
    a=parser.parse_args()
    inp={a.root.resolve(),a.price.resolve(),a.six.resolve()}
    need(a.out.resolve() not in inp,"NO_SOURCE_OVERWRITE")
    now=(dt.datetime.fromisoformat(a.observed_at_utc.replace("Z","+00:00"))
         if a.observed_at_utc else dt.datetime.now(dt.timezone.utc))
    report=reconcile(json.loads(a.root.read_text()),
                     json.loads(a.price.read_text()),
                     json.loads(a.six.read_text()),now_utc=now)
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":report["status"],
        "universe_count":report["universe_count"],
        "root_history_unknown":report["canonical_root_history_unknown_count"],
        "shadow_260_history_unproven":
            report["independent_research_history_260_52_unproven_count"],
        "canonical_price_unknown":report["canonical_price_dv30_unknown_count"],
        "alpha_authority":False,
        "execution":"NONE","real_money":"NO-GO"
    },sort_keys=True))


if __name__=="__main__":
    main()
