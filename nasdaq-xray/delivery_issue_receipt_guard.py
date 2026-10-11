#!/usr/bin/env python3
"""Verify a REAL GitHub Issue receipt against a pre-authorized R92 body.

A GitHub Issue receipt is backup issue persistence ONLY. It never attests a
ChatGPT/email/mobile delivery, user reading the message, or trade execution.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

REPO="gokaydonmez39-jpg/kripto-radar"

def text_normalize(value):
    if not isinstance(value,str):return None
    return value.replace("\r\n","\n").rstrip("\n")

def validate_receipt(issue, *, issue_number, delivery_key, symbol, expected_body):
    """No partial or ambiguous Issue can be marked backup delivered."""
    if (not isinstance(issue,dict) or
        type(issue_number) is not int or issue_number<=0 or
        not isinstance(delivery_key,str) or not delivery_key or
        not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9.\\-]{1,12}",symbol)):
        return False,"ISSUE_OR_DELIVERY_IDENTITY_INVALID"
    if type(issue.get("number")) is not int or issue["number"]!=issue_number:
        return False,"ISSUE_NUMBER_MISMATCH"
    exact_title="[XRAY RESEARCH AL ADAYI] "+symbol+" — "+delivery_key
    if issue.get("title")!=exact_title:
        return False,"ISSUE_TITLE_OR_KEY_MISMATCH"
    try:target=urlparse(issue.get("url") or "")
    except (TypeError,ValueError):
        return False,"ISSUE_URL_MALFORMED"
    if (target.scheme!="https" or target.netloc!="github.com"
        or target.path!="/"+REPO+"/issues/"+str(issue_number)
        or target.query or target.fragment or target.username or target.password):
        return False,"ISSUE_REPO_URL_MISMATCH"
    normalized_expected=text_normalize(expected_body)
    normalized_actual=text_normalize(issue.get("body"))
    if not normalized_expected or normalized_actual!=normalized_expected:
        return False,"ISSUE_BODY_EXACT_MISMATCH"
    if (normalized_expected.count("Delivery key: `"+delivery_key+"`")!=1
        or normalized_expected.count("Symbol: **"+symbol+"**")!=1
        or "EXECUTION: **NONE**" not in normalized_expected
        or "REAL_MONEY: **NO-GO**" not in normalized_expected):
        return False,"ISSUE_BODY_SEMANTIC_BINDING_INVALID"
    return True,"BACKUP_ISSUE_EXACT_CONTENT_AND_URL_VERIFIED_NO_USER_RECEIPT"

def selftest():
    key="XRAY|2026-10-09|AAPL|R92_01"
    symbol="AAPL"
    body=("# XRAY RESEARCH AL ADAYI\n\n"
          "- Delivery key: `"+key+"`\n"
          "- Symbol: **"+symbol+"**\n"
          "- EXECUTION: **NONE**\n- REAL_MONEY: **NO-GO**\n")
    good={"number":123,"title":"[XRAY RESEARCH AL ADAYI] "+symbol+" — "+key,
          "body":body,"url":"https://github.com/"+REPO+"/issues/123"}
    assert validate_receipt(good,issue_number=123,delivery_key=key,
                            symbol=symbol,expected_body=body)[0]
    cases=[
        dict(good,number=122),
        dict(good,title=good["title"]+" FAKE"),
        dict(good,title=good["title"].replace("AAPL","MSFT")),
        dict(good,url=good["url"].replace(REPO,"attacker/repo")),
        dict(good,url="http://github.com/"+REPO+"/issues/123"),
        dict(good,url=good["url"]+"?template=1"),
        dict(good,body=body.replace("R92_01","R92_02")),
        dict(good,body=body.replace("REAL_MONEY: **NO-GO**","REAL_MONEY: **GO**")),
        dict(good,body=body[:-17]),
    ]
    for i,bad in enumerate(cases):
        assert not validate_receipt(bad,issue_number=123,delivery_key=key,
                                    symbol=symbol,expected_body=body)[0],i
    assert not validate_receipt(good,issue_number=124,delivery_key=key,
                                symbol=symbol,expected_body=body)[0]
    assert not validate_receipt(good,issue_number=123,delivery_key="",
                                symbol=symbol,expected_body=body)[0]
    assert not validate_receipt(good,issue_number=123,delivery_key=key,
                                symbol="BAD SYMBOL",expected_body=body)[0]
    assert not validate_receipt(good,issue_number=123,delivery_key=key,
                                symbol=symbol,expected_body=body+"new field\n")[0]
    assert validate_receipt(dict(good,body=body.replace("\n","\r\n")),
                            issue_number=123,delivery_key=key,
                            symbol=symbol,expected_body=body)[0]
    print("XRAY_BACKUP_ISSUE_RECEIPT_SELFTEST=PASS_13_NEGATIVE_AND_CRLF_NO_PHONE_CLAIM")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--issue-json",type=Path)
    parser.add_argument("--issue-number",type=int)
    parser.add_argument("--delivery-key")
    parser.add_argument("--symbol")
    parser.add_argument("--body-file",type=Path)
    a=parser.parse_args()
    if a.selftest:
        selftest();return
    if not all((a.issue_json,a.issue_number,a.delivery_key,a.symbol,a.body_file)):
        parser.error("Issue JSON, positive number, key, symbol and body file required")
    try:
        issue=json.loads(a.issue_json.read_text(encoding="utf-8"))
        body=a.body_file.read_text(encoding="utf-8")
    except (OSError,ValueError,UnicodeError) as exc:
        raise SystemExit("XRAY_BACKUP_ISSUE_RECEIPT=UNREADABLE:"+type(exc).__name__)
    valid,reason=validate_receipt(issue,issue_number=a.issue_number,
                                 delivery_key=a.delivery_key,
                                 symbol=a.symbol,expected_body=body)
    print("XRAY_BACKUP_ISSUE_RECEIPT="+reason)
    if not valid:raise SystemExit(2)

if __name__=="__main__":
    main()
