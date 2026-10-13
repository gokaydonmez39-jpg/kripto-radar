#!/usr/bin/env python3
"""Evidence-only PERSONAL_RESEARCH technical checks; never C4.17 release authority.

Pure offline functions. No network, broker calls, fee bypass, secret use, or
raw provider data persistence. A technical outcome is NEVER canonical alpha.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections.abc import Mapping

SCHEMA = "XRAY_PERSONAL_TECHNICAL_EVIDENCE_V1"
NONPASS = "UNKNOWN_INCOMPLETE_OR_UNVERIFIED"
SAFETY = {"execution": "NONE", "real_money": "NO-GO",
          "r92_created": False, "canonical_primary_created": False,
          "unknown_never_pass": True}


def numeric(x):
    return type(x) in (float, int) and math.isfinite(x) and x > 0


def official_scope(asof, dates, n):
    try:
        assert isinstance(dates, list) and len(dates) == n
        assert dates == sorted(set(dates)) and dates[-1] == asof
        assert all(dt.date.fromisoformat(d).isoformat() == d for d in dates)
        return True
    except (AssertionError, TypeError, ValueError):
        return False


def daily_quality(bar, previous_close=None):
    """Classify raw daily evidence without fabricating volume or traded bars."""
    if not isinstance(bar, Mapping):
        return "UNKNOWN_MISSING_DAILY_BAR"
    try:
        values = [bar[k] for k in ("o", "h", "l", "c")]
        vol = bar["v"]
    except KeyError:
        return "UNKNOWN_MALFORMED_DAILY_BAR"
    if not all(numeric(x) for x in values):
        return "UNKNOWN_MALFORMED_PRICE"
    o, h, lo, c = values
    if lo > min(o, h, c) or h < max(o, lo, c):
        return "UNKNOWN_OHLC_ORDER"
    if type(vol) is not int:
        return "UNKNOWN_NONINTEGER_VOLUME"
    if vol < 0:
        return "UNKNOWN_NEGATIVE_VOLUME"
    if vol == 0:
        count = bar.get("n")
        vwap = bar.get("vw")
        carried = (numeric(previous_close) and all(x == previous_close for x in values))
        if count == 0 and vwap == 0 and carried:
            return "UNKNOWN_ZERO_VOLUME_CARRY_FORWARD_PLACEHOLDER"
        return "UNKNOWN_ZERO_VOLUME_NO_TRADE_PROVEN"
    return "OBSERVED_POSITIVE_RAW_BAR"


def assess_history(asof, expected260, bars_by_date, weekly52,
                   identity_pit_verified=False, corporate_actions_verified=False):
    if not official_scope(asof, expected260, 260):
        return "UNKNOWN_OFFICIAL_260_SCOPE"
    if not isinstance(weekly52, list) or len(weekly52) != 52 or \
       weekly52 != sorted(set(weekly52)) or not set(weekly52).issubset(expected260):
        return "UNKNOWN_OFFICIAL_52_SCOPE"
    if not isinstance(bars_by_date, Mapping):
        return NONPASS
    previous = None
    for date in expected260:
        bar = bars_by_date.get(date)
        if daily_quality(bar, previous) != "OBSERVED_POSITIVE_RAW_BAR":
            return "UNKNOWN_HISTORY_BAD_OR_MISSING_SESSION"
        previous = bar["c"]
    if identity_pit_verified and corporate_actions_verified:
        return "TECHNICAL_PRIMARY_PERSONAL_HISTORY_NOT_RELEASE"
    return "SHADOW_260_52_OBSERVED_NOT_PRIMARY"


def assess_price_dv30(asof, expected30, daily_by_date,
                      official_close_verified, rth_volume_verified,
                      correction_lineage_verified, identity_pit_verified):
    if not official_scope(asof, expected30, 30):
        return {"status": "UNKNOWN_OFFICIAL_30_SCOPE"}
    if not isinstance(daily_by_date, Mapping) or not all(
            isinstance(x, Mapping) for x in (official_close_verified, rth_volume_verified)):
        return {"status": NONPASS}
    vals = []
    prev = None
    for d in expected30:
        b = daily_by_date.get(d)
        if daily_quality(b, prev) != "OBSERVED_POSITIVE_RAW_BAR":
            return {"status": "UNKNOWN_DV30_BAD_OR_MISSING_SESSION", "date": d}
        if not (official_close_verified.get(d) is True and
                rth_volume_verified.get(d) is True and
                type(b.get("rth_v")) is int and b["rth_v"] > 0):
            return {"status": "UNKNOWN_RTH_SETTLEMENT_OR_VOLUME", "date": d}
        vals.append(b["c"] * b["rth_v"])
        prev = b["c"]
    if not (correction_lineage_verified and identity_pit_verified):
        return {"status": "SHADOW_EXACT30_UNRECONCILED_NOT_PRIMARY"}
    # Exactly thirty dollar-volume observations; zero-indexed median positions 14, 15.
    vals.sort()
    dv = (vals[14] + vals[15]) / 2.0
    return {"status": "TECHNICAL_PRIMARY_PERSONAL_PRICE_DV30_NOT_RELEASE",
            "dv30_usd": dv,
            "price_gate": "PASS" if daily_by_date[asof]["c"] >= 5 else "FAIL",
            "dv30_gate": "PASS" if dv >= 50_000_000 else "FAIL",
            "sessions": 30}


def assess_sec_pit_mc(asof, issuer, exact_close_usd):
    """Only class-aware, PIT-dated SEC shares can support a technical MC label."""
    if not isinstance(issuer, Mapping) or not numeric(exact_close_usd):
        return {"status": NONPASS}
    try:
        cik = issuer["cik"]
        shares = issuer["shares_outstanding"]
        accepted_date = issuer["filing_accepted_date"]
        security_class = issuer["security_class"]
    except KeyError:
        return {"status": "UNKNOWN_SEC_REQUIRED_FIELD"}
    if not (isinstance(cik, str) and len(cik) == 10 and cik.isdigit() and
            isinstance(security_class, str) and bool(security_class.strip()) and
            type(shares) is int and shares > 0):
        return {"status": "UNKNOWN_SEC_IDENTITY_OR_SHARES"}
    try:
        if dt.date.fromisoformat(accepted_date) > dt.date.fromisoformat(asof):
            return {"status": "UNKNOWN_SEC_LOOKAHEAD"}
    except (ValueError, TypeError):
        return {"status": "UNKNOWN_SEC_DATE"}
    required = ("cik_class_exact", "pit_shares_verified", "split_adjustment_verified",
                "other_share_classes_reconciled", "sec_primary_source_verified",
                "price_security_class_matched")
    if not all(issuer.get(x) is True for x in required):
        return {"status": "UNKNOWN_SEC_PIT_CLASS_OR_CORPORATE_ACTION"}
    market_cap = shares * exact_close_usd
    return {"status": "TECHNICAL_PRIMARY_PERSONAL_MC_NOT_RELEASE",
            "mc_usd": market_cap,
            "mc_gate": "PASS" if market_cap >= 2_000_000_000 else "FAIL"}


def selftest():
    def ck(x, code):
        if not x:
            raise AssertionError("XRAY_PERSONAL_ENGINE_" + code)
    z = {"o": 10, "h": 10, "l": 10, "c": 10,
         "v": 0, "n": 0, "vw": 0}
    ck(daily_quality(z, 10) == "UNKNOWN_ZERO_VOLUME_CARRY_FORWARD_PLACEHOLDER",
       "CARRY_FORWARD")
    ck(daily_quality(z, None) == "UNKNOWN_ZERO_VOLUME_NO_TRADE_PROVEN",
       "ZERO_NO_EVIDENCE")
    ck(daily_quality(dict(z, v=-1), 10) == "UNKNOWN_NEGATIVE_VOLUME",
       "NEGATIVE")
    ck(daily_quality(dict(z, v=True), 10) == "UNKNOWN_NONINTEGER_VOLUME",
       "BOOLEAN")
    ck(daily_quality(dict(z, v=100), 10) == "OBSERVED_POSITIVE_RAW_BAR",
       "POSITIVE")
    dates = [(dt.date(2026, 9, 1) + dt.timedelta(days=i)).isoformat()
             for i in range(30)]
    b = {d: {"o": 100, "h": 101, "l": 99, "c": 100,
             "v": 500_000, "rth_v": 500_000} for d in dates}
    true = {d: True for d in dates}
    no = assess_price_dv30(dates[-1], dates, b, true, true, False, True)
    ck(no["status"].startswith("SHADOW_"), "NO_CORRECTION_NO_PRIMARY")
    yes = assess_price_dv30(dates[-1], dates, b, true, true, True, True)
    ck(yes["sessions"] == 30 and yes["dv30_usd"] == 50_000_000 and
       yes["dv30_gate"] == "PASS", "EXACT_30_MEDIAN_BOUNDARY")
    ck(assess_price_dv30(dates[-1], dates, b, {}, true, True, True)["status"] ==
       "UNKNOWN_RTH_SETTLEMENT_OR_VOLUME", "NO_SETTLEMENT_FALSE_PASS")
    missing = dict(b)
    missing.pop(dates[9])
    ck(assess_price_dv30(dates[-1], dates, missing, true, true, True, True)["status"] ==
       "UNKNOWN_DV30_BAD_OR_MISSING_SESSION", "NO_SYNTHETIC_BAR")
    sec = {"cik": "0002079013", "shares_outstanding": 100_000_000,
           "security_class": "Class A", "filing_accepted_date": "2026-10-12"}
    ck(assess_sec_pit_mc("2026-10-13", sec, 20)["status"].startswith("UNKNOWN"),
       "SEC_CLASS_GUARD")
    sec.update({s: True for s in
                ("cik_class_exact", "pit_shares_verified",
                 "split_adjustment_verified", "other_share_classes_reconciled",
                 "sec_primary_source_verified", "price_security_class_matched")})
    ck(assess_sec_pit_mc("2026-10-13", sec, 20)["mc_usd"] == 2_000_000_000,
       "SEC_MC_GATE")
    sec["filing_accepted_date"] = "2026-10-14"
    ck(assess_sec_pit_mc("2026-10-13", sec, 20)["status"] ==
       "UNKNOWN_SEC_LOOKAHEAD", "PIT_LOOKAHEAD")
    ck(SAFETY["r92_created"] is False and
       SAFETY["canonical_primary_created"] is False, "NO_ALPHA")
    print(json.dumps({"schema": SCHEMA, "result": "OFFLINE_SELFTEST_PASS",
                      "negative_and_boundary_tests": 13, **SAFETY},
                     sort_keys=True))


def audit_frozen_metadata(root):
    """Validate all frozen metadata partitions; never synthesize missing OHLCV."""
    from pathlib import Path
    p = Path(root) / "nasdaq-xray" / "research"
    history = json.loads((p / "personal_root260_full3185_20261013_verified_v1.json").read_text())
    price = json.loads((p / "personal_price540_full_bounded_20261012_verified_v1.json").read_text())
    joint = json.loads((p / "personal_joint_price540_root260_cross_asof_diagnostic_20261014_v1.json").read_text())
    hc = history.get("statuses", {})
    pc = price.get("counts", {})
    ok = (
        history.get("scope_count") == history.get("source_count_classified") == 3185 and
        history.get("positive_shadow_count") == 2679 and
        history.get("unresolved_count") == 506 and
        sum(hc.values()) == 3185 and
        hc.get("UNKNOWN_BAD_OHLCV") == 338 and
        hc.get("UNKNOWN_260_CONSECUTIVE_OFFICIAL_DATES_INCOMPLETE") == 168 and
        history.get("canonical_history_updated") is False and
        price.get("scope_symbols") == price.get("classified_symbols") == 540 and
        sum(pc.values()) == 540 and
        pc.get("LOWER_BOUND_GE_50M_SHADOW", 0) +
        pc.get("PRIOR_VERIFIED_LOWER_BOUND_GE_50M_SHADOW", 0) == 419 and
        pc.get("AMBIGUOUS_BETWEEN_BOUNDS_SHADOW") == 91 and
        pc.get("UNKNOWN_INCOMPLETE_OR_INTEGRITY_SHADOW") == 30 and
        price.get("canonical_price_dv30_written") is False and
        history.get("report_asof_et") == "2026-10-13" and
        price.get("research_asof_et") == "2026-10-12" and
        joint.get("same_asof_proven") is False and
        joint.get("joined_price_scope") == 540 and
        joint.get("price_scope_missing_in_root") == 0 and
        joint.get("price_positive_lower_bound_count") == 419 and
        joint.get("price_positive_and_other_day_history_complete") == 404 and
        joint.get("price_positive_but_other_day_history_incomplete") == 15 and
        joint.get("price_ambiguous_history_observed_other_day") == 89 and
        joint.get("price_ambiguous_history_missing_other_day") == 2 and
        joint.get("price_unknown_integrity_and_root_zerovolume") == 27
    )
    if not ok:
        raise ValueError("XRAY_PERSONAL_FROZEN_METADATA_PARTITION_DRIFT")
    report = {
        "schema": "XRAY_PERSONAL_FROZEN_COHORT_READBACK_V1",
        "history_asof_et": "2026-10-13",
        "price_asof_et": "2026-10-12",
        "history_classified": 3185,
        "history_observed_positive_shadow": 2679,
        "history_placeholder_or_bad_ohlcv_unknown": 338,
        "history_missing_official_dates_unknown": 168,
        "price_classified": 540,
        "price_rth_lower_bound_shadow": 419,
        "price_ambiguous": 91,
        "price_incomplete_integrity": 30,
        "cross_asof_price_with_other_day_history_observed": 404,
        "same_asof_primary_chain": False,
        "valid_all_symbol_primary_mc": False,
        "technical_primary_claimed": False,
        "result": "FROZEN_RESEARCH_COUNTS_PASS_RELEASE_NOT_READY",
        **SAFETY,
    }
    print(json.dumps(report, sort_keys=True))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--audit-frozen", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.audit_frozen:
        from pathlib import Path
        audit_frozen_metadata(Path(__file__).resolve().parent.parent)
    else:
        ap.error("run --selftest or --audit-frozen; no provider side effects")
