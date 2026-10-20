#!/usr/bin/env python3
"""Cross-run SHA-anchored current RTH proof deficit; counts derive from authenticated inputs.

Read-only classification and official evidence REQUIREMENTS. This cannot
authenticate a caller-provided GitHub JSON, market-data rights, trade prints,
actual closing auction/corrections or C4.17 PASS. The GitHub Actions caller
must independently download authentic same-run artifacts. No vendor OHLCV.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from source_epoch_freshness_guard import last_complete_session

SCHEMA="XRAY_OFFICIAL_RTH_PROOF_DEFICIT_V1"
CROSS="XRAY_CROSS_PLANE_BLOCKER_RECONCILIATION_V1"
SIX="XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1"
JOINT="XRAY_PERSONAL_JOINT_HISTORY_DAILY30_EXACT_RTH30_BOUND_V1"
HIGH="LOWER_BOUND_GE_50M_SHADOW"
MID="AMBIGUOUS_BETWEEN_BOUNDS_SHADOW"
UNK="UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW"
PART_HIGH="PARTIAL_OBSERVED_RTH_BARLOW_NOTIONAL_PROXY_GE50M_RESEARCH_ONLY"
PART_MID="PARTIAL_OBSERVED_RTH_BARLOW_NOTIONAL_PROXY_INDETERMINATE"
PART_REJECT="PARTIAL_SOURCE_SCHEMA_OR_VOLUME_REJECTED"
ACTION={
    HIGH:"PROVE_OFFICIAL_RTH_AUCTION_CORRECTIONS_SPLITS_AND_RIGHTS",
    MID:"RECONCILE_AUCTION_AND_CORRECTED_RTH_VOLUME",
    UNK:"ISOLATE_BAD_30MIN_SESSION_OR_PROVIDER_BATCH"}
HEX64=re.compile(r"[0-9a-f]{64}")


def need(value,reason):
    if not value: raise ValueError("XRAY_RTH_PROOF_"+reason)


def universe_sha(symbols):
    return hashlib.sha256("\n".join(symbols).encode("ascii")).hexdigest()


def reconcile(cross,six,joint,raw_joint,*,now_utc,upstream_run_id):
    need(type(now_utc) is dt.datetime and now_utc.tzinfo is not None and
         now_utc.utcoffset()==dt.timedelta(0),"UTC_REQUIRED")
    need(all(type(obj) is dict for obj in (cross,six,joint)) and
         type(raw_joint) is bytes and 0<len(raw_joint)<1_000_000,
         "SOURCE_INPUT_SHAPE")
    need(type(upstream_run_id) is int and upstream_run_id>0,
         "EXTERNALLY_AUTHENTICATED_RUN_ID_REQUIRED")
    asof=last_complete_session(now_utc)
    need(all(obj.get("asof_et")==asof for obj in (cross,six,joint)),
         "LATEST_OFFICIAL_SAME_ASOF")
    need(cross.get("schema")==CROSS and six.get("schema")==SIX and
         joint.get("schema")==JOINT,"SOURCE_SCHEMAS")
    need(all(obj.get("execution")=="NONE" and obj.get("real_money")=="NO-GO"
             for obj in (cross,six,joint)),"NO_EXECUTION")
    need(cross.get("alpha_authority") is False and
         cross.get("r92_authority") is False and
         cross.get("unknown_never_pass") is True and
         cross.get("canonical_mutated") is False and
         type(cross.get("universe_count")) is int and
         cross["universe_count"]>0 and
         type(cross.get("canonical_price_dv30_unknown_count")) is int and
         0<cross["canonical_price_dv30_unknown_count"]<=cross["universe_count"] and
         cross.get("canonical_price_dv30_reported_pass_count_not_independently_attested")==0 and
         type(cross.get("canonical_root_history_unknown_count")) is int and
         0<=cross["canonical_root_history_unknown_count"]<=cross["universe_count"] and
         type(cross.get("independent_research_history_260_52_unproven_count")) is int and
         0<=cross["independent_research_history_260_52_unproven_count"]<=cross["universe_count"] and
         cross.get("same_epoch_and_identity_does_not_establish_same_policy") is True and
         cross.get("canonical_price_primary_evidence_independently_verified_here") is False,
         "CROSS_PLANE_AUTHORITY_AND_SCOPE")
    need(six.get("scope_count")==cross["universe_count"] and
         six.get("registered_r92_count")==0 and
         six.get("c417_price_dv30_primary_attested") is False and
         six.get("source_rights_not_inferred") is True and
         six.get("no_vendor_ohlcv_persisted") is True,
         "SIX_GATE_RESEARCH_ONLY")
    digests=six.get("input_report_sha256")
    need(type(digests) is dict and
         set(digests)=={"daily","history","bridge","rth"} and
         all(type(v) is str and HEX64.fullmatch(v) for v in digests.values()) and
         cross.get("six_gate_input_report_sha256")==digests and
         hashlib.sha256(raw_joint).hexdigest()==digests["rth"] and
         json.loads(raw_joint)==joint,
         "EXACT_SAME_RUN_RTH_SOURCE_BYTES_SHA")
    rows=joint.get("classifications")
    known=cross.get("canonical_unknown_symbolic_repair_worklist")
    routes=six.get("per_symbol_causal_routing")
    need(all(type(x) is dict for x in (rows,known,routes)) and
         len(known)==cross["canonical_price_dv30_unknown_count"] and
         len(routes)==cross["universe_count"] and
         set(known).issubset(routes) and
         cross.get("root_universe_sha256")==
             six.get("exact_root_identity_scope_sha256")==
             universe_sha(sorted(routes)),
         "SAME_EXACT_NASDAQ_UNIVERSE")
    cohort=sorted(rows)
    need(cohort and len(cohort)==joint.get("joint_cohort_count")==
         six.get("joint260_daily30_research_scope") and
         len(cohort)<=len(known) and
         universe_sha(cohort)==joint.get(
             "joint_history260_daily30_cohort_sha256") and
         set(cohort).issubset(known) and
         joint.get("official_session_count")==30 and
         joint.get("registered_R92_count")==0 and
         joint.get("official_c417_primary_dv30_attested") is False and
         joint.get("official_RTH_close_auction_volume_attested") is False and
         joint.get("official_RTH_corrections_attested") is False and
         joint.get("same_issuer_corporate_action_adjustment_attested") is False and
         joint.get("source_rights_not_inferred") is True and
         joint.get("vendor_ohlcv_persisted") is False and
         joint.get("canonical_master_price_history_mc_untouched") is True,
         "RTH_NO_PRIMARY_EVIDENCE")
    classes=Counter(rows.values())
    need(set(classes).issubset({HIGH,MID,UNK}) and
         classes==joint.get("classification_counts") and
         classes[HIGH]==joint.get("rth_lower_bound_ge50m_shadow_count") and
         classes[MID]==joint.get("rth_ambiguous_shadow_count") and
         classes[UNK]==joint.get("rth_incomplete_or_unknown_count") and
         classes[HIGH]+classes[MID]+classes[UNK]==len(cohort),
         "EXACT_RTH_PARTITION")
    partial=joint.get("partial_missing_slot_research_by_symbol")
    failures=joint.get("symbol_rth_integrity_failure_codes")
    need(type(partial) is dict and type(failures) is dict and
         set(partial)==set(failures)=={k for k,v in rows.items() if v==UNK} and
         set(failures.values()).issubset({"EARLY_AND_FULL_BAR_COUNTS_EXACT"}) and
         set(partial.values()).issubset({PART_HIGH,PART_MID,PART_REJECT}) and
         dict(sorted(Counter(partial.values()).items()))==
             joint.get("partial_missing_slot_research_counts") and
         joint.get("partial_missing_slot_symbolic_only_never_canonical") is True and
         joint.get("partial_notional_proxy_not_mathematical_trade_floor") is True and
         joint.get("partial_notional_source_trade_conditions_unattested") is True and
         joint.get("partial_no_daily_close_proxy_or_unobserved_zero_fill") is True,
         "PARTIAL_BARLOW_NOT_A_TRADE_PRICE_FLOOR")
    deny={}
    for symbol in cohort:
        status=rows[symbol]
        row=known.get(symbol)
        routing=routes.get(symbol)
        need(type(row) is dict and type(routing) is dict and
             row.get("canonical_price_state")=="UNKNOWN" and
             row.get("research_first_unresolved_gate")=="PRICE_DV30" and
             row.get("safe_next_evidence_action")==ACTION[status] and
             routing.get("next_safe_evidence_action")==ACTION[status] and
             row.get("research_causal_class")==routing.get("causal_class") and
             row.get("alpha_authority") is False,
             "CANONICAL_UNKNOWN_VS_RTH_ACTION_DRIFT")
        deny[symbol]={
            "rth_source_class":status,
            "safe_next_evidence_action":ACTION[status],
            "partial_slot_proxy":partial.get(symbol),
            "official_auction_and_corrections_proven":False,
            "official_trade_condition_eligible_volume_proven":False,
            "same_issuer_corporate_action_and_legal_rights_proven":False,
            "eligible_for_c417_price_pass":False,
            "alpha_authority":False}
    missing=sorted(set(known)-set(cohort))
    first_gates=Counter(known[s].get("research_first_unresolved_gate")
                        for s in known)
    need(len(missing)==len(known)-len(cohort) and
         all(known[s]["research_first_unresolved_gate"] in ("SOURCE","HISTORY")
             for s in missing) and
         dict(first_gates)==cross.get("canonical_price_unknown_by_personal_first_gate") and
         first_gates.get("PRICE_DV30",0)==len(cohort) and
         six.get("rth30_strict_complete_slot_lower_bound_observed")==classes[HIGH] and
         six.get("rth30_ambiguous_count")==classes[MID] and
         six.get("rth30_data_unknown_count")==classes[UNK] and
         six.get("rth30_partial_missing_slot_high_research_only_count")==
             sum(v==PART_HIGH for v in partial.values()),
         "UNRESOLVED_OUTSIDE_RTH_OR_SHADOW_REPLAY")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "upstream_source_workflow_run_id":upstream_run_id,
        "source_rth_raw_artifact_sha256":digests["rth"],
        "exact_root_universe_sha256":cross["root_universe_sha256"],
        "source_universe_count":cross["universe_count"],
        "canonical_price_dv30_unknown_count":len(known),
        "outside_complete_rth_cohort_unknown_count":len(missing),
        "rth_exact_30session_research_cohort":len(cohort),
        "rth_shadow_classification_counts":dict(sorted(classes.items())),
        "rth_complete_slot_research_high_count":classes[HIGH],
        "rth_auction_volume_ambiguous_count":classes[MID],
        "rth_incomplete_slot_count":classes[UNK],
        "partial_high_bar_low_is_not_true_price_floor_count":
            sum(v==PART_HIGH for v in partial.values()),
        "rth_proof_denied_per_symbol":deny,
        "outside_rth_safe_actions":{
            sym:known[sym]["safe_next_evidence_action"] for sym in missing},
        "official_trade_prints_and_auction_ingested":False,
        "source_license_independently_verified":False,
        "primary_c417_price_dv30_proven":False,
        "canonical_updated":False,
        "source_market_api_calls":0,
        "no_vendor_ohlcv_in_artifact":True,
        "alpha_authority":False,"r92_authority":False,
        "iphone_delivery_receipt_attested":False,
        "unknown_never_pass":True,
        "execution":"NONE","real_money":"NO-GO",
        "status":"RTH_SHADOW_BOUNDS_AND_SLOT_GAPS_PROOF_DENIED_NO_AL",
    }


def main():
    p=argparse.ArgumentParser()
    for key in ("cross","six","joint","out"):
        p.add_argument("--"+key,required=True,type=Path)
    p.add_argument("--upstream-run-id",type=int,required=True)
    args=p.parse_args()
    inputs=[args.cross.resolve(),args.six.resolve(),args.joint.resolve()]
    need(args.out.resolve() not in inputs,"INPUT_OVERWRITE")
    bb=args.joint.read_bytes()
    result=reconcile(json.loads(args.cross.read_text()),
        json.loads(args.six.read_text()),json.loads(bb),bb,
        now_utc=dt.datetime.now(dt.timezone.utc),
        upstream_run_id=args.upstream_run_id)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
        "cohort":result["rth_exact_30session_research_cohort"],
        "classes":result["rth_shadow_classification_counts"],
        "c417_price_pass":False,"alpha":False,
        "execution":"NONE","real_money":"NO-GO"},sort_keys=True))


if __name__=="__main__":
    main()
