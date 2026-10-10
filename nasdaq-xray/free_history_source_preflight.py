#!/usr/bin/env python3
"""C4.17 zero-dollar historical OHLCV source feasibility, research only.

No network calls, credentials, vendor bars, market-cap authority, HISTORY PASS,
or AL registration. Makes published free-plan quotas observable without
claiming the runner holds an individual non-display/data-retention entitlement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PRICE = "nasdaq-xray/canonical_current_price_dv30.json"
SCHEMA = "XRAY_ZERO_DOLLAR_HISTORY_PROVIDER_PREFLIGHT_V1"
TWELVE_PRICING = "https://twelvedata.com/pricing"
TWELVE_TERMS = "https://twelvedata.com/terms"
TWELVE_DOCS = "https://twelvedata.com/docs"
BASIC_DAILY = 800
BASIC_PER_MINUTE = 8
SERIES_COST_PER_SYMBOL = 1
REQUEST_DAILY_OUTPUTSIZE = 320
FULL_UNIVERSE_REFERENCE = 3401
EULERPOOL_MONTHLY_REQUESTS = 100000  # 2026-10-09 current official pricing, NOT granted entitlement
BUSINESSQUANT_DAILY_REQUESTS = 30
BUSINESSQUANT_MONTHLY_GB = 0.1
STRESS_SESSIONS_PER_MONTH = 22  # conservative calendar stress scenario, NOT a forecast


def make(price: dict, source_blob_sha: str, universe_count: int = FULL_UNIVERSE_REFERENCE) -> dict:
    symbols = price.get("pass_symbols")
    assert isinstance(symbols, list) and bool(symbols)
    assert symbols == sorted(set(symbols)), "PRICE_DUPLICATE_OR_UNSORTED"
    assert len(symbols) == price.get("pass_count"), "PRICE_COUNT_DRIFT"
    assert hashlib.sha256("\n".join(symbols).encode()).hexdigest() == price.get("pass_hash"), "PRICE_HASH_DRIFT"
    # Estimate only independently proven PASS symbols; global UNKNOWN rows
    # are not converted to PASS and cannot starve source-quota research.
    unknown=price.get("unknown_symbols", [])
    blocked=price.get("blocked_symbols", [])
    assert isinstance(unknown,list) and unknown==sorted(set(unknown)), "UNKNOWN_SCOPE_INVALID"
    assert isinstance(blocked,list) and blocked==sorted(set(blocked)), "BLOCKED_SCOPE_INVALID"
    assert type(price.get("unknown_count")) is int and price["unknown_count"]==len(unknown), "UNKNOWN_COUNT_MISMATCH"
    assert type(price.get("blocked_count",0)) is int and price.get("blocked_count",0)==len(blocked), "BLOCKED_COUNT_MISMATCH"
    assert not (set(symbols)&set(unknown) or set(symbols)&set(blocked) or set(unknown)&set(blocked)), "PRICE_SCOPE_OVERLAP"
    assert price.get("execution") == "NONE" and price.get("real_money") == "NO-GO", "SAFETY_MISMATCH"
    asof = price.get("asof_et")
    assert isinstance(asof, str) and len(asof) == 10, "ASOF_INVALID"
    assert isinstance(source_blob_sha, str) and len(source_blob_sha) == 40, "BLOB_UNVERIFIED"
    assert type(universe_count) is int and universe_count >= len(symbols)
    count = len(symbols)
    credits = count * SERIES_COST_PER_SYMBOL
    return {
        "schema": SCHEMA, "status": "RESEARCH_QUOTA_FEASIBLE_ENTITLEMENT_AND_BARS_UNVERIFIED",
        "asof_et": asof, "policy": "C4.17", "control": "C4.27",
        "source_price_path": PRICE, "source_price_blob_sha": source_blob_sha,
        "price_pass_count": count, "price_pass_hash": price["pass_hash"],
        "price_unknown_count":len(unknown), "price_blocked_count":len(blocked),
        "unknown_blocked_excluded_from_quota":True,
        "global_price_partition_complete":not unknown and not blocked,
        "full_universe_reference_count": universe_count,
        "provider": "Twelve Data Basic", "tier_cost_usd_per_month": 0,
        "public_documented_internal_non_display": True,
        "public_documented_batch_requests": True,
        "quota_credits_daily": BASIC_DAILY,
        "quota_credits_per_minute": BASIC_PER_MINUTE,
        "time_series_credit_per_symbol": SERIES_COST_PER_SYMBOL,
        "intended_interval": "1day", "intended_outputsize": REQUEST_DAILY_OUTPUTSIZE,
        "required_independent_completed_daily_sessions": 260,
        "required_completed_week_closes": 52,
        "scope_initial_credit_estimate": credits,
        "scope_fits_published_daily_budget": credits <= BASIC_DAILY,
        "scope_lower_bound_minutes_at_published_rate": math.ceil(credits / BASIC_PER_MINUTE),
        "universe_initial_credit_estimate": universe_count * SERIES_COST_PER_SYMBOL,
        "universe_min_calendar_days_at_published_daily_limit":
            math.ceil(universe_count * SERIES_COST_PER_SYMBOL / BASIC_DAILY),
        "universe_full_daily_refresh_fits_one_key": universe_count <= BASIC_DAILY,
        # Official /market_cap docs: 5 credits/request, Ultra (individual)
        # or Enterprise (business) ONLY. Free Basic historical OHLCV quota
        # does NOT solve the independent C4.17 same-ASOF PRIMARY MC gate.
        "twelve_market_cap_endpoint_credits_per_request": 5,
        "twelve_market_cap_minimum_individual_tier": "Ultra",
        "twelve_market_cap_basic_available": False,
        "twelve_market_cap_can_supply_primary_mc": False,
        "twelve_market_cap_official_documentation": TWELVE_DOCS,
        "source_eod_publication_rule": "AFTER_00_00_ET_NEXT_NASDAQ_TRADING_DAY",
        "source_eod_publication_independent_bar_observation": False,
        "scope_actual_endpoint_entitlement_verified": False,
        "historical_320_bars_retrieved": False,
        "actual_260_daily_52_week_source_proven": False,
        "exact_514_source_vendor_bar_set_proven": False,
        "license_storage_and_third_party_conditions_verified": False,
        "rights_to_store_raw_ohlcv_on_public_github": False,
        "canonical_history_pass_created": 0,
        "primary_mc_pass_created": 0,
        "history_authoritative": False,
        "can_register_R92": False, "execution": "NONE",
        "real_money": "NO-GO", "unknown_never_pass": True,
        "other_free_source_quota_research": {
            "Eulerpool Free": {
                "official_pricing": "https://eulerpool.com/financial-data-api/pricing",
                "official_licensing": "https://eulerpool.com/financial-data-api/licensing",
                "official_history": "https://eulerpool.com/financial-data-api/historical-data",
                "monthly_requests": EULERPOOL_MONTHLY_REQUESTS,
                "personal_noncommercial_only": True,
                "free_batch_max_symbols_advertised": 10,
                "single_symbol_history_requests_514_scope": count,
                "single_symbol_history_requests_3401_universe": universe_count,
                "stress_22_session_full_universe_requests": universe_count * STRESS_SESSIONS_PER_MONTH,
                "stress_22_session_full_universe_fits_monthly": universe_count * STRESS_SESSIONS_PER_MONTH <= EULERPOOL_MONTHLY_REQUESTS,
                "stress_22_session_514_scope_requests": count * STRESS_SESSIONS_PER_MONTH,
                "requires_api_key": True,
                "api_key_available_in_actions_verified": False,
                "full_history_endpoint_260_actual_bars_tested": False,
                "data_retention_for_free_runner_granted": False,
                "market_data_provenance_qualified": False,
                "same_asof_class_mc_qualified": False,
                "advertised_limit_in_all_marketing_consistent": False,
                "public_blog_some_pages_still_say_10000": True,
                "production_authority": False,
            },
            "Business Quant Free": {
                "official_pricing": "https://businessquant.com/pricing",
                "official_terms": "https://businessquant.com/terms-of-use",
                "official_history": "https://businessquant.com/docs/api/quotes",
                "daily_requests": BUSINESSQUANT_DAILY_REQUESTS,
                "monthly_data_transfer_gb": BUSINESSQUANT_MONTHLY_GB,
                "multi_ticker_eod_advertised": True,
                "minimum_symbols_per_request_to_cover_scope_in_one_day": math.ceil(count / BUSINESSQUANT_DAILY_REQUESTS),
                "actual_batch_max_verified": False,
                "registered_key_available": False,
                "actual_260_bar_full_scope_verified": False,
                "public_data_repository_export_authorized": False,
                "production_authority": False,
            },
            "HF Data Library": {
                "official_api": "https://hfdatalibrary.com/pages/api",
                "upstream_terms": "https://www.iex.io/legal/hist-data-terms",
                "published_tickers_reference": 1391,
                "post_2022_venue": "IEX_ONLY_NOT_CONSOLIDATED",
                "post_2022_data_qualifies_as_NASDAQ_consolidated_DV30": False,
                "scope_coverage_514_verified": False,
                "registration_or_free_rotating_key_required": True,
                "production_authority": False,
            },
        },
        "source_urls": [TWELVE_PRICING, TWELVE_TERMS, TWELVE_DOCS],
        "scope_symbol_list_committed": False,
        "vendor_bars_committed": False,
        "next": "Only after lawful Basic entitlement, retention conditions, secret-in-runner and actual 320-bar probe are independently verified: private history retrieval, session/issuer/corporate-action check, then separate authority gate"
    }


def selftest() -> None:
    syms = ["AAA", "BBB"]
    p = {"pass_symbols": syms, "pass_count": 2, "pass_hash": hashlib.sha256("\n".join(syms).encode()).hexdigest(),
         "unknown_count": 0, "unknown_symbols":[], "blocked_count":0, "blocked_symbols":[],
         "execution": "NONE", "real_money": "NO-GO", "asof_et": "2026-10-08"}
    v = make(p, "a" * 40)
    assert v["scope_initial_credit_estimate"] == 2
    partial=dict(p, unknown_count=1, unknown_symbols=["CCC"])
    partial_out=make(partial,"a"*40)
    assert partial_out["scope_initial_credit_estimate"]==2
    assert partial_out["price_unknown_count"]==1
    assert partial_out["unknown_blocked_excluded_from_quota"] is True
    assert partial_out["global_price_partition_complete"] is False
    assert partial_out["history_authoritative"] is False and partial_out["can_register_R92"] is False
    assert v["universe_min_calendar_days_at_published_daily_limit"] == 5
    assert v["universe_full_daily_refresh_fits_one_key"] is False
    assert v["history_authoritative"] is False and v["can_register_R92"] is False
    assert v["twelve_market_cap_basic_available"] is False
    assert v["twelve_market_cap_can_supply_primary_mc"] is False
    assert v["twelve_market_cap_minimum_individual_tier"]=="Ultra"
    assert v["source_eod_publication_rule"]=="AFTER_00_00_ET_NEXT_NASDAQ_TRADING_DAY"
    other = v["other_free_source_quota_research"]
    e = other["Eulerpool Free"]
    assert e["stress_22_session_full_universe_requests"] == 3401 * 22
    assert e["stress_22_session_full_universe_fits_monthly"] is True
    assert e["single_symbol_history_requests_514_scope"] == 2
    assert e["production_authority"] is False
    b = other["Business Quant Free"]
    assert b["minimum_symbols_per_request_to_cover_scope_in_one_day"] == 1
    assert b["production_authority"] is False
    assert other["HF Data Library"]["post_2022_data_qualifies_as_NASDAQ_consolidated_DV30"] is False
    wide = dict(p, pass_symbols=[f"S{i:04d}" for i in range(801)], pass_count=801)
    wide["pass_hash"] = hashlib.sha256("\n".join(wide["pass_symbols"]).encode()).hexdigest()
    out = make(wide, "a" * 40)
    assert out["scope_initial_credit_estimate"] == 801 and out["scope_fits_published_daily_budget"] is False
    assert out["scope_lower_bound_minutes_at_published_rate"] == 101
    assert out["history_authoritative"] is False
    assert out["other_free_source_quota_research"]["Business Quant Free"]["minimum_symbols_per_request_to_cover_scope_in_one_day"] == 27
    assert out["other_free_source_quota_research"]["Eulerpool Free"]["production_authority"] is False
    corruptions = [
        dict(p, pass_count=3),
        dict(p, pass_hash="0" * 64),
        dict(p, unknown_count=1),
        dict(p, unknown_count=1, unknown_symbols=["AAA"]),
        dict(p, blocked_count=1, blocked_symbols=["BBB"]),
        dict(p, execution="REAL"),
        dict(p, pass_symbols=["AAA", "AAA"]),
    ]
    for bad in corruptions:
        try:
            make(bad, "a" * 40)
        except AssertionError:
            continue
        raise AssertionError("ACCEPTED_BAD_PRICE_SCOPE_OR_SAFETY")
    print("XRAY_TWELVE_FREE_HISTORY_PREFLIGHT_SELFTEST=PASS_2_QUOTA_CASES_5_NEGATIVES_NO_VENDOR_OR_ALPHA_AUTHORITY")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    price = json.loads((REPO / PRICE).read_text(encoding="utf-8"))
    sha = subprocess.check_output(["git", "hash-object", str(REPO / PRICE)], cwd=REPO, text=True).strip()
    out = make(price, sha)
    if args.out:
        args.out.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("XRAY_TWELVE_FREE_PREFLIGHT=" + out["status"])
    print("XRAY_TWELVE_SCOPE=" + str(out["price_pass_count"]))
    print("XRAY_TWELVE_MIN_CREDITS=" + str(out["scope_initial_credit_estimate"]))
    print("XRAY_TWELVE_MIN_MINUTES=" + str(out["scope_lower_bound_minutes_at_published_rate"]))
    alt = out["other_free_source_quota_research"]
    print("XRAY_EULERPOOL_FREE_MONTHLY_CAP=" + str(alt["Eulerpool Free"]["monthly_requests"]))
    print("XRAY_EULERPOOL_FULL3401_STRESS22_REQUESTS=" + str(alt["Eulerpool Free"]["stress_22_session_full_universe_requests"]))
    print("XRAY_BUSINESSQUANT_FREE_MIN_BATCH_SIZE=" + str(alt["Business Quant Free"]["minimum_symbols_per_request_to_cover_scope_in_one_day"]))
    print("XRAY_HF_IEX_ONLY_NOT_CONSOLIDATED=PASS_NONAUTHORITY")
    print("XRAY_TWELVE_LICENSE_AND_BARS=" + ("UNVERIFIED" if not out["history_authoritative"] else "ERROR"))
    print("XRAY_TWELVE_BASIC_PRIMARY_MC=NOT_AVAILABLE_ULTRA_ONLY")


if __name__ == "__main__":
    main()
