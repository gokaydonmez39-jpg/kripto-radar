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
            source.get("symbol") not in (None,symbol) or
            type(source.get("trades")) is not list or
            len(source["trades"])>MAX_TRADES):
            return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
        trades=source["trades"]
        seen=set()
        for row in trades:
            if type(row) is not dict:
                return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
            timestamp=row.get("t")
            price=row.get("p")
            size=row.get("s")
            ident=row.get("i")
            if (type(timestamp) is not str or
                type(price) not in (int,float) or not math.isfinite(price) or price<=0 or
                type(size) is not int or size<=0 or
                type(ident) is not int or ident<0):
                return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
            when=dt.datetime.fromisoformat(timestamp.replace("Z","+00:00"))
            if (when.tzinfo is None or
                not slot<=when.astimezone(dt.timezone.utc)<end):
                return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
            key=(row.get("x"),ident)
            if key in seen:
                return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
            seen.add(key)
            conditions=row.get("c")
            if conditions is not None and (
                type(conditions) is not list or
                any(type(flag) is not str for flag in conditions)):
                return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
        token=source.get("next_page_token")
        if token is not None and (type(token) is not str or not token or len(token)>2048):
            return "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN"
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
    from alpaca_rth_minute_integrity_shadow import official_window
    start,close,n=official_window("2026-10-14")
    slot=start+dt.timedelta(minutes=30*5)
    assert n==390
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
            assert q["feed"]==["sip"] and q["limit"]==[str(MAX_TRADES)]
            assert q["asof"]==["2026-10-14"]
            assert "PASSWORD" not in request.full_url
            assert timeout==22
            return Response(obj)
        return opener
    tr={"i":1,"t":(slot+dt.timedelta(seconds=12)).isoformat(),
        "p":25.5,"s":100,"x":"Q","c":["@"]}
    auth=("FAKE_ID","PASSWORD")
    present={"symbol":"AAA","trades":[tr],"next_page_token":None}
    assert probe("AAA",slot,"2026-10-14",auth,responder(present))==(
        "TRADE_RECORD_PRESENT_AGGREGATE_BAR_MISSING_RESEARCH_ONLY")
    assert probe("AAA",slot,"2026-10-14",auth,responder({
        "symbol":"AAA","trades":[],"next_page_token":None}))==(
        "NO_TRADE_RECORD_RETURNED_STILL_UNKNOWN")
    assert probe("AAA",slot,"2026-10-14",auth,responder({
        "symbol":"AAA","trades":[],"next_page_token":"MORE"}))==(
        "TRADE_QUERY_PAGINATED_INCOMPLETE_UNKNOWN")
    import copy
    for mutation in (
        lambda o:o["trades"][0].update(s=0),
        lambda o:o["trades"][0].update(p=float("nan")),
        lambda o:o["trades"][0].update(t=close.isoformat()),
        lambda o:o["trades"][0].update(i="bad"),
        lambda o:o["trades"].append(copy.deepcopy(o["trades"][0])),
        lambda o:o.update(symbol="OTHER"),
        lambda o:o["trades"][0].update(c=["@",4]),
    ):
        bad=copy.deepcopy(present);mutation(bad)
        assert probe("AAA",slot,"2026-10-14",auth,responder(bad))==(
            "TRADE_SCHEMA_OR_INTEGRITY_UNKNOWN")
    before=len(calls)
    for sym,timestamp,asof in (
        ("../BAD",slot,"2026-10-14"),
        ("AAA",close,"2026-10-14"),
        ("AAA",slot,"2026-10-13"),
    ):
        assert probe(sym,timestamp,asof,auth,responder(present))==(
            "TRADE_SCOPE_REJECTED_NO_CALL")
    assert len(calls)==before
    assert len(STATES)==9
    print("XRAY_RTH_TRADE_GAP_WITNESS_SELFTEST=PASS_3_DIAGNOSTICS_10_NEGATIVES_NO_ALPHA")


if __name__=="__main__":
    selftest()
