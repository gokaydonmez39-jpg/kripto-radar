#!/usr/bin/env python3
"""Bounded secondary *transport route* for single-symbol SIP minute bars=null.

Call only after a valid HTTP 200 single-symbol document explicitly reports
bars:null. Uses the same provider, feed, timeframe, ASOF and RTH interval via
the multi-symbol /v2/stocks/bars route (one symbol, ONE request, no pagination
replay). It is not an independent data source, trade/auction lineage, DV30
authority, or proof that absent bars mean zero trades/volume.
All vendor rows, identifiers, exact session dates and credentials are ephemeral.
Only a fixed, non-identifying enum leaves the helper.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

from alpaca_minute_source_response_diagnostics import classify_minute_document

MAX_BYTES=300_000
VALID_SYMBOL=re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")
STATUS=frozenset({
    "MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW",
    "MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN",
    "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN",
    "MULTI_ROUTE_HTTP_OR_NETWORK_UNKNOWN",
    "MULTI_ROUTE_INVALID_INPUT_NO_CALL",
})

def probe(symbol, day, asof, credentials, opener=urllib.request.urlopen, *,
          window_start=None, window_end=None):
    if (type(symbol) is not str or VALID_SYMBOL.fullmatch(symbol) is None
        or type(day) is not str or type(asof) is not str
        or type(credentials) is not tuple or len(credentials)!=2
        or any(type(x) is not str or not x for x in credentials)
        or day>asof):
        return "MULTI_ROUTE_INVALID_INPUT_NO_CALL"
    try:
        from alpaca_rth_minute_integrity_shadow import official_window
        start,close,minutes=official_window(day)
        if minutes not in (390,210) or close-start != dt.timedelta(minutes=minutes):
            return "MULTI_ROUTE_INVALID_INPUT_NO_CALL"
        if (window_start is None)!=(window_end is None):
            return "MULTI_ROUTE_INVALID_INPUT_NO_CALL"
        if window_start is not None:
            if (type(window_start) is not dt.datetime
                or type(window_end) is not dt.datetime
                or window_start.tzinfo is None or window_end.tzinfo is None
                or not(start<=window_start<window_end<=close)
                or window_end-window_start!=dt.timedelta(minutes=30)
                or (window_start-start)%dt.timedelta(minutes=30)!=dt.timedelta(0)):
                return "MULTI_ROUTE_INVALID_INPUT_NO_CALL"
            request_start,request_end=window_start,window_end
            expected_max=30
        else:
            request_start,request_end=start,close
            expected_max=minutes
    except (TypeError,ValueError,OverflowError):
        return "MULTI_ROUTE_INVALID_INPUT_NO_CALL"
    args={
        "symbols":symbol,"timeframe":"1Min","feed":"sip",
        "adjustment":"raw","sort":"asc","asof":asof,
        "limit":"1000",
        "start":request_start.isoformat().replace("+00:00","Z"),
        "end":(request_end-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z"),
    }
    url="https://data.alpaca.markets/v2/stocks/bars?"+urllib.parse.urlencode(args)
    request=urllib.request.Request(url,headers={
        "APCA-API-KEY-ID":credentials[0],
        "APCA-API-SECRET-KEY":credentials[1],
        "Accept":"application/json",
        "User-Agent":"NASDAQ-XRAY-ReadOnly-Null-Bar-Route-Compare/1.0"})
    try:
        with opener(request,timeout=22) as resp:
            if resp.status!=200:
                return "MULTI_ROUTE_HTTP_OR_NETWORK_UNKNOWN"
            raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"
        doc=json.loads(raw)
        if (type(doc) is not dict
            or type(doc.get("bars")) is not dict
            or doc.get("next_page_token") is not None
            or any(key != symbol for key in doc["bars"])):
            return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"
        # Missing symbol or a null symbol value never proves zero trading.
        bars=doc["bars"].get(symbol,[])
        if bars is None:
            return "MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN"
        result=classify_minute_document(
            {"bars":bars,"symbol":symbol,"next_page_token":None},
            symbol=symbol,start=request_start,end_exclusive=request_end,max_bars=expected_max,
            present_code="MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW",
            empty_code="MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN")
        if result=="MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW":
            # Verify positive finite OHLC prices, not volume alone.
            for row in bars:
                vals=[row.get(k) for k in ("o","h","l","c")]
                if any(type(x) not in (int,float) or not math.isfinite(x)
                       or x<=0 for x in vals):
                    return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"
                o,h,l,c=vals
                if not (h>=max(o,l,c) and l<=min(o,c)):
                    return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"
            return result
        if result=="MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN":
            return result
        return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError):
        return "MULTI_ROUTE_HTTP_OR_NETWORK_UNKNOWN"
    except (ValueError,TypeError,KeyError,OverflowError):
        return "MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN"

def selftest():
    from alpaca_rth_minute_integrity_shadow import official_window
    start,close,minutes=official_window("2026-10-14")
    bar={"t":start.isoformat(),"o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":15}
    invoked=[]
    class Response:
        status=200
        def __init__(self,body):self.body=json.dumps(body).encode()
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def read(self,n):return self.body[:n]
    def source(body):
        def run(req,timeout):
            invoked.append(req)
            p=urllib.parse.urlsplit(req.full_url)
            q=urllib.parse.parse_qs(p.query)
            assert p.path=="/v2/stocks/bars" and q["symbols"]==["AAA"]
            assert q["timeframe"]==["1Min"] and q["feed"]==["sip"]
            assert q["adjustment"]==["raw"] and q["asof"]==["2026-10-14"]
            assert q["start"]==[start.isoformat().replace("+00:00","Z")]
            assert q["end"]==[(close-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z")]
            assert q["limit"]==["1000"]
            assert "SECRET" not in req.full_url and timeout==22
            return Response(body)
        return run
    auth=("KEY","SECRET")
    def check(payload,code):
        before=len(invoked)
        assert probe("AAA","2026-10-14","2026-10-14",auth,source(payload))==code
        assert len(invoked)==before+1
    check({"bars":{"AAA":[bar]},"next_page_token":None},
          "MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW")
    check({"bars":{},"next_page_token":None},
          "MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN")
    check({"bars":{"AAA":None},"next_page_token":None},
          "MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN")
    check({"bars":{"AAA":[]},"next_page_token":None},
          "MULTI_ROUTE_NO_ELIGIBLE_BAR_OBSERVED_UNKNOWN")
    for bad in (
        {"bars":{"AAA":[bar]},"next_page_token":"PAGE"},
        {"bars":{"BBB":[bar]},"next_page_token":None},
        {"bars":None,"next_page_token":None},
        {"bars":{"AAA":[dict(bar,v=0)]},"next_page_token":None},
        {"bars":{"AAA":[dict(bar,c=float("nan"))]},"next_page_token":None},
        {"bars":{"AAA":[dict(bar,t=close.isoformat())]},"next_page_token":None},
    ):
        check(bad,"MULTI_ROUTE_INCOMPLETE_OR_INVALID_RESPONSE_UNKNOWN")
    before=len(invoked)
    for symbol,day in (("../BAD","2026-10-14"),("AAA","2026-10-11")):
        assert probe(symbol,day,"2026-10-14",auth,source({}))==(
            "MULTI_ROUTE_INVALID_INPUT_NO_CALL")
    assert len(invoked)==before
    def forbidden(req,timeout):
        invoked.append(req)
        raise urllib.error.HTTPError(req.full_url,403,"PRIVATE",{},None)
    assert probe("AAA","2026-10-14","2026-10-14",auth,forbidden)==(
        "MULTI_ROUTE_HTTP_OR_NETWORK_UNKNOWN")
    assert len(invoked)==before+1
    slot=start+dt.timedelta(minutes=30)
    def slot_source(req,timeout):
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        assert q["start"]==[slot.isoformat().replace("+00:00","Z")]
        assert q["end"]==[(slot+dt.timedelta(minutes=29)).isoformat().replace("+00:00","Z")]
        return Response({"bars":{"AAA":[{
            "t":slot.isoformat(),"o":10.0,"h":11.0,"l":9.0,"c":10.5,"v":2
        }]},"next_page_token":None})
    assert probe("AAA","2026-10-14","2026-10-14",auth,slot_source,
                 window_start=slot,window_end=slot+dt.timedelta(minutes=30))==(
                 "MULTI_ROUTE_MINUTE_VALID_BAR_OBSERVED_SHADOW")
    before=len(invoked)
    assert probe("AAA","2026-10-14","2026-10-14",auth,source({}),
                 window_start=slot,window_end=slot+dt.timedelta(minutes=60))==(
                 "MULTI_ROUTE_INVALID_INPUT_NO_CALL")
    assert len(invoked)==before
    assert len(STATUS)==5
    print("XRAY_NULL_BAR_ALTERNATE_ROUTE_SELFTEST=PASS_EXACT_ONE_REQUEST_PER_CALL_4_POSITIVE_6_NEGATIVE_DENIAL_NO_PRIMARY")

if __name__=="__main__":
    selftest()
