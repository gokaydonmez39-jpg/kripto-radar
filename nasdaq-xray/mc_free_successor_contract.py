#!/usr/bin/env python3
"""Strict evidence contract for a hypothetical zero-dollar MC successor.

Research-only shadow test. This does NOT amend C4.17 or create PRIMARY MC.
A provider's financial data may only be used when automated-use rights are
independently documented; user permission is not a vendor license.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import sys
from zoneinfo import ZoneInfo

SCHEMA="XRAY_FREE_MC_SUCCESSOR_EVIDENCE_V1"
KNOWN_EXCHANGES={"XNAS","XNGS","XNMS","XNCM"}
MAX_SHARES_AGE_DAYS=120
MAX_RELATIVE_DIVERGENCE=0.10
MC_FLOOR_USD=2_000_000_000
PASS_BUFFER_USD=2_100_000_000

def finite_positive(v):
    if isinstance(v,bool) or type(v) not in (int,float):
        return None
    x=float(v)
    return x if math.isfinite(x) and x>0 else None

def timestamp(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(dt.timezone.utc) if t.tzinfo is not None else None
    except (ValueError,OverflowError):return None

def evaluate(evidence):
    """Fail closed with explicit reasons; never issue production PASS."""
    reasons=[]
    def require(ok,reason):
        if not ok: reasons.append(reason)
    if not isinstance(evidence,dict):
        evidence={}
    sec=evidence.get("sec") or {}
    price=evidence.get("price") or {}
    actions=evidence.get("corporate_actions") or {}
    identity=evidence.get("identity") or {}
    cross=evidence.get("independent_crosscheck") or {}
    session=evidence.get("official_session") or {}
    asof=str(evidence.get("asof_et") or "")
    cutoff=timestamp(evidence.get("decision_cutoff_utc"))
    try: asof_date=dt.date.fromisoformat(asof)
    except ValueError: asof_date=None
    require(asof_date is not None and cutoff is not None and cutoff.date()==asof_date,
            "INVALID_ASOF_OR_DECISION_CUTOFF")
    # The research decision may be 15 minutes AFTER the market close,
    # but SEC shares must have been PUBLIC no later than the ACTUAL RTH close.
    # Never assume a fixed 16:00 ET close (early closes are 13:00 ET).
    # The upstream adapter must validate the exchange calendar witness.
    market_close=timestamp(session.get("rth_close_utc"))
    local_close=(market_close.astimezone(ZoneInfo("America/New_York"))
                 if market_close is not None else None)
    require(session.get("exchange")=="XNAS"
            and session.get("asof_et")==asof
            and session.get("calendar_source")=="ALPACA_MARKET_CALENDAR"
            and session.get("calendar_verified") is True
            and local_close is not None
            and asof_date is not None
            and local_close.date()==asof_date
            and (local_close.hour,local_close.minute,local_close.second)
                in ((16,0,0),(13,0,0))
            and cutoff is not None and market_close is not None
            and cutoff>=market_close+dt.timedelta(minutes=15),
            "OFFICIAL_RTH_CLOSE_MISSING_OR_INCONSISTENT")
    symbol=identity.get("ticker")
    cik=identity.get("cik")
    require(isinstance(symbol,str) and symbol and symbol==sec.get("ticker")
            and symbol==price.get("ticker"),"TICKER_IDENTITY_NOT_EXACT")
    require(isinstance(cik,str) and cik.isdigit() and len(cik)==10
            and cik==sec.get("cik"),"SEC_CIK_NOT_EXACT")
    require(identity.get("exchange") in KNOWN_EXCHANGES
            and identity.get("exchange")==price.get("exchange")
            and identity.get("official_nasdaq_listing_verified") is True,
            "NASDAQ_LISTING_NOT_OFFICIAL_EXACT")
    require(sec.get("source")=="SEC_EDGAR_OFFICIAL"
            and sec.get("filing_accession_verified") is True
            and sec.get("fact_in_filing_verified") is True,
            "SEC_FILING_FACT_NOT_VERIFIED")
    accepted=timestamp(sec.get("acceptance_utc"))
    require(market_close is not None and accepted is not None
            and accepted<=market_close,
            "PIT_ACCEPTANCE_AFTER_RTH_CLOSE_OR_UNKNOWN")
    try:
        filed=dt.date.fromisoformat(str(sec["filed"]))
        observed=dt.date.fromisoformat(str(sec["observed"]))
    except (ValueError,KeyError,TypeError):filed=observed=None
    require(asof_date is not None and filed is not None and observed is not None
            and observed<=filed<=asof_date
            and 0<=(asof_date-observed).days<=MAX_SHARES_AGE_DAYS,
            "SHARES_NOT_CURRENT_AND_PIT")
    shares=finite_positive(sec.get("shares"))
    require(shares is not None and float(shares).is_integer(),
            "SHARE_COUNT_INVALID")
    require(sec.get("single_tradeable_share_class_proven") is True
            and sec.get("adr_ratio_validated") is True
            and sec.get("multiple_class_ambiguity_resolved") is True,
            "SHARE_CLASS_OR_ADR_RATIO_UNRESOLVED")
    require(actions.get("official_full_interval_coverage") is True
            and actions.get("no_unresolved_split_reverse_split") is True
            and actions.get("issuance_and_buybacks_reconciled") is True,
            "CORPORATE_ACTION_COVERAGE_INCOMPLETE")
    require(price.get("asof_et")==asof
            and price.get("status")=="SETTLED_RTH_CLOSE"
            and price.get("same_asof_official_session_verified") is True
            and price.get("adjustment_basis_matches_shares") is True,
            "PRICE_SESSION_OR_SPLIT_BASIS_UNVERIFIED")
    close=finite_positive(price.get("close_usd"))
    require(close is not None,"PRICE_NOT_FINITE")
    require(price.get("automated_use_entitlement_verified") is True,
            "PRICE_VENDOR_AUTOMATED_ENTITLEMENT_NOT_PROVEN")
    cross_mc=finite_positive(cross.get("market_cap_usd"))
    require(cross.get("ticker")==symbol and cross.get("asof_et")==asof
            and cross.get("independent_lineage_verified") is True
            and cross.get("automated_use_entitlement_verified") is True
            and cross_mc is not None,
            "INDEPENDENT_CROSSCHECK_OR_RIGHTS_UNKNOWN")
    if not reasons:
        derived=shares*close
        if not math.isfinite(derived) or derived<=0:
            reasons.append("DERIVED_MC_INVALID")
        elif abs(derived-cross_mc)/max(derived,cross_mc)>MAX_RELATIVE_DIVERGENCE:
            reasons.append("MC_CONFLICT_GREATER_THAN_10_PERCENT")
        elif min(derived,cross_mc)<PASS_BUFFER_USD:
            reasons.append("BELOW_CONSERVATIVE_PASS_BUFFER_OR_BORDERLINE")
    return {
      "schema":SCHEMA,
      "asof_et":asof,
      "status":"SHADOW_ELIGIBLE_FOR_INDEPENDENT_POLICY_REVIEW" if not reasons else "UNKNOWN",
      "reasons":sorted(set(reasons)),
      "production_authority":False,
      "c417_primary_pass":False,
      "r92_eligible":False,
      "execution":"NONE","real_money":"NO-GO",
      "unknown_never_pass":True
    }

def selftest():
    base={
      "asof_et":"2026-10-08","decision_cutoff_utc":"2026-10-08T20:15:00Z",
      "identity":{"ticker":"TEST","cik":"0000123456","exchange":"XNAS",
                  "official_nasdaq_listing_verified":True},
      "sec":{"ticker":"TEST","cik":"0000123456","source":"SEC_EDGAR_OFFICIAL",
             "filing_accession_verified":True,"fact_in_filing_verified":True,
             "acceptance_utc":"2026-10-01T14:00:00Z",
             "filed":"2026-10-01","observed":"2026-09-30",
             "shares":1_000_000_000,
             "single_tradeable_share_class_proven":True,
             "adr_ratio_validated":True,
             "multiple_class_ambiguity_resolved":True},
      "price":{"ticker":"TEST","asof_et":"2026-10-08","exchange":"XNAS",
               "status":"SETTLED_RTH_CLOSE",
               "same_asof_official_session_verified":True,
               "adjustment_basis_matches_shares":True,
               "close_usd":10.0,"automated_use_entitlement_verified":True},
      "corporate_actions":{"official_full_interval_coverage":True,
               "no_unresolved_split_reverse_split":True,
               "issuance_and_buybacks_reconciled":True},
      "independent_crosscheck":{"ticker":"TEST","asof_et":"2026-10-08",
                "independent_lineage_verified":True,
                "automated_use_entitlement_verified":True,
                "market_cap_usd":10_000_000_000}
    }
    from copy import deepcopy
    # Official session closes are immutable reference witnesses in unit fixtures.
    base["official_session"]={"exchange":"XNAS","asof_et":"2026-10-08",
        "rth_close_utc":"2026-10-08T20:00:00Z",
        "calendar_source":"ALPACA_MARKET_CALENDAR",
        "calendar_verified":True}
    good=evaluate(base)
    assert good["status"]=="SHADOW_ELIGIBLE_FOR_INDEPENDENT_POLICY_REVIEW"
    assert good["c417_primary_pass"] is False and good["r92_eligible"] is False
    # RED: SEC acceptance at 16:07 ET is AFTER the 16:00 RTH close,
    # but BEFORE a 16:15 research read. Never apply post-close shares.
    post_close=deepcopy(base)
    post_close["sec"]["acceptance_utc"]="2026-10-08T20:07:00Z"
    assert evaluate(post_close)["status"]=="UNKNOWN"
    # RED: Black Friday 13:00 ET early close is 18:00 UTC (EST).
    early=deepcopy(base)
    early["asof_et"]=early["price"]["asof_et"]="2026-11-27"
    early["decision_cutoff_utc"]="2026-11-27T18:15:00Z"
    early["official_session"]["asof_et"]="2026-11-27"
    early["official_session"]["rth_close_utc"]="2026-11-27T18:00:00Z"
    early["sec"]["observed"]="2026-11-25"
    early["sec"]["filed"]="2026-11-27"
    early["sec"]["acceptance_utc"]="2026-11-27T18:05:00Z"
    assert evaluate(early)["status"]=="UNKNOWN"
    early["sec"]["acceptance_utc"]="2026-11-27T17:59:00Z"
    assert evaluate(early)["status"]=="SHADOW_ELIGIBLE_FOR_INDEPENDENT_POLICY_REVIEW"
    bad_calendar=deepcopy(base)
    bad_calendar["official_session"]["calendar_verified"]=False
    assert evaluate(bad_calendar)["status"]=="UNKNOWN"
    missing_close=deepcopy(base)
    missing_close["official_session"].pop("rth_close_utc")
    assert evaluate(missing_close)["status"]=="UNKNOWN"
    wrong_date=deepcopy(base)
    wrong_date["official_session"]["asof_et"]="2026-10-07"
    assert evaluate(wrong_date)["status"]=="UNKNOWN"
    negatives=[
      ("sec","acceptance_utc","2026-10-09T00:01:00Z"),
      ("sec","cik","0000000001"),
      ("sec","single_tradeable_share_class_proven",False),
      ("sec","observed","2025-01-01"),
      ("sec","shares",float("nan")),
      ("sec","shares",True),
      ("corporate_actions","no_unresolved_split_reverse_split",False),
      ("corporate_actions","issuance_and_buybacks_reconciled",False),
      ("price","status","UNKNOWN"),
      ("price","asof_et","2026-10-07"),
      ("price","automated_use_entitlement_verified",False),
      ("price","close_usd",0),
      ("independent_crosscheck","independent_lineage_verified",False),
      ("independent_crosscheck","market_cap_usd",6_000_000_000),
      ("independent_crosscheck","market_cap_usd",1_990_000_000),
    ]
    for segment,key,val in negatives:
        case=deepcopy(base)
        case[segment][key]=val
        result=evaluate(case)
        assert result["status"]=="UNKNOWN",(segment,key,result)
        assert result["c417_primary_pass"] is False
    assert evaluate({"asof_et":"2026-10-08"})["status"]=="UNKNOWN"
    print("XRAY_FREE_MC_SUCCESSOR_CONTRACT_SELFTEST=PASS_POSITIVE_16_NEGATIVE_NO_PRIMARY")
if __name__=="__main__":
    if "--selftest" in sys.argv:selftest()
    else:raise SystemExit("Only --selftest is authorized; NO LIVE PRIMARY PROMOTION")
