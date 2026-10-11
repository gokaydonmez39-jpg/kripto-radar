#!/usr/bin/env python3
"""Hard negative evidence: Massive ticker MC is NOT an independent MC oracle.

Vendor ticker overview MARKET_CAP = weighted_shares_outstanding * selected
ticker's close. Different listed classes sharing a CIK may have different
close prices, so ticker-specific market cap is not a unique class-weighted
issuer valuation. Vendor reference date can use SEC period end, which is
not independent filing acceptance PIT. This guard is research-only; all
outputs keep production MC, HISTORY, AL/R92 and GO disabled.
No downloaded vendor prices/shares are embedded in tests or archived.
"""
from __future__ import annotations
import argparse
import math

SCHEMA="XRAY_MULTICLASS_TICKER_MC_NON_INDEPENDENCE_GUARD_V1"
EPS=1e-9

def require(ok,why):
    if not ok:raise ValueError("XRAY_MC_TICKER_CAP_NONINDEPENDENCE:"+why)

def positive(v):
    if isinstance(v,bool) or type(v) not in (int,float) or not math.isfinite(v) or v<=0:
        return None
    return float(v)

def audit(records, decision_asof):
    require(isinstance(decision_asof,str) and len(decision_asof)==10,
            "DECISION_DATE_ABSENT")
    require(isinstance(records,list) and 1<=len(records)<=4,
            "INVALID_RESEARCH_SCOPE")
    if any(type(row) is not dict for row in records):
        raise ValueError("XRAY_MC_TICKER_CAP_NONINDEPENDENCE:BAD_ROW")
    issuer_ids={row.get("cik") for row in records}
    require(len(issuer_ids)==1 and all(
        isinstance(x,str) and len(x)==10 and x.isdigit() for x in issuer_ids),
        "NOT_ONE_OFFICIAL_ISSUER")
    names=[x.get("ticker") for x in records]
    require(len(names)==len(set(names)) and all(
        isinstance(x,str) and 1<=len(x)<=12 for x in names),
        "INVALID_TICKER_OR_DUPLICATE")
    closes=[]
    for row in records:
        weighted=positive(row.get("weighted_shares"))
        cap=positive(row.get("reported_cap"))
        close=positive(row.get("external_SIP_close"))
        require(weighted is not None and cap is not None and close is not None,
                "MISSING_REAL_NUMERIC_PROOF")
        require(row.get("asof_et")==decision_asof and
                row.get("price_asof_et")==decision_asof and
                row.get("primary_exchange")=="XNAS",
                "SOURCE_SESSION_OR_EXCHANGE_DRIFT")
        require(abs(cap-weighted*close)/cap<=EPS,
                "VENDOR_MARKET_CAP_NOT_REPRODUCIBLE")
        closes.append(close)
    multilateral=len(records)>=2
    different_closes=max(closes)!=min(closes)
    return {
        "schema":SCHEMA,"asof_et":decision_asof,
        "same_issuer_different_listed_class_prices":multilateral and different_closes,
        "vendor_formula_matches_external_session_close":True,
        "independent_issuer_cap_observation":False,
        "SEC_pit_filing_acceptance_from_vendor_ticker_overview_attested":False,
        "class_weighted_issuer_cap_verified":False,
        "result":("SHADOW_MULTICLASS_REFERENCE_CAPS_NON_UNIQUE"
                  if multilateral and different_closes else
                  "SHADOW_PROVIDER_WEIGHTED_PRICE_FORMULA_ONLY"),
        "C417_PRIMARY_MC_created":0,"canonical_HISTORY_PASS_created":0,
        "R92_created":False,"GO":False,
        "raw_vendor_price_or_shares_persisted":False,
        "execution":"NONE","real_money":"NO-GO"
    }

def selftest():
    # Deliberately fabricated symbols and observations, not vendor OHLCV.
    one={"cik":"0000001234","ticker":"TESTA",
         "weighted_shares":1000,"reported_cap":10000.,
         "external_SIP_close":10.,"asof_et":"2026-10-09",
         "price_asof_et":"2026-10-09","primary_exchange":"XNAS"}
    two=dict(one,ticker="TESTC",reported_cap=11000.,external_SIP_close=11.)
    o=audit([one,two],"2026-10-09")
    require(o["same_issuer_different_listed_class_prices"] is True and
            o["independent_issuer_cap_observation"] is False and
            o["C417_PRIMARY_MC_created"]==0 and
            o["result"]=="SHADOW_MULTICLASS_REFERENCE_CAPS_NON_UNIQUE",
            "MULTICLASS_NONUNIQUENESS_POSITIVE")
    s=audit([one],"2026-10-09")
    require(s["result"]=="SHADOW_PROVIDER_WEIGHTED_PRICE_FORMULA_ONLY"
            and s["C417_PRIMARY_MC_created"]==0,"SINGLE_CLASS_NOT_AUTOPASS")
    checks=[
        ("WRONG_CIK",dict(two,cik="0000001235")),
        ("NO_SIP_PRICE",dict(two,external_SIP_close=None)),
        ("WRONG_FORMULA",dict(two,reported_cap=11001.)),
        ("DIFFERENT_ASOF",dict(two,asof_et="2026-10-08")),
        ("DIFFERENT_PRICE_ASOF",dict(two,price_asof_et="2026-10-08")),
        ("DIFFERENT_EXCHANGE",dict(two,primary_exchange="XNYS")),
        ("INVALID_WEIGHT",dict(two,weighted_shares=0)),
        ("BOOLEAN_CLOSE",dict(two,external_SIP_close=True)),
        ("INFINITE_CAP",dict(two,reported_cap=float("inf")))
    ]
    for label,bad in checks:
        try:audit([one,bad],"2026-10-09")
        except ValueError:pass
        else:raise AssertionError("UNSAFE_VENDOR_MC_PROMOTION:"+label)
    print("XRAY_MC_TICKER_CLASS_NONINDEPENDENCE=PASS_2_POSITIVE_9_NEGATIVE_NORMAL_AND_PYTHON_O_NO_GO")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if not args.selftest:raise SystemExit("Research-only selftest: no raw vendor data writing allowed")
    selftest()
