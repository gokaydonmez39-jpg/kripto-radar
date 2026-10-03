#!/usr/bin/env python3
from __future__ import annotations
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"g9_preauthority_runtime.json"
SYMBOLS=("AAPL","NVDA")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_ts(v):
    if v is None: return None
    try:
        if isinstance(v,(int,float)):
            x=float(v)
            if x>10_000_000_000: x/=1000.0
            return datetime.fromtimestamp(x,tz=timezone.utc)
        s=str(v).strip()
        if s.replace(".","",1).isdigit():
            x=float(s)
            if x>10_000_000_000: x/=1000.0
            return datetime.fromtimestamp(x,tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def is_rth():
    et=datetime.now(ZoneInfo("America/New_York"))
    if et.weekday()>=5: return False
    m=et.hour*60+et.minute
    return 570 <= m < 960

def http_json(method,url,headers=None,payload=None):
    h={"Accept":"application/json",**(headers or {})}
    data=None
    if payload is not None:
        h["Content-Type"]="application/json"
        data=json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode())

def unwrap(j):
    if isinstance(j,dict) and isinstance(j.get("data"),dict):
        return j["data"]
    return j

def validate_triplet(bid,ask,last,qts,tts,utcnow):
    bid=float(bid); ask=float(ask); last=float(last)
    if min(bid,ask,last)<=0 or bid>ask or not qts or not tts:
        raise RuntimeError("INVALID_QUOTE_TRADE")
    qa=(utcnow-qts).total_seconds()
    ta=(utcnow-tts).total_seconds()
    sk=abs((qts-tts).total_seconds())
    if qa<0 or ta<0: raise RuntimeError("FUTURE_TIMESTAMP")
    if qa>60: raise RuntimeError(f"QUOTE_STALE:{qa:.3f}")
    if ta>60: raise RuntimeError(f"TRADE_STALE:{ta:.3f}")
    if sk>15: raise RuntimeError(f"QUOTE_TRADE_SKEW:{sk:.3f}")
    return bid,ask,last,qa,ta,sk

def paper_probe():
    key=os.getenv("PAPER_INVEST_API_KEY","").strip()
    if not key: return {"status":"NOT_CONFIGURED","reason":"PAPER_INVEST_API_KEY_NOT_CONFIGURED","network_attempted":False}
    if not is_rth(): return {"status":"WAITING_RTH","reason":"FRESHNESS_REQUIRES_US_RTH","network_attempted":False}
    try:
        auth=unwrap(http_json("POST","https://api.paperinvest.io/v1/auth/token",payload={"apiKey":key}))
        token=(auth.get("token") or auth.get("access_token") or auth.get("accessToken")) if isinstance(auth,dict) else None
        if not token: raise RuntimeError("AUTH_NO_TOKEN")
        now=datetime.now(timezone.utc); details={}
        for sym in SYMBOLS:
            q=unwrap(http_json("GET",f"https://api.paperinvest.io/v1/market-data/quote/{sym}",headers={"Authorization":f"Bearer {token}"}))
            t=unwrap(http_json("GET",f"https://api.paperinvest.io/v1/market-data/trade/{sym}",headers={"Authorization":f"Bearer {token}"}))
            if not isinstance(q,dict) or not isinstance(t,dict): raise RuntimeError(f"SCHEMA_{sym}")
            qts=parse_ts(q.get("timestamp")); tts=parse_ts(t.get("timestamp"))
            bid,ask,last,qa,ta,sk=validate_triplet(q.get("bid"),q.get("ask"),t.get("price"),qts,tts,now)
            details[sym]={"bid":bid,"ask":ask,"last":last,"quote_timestamp":qts.isoformat(),"trade_timestamp":tts.isoformat(),
                          "quote_age_seconds":round(qa,3),"trade_age_seconds":round(ta,3),"quote_trade_skew_seconds":round(sk,3)}
        return {"status":"TECHNICAL_B_D_PASS_ONLY","network_attempted":True,"provider_claim":"REALTIME_NBBO",
                "technical_evidence":details,"authority_effect":"NONE","g9_pass":False}
    except Exception as e:
        return {"status":"TECHNICAL_FAIL_CLOSED","reason":f"{type(e).__name__}:{str(e)[:220]}","network_attempted":True,"g9_pass":False}

def wealthnow_probe():
    key=os.getenv("WEALTHNOW_API_KEY","").strip()
    if not key: return {"status":"NOT_CONFIGURED","reason":"WEALTHNOW_API_KEY_NOT_CONFIGURED","network_attempted":False}
    if not is_rth(): return {"status":"WAITING_RTH","reason":"FRESHNESS_REQUIRES_US_RTH","network_attempted":False}
    try:
        now=datetime.now(timezone.utc); details={}
        for sym in SYMBOLS:
            url="https://firm.wealthnow.io/api/v3/fundamentals/price_snapshot?"+urllib.parse.urlencode({"ticker":sym})
            j=unwrap(http_json("GET",url,headers={"X-API-Key":key}))
            snap=j.get("snapshot") if isinstance(j,dict) and isinstance(j.get("snapshot"),dict) else j
            if not isinstance(snap,dict): raise RuntimeError(f"SCHEMA_{sym}")
            if str(snap.get("market_session") or snap.get("session") or "").lower()!="regular":
                raise RuntimeError(f"NOT_REGULAR_SESSION_{sym}")
            if snap.get("is_stale") is not False: raise RuntimeError(f"STALE_OR_UNKNOWN_{sym}")
            qts=parse_ts(snap.get("quote_as_of")); tts=parse_ts(snap.get("as_of") or snap.get("time"))
            bid,ask,last,qa,ta,sk=validate_triplet(snap.get("bid"),snap.get("ask"),snap.get("price"),qts,tts,now)
            details[sym]={"bid":bid,"ask":ask,"last":last,"quote_timestamp":qts.isoformat(),"trade_timestamp":tts.isoformat(),
                          "quote_age_seconds":round(qa,3),"trade_age_seconds":round(ta,3),"quote_trade_skew_seconds":round(sk,3),
                          "source":snap.get("source")}
        return {"status":"TECHNICAL_B_D_PASS_ONLY","network_attempted":True,"technical_evidence":details,
                "authority_effect":"NONE","g9_pass":False}
    except Exception as e:
        return {"status":"TECHNICAL_FAIL_CLOSED","reason":f"{type(e).__name__}:{str(e)[:220]}","network_attempted":True,"g9_pass":False}

def main():
    out={
      "schema":"XRAY_G9_PREAUTHORITY_DIAGNOSTIC_V1",
      "generated_at_utc":now_iso(),
      "execution":"NONE","real_money":"NO-GO","alpha_authority":False,"g9_pass":False,
      "purpose":"Technical B/D evidence only. This file can never authorize lineage/entitlement A/C or G9 PASS.",
      "providers":{"PAPER_INVEST":paper_probe(),"WEALTHNOW":wealthnow_probe()},
      "hard_rule":"PREAUTHORITY_DIAGNOSTIC_NEVER_CREATES_PASS"
    }
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"g9_pass":False,"providers":{k:v.get("status") for k,v in out["providers"].items()}},sort_keys=True))

if __name__=="__main__":
    main()
