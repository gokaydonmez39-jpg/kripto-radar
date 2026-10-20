#!/usr/bin/env python3
"""Condition-aware close-auction vs after-hours SIP sample validator.

This is a pure offline classification of a SMALL provided closing-window trade
sample. It never fetches market data, declares whole-day coverage, persists
vendor prices/volumes or upgrades C4.17 RTH DV30/MC/R92. Source:
https://docs.alpaca.markets/us/docs/market-data-faq (condition 6 vs T/M).
"""
from __future__ import annotations
import datetime as dt
import math
from alpaca_rth_minute_integrity_shadow import official_window,UTC

SCHEMA="XRAY_ALPACA_CLOSE_AUCTION_SALE_CONDITIONS_SHADOW_V1"
MAX_WINDOW_SECONDS=10
MAX_SAMPLE_TRADES=10000

def require(condition,name):
    if not condition:
        raise ValueError("XRAY_AUCTION_"+name)

def classify_one(row,symbol,close,*,max_seconds=MAX_WINDOW_SECONDS):
    require(type(row) is dict,"NOT_OBJECT")
    require(row.get("symbol")==symbol and type(symbol) is str,"SYMBOL_MISMATCH")
    require(row.get("tape")=="C","NOT_NASDAQ_TAPE_C")
    stamp=row.get("timestamp")
    require(type(stamp) is str,"TIMESTAMP_MISSING")
    try:
        time=dt.datetime.fromisoformat(stamp.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("XRAY_AUCTION_TIMESTAMP_UNPARSEABLE") from exc
    require(time.tzinfo is not None and time.utcoffset() is not None,
            "NAIVE_TIMESTAMP")
    moment=time.astimezone(UTC)
    require(close<=moment<close+dt.timedelta(seconds=max_seconds),
            "OUTSIDE_OFFICIAL_CLOSE_WINDOW")
    require(type(row.get("size")) is int and row["size"]>0,
            "INVALID_TRADE_SIZE")
    px=row.get("price")
    require(type(px) in (int,float) and math.isfinite(px) and px>0,
            "INVALID_PRICE")
    require(type(row.get("id")) is int and row["id"]>0,
            "INVALID_TRADE_ID")
    cond=row.get("conditions")
    require(type(cond) is list and cond and
            all(type(x) is str and x for x in cond),"INVALID_CONDITIONS")
    flags=set(cond)
    require(len(flags)==len(cond),"DUPLICATE_CONDITIONS")
    if "6" in flags:
        # SIP auction execution and its sale conditions must be distinguished
        # from extended-session Form T and non-volume official close marker M.
        require(row.get("exchange")=="Q","AUCTION_NOT_NASDAQ_EXCHANGE")
        require(not flags.intersection({"T","M","I","9","Q"}),
                "AUCTION_CONFLICTING_CONDITIONS")
        require(flags.issubset({"@","6","X","F"}),
                "AUCTION_UNRECOGNIZED_CONDITION")
        return "CLOSING_AUCTION_6"
    if "T" in flags:
        require("M" not in flags and "9" not in flags,
                "AFTER_HOURS_CONFLICT")
        require(flags.issubset({"@","T","I","F"}),
                "AFTER_HOURS_UNRECOGNIZED_CONDITION")
        return "EXTENDED_HOURS_T_EXCLUDE"
    if "M" in flags:
        require(flags.issubset({"@","M","I"}),
                "OFFICIAL_REFERENCE_UNRECOGNIZED_CONDITION")
        return "MARKET_CENTER_REFERENCE_M_EXCLUDE"
    # Do not infer RTH from clock-time alone or an ordinary after-close '@'.
    raise ValueError("XRAY_AUCTION_UNCLASSIFIED_SALE_CONDITION")

def classify_sample(symbol,asof,trades,*,window_seconds=4):
    start,close,minutes=official_window(asof)
    require(type(window_seconds) is int and
            1<=window_seconds<=MAX_WINDOW_SECONDS,"BAD_WINDOW")
    require(type(trades) is list and 0<len(trades)<=MAX_SAMPLE_TRADES,
            "EMPTY_OR_OVERSIZED_SAMPLE")
    seen=set()
    counts={"CLOSING_AUCTION_6":0,"EXTENDED_HOURS_T_EXCLUDE":0,
            "MARKET_CENTER_REFERENCE_M_EXCLUDE":0}
    sizes={key:0 for key in counts}
    for trade in trades:
        category=classify_one(trade,symbol,close,max_seconds=window_seconds)
        key=(trade["exchange"],trade["id"])
        require(key not in seen,"DUPLICATE_TRADE_ID")
        seen.add(key)
        counts[category]+=1
        sizes[category]+=trade["size"]
    require(sum(counts.values())==len(trades),"COUNT_PARTITION")
    require(sum(sizes.values())==sum(t["size"] for t in trades),"SIZE_PARTITION")
    return {"schema":SCHEMA,"symbol":symbol,"asof_et":asof,
            "close_time_utc":close.isoformat(),"official_session_minutes":minutes,
            "sample_window_seconds":window_seconds,
            "trade_records_inspected":len(trades),
            "condition_partition_counts":counts,
            "condition_partition_sizes_research_only":sizes,
            "sample_input_rows_classified":True,
            "sample_scope_complete":False,
            "provider_pagination_and_corrections_attested":False,
            "whole_day_trade_coverage_verified":False,
            "all_trade_corrections_verified":False,
            "close_auction_full_coverage_verified":False,
            "daily_rth_volume_verified":False,
            "c417_price_dv30_primary_pass":False,"primary_mc_created":False,
            "r92_created":False,"vendor_trade_prices_and_sizes_persisted":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
            "status":"SHADOW_CLOSE_CONDITION_SAMPLE_ONLY"}

def selftest():
    from copy import deepcopy
    _,close,minutes=official_window("2026-10-12")
    require(minutes==390,"REGULAR_390")
    def trade(sec,conditions,ident,exchange="Q",symbol="AAON",size=100):
        return {"symbol":symbol,"tape":"C","exchange":exchange,"id":ident,
                "timestamp":(close+dt.timedelta(seconds=sec)).isoformat(),
                "price":84.77,"size":size,"conditions":conditions}
    # Recreate only conditions/counts from observed 17-trade AAON witness.
    sample=[trade(0.597393,["@","6","X"],1)]
    sample += [trade(1.0+(i/100),["@","T","I"] if i<8 else ["@","T"],
                     i+2,exchange="D") for i in range(14)]
    sample += [trade(0.05,["@","M"],16),
               trade(0.06,["@","M"],17)]
    report=classify_sample("AAON","2026-10-12",sample)
    require(report["condition_partition_counts"]=={
      "CLOSING_AUCTION_6":1,"EXTENDED_HOURS_T_EXCLUDE":14,
      "MARKET_CENTER_REFERENCE_M_EXCLUDE":2},"SAMPLE_PARTITION")
    require(report["condition_partition_sizes_research_only"]=={
        "CLOSING_AUCTION_6":100,
        "EXTENDED_HOURS_T_EXCLUDE":1400,
        "MARKET_CENTER_REFERENCE_M_EXCLUDE":200},"SIZE_PARTITION")
    require(report["sample_scope_complete"] is False and
            report["sample_input_rows_classified"] is True and
            report["provider_pagination_and_corrections_attested"] is False,
            "NO_FALSE_SAMPLE_COMPLETENESS")
    require(report["daily_rth_volume_verified"] is False and
            report["r92_created"] is False,"NONAUTHORITY")
    _,early,early_minutes=official_window("2026-11-27")
    require(early_minutes==210 and early.astimezone(
            dt.timezone(dt.timedelta(hours=-5))).hour==13,
            "EARLY_CLOSE_CALENDAR")
    negatives=[
        ("AUCTION_T",lambda v:v[0].update(conditions=["@","6","T"])),
        ("AUCTION_M",lambda v:v[0].update(conditions=["@","6","M"])),
        ("AUCTION_WRONG_EXCHANGE",lambda v:v[0].update(exchange="D")),
        ("UNKNOWN_CODE",lambda v:v[0].update(conditions=["@","6","?"])),
        ("EXTENDED_M",lambda v:v[1].update(conditions=["@","T","M"])),
        ("NO_CLASS",lambda v:v[1].update(conditions=["@"])),
        ("WRONG_TAPE",lambda v:v[0].update(tape="A")),
        ("WRONG_SYMBOL",lambda v:v[0].update(symbol="NVDA")),
        ("VOLUME_FLOAT",lambda v:v[0].update(size=12.5)),
        ("PRICE_NAN",lambda v:v[0].update(price=float("nan"))),
        ("TRADE_DUPLICATE",lambda v:v[1].update(id=v[0]["id"],exchange=v[0]["exchange"])),
        ("TRADE_OUTSIDE_WINDOW",lambda v:v[0].update(
            timestamp=(close+dt.timedelta(seconds=5)).isoformat())),
        ("NAIVE_TIME",lambda v:v[0].update(timestamp="2026-10-12T16:00:00")),
    ]
    for code,mutate in negatives:
        candidate=deepcopy(sample);mutate(candidate)
        try:classify_sample("AAON","2026-10-12",candidate)
        except (ValueError,TypeError):pass
        else:raise RuntimeError("XRAY_AUCTION_FALSE_ACCEPT_"+code)
    for date in ("2026-07-03","2026-11-26","2026-12-25"):
        try:classify_sample("AAON",date,sample)
        except (ValueError,TypeError,IndexError):pass
        else:raise RuntimeError("XRAY_AUCTION_HOLIDAY_FALSE_ACCEPT")
    print("XRAY_AUCTION_CONDITION_SHADOW_SELFTEST=PASS_13_NEGATIVES_3_HOLIDAYS_390_210_NO_PRIMARY")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:p.error("Explicit --selftest only; no provider fetch or production entrypoint")
