"""A37 research-only release boundary: independent split witnesses != historical alpha.

No network, tokens, trade, Sheets or signal writes; no autonomous promotion.
A third-party source returning dated data is NOT evidence that it was known then.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import math

STUDY = "XRAY_A37_EVIDENCE_BOUNDARY_V1"
KNOWN_SPLIT_WITNESSES = {
    "MNST": {"date": "2026-08-11", "ratio": 2, "raw_pre": "91.41",
             "adjusted_pre": "45.715"},
    "IESC": {"date": "2026-08-24", "ratio": 2, "raw_pre": "685.44",
             "adjusted_pre": "342.52"},
}
BLOCKERS = (
    "COMPLETE_CA_AND_ADJUSTMENT_PROVENANCE_UNATTESTED",
    "HISTORICAL_POINT_IN_TIME_UNIVERSE_UNATTESTED",
    "COMPLETE_PREREGISTERED_500_SESSION_OOS_NOT_RUN",
    "NET_COST_AND_TAIL_RISK_SUPERIORITY_NOT_ESTABLISHED",
)

class EvidenceBlocked(ValueError):
    pass

def need(value, code):
    if not value:
        raise EvidenceBlocked(code)

def dec(value):
    need(type(value) in (str,int,float,Decimal), "NON_NUMERIC")
    try:
        n=Decimal(str(value))
    except InvalidOperation as e:
        raise EvidenceBlocked("INVALID_DECIMAL") from e
    need(n.is_finite() and n > 0, "NONPOSITIVE_OR_NONFINITE")
    return n

def verify_split_sample(witnesses):
    """Check public two-source 2:1 examples, NOT full CA/PIT or vendor attestation."""
    need(type(witnesses) is dict and set(witnesses)==set(KNOWN_SPLIT_WITNESSES),
         "SPLIT_SAMPLE_MISSING")
    out={}
    for sym, expected in KNOWN_SPLIT_WITNESSES.items():
        w=witnesses[sym]
        need(type(w) is dict and set(w)==set(expected), "WITNESS_SCHEMA")
        need(w["date"]==expected["date"] and w["ratio"]==expected["ratio"],
             "WITNESS_DATE_OR_RATIO")
        raw=dec(w["raw_pre"])
        adjusted=dec(w["adjusted_pre"])
        need(abs(raw/adjusted - Decimal(2)) < Decimal(".01"),
             "SPLIT_RATIO_RECONCILIATION")
        need(raw==dec(expected["raw_pre"]) and adjusted==dec(expected["adjusted_pre"]),
             "WITNESS_PRICE_DRIFT")
        out[sym]="TWO_VENDOR_SPLIT_SAMPLE_RECONCILED_NOT_CA_UNIVERSE_CLEARED"
    return out

def hypothetical_gap_loss(reference, stop, open_price, *,
                          entry_bps=15, exit_bps=15):
    """Reference-close vs next-open cost scenario; this NEVER observes an actual fill."""
    reference,stop,opening=dec(reference),dec(stop),dec(open_price)
    need(stop<reference and opening<stop, "NOT_A_STOP_GAP_EXAMPLE")
    need(type(entry_bps) is int and type(exit_bps) is int
         and 0<=entry_bps<=500 and 0<=exit_bps<=500, "INVALID_COST_ASSUMPTION")
    entry_cost=Decimal(entry_bps)/Decimal(10000)
    exit_cost=Decimal(exit_bps)/Decimal(10000)
    theoretical_stop=Decimal(100)*((stop*(1-exit_cost))/(reference*(1+entry_cost))-1)
    theoretical_gap=Decimal(100)*((opening*(1-exit_cost))/(reference*(1+entry_cost))-1)
    return {"stop_net_pct":float(round(theoretical_stop,3)),
            "gap_open_net_pct":float(round(theoretical_gap,3)),
            "fill_observed":False,"costs_observed":False,
            "may_claim_executed_pnl":False}

def audit_research_gate(payload):
    """A live vendor quote or self-asserted success flags can never override NO-GO.

    Future promotion requires a separate independently reviewed signed evidence
    and a different production-owner decision; NOT this offline module.
    """
    need(type(payload) is dict and set(payload)=={
        "schema","splits","full_adjustment_provenance",
        "full_pit_477_daily_universe","complete_oos",
        "actual_or_sourced_execution_costs","full_tail_risk_results",
        "real_500_bar_sample_count","complete_closed_episode_sample_count",
        "provider_access_rate_limited","source_asof_verification"}, "MANIFEST_SCHEMA")
    need(payload["schema"]==STUDY, "MANIFEST_VERSION")
    split_check=verify_split_sample(payload["splits"])
    for key in ("full_adjustment_provenance","full_pit_477_daily_universe",
                "complete_oos","actual_or_sourced_execution_costs",
                "full_tail_risk_results","source_asof_verification"):
        need(payload[key] is False, "UNVERIFIED_PROMOTION_"+key)
    need(payload["provider_access_rate_limited"] is True,
         "HIDDEN_RATE_LIMIT")
    need(type(payload["real_500_bar_sample_count"]) is int
         and 0 <= payload["real_500_bar_sample_count"] <= 3,
         "FALSE_FULL_HISTORY_CLAIM")
    need(type(payload["complete_closed_episode_sample_count"]) is int
         and payload["complete_closed_episode_sample_count"] == 0,
         "PRIVATE_EPISODE_EVIDENCE_CANNOT_BE_ATTESTED_PUBLICLY")
    return {
        "state":"RESEARCH_ENGINEERING_READY_BUT_SCIENTIFIC_FINAL_NO_GO",
        "split_witnesses":split_check,
        "four_release_gates":{k:"BLOCKED_NO_AUTHORITATIVE_COMPLETE_EVIDENCE" for k in BLOCKERS},
        "independent_vendor_PIT_attested":False,
        "all_477_500plus_adjusted_history_verified":False,
        "prospective_out_of_sample_completed":False,
        "actual_fill_economics_verified":False,
        "may_generate_al":False,
        "may_change_rules":False,
        "may_send_notifications":False,
        "may_write_sheets":False,
        "may_trade":False,
        "may_merge_to_production":False,
    }

def current_public_sample():
    """Public source sample only. Never embed private Sheets or signal history."""
    return {"schema": STUDY,
            "splits":KNOWN_SPLIT_WITNESSES,
            "full_adjustment_provenance":False,
            "full_pit_477_daily_universe":False,
            "complete_oos":False,
            "actual_or_sourced_execution_costs":False,
            "full_tail_risk_results":False,
            "source_asof_verification":False,
            "real_500_bar_sample_count":3,
            "complete_closed_episode_sample_count":0,
            "provider_access_rate_limited":True}
