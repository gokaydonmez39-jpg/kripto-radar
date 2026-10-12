#!/usr/bin/env python3
"""C4.18 PERSONAL research-only issuer-class market-cap lower-bound certificate.

Pure math with explicit SEC filing-vintage + Alpaca SIP EOD evidence.
Never creates C4.17 PRIMARY, HISTORY PASS, R92, GO, real-money orders,
paid requests, alerts or vendor data exports. Upstream proof remains required.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from zoneinfo import ZoneInfo

SCHEMA = "XRAY_C418_SEC_ALPACA_CLASS_MC_FLOOR_RESEARCH_V1"
FLOOR = Decimal("2000000000")
NY = ZoneInfo("America/New_York")
SHA = re.compile(r"^[a-f0-9]{64}$")
TICKER = re.compile(r"^[A-Z0-9.\-]{1,12}$")


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return out.astimezone(timezone.utc) if out.tzinfo is not None else None
    except ValueError:
        return None


def prove(row):
    """Issue redacted, non-authoritative proof from *verified* class-level inputs.

    Under an independently proven class identity and audited maximum later share reduction, nonnegative equity
    class values imply issuer equity MC >= class outstanding shares * close.
    A valid floor certificate is necessary evidence for a future policy source,
    NOT C4.17 MC authority. A SHA string alone never proves issuer/usage rights.
    """
    if not isinstance(row, dict):
        raise ValueError("ROW_NOT_OBJECT")
    asof, symbol, cik = (row.get("asof_et"), row.get("symbol"), row.get("cik"))
    if not (isinstance(asof, str) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", asof)
            and isinstance(symbol, str) and TICKER.fullmatch(symbol)
            and isinstance(cik, str) and re.fullmatch(r"\d{10}", cik)):
        raise ValueError("BAD_IDENTITY")
    day = date.fromisoformat(asof)

    def unknown(reason):
        return {"schema": SCHEMA, "asof_et": asof, "symbol": symbol,
                "status": "UNKNOWN_" + reason, "can_create_PRIMARY": False,
                "can_create_R92": False, "execution": "NONE",
                "real_money": "NO-GO", "unknown_never_pass": True}

    for field in ("sec_filing_sha256", "sec_class_identity_sha256",
                  "actions_interval_sha256", "alpaca_bar_sha256"):
        if not isinstance(row.get(field), str) or not SHA.fullmatch(row[field]):
            return unknown("MISSING_EVIDENCE_DIGEST")

    necessary = ("class_shares_pit_verified", "sec_class_ticker_exact",
                 "accepted_before_official_close", "actions_interval_exhaustive",
                 "split_and_conversion_adjusted", "alpaca_same_session_sip_eod",
                 "issuer_common_equity_class_verified",
                 "not_adr_or_depositary_receipt")
    if any(row.get(key) is not True for key in necessary):
        return unknown("ISSUER_CLASS_CA_OR_PIT_UNPROVEN")
    if row.get("source_rights_attested") is not True:
        return unknown("PERSONAL_USAGE_RIGHTS_UNVERIFIED")

    observed = row.get("shares_observation_date")
    accepted, price_stamp = (_utc(row.get("filing_accepted_utc")),
                             _utc(row.get("alpaca_bar_utc")))
    try:
        observed = date.fromisoformat(observed)
    except (TypeError, ValueError):
        return unknown("INVALID_SHARES_VINTAGE")
    official_close = datetime.combine(day, datetime.min.time()).replace(
        tzinfo=NY, hour=16).astimezone(timezone.utc)
    if (observed > day or (day - observed).days > 120 or accepted is None
            or accepted > official_close or price_stamp is None
            or price_stamp.astimezone(NY).date() != day):
        return unknown("LOOKAHEAD_OR_STALE_OR_WRONG_SESSION")
    if type(row.get("outstanding_class_shares")) is not int:
        return unknown("SHARE_TYPE_INVALID")
    try:
        shares = row["outstanding_class_shares"]
        close = Decimal(str(row.get("sip_close_usd")))
    except (InvalidOperation, ValueError):
        return unknown("PRICE_PARSE_INVALID")
    if shares <= 0 or not close.is_finite() or close <= 0:
        return unknown("NONPOSITIVE_OR_NONFINITE")
    # PIT share vintages are NOT current lower bounds: buybacks can reduce shares.
    # Only an independently audited upper bound on shares removed since the
    # historical filing permits a conservative *current* minimum.
    bound_sha = row.get("post_vintage_share_change_audit_sha256")
    if (row.get("max_share_reduction_asof_verified") is not True
            or not isinstance(bound_sha, str) or not SHA.fullmatch(bound_sha)):
        return unknown("ASOF_SHARE_REDUCTION_UPPER_BOUND_UNPROVEN")
    maximum_decrease = row.get("maximum_post_vintage_share_reduction")
    if (type(maximum_decrease) is not int or maximum_decrease < 0
            or maximum_decrease > shares):
        return unknown("INVALID_ASOF_SHARE_REDUCTION_BOUND")
    current_class_minimum = shares - maximum_decrease
    if current_class_minimum <= 0:
        return unknown("NO_POSITIVE_ASOF_CLASS_SHARE_LOWER_BOUND")
    met = Decimal(current_class_minimum) * close >= FLOOR
    return {"schema": SCHEMA, "asof_et": asof, "symbol": symbol,
            "status": ("SHADOW_CLASS_MC_LOWER_BOUND_GE_2B" if met
                       else "SHADOW_CLASS_MC_LOWER_BOUND_INSUFFICIENT"),
            "issuer_mc_floor_mathematically_met": met,
            "measurement_research_only": True, "can_create_PRIMARY": False,
            "can_create_R92": False, "execution": "NONE",
            "real_money": "NO-GO", "unknown_never_pass": True}


def selftest():
    """All checks run with python -O too (never rely on assert statements)."""
    row = {"asof_et": "2026-10-09", "symbol": "TEST", "cik": "0000000001",
           "outstanding_class_shares": 100000000, "sip_close_usd": "25.01",
           "shares_observation_date": "2026-09-30",
           "filing_accepted_utc": "2026-10-02T12:00:00Z",
           "alpaca_bar_utc": "2026-10-09T04:00:00Z",
           "source_rights_attested": True}
    row.update({key: "a"*64 for key in (
        "sec_filing_sha256", "sec_class_identity_sha256",
        "actions_interval_sha256", "alpaca_bar_sha256")})
    for key in ("class_shares_pit_verified", "sec_class_ticker_exact",
                "accepted_before_official_close", "actions_interval_exhaustive",
                "split_and_conversion_adjusted", "alpaca_same_session_sip_eod",
                "issuer_common_equity_class_verified",
                "not_adr_or_depositary_receipt"):
        row[key] = True
    row["max_share_reduction_asof_verified"] = True
    row["post_vintage_share_change_audit_sha256"] = "b"*64
    row["maximum_post_vintage_share_reduction"] = 0
    good = prove(row)
    if good["status"] != "SHADOW_CLASS_MC_LOWER_BOUND_GE_2B":
        raise AssertionError("POSITIVE_PROOF_MISSING")
    if good["can_create_PRIMARY"] or good["can_create_R92"]:
        raise AssertionError("FORBIDDEN_AUTHORITY")
    if "sip_close_usd" in good or "outstanding_class_shares" in good:
        raise AssertionError("RAW_DATA_LEAK")
    negative = (
        ("sip_close_usd", "19.99", "SHADOW_CLASS_MC_LOWER_BOUND_INSUFFICIENT"),
        ("max_share_reduction_asof_verified", False, "UNKNOWN_ASOF_SHARE_REDUCTION_UPPER_BOUND_UNPROVEN"),
        ("post_vintage_share_change_audit_sha256", "invalid", "UNKNOWN_ASOF_SHARE_REDUCTION_UPPER_BOUND_UNPROVEN"),
        ("maximum_post_vintage_share_reduction", None, "UNKNOWN_INVALID_ASOF_SHARE_REDUCTION_BOUND"),
        ("maximum_post_vintage_share_reduction", 90000000, "SHADOW_CLASS_MC_LOWER_BOUND_INSUFFICIENT"),
        ("maximum_post_vintage_share_reduction", 100000000, "UNKNOWN_NO_POSITIVE_ASOF_CLASS_SHARE_LOWER_BOUND"),
        ("class_shares_pit_verified", False, "UNKNOWN_ISSUER_CLASS_CA_OR_PIT_UNPROVEN"),
        ("actions_interval_exhaustive", False, "UNKNOWN_ISSUER_CLASS_CA_OR_PIT_UNPROVEN"),
        ("source_rights_attested", False, "UNKNOWN_PERSONAL_USAGE_RIGHTS_UNVERIFIED"),
        ("sec_class_identity_sha256", "invalid", "UNKNOWN_MISSING_EVIDENCE_DIGEST"),
        ("filing_accepted_utc", "2026-10-10T00:00:00Z", "UNKNOWN_LOOKAHEAD_OR_STALE_OR_WRONG_SESSION"),
        ("shares_observation_date", "2026-01-01", "UNKNOWN_LOOKAHEAD_OR_STALE_OR_WRONG_SESSION"),
        ("outstanding_class_shares", True, "UNKNOWN_SHARE_TYPE_INVALID"),
        ("sip_close_usd", "NaN", "UNKNOWN_NONPOSITIVE_OR_NONFINITE"),
        ("alpaca_bar_utc", "2026-10-10T04:00:00Z", "UNKNOWN_LOOKAHEAD_OR_STALE_OR_WRONG_SESSION"),
    )
    vintage_only = dict(row)
    del vintage_only["maximum_post_vintage_share_reduction"]
    if prove(vintage_only)["status"] != "UNKNOWN_INVALID_ASOF_SHARE_REDUCTION_BOUND":
        raise AssertionError("VINTAGE_ONLY_MUST_NOT_PASS")
    for field, bad, reason in negative:
        mutated = dict(row)
        mutated[field] = bad
        if prove(mutated)["status"] != reason:
            raise AssertionError("NEGATIVE_REGRESSION:" + field)
    print(json.dumps({"selftest": "PASS", "cases": 17,
                      "production_mc_created": 0, "R92_created": 0,
                      "version": SCHEMA}))


if __name__ == "__main__":
    selftest()
