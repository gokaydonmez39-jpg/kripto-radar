#!/usr/bin/env python3
"""Actual FROG Oct13 three-artifact SHA-bound R92 math adjudication.

Separate five positive SOURCE OBSERVATIONS from release-grade evidence; do not
fabricate issuer shares lower bound from insider sales, SIP corrections from
four-second trades, or an IR no-event certification from HTTP200.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_FROG_20261013_CONDITIONAL_R92_MATH_EVIDENCE_REVIEW_V1"
ASOF="2026-10-13"
SHARES=123301311

def require(ok,reason):
    if not ok:raise ValueError("FROG_R92_MATH_"+reason)

def load(path):
    b=path.read_bytes()
    return json.loads(b),hashlib.sha256(b).hexdigest()

def canonical_release_readback(source_sha256):
    """Registration can be minted first; actual phone delivery is a separate fact."""
    from frog_c417_first_registration_writer_v1 import read_registration, root_sha
    try:
        terminal=json.loads((ROOT/"canonical_current_terminal.json").read_text())
        registry=json.loads((ROOT/"canonical_candidate_lifecycle_registry.json").read_text())
        ledger=json.loads((ROOT/"delivery_ledger.json").read_text())
        compiled=json.loads((ROOT/"chatgpt_compiled_policy_v3.json").read_text())
        evidence_id=root_sha(source_sha256)
        item=(terminal.get("candidate_releases") or {}).get("FROG|D") or {}
        terminal_ok=(terminal.get("asof_et")==ASOF and
            terminal.get("compiled_policy_hash")==compiled.get("policy_hash") and
            item.get("asof_et")==ASOF and
            item.get("evidence_root_sha256")==evidence_id and
            item.get("independent_c417_release_pass") is True)
        registered=read_registration(registry,terminal,compiled,source_sha256)
        key="FROG|D|"+ASOF
        rec=(registry.get("records") or {}).get(key) or {}
        delivery=(ledger.get("deliveries") or {}).get(key) or {}
        delivered=bool(registered and delivery.get("signal_id")==rec.get("signal_id")
            and delivery.get("evidence_root_sha256")==evidence_id and
            delivery.get("platform_receipt_verified") is True)
        return {"terminal":bool(terminal_ok),"registered":bool(registered),
                "delivered":bool(delivered)}
    except (OSError,ValueError,TypeError,KeyError):
        return {"terminal":False,"registered":False,"delivered":False}

def decide(cover,rollup,lastmile,policy,source_sha256=None):
    require(cover.get("schema")=="XRAY_FROG_OCT13_CLASS_SPECIFIC_10Q_COVER_AND_SIP_MC_SHADOW_V1","COVER_SCHEMA")
    require(rollup.get("schema")=="XRAY_FROG_20261013_CANDIDATE_LOCAL_LIVE_SOURCE_RECONCILIATION_V1","PRICE_SCHEMA")
    require(lastmile.get("schema")=="XRAY_FROG_OCT13_LAST_MILE_SEC_FORM4_CA_EVENT_HALT_TRADE_SHADOW_V1","LAST_MILE_SCHEMA")
    require(all(z.get("asof_et")==ASOF and z.get("symbol")=="FROG"
                for z in (cover,rollup,lastmile)),"CROSS_ASOF_IDENTITY")
    require(all(z.get("execution")=="NONE" and z.get("real_money")=="NO-GO"
                for z in (cover,rollup,lastmile,policy)),"SAFETY")
    require(cover["cover_shares_observed"]==SHARES and
            cover["sec_cover_shares_observation_date"]=="2026-07-31" and
            cover["sec_filing_date"]=="2026-08-07" and
            cover["historical_sec_class_cover_verified"] is True,
            "EXACT_HISTORICAL_COVER")
    require(cover.get("observed_vintage_cap_band")=="GE_10B_SHADOW" and
            cover.get("price_source_status")=="ALPACA_RAW_AND_ALL_SIP_1DAY_ASOF_OBSERVED",
            "REAL_10B_DIAGNOSTIC")
    require(rollup["price"]["raw_completed_days"]==30 and
            rollup["price"]["all_adjusted_completed_days"]==30 and
            rollup["price"]["raw_vs_all_close_diff_days"]==0 and
            rollup["price"]["observed_30min_lower_bound_state"]=="LOWER_BOUND_GE_50M_SHADOW",
            "OBSERVED_30_SESSIONS")
    require(rollup["corporate_actions"]["complete"]["status"]=="SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET" and
            rollup["corporate_actions"]["all"]["status"]=="SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET" and
            rollup["corporate_actions"]["complete"]["event_types"]=={} and
            rollup["corporate_actions"]["all"]["event_types"]=={},
            "CA_NEGATIVE_PROVIDER_CENSUS")
    sec=lastmile["sec"];price=lastmile["price"];ev=lastmile["issuer_event"];halt=lastmile["halt"]
    forms=sec.get("tracked_form_counts") or {}
    require(forms.get("4")==18 and forms.get("144")==8 and forms.get("10-Q")==1 and
            sec["all_issuer_filings_in_asof_interval"]==27 and
            sec["submissions_recent_covers_interval"] is True,
            "ACTUAL_SEC_27_COUNTS")
    require(price.get("observed_sessions")==price.get("requested_sessions")==30 and
            price.get("observed_auction_condition6_sessions")==30,
            "ACTUAL_AUCTION_30")
    require(halt.get("snapshot_frog_veto") is False and
            halt["observed_dates"][ASOF]["frog_halt_rows_observed"]==0 and
            halt["observed_dates"][ASOF]["http_200"] is True,
            "HALT_SNAPSHOT_SOURCE")
    require(ev["pages"]["issuer_news"].get("http_200") is True and
            ev["pages"]["issuer_events"].get("http_200") is True,
            "IR_HTTP_SOURCE")
    require(policy.get("can_create_r92") is True and
            policy.get("r92_registration_mode")=="INDEPENDENT_C417_RELEASE_APPROVAL_REQUIRED" and
            policy.get("can_update_compiled_C417_alpha") is True and
            policy.get("can_override_canonical_unknown") is True and
            policy.get("observational_evidence_never_equivalent_to_release_primary") is True and
            policy.get("canonical_unknown_override_semantics")=="ONLY_AFTER_NEW_EXACT_SAME_ASOF_PRIMARY_EVIDENCE_IS_INDEPENDENTLY_VERIFIED" and
            policy.get("r92_creation_requires_all_candidate_local_and_compiled_gates") is True,
            "CONDITIONAL_PERMISSION")
    # CAP_OLD > 10bn means at unchanged observed SIP price CAP_NEW <2bn
    # requires NEW_SHARES <= floor(SHARES/5), i.e. >80% of old shares
    # cancelled. This is a NECESSARY SCENARIO THRESHOLD, not evidence
    # that no cancellation occurred. No observed SEC owner sale provides
    # a certified outstanding-share lower bound (or issuer issuance cap).
    cut=SHARES//5
    required_decrease=SHARES-cut
    require(cut==24660262 and required_decrease==98641049,"INTEGER_MATH")
    observed={
      "sec_issuer_filing_inventory":"PASS_OBSERVED",
      "alpaca_complete_all_ca_census":"PASS_OBSERVED_ZERO_MATCHES",
      "sip_close_condition6_samples":"PASS_OBSERVED_30_OF_30",
      "nasdaq_halt_rss_snapshot":"PASS_OBSERVED_NO_FROG",
      "issuer_ir_two_http_pages":"PASS_OBSERVED_ACCESSIBLE"
    }
    certification=canonical_release_readback(source_sha256 or {})
    exact={
      "same_asof_sec_class_outstanding_lower_bound":
          sec.get("current_class_shares_reconciled") is True,
      "independent_ca_pit_complete":
          sec.get("corporate_actions_independent_pit_pass") is True and
          rollup["corporate_actions"].get("ca_primary_pass") is True,
      "all_rth_close_and_corrections":
          price.get("exact_rth_dv30_primary_pass") is True and
          rollup["price"].get("independent_close_corrections_verified") is True,
      "eight_session_forward_issuer_event_clear":
          ev.get("eight_day_event_calendar_clear") is True,
      "complete_historical_and_live_halt_clear":
          halt.get("historical_complete_clear_pass") is True and
          halt.get("live_halt_clear_pass") is True,
      "regime_breadth_primary":
          rollup.get("regime_breadth_primary") is True and
          lastmile.get("regime_breadth_primary_pass") is True,
      "compiled_c417_independent_release":certification["terminal"]
    }
    eligible=all(x is True for x in exact.values())
    return {"schema":SCHEMA,"symbol":"FROG","setup":"D","asof_et":ASOF,
            "policy_r92_conditional_permission_enabled":True,
            "observed_source_checks":observed,
            "mathematical_vintage_scenario":{
               "sec_10q_cover_shares_july31":SHARES,
               "indicative_asof_vintage_cap_at_least_usd":10000000000,
               "release_mc_threshold_usd":2000000000,
               "required_remaining_shares_for_cap_below_2b_at_same_price_at_most":cut,
               "required_minimum_share_cancellation_at_same_price":required_decrease,
               "minimum_share_cancellation_fraction_gt_or_eq":0.80,
               "form4_and_form144_prove_issuer_net_outstanding_change":False,
               "known_independent_current_outstanding_lower_bound_shares":None,
               "market_cap_floor_proven":False,
               "mc_primary_ge_2b":False,
               "explanation":"Necessary 80pct cancellation hypothetical is not issuer share-rollforward proof"},
            "independent_release_evidence_gates":exact,
            "missing_release_evidence":[k for k,v in exact.items() if v is not True],
            "eligible_c417_primary":eligible,
            "r92_registered":bool(eligible and certification["registered"]),
            "iphone_delivery_receipt_attested":certification["delivered"],
            "canonical_files_modified":False,
            "delivery_ledger_modified":False,
            "real_money":"NO-GO","execution":"NONE","unknown_never_pass":True}

def exact_primary_source_component_matrix(cover,rollup,lastmile):
    """No extrapolation: expose independently witnessed positives and missing releases.

    Each named component distinguishes actually observed source rows from the
    completion/authorization required by the compiled C4.17 primary gate.
    """
    s=lastmile["sec"]
    p=lastmile["price"]
    e=lastmile["issuer_event"]
    h=lastmile["halt"]
    r=rollup["price"]
    a=rollup["corporate_actions"]
    sec=rollup.get("sec_mc_legal_event") or {}
    close=p.get("session_observations") or {}
    future=lastmile.get("event_forward_8_official_sessions") or []
    expected_future=["2026-10-14","2026-10-15","2026-10-16",
                     "2026-10-19","2026-10-20","2026-10-21",
                     "2026-10-22","2026-10-23"]
    require(len(close)==30 and len(future)==8 and future==expected_future,
            "EXACT_OFFICIAL_RTH_EVENT_SCOPE")
    require(all(z.get("status")=="OBSERVED_WINDOW_ONLY" and
                z.get("nasdaq_condition6_observed",0)>0
                for z in close.values()),"REAL_AUCTION_OBSERVATIONS")
    matrix={
        "identity_and_share_class":{
            "sec_cik_exact":sec.get("sec_cik_exact") is True,
            "sec_10q_class_cover_jul31":cover.get("historical_sec_class_cover_verified") is True,
            "issuer_class_current_on_oct13":s.get("current_class_shares_reconciled") is True},
        "corrected_rth_close_dv30_condition6":{
            "sip_daily_exact30_raw":r.get("raw_completed_days")==30,
            "sip_daily_exact30_all_adjusted":r.get("all_adjusted_completed_days")==30,
            "sip_30min_dv30_observed_lower_bound_ge50m":
                r.get("observed_30min_lower_bound_state")=="LOWER_BOUND_GE_50M_SHADOW",
            "all_30_nasdaq_condition6_auction_samples_observed":True,
            "complete_corrected_close_tape_attested":
                p.get("exact_consolidated_close_corrections_pass") is True,
            "exact_c417_dv30_primary":p.get("exact_rth_dv30_primary_pass") is True},
        "independent_corporate_actions_pit":{
            "alpaca_ca_complete_one_page_zero_frog_events":
                a.get("complete",{}).get("status")=="SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET"
                and a.get("complete",{}).get("event_types")=={},
            "alpaca_ca_all_one_page_zero_frog_events":
                a.get("all",{}).get("status")=="SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET"
                and a.get("all",{}).get("event_types")=={},
            "alpaca_asof_publication_time_proved":
                a.get("asof_publication_time_confirmed") is True,
            "issuer_sec_ca_pit_independently_reconciled":
                s.get("corporate_actions_independent_pit_pass") is True},
        "same_asof_class_market_cap_ge_2b":{
            "historical_july31_class_shares_verified":cover.get("cover_shares_observed")==SHARES,
            "indicative_july31_shares_x_oct13_sip_close_ge10b":
                cover.get("observed_vintage_cap_band")=="GE_10B_SHADOW",
            "form4_form144_issuer_net_shares_rollforward_proved":
                s.get("current_class_shares_reconciled") is True,
            "issuer_net_cancellation_below_80pct_excluded":
                s.get("absence_of_80pct_change_proved") is True,
            "same_asof_corrected_market_cap_primary":
                s.get("asof_mc_ge_2b_primary_pass") is True},
        "history_260_52_setup_d_r1_rr_regime":{
            "candidate_deep_trigger_sha_bound":
                rollup.get("source_deep_sha256") is not None,
            "frog_d_frozen_r1_rr_geometry_pass":rollup.get("risk_rr_geometry_pass") is True,
            "stage1_260_52_observational_source_evaluated":
                rollup.get("real_trigger") is True,
            "full_history_corporate_actions_pit_primary":
                lastmile.get("history_260_52_corporate_actions_primary_pass") is True,
            "same_asof_regime_breadth_primary":
                rollup.get("regime_breadth_primary_pass") is True and
                lastmile.get("regime_breadth_primary_pass") is True},
        "eight_session_official_event_clear":{
            "issuer_news_and_events_http200":
                all(z.get("http_200") is True
                    for z in (e.get("pages") or {}).values())
                and len(e.get("pages") or {})==2,
            "eight_official_future_sessions_enumerated":future==expected_future,
            "full_eight_session_ir_calendar_attested":
                all(z.get("calendar_exact_eight_session_completeness_attested") is True
                    for z in (e.get("pages") or {}).values()),
            "future_material_issuer_events_explicitly_clear":
                e.get("eight_day_event_calendar_clear") is True},
        "sec_legal_and_historical_live_nasdaq_halt_clear":{
            "seven_sec_legal_docs_reviewed":sec.get("primary_documents_read")==7,
            "zero_severe_sec_legal_flags":sec.get("hard_legal_flag_count")==0,
            "issuer_legal_review_primary":sec.get("official_legal_clear_pit") is True,
            "oct13_nasdaq_halt_rss_http200_zero_frog":
                (h.get("observed_dates") or {}).get(ASOF,{}).get("http_200") is True
                and (h.get("observed_dates") or {}).get(ASOF,{}).get("frog_halt_rows_observed")==0,
            "full_30_day_official_halt_attested":
                h.get("historical_complete_clear_pass") is True,
            "fresh_live_halt_clear_attested":h.get("live_halt_clear_pass") is True}
    }
    require(len(matrix)==7 and all(type(v) is bool
                for group in matrix.values() for v in group.values()),
                "BOOLEAN_COMPONENT_MATRIX")
    return {key:{"components":group,
                 "verified_positive_components":sum(v is True for v in group.values()),
                 "required_components":len(group),
                 "unknown_components":[n for n,v in group.items() if v is not True]}
            for key,group in matrix.items()}

def seven_official_gate_readout(cover,rollup,lastmile):
    """Seven release proofs, using source facts rather than five observational shortcuts."""
    price=rollup["price"]
    corp=rollup["corporate_actions"]
    s=lastmile["sec"]
    p=lastmile["price"]
    e=lastmile["issuer_event"]
    h=lastmile["halt"]
    checks={
        "identity_and_share_class": (
            cover.get("historical_sec_class_cover_verified") is True and
            cover.get("cover_shares_observed")==123301311 and
            rollup.get("sec_mc_legal_event",{}).get("sec_cik_exact") is True),
        "corrected_rth_close_dv30_condition6": (
            price.get("dv30_primary_pass") is True and
            price.get("independent_close_corrections_verified") is True and
            p.get("exact_rth_dv30_primary_pass") is True and
            p.get("observed_auction_condition6_sessions")==30),
        "independent_corporate_actions_pit": (
            corp.get("ca_primary_pass") is True and
            s.get("corporate_actions_independent_pit_pass") is True),
        "same_asof_class_market_cap_ge_2b": (
            cover.get("class_aware_exact_asof_shares") is True and
            s.get("current_class_shares_reconciled") is True and
            s.get("asof_mc_ge_2b_primary_pass") is True),
        "history_260_52_setup_d_r1_rr_regime": (
            rollup.get("risk_rr_geometry_pass") is True and
            lastmile.get("regime_breadth_primary_pass") is True and
            lastmile.get("history_260_52_corporate_actions_primary_pass") is True),
        "eight_session_official_event_clear": (
            e.get("eight_day_event_calendar_clear") is True and
            e.get("all_material_8k_primary_review_complete") is True),
        "sec_legal_and_historical_live_nasdaq_halt_clear": (
            rollup.get("sec_mc_legal_event",{}).get("official_legal_review_status")=="PASS" and
            h.get("historical_complete_clear_pass") is True and
            h.get("live_halt_clear_pass") is True)
    }
    require(len(checks)==7,"SEVEN_EXACT_SOURCE_GATES")
    states={name:("PASS" if passed is True else "UNKNOWN")
            for name,passed in checks.items()}
    return {"states":states,"pass_count":sum(x=="PASS" for x in states.values()),
            "required":7,"missing":[k for k,v in states.items() if v!="PASS"]}

def build_candidate_local_terminal(result):
    """Derive an Oct13 research terminal without transplanting the Oct07 global canonical chain."""
    from frog_c417_first_registration_writer_v1 import root_sha
    source=result.get("source_json_sha256")
    gates=result.get("seven_official_source_release_gates") or {}
    states=gates.get("states") or {}
    require(type(source) is dict and len(source)==4,"CANDIDATE_SOURCE_SHA_SET")
    require(result.get("asof_et")==ASOF and result.get("symbol")=="FROG"
            and result.get("setup")=="D","CANDIDATE_TERMINAL_IDENTITY")
    require(len(states)==7 and gates.get("required")==7 and
            gates.get("pass_count")==sum(x=="PASS" for x in states.values()),
            "CANDIDATE_TERMINAL_SOURCE_GATE_COUNTS")
    require(set(states.values()).issubset({"PASS","UNKNOWN"}),
            "CANDIDATE_TERMINAL_GATE_STATES")
    first=result.get("first_registration_readiness") or {}
    return {"schema":"XRAY_FROG_ASOF_CANDIDATE_LOCAL_RESEARCH_TERMINAL_V1",
            "symbol":"FROG","setup":"D","asof_et":ASOF,
            "source_sha256":source,"evidence_root_sha256":root_sha(source),
            "observational_source_pass_count":len(result["observed_source_checks"]),
            "primary_gates":states,"primary_pass_count":gates["pass_count"],
            "primary_required_count":7,"primary_missing":gates["missing"],
            "candidate_source_asof_verified":True,
            "global_c417_current_terminal_reconstructed":False,
            "global_c417_current_terminal_asof":first.get("terminal_asof_et"),
            "eligible_for_c417_release":gates["pass_count"]==7 and
                first.get("terminal_2026_10_13_c417_ready") is True,
            "first_registration_ready":first.get("may_mint_first_registration_without_prior_ledger") is True,
            "first_registration_writer_staging_implemented":True,
            "first_registration_writer_requires_source_proofs_and_current_c417_terminal":True,
            "registration_does_not_require_prior_platform_delivery":True,
            "platform_delivery_requires_separate_acknowledgement":True,
            "registered_r92":result.get("r92_registered") is True,
            "platform_phone_receipt_verified":result.get("iphone_delivery_receipt_attested") is True,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest():
    from copy import deepcopy
    def sample():
        return (
            {"schema":"XRAY_FROG_OCT13_CLASS_SPECIFIC_10Q_COVER_AND_SIP_MC_SHADOW_V1",
             "symbol":"FROG","asof_et":ASOF,"execution":"NONE","real_money":"NO-GO",
             "cover_shares_observed":SHARES,"sec_cover_shares_observation_date":"2026-07-31",
             "sec_filing_date":"2026-08-07","historical_sec_class_cover_verified":True,
             "observed_vintage_cap_band":"GE_10B_SHADOW",
             "price_source_status":"ALPACA_RAW_AND_ALL_SIP_1DAY_ASOF_OBSERVED"},
            {"schema":"XRAY_FROG_20261013_CANDIDATE_LOCAL_LIVE_SOURCE_RECONCILIATION_V1",
             "symbol":"FROG","asof_et":ASOF,"execution":"NONE","real_money":"NO-GO",
             "price":{"raw_completed_days":30,"all_adjusted_completed_days":30,
                      "raw_vs_all_close_diff_days":0,
                      "observed_30min_lower_bound_state":"LOWER_BOUND_GE_50M_SHADOW"},
             "corporate_actions":{"complete":{"status":"SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET","event_types":{}},
                                  "all":{"status":"SOURCE_RESPONSES_COMPLETE_WITHIN_BUDGET","event_types":{}}}},
            {"schema":"XRAY_FROG_OCT13_LAST_MILE_SEC_FORM4_CA_EVENT_HALT_TRADE_SHADOW_V1",
             "symbol":"FROG","asof_et":ASOF,"execution":"NONE","real_money":"NO-GO",
             "sec":{"tracked_form_counts":{"4":18,"144":8,"10-Q":1},"all_issuer_filings_in_asof_interval":27,
                    "submissions_recent_covers_interval":True},
             "price":{"observed_sessions":30,"requested_sessions":30,"observed_auction_condition6_sessions":30},
             "issuer_event":{"pages":{"issuer_news":{"http_200":True},"issuer_events":{"http_200":True}}},
             "halt":{"snapshot_frog_veto":False,"observed_dates":{ASOF:{"http_200":True,"frog_halt_rows_observed":0}}}},
            {"can_create_r92":True,"r92_registration_mode":"INDEPENDENT_C417_RELEASE_APPROVAL_REQUIRED",
             "can_update_compiled_C417_alpha":True,"can_override_canonical_unknown":True,
             "observational_evidence_never_equivalent_to_release_primary":True,
             "canonical_unknown_override_semantics":"ONLY_AFTER_NEW_EXACT_SAME_ASOF_PRIMARY_EVIDENCE_IS_INDEPENDENTLY_VERIFIED",
             "r92_creation_requires_all_candidate_local_and_compiled_gates":True,
             "execution":"NONE","real_money":"NO-GO"})
    a=sample()
    sample_gates=seven_official_gate_readout(*a[:3])
    require(sample_gates["pass_count"]==0 and len(sample_gates["missing"])==7,
            "FIVE_OBSERVATIONS_NEVER_IMPLY_SEVEN_PRIMARY_RELEASE")
    result=decide(*a)
    require(result["policy_r92_conditional_permission_enabled"] and
            result["mathematical_vintage_scenario"]["required_minimum_share_cancellation_at_same_price"]==98641049 and
            not result["eligible_c417_primary"] and not result["r92_registered"],
            "CONDITIONAL_PASS_MATH_NO_FALSE_R92")
    for label,obj,key,val in (
        ("ASOF",0,"asof_et","2026-10-12"),("COVER",0,"cover_shares_observed",SHARES-1),
        ("R92_LOCK",3,"can_create_r92",False),("RELEASE_BYPASS",3,"r92_registration_mode","UNCONDITIONAL"),
        ("EXECUTION",2,"execution","ORDER")):
        bad=deepcopy(a);bad[obj][key]=val
        try:decide(*bad)
        except ValueError:pass
        else:raise AssertionError("FALSE_POSITIVE_"+label)
    synthetic={"schema":SCHEMA,"symbol":"FROG","setup":"D","asof_et":ASOF,
        "source_json_sha256":{z:"a"*64 for z in
             ("sec_cover","ca_price","sec_halt_event_auction","conditional_policy")},
        "observed_source_checks":{"a":"PASS_OBSERVED"},
        "seven_official_source_release_gates":{"states":{
             "identity_and_share_class":"PASS",
             "corrected_rth_close_dv30_condition6":"UNKNOWN",
             "independent_corporate_actions_pit":"UNKNOWN",
             "same_asof_class_market_cap_ge_2b":"UNKNOWN",
             "history_260_52_setup_d_r1_rr_regime":"UNKNOWN",
             "eight_session_official_event_clear":"UNKNOWN",
             "sec_legal_and_historical_live_nasdaq_halt_clear":"UNKNOWN"},
            "pass_count":1,"required":7,"missing":[
             "corrected_rth_close_dv30_condition6",
             "independent_corporate_actions_pit",
             "same_asof_class_market_cap_ge_2b",
             "history_260_52_setup_d_r1_rr_regime",
             "eight_session_official_event_clear",
             "sec_legal_and_historical_live_nasdaq_halt_clear"]},
        "first_registration_readiness":{"terminal_asof_et":"2026-10-07",
           "terminal_2026_10_13_c417_ready":False,
           "may_mint_first_registration_without_prior_ledger":False},
        "r92_registered":False,"iphone_delivery_receipt_attested":False}
    rt=build_candidate_local_terminal(synthetic)
    require(rt["asof_et"]==ASOF and rt["primary_pass_count"]==1 and
         rt["global_c417_current_terminal_asof"]=="2026-10-07" and
         rt["first_registration_writer_staging_implemented"] is True and
         rt["platform_delivery_requires_separate_acknowledgement"] is True and
         rt["eligible_for_c417_release"] is False and
         rt["global_c417_current_terminal_reconstructed"] is False,
         "CANDIDATE_LOCAL_TERMINAL_NOT_TRANSPLANTED_GLOBAL")
    from frog_c417_first_registration_writer_v1 import selftest as first_registry_selftest
    first_registry_selftest()
    print("XRAY_FROG_R92_MATH_SELFTEST=PASS_5_NEGATIVE_80PCT_CONDITIONAL_ONLY")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--cover",type=Path)
    p.add_argument("--rollup",type=Path)
    p.add_argument("--lastmile",type=Path)
    p.add_argument("--out",type=Path)
    x=p.parse_args()
    if x.selftest:return selftest()
    require(x.cover and x.rollup and x.lastmile and x.out and
            not x.out.resolve().is_relative_to(ROOT.parent.resolve()),"INPUTS")
    cover,sha_cover=load(x.cover)
    rollup,sha_rollup=load(x.rollup)
    lastmile,sha_lastmile=load(x.lastmile)
    policy,sha_policy=load(ROOT/"personal_research_technical_policy_v1.json")
    result=decide(cover,rollup,lastmile,policy,{"sec_cover":sha_cover,"ca_price":sha_rollup,"sec_halt_event_auction":sha_lastmile,"conditional_policy":sha_policy})
    result["seven_official_source_release_gates"]=seven_official_gate_readout(cover,rollup,lastmile)
    result["source_component_provenance_matrix"]=exact_primary_source_component_matrix(cover,rollup,lastmile)
    from frog_c417_first_registration_writer_v1 import (
        release_proved, terminal_proved, read_registration)
    terminal=json.loads((ROOT/"canonical_current_terminal.json").read_text())
    registry=json.loads((ROOT/"canonical_candidate_lifecycle_registry.json").read_text())
    compiled=json.loads((ROOT/"chatgpt_compiled_policy_v3.json").read_text())
    source_hashes={"sec_cover":sha_cover,"ca_price":sha_rollup,
                   "sec_halt_event_auction":sha_lastmile,
                   "conditional_policy":sha_policy}
    candidate_release=release_proved(result)
    terminal_release=terminal_proved(result,terminal,compiled) if candidate_release else False
    result["first_registration_readiness"]={
        "independent_seven_gates_ready":candidate_release,
        "terminal_2026_10_13_c417_ready":terminal_release,
        "may_mint_first_registration_without_prior_ledger":bool(candidate_release and terminal_release),
        "registration_in_actual_registry":read_registration(registry,terminal,compiled,source_hashes),
        "platform_delivery_acknowledged":result["iphone_delivery_receipt_attested"],
        "terminal_asof_et":terminal.get("asof_et"),
        "registry_asof_et":registry.get("asof_et")}
    result["source_json_sha256"]={"sec_cover":sha_cover,"ca_price":sha_rollup,
                                  "sec_halt_event_auction":sha_lastmile,"conditional_policy":sha_policy}
    result["candidate_local_terminal_20261013"]=build_candidate_local_terminal(result)
    x.out.write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10))
    print("XRAY_FROG_R92_MATH_SAME_PRICE_MIN_CANCELLATIONS="+str(result["mathematical_vintage_scenario"]["required_minimum_share_cancellation_at_same_price"]))
    print("XRAY_FROG_R92_SOURCE_OBSERVATIONS=5_PASS")
    print("XRAY_FROG_SEVEN_OFFICIAL_PRIMARY_PASS="+str(result["seven_official_source_release_gates"]["pass_count"])+"/7")
    print("XRAY_FROG_SEVEN_GATE_SOURCE_COMPONENTS="+json.dumps({k:v["verified_positive_components"] for k,v in result["source_component_provenance_matrix"].items()},sort_keys=True))
    print("XRAY_FROG_R92_RELEASE_EVIDENCE_MISSING="+str(len(result["missing_release_evidence"])))
    print("XRAY_FROG_CANDIDATE_LOCAL_TERMINAL_ASOF="+
          result["candidate_local_terminal_20261013"]["asof_et"]+
          "_NOT_GLOBAL_CANONICAL_CURRENT")
    print("XRAY_FROG_FIRST_REGISTRATION_READY="+
          str(result["first_registration_readiness"]["may_mint_first_registration_without_prior_ledger"]).upper())
    print("XRAY_FROG_R92_CANONICAL=BLOCKED_INDEPENDENT_C417_R92_FALSE")

if __name__=="__main__":main()
