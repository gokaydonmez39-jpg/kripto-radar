#!/usr/bin/env python3
"""Alpaca free 15-min delayed SIP research canary; zero strict G9/ACCOUNT/AL authority."""
import argparse,datetime as dt,json,os,pathlib,urllib.error,urllib.parse,urllib.request
SYMBOLS=("AAPL","PLTR","MSTR")
def valid(q,now):
    try:
        t=dt.datetime.fromisoformat(str(q["t"]).replace("Z","+00:00"))
        if t.tzinfo is None:return False
        age=(now-t).total_seconds()
        return 900<=age<=14400 and 0<float(q["bp"])<=float(q["ap"]) and float(q["bs"])>0 and float(q["as"])>0 and bool(q["bx"]) and bool(q["ax"])
    except (KeyError,TypeError,ValueError,OverflowError):return False
def classify(doc,now):
    if not isinstance(doc,dict) or not isinstance(doc.get("quotes"),dict):return "UNKNOWN_SCHEMA",0
    q=doc["quotes"]
    if set(q)!=set(SYMBOLS):return "UNKNOWN_COVERAGE",0
    n=sum(valid(q[k],now) for k in SYMBOLS)
    return ("DELAYED_SIP_RESEARCH_ONLY_COHERENT" if n==3 else "UNKNOWN_QUOTE_OR_DELAY"),n
def historical_url(symbol, now):
    """Free-tier historical SIP; never query the subscription-only recent SIP window."""
    if symbol not in SYMBOLS or now.tzinfo is None:
        raise ValueError("INVALID_SYMBOL_OR_UNAWARE_CLOCK")
    start=(now-dt.timedelta(minutes=60)).astimezone(dt.timezone.utc).replace(microsecond=0)
    end=(now-dt.timedelta(minutes=17)).astimezone(dt.timezone.utc).replace(microsecond=0)
    args=urllib.parse.urlencode({
        "feed":"sip","start":start.isoformat().replace("+00:00","Z"),
        "end":end.isoformat().replace("+00:00","Z"),"sort":"desc","limit":1})
    return "https://data.alpaca.markets/v2/stocks/"+symbol+"/quotes?"+args

def extract_historical_quote(doc,symbol,now):
    if not isinstance(doc,dict) or doc.get("symbol")!=symbol:
        return None
    rows=doc.get("quotes")
    if not isinstance(rows,list) or len(rows)!=1:
        return None
    quote=rows[0]
    return quote if isinstance(quote,dict) and valid(quote,now) else None

def selftest():
    now=dt.datetime(2026,10,8,15,30,tzinfo=dt.timezone.utc)
    q={"t":(now-dt.timedelta(minutes=18)).isoformat(),"bp":9,"ap":10,"bs":1,"as":2,"bx":"Q","ax":"P"}
    assert valid(q,now)
    assert not valid(dict(q,t=now.isoformat()),now)
    assert not valid(dict(q,t=(now-dt.timedelta(hours=8)).isoformat()),now)
    assert not valid(dict(q,bp=11),now)
    assert not valid(dict(q,bx=""),now)
    assert not valid(dict(q,bs=0),now)
    assert classify({"quotes":{k:q for k in SYMBOLS}},now)==("DELAYED_SIP_RESEARCH_ONLY_COHERENT",3)
    assert classify({"quotes":{"AAPL":q}},now)[0]=="UNKNOWN_COVERAGE"
    assert classify({"quotes":{k:dict(q,ap=0) for k in SYMBOLS}},now)[0]=="UNKNOWN_QUOTE_OR_DELAY"
    url=historical_url("AAPL",now)
    parsed=urllib.parse.urlparse(url)
    params=urllib.parse.parse_qs(parsed.query)
    assert parsed.path=="/v2/stocks/AAPL/quotes"
    assert params["feed"]==["sip"] and params["sort"]==["desc"] and params["limit"]==["1"]
    assert params["end"]==["2026-10-08T15:13:00Z"]
    assert params["start"]==["2026-10-08T14:30:00Z"]
    assert extract_historical_quote({"symbol":"AAPL","quotes":[q]},"AAPL",now)==q
    assert extract_historical_quote({"symbol":"MSFT","quotes":[q]},"AAPL",now) is None
    assert extract_historical_quote({"symbol":"AAPL","quotes":[dict(q,bp=11)]},"AAPL",now) is None
    assert extract_historical_quote({"symbol":"AAPL","quotes":[q,q]},"AAPL",now) is None
    assert extract_historical_quote({"symbol":"AAPL","quotes":[]},"AAPL",now) is None
    try:
        historical_url("INVALID",now)
    except ValueError:
        pass
    else:
        raise AssertionError("INVALID_SYMBOL_ACCEPTED")
    print("XRAY_HISTORICAL_SIP_FAIL_CLOSED_SELFTEST=PASS cases=19")

def run(path):
    status="BLOCKED_MISSING_ALPACA_KEYS";observed=0
    kid=os.getenv("XRAY_ALPACA_API_KEY_ID","").strip()
    sec=os.getenv("XRAY_ALPACA_API_SECRET_KEY","").strip()
    if kid and sec:
        now=dt.datetime.now(dt.timezone.utc)
        quotes={}
        for symbol in SYMBOLS:
            request=urllib.request.Request(historical_url(symbol,now),
                headers={"APCA-API-KEY-ID":kid,"APCA-API-SECRET-KEY":sec,"Accept":"application/json"})
            try:
                with urllib.request.urlopen(request,timeout=15) as resp:
                    body=resp.read(160001)
                if len(body)>160000:
                    status="UNKNOWN_OVERSIZE";break
                quote=extract_historical_quote(json.loads(body),symbol,now)
                if quote is None:
                    status="UNKNOWN_HISTORICAL_SIP_SCHEMA_OR_STALE";break
                quotes[symbol]=quote
            except urllib.error.HTTPError as e:
                status="BLOCKED_HTTP_"+str(e.code);break
            except (OSError,ValueError,TimeoutError) as e:
                status="UNKNOWN_TRANSPORT_"+type(e).__name__;break
        else:
            status,observed=classify({"quotes":quotes},now)
    out={"schema":"XRAY_DELAYED_SIP_HEALTH_V1","status":status,"valid_count":observed,
         "expected_count":3,"source_role":"NONCANONICAL_ALPACA_DELAYED_SIP_SHADOW",
         "retrieval_mode":"HISTORICAL_SIP_END_17_MINUTES_AGO",
         "execution":"NONE","real_money":"NO-GO","policy":"C4.17","strict_g9_pass":False,
         "account_pass":False,"alpha_authority":False,"r92_created":False,
         "vendor_quotes_persisted":False,"orders":[]}
    pathlib.Path(path).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_HISTORICAL_SIP="+status)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    a=p.parse_args()
    if a.selftest:selftest()
    elif a.out:run(a.out)
    else:p.error("--out required")
