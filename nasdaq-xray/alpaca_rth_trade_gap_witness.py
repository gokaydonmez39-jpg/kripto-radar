#!/usr/bin/env python3
"""Bounded Alpaca historical SIP trade *presence* witness for missing RTH slots.

One HTTP GET per official 30-minute gap. No raw vendor trade, price, size,
trade ID, URL, timestamp or credential in public artifacts. A trade sample is
NOT proof of eligible RTH volume, corrected tape or a canonical PRICE PASS.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

from alpaca_rth_minute_integrity_shadow import official_window

SCHEMA="XRAY_ALPACA_HISTORICAL_SIP_TRADE_GAP_WITNESS_V1"
STATES=frozenset({
    "TRADE_RECORD_PRESENT_AGGREGATE_BAR_MISSING_RESEARCH_ONLY",
    "NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN",
    "TRADE_QUERY_PAGINATED_INCOMPLETE_UNKNOWN",
    "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN",
    "TRADE_VENDOR_NULL_TRADES_UNKNOWN",
    "TRADE_DOCUMENT_OR_LENGTH_INVALID_UNKNOWN",
    "TRADE_TIMESTAMP_INVALID_UNKNOWN",
    "TRADE_PRICE_OR_SIZE_INVALID_UNKNOWN",
    "TRADE_ID_INVALID_OR_DUPLICATE_UNKNOWN",
    "TRADE_CONDITIONS_INVALID_UNKNOWN",
    "TRADE_PAGINATION_INVALID_UNKNOWN",
    "TRADE_HTTP_401_403_NOT_ENTITLED",
    "TRADE_HTTP_429_THROTTLED",
    "TRADE_HTTP_OTHER_UNKNOWN",
    "TRADE_TRANSPORT_UNKNOWN",
    "TRADE_SCOPE_REJECTED_NO_CALL",
})
MAX_BYTES=320000
MAX_TRADES=250
SYMBOL=re.compile(r"[A-Z][A-Z0-9.\\-]{0,12}")


def probe(symbol,slot,asof,credentials,opener=urllib.request.urlopen):
    """Return enumerated result ONLY, making at most one bounded read call."""
    if (type(symbol) is not str or SYMBOL.fullmatch(symbol) is None or
        type(slot) is not dt.datetime or slot.tzinfo is None or
        slot.utcoffset() is None or type(asof) is not str or
        type(credentials) is not tuple or len(credentials)!=2 or
        any(type(v) is not str or not v for v in credentials)):
        return "TRADE_SCOPE_REJECTED_NO_CALL"
    try:
        from zoneinfo import ZoneInfo
        day=slot.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        start,close,length=official_window(day)
        if (length not in (210,390) or day>asof or
            not (start<=slot and slot+dt.timedelta(minutes=30)<=close) or
            (slot-start)%dt.timedelta(minutes=30)!=dt.timedelta(0)):
            return "TRADE_SCOPE_REJECTED_NO_CALL"
    except (KeyError,ValueError,TypeError,OverflowError):
        return "TRADE_SCOPE_REJECTED_NO_CALL"
    end=slot+dt.timedelta(minutes=30)
    def fmt(value):
        return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00","Z")
    params={
        "start":fmt(slot),
        "end":fmt(end-dt.timedelta(microseconds=1)),
        "feed":"sip",
        "sort":"asc",
        "limit":str(MAX_TRADES),
        "asof":asof,
    }
    url="https://data.alpaca.markets/v2/stocks/"+symbol+"/trades?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "APCA-API-KEY-ID":credentials[0],
        "APCA-API-SECRET-KEY":credentials[1],
        "Accept":"application/json",
        "User-Agent":"XRAY-ReadOnly-RTH-TradePresence/1.0",
    })
    try:
        with opener(req,timeout=22) as response:
            if response.status!=200:
                return "TRADE_HTTP_OTHER_UNKNOWN"
            bb=response.read(MAX_BYTES+1)
        if len(bb)>MAX_BYTES:
            return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
        source=json.loads(bb)
        if (type(source) is not dict or
            source.get("symbol") not in (None,symbol)):
            return "TRADE_DOCUMENT_OR_LENGTH_INVALID_UNKNOWN"
        if source.get("trades") is None:
            # Null/missing is not an empty list and NEVER means no trades.
            return "TRADE_VENDOR_NULL_TRADES_UNKNOWN"
        if (type(source["trades"]) is not list or
            len(source["trades"])>MAX_TRADES):
            return "TRADE_DOCUMENT_OR_LENGTH_INVALID_UNKNOWN"
        trades=source["trades"]
        seen=set()
        for row in trades:
            if type(row) is not dict:
                return "TRADE_DOCUMENT_OR_LENGTH_INVALID_UNKNOWN"
            timestamp=row.get("t")
            price=row.get("p")
            size=row.get("s")
            ident=row.get("i")
            if type(timestamp) is not str:
                return "TRADE_TIMESTAMP_INVALID_UNKNOWN"
            if (type(price) not in (int,float) or
                not math.isfinite(price) or price<=0 or
                type(size) is not int or size<=0):
                return "TRADE_PRICE_OR_SIZE_INVALID_UNKNOWN"
            if type(ident) is not int or ident<0:
                return "TRADE_ID_INVALID_OR_DUPLICATE_UNKNOWN"
            try:
                when=dt.datetime.fromisoformat(timestamp.replace("Z","+00:00"))
            except (ValueError,TypeError,OverflowError):
                return "TRADE_TIMESTAMP_INVALID_UNKNOWN"
            if (when.tzinfo is None or
                not slot<=when.astimezone(dt.timezone.utc)<end):
                return "TRADE_TIMESTAMP_INVALID_UNKNOWN"
            key=(row.get("x"),ident)
            if key in seen:
                return "TRADE_ID_INVALID_OR_DUPLICATE_UNKNOWN"
            seen.add(key)
            conditions=row.get("c")
            if conditions is not None and (
                type(conditions) is not list or
                any(type(flag) is not str for flag in conditions)):
                return "TRADE_CONDITIONS_INVALID_UNKNOWN"
        token=source.get("next_page_token")
        if token is not None and (type(token) is not str or
                                  not token or len(token)>2048):
            return "TRADE_PAGINATION_INVALID_UNKNOWN"
        if trades:
            # Even with pagination, only presence is observed; NO volume sums.
            return "TRADE_RECORD_PRESENT_AGGREGATE_BAR_MISSING_RESEARCH_ONLY"
        if token is not None:
            return "TRADE_QUERY_PAGINATED_INCOMPLETE_UNKNOWN"
        return "NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN"
    except urllib.error.HTTPError as err:
        if err.code in (401,403):
            return "TRADE_HTTP_401_403_NOT_ENTITLED"
        if err.code==429:
            return "TRADE_HTTP_429_THROTTLED"
        return "TRADE_HTTP_OTHER_UNKNOWN"
    except (urllib.error.URLError,OSError,TimeoutError):
        return "TRADE_TRANSPORT_UNKNOWN"
    except (ValueError,KeyError,TypeError,OverflowError):
        return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"


def selftest():
    """Assertions deliberately remain active under python -O."""
    from alpaca_rth_minute_integrity_shadow import official_window
    import copy
    start,close,n=official_window("2026-10-14")
    slot=start+dt.timedelta(minutes=150)
    def check(ok,code):
        if not ok:raise AssertionError("XRAY_TRADE_PRINT_"+code)
    check(n==390,"OFFICIAL_SESSION")
    calls=[]
    class Response:
        status=200
        def __init__(self,obj):self.data=json.dumps(obj).encode()
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,n):return self.data[:n]
    def responder(obj):
        def opener(request,timeout):
            calls.append(request)
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
            check(q.get("feed")==["sip"] and
                  q.get("limit")==[str(MAX_TRADES)] and
                  q.get("asof")==["2026-10-14"] and
                  "PASSWORD" not in request.full_url and timeout==22,
                  "AUTH_AND_REQUEST_PARAMETERS")
            return Response(obj)
        return opener
    tr={"i":1,"t":(slot+dt.timedelta(seconds=12)).isoformat(),
        "p":25.5,"s":100,"x":"Q","c":["@"]}
    auth=("FAKE_ID","PASSWORD")
    positive={"symbol":"AAA","trades":[tr],"next_page_token":None}
    check(probe("AAA",slot,"2026-10-14",auth,responder(positive))==
          "TRADE_RECORD_PRESENT_AGGREGATE_BAR_MISSING_RESEARCH_ONLY",
          "POSITIVE_NOT_PRIMARY")
    check(probe("AAA",slot,"2026-10-14",auth,responder({
          "symbol":"AAA","trades":[],"next_page_token":None}))==
          "NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN","EMPTY_NOT_ZERO")
    check(probe("AAA",slot,"2026-10-14",auth,responder({
          "symbol":"AAA","trades":[],"next_page_token":"MORE"}))==
          "TRADE_QUERY_PAGINATED_INCOMPLETE_UNKNOWN","PAGINATION_NOT_COMPLETE")
    for mutation,code in (
        (lambda o:o["trades"][0].update(s=0),"TRADE_PRICE_OR_SIZE_INVALID_UNKNOWN"),
        (lambda o:o["trades"][0].update(p=float("nan")),"TRADE_PRICE_OR_SIZE_INVALID_UNKNOWN"),
        (lambda o:o["trades"][0].update(t=close.isoformat()),"TRADE_TIMESTAMP_INVALID_UNKNOWN"),
        (lambda o:o["trades"][0].update(i="bad"),"TRADE_ID_INVALID_OR_DUPLICATE_UNKNOWN"),
        (lambda o:o["trades"].append(copy.deepcopy(o["trades"][0])),"TRADE_ID_INVALID_OR_DUPLICATE_UNKNOWN"),
        (lambda o:o.update(symbol="OTHER"),"TRADE_DOCUMENT_OR_LENGTH_INVALID_UNKNOWN"),
        (lambda o:o["trades"][0].update(c=["@",4]),"TRADE_CONDITIONS_INVALID_UNKNOWN"),
        (lambda o:o.update(trades=None),"TRADE_VENDOR_NULL_TRADES_UNKNOWN"),
        (lambda o:o.update(next_page_token=123),"TRADE_PAGINATION_INVALID_UNKNOWN"),
    ):
        bad=copy.deepcopy(positive);mutation(bad)
        check(probe("AAA",slot,"2026-10-14",auth,responder(bad))==code,
              "MALFORMED_VENDOR_ROW_CLASSIFIED_EXACTLY")
    before=len(calls)
    for sym,timestamp,asof in (
        ("../BAD",slot,"2026-10-14"),
        ("AAA",close,"2026-10-14"),
        ("AAA",slot,"2026-10-13"),
    ):
        check(probe(sym,timestamp,asof,auth,responder(positive))==
              "TRADE_SCOPE_REJECTED_NO_CALL","FORGED_OR_STALE_SCOPE")
    check(len(calls)==before,"NO_CALL_WHEN_SCOPE_INVALID")
    check(len(STATES)==16,"STATUS_CLOSED_ENUMERATION")
    print("XRAY_RTH_TRADE_GAP_WITNESS_SELFTEST=PASS_3_DIAGNOSTICS_12_NEGATIVES_PYTHON_O_SAFE_NO_ALPHA")


if __name__=="__main__":
    selftest()
