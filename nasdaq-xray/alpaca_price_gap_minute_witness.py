#!/usr/bin/env python3
"""One missing 30Min SIP RTH slot -> one private 1Min SIP witness request.

Research source disagreement only. One minute bar from the SAME Alpaca SIP
feed can prove that 30Min source aggregation was incomplete, but is NOT an
independent venue, closing-auction, correction, trade-condition, rights or
C4.17 DV30 witness. Never repair or synthesize the missing 30Min OHLCV.
No identity, timestamp, quotes, or credentials may leave process memory.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from alpaca_rth_minute_integrity_shadow import official_window
from alpaca_sip_30min_rth_lower_bound_pilot import stamp

SLOT=dt.timedelta(minutes=30)
MAX_BODY_BYTES=150000
SYMBOL_RE=re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")
WITNESS_CODES={
    "MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW",
    "MINUTE_NO_BAR_OBSERVED_STILL_UNKNOWN",
    "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN",
    "MINUTE_GLOBAL_BUDGET_BLOCKED",
}

def missing_first_slot(half,days):
    """No replacement data; compute first official RTH 30m start not observed."""
    if not isinstance(half,list) or not isinstance(days,list):
        return None
    expected=set()
    for day in days:
        start,close,n=official_window(day)
        if n not in (210,390) or n%30 or close-start!=dt.timedelta(minutes=n):
            return None
        expected.update(start+SLOT*i for i in range(n//30))
    try:
        stamps=[stamp(b) for b in half]
    except (ValueError,TypeError,KeyError,OverflowError):
        return None
    if len(stamps)!=len(set(stamps)):
        return None
    missing=sorted(expected-set(stamps))
    return missing[0] if missing else None

def observe(symbol,slot,asof,credentials,counter,limit,
            urlopen=urllib.request.urlopen):
    """One request maximum; private result is enum only. Never turns UNKNOWN PASS."""
    if (not isinstance(symbol,str) or not SYMBOL_RE.fullmatch(symbol)
        or not isinstance(slot,dt.datetime) or slot.tzinfo is None
        or slot.utcoffset() is None
        or not isinstance(asof,str) or not isinstance(credentials,tuple)
        or len(credentials)!=2 or not all(isinstance(v,str) and v for v in credentials)
        or not isinstance(counter,list) or len(counter)!=1
        or type(counter[0]) is not int or type(limit) is not int
        or not 0<=counter[0]<=limit):
        return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
    try:
        official_day=slot.astimezone(dt.timezone.utc)
        # Requested window is exactly one RTH 30Min interval. Return nothing
        # for any off-exchange timestamps or mismatched completed session.
        from zoneinfo import ZoneInfo
        day=official_day.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        start,close,n=official_window(day)
        if day>asof or not (start<=slot<close and
                           (slot-start)%SLOT==dt.timedelta(0) and slot+SLOT<=close):
            return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
    except (ValueError,TypeError,OverflowError):
        return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
    if counter[0]>=limit:
        return "MINUTE_GLOBAL_BUDGET_BLOCKED"
    end=slot+SLOT-dt.timedelta(minutes=1)
    params={
        "start":slot.astimezone(dt.timezone.utc).isoformat().replace("+00:00","Z"),
        "end":end.astimezone(dt.timezone.utc).isoformat().replace("+00:00","Z"),
        "timeframe":"1Min","feed":"sip","adjustment":"raw",
        "sort":"asc","limit":"1000","asof":asof,
    }
    url="https://data.alpaca.markets/v2/stocks/"+symbol+"/bars?"+urllib.parse.urlencode(params)
    headers={"APCA-API-KEY-ID":credentials[0],
             "APCA-API-SECRET-KEY":credentials[1],
             "Accept":"application/json",
             "User-Agent":"NASDAQ-XRAY-ReadOnly-Price-Reconciliation/1.0"}
    counter[0]+=1
    try:
        req=urllib.request.Request(url,headers=headers)
        with urlopen(req,timeout=22) as response:
            if response.status!=200:
                return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
            raw=response.read(MAX_BODY_BYTES+1)
        if len(raw)>MAX_BODY_BYTES:
            return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
        doc=json.loads(raw)
        if (type(doc) is not dict or not isinstance(doc.get("bars"),list)
                or doc.get("next_page_token") is not None
                or (doc.get("symbol") is not None and doc["symbol"]!=symbol)):
            return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
        bars=doc["bars"]
        if len(bars)>30:
            return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
        seen=set()
        for bar in bars:
            if type(bar) is not dict:
                return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
            t=stamp(bar)
            if (t<slot or t>slot+SLOT-dt.timedelta(minutes=1)
                or t.second!=0 or t.microsecond!=0 or t in seen
                or type(bar.get("v")) is not int or bar["v"]<=0):
                return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"
            seen.add(t)
        return ("MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW" if bars else
                "MINUTE_NO_BAR_OBSERVED_STILL_UNKNOWN")
    except (ValueError,KeyError,TypeError,OverflowError,
            urllib.error.URLError,TimeoutError,OSError):
        return "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"

def selftest():
    from unittest.mock import patch
    start,close,n=official_window("2026-10-14")
    slot=start+SLOT
    expected=[start+SLOT*i for i in range(n//30)]
    valid=[{"t":t.isoformat(),"v":10} for t in expected[1:]]
    assert missing_first_slot(valid,["2026-10-14"])==start
    assert missing_first_slot([{"t":t.isoformat(),"v":10} for t in expected],
                              ["2026-10-14"]) is None
    assert missing_first_slot([{"t":"bad","v":10}],["2026-10-14"]) is None
    assert missing_first_slot([valid[0],valid[0]],["2026-10-14"]) is None
    calls=[]
    class Response:
        status=200
        def __init__(self,doc):self.body=json.dumps(doc).encode()
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):return self.body[:n]
    def fake(req,timeout):
        calls.append(req)
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        assert q["timeframe"]==["1Min"] and q["feed"]==["sip"]
        assert q["adjustment"]==["raw"] and q["asof"]==["2026-10-14"]
        assert q["start"]==[slot.isoformat().replace("+00:00","Z")]
        assert q["end"]==[(slot+dt.timedelta(minutes=29)).isoformat().replace("+00:00","Z")]
        assert "FAKE_SECRET" not in req.full_url
        return Response({"symbol":"AAA","bars":[{"t":slot.isoformat(),"v":123}],
                         "next_page_token":None})
    count=[0]
    assert observe("AAA",slot,"2026-10-14",("FAKE_KEY","FAKE_SECRET"),
                   count,2,fake)=="MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW"
    assert count==[1] and len(calls)==1
    assert observe("AAA",slot,"2026-10-14",("FAKE_KEY","FAKE_SECRET"),
                   count,1,fake)=="MINUTE_GLOBAL_BUDGET_BLOCKED"
    assert count==[1] and len(calls)==1
    assert observe("AAA",slot,"2026-10-14",("",""),[0],1,fake)==(
        "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN")
    assert observe("../SECRET",slot,"2026-10-14",("a","b"),[0],1,fake)==(
        "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN")
    assert observe("AAA",close,"2026-10-14",("a","b"),[0],1,fake)==(
        "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN")
    def reply(data):
        return lambda *_a,**_kw:Response(data)
    for doc,category in [
        ({"symbol":"AAA","bars":[],"next_page_token":None},
         "MINUTE_NO_BAR_OBSERVED_STILL_UNKNOWN"),
        ({"symbol":"AAA","bars":[{"t":slot.isoformat(),"v":3}],
          "next_page_token":"MORE"},"MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"),
        ({"symbol":"ZZZ","bars":[],"next_page_token":None},
         "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"),
        ({"symbol":"AAA","bars":[{"t":slot.isoformat(),"v":0}],
          "next_page_token":None},"MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"),
        ({"symbol":"AAA","bars":[{"t":slot.isoformat(),"v":3}]*2,
          "next_page_token":None},"MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"),
        ({"symbol":"AAA","bars":[{"t":(slot+SLOT).isoformat(),"v":3}],
          "next_page_token":None},"MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN"),
    ]:
        assert observe("AAA",slot,"2026-10-14",("a","b"),[0],1,reply(doc))==category
    assert WITNESS_CODES=={
        "MINUTE_BAR_PRESENT_COARSE_BAR_MISSING_SHADOW",
        "MINUTE_NO_BAR_OBSERVED_STILL_UNKNOWN",
        "MINUTE_TRANSPORT_OR_SCHEMA_UNKNOWN",
        "MINUTE_GLOBAL_BUDGET_BLOCKED",
    }
    print("XRAY_PRICE_1MIN_PRIVATE_WITNESS_SELFTEST=PASS_SOURCE_BOUND_ONE_CALL_6_NEGATIVE_BUDGET_PRIVACY_NO_ALPHA")

if __name__=="__main__":
    selftest()
