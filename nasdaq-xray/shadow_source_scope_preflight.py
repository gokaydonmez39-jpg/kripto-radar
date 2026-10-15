#!/usr/bin/env python3
"""Fail-closed nonempty canonical PRICE scope preflight for shadow joins.

This validator establishes only that a current checked-out master/PRICE
snapshot has a nonempty, matching, internally consistent symbol set.
It NEVER attests PRIMARY price, SEC shares, MC, HISTORY, R92 or delivery.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify(master: dict, price: dict) -> dict:
    if not isinstance(master, dict) or not isinstance(price, dict):
        raise ValueError("INVALID_SOURCE_TYPE")
    for source in (master, price):
        if (source.get("execution") != "NONE"
                or source.get("real_money") != "NO-GO"
                or source.get("unknown_never_pass") is not True):
            raise ValueError("UNSAFE_SOURCE_CONTROL")
    asof = price.get("asof_et")
    if (not isinstance(asof, str) or len(asof) != 10
            or master.get("asof_et") != asof):
        raise ValueError("MISMATCHED_SOURCE_ASOF")
    try:
        dt.date.fromisoformat(asof)
    except ValueError as exc:
        raise ValueError("INVALID_SOURCE_DATE") from exc
    symbols = price.get("pass_symbols")
    count = price.get("pass_count")
    master_symbols = master.get("pass_symbols")
    if (not isinstance(symbols, list)
            or any(not isinstance(x, str) or not x for x in symbols)
            or type(count) is not int or count != len(symbols)
            or len(set(symbols)) != len(symbols)
            or not isinstance(master_symbols, list)
            or any(not isinstance(x, str) or not x for x in master_symbols)):
        raise ValueError("INVALID_PRICE_MASTER_SCOPE")
    if not symbols:
        raise ValueError("NO_CANONICAL_PRICE_PASS_SCOPE")
    if not set(symbols).issubset(set(master_symbols)):
        raise ValueError("PRICE_NOT_IN_MASTER_IDENTITY")
    return {
        "schema": "XRAY_SHADOW_SOURCE_SCOPE_PREFLIGHT_V1",
        "asof_et": asof,
        "price_pass_count": count,
        "snapshot_set_consistent": True,
        "primary_price_authority": False,
        "primary_mc_authority": False,
        "history_authority": False,
        "can_register_r92": False,
        "device_delivery_receipt_attested": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
    }


def selftest() -> None:
    master = {
        "asof_et": "2026-10-14",
        "pass_symbols": ["AAPL", "MSFT"],
        "execution": "NONE", "real_money": "NO-GO",
        "unknown_never_pass": True,
    }
    price = {
        "asof_et": "2026-10-14", "pass_symbols": ["AAPL"],
        "pass_count": 1, "execution": "NONE",
        "real_money": "NO-GO", "unknown_never_pass": True,
    }
    if verify(master, price)["price_pass_count"] != 1:
        raise AssertionError("ONE_PASS_VALID_SOURCE_REJECTED")
    both = copy.deepcopy(price)
    both["pass_symbols"] = ["AAPL", "MSFT"]
    both["pass_count"] = 2
    if verify(master, both)["price_pass_count"] != 2:
        raise AssertionError("TWO_PASS_VALID_SOURCE_REJECTED")
    negative = [
        (master, dict(price, pass_symbols=[], pass_count=0)),
        (master, dict(price, pass_symbols=[], pass_count=1)),
        (master, dict(price, asof_et="2026-10-13")),
        (master, dict(price, asof_et="2026-99-99")),
        (master, dict(price, pass_symbols=["AAPL", "AAPL"], pass_count=2)),
        (master, dict(price, pass_symbols=["FICTITIOUS"])),
        (master, dict(price, real_money="YES")),
        (master, dict(price, unknown_never_pass=False)),
        (dict(master, execution="AUTO"), price),
    ]
    for idx, (m, p) in enumerate(negative):
        try:
            verify(m, p)
        except ValueError:
            continue
        raise AssertionError("SHADOW_SOURCE_VETO_BYPASS_" + str(idx))
    print("XRAY_SHADOW_SCOPE_SELFTEST=PASS_2_POSITIVE_9_NEGATIVE_NO_ALPHA")


def live() -> None:
    try:
        master = json.loads((ROOT / "canonical_current_master_manifest.json").read_text())
        price = json.loads((ROOT / "canonical_current_price_dv30.json").read_text())
        result = verify(master, price)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("XRAY_SHADOW_SCOPE=BLOCKED:" + str(exc))
        raise SystemExit(2) from exc
    print("XRAY_SHADOW_SCOPE=PASS_SNAPSHOT_ONLY_ASOF_" + result["asof_et"])
    print("XRAY_SHADOW_SCOPE_PRICE_PASS_COUNT=" + str(result["price_pass_count"]))
    print("XRAY_SHADOW_SCOPE_ALPHA_AUTHORITY=false EXECUTION=NONE REAL_MONEY=NO-GO")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.selftest == args.live:
        parser.error("Specify exactly one of --selftest or --live")
    if args.selftest:
        selftest()
    else:
        live()
