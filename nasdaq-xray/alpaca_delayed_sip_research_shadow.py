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
def selftest():
    now=dt.datetime(2026,10,8,15,30,tzinfo=dt.timezone.utc)
    q={"t":(now-dt.timedelta(seconds=901)).isoformat(),"bp":9,"ap":10,"bs":1,"as":2,"bx":"Q","ax":"P"}
    assert valid(q,now)
    assert not valid(dict(q,t=now.isoformat()),now)
    assert not valid(dict(q,t=(now-dt.timedelta(hours=8)).isoformat()),now)
    assert not valid(dict(q,bp=11),now)
    assert not valid(dict(q,bx=""),now)
    assert not valid(dict(q,bs=0),now)
    assert classify({"quotes":{k:q for k in SYMBOLS}},now)==("DELAYED_SIP_RESEARCH_ONLY_COHERENT",3)
    assert classify({"quotes":{"AAPL":q}},now)[0]=="UNKNOWN_COVERAGE"
    assert classify({"quotes":{k:dict(q,ap=0) for k in SYMBOLS}},now)[0]=="UNKNOWN_QUOTE_OR_DELAY"
    print("XRAY_DELAYED_SIP_FAIL_CLOSED_SELFTEST=PASS tests=9")
def run(path):
    status="BLOCKED_MISSING_ALPACA_KEYS";observed=0
    kid=os.getenv("XRAY_ALPACA_API_KEY_ID","").strip()
    sec=os.getenv("XRAY_ALPACA_API_SECRET_KEY","").strip()
    if kid and sec:
        qs=urllib.parse.urlencode({"symbols":",".join(SYMBOLS),"feed":"delayed_sip"})
        request=urllib.request.Request("https://data.alpaca.markets/v2/stocks/quotes/latest?"+qs,
            headers={"APCA-API-KEY-ID":kid,"APCA-API-SECRET-KEY":sec,"Accept":"application/json"})
        try:
            with urllib.request.urlopen(request,timeout=15) as resp:
                body=resp.read(160001)
                if len(body)>160000:status="UNKNOWN_OVERSIZE"
                else:status,observed=classify(json.loads(body),dt.datetime.now(dt.timezone.utc))
        except urllib.error.HTTPError as e:status="BLOCKED_HTTP_"+str(e.code)
        except (OSError,ValueError,TimeoutError) as e:status="UNKNOWN_TRANSPORT_"+type(e).__name__
    out={"schema":"XRAY_DELAYED_SIP_HEALTH_V1","status":status,"valid_count":observed,
         "expected_count":3,"source_role":"NONCANONICAL_ALPACA_DELAYED_SIP_SHADOW",
         "execution":"NONE","real_money":"NO-GO","policy":"C4.17","strict_g9_pass":False,
         "account_pass":False,"alpha_authority":False,"r92_created":False,
         "vendor_quotes_persisted":False,"orders":[]}
    pathlib.Path(path).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("XRAY_DELAYED_SIP="+status)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    a=p.parse_args()
    if a.selftest:selftest()
    elif a.out:run(a.out)
    else:p.error("--out required")
