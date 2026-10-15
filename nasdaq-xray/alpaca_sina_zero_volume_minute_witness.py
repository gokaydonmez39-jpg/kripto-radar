#!/usr/bin/env python3
"""Symbol-local, one-off 1Min SIP witness for a zero-volume daily HISTORY bar.

Zero daily volume is a reason to withhold 260/52 HISTORY, not a zero-trading
attestation. One minute with a positive SIP volume on the same official day
shows a vendor granularity inconsistency. The SAME provider is not independent
primary source authority. Do not reconstruct or promote HISTORY bars.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from alpaca_rth_minute_integrity_shadow import official_window
from alpaca_free_sip_shadow_guard import timestamp_date
from alpaca_sip_30min_rth_lower_bound_pilot import stamp

MAX_BYTES=280000
SRE=re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")
WITNESS_CODES={
    "MINUTE_POSITIVE_DAILY_ZERO_DISCREPANCY_SHADOW",
    "MINUTE_NO_RTH_BARS_STILL_UNKNOWN",
    "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN",
    "MINUTE_HTTP_400_INVALID_REQUEST",
    "MINUTE_HTTP_401_403_DENIED",
    "MINUTE_HTTP_429_THROTTLED",
    "MINUTE_HTTP_OTHER_ERROR",
    "MINUTE_NETWORK_OR_TIMEOUT",
    "MINUTE_OFFICIAL_ZERO_DAY_UNVERIFIED",
}

def zero_day(rows,days):
    """Return newest zero-daily-volume official session, never a trading claim."""
    if type(rows) is not list or type(days) is not list:
        return None
    eligible=set(days)
    found=[]
    try:
        for row in rows:
            if type(row) is not dict:
                return None
            if type(row.get("v")) is int and row["v"]==0:
                day=timestamp_date(row["t"]).isoformat()
                if day not in eligible:
                    return None
                found.append(day)
    except (ValueError,TypeError,KeyError,OverflowError):
        return None
    return sorted(found)[-1] if found else None

def observe(symbol,day,asof,creds,urlopen=urllib.request.urlopen):
    if (type(symbol) is not str or SRE.fullmatch(symbol) is None
        or type(day) is not str or type(asof) is not str
        or type(creds) is not tuple or len(creds)!=2
        or not all(type(x) is str and x for x in creds)
        or day>asof):
        return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
    try:
        start,close,minutes=official_window(day)
        if minutes not in (210,390) or not start<close:
            return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
    except (ValueError,TypeError,OverflowError):
        return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
    params={
        "timeframe":"1Min","feed":"sip","adjustment":"raw",
        "limit":"500","sort":"asc","asof":asof,
        "start":start.isoformat().replace("+00:00","Z"),
        "end":(close-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z"),
    }
    url="https://data.alpaca.markets/v2/stocks/"+symbol+"/bars?"+urllib.parse.urlencode(params)
    try:
        req=urllib.request.Request(url,headers={
            "APCA-API-KEY-ID":creds[0],
            "APCA-API-SECRET-KEY":creds[1],
            "Accept":"application/json",
            "User-Agent":"NASDAQ-XRAY-ReadOnly-Sina-Exception-Witness/1.0"})
        with urlopen(req,timeout=22) as reply:
            if reply.status!=200:
                return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
            raw=reply.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
        doc=json.loads(raw)
        if (type(doc) is not dict or type(doc.get("bars")) is not list
            or (doc.get("symbol") is not None and doc["symbol"]!=symbol)
            or doc.get("next_page_token") is not None
            or len(doc["bars"])>minutes):
            return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
        seen=set()
        for bar in doc["bars"]:
            if type(bar) is not dict:
                return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
            at=stamp(bar)
            if (not(start<=at<close) or at.second!=0
                or at.microsecond!=0 or at in seen
                or type(bar.get("v")) is not int or bar["v"]<=0):
                return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"
            seen.add(at)
        return ("MINUTE_POSITIVE_DAILY_ZERO_DISCREPANCY_SHADOW" if seen
                else "MINUTE_NO_RTH_BARS_STILL_UNKNOWN")
    except urllib.error.HTTPError as error:
        # No response text, URL, provider timestamp or credentials are logged.
        if error.code==400:
            return "MINUTE_HTTP_400_INVALID_REQUEST"
        if error.code in (401,403):
            return "MINUTE_HTTP_401_403_DENIED"
        if error.code==429:
            return "MINUTE_HTTP_429_THROTTLED"
        return "MINUTE_HTTP_OTHER_ERROR"
    except (urllib.error.URLError,TimeoutError,OSError):
        return "MINUTE_NETWORK_OR_TIMEOUT"
    except (ValueError,TypeError,KeyError,OverflowError):
        return "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"

def selftest():
    from alpaca_free_sip_shadow_guard import EST
    from unittest.mock import patch
    day="2026-10-14"
    daily={"t":dt.datetime(2026,10,14,tzinfo=EST).isoformat(),
           "o":10,"h":11,"l":9,"c":10,"v":0}
    assert zero_day([daily],[day])==day
    assert zero_day([dict(daily,v=1)],[day]) is None
    assert zero_day([dict(daily,t="2026-10-14T13:30:00Z")],[day]) is None
    start,close,minutes=official_window(day)
    class Reply:
        status=200
        def __init__(self,obj): self.body=json.dumps(obj).encode()
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def read(self,n):return self.body[:n]
    seen=[]
    def fake(req,timeout):
        seen.append(req.full_url)
        args=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        assert args["feed"]==["sip"] and args["timeframe"]==["1Min"]
        assert args["asof"]==[day] and args["adjustment"]==["raw"]
        assert args["start"]==[start.isoformat().replace("+00:00","Z")]
        assert args["end"]==[(close-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z")]
        assert "SECRET" not in req.full_url
        return Reply({"symbol":"AAA","bars":[{"t":start.isoformat(),"v":7}],
                      "next_page_token":None})
    assert observe("AAA",day,day,("KEY","SECRET"),fake)==(
        "MINUTE_POSITIVE_DAILY_ZERO_DISCREPANCY_SHADOW")
    assert len(seen)==1
    assert observe("../SECRET",day,day,("KEY","SECRET"),fake)==(
        "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN")
    assert len(seen)==1
    for rows,expected in [
        ([],"MINUTE_NO_RTH_BARS_STILL_UNKNOWN"),
        ([{"t":start.isoformat(),"v":0}],"MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"),
        ([{"t":start.isoformat(),"v":1}]*2,"MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"),
        ([{"t":close.isoformat(),"v":1}],"MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"),
        ([{"t":start.isoformat(),"v":True}],"MINUTE_SCHEMA_OR_SCOPE_UNKNOWN"),
    ]:
        def getter(req,timeout):
            return Reply({"symbol":"AAA","bars":rows,"next_page_token":None})
        assert observe("AAA",day,day,("KEY","SECRET"),getter)==expected
    def paged(req,timeout):
        return Reply({"symbol":"AAA","bars":[],"next_page_token":"other"})
    assert observe("AAA",day,day,("KEY","SECRET"),paged)==(
        "MINUTE_SCHEMA_OR_SCOPE_UNKNOWN")
    for code,expected in [
        (400,"MINUTE_HTTP_400_INVALID_REQUEST"),
        (403,"MINUTE_HTTP_401_403_DENIED"),
        (429,"MINUTE_HTTP_429_THROTTLED"),
        (500,"MINUTE_HTTP_OTHER_ERROR"),
    ]:
        def failed(req,timeout,code=code):
            raise urllib.error.HTTPError(req.full_url,code,"private",{},None)
        assert observe("AAA",day,day,("KEY","SECRET"),failed)==expected
    def offline(req,timeout):
        raise urllib.error.URLError("private")
    assert observe("AAA",day,day,("KEY","SECRET"),offline)==(
        "MINUTE_NETWORK_OR_TIMEOUT")
    print("XRAY_SINA_DAILY_ZERO_MINUTE_SELFTEST=PASS_ONE_BOUND_SESSION_POSITIVE_NEGATIVES_NO_RAW_NO_PRIMARY")

if __name__=="__main__":
    selftest()
