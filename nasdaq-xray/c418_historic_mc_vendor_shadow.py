#!/usr/bin/env python3
"""Finnhub/EODHD historical MC response validators — C4.18 research only.

Does not use APIs or secrets, does not infer PIT from an observation date,
does not copy vendor data into git, and NEVER grants C4.17 PRIMARY or R92.
Input is a transient caller-provided API response. Upstream origin and legal
entitlement must be separately independently attested before any future policy.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import math

SCHEMA = "XRAY_C418_HISTORIC_MC_VENDOR_SHADOW_V1"
VENDORS = {"FINNHUB": "FINNHUB_STOCK_HISTORICAL_MARKET_CAP",
           "EODHD": "EODHD_HISTORICAL_MARKET_CAP_WEEKLY"}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("C418_MC_VENDOR_FAIL_CLOSED:" + reason)


def date(value: object, reason: str) -> str:
    require(isinstance(value, str), reason)
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError("C418_MC_VENDOR_FAIL_CLOSED:" + reason) from None
    # Never rely on assert in input validation: python -O erases assertions.
    require(parsed.isoformat() == value, reason)
    return value


def number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def evaluate(vendor: str, symbol: str, asof: str, payload: object) -> dict:
    require(vendor in VENDORS, "UNKNOWN_VENDOR")
    require(isinstance(symbol, str) and symbol.strip() == symbol and symbol, "BAD_TICKER")
    asof = date(asof, "INVALID_ASOF")
    require(isinstance(payload, dict), "NOT_OBJECT")
    if vendor == "FINNHUB":
        require(payload.get("symbol") == symbol, "FINNHUB_SYMBOL_MISMATCH")
        require(payload.get("currency") == "USD", "FINNHUB_CURRENCY_UNPROVEN")
        raw = payload.get("data")
        require(isinstance(raw, list), "FINNHUB_ROWS_INVALID")
        dkey, mkey = "atDate", "marketCapitalization"
    else:
        # Documented EODHD returns indexed JSON keys 0,1,2 etc; a "date"
        # label is NOT a publication timestamp and observations are weekly.
        require(all(isinstance(k, str) and k.isdigit() for k in payload), "EODHD_INDEX_INVALID")
        indices = [int(k) for k in payload]
        require(sorted(indices) == list(range(len(indices))), "EODHD_INDEX_DISCONTIGUOUS")
        raw = [payload[str(i)] for i in sorted(indices)]
        dkey, mkey = "date", "value"
    require(len(raw) <= 5000, "EXCESSIVE_RESPONSE_ROWS")
    seen = set()
    exact = 0
    dated = 0
    for row in raw:
        require(isinstance(row, dict), "ROW_NOT_OBJECT")
        row_date = date(row.get(dkey), "ROW_DATE_BAD")
        require(row_date not in seen, "DUPLICATE_DAY_OR_CONFLICT")
        seen.add(row_date)
        require(number(row.get(mkey)), "INVALID_MARKET_CAP")
        # Future rows are never usable in a same-ASOF record.
        require(row_date <= asof, "FUTURE_DATA_INCLUDED")
        dated += 1
        if row_date == asof:
            exact += 1
    reasons = ["VENDOR_RIGHTS_AND_NONDISPLAY_UNVERIFIED",
               "OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP",
               "INDEPENDENT_UPSTREAM_NOT_ATTESTED",
               "HISTORICAL_SEC_ACCEPTANCE_PIT_NOT_PROVEN"]
    if exact != 1:
        reasons.append("EXACT_ASOF_MC_NOT_RETURNED")
    if vendor == "EODHD":
        reasons.append("WEEKLY_MC_NOT_DAILY_ASOF_AUTHORITY")
    return {
        "schema": SCHEMA, "provider": vendor, "source_root": VENDORS[vendor],
        "asof_et": asof, "requested_exact_symbol": symbol,
        "rows_validated": dated, "exact_asof_row_count": exact,
        "status": "SHADOW_ROW_FOUND_NONPIT" if exact == 1 else "SHADOW_NO_EXACT_ASOF_ROW",
        "reasons": reasons, "source_timestamp_attested": False,
        "source_legal_automated_rights_attested": False,
        "upstream_lineage_independence_attested": False,
        "source_PIT_attested": False,
        "can_create_PRIMARY": False, "can_register_R92": False,
        "can_enable_G9": False, "production_go": False,
        "vendor_market_caps_persisted": False,
        "execution": "NONE", "real_money": "NO-GO", "unknown_never_pass": True
    }


def selftest() -> None:
    a = {"symbol":"AAPL","currency":"USD",
         "data":[{"atDate":"2026-10-09","marketCapitalization":3000000000000.0}]}
    b = {"0":{"date":"2026-10-09","value":3000000000000}}
    for name, data in (("FINNHUB",a), ("EODHD",b)):
        result = evaluate(name,"AAPL","2026-10-09",data)
        require(result["exact_asof_row_count"] == 1, "POSITIVE_SHADOW_SCHEMA")
        require(all(result[k] is False for k in (
            "source_timestamp_attested", "source_legal_automated_rights_attested",
            "upstream_lineage_independence_attested", "source_PIT_attested",
            "can_create_PRIMARY", "can_register_R92", "can_enable_G9",
            "production_go","vendor_market_caps_persisted")), "FALSE_PRODUCTION")
    weekly = {"0":{"date":"2026-10-02","value":3000000000000}}
    require(evaluate("EODHD","AAPL","2026-10-09",weekly)["exact_asof_row_count"] == 0,
            "WEEKLY_ROW_CARRY_FORWARD")
    negatives = [
       ("FINNHUB_SYMBOL_MISMATCH","FINNHUB", lambda x: x.update(symbol="APPL")),
       ("FINNHUB_CURRENCY_UNPROVEN","FINNHUB", lambda x: x.update(currency="EUR")),
       ("FINNHUB_ROWS_INVALID","FINNHUB", lambda x: x.update(data=None)),
       ("DUPLICATE_DAY_OR_CONFLICT","FINNHUB", lambda x: x["data"].append(copy.deepcopy(x["data"][0]))),
       ("INVALID_MARKET_CAP","FINNHUB", lambda x: x["data"][0].update(marketCapitalization=float("nan"))),
       ("INVALID_MARKET_CAP","FINNHUB", lambda x: x["data"][0].update(marketCapitalization=True)),
       ("FUTURE_DATA_INCLUDED","FINNHUB", lambda x: x["data"][0].update(atDate="2026-10-12")),
       ("ROW_DATE_BAD","FINNHUB", lambda x: x["data"][0].update(atDate="2026-10-9")),
       ("EODHD_INDEX_INVALID","EODHD", lambda x: x.update({"missing":{"date":"2026-10-08","value":2}})),
       ("EODHD_INDEX_DISCONTIGUOUS","EODHD", lambda x: x.update({"2":{"date":"2026-10-08","value":2}})),
       ("FUTURE_DATA_INCLUDED","EODHD", lambda x: x["0"].update(date="2026-10-10")),
       ("INVALID_MARKET_CAP","EODHD", lambda x: x["0"].update(value=-1)),
       ("ROW_NOT_OBJECT","EODHD", lambda x: x.update({"0":None})),
    ]
    for code, vendor, mut in negatives:
        d = copy.deepcopy(a if vendor == "FINNHUB" else b)
        mut(d)
        try: evaluate(vendor,"AAPL","2026-10-09",d)
        except ValueError as e:
            require(code in str(e), "WRONG_FAILURE:" + code)
        else: raise RuntimeError("UNSAFE_VENDOR_ROW_ACCEPTED:" + code)
    for vendor,sym,asof,data in (("UNKNOWN","AAPL","2026-10-09",a),
                                 ("FINNHUB","","2026-10-09",a),
                                 ("FINNHUB","AAPL","2026-99-09",a)):
        try: evaluate(vendor,sym,asof,data)
        except ValueError: pass
        else: raise RuntimeError("INVALID_METADATA_ACCEPTED")
    print("XRAY_MC_VENDOR_SHADOW_SELFTEST=PASS_2_SHADOW_1_WEEKLY_16_NEGATIVE_OPTIMIZER_SAFE_NO_PRIMARY")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if not args.selftest:
        raise SystemExit("ONLY_SELFTEST; LICENSED_CALLER_MUST_SUPPLY_EPHEMERAL_RESPONSE")
    selftest()


if __name__ == "__main__":
    main()
