#!/usr/bin/env python3
"""Shared, fail-closed *structural* classification of Alpaca 1Min response.

Input remains entirely in process memory. Output is one fixed enumeration,
never a ticker, timestamp, price, volume, raw provider message, URL or key.
No price reconstruction or PRIMARY authority. Both PRICE 30Min gaps and
HISTORY zero daily-volume sources use the same independently tested contract.
"""
from __future__ import annotations

import datetime as dt

SCHEMA_CODES = frozenset({
    "MINUTE_SCHEMA_DOC_INVALID",
    "MINUTE_SCHEMA_BARS_FIELD_MISSING",
    "MINUTE_SCHEMA_BARS_NULL",
    "MINUTE_SCHEMA_BARS_MAPPING_NOT_LIST",
    "MINUTE_SCHEMA_BARS_SCALAR_NOT_LIST",
    "MINUTE_SCHEMA_SYMBOL_MISMATCH",
    "MINUTE_SCHEMA_UNEXPECTED_PAGE_CURSOR",
    "MINUTE_SCHEMA_BAR_COUNT_EXCEEDED",
    "MINUTE_SCHEMA_ROW_NOT_OBJECT",
    "MINUTE_SCHEMA_TIMESTAMP_PARSE_INVALID",
    "MINUTE_SCHEMA_TIMESTAMP_OUT_OF_WINDOW",
    "MINUTE_SCHEMA_DUPLICATE_TIMESTAMP",
    "MINUTE_SCHEMA_VOLUME_NOT_POSITIVE_INT",
    "MINUTE_SCHEMA_BODY_OVERSIZE",
    "MINUTE_SCHEMA_JSON_INVALID",
    "MINUTE_SCHEMA_PRECHECK_INVALID",
})
EMPTY = "MINUTE_NO_RTH_BARS_STILL_UNKNOWN"


def classify_minute_document(doc, *, symbol, start, end_exclusive,
                             max_bars, present_code, empty_code):
    """Validate the entire returned page before classifying any observed bars."""
    if (type(doc) is not dict):
        return "MINUTE_SCHEMA_DOC_INVALID"
    if "bars" not in doc:
        return "MINUTE_SCHEMA_BARS_FIELD_MISSING"
    if doc["bars"] is None:
        return "MINUTE_SCHEMA_BARS_NULL"
    if type(doc["bars"]) is dict:
        return "MINUTE_SCHEMA_BARS_MAPPING_NOT_LIST"
    if type(doc["bars"]) is not list:
        return "MINUTE_SCHEMA_BARS_SCALAR_NOT_LIST"
    if doc.get("symbol") is not None and doc["symbol"] != symbol:
        return "MINUTE_SCHEMA_SYMBOL_MISMATCH"
    if doc.get("next_page_token") is not None:
        return "MINUTE_SCHEMA_UNEXPECTED_PAGE_CURSOR"
    rows=doc["bars"]
    if len(rows)>max_bars:
        return "MINUTE_SCHEMA_BAR_COUNT_EXCEEDED"
    from alpaca_sip_30min_rth_lower_bound_pilot import stamp
    seen=set()
    for bar in rows:
        if type(bar) is not dict:
            return "MINUTE_SCHEMA_ROW_NOT_OBJECT"
        try:
            at=stamp(bar)
        except (KeyError,ValueError,TypeError,OverflowError):
            return "MINUTE_SCHEMA_TIMESTAMP_PARSE_INVALID"
        if (not(start<=at<end_exclusive)
                or at.second!=0 or at.microsecond!=0):
            return "MINUTE_SCHEMA_TIMESTAMP_OUT_OF_WINDOW"
        if at in seen:
            return "MINUTE_SCHEMA_DUPLICATE_TIMESTAMP"
        seen.add(at)
        v=bar.get("v")
        if type(v) is not int or v<=0:
            return "MINUTE_SCHEMA_VOLUME_NOT_POSITIVE_INT"
    return present_code if seen else empty_code


def selftest():
    t=dt.datetime(2026,10,14,13,30,tzinfo=dt.timezone.utc)
    end=t+dt.timedelta(minutes=30)
    good={"symbol":"AAA","bars":[{"t":t.isoformat(),"v":1}],
          "next_page_token":None}
    kwargs=dict(symbol="AAA",start=t,end_exclusive=end,max_bars=30,
                present_code="PRESENT_SHADOW",empty_code="EMPTY_UNKNOWN")
    assert classify_minute_document(good,**kwargs)=="PRESENT_SHADOW"
    assert classify_minute_document(dict(good,bars=[]),**kwargs)=="EMPTY_UNKNOWN"
    assert classify_minute_document(None,**kwargs)=="MINUTE_SCHEMA_DOC_INVALID"
    assert classify_minute_document(dict(good,bars={}),**kwargs)==(
           "MINUTE_SCHEMA_BARS_MAPPING_NOT_LIST")
    assert classify_minute_document(dict(good,bars=None),**kwargs)==(
           "MINUTE_SCHEMA_BARS_NULL")
    assert classify_minute_document(dict(good,bars=""),**kwargs)==(
           "MINUTE_SCHEMA_BARS_SCALAR_NOT_LIST")
    missing=dict(good)
    del missing["bars"]
    assert classify_minute_document(missing,**kwargs)==(
           "MINUTE_SCHEMA_BARS_FIELD_MISSING")
    assert classify_minute_document(dict(good,symbol="BBB"),**kwargs)=="MINUTE_SCHEMA_SYMBOL_MISMATCH"
    assert classify_minute_document(dict(good,next_page_token="secret"),**kwargs)==(
           "MINUTE_SCHEMA_UNEXPECTED_PAGE_CURSOR")
    assert classify_minute_document(dict(good,bars=good["bars"]*31),**kwargs)==(
           "MINUTE_SCHEMA_BAR_COUNT_EXCEEDED")
    assert classify_minute_document(dict(good,bars=[None]),**kwargs)==(
           "MINUTE_SCHEMA_ROW_NOT_OBJECT")
    assert classify_minute_document(dict(good,bars=[{"t":"bad","v":1}]),**kwargs)==(
           "MINUTE_SCHEMA_TIMESTAMP_PARSE_INVALID")
    assert classify_minute_document(dict(good,bars=[{"t":end.isoformat(),"v":1}]),**kwargs)==(
           "MINUTE_SCHEMA_TIMESTAMP_OUT_OF_WINDOW")
    assert classify_minute_document(dict(good,bars=good["bars"]*2),**kwargs)==(
           "MINUTE_SCHEMA_DUPLICATE_TIMESTAMP")
    for volume in (0,True,3.5,"17",None):
        assert classify_minute_document(
            dict(good,bars=[{"t":t.isoformat(),"v":volume}]),**kwargs)==(
            "MINUTE_SCHEMA_VOLUME_NOT_POSITIVE_INT")
    assert all(s.startswith("MINUTE_SCHEMA_") for s in SCHEMA_CODES)
    assert len(SCHEMA_CODES)==16
    print("XRAY_SHARED_SIP_MINUTE_SCHEMA_SELFTEST=PASS_16_ROOT_REASONS_NULL_VS_MISSING_NO_RAW_NO_PRIMARY")

if __name__=="__main__":
    selftest()
