#!/usr/bin/env python3
"""SEC-only one-request connectivity diagnostic; no market data or primary authority.

SEC User-Agent stays in an encrypted GitHub Actions Secret and is never logged,
stored, hashed or included in witnesses. Missing contact is an explicit BLOCKED,
never a false success and never permission to replace it with a public value.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import urllib.error
import urllib.request

URL = "https://data.sec.gov/submissions/CIK0000789019.json"  # public Microsoft issuer canary
CAP = 8_000_000
SCHEMA = "XRAY_SEC_SINGLE_OFFICIAL_ISSUER_TRANSPORT_PREFLIGHT_V1"

def valid_contact(text):
    return (
        type(text) is str and 16 <= len(text) <= 180
        and not any(c in text for c in "\r\n\t")
        and text == text.strip()
        and re.search(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])",text) is not None
        and "${{" not in text
    )

def preflight(contact, fetch=None):
    base = {
        "schema": SCHEMA,
        "sec_transport": "BLOCKED_OPERATOR_SECRET_MISSING",
        "contact_configured": False,
        "contact_syntactically_valid": False,
        "sec_single_request_attempted": False,
        "sec_issuer_cik_proven": False,
        "sec_transport_full_universe_attested": False,
        "sec_asof_nine_issuers_attested": False,
        "market_data_non_display_entitlement_attested": False,
        "primary_price_dv30_authority": False,
        "primary_mc_authority": False,
        "r92_created": False,
        "device_delivery_receipt_attested": False,
        "execution": "NONE",
        "real_money": "NO-GO",
        "unknown_never_pass": True,
    }
    if not contact:
        return base
    base["contact_configured"] = True
    if not valid_contact(contact):
        base["sec_transport"] = "BLOCKED_OPERATOR_SECRET_FORMAT"
        return base
    base["contact_syntactically_valid"] = True
    base["sec_single_request_attempted"] = True
    try:
        if fetch is None:
            fetch = fetch_one
        data = fetch(contact)
        if (type(data) is not dict or data.get("cik") != 789019
                or type(data.get("tickers")) is not list
                or "MSFT" not in data["tickers"]
                or type(data.get("name")) is not str):
            base["sec_transport"] = "BLOCKED_SEC_RESPONSE_WRONG_CIK_OR_SCHEMA"
            return base
        base["sec_issuer_cik_proven"] = True
        base["sec_transport"] = "SEC_ONE_PUBLIC_ISSUER_REACHABLE_RESEARCH_ONLY"
    except urllib.error.HTTPError as exc:
        base["sec_transport"] = (
            "BLOCKED_SEC_HTTP_403" if exc.code == 403 else
            "BLOCKED_SEC_HTTP_429" if exc.code == 429 else
            "BLOCKED_SEC_HTTP_OTHER")
    except (TimeoutError, urllib.error.URLError, OSError):
        base["sec_transport"] = "BLOCKED_SEC_NETWORK_OR_TIMEOUT"
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        base["sec_transport"] = "BLOCKED_SEC_RESPONSE_INVALID_OR_OVERSIZE"
    return base

def fetch_one(contact):
    req = urllib.request.Request(
        URL,
        headers={"User-Agent":contact,"Accept":"application/json",
                 "Accept-Encoding":"identity"})
    with urllib.request.urlopen(req,timeout=18) as response:
        if response.geturl() != URL:
            raise ValueError("SEC_REDIRECT_NOT_EXACT_OFFICIAL_URL")
        body = response.read(CAP+1)
    if len(body)>CAP:
        raise ValueError("SEC_RESPONSE_CAP_EXCEEDED")
    return json.loads(body.decode("utf-8"))

def selftest():
    good = "XRAY private research operator-contact@example.org"
    assert valid_contact(good)
    for invalid in ("","unknown","XRAY anonymous research",
                    "XRAY contact@example.org\nSecret: junk",
                    " ${{ vars.XRAY_SEC_USER_AGENT }} ",
                    "XRAY foo@example.org\tinvalid"):
        assert not valid_contact(invalid), "INVALID_CONTACT_ACCEPTED"
    mock = lambda _:{"cik":789019,"tickers":["MSFT"],"name":"MICROSOFT CORPORATION"}
    a = preflight(good,mock)
    assert a["sec_transport"]=="SEC_ONE_PUBLIC_ISSUER_REACHABLE_RESEARCH_ONLY"
    assert a["sec_issuer_cik_proven"] is True
    assert preflight("",mock)["sec_single_request_attempted"] is False
    assert preflight("missing@example.com\n",mock)["sec_single_request_attempted"] is False
    for bad in (
        {"cik":789019,"tickers":["AAPL"],"name":"bad"},
        {"cik":789020,"tickers":["MSFT"],"name":"bad"},
        {"cik":789019,"tickers":"MSFT","name":"bad"},
        {"cik":789019,"tickers":["MSFT"],"name":None},
        {"cik":789019,"tickers":["msft"],"name":"bad"},
    ):
        b = preflight(good,lambda _:bad)
        assert b["sec_transport"]=="BLOCKED_SEC_RESPONSE_WRONG_CIK_OR_SCHEMA"
    for item in [a,preflight("",mock),preflight("bad",mock)]:
        for key in ("sec_transport_full_universe_attested",
                    "sec_asof_nine_issuers_attested",
                    "market_data_non_display_entitlement_attested",
                    "primary_price_dv30_authority","primary_mc_authority",
                    "r92_created","device_delivery_receipt_attested"):
            assert item[key] is False, "FALSE_CANONICAL_PROMOTION_" + key
        assert "operator-contact" not in json.dumps(item)
        assert item["execution"]=="NONE" and item["real_money"]=="NO-GO"
    print("XRAY_SEC_CANARY_SELFTEST=PASS_MISSING_SECRET_6_INVALID_CONTACTS_5_WRONG_ISSUERS_NO_FALSE_MC")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    report=preflight(os.environ.get("XRAY_SEC_USER_AGENT",""))
    # No user agent, email, request or response body may enter stdout.
    print("XRAY_SEC_SINGLE_REQUEST="+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
