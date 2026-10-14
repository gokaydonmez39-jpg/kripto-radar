#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
j=json.loads((ROOT/"provider_automation_governance.json").read_text())
assert j["schema"]=="XRAY_PROVIDER_AUTOMATION_GOVERNANCE_V1"
assert j["execution"]=="NONE" and j["real_money"]=="NO-GO"
assert j["unknown_never_pass"] is True and j["no_paid_fallback"] is True
a=j["providers"]["ALPHASTOCKS"]
assert a["unattended_automation_allowed"] is False
assert a["cutover"] is False
assert "UNKNOWN" in a["production_effect"]
assert j["providers"]["ALPACA"]["live_sip_g9_allowed"] is False
assert j["providers"]["BIGDATA"]["paid_top_up_allowed"] is False
assert j["providers"]["LONGBRIDGE"]["broad_market_data_core_allowed"] is False
rallies=j["providers"]["RALLIES"]
assert rallies["positive_price_dv30_promotion_allowed"] is False
assert rallies["passive_reader_positive_promotion_allowed"] is False
assert rallies["automated_non_display_runner_entitlement"]=="NOT_ATTESTED"
assert rallies["unadjusted_official_rth_integer_volume_lineage"]=="NOT_ATTESTED"
assert rallies["unverified_existing_passive_reader_price_dv30"]=="QUARANTINE_UNKNOWN_NOT_AUTHORITY"
assert rallies["no_threshold_change"] is True and rallies["no_fabricated_pass"] is True
assert rallies["paid_top_up_allowed"] is False
assert "fractional" in rallies["volume_integrity"].lower()
bq=j["providers"]["BUSINESSQUANT"]
assert bq["role"]=="C417_MC_HISTORICAL_DAILY_RESEARCH_SHADOW_NOT_PRIMARY"
assert bq["official_api_terms"]=="https://businessquant.com/terms-of-use"
assert bq["free_plan_api_calls_per_day_documented"]==30
assert bq["historical_mc_tickers_per_call_documented"]==5
assert bq["api_is_authorized_programmatic_access_subject_to_account_plan"] is True
assert bq["personal_account_api_key_connected_to_github"]=="NOT_ATTESTED"
assert bq["unattended_runner_use_entitlement_for_this_account"]=="NOT_ATTESTED"
assert bq["same_asof_issuer_filing_acceptance_pit"]=="NOT_ATTESTED"
assert bq["current_usd_share_class_mc_authority"]=="NOT_ATTESTED"
assert bq["price_pass_scope_required"] is True
assert bq["automated_research_call_allowed_without_key_and_rights"] is False
assert bq["primary_mc_promotion_allowed"] is False
assert bq["r92_promotion_allowed"] is False and bq["paid_upgrade_allowed"] is False
assert bq["no_vendor_raw_data_in_public_github"] is True
assert bq["execution"]=="NONE" and bq["real_money"]=="NO-GO"
td=j["providers"]["TWELVE_DATA"]
assert td["role"]=="C417_COMPLETED_EOD_OHLCV_RESEARCH_CANDIDATE_NOT_MC_PRIMARY"
assert td["free_basic_api_credits_per_minute_advertised"]==8
assert td["free_basic_api_credits_per_day_advertised"]==800
assert td["internal_non_display_listed_on_free_plan"] is True
assert td["github_runner_api_key_and_own_account_entitlement"]=="NOT_ATTESTED"
assert td["current_exact30_unadjusted_nasdaq_rth_integer_volume_lineage"]=="NOT_ATTESTED"
assert td["same_asof_260_sessions_52_completed_weeks"]=="NOT_ATTESTED"
assert td["coverage_for_540_unknown"]=="NOT_ATTESTED"
assert td["market_cap_source"]=="NOT_PROVEN_FOR_BASIC"
assert td["primary_mc_promotion_allowed"] is False
assert td["price_dv30_positive_promotion_allowed"] is False
assert td["r92_promotion_allowed"] is False and td["paid_upgrade_allowed"] is False
assert td["execution"]=="NONE" and td["real_money"]=="NO-GO"
massive=j["providers"]["MASSIVE"]
def require(condition,reason):
    if not condition:raise ValueError("XRAY_MASSIVE_"+reason)
require(massive["role"]=="INDEPENDENT_INTERACTIVE_PRICE_CROSSCHECK_RESEARCH_ONLY",
        "NOT_PRICE_CROSSCHECK_ONLY")
require(massive["sample_daily_volume_integrity"]==
        "FRACTIONAL_NOT_INTEGER_AAPL_OCT13","FRACTIONAL_EVIDENCE_LOST")
require(massive["github_runner_api_key_and_entitlement"]=="NOT_ATTESTED"
        and massive["automated_non_display_entitlement"]=="NOT_ATTESTED",
        "RUNNER_PERMISSION_GUESSED")
require(massive["positive_price_dv30_promotion_allowed"] is False
        and massive["primary_mc_promotion_allowed"] is False
        and massive["strict_g9_promotion_allowed"] is False
        and massive["r92_promotion_allowed"] is False
        and massive["paid_top_up_allowed"] is False,
        "FALSE_PRIMARY_OR_LICENSE_SHORTCUT")
# Synthetic adversarial v test: finite integer is mandatory for current
# policy; fractional vendor daily volume must not be rounded.
import math
def valid_integer_volume(value):
    return (type(value) in (int,float) and math.isfinite(value)
            and value>0 and int(value)==value)
require(valid_integer_volume(38983564) and
        not valid_integer_volume(38983564.125) and
        not valid_integer_volume(float("nan")) and
        not valid_integer_volume(True),
        "FRACTIONAL_OR_NONFINITE_VOLUME_ACCEPTED")
print("XRAY_MASSIVE_BACKUP_SELFTEST=PASS_FRACTIONAL_QUARANTINE_4_NEGATIVES_NO_PRIMARY")
print("XRAY_BACKUP_PROVIDER_BQ_TWELVE_SELFTEST=PASS_DOCUMENTED_FREE_NOT_ACTIVATED_RIGHTS_ASOF_AND_NO_PRIMARY")
print("XRAY_PROVIDER_AUTOMATION_GOVERNANCE_SELFTEST=PASS")

# READINESS_WORKFLOW_RUN_REBIND_PROBE_2026_10_05: no semantic change.
