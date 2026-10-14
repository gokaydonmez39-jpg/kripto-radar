#!/usr/bin/env python3
"""Independent exact-30-day daily SIP PRICE/DV proxy for personal research.

Uses the same in-memory historical SIP 1Day rows already fetched for 260/52.
Measures only source daily bars, NOT official 09:30–16:00 RTH DV30. The daily
SIP bar may contain extended sessions/closing auction; raw history may span a
corporate action. All outputs are categorical labels, never vendor prices.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal
import math

from alpaca_free_sip_shadow_guard import timestamp_date

SCHEMA = "XRAY_FULL_UNIVERSE_30DAY_SIP_DAILY_PROXY_NO_RTH_AUTHORITY_V1"
VALID = "SHADOW_DAILY_30_OBSERVED_PRICE_GE5_DV_PROXY_GE50M_NOT_RTH"
LOW_PRICE = "SHADOW_DAILY_30_OBSERVED_CURRENT_PRICE_LT5_NOT_RTH"
LOW_DV = "SHADOW_DAILY_30_OBSERVED_DV_PROXY_LT50M_NOT_RTH"
UNKNOWN_RECENT_ZERO = "UNKNOWN_DAILY30_ZERO_OR_NEGATIVE_VOLUME"
UNKNOWN_RECENT_BAD = "UNKNOWN_DAILY30_BAD_OHLCV"
UNKNOWN_CURRENT = "UNKNOWN_DAILY30_ASOF_MISSING"
UNKNOWN_PRIOR = "UNKNOWN_DAILY30_PRIOR_SESSION_MISSING"
UNKNOWN_SOURCE = "UNKNOWN_DAILY30_NO_VALID_SOURCE"
UNKNOWN_TIMESTAMP = "UNKNOWN_DAILY30_TIMESTAMP_DUPLICATE_OR_NOT_OFFICIAL"
UNKNOWN_PROVIDER = "UNKNOWN_DAILY30_PROVIDER_TRANSPORT"
FLOOR = Decimal("50000000")
PRICE = Decimal("5")


def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_SIP_DAILY30_PROXY_" + reason)


def classify(rows, official260):
    """Return one fail-closed source label; no numeric OHLCV leaves caller."""
    need(type(official260) is list and len(official260) == 260 and
         official260 == sorted(set(official260)), "CALENDAR")
    if type(rows) is not list:
        return UNKNOWN_SOURCE
    required = official260[-30:]
    desired = set(required)
    official = set(official260)
    by_day = {}
    for row in rows:
        if type(row) is not dict:
            return UNKNOWN_TIMESTAMP
        try:
            day = timestamp_date(row["t"]).isoformat()
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            return UNKNOWN_TIMESTAMP
        if day not in official or day in by_day:
            return UNKNOWN_TIMESTAMP
        by_day[day] = row
    if required[-1] not in by_day:
        return UNKNOWN_CURRENT
    if not desired.issubset(by_day):
        return UNKNOWN_PRIOR
    recent = [by_day[d] for d in required]
    dollar = []
    for row in recent:
        try:
            o,h,l,c,v = (row[k] for k in ("o", "h", "l", "c", "v"))
        except KeyError:
            return UNKNOWN_RECENT_BAD
        if any(type(x) not in (int,float) or not math.isfinite(x)
               for x in (o,h,l,c,v)):
            return UNKNOWN_RECENT_BAD
        if v <= 0:
            return UNKNOWN_RECENT_ZERO
        if min(o,h,l,c) <= 0 or h < max(o,l,c) or l > min(o,c):
            return UNKNOWN_RECENT_BAD
        dollar.append(Decimal(str(c))*Decimal(str(v)))
    if Decimal(str(recent[-1]["c"])) < PRICE:
        return LOW_PRICE
    ordered = sorted(dollar)
    med = (ordered[14] + ordered[15])/Decimal(2)
    return VALID if med >= FLOOR else LOW_DV


def summarize(labels, history_labels, causes):
    need(set(labels) == set(history_labels) == set(causes) and
         all(type(x) is str for x in labels.values()), "FULL_PARTITION")
    counts = dict(sorted(Counter(labels.values()).items()))
    confirmed = sum(x in {VALID,LOW_PRICE,LOW_DV} for x in labels.values())
    names = [s for s in labels
             if causes[s] == "ZERO_OR_NEGATIVE_RECORDED_VOLUME"]
    # This is a temporal SOURCE diagnostic, not a 260 pass.
    old_zero = sum(labels[s] in {VALID,LOW_PRICE,LOW_DV} for s in names)
    recent_zero = sum(labels[s] == UNKNOWN_RECENT_ZERO for s in names)
    need(old_zero + recent_zero <= len(names), "ZERO_CROSS_PARTITION")
    observed260 = "SHADOW_260_DAILY_52_WEEK_OBSERVED"
    need(all(labels[s] in {VALID,LOW_PRICE,LOW_DV}
             for s in labels if history_labels[s] == observed260),
         "260_COMPLETE_BUT_30DAY_DAILY_MISSING")
    return {
        "schema": SCHEMA,
        "session_count": 30,
        "scope_count": len(labels),
        "source_daily_30_valid_price_volume_count": confirmed,
        "hist_260_zero_volume_symbols": len(names),
        "hist_260_zero_volume_outside_last30": old_zero,
        "hist_260_zero_volume_within_last30": recent_zero,
        "hist_260_zero_volume_other_30day_unknown": len(names)-old_zero-recent_zero,
        "classification_counts": counts,
        "symbol_classifications": dict(sorted(labels.items())),
        "research_daily_proxy_not_official_rth_dv30": True,
        "daily_close_not_canonical_price": True,
        "corporate_action_adjustment_and_issuer_identity_unproven": True,
        "no_vendor_ohlcv_persisted": True,
        "canonical_price_history_mc_untouched": True,
        "registered_R92_count": 0,
        "execution": "NONE", "real_money": "NO-GO"
    }


def selftest():
    # Only fictitious data; official-like mock session labels.
    import datetime as dt
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    first = dt.date(2025, 1, 1)
    days = [(first+dt.timedelta(days=i)).isoformat() for i in range(260)]
    def bar(day, vol=6000000, close=10):
        stamp = dt.datetime.combine(dt.date.fromisoformat(day),
                 dt.time(), tzinfo=ny).astimezone(dt.timezone.utc)
        return {"t":stamp.isoformat(), "o":close, "h":close+1,
                "l":close-1, "c":close, "v":vol}
    valid = [bar(d) for d in days]
    need(classify(valid,days) == VALID, "HIGH_DV_SOURCE_ONLY")
    need(classify(valid[:-1],days) == UNKNOWN_CURRENT, "NO_ASOF_FALSE_PASS")
    need(classify(valid[:240]+valid[241:],days) == UNKNOWN_PRIOR,
         "MISSING_RECENT_NOT_OLD")
    prior_zero = [dict(valid[0],v=0)] + valid[1:]
    need(classify(prior_zero,days) == VALID, "OLD_ZERO_DOES_NOT_POISON_30")
    recent_zero = valid[:-1]+[dict(valid[-1],v=0)]
    need(classify(recent_zero,days)==UNKNOWN_RECENT_ZERO,"RECENT_ZERO_NEVER_PASS")
    need(classify([dict(valid[0],t="broken")]+valid[1:],days) ==
         UNKNOWN_TIMESTAMP,"BAD_TIMESTAMP_FAIL_CLOSED")
    need(classify(valid+[valid[-1]],days)==UNKNOWN_TIMESTAMP,
         "DUPLICATE_NO_VOLUME_DOUBLE_COUNT")
    need(classify([bar(d,vol=100) for d in days],days)==LOW_DV,
         "LOW_DV")
    need(classify([bar(d,close=4) for d in days],days)==LOW_PRICE,
         "LOW_PRICE")
    need(classify([dict(valid[0],c=400)]+valid[1:],days)==VALID,
         "OLD_BAD_GEOMETRY_REQUIRES_HISTORY_GATE_NOT_RECENT")
    need(classify([dict(valid[0],v=True)]+valid[1:],days)==VALID,
         "OLD_BAD_FIELDS_NEVER_COUNT_IN_RECENT_DV")
    h = {"AAA":"SHADOW_260_DAILY_52_WEEK_OBSERVED",
         "BBB":"INVALID_OHLCV_OR_ZERO_VOLUME",
         "CCC":"INVALID_OHLCV_OR_ZERO_VOLUME"}
    c = {"AAA":"260_52_OBSERVED_RESEARCH_ONLY",
         "BBB":"ZERO_OR_NEGATIVE_RECORDED_VOLUME",
         "CCC":"ZERO_OR_NEGATIVE_RECORDED_VOLUME"}
    out = summarize({"AAA":VALID,"BBB":VALID,"CCC":UNKNOWN_RECENT_ZERO},h,c)
    need(out["hist_260_zero_volume_outside_last30"]==1 and
         out["hist_260_zero_volume_within_last30"]==1,
         "CROSS_CAUSAL_COUNTS")
    try:
        summarize({"AAA":UNKNOWN_CURRENT,"BBB":VALID,"CCC":UNKNOWN_RECENT_ZERO},
                  h,c)
    except ValueError as exc:
        need("260_COMPLETE_BUT_30DAY" in str(exc),"CROSS_FAIL_REASON")
    else:
        raise AssertionError("CONTRADICTORY_260_AND_DAILY30_ACCEPTED")
    print("XRAY_SIP_DAILY30_PROXY_SELFTEST=PASS_CAUSAL_260_DAILY30_NEGATIVES_NO_RTH_NO_ALPHA")


if __name__ == "__main__":
    selftest()
