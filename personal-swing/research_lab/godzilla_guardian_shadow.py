"""XRAY NASDAQ BLACK-SWAN GUARDIAN: offline, hypothetical risk research ONLY.

No production imports, network, market discovery, Sheets, ChatGPT messages,
model selection, broker, order generation, account queries or trading approval.
Data/rights hashes are schema checks, not verified provenance attestations.
A 2-ATR adverse exit scenario is NOT an upper bound on market losses.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
import re

import exchange_calendars as ec

SCHEMA = "XRAY_NASDAQ_GUARDIAN_PAPER_V1"
SOURCE = "ALPACA_IEX_RAW_1D"
SHA = re.compile(r"^[a-f0-9]{64}$")
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,15}$")
KEYS = frozenset((
    "schema", "source", "symbol", "asof_et", "scope_sha256",
    "algorithm_sha256", "consecutive_xnas_sessions",
    "universe_477_valid", "previous_active_episode",
    "reference_close", "original_stop", "original_target",
    "hypothetical_next_open", "atr14", "paper_equity_usd",
    "paper_risk_bps", "paper_exposure_cap_bps", "spread_bps",
    "slippage_bps", "fees_bps", "adverse_gap_atr",
))


class GuardianBlocked(ValueError):
    pass


def need(condition: bool, reason: str):
    if not condition:
        raise GuardianBlocked(reason)


def amount(value, *, allow_zero=False):
    need(type(value) in (int, float, str, Decimal), "NONNUMERIC_AMOUNT")
    try:
        v = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise GuardianBlocked("INVALID_AMOUNT") from exc
    need(v.is_finite() and (v >= 0 if allow_zero else v > 0),
         "NONFINITE_OR_NONPOSITIVE_AMOUNT")
    return v


def bps(value, *, maximum, allow_zero=False):
    v = amount(value, allow_zero=allow_zero)
    need(v <= Decimal(maximum), "BPS_OUTSIDE_CONTRACT")
    return v / Decimal(10000)


def _canonical_date(value):
    need(type(value) is str, "BAD_ASOF_TYPE")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise GuardianBlocked("BAD_ASOF_DATE") from exc
    need(d.isoformat() == value, "BAD_ASOF_CANONICAL")
    return value


def _safe_stub(kind, code):
    return {
        "schema": SCHEMA, "decision": kind, "reason": code,
        "automatic_trade": False, "broker_access": False, "orders": False,
        "production_al_change": False, "can_emit_alert": False,
        "device_ack_proven": False, "real_fill_proven": False,
        "scientific_alpha_proven": False, "live_trading_authorized": False,
        "proof_scope": "SYNTHETIC_OR_EXTERNALLY_SUPPLIED_PAPER_ONLY",
    }


def guardian(candidate):
    """Evaluate one externally supplied scenario; NEVER return trading GO."""
    need(type(candidate) is dict and set(candidate) == KEYS,
         "MISSING_OR_EXTRA_FIELDS")
    need(candidate["schema"] == SCHEMA and candidate["source"] == SOURCE,
         "INVALID_SCHEMA_OR_PRICE_SOURCE")
    symbol = candidate["symbol"]
    need(type(symbol) is str and SYMBOL.fullmatch(symbol), "INVALID_SYMBOL")
    asof = _canonical_date(candidate["asof_et"])
    need(ec.get_calendar("XNAS").is_session(asof), "ASOF_NOT_OFFICIAL_XNAS_SESSION")
    need(all(type(candidate[k]) is str and SHA.fullmatch(candidate[k])
             for k in ("scope_sha256", "algorithm_sha256")),
         "SOURCE_POLICY_HASH_NOT_ATTESTED")
    need(type(candidate["consecutive_xnas_sessions"]) is int and
         candidate["consecutive_xnas_sessions"] == 52 and
         candidate["universe_477_valid"] is True,
         "NOT_477_52_XNAS_EVIDENCE")
    need(type(candidate["previous_active_episode"]) is bool,
         "PRIOR_EPISODE_STATUS_UNKNOWN")
    close, stop, target, opening, atr = (
        amount(candidate[k]) for k in (
            "reference_close", "original_stop", "original_target",
            "hypothetical_next_open", "atr14"))
    need(stop < close < target, "IMMUTABLE_LEVEL_GEOMETRY")
    need(abs(target - (close + 2 * (close - stop))) <= Decimal("0.025"),
         "ORIGINAL_TARGET_NOT_2R")
    need(2 * atr / close <= Decimal("0.08"),
         "ORIGINAL_ATR_RISK_LIMIT_MISMATCH")
    equity = amount(candidate["paper_equity_usd"])
    risk = bps(candidate["paper_risk_bps"], maximum=10000)
    exposure = bps(candidate["paper_exposure_cap_bps"], maximum=10000)
    spread = bps(candidate["spread_bps"], maximum=500, allow_zero=True)
    slip = bps(candidate["slippage_bps"], maximum=500, allow_zero=True)
    fees = bps(candidate["fees_bps"], maximum=500, allow_zero=True)
    gap = amount(candidate["adverse_gap_atr"], allow_zero=True)
    need(gap <= 20, "GAP_STRESS_OUTSIDE_BOUND")

    result = _safe_stub("HOLD", "NOT_PROMOTED")
    result.update({
        "symbol": symbol, "asof_et": asof,
        "input_sha256": hashlib.sha256(json.dumps(
            candidate, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()).hexdigest(),
        "paper_risk_budget_usd": str(equity * risk),
        "paper_exposure_cap_usd": str(equity * exposure),
        "hypothetical_share_cap": 0,
        "scenario_is_a_loss_ceiling": False,
        "stop_is_guaranteed_fill": False,
        "liquidity_and_market_impact_verified": False,
        "quote_freshness_and_execution_verified": False,
    })
    if candidate["previous_active_episode"]:
        result["reason"] = "EXISTING_ACTIVE_EPISODE_NO_SECOND_NEW_AL"
        return result
    if not (stop < opening < target):
        result["reason"] = "NEXT_OPEN_OUTSIDE_ORIGINAL_LEVELS_NO_ENTRY"
        return result

    # Explicitly separate theoretical price-stop loss and a lower stress exit.
    stress_exit = max(Decimal(0), stop - gap * atr)
    entry_cost_per_share = opening * (spread + slip + fees)
    normal_exit_cost = stop * (slip + fees)
    stress_exit_cost = stress_exit * (slip + fees)
    nominal_unit_loss = opening - stop + entry_cost_per_share + normal_exit_cost
    stress_unit_loss = opening - stress_exit + entry_cost_per_share + stress_exit_cost
    need(stress_unit_loss >= nominal_unit_loss > 0,
         "STRESS_MONOTONICITY_FAILURE")

    loss_cap = equity * risk
    exposure_cap = equity * exposure
    by_stress = int((loss_cap / stress_unit_loss).to_integral_value(rounding=ROUND_FLOOR))
    by_exposure = int((exposure_cap / opening).to_integral_value(rounding=ROUND_FLOOR))
    quantity = min(by_stress, by_exposure)
    result.update({
        "reason": "PAPER_ONLY_NO_TRADE_APPROVAL" if quantity > 0
                  else "HOLD_PAPER_BUDGET_BELOW_ONE_SHARE",
        "hypothetical_share_cap": quantity,
        "normal_stop_unit_loss_usd": str(nominal_unit_loss),
        "stress_exit_price_usd": str(stress_exit),
        "stressed_unit_loss_usd": str(stress_unit_loss),
        "stressed_paper_loss_usd": str(stress_unit_loss * quantity),
        "stressed_paper_loss_budget_pass": stress_unit_loss * quantity <= loss_cap,
        "stressed_paper_notional_usd": str(opening * quantity),
        "exposure_budget_pass": opening * quantity <= exposure_cap,
        "stress_model": "STOP_MINUS_USER_SUPPLIED_ATR_MULTIPLE_WITH_FRICTION",
    })
    return result
