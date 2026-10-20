#!/usr/bin/env python3
"""Pure offline Alpaca SIP/Longbridge guard; synthetic inputs, no vendor data.

The inclusive daily end can include a later bar. The 16:00 ET minute can
contain auction 6, extended-hours T, official-close reference M. Never promote
this research into PRIMARY, C4.17 DV30, MC, R92 or notification.
Sources: Alpaca Market Data FAQ and Longbridge Historical Candlesticks docs.
"""
import argparse
import copy
import datetime as dt
import json
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
SCHEMA = "XRAY_SIP_1600_AND_QUOTA_SHADOW_V1"

def need(ok, reason):
    if not ok:
        raise ValueError("XRAY_SIP_1600_" + reason)

def instant(value):
    need(type(value) is str, "STAMP_TYPE")
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("XRAY_SIP_1600_STAMP_PARSE") from exc
    need(stamp.tzinfo is not None and stamp.utcoffset() is not None, "NAIVE_TIME")
    return stamp.astimezone(UTC)

def daily_scope(bars, expected):
    need(type(bars) is list and type(expected) is list and
         0 < len(expected) <= 30 and
         all(type(d) is str and dt.date.fromisoformat(d).isoformat() == d for d in expected)
         and sorted(set(expected)) == expected, "EXPECTED_DAILY_SCOPE")
    days = []
    for row in bars:
        need(type(row) is dict, "DAILY_ROW")
        when = instant(row.get("timestamp")).astimezone(NY)
        need(when.time() == dt.time(0), "NOT_ET_MIDNIGHT")
        days.append(when.date().isoformat())
    need(days == expected, "DAILY_EXTRA_MISSING_OR_DUPLICATE_ASOF")
    return {"exact_asof_days": len(days), "rth_volume_proven": False,
            "primary_price_pass": False, "r92_created": False}

def close_minute(asof, bar_volume, rows):
    need(type(asof) is str and dt.date.fromisoformat(asof).isoformat() == asof,
         "BAD_ASOF")
    close = dt.datetime.combine(dt.date.fromisoformat(asof),
                                dt.time(16), NY).astimezone(UTC)
    need(type(bar_volume) is int and bar_volume >= 0, "BAR_VOLUME")
    need(type(rows) is list and 0 < len(rows) <= 10000, "ROWS")
    sums = {"SIX": 0, "T": 0, "M_REFERENCE": 0, "OTHER_AFTER_CLOSE": 0}
    counts = {key: 0 for key in sums}
    seen = set()
    for row in rows:
        need(type(row) is dict, "ROW_TYPE")
        stamp = instant(row.get("timestamp"))
        need(close <= stamp < close + dt.timedelta(minutes=1), "OUTSIDE_1600")
        size, ident, exchange = row.get("size"), row.get("id"), row.get("exchange")
        need(type(size) is int and 0 < size < 10**12, "TRADE_SIZE")
        need(type(ident) is int and ident > 0 and
             type(exchange) is str and bool(exchange), "TRADE_ID")
        need((exchange, ident) not in seen, "TRADE_DUPLICATE")
        seen.add((exchange, ident))
        flags = row.get("conditions")
        need(type(flags) is list and bool(flags)
             and all(type(c) is str and c in {"@", "6", "T", "M", "I", "F", "X"} for c in flags)
             and len(set(flags)) == len(flags), "UNRECOGNIZED_CONDITIONS")
        flags = set(flags)
        if "6" in flags:
            need(exchange == "Q" and flags.issubset({"@", "6", "X", "F"}),
                 "AUCTION_MIXED_OR_NOT_NASDAQ")
            kind = "SIX"
        elif "M" in flags:
            need(flags.issubset({"@", "M", "I"}), "REFERENCE_M_MIXED")
            kind = "M_REFERENCE"
        elif "T" in flags:
            need(flags.issubset({"@", "T", "I", "F"}), "EXTENDED_T_MIXED")
            kind = "T"
        else:
            need("@" in flags and flags.issubset({"@", "I", "F", "X"}),
                 "UNCLASSIFIED_AFTER_CLOSE")
            kind = "OTHER_AFTER_CLOSE"
        sums[kind] += size
        counts[kind] += 1
    counted = sum(value for key, value in sums.items() if key != "M_REFERENCE")
    need(counted == bar_volume, "VENDOR_MINUTE_SUM_MISMATCH")
    return {
        "status": "SAMPLE_RECONCILED_NO_RTH_AUTHORITY",
        "counts": counts, "excluded_M_reference": sums["M_REFERENCE"] > 0,
        "sample_sum_matches_minute": True,
        "pagination_complete_verified": False,
        "rth_only_volume_verified": False,
        "daily_sip_volume_is_rth": False,
        "primary_pass": False, "r92_created": False,
        "notification_sent": False,
    }

def longbridge_result(reply):
    r = reply if type(reply) is dict else {}
    msg = r.get("message")
    blocked = r.get("error_code") == 301607 and type(msg) is str and (
        "requested:0/limit:0" in msg)
    return {"status": ("BLOCKED_HISTORICAL_QUOTA_0" if blocked else
                       "UNKNOWN_UNATTESTED_ENTITLEMENT"),
            "can_retry_by_smaller_symbol_batch": False if blocked else None,
            "missing_is_zero_volume": False, "history_pass": False,
            "primary_pass": False, "r92_created": False}

def selftest():
    date = "2026-10-19"
    bars = [{"timestamp": "2026-10-19T04:00:00Z"}]
    need(not daily_scope(bars, [date])["rth_volume_proven"], "DAILY_FALSE_AUTHORITY")
    def t(ident, code, size, exchange="Q", when="2026-10-19T20:00:00.100Z"):
        return {"id": ident, "conditions": code, "size": size,
                "exchange": exchange, "timestamp": when}
    rows = [t(1, ["@", "6", "X"], 100),
            t(2, ["@", "T"], 20, "D"),
            t(3, ["@", "M"], 101),
            t(4, ["@", "I"], 5, "D")]
    good = close_minute(date, 125, rows)
    need(good["counts"] == {"SIX": 1, "T": 1, "M_REFERENCE": 1,
                            "OTHER_AFTER_CLOSE": 1} and
         good["excluded_M_reference"] and
         not good["rth_only_volume_verified"], "M_REFERENCE_DOUBLE_COUNT")
    blocked = longbridge_result({"error_code": 301607,
        "message": "history candlestick symbol count out of limit, requested:0/limit:0"})
    need(blocked["status"] == "BLOCKED_HISTORICAL_QUOTA_0" and
         blocked["can_retry_by_smaller_symbol_batch"] is False and
         not blocked["missing_is_zero_volume"], "QUOTA0_ERROR_ZERO_CANDLE")
    need(longbridge_result({})["status"] == "UNKNOWN_UNATTESTED_ENTITLEMENT",
         "NO_ERROR_NOT_RIGHTS")
    negatives = [
      ("future_day", lambda: daily_scope(bars + [{"timestamp": "2026-10-20T04:00:00Z"}], [date])),
      ("duplicate_day", lambda: daily_scope(bars + bars, [date])),
      ("missing_day", lambda: daily_scope([], [date])),
      ("naive", lambda: daily_scope([{"timestamp": "2026-10-19T00:00:00"}], [date])),
      ("wrong_et_midnight", lambda: daily_scope([{"timestamp": "2026-10-19T00:00:00Z"}], [date])),
      ("wrong_close_sum", lambda: close_minute(date, 126, rows)),
      ("auction_T", lambda: close_minute(date, 125, [dict(rows[0], conditions=["@", "6", "T"]), *rows[1:]])),
      ("auction_M", lambda: close_minute(date, 125, [dict(rows[0], conditions=["@", "6", "M"]), *rows[1:]])),
      ("auction_wrong_exchange", lambda: close_minute(date, 125, [dict(rows[0], exchange="P"), *rows[1:]])),
      ("duplicate_trade", lambda: close_minute(date, 125, [rows[0], dict(rows[0]), *rows[2:]])),
      ("unknown_code", lambda: close_minute(date, 125, [dict(rows[0], conditions=["@", "6", "?"]), *rows[1:]])),
      ("outside_minute", lambda: close_minute(date, 125, [dict(rows[0], timestamp="2026-10-19T20:01:00Z"), *rows[1:]])),
      ("bool_volume", lambda: close_minute(date, 125, [dict(rows[0], size=True), *rows[1:]])),
      ("T_M_mixed", lambda: close_minute(date, 125, [rows[0], dict(rows[1], conditions=["@", "T", "M"]), *rows[2:]])),
    ]
    for label, action in negatives:
        try:
            action()
        except ValueError:
            continue
        raise RuntimeError("XRAY_SIP_1600_FALSE_ACCEPT_" + label)
    need(len(negatives) == 14, "NEGATIVE_COUNT")
    print(json.dumps({"schema": SCHEMA,
          "status": "PASS_14_NEGATIVES_4_CONTROLS_NO_PRIMARY_NO_R92",
          "vendor_calls": 0, "execution": "NONE", "real_money": "NO-GO",
          "primary_pass": False, "r92_created": False,
          "notification_sent": False}, sort_keys=True))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    need(args.selftest, "SYNTHETIC_SELFTEST_ONLY")
    selftest()
